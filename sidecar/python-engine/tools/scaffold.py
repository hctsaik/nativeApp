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

{requires_block}
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
{requires_block}"""

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
"""Output layer for module_{mid}.

效能三鐵律（每次 rerun 都會重跑整個 render，務必遵守；見 docs/patterns/streamlit_output_perf.md）：
  1. mtime 驅動增量更新：掃描結果快取在 session_state，rerun 只 stat() 比對，變了才重讀。
  2. 大型列表必須分頁（PAGE_SIZE）：避免每次 rerun widget 樹線性爆炸。
  3. 禁止 loop 內 list.index()（O(N²)）：loop 前建 {{item_id: idx}} dict，O(1) 查表。
本範本已內建分頁骨架；接真實大型列表時，照下方註解補 mtime 快取與 index dict。
"""
from __future__ import annotations
import streamlit as st

PAGE_SIZE = 50  # 規則 2：大型列表分頁


def render_output(result: dict) -> None:
    if result.get("mode") != "ready":
        st.info("請在 Input 頁填表並按 ▶ 執行。")
        return

    st.write(result.get("echo", ""))

    # 範例：分頁渲染列表（規則 2）。把 "items" 換成你的結果鍵。
    items = result.get("items", [])
    if items:
        # 規則 3：loop 前建 index dict，迴圈內以 O(1) 查表取代 items.index(x)
        # idx_by_id = {{it["id"]: i for i, it in enumerate(items)}}
        # 規則 1：大型掃描結果請快取在 st.session_state，並以 mtime 比對決定是否重讀
        total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
        page = st.number_input("頁", 1, max(total_pages, 1), 1) if total_pages > 1 else 1
        start = (page - 1) * PAGE_SIZE
        for it in items[start:start + PAGE_SIZE]:
            st.write(it)
'''

# External-GUI launcher tool (the Label-tool pattern): launches a desktop
# program, no input/process/output code — the framework renders a launch button
# and core.external_gui handles env sanitization / WDAC workaround / lock.
_EXTGUI_PLUGIN_YAML = """\
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
  {name}（外部 GUI 啟動工具）：啟動一個桌面程式（像 Label tool 啟動 X-AnyLabeling），
  完成後關閉視窗即可。本模組無 input/process/output 程式碼，全靠下方 external_gui: 宣告。

{requires_block}
# 先用 form: 收集要傳給外部程式的參數（可選）
form:
  - {{ key: input_dir,  type: text, label: 輸入資料夾, default: "" }}
  - {{ key: output_dir, type: text, label: 輸出資料夾, default: "" }}

# 宣告式外部 GUI 啟動（框架自動渲染啟動鈕；core/external_gui 處理環境淨化/WDAC/單例）
external_gui:
  exe_env: {env_var}                 # 用此環境變數覆寫程式路徑（最優先）
  exe_candidates:                    # 依序嘗試的候選路徑（相對 engine 根目錄）
    - .venv-mytool/Scripts/mytool.exe
  exe_fallback: mytool               # 找不到時用 PATH 上的這個名字
  # python_module: anylabeling.app   # 若外部程式是 Python app 且 exe 被 WDAC 擋，改用 <python> -m <module>
  args: ["--input", "{{input_dir}}", "--output", "{{output_dir}}"]
  single_instance: true
  collect:
    dir: "{{output_dir}}"
    glob: "*.json"

# 外部程式關閉後，框架自動回收 collect.dir 內檔案並寫入結果，Output 頁顯示：
output:
  - {{ type: metric, label: 收集到的輸出檔, key: collected_count }}
  - {{ type: list, key: collected_files }}
"""

# Sheet (multi-tab workflow) YAML — like the Label tool's 4-tab annotation sheet.
_SHEET_YAML = """\
sheet_id: {sheet_id}
name: {name}
description: {description}
enabled_dev: true
enabled_prod: false
tabs:
{tabs}
"""

_CONNECTOR_TEMPLATE = '''\
"""{name} connector — connect to a NON-REST external system.

REST/HTTP systems need NO class: declare them in config/external_systems.yaml
(or the Management Center form). Use this skeleton only for protocols the
declarative REST path can't express (OPC-UA, SECS/GEM, SOAP, a vendor SDK…).

Implements the platform ExternalSystemConnector ABC (core.integrations.connector)
— fill in the three abstract methods.

