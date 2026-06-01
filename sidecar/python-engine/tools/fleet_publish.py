"""Fleet 發布 CLI（功能 #1）— 把一個本機工具資料夾簽章打包並推送到 registry。

把一個模組資料夾（含 plugin.yaml + *.py）打包成已簽章的 ToolArtifact，
POST 到 registry-server 的 /publish。其他訂閱同 channel 的裝置在啟動或
/reload 時就會拉到這個工具（fetch 會驗章，竄改的碼會被拒）。

用法：
    python tools/fleet_publish.py scripts/module_007 --registry http://127.0.0.1:9000
    python tools/fleet_publish.py scripts/module_007 --registry http://127.0.0.1:9000 --channel prod

簽章密鑰取自環境變數 CIM_DISTRIBUTION_SECRET（registry 與裝置端須一致；
dev 未設時雙方落到同一固定預設值，可直接跑）。

設計見 docs/platform/fleet-distribution.md。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE_DIR))

from core.distribution import (  # noqa: E402
    artifact_to_dict,
    get_secret,
    make_artifact,
)


def _read_module_content(folder: Path) -> dict[str, str]:
    """收集要分發的快照內容：資料夾內所有 *.py + plugin.yaml（與本機 publish 同形狀）。"""
    content: dict[str, str] = {}
    for py_file in sorted(folder.glob("*.py")):
        content[py_file.name] = py_file.read_text(encoding="utf-8")
    manifest = folder / "plugin.yaml"
    if manifest.exists():
        content["plugin.yaml"] = manifest.read_text(encoding="utf-8")
    return content


def _parse_plugin_yaml(content: dict[str, str]) -> dict:
    try:
        import yaml  # noqa: PLC0415

        return yaml.safe_load(content.get("plugin.yaml", "")) or {}
    except Exception:
        return {}


def publish_folder(folder: Path, registry: str, channel: str,
                   version: str | None = None, author: str = "fleet-publish") -> dict:
    folder = folder.resolve()
    if not folder.is_dir():
        raise SystemExit(f"找不到模組資料夾：{folder}")
    content = _read_module_content(folder)
    if "plugin.yaml" not in content:
        raise SystemExit(f"{folder} 內沒有 plugin.yaml，無法判定 tool_id")

    meta = _parse_plugin_yaml(content)
    tool_id = meta.get("id") or folder.name
    version = version or str(meta.get("version", "1.0.0"))

    artifact = make_artifact(tool_id, version, channel, content, author, get_secret())
    payload = json.dumps(artifact_to_dict(artifact), ensure_ascii=False).encode("utf-8")

    url = registry.rstrip("/") + "/publish"
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 (localhost registry)
        body = json.loads(resp.read().decode("utf-8"))
    return {"tool_id": tool_id, "version": version, "channel": channel, "response": body}


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(prog="fleet_publish",
                                description="把工具資料夾簽章發布到 fleet registry")
    p.add_argument("folder", help="模組資料夾，如 scripts/module_007")
    p.add_argument("--registry", default="http://127.0.0.1:9000",
                   help="registry-server base URL（預設 http://127.0.0.1:9000）")
    p.add_argument("--channel", default="prod", help="發布頻道（dev/prod，預設 prod）")
    p.add_argument("--version", default=None, help="覆寫版本（預設取 plugin.yaml）")
    args = p.parse_args(argv)

    result = publish_folder(Path(args.folder), args.registry, args.channel, args.version)
    print(f"✅ 已發布 {result['tool_id']}@{result['version']} → {args.registry} "
          f"（channel={args.channel}）")
    print(f"   訂閱同 channel 的裝置啟動或 POST /reload 即會拉到（fetch 會驗章）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
