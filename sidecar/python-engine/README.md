# Python Sidecar

The sidecar exposes a FastAPI control service and starts one active Streamlit
tool subprocess at a time.

## Run

```bash
python engine.py --control-port 8765 --log-dir logs
```

## Package

```bash
python -m PyInstaller engine.spec
```

The Windows build output is expected at `dist/engine.exe`.

To regenerate the spec manually:

```bash
python -m PyInstaller --onefile --name engine --add-data "tools;tools" engine.py
```

The `tools` data folder is required so packaged `engine.exe` can start the
sample Streamlit tool from its bundled resources.

---

## CV Module Framework

The sidecar includes a modular CV tool framework (`cv_framework_runner.py`) that
dynamically loads modules from the `scripts/` directory.

### Module layout

```
scripts/
├── shared/                    # Reusable UI helpers
│   ├── ui_components.py       # Date pickers, Parts input, toast, download button
│   └── image_widget.py        # Thumbnail + hover preview + lightbox + download
├── module_003/                # 不規則邊框產生器 (Irregular border generator)
├── module_004/                # 邊緣完整度偵測 (Edge integrity detection)
│   └── *.py                   # SQLite: $CIM_LOG_DIR/edge_records.sqlite
└── module_005/                # 邊緣記錄查詢 (Edge record query)
```

### Three-layer contract

Every module must implement exactly these three functions:

| Layer | File | Function | Streamlit? |
|-------|------|----------|------------|
| Input | `{ID}_input.py` | `render_input() -> dict` | yes |
| Process | `{ID}_process.py` | `execute_logic(params: dict) -> dict` | **no** |
| Output | `{ID}_output.py` | `render_output(result: dict) -> None` | yes |

`execute_logic()` must be pure Python — no `import streamlit`. Its return value
is JSON-serialised, so use `base64` strings for bytes and `str` for datetime.

### Plugin Manifest (v2)

Each module folder contains a `plugin.yaml` self-description:

```yaml
id: module_003
name: 不規則邊框產生器
version: "1.0.0"
category: module          # module | tool | workflow
runner: cv_framework
```

The framework discovers plugins at runtime — no changes to `engine.py` are
needed when adding a new module.

### Dev / Prod mode

| Env var | Value | Behaviour |
|---------|-------|-----------|
| `CIM_DEV_MODE` | `1` (default) | Load scripts directly from `scripts/module_*/` |
| `CIM_DEV_MODE` | `0` | Load from the active DB snapshot in `plugin_versions` |

In dev mode, editing any `.py` file under `scripts/` takes effect on the next
Streamlit rerun — no DB operations required.

To publish the current filesystem state to the DB (for prod mode):

```python
from plugin_registry import PluginRegistry
reg = PluginRegistry(db_path=Path("logs/data/tools.sqlite"))
reg.publish("module_003", changelog="Initial release", author="me")
```

Or use the **Management Center** (tool id `management-center`) from the Portal.

### Workflow / Suite

A workflow groups multiple modules into a single tabbed UI.
Define `scripts/workflows/{id}/workflow.yaml`:

```yaml
id: edge_analysis
name: 邊緣品質分析
steps:
  - plugin_id: module_003
    tab_label: "影像來源"
    optional: true
  - plugin_id: module_004
    tab_label: "偵測分析"
```

The state from step N is injected into step N+1 via `st.session_state`.

### Adding a new module

Use the `/new-cv-module` Claude Code skill, or:

1. Create `scripts/module_{ID}/` with the three-layer files
2. Add `scripts/module_{ID}/plugin.yaml`
3. Restart the framework — the new module appears automatically in the selector

### Shared UI components

Import shared helpers without relying on `sys.path`:

```python
import importlib.util
from pathlib import Path

def _load_shared(name: str):
    path = Path(__file__).resolve().parent.parent / "shared" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_ui  = _load_shared("ui_components")   # date pickers, toast, download
_img = _load_shared("image_widget")    # render_image_preview()
```

### Auth permission check

Before executing any module, `cv_framework_runner.py` and `workflow_runner.py`
call `AuthProvider.check_permission(plugin_id, "execute")`.  Currently the
provider always returns `True` (placeholder), but the permission rows in
`plugin_permissions` are already respected when populated.

### Syncing Workflows to DB (prod mode)

Dev mode discovers workflows from the filesystem on every request.
For prod mode (`CIM_DEV_MODE=0`), workflows must first be synced to the DB:

```python
from plugin_registry import PluginRegistry
reg = PluginRegistry(db_path=Path("logs/data/tools.sqlite"))
reg.sync_workflows()   # reads all scripts/workflows/*/workflow.yaml → DB
```

Or click **"同步 Workflow 到 DB"** in the Management Center's workflow tab.

### Running tests

```bash
cd sidecar/python-engine
python -m pytest tests/ scripts/module_003/ scripts/module_004/ scripts/module_005/ -q
```

308 tests across engine, plugins, shared components, registry, loader, auth, and fix verifications.