This file already auto-registers itself: keep it in core/integrations/connectors/
and the engine's startup autodiscover() will import it and call register() below.
Then, in config/external_systems.yaml, set `connector_type: {slug}` on the system
that should use it. (No call-site edits anywhere.)
"""
from __future__ import annotations

from core.integrations.connector import (
    ConnectorHealth,
    ExternalSystemConnector,
    ExternalTask,
    ExternalTaskDetail,
)
from core.integrations.registry import register_connector


class {cls}Connector(ExternalSystemConnector):
    """Talk to the {name} external system (implements the platform contract)."""

    def __init__(self, tenant=None) -> None:
        self.tenant = tenant  # SystemTenant: host/token/format live here

    def get_ant_list(self) -> list[ExternalTask]:
        """Return pending work items from the system."""
        # TODO: query the system (use self.tenant) and map each item to ExternalTask.
        return []

    def get_ant_task_detail(self, task_id: str, format: str) -> ExternalTaskDetail:
        """Return the detail (usually a download URL) for one task."""
        # TODO: ask the system for task_id in `format` and return its download URL.
        return ExternalTaskDetail(download_url="")

    def health_check(self) -> ConnectorHealth:
        """Check connectivity / credentials."""
        # TODO: ping the system using self.tenant; report connected + latency.
        return ConnectorHealth(connected=True)


def register() -> None:
    """Auto-called by core.integrations.registry.autodiscover() at startup."""
    register_connector("{slug}", lambda tenant=None: {cls}Connector(tenant))
'''

_DOMAIN_SERVICES = '''\
"""Domain services for the {name} plugin.

Keep business logic here (pure, testable), separate from Streamlit UI. Modules
under modules/ import and call these. Mirrors plugins/labeling/domain/services.py.
"""
from __future__ import annotations


class {cls}Service:
    """Entry point for {name} domain operations."""

    def ping(self) -> str:
        return "{name} domain ready"
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


def next_free_module_id(base: Path) -> str:
    """Pick the next globally-free module_NNN so a scaffolded id never collides
    with an existing module anywhere — scripts/, every plugins/*/modules/, AND
    the target `base`. Lets an engineer run `scaffold module` without hunting for
    a free number (tool_ids are global, so local-only scanning would clash)."""
    roots: set[Path] = {ENGINE_DIR / "scripts", base}
    roots.update((ENGINE_DIR / "plugins").glob("*/modules"))
    roots.update((base.parent / "plugins").glob("*/modules"))
    used: set[int] = set()
    for root in roots:
        if root.is_dir():
            for f in root.glob("module_[0-9][0-9][0-9]"):
                try:
                    used.add(int(f.name.removeprefix("module_")))
                except ValueError:
                    pass
    n = 1
    while n in used:
        n += 1
    return f"{n:03d}"


def _requires_block(requires: list[str] | None) -> str:
    """Render the plugin.yaml `requires:` block for per-tool dependencies (#7).

    With deps → an active block; without → a commented example so engineers
    discover the feature. See docs/platform/per-tool-dependencies.md.
    """
    if requires:
        lines = "\n".join(f"  - {r}" for r in requires)
        return ("# 本工具自帶的 Python 相依（框架自動建 per-tool venv 安裝並注入）\n"
                f"requires:\n{lines}\n")
    return ("# 本工具自帶的 Python 相依（取消註解即啟用 per-tool venv 安裝；\n"
            "# 見 docs/platform/per-tool-dependencies.md）\n"
            "# requires:\n"
            "#   - shapely>=2.0\n")


def scaffold_module(mid: str | None, name: str, vendor: str, domain: str,
                    author: str, full: bool, base: Path,
                    external_gui: bool = False,
                    requires: list[str] | None = None) -> Path:
    if mid is None:
        mid = next_free_module_id(base)
    mid = mid.removeprefix("module_")
    if not (mid.isdigit() and len(mid) == 3):
        raise SystemExit(f"module id 必須是 3 位數字（如 042），得到 {mid!r}")
    folder = base / f"module_{mid}"
    if folder.exists():
        raise SystemExit(f"已存在：{folder}")
    folder.mkdir(parents=True)
    ctx = dict(mid=mid, name=name, vendor=vendor, domain=domain,
               author=author, slug=name.lower().replace(" ", "-"),
               env_var=f"{(name or 'MYTOOL').upper().replace(' ', '_')}_EXE",
               requires_block=_requires_block(requires))
    (folder / "__init__.py").write_text("", encoding="utf-8")
    if external_gui:
        (folder / "plugin.yaml").write_text(_EXTGUI_PLUGIN_YAML.format(**ctx), encoding="utf-8")
    elif full:
        (folder / "plugin.yaml").write_text(_FULL_PLUGIN_YAML.format(**ctx), encoding="utf-8")
        (folder / f"{mid}_input.py").write_text(_FULL_INPUT.format(**ctx), encoding="utf-8")
        (folder / f"{mid}_process.py").write_text(_FULL_PROCESS.format(**ctx), encoding="utf-8")
        (folder / f"{mid}_output.py").write_text(_FULL_OUTPUT.format(**ctx), encoding="utf-8")
    else:
        (folder / "plugin.yaml").write_text(_FORM_PLUGIN_YAML.format(**ctx), encoding="utf-8")
        (folder / f"{mid}_process.py").write_text(_FORM_PROCESS.format(**ctx), encoding="utf-8")
    return folder


