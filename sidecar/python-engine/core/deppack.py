"""Dep-pack（相依包）— 產 wheelhouse 包 + 離線裝進 per-tool venv 的核心。

對應 docs/platform/modules-independence-and-store-plan.md §6（隨選下載相依包）。

問題：LV(torch ~2GB)、Labeling(ultralytics) 等重模組,對「沒 Python、沒環境」的
終端機器,首次啟動才從 PyPI 線上裝相依——慢、需網路、不可控。dep-pack 把相依預先
`pip download` 成一包 wheelhouse(一堆 .whl)+ 簽記每個 wheel 的 sha256 的 manifest,
讓 agent/商店把它 copy 到裝置;平台再以 `pip --no-index` **離線**裝進隔離 per-tool venv。

本模組職責：
  1. **產包**：`build_wheelhouse()` / CLI tools/build_deppack.py。
  2. **驗證**：`verify_wheelhouse()` 逐檔比對 sha256（防半路被換包 / 損毀）。
  3. **解析裝置端 per-tool 快取**：`prepare_tool_wheelhouse()` 供 tool_deps 自動接線
     （快取存在且驗章通過才回 wheelhouse 路徑；存在但壞掉 → 拋 DepPackError，
     **fail-closed**：不靜默退回連 PyPI，避免裝到被竄改的相依）。

設計刻意與 core/tool_deps.py 解耦方向：deppack 依賴 tool_deps（base_python /
requires_fingerprint），tool_deps 只在執行期 lazy-import deppack（無載入期循環）。
也不 import engine / streamlit，保持純函式可測。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.tool_deps import base_python, requires_fingerprint


# ─── 常數 ──────────────────────────────────────────────────────────────────────

ENV_DEPPACK_CACHE = "CIM_DEPPACK_CACHE"
_DEFAULT_CACHE_DIRNAME = ".deppack-cache"
MANIFEST_FILENAME = "deppack.json"
WHEELS_DIRNAME = "wheels"
SCHEMA_VERSION = 1


class DepPackError(Exception):
    """dep-pack 存在但無法信任（驗章失敗 / requires 不符 / manifest 損毀）。

    這是 **fail-closed 訊號**：呼叫端不可在收到此例外時退回連 PyPI。
    """


# ─── 路徑解析（裝置端 per-tool 快取）────────────────────────────────────────────

def _engine_root() -> Path:
    """engine 根（sidecar/python-engine）——本檔在 core/ 下,上一層即是。"""
    return Path(__file__).resolve().parents[1]


def deppack_cache_root() -> Path:
    """裝置端 dep-pack 快取家目錄。

    預設 ``<engine_root>/.deppack-cache/``;可由 ``CIM_DEPPACK_CACHE`` 覆寫
    （frozen/packaged 必須指向**可寫**資料夾,且**不綁 log-dir**——否則換 log-dir
    會連同失去 wheelhouse,「離線可重用」破功,見設計文件 §6.3）。
    """
    import os  # 局部 import：避免污染模組命名空間,且此函式才需要
    override = os.environ.get(ENV_DEPPACK_CACHE)
    return Path(override) if override else _engine_root() / _DEFAULT_CACHE_DIRNAME


def tool_deppack_dir(tool_id: str) -> Path:
    """單一工具的 dep-pack 目錄：``<cache_root>/<tool_id>/``（含 manifest + wheels/）。"""
    return deppack_cache_root() / tool_id


def tool_wheelhouse_dir(tool_id: str) -> Path:
    """單一工具的 wheelhouse 目錄：``<cache_root>/<tool_id>/wheels/``。"""
    return tool_deppack_dir(tool_id) / WHEELS_DIRNAME


# ─── manifest 型別 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WheelEntry:
    """wheelhouse 內單一 wheel 的指紋。"""

    name: str
    sha256: str
    size: int

    def to_dict(self) -> dict:
        return {"name": self.name, "sha256": self.sha256, "size": self.size}

    @classmethod
    def from_dict(cls, d: dict) -> "WheelEntry":
        return cls(name=str(d["name"]), sha256=str(d["sha256"]), size=int(d["size"]))


@dataclass(frozen=True)
class DepPackManifest:
    """一個 dep-pack 的清單：哪個工具、哪組 requires、目標 ABI、每個 wheel 的雜湊。

    `requires_fingerprint` 讓裝置端能確認「這包就是這組 requires 的」(防裝錯包)。
    `python_tag`/`platform_tag` 供商店 UI 預檢(省下載),最終相容性仍由 pip 自己把關。
    """

    tool_id: str
    requires: list[str]
    requires_fingerprint: str
    python_tag: str
    platform_tag: str
    wheels: list[WheelEntry]
    created_at: str
    schema: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "tool_id": self.tool_id,
            "requires": list(self.requires),
            "requires_fingerprint": self.requires_fingerprint,
            "python_tag": self.python_tag,
            "platform_tag": self.platform_tag,
            "created_at": self.created_at,
            "wheels": [w.to_dict() for w in self.wheels],
        }

    def to_json(self) -> str:
        # canonical：鍵排序固定,跨機器可重算/可 diff
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "DepPackManifest":
        return cls(
            tool_id=str(d["tool_id"]),
            requires=list(d.get("requires", [])),
            requires_fingerprint=str(d["requires_fingerprint"]),
            python_tag=str(d.get("python_tag", "")),
            platform_tag=str(d.get("platform_tag", "")),
            wheels=[WheelEntry.from_dict(w) for w in d.get("wheels", [])],
            created_at=str(d.get("created_at", "")),
            schema=int(d.get("schema", SCHEMA_VERSION)),
        )

    @classmethod
    def from_json(cls, text: str) -> "DepPackManifest":
        return cls.from_dict(json.loads(text))


# ─── 雜湊 / manifest 計算 ───────────────────────────────────────────────────────

def _sha256_file(path: Path) -> tuple[str, int]:
    """串流計算單檔 sha256 + 大小（大檔不一次讀進記憶體）。"""
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _default_python_tag(python_version: str | None) -> str:
    """如 '3.11' → 'cp311';未指定 → 取自當前直譯器。"""
    if python_version:
        parts = python_version.split(".")
        if len(parts) >= 2:
            return f"cp{parts[0]}{parts[1]}"
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def compute_manifest(
    tool_id: str,
    requires: list[str],
    wheels_dir: Path,
    *,
    python_tag: str,
    platform_tag: str,
) -> DepPackManifest:
    """掃 wheels_dir 內所有 .whl,算每檔 sha256,組出 manifest（wheel 依檔名排序）。"""
    wheels_dir = Path(wheels_dir)
    entries: list[WheelEntry] = []
    for whl in sorted(wheels_dir.glob("*.whl")):
        digest, size = _sha256_file(whl)
        entries.append(WheelEntry(name=whl.name, sha256=digest, size=size))
    return DepPackManifest(
        tool_id=tool_id,
        requires=sorted(requires),
        requires_fingerprint=requires_fingerprint(requires),
        python_tag=python_tag,
        platform_tag=platform_tag,
        wheels=entries,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def write_manifest(manifest: DepPackManifest, manifest_path: Path) -> None:
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.to_json(), encoding="utf-8")


def load_manifest(manifest_path: Path) -> DepPackManifest:
    return DepPackManifest.from_json(Path(manifest_path).read_text(encoding="utf-8"))


# ─── 驗證（逐檔 sha256）─────────────────────────────────────────────────────────

def verify_wheelhouse(wheels_dir: Path, manifest: DepPackManifest) -> tuple[bool, list[str]]:
    """逐檔比對 wheels_dir 是否符合 manifest（存在 / 大小 / sha256 / 無多餘檔）。

    回 (ok, errors)。errors 為人類可讀字串清單,ok==True 時為空。
    """
    wheels_dir = Path(wheels_dir)
    errors: list[str] = []
    present = {p.name: p for p in wheels_dir.glob("*.whl")}
    for w in manifest.wheels:
        p = present.get(w.name)
        if p is None:
            errors.append(f"缺少 wheel：{w.name}")
            continue
        digest, size = _sha256_file(p)
        if size != w.size:
            errors.append(f"大小不符：{w.name}（manifest {w.size} / 實際 {size}）")
        if digest != w.sha256:
            errors.append(f"sha256 不符（疑被竄改/損毀）：{w.name}")
    extra = set(present) - {w.name for w in manifest.wheels}
    for name in sorted(extra):
        errors.append(f"manifest 未列的多餘 wheel：{name}")
    return (not errors, errors)


def prepare_tool_wheelhouse(tool_id: str, requires: list[str] | None = None) -> Path | None:
    """裝置端：解析 + 驗證某工具的 dep-pack 快取,回可用的 wheelhouse 目錄。

    - 無此工具的 dep-pack（manifest 不存在）→ 回 None（呼叫端可退回 PyPI / env）。
    - 有 dep-pack 但驗證失敗（sha256 不符 / requires 指紋不符 / manifest 壞）→ 拋
      DepPackError（**fail-closed**：呼叫端不可退回連 PyPI）。
    - 驗證通過 → 回 wheels 目錄（供 `pip --no-index --find-links=<它>` 離線安裝）。
    """
    pack_dir = tool_deppack_dir(tool_id)
    manifest_path = pack_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        return None  # 沒有為這個工具準備 dep-pack

    try:
        manifest = load_manifest(manifest_path)
    except (OSError, ValueError, KeyError) as exc:
        raise DepPackError(f"{tool_id} 的 dep-pack manifest 無法解析：{exc}") from exc

    wheels_dir = pack_dir / WHEELS_DIRNAME
    ok, errors = verify_wheelhouse(wheels_dir, manifest)
    if not ok:
        raise DepPackError(
            f"{tool_id} 的 dep-pack 驗證失敗（拒絕安裝）：" + "；".join(errors[:5])
        )
    if requires is not None and manifest.requires_fingerprint != requires_fingerprint(requires):
        raise DepPackError(
            f"{tool_id} 的 dep-pack 是給不同 requires 的（指紋不符）——請重產對應的 dep-pack"
        )
    return wheels_dir


# ─── 產包（pip download → wheelhouse + manifest）─────────────────────────────────

def _run(cmd: list[str]) -> tuple[bool, str]:
    """執行外部指令,回 (ok, 訊息)。失敗收斂成 (False, stderr 摘要)。"""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, ValueError) as exc:
        return False, f"無法執行 {cmd[0]!r}：{exc}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        tail = "\n".join(err.splitlines()[-15:]) if err else f"exit code {proc.returncode}"
        return False, tail
    return True, (proc.stdout or "").strip()


def build_pip_download_command(
    python_cmd: list[str],
    requires: list[str],
    wheels_dir: Path,
    *,
    platform_tag: str | None = None,
    python_version: str | None = None,
    abi: str | None = None,
    implementation: str = "cp",
    only_binary: bool = True,
) -> list[str]:
    """組裝 `pip download` 指令。

    跨平台產包（在 A 機產給 B 機用）時必須指定 ``--platform/--python-version/--abi``,
    而 pip 規定此時一定要 ``--only-binary=:all:``——故只要指定任一目標標籤就強制 only_binary。
    """
    targeted = bool(platform_tag or python_version or abi)
    if targeted:
        only_binary = True
    cmd = [*python_cmd, "-m", "pip", "download", *requires, "-d", str(wheels_dir)]
    if only_binary:
        cmd += ["--only-binary=:all:"]
    if platform_tag:
        cmd += ["--platform", platform_tag]
    if python_version:
        cmd += ["--python-version", python_version]
    if abi:
        cmd += ["--abi", abi]
    if targeted:
        cmd += ["--implementation", implementation]
    return cmd


def build_wheelhouse(
    tool_id: str,
    requires: list[str],
    dest_root: Path,
    *,
    python_cmd: list[str] | None = None,
    platform_tag: str | None = None,
    python_version: str | None = None,
    abi: str | None = None,
    only_binary: bool = True,
) -> DepPackManifest:
    """為 tool_id 產一個 dep-pack：`pip download` requires 成 wheelhouse + 寫 manifest。

    產出佈局（agent/商店把整個 ``<dest_root>/<tool_id>/`` copy 到裝置的 CIM_DEPPACK_CACHE）：
        <dest_root>/<tool_id>/wheels/*.whl
        <dest_root>/<tool_id>/deppack.json

    pip download 失敗 → 拋 DepPackError（CLI 會印錯誤）。requires 空 → 拋 ValueError。
    """
    requires = [r for r in (requires or []) if r and str(r).strip()]
    if not requires:
        raise ValueError(f"{tool_id} 沒有可下載的 requires（dep-pack 無意義）")

    python_cmd = list(python_cmd) if python_cmd else base_python()
    pack_dir = Path(dest_root) / tool_id
    wheels_dir = pack_dir / WHEELS_DIRNAME
    wheels_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_pip_download_command(
        python_cmd, requires, wheels_dir,
        platform_tag=platform_tag, python_version=python_version,
        abi=abi, only_binary=only_binary,
    )
    ok, msg = _run(cmd)
    if not ok:
        raise DepPackError(f"pip download 失敗：{msg}")

    manifest = compute_manifest(
        tool_id, requires, wheels_dir,
        python_tag=_default_python_tag(python_version),
        platform_tag=platform_tag or "host",
    )
    write_manifest(manifest, pack_dir / MANIFEST_FILENAME)
    return manifest
