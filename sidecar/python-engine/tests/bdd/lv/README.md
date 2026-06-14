# LV (VisualLatent) BDD E2E suite

Reusable, repeatable behaviour specs for the **LV plugin** (`app-lv`) and its
**hand-off to the labeling plugin** inside the CIM Native App. 20 scenarios,
authored multi-persona (QA / data-curation / labeling-ops), driven through the
project's **cim-gui MCP** machinery.

## Layout

| Path | What |
|------|------|
| `features/*.feature` | The 20 scenarios as Gherkin (the human-readable, version-controlled spec). |
| `fixtures.py` | Deterministic, no-network fixtures: a random-weight `resnet18.pth` + a tiny multi-class coco8 YOLO dataset (with a planted train→val leakage duplicate). Targets are gitignored. |
| `mcp_driver.py` | Sync facade over the **cim-gui MCP** code: `MCPDriver` wraps the exact `SidecarClient` + `BrowserDriver` the MCP tools call; `mcp_stdio_smoke` / `prove_mcp_server` drive the **literal** `cim_gui_mcp.server` over the MCP stdio protocol. |
| `run_bdd.py` | Orchestrator — runs all 20, writes `report.md` / `report.json` and screenshot `evidence/`. |
| `test_lv_bdd.py` | `pytest` entrypoints: contract scenarios always run; live E2E runs when opted-in. |

## Scenario tiers

- **Tier A** — fully E2E headless now: launch, shell, feature-map, guard states, navigation, multi-tool session, RBAC. No model/dataset needed.
- **Tier B** — E2E against the provisioned model + coco8 fixture: demo run, scatter, manifest write, compare/completeness panels, cart export. Each also asserts a deterministic framework-free **contract** so it never depends on Plotly-canvas gestures a headless browser can't perform.
- **Tier C** — pure contract/structural verification (`interaction.py` / `manifest.py` / `completeness.py` / `core.rbac`): curation-log replay, manifest schema, incremental refresh, gray-zone routing.

## How to run

The engine must be up (default `http://127.0.0.1:8765`). The LV contract modules
import torch / scikit-learn / hnswlib, so put the **app-lv per-tool venv** on
`PYTHONPATH`:

```bash
# 1) bring up an engine (or reuse start-dev.bat's)
py -3.11 sidecar/python-engine/engine.py --control-port 8765 --log-dir /tmp/lv_logs --rebuild-catalog

# 2) run the full BDD E2E suite
VENV=sidecar/python-engine/.tool-venvs/app-lv/Lib/site-packages
PYTHONUTF8=1 PYTHONPATH="$VENV" \
  py -3.11 sidecar/python-engine/tests/bdd/lv/run_bdd.py --base http://127.0.0.1:8765
```

Outputs: `report.md`, `report.json`, and `evidence/*.png` (per-scenario
screenshots). Exit code 0 = every required check passed.

### Contract-only (fast, no engine)

```bash
PYTHONPATH="$VENV" py -3.11 -m pytest sidecar/python-engine/tests/bdd/lv/test_lv_bdd.py -k contract -q
```

## Why "uses MCP" is literal here

`mcp_driver.MCPDriver` imports `cim_gui_mcp.browser_driver.BrowserDriver` and
`cim_gui_mcp.sidecar_client.SidecarClient` — the same callables the MCP server's
`@mcp.tool()` functions invoke, so each step issues the identical engine HTTP
request and Playwright action an MCP tool call would. On top of that, **S01**
launches LV through the *actual* `python -m cim_gui_mcp.server` process and calls
its `sidecar_start_tool` / `browser_get_text` / `browser_screenshot` tools over
the MCP stdio protocol, and every run asserts the server advertises its 13
`sidecar_* / browser_* / assert_*` tools.
