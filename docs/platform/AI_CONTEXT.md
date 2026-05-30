# AI Context — CIM Hybrid Edge Platform

This file is written for AI assistants (Claude, Copilot, etc.) working in this codebase. It provides orientation to the architecture, conventions, and critical gotchas that are not obvious from reading individual files.

> **⚠️ Current structure (post-2026-05 refactor).** Shared code now lives in **`core/`**, the Labeling feature in **`plugins/labeling/`**. Some sections below (Repository Map, How to Add a New Module) still reference **pre-refactor paths that no longer exist**. Use this mapping (authoritative current map: [`../README.md`](../README.md) "專案結構" + [`shared-components.md`](shared-components.md)):
> `annotation/` → `plugins/labeling/domain/`; `cim_platform/` → `core/integrations/`; `mcp/annotation_mcp/` → `plugins/labeling/mcp/`; top-level `scripts/sheets/` → removed.
> **To add a tool, prefer `python tools/scaffold.py module|sheet|plugin|connector` (+ `--external-gui`)**, then hot-reload via the portal "reload tools" button or `POST /reload` — no `engine.py` edit needed. Declarative no-code: `form:` / `output:` / `external_gui:` in plugin.yaml. RBAC is live (`core/rbac.py` + `auth_provider`), not a placeholder.

---

## Table of Contents

