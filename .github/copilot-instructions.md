# Copilot instructions

To **set up / install / build** this project, read and execute the repo-root [`INSTALL.md`](../INSTALL.md) top-to-bottom.

Project & collaboration rules live in [`CLAUDE.md`](../CLAUDE.md) (Traditional Chinese).

Must-knows before you start:
- Use **`py -3.11`** for all Python (the repo's bare `python` may be a venv without pytest/fastapi). Do **not** use `npm run test:python`.
- Clone with **`--recurse-submodules`** (submodules: `vendor/AI4BI`, `vendor/LV`, `plugins/cim-modules`).
- **Labeling (ANnoTation) is a directory junction, not a submodule** — `INSTALL.md` step 4 mounts it.
- The **Tauri shell** is the sibling repo `nativeApp_Light`; build it on a machine **without WDAC enforce**.