def scaffold_sheet(sheet_id: str, name: str, tabs: list[str], base: Path,
                   description: str = "", create_stubs: bool = False,
                   modules_base: Path | None = None) -> Path:
    """Create a multi-tab workflow sheet YAML (the Label-tool 4-tab pattern).

    `tabs` is a list of module ids; each becomes a tab in order. The file lands
    in <base>/<sheet_id>.yaml (base is typically plugins/<p>/sheets or sheets/).

    With `create_stubs=True`, any tab whose module folder doesn't yet exist gets
    a runnable no-code form-first stub scaffolded into `modules_base` (default
    scripts/), so the whole multi-tab tool is launchable immediately — no manual
    per-tab module creation."""
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{sheet_id}.yaml"
    if path.exists():
        raise SystemExit(f"已存在：{path}")
    if create_stubs:
        mbase = modules_base or (ENGINE_DIR / "scripts")
        for mid in tabs:
            short = mid.removeprefix("module_")
            if not (mbase / f"module_{short}").exists() and not _module_exists_anywhere(mid):
                scaffold_module(short, f"{mid} 分頁", "cimcore", "workflow", "system",
                                full=False, base=mbase)
    tabs_yaml = "\n".join(
        f"  - {{ order: {i}, module_id: {mid}, label: {mid} }}"
        for i, mid in enumerate(tabs)
    ) or "  []"
    path.write_text(
        _SHEET_YAML.format(sheet_id=sheet_id, name=name,
                           description=description or name, tabs=tabs_yaml),
        encoding="utf-8")
    return path


def _module_exists_anywhere(plugin_id: str) -> bool:
    """True if a module folder for plugin_id exists under scripts/ or any plugin."""
    short = plugin_id.removeprefix("module_")
    roots = [ENGINE_DIR / "scripts"] + sorted((ENGINE_DIR / "plugins").glob("*/modules"))
    return any((r / f"module_{short}").is_dir() for r in roots)


def scaffold_connector(name: str, base: Path) -> Path:
    """Create a non-REST ExternalSystemConnector class skeleton. REST systems
    don't need this (use the declarative external_systems.yaml / GUI)."""
    base.mkdir(parents=True, exist_ok=True)
    slug = name.lower().replace(" ", "-")
    cls = "".join(p.capitalize() for p in name.replace("-", "_").split("_")) or "External"
    path = base / f"{slug.replace('-', '_')}_connector.py"
    if path.exists():
        raise SystemExit(f"已存在：{path}")
    path.write_text(_CONNECTOR_TEMPLATE.format(name=name, slug=slug, cls=cls), encoding="utf-8")
    return path


