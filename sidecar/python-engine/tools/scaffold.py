"""Platform-native scaffolding CLI (no Claude Code / AI agent required).

Generate a new tool or plugin skeleton from the terminal:

    # No-code form-first module (input form + output declared in YAML;
    # you only fill in the pure process logic):
    python tools/scaffold.py module 042 --name "我的工具"

    # A full split-tool module (hand-written input/output):
    python tools/scaffold.py module 042 --name "我的工具" --full

    # A new feature plugin (plugins/<name>/ with manifest + dirs):
    python tools/scaffold.py plugin qc --vendor cimcore --domain quality

This replaces the dependency on the `/new-cv-module` Claude skill so a normal
engineer (no AI agent) can scaffold a working tool. The form-first default
produces a module with ZERO Streamlit code (see scripts/module_007 for the
shape).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent

_FORM_PLUGIN_YAML = """\
id: module_{mid}
name: {name}
version: 1.0.0
runner: cv_framework
category: module
vendor: {vendor}
domain: {domain}
enabled: true
slug: {slug}
author: {author}
description: >
  {name}（no-code form-first）：input 用 form: 宣告、output 用 output: 宣告，
  只需在 {mid}_process.py 寫純運算邏輯（無 Streamlit）。

# 宣告式 input（免寫 *_input.py）
form:
  - {{ key: text, type: text, label: 輸入文字, default: "" }}
  - {{ key: count, type: integer, label: 次數, default: 1, min: 1, max: 100 }}

# 宣告式 output（免寫 *_output.py）
output:
  - {{ type: text, label: 結果, key: echo }}
  - {{ type: metric, label: 次數, key: count }}
"""

_FORM_PROCESS = '''\
"""Process layer for module_{mid} — pure logic, no Streamlit.

`params` comes from the plugin.yaml `form:` schema (auto-rendered by the
framework). Return a dict the plugin.yaml `output:` blocks read by key.
"""

from __future__ import annotations


def execute_logic(params: dict) -> dict:
    text = str(params.get("text", ""))
    count = int(params.get("count", 1) or 1)
    return {{"mode": "ready", "echo": text * count, "count": count}}
'''

_FULL_PLUGIN_YAML = """\
id: module_{mid}
name: {name}
version: 1.0.0
runner: cv_framework
category: module
vendor: {vendor}
domain: {domain}
enabled: true
slug: {slug}
author: {author}
description: {name}
"""

_FULL_INPUT = '''\
"""Input layer for module_{mid}."""
from __future__ import annotations
import streamlit as st


def render_input() -> dict:
    text = st.text_input("輸入文字", value="")
    return {{"text": text}}
'''

_FULL_PROCESS = '''\
"""Process layer for module_{mid} — pure logic, no Streamlit."""
from __future__ import annotations


def execute_logic(params: dict) -> dict:
    return {{"mode": "ready", "echo": str(params.get("text", ""))}}
'''

_FULL_OUTPUT = '''\
"""Output layer for module_{mid}."""
from __future__ import annotations
import streamlit as st


def render_output(result: dict) -> None:
    if result.get("mode") != "ready":
        st.info("請在 Input 頁填表並按 ▶ 執行。")
        return
    st.write(result.get("echo", ""))
'''

_PLUGIN_MANIFEST = """\
id: {name}
vendor: {vendor}
domain: {domain}
version: 1.0.0
depends_on:
  - core
provides:
  modules:
    current_path: plugins/{name}/modules/
  sheets:
    current_path: plugins/{name}/sheets/
"""


def scaffold_module(mid: str, name: str, vendor: str, domain: str,
                    author: str, full: bool, base: Path) -> Path:
    mid = mid.lstrip("module_")
    if not (mid.isdigit() and len(mid) == 3):
        raise SystemExit(f"module id 必須是 3 位數字（如 042），得到 {mid!r}")
    folder = base / f"module_{mid}"
    if folder.exists():
        raise SystemExit(f"已存在：{folder}")
    folder.mkdir(parents=True)
    ctx = dict(mid=mid, name=name, vendor=vendor, domain=domain,
               author=author, slug=name.lower().replace(" ", "-"))
    (folder / "__init__.py").write_text("", encoding="utf-8")
    if full:
        (folder / "plugin.yaml").write_text(_FULL_PLUGIN_YAML.format(**ctx), encoding="utf-8")
        (folder / f"{mid}_input.py").write_text(_FULL_INPUT.format(**ctx), encoding="utf-8")
        (folder / f"{mid}_process.py").write_text(_FULL_PROCESS.format(**ctx), encoding="utf-8")
        (folder / f"{mid}_output.py").write_text(_FULL_OUTPUT.format(**ctx), encoding="utf-8")
    else:
        (folder / "plugin.yaml").write_text(_FORM_PLUGIN_YAML.format(**ctx), encoding="utf-8")
        (folder / f"{mid}_process.py").write_text(_FORM_PROCESS.format(**ctx), encoding="utf-8")
    return folder


def scaffold_plugin(name: str, vendor: str, domain: str, base: Path) -> Path:
    folder = base / name
    if folder.exists():
        raise SystemExit(f"已存在：{folder}")
    for sub in ("modules", "sheets", "mcp", "domain", "docs"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    (folder / "__init__.py").write_text(f'"""{name} plugin."""\n', encoding="utf-8")
    (folder / "plugin.manifest.yaml").write_text(
        _PLUGIN_MANIFEST.format(name=name, vendor=vendor, domain=domain), encoding="utf-8")
    return folder


def main(argv: list[str] | None = None) -> int:
    try:  # ensure emoji/Chinese output works on cp950 (Windows) consoles
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(prog="scaffold", description="CIM platform scaffolding CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("module", help="generate a new module/tool skeleton")
    pm.add_argument("id", help="3-digit module id, e.g. 042")
    pm.add_argument("--name", default="新工具")
    pm.add_argument("--vendor", default="cimcore")
    pm.add_argument("--domain", default="cv")
    pm.add_argument("--author", default="system")
    pm.add_argument("--full", action="store_true", help="hand-written input/output (default: no-code form-first)")
    pm.add_argument("--dest", default=str(ENGINE_DIR / "scripts"))

    pp = sub.add_parser("plugin", help="generate a new feature plugin skeleton")
    pp.add_argument("name")
    pp.add_argument("--vendor", default="cimcore")
    pp.add_argument("--domain", default="general")
    pp.add_argument("--dest", default=str(ENGINE_DIR / "plugins"))

    args = p.parse_args(argv)
    if args.cmd == "module":
        folder = scaffold_module(args.id, args.name, args.vendor, args.domain,
                                 args.author, args.full, Path(args.dest))
        kind = "full split-tool" if args.full else "no-code form-first"
        print(f"✅ 已建立 {kind} 模組：{folder}")
        print("   重啟 engine（或 start-dev）即會自動掃描出現。")
    elif args.cmd == "plugin":
        folder = scaffold_plugin(args.name, args.vendor, args.domain, Path(args.dest))
        print(f"✅ 已建立 plugin：{folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
