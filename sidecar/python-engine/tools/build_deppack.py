"""build_deppack — 產一個工具的 dep-pack（wheelhouse + manifest）。

把工具 plugin.yaml 宣告的 `requires:` 預先 `pip download` 成一包 .whl + 簽記每檔
sha256 的 manifest,供「沒 Python、沒環境」的裝置離線安裝（見
docs/platform/modules-independence-and-store-plan.md §6）。

用法：
    # 從工具資料夾讀 requires（最常用）
    py -3.11 tools/build_deppack.py plugins/lv/modules/app-lv

    # 跨平台產包（在管理機產給工廠 win/cp311 機器用）
    py -3.11 tools/build_deppack.py plugins/lv/modules/app-lv \
        --platform win_amd64 --python-version 3.11 --abi cp311

    # 直接給 requires（免工具資料夾）
    py -3.11 tools/build_deppack.py --tool-id app-lv --requires torch==2.6.0,numpy

產出 <dest>/<tool_id>/{wheels/*.whl, deppack.json}。把整個 <tool_id>/ 資料夾 copy
到裝置的 CIM_DEPPACK_CACHE 下,平台首次啟動該工具即 `pip --no-index` 離線裝。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from core import deppack  # noqa: E402


def _read_plugin_yaml(tool_folder: Path) -> tuple[str | None, list[str]]:
    """從工具資料夾的 plugin.yaml 讀 (id, requires)。讀不到回 (None, [])。"""
    pyaml = tool_folder / "plugin.yaml"
    if not pyaml.exists():
        return None, []
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        raise SystemExit("需要 PyYAML 才能讀 plugin.yaml；請 `pip install pyyaml` 或改用 --requires")
    data = yaml.safe_load(pyaml.read_text(encoding="utf-8")) or {}
    requires = [str(r).strip() for r in (data.get("requires") or []) if str(r).strip()]
    return data.get("id"), requires


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="產一個工具的 dep-pack（wheelhouse + manifest）")
    p.add_argument("tool_folder", nargs="?",
                   help="工具資料夾（含 plugin.yaml），用來讀 id 與 requires")
    p.add_argument("--tool-id", help="工具 id（省略則取自 plugin.yaml；無資料夾時必填）")
    p.add_argument("--requires", default="",
                   help="逗號分隔的 requires，覆蓋 plugin.yaml（如 'torch==2.6.0,numpy'）")
    p.add_argument("--dest", default=str(ENGINE_DIR / "release" / "deppacks"),
                   help="產出根目錄（預設 release/deppacks，已 gitignore）")
    p.add_argument("--platform", dest="platform_tag",
                   help="目標平台標籤（如 win_amd64）；跨平台產包必填")
    p.add_argument("--python-version", dest="python_version",
                   help="目標 Python 版本（如 3.11）；跨平台產包必填")
    p.add_argument("--abi", help="目標 ABI（如 cp311）；跨平台產包建議填")
    p.add_argument("--allow-sdist", action="store_true",
                   help="允許 sdist（預設只收 wheel；跨平台一律只能 wheel）")
    p.add_argument("--dry-run", action="store_true",
                   help="只解析 requires 並印出將執行的 pip download 指令，不真的下載")
    args = p.parse_args(argv)

    requires: list[str] = []
    tool_id = args.tool_id
    if args.tool_folder:
        folder = Path(args.tool_folder)
        if not folder.is_dir():
            raise SystemExit(f"找不到工具資料夾：{folder}")
        yid, requires = _read_plugin_yaml(folder)
        tool_id = tool_id or yid or folder.name
    if args.requires:
        requires = [r.strip() for r in args.requires.split(",") if r.strip()]

    if not tool_id:
        raise SystemExit("缺 --tool-id（且未從 plugin.yaml 取得 id）")
    if not requires:
        raise SystemExit(f"{tool_id} 沒有 requires，無需產 dep-pack（plugin.yaml 未宣告或為空）")

    print(f"[deppack] 工具 {tool_id}：下載 {len(requires)} 個 requires → {args.dest}")
    print(f"[deppack] requires = {requires}")

    if args.dry_run:
        wheels_dir = Path(args.dest) / tool_id / deppack.WHEELS_DIRNAME
        cmd = deppack.build_pip_download_command(
            deppack.base_python(), requires, wheels_dir,
            platform_tag=args.platform_tag, python_version=args.python_version,
            abi=args.abi, only_binary=not args.allow_sdist,
        )
        print("[deppack] (dry-run) 將執行：")
        print("   " + " ".join(cmd))
        return 0

    try:
        manifest = deppack.build_wheelhouse(
            tool_id, requires, Path(args.dest),
            platform_tag=args.platform_tag,
            python_version=args.python_version,
            abi=args.abi,
            only_binary=not args.allow_sdist,
        )
    except deppack.DepPackError as exc:
        raise SystemExit(f"[deppack] 失敗：{exc}")

    total_mb = sum(w.size for w in manifest.wheels) / (1024 * 1024)
    pack_dir = Path(args.dest) / tool_id
    print(f"[deppack] ✅ 完成：{len(manifest.wheels)} 個 wheel，共 {total_mb:.1f} MB")
    print(f"[deppack]    python_tag={manifest.python_tag} platform_tag={manifest.platform_tag}")
    print(f"[deppack]    輸出：{pack_dir}")
    print(f"[deppack] 裝置端安裝：把整個 {tool_id}/ 資料夾 copy 到該機 CIM_DEPPACK_CACHE 下，")
    print(f"[deppack]    首次啟動該工具時平台會驗章後 `pip --no-index` 離線裝進 per-tool venv。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