1. [Repository Map](#repository-map)
2. [Architecture Decisions](#architecture-decisions)
3. [Critical Conventions](#critical-conventions)
4. [Database Schema](#database-schema)
5. [Environment Variables](#environment-variables)
6. [Known Gotchas](#known-gotchas)
7. [Test Conventions](#test-conventions)
8. [How to Add a New Module](#how-to-add-a-new-module)
9. [Packaging](#packaging)

---

## Repository Map

```
nativeApp/                               # Monorepo root
├── apps/
│   ├── host-electron/
│   │   ├── src/main.js                  # Electron main process — manages sidecar lifecycle, IPC handlers
│   │   ├── src/preload.js               # Exposes window.cimHost bridge (contextIsolation=true)
│   │   ├── launch-electron.js           # Workaround: deletes ELECTRON_RUN_AS_NODE before spawning electron
│   │   ├── dev-wait-portal.js           # Waits for Vite dev server then spawns launch-electron.js
│   │   ├── logs/                        # Runtime log directory (host.log, engine.log, streamlit-*.log)
│   │   └── logs/data/tools.sqlite       # SQLite database: tools, tool_versions, sheets, roles, users
│   └── portal-react/
│       ├── src/main.jsx                 # Single React component — toolbar, iframe panels, postMessage handler
│       └── src/styles.css
├── sidecar/
│   └── python-engine/
│       ├── engine.py                    # FastAPI app + SQLiteToolAdapter + ToolProcessManager + SelectedPathStore
│       ├── plugin_registry.py           # PluginRegistry — publish, rollback, set_enabled, list_versions, sheets
│       ├── plugin_loader.py             # PluginLoader.load_module() — DEV=filesystem, PROD=exec(content_json)
│       ├── auth_provider.py             # Placeholder auth — always returns 'admin', checks plugin_permissions table
│       ├── requirements.txt             # fastapi, uvicorn, streamlit, opencv-python-headless, streamlit-image-annotation, pyyaml, ...
│       ├── engine.spec                  # PyInstaller spec — bundles tools/ directory into engine.exe
│       ├── tools/
│       │   ├── cv_framework_runner.py   # Streamlit runner for all module_NNN tools (dispatches to input/process/output layers)
│       │   ├── management_runner.py     # Streamlit UI: tool publish/rollback/archive, sheet editor, system backup
│       │   ├── sheet_runner.py          # Streamlit runner for multi-tab sheet compositions
│       │   ├── workflow_runner.py       # Streamlit runner for workflow-style tools
│       │   ├── db_utils.py              # SimpleDAO — lightweight per-operation SQLite DAO
│       │   ├── tool_comms.py            # Inter-tool communication helpers
│       │   ├── tool_result.py           # Result file read/write helpers
│       │   ├── log_utils.py             # Log file helpers
│       │   └── ui_utils.py              # Shared Streamlit UI utilities
│       ├── scripts/
│       │   ├── module_001/              # OpenCV basic processing
│       │   │   ├── 001_input.py         # render_input() -> dict
│       │   │   ├── 001_process.py       # execute_logic(params) -> dict  (no streamlit)
│       │   │   ├── 001_output.py        # render_output(result) -> None
│       │   │   ├── 001_process_test.py  # pytest for process layer
│       │   │   ├── plugin.yaml          # Module manifest
│       │   │   └── __init__.py          # MODULE_NAME = "..."
│       │   ├── module_002/ ... module_006/   # Same structure per module
│       │   ├── shared/
│       │   │   ├── image_widget.py      # Reusable Streamlit image display widget
│       │   │   └── ui_components.py     # date_input_range(), save_success_toast(), etc.
│       │   └── sheets/
│       │       └── edge_analysis/
│       │           └── sheet.yaml       # Sheet manifest (id, name, tabs[])
│       ├── annotation/                  # Annotation common component: core, storage, adapters, services
│       └── tests/
│           ├── conftest.py              # sys.path setup only
│           ├── test_api.py
│           ├── test_plugin_registry.py
│           ├── test_plugin_loader.py
│           ├── test_sqlite_adapter.py
│           ├── test_auth_provider.py
│           ├── test_tool_comms.py
│           ├── test_tool_result.py
│           ├── test_db_utils.py
│           ├── test_log_utils.py
│           ├── test_split_scripts.py
│           ├── test_wait_for_port.py
│           └── ...
├── packages/
│   └── shared-protocol/                 # MessageTypes enum shared between Electron and React
├── .claude/
│   └── commands/
│       ├── new-cv-module.md             # Skill: scaffold a new module (prompts for ID/name, generates 5 files)
│       ├── package-build.md             # Skill: full build pipeline (test -> build -> electron-builder)
│       ├── checkpoint.md                # Skill: save work state to memory files
│       └── resume.md                    # Skill: restore work state from memory files
├── start-dev.bat                        # Kill stale processes; set CIM_DEV_MODE=1; npm run dev
├── start-prod.bat                       # Kill stale processes; set CIM_DEV_MODE=0; npm run dev
└── package.json                         # Workspaces root; scripts: dev, build, test, test:python
```

---

## Architecture Decisions

### Why a sidecar pattern?

Electron's renderer process is a Chromium sandbox — it cannot run Python or spawn OS processes directly. A separate Python sidecar process (FastAPI on a loopback port) acts as the local backend, keeping all compute in Python while the UI stays in React/Streamlit. The sidecar port is discovered dynamically at startup and communicated to React via the IPC `get-app-config` handler.

### Why Streamlit for tools instead of React?

Streamlit lets data-science engineers write interactive tool UIs in pure Python, with no frontend knowledge required. Each tool runs as two Streamlit processes (Input pane and Output pane) on separate ports, embedded as iframes inside the React Portal. This lets module authors focus on domain logic.

### Why the three-layer module pattern (Input / Process / Output)?

- **Input** (`NNN_input.py`) — only Streamlit widgets; returns a plain `dict` of parameters.
- **Process** (`NNN_process.py`) — pure computation; **no Streamlit imports allowed**. Returns a JSON-serializable `dict`.
- **Output** (`NNN_output.py`) — only Streamlit rendering; receives the `dict` from Process.

The strict separation enables:
1. Unit-testing Process logic without a Streamlit runtime.
2. PROD mode to exec Process code from DB snapshots safely.
3. The result `dict` is written to `{tool_id}_result.json` on disk; the Output pane polls for it and rerenders.

### Why SQLite for the tool database?

Single-file, zero-install, sufficient for the edge/single-machine deployment model. No network dependency, works offline. The same `tools.sqlite` file is shared between the Sidecar (`SQLiteToolAdapter` in `engine.py`) and `PluginRegistry` in `plugin_registry.py`. Both components use `INSERT OR IGNORE` + migration ALTER TABLE to stay idempotent.

### Why a separate `plugin_registry.py`?

`engine.py` manages the FastAPI HTTP layer and process management. `plugin_registry.py` owns all module lifecycle concerns: publish (snapshot all .py files to `tool_versions`), rollback (swap `is_active`), sheet composition. This separation keeps `engine.py` focused on runtime concerns.

### Why `PluginLoader.load_module_prod` uses `exec()`?

In PROD mode, module source code is stored as JSON strings in `tool_versions.content_json`. Loading from disk is not available (the `scripts/` directory is excluded from the production build). `exec(compile(source, ...))` loads a module from a string into a fresh `types.ModuleType`, mimicking `importlib` for code that was never written to disk. This is intentional and the known risk (arbitrary code exec) is accepted because the code was published by an administrator through the management UI.

---

## Critical Conventions

### Naming

| Entity | Convention | Example |
|--------|-----------|---------|
| Module folder | `module_{NNN}` (zero-padded 3 digits) | `module_006` |
| Module files | `{NNN}_{layer}.py` | `006_input.py` |
| Tool ID in DB | same as module folder name | `module_006` |
| Sheet tool ID | `sheet-{sheet_id}` | `sheet-edge-analysis` |
| Management tool ID | `management-{name}` | `management-center` |
| Plugin manifest | `plugin.yaml` in module folder | — |
| Sheet manifest | `sheet.yaml` in sheets subfolder | — |

### What MUST NOT be done

- **Do not import streamlit in `_process.py` files.** The process layer runs headlessly in tests; any `import streamlit` will break `test_*_process_test.py`.
- **Do not return non-JSON-serializable types from `execute_logic()`.** `bytes`, `numpy.ndarray`, `datetime`, `tuple` (top-level) will silently break the result file. Encode bytes as `base64.b64encode(x).decode("ascii")`, lists are fine, convert `tuple` to `list`.
- **Do not resolve DB paths at module import time.** Always use a function `def _db_path() -> Path: return Path(os.environ.get("CIM_LOG_DIR", "/tmp")) / "...sqlite"`. Otherwise pytest monkeypatching of `CIM_LOG_DIR` will not work.
- **Do not hardcode ports.** Sidecar and Streamlit ports are all chosen dynamically via `find_free_port()`.
- **Do not skip the engine.py seed + re-enable step when adding a new module.** If the tool ID is not in the `_initialize()` INSERT OR IGNORE list AND the re-enable UPDATE list, the tool will appear disabled in the DB on first startup.
- **Do not use `COALESCE` in migration UPDATEs that sync enabled flags from legacy tables.** Use `MAX()` instead (see Known Gotchas).
- **Do not name a new module with the same numeric ID as an existing module.** The three-digit prefix is the unique key for file resolution.

### Module `plugin.yaml` required fields

```yaml
id: module_NNN          # must match folder name
name: <display name>    # shown in Portal dropdown
version: "1.0.0"
category: module
description: <one line>
author: system
tags: []
runner: cv_framework
```

---

## Database Schema

File location: `apps/host-electron/logs/data/tools.sqlite` (dev) or `<exe_dir>/logs/data/tools.sqlite` (packaged).

### `tools` table

| Column | Type | Notes |
|--------|------|-------|
| `tool_id` | TEXT PK | e.g. `module_006`, `sheet-edge-analysis`, `management-center` |
| `name` | TEXT | Display name, e.g. `006 - 動物影像標記` |
| `script_relative_path` | TEXT | Relative to `tools/` dir, e.g. `cv_framework_runner.py` |
| `version` | TEXT | Semver string |
| `signature` | TEXT | Nullable; reserved for future code signing |
| `source_commit` | TEXT | Nullable; seed rows use `"seed"` |
| `author` | TEXT | Nullable |
| `approved_at` | TEXT | Nullable ISO datetime |
| `enabled` | INTEGER | 1 = visible in Portal; 0 = archived |
| `enabled_prod` | INTEGER | 1 = visible in PROD mode |
| `enabled_dev` | INTEGER | 1 = visible in DEV mode (default 1) |
| `order_index` | INTEGER | Sort order in Portal dropdown |
| `description` | TEXT | Nullable; populated from `plugin.yaml` |

### `tool_versions` table

| Column | Type | Notes |
|--------|------|-------|
| `version_id` | INTEGER PK AUTOINCREMENT | |
| `tool_id` | TEXT | FK → `tools.tool_id` (soft reference) |
| `version` | TEXT | Semver string from plugin.yaml |
| `content_json` | TEXT | JSON object: `{"NNN_input.py": "<source>", "plugin.yaml": "<source>", ...}` |
| `changelog` | TEXT | Nullable; human-readable change description |
| `author` | TEXT | Nullable |
| `created_at` | TEXT | ISO datetime (SQLite `datetime('now')`) |
| `is_active` | INTEGER | Only one row per `tool_id` should have `is_active=1` at a time |
| `source` | TEXT | `'filesystem'` for UI-published versions |

### `sheets` table

| Column | Type | Notes |
|--------|------|-------|
| `sheet_id` | TEXT PK | e.g. `edge_analysis` |
| `name` | TEXT | Display name |
| `description` | TEXT | Nullable |
| `enabled_dev` | INTEGER | Default 1 |
| `enabled_prod` | INTEGER | Default 0 |
| `created_at` | TEXT | |

### `sheet_tabs` table

| Column | Type | Notes |
|--------|------|-------|
| `tab_id` | INTEGER PK AUTOINCREMENT | |
| `sheet_id` | TEXT | FK → `sheets.sheet_id` |
| `tab_order` | INTEGER | 0-indexed display order |
| `plugin_id` | TEXT | References a `module_NNN` tool_id |
| `label` | TEXT | Tab label shown in the UI |

### `roles` table

Seeded with three rows: `admin`, `operator`, `viewer`. RBAC is a placeholder; `AuthProvider` currently always returns `admin`.

### `users` table

| Column | Type |
|--------|------|
| `user_id` | TEXT PK |
| `username` | TEXT UNIQUE |
| `role_id` | TEXT FK → `roles` |
| `api_token` | TEXT |
| `created_at` | TEXT |

### `plugin_permissions` table

| Column | Type |
|--------|------|
| `perm_id` | INTEGER PK |
| `plugin_id` | TEXT |
| `role_id` | TEXT FK → `roles` |
| `can_view` | INTEGER |
| `can_execute` | INTEGER |

Default behavior (no row present): allow all actions.

---

## Environment Variables

| Variable | Set By | Default | Meaning |
|----------|--------|---------|---------|
| `CIM_DEV_MODE` | `start-dev.bat` / `start-prod.bat` | `"1"` | `"1"` = DEV (filesystem modules); `"0"` = PROD (DB snapshots only) |
| `CIM_TOOL_ID` | `ToolProcessManager._make_env()` | — | The tool_id being executed, e.g. `module_006`. Set on Streamlit subprocess. |
| `CIM_MODULE_ID` | `ToolProcessManager._make_env()` | — | Numeric part of tool_id, e.g. `"006"` for `module_006`. Used by `cv_framework_runner.py` to skip module selector. |
| `CIM_SHEET_ID` | `ToolProcessManager._make_env()` | — | Set for `sheet-*` tools; value is slug form of sheet id. |
| `CIM_TOOL_LAYER` | `ToolProcessManager._spawn()` | `"input"` | `"input"` or `"output"` — tells cv_framework_runner which pane to render. |
| `CIM_LOG_DIR` | `ToolProcessManager._make_env()` | `ROOT_DIR/logs` | Directory for result JSON files and module SQLite databases. |
| `CIM_SELECTED_PATHS_FILE` | `ToolProcessManager._make_env()` | — | Path to `selected_paths.json` written by Electron's file-picker dialog. |
| `CIM_CONTROL_PORT` | `engine.py main()` | — | The FastAPI sidecar HTTP port, set on the sidecar process itself. Used by `management_runner.py` to call `/tools/{id}/start`. |
| `PORTAL_DEV_URL` | `dev-wait-portal.js` | `http://127.0.0.1:5173` | Vite dev server URL, passed to Electron `main.js`. |
| `PYTHON` | caller / system | `"python"` | Overrides the python executable path used when spawning the sidecar. |
| `ELECTRON_DEBUG` | developer | — | If set, adds `--remote-debugging-port=9222` to Electron spawn args. |
| `ELECTRON_RUN_AS_NODE` | Claude Code CLI | — | **Must NOT be set when launching Electron.** `launch-electron.js` explicitly deletes it before spawning. See Known Gotchas. |

---

## Known Gotchas

### 1. ELECTRON_RUN_AS_NODE breaks main.js

**Problem:** Claude Code CLI (and some other tools) sets `ELECTRON_RUN_AS_NODE=1` in the environment. When this is set, Electron runs as a plain Node.js process and `require('electron')` returns the path string to the binary rather than the Electron API object. This causes `const { ipcMain } = require('electron')` to destructure `undefined`, crashing `main.js` at load time.

**Fix:** `apps/host-electron/launch-electron.js` clones `process.env`, deletes `ELECTRON_RUN_AS_NODE`, and spawns Electron with the cleaned environment. The `dev` script in `host-electron/package.json` invokes `node launch-electron.js` instead of `electron .` directly.

**Test:** `apps/host-electron/src/electron-env.test.js` documents and verifies the fix.

---

### 2. COALESCE → MAX bug in plugin_registry.py migration

**Problem:** An early version of the migration that syncs `enabled_prod` from the legacy `plugins` table to the `tools` table used:

```sql
UPDATE tools SET enabled_prod = COALESCE((SELECT enabled_prod FROM plugins WHERE ...), 0)
```

This would reset `enabled_prod` back to `0` when `plugins.enabled_prod = 0`, overwriting a `1` that had been set by `publish()`. This caused published modules to silently become invisible in PROD mode after any Streamlit `st.rerun()` that instantiated a new `PluginRegistry`.

**Fix:** Changed to `MAX(enabled_prod, COALESCE(..., 0))` so the column can only go up, never down:

```sql
UPDATE tools SET
    enabled_dev  = MAX(enabled_dev,  COALESCE((SELECT enabled_dev  FROM plugins WHERE plugin_id = tools.tool_id), 0)),
    enabled_prod = MAX(enabled_prod, COALESCE((SELECT enabled_prod FROM plugins WHERE plugin_id = tools.tool_id), 0))
WHERE tool_id LIKE 'module_%'
```

**Test:** `test_enabled_prod_not_downgraded_by_legacy_zero` in `tests/test_plugin_registry.py` explicitly recreates the legacy `plugins` table with `enabled_prod=0` and verifies the value stays `1`.

---

### 3. Windows socket timing on port discovery

**Problem:** `find_free_port()` in both `engine.py` (Python) and `main.js` (Node.js) works by binding to port 0, reading the assigned port, then closing the socket. On Windows, there is a short TIME_WAIT window after the socket is closed where the port may be briefly unavailable.

**Behavior:** The `wait_for_port()` function polls every 300ms for up to 30 seconds, which is sufficient in practice. Do not reduce the poll interval or timeout when modifying startup logic.

---

### 4. Module selector skipping via CIM_MODULE_ID

`cv_framework_runner.py` checks `CIM_MODULE_ID` on startup. If set, it skips the sidebar module `st.selectbox` and jumps directly to the specified module. `CIM_MODULE_ID` may be the short form (`"006"`) or the full form (`"module_006"`); the runner normalizes both to the `plugin_id` form.

This means that when `ToolProcessManager` spawns a Streamlit process for `module_006`, it injects `CIM_MODULE_ID=006`, and the user never sees the module selector dropdown inside the Streamlit iframe.

---

### 5. Result file polling vs. postMessage

The Output pane reloads when `{tool_id}_result.json` changes on disk. The React Portal polls `GET /tools/active/status` every 2 seconds while a tool is active, comparing `result_mtime`. The `postMessage` `EXECUTE_COMPLETE` event from Streamlit is treated as a **fast-path fallback** only — it may not arrive due to Streamlit's iframe sandbox. Do not rely on it as the primary mechanism.

---

### 6. Packaged sidecar fallback chain

In a packaged Electron app (`app.isPackaged === true`), `main.js` tries two sidecar candidates in order:

1. `resources/engine/engine.exe` — the PyInstaller-compiled binary
2. `resources/sidecar-source/engine.py` — raw Python source (requires Python in PATH)

If the `.exe` fails (e.g., first-time Windows Defender scan), the app automatically falls back to the Python source. This fallback is intentional.

---

### 7. scripts/ directory excluded from packaged build

The `scripts/module_*/` source tree is **not bundled** in the packaged `.exe`. In PROD mode, module code is loaded entirely from `tool_versions.content_json` in the SQLite DB. This is intentional: the DB is writable at runtime (new publishes, rollbacks), while bundled files are read-only inside the ASAR archive.

---

## Test Conventions

### Python tests

- Location: `sidecar/python-engine/tests/` (integration/unit for engine-level code) and `sidecar/python-engine/scripts/module_NNN/NNN_process_test.py` (per-module process layer tests).
- Runner: `pytest` (version 9+, from `requirements.txt`).
- `conftest.py` only adds the parent directory to `sys.path`; no shared fixtures at engine level.
- Each test file imports what it needs directly. `monkeypatch.setenv("CIM_DEV_MODE", ...)` is the primary way to switch modes in tests.
- **Minimum 8 tests per new module process file**, covering: all required output fields, base64 validity, numeric type/range, pass-through fields, no-image error path, no-DB error path (if applicable), and `import streamlit` absence check.
- DB path must use `os.environ.get("CIM_LOG_DIR", "/tmp")` at call time; `tmp_path` fixture provides an isolated directory for tests.

### JavaScript tests

- Location: `apps/host-electron/src/electron-env.test.js` and `packages/shared-protocol/`.
- Runner: `vitest` (ESM mode).
- Tests are documentation-style for the ELECTRON_RUN_AS_NODE fix.
- Run via `npm test` at the monorepo root.

### Key test files to know

| File | What it tests |
|------|--------------|
| `tests/test_plugin_registry.py` | publish, rollback, set_enabled, list_versions, sheets, MAX migration fix |
| `tests/test_sqlite_adapter.py` | SQLiteToolAdapter CRUD |
| `tests/test_plugin_loader.py` | DEV/PROD module loading, `exec()` path |
| `tests/test_api.py` | FastAPI endpoint integration (TestClient) |
| `tests/test_split_scripts.py` | `_split_scripts()` input/output file resolution |
| `tests/test_tool_result.py` | Result file read/write helpers |
| `apps/host-electron/src/electron-env.test.js` | ELECTRON_RUN_AS_NODE workaround |

---

## How to Add a New Module

Use the Claude skill `/new-cv-module` for automated scaffolding. Manual checklist:

1. **Choose a unique 3-digit ID** (e.g., `009`). Check `scripts/` for existing IDs.

2. **Create the module folder:**
   ```
   sidecar/python-engine/scripts/module_00N/
   ├── __init__.py             # MODULE_NAME = "<display name>"
   ├── 00N_input.py            # def render_input() -> dict:
   ├── 00N_process.py          # def execute_logic(params: dict) -> dict:  (NO streamlit)
   ├── 00N_output.py           # def render_output(result: dict) -> None:
   ├── 00N_process_test.py     # pytest, minimum 8 tests
   └── plugin.yaml             # id: module_00N, name: ..., version, category, runner: cv_framework
   ```

3. **Implement the three-layer contract:**
   - `render_input()` returns a `dict` with all parameters needed by `execute_logic()`.
   - `execute_logic(params)` returns a JSON-serializable `dict`. No `import streamlit`.
   - `render_output(result)` reads from the dict and displays with Streamlit.

4. **Register in engine.py `_initialize()`:**
   ```python
   # Add to INSERT OR IGNORE list:
   ("module_00N", "00N - <Name>", "cv_framework_runner.py", "0.1.0", None, "seed", "system", None, 1),

   # Add tool_id to the re-enable UPDATE:
   WHERE tool_id IN ("module_001", ..., "module_00N", ...)
   ```

5. **Run tests:**
   ```bat
   python -m pytest sidecar/python-engine/scripts/module_00N/ -v
   python -m pytest sidecar/python-engine/tests/ -v
   ```

6. **Restart the sidecar** (or full app restart). The new tool appears in the Portal dropdown.

7. **To make available in PROD:** Open Management Center → Tool Management → `module_00N` → "🚀 發布到 Prod".

### JSON serialization rules for execute_logic() return value

| Allowed | Forbidden | Fix |
|---------|-----------|-----|
| `str`, `int`, `float`, `bool`, `None`, `list`, `dict` | `bytes` | `base64.b64encode(x).decode("ascii")` |
| | `numpy.ndarray` | `.tolist()` or base64 |
| | `datetime` | `.isoformat()` |
| | top-level `tuple` | convert to `list` |

---

## Packaging

### What gets included

| Build artifact | Source | Destination in package |
|---------------|--------|----------------------|
| `engine.exe` | `sidecar/python-engine/dist/engine.exe` | `resources/engine/engine.exe` |
| Portal static files | `apps/portal-react/dist/` | `resources/portal/` |
| Sidecar source fallback | `sidecar/python-engine/engine.py` + `plugin_registry.py` + `plugin_loader.py` + `auth_provider.py` + `tools/**` | `resources/sidecar-source/` |
| Electron main | `apps/host-electron/src/` | `resources/app/src/` |

### What gets excluded

| Pattern | Reason |
|---------|--------|
| `scripts/module_*/` | Module code loaded from DB in PROD; not needed in binary |
| `tests/` | Test files |
| `**/__pycache__/`, `**/*.pyc` | Python bytecode cache |
| `**/*_test.py` | Module-level pytest files |
| `tools/sample_csv_tool.py` | Legacy, retired |
| `tools/opencv_tool*.py` | Legacy, replaced by module_001 |
| `tools/animal_tagger*.py` | Legacy, replaced by module_006 |
| `logs/` | Runtime-generated |

### Build commands

```bat
# 1. Compile Python sidecar
cd sidecar\python-engine
pyinstaller engine.spec

# 2. Build React Portal
cd apps\portal-react
npm run build

# 3. Package Electron portable
cd apps\host-electron
npm run package:portable
# Output: release\CIM Hybrid Edge Platform*.exe
```

The PyInstaller spec (`engine.spec`) uses `--onefile` mode with `datas=[('tools', 'tools')]`, so all files in `tools/` are bundled into the single `engine.exe`. At runtime, PyInstaller extracts them to a temp `_MEIPASS` directory; `resource_root()` in `engine.py` returns `sys._MEIPASS` when frozen.

### First-run PROD behavior

A freshly deployed `.exe` has an empty `tools.sqlite` (created on first run). No modules are visible until each one is published via Management Center. The recommended deployment workflow:

1. Run in DEV mode once to initialize the DB.
2. Open Management Center, bulk-publish all desired modules.
3. Distribute to end-users who run in PROD mode.