def scaffold_plugin(name: str, vendor: str, domain: str, base: Path) -> Path:
    folder = base / name
    if folder.exists():
        raise SystemExit(f"已存在：{folder}")
    for sub in ("modules", "sheets", "mcp", "domain", "docs"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    (folder / "__init__.py").write_text(f'"""{name} plugin."""\n', encoding="utf-8")
    (folder / "plugin.manifest.yaml").write_text(
        _PLUGIN_MANIFEST.format(name=name, vendor=vendor, domain=domain), encoding="utf-8")
    # A runnable starter module (so the plugin isn't an empty shell) — picks the
    # next free id across all roots, writes a no-code form-first module.
    cls = "".join(p.capitalize() for p in name.replace("-", "_").split("_")) or "Plugin"
    (folder / "domain" / "__init__.py").write_text("", encoding="utf-8")
    (folder / "domain" / "services.py").write_text(
        _DOMAIN_SERVICES.format(name=name, cls=cls), encoding="utf-8")
    starter_id = next_free_module_id(folder / "modules")
    scaffold_module(starter_id, f"{name} 起步工具", vendor, domain, "system",
                    full=False, base=folder / "modules")
    # A starter sheet wiring the starter module as its first tab.
    scaffold_sheet(f"{name}-workflow", f"{name} 工作流",
                   [f"module_{starter_id}"], folder / "sheets")
    return folder


def main(argv: list[str] | None = None) -> int:
    try:  # ensure emoji/Chinese output works on cp950 (Windows) consoles
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser(prog="scaffold", description="CIM platform scaffolding CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("module", help="generate a new module/tool skeleton")
    pm.add_argument("id", nargs="?", default=None,
                    help="3-digit module id, e.g. 042 (omit = auto-pick next free)")
    pm.add_argument("--name", default="新工具")
    pm.add_argument("--vendor", default="cimcore")
    pm.add_argument("--domain", default="cv")
    pm.add_argument("--author", default="system")
    pm.add_argument("--full", action="store_true", help="hand-written input/output (default: no-code form-first)")
    pm.add_argument("--external-gui", dest="external_gui", action="store_true",
                    help="external-GUI launcher tool (Label-tool pattern; no code)")
    pm.add_argument("--requires", default="",
                    help="comma-separated Python deps for a per-tool venv, e.g. 'shapely>=2.0,scikit-image'")
    pm.add_argument("--dest", default=str(ENGINE_DIR / "scripts"))

    psh = sub.add_parser("sheet", help="generate a multi-tab workflow sheet YAML")
    psh.add_argument("id", help="sheet id, e.g. defect-review")
    psh.add_argument("--name", default="新工作流")
    psh.add_argument("--tabs", default="", help="comma-separated module ids, e.g. module_042,module_043")
    psh.add_argument("--create-stubs", dest="create_stubs", action="store_true",
                     help="also scaffold a runnable stub module for any tab that doesn't exist yet")
    psh.add_argument("--dest", default=str(ENGINE_DIR / "sheets"))

    pc = sub.add_parser("connector", help="generate a NON-REST external-system connector skeleton")
    pc.add_argument("name", help="connector name, e.g. opcua-fab")
    pc.add_argument("--dest", default=str(ENGINE_DIR / "core" / "integrations" / "connectors"))

    pp = sub.add_parser("plugin", help="generate a new feature plugin skeleton (runnable starter)")
    pp.add_argument("name")
    pp.add_argument("--vendor", default="cimcore")
    pp.add_argument("--domain", default="general")
    pp.add_argument("--dest", default=str(ENGINE_DIR / "plugins"))

    args = p.parse_args(argv)
    _reload_hint = ("   熱載：呼叫 POST http://127.0.0.1:<engine_port>/reload "
                    "（或重啟 start-dev）即會出現，免重啟整個 app。")
    if args.cmd == "module":
        requires = [r.strip() for r in args.requires.split(",") if r.strip()]
        folder = scaffold_module(args.id, args.name, args.vendor, args.domain,
                                 args.author, args.full, Path(args.dest),
                                 external_gui=args.external_gui, requires=requires)
        kind = ("external-GUI 啟動工具" if args.external_gui
                else "full split-tool" if args.full else "no-code form-first")
        print(f"✅ 已建立 {kind} 模組：{folder}")
        print(_reload_hint)
    elif args.cmd == "sheet":
        tabs = [t.strip() for t in args.tabs.split(",") if t.strip()]
        path = scaffold_sheet(args.id, args.name, tabs, Path(args.dest),
                              create_stubs=args.create_stubs)
        extra = "（含自動產生缺少的分頁模組）" if args.create_stubs else ""
        print(f"✅ 已建立 sheet（{len(tabs)} 個分頁）{extra}：{path}")
        print(_reload_hint)
    elif args.cmd == "connector":
        path = scaffold_connector(args.name, Path(args.dest))
        print(f"✅ 已建立非-REST connector 骨架：{path}")
        print("   （REST 系統免寫 class：用 config/external_systems.yaml 或管理中心表單）")
    elif args.cmd == "plugin":
        folder = scaffold_plugin(args.name, args.vendor, args.domain, Path(args.dest))
        print(f"✅ 已建立 plugin（含可執行起步模組 + domain 服務 + 工作流 sheet）：{folder}")
        print(_reload_hint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
