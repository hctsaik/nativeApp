# AGENTS.md

> 🤖 **AI AGENT — to SET UP / INSTALL / BUILD this project you MUST read and execute the repo-root [`INSTALL.md`](INSTALL.md) top-to-bottom.**
> It is the single authoritative, ordered runbook (work-root → clone+submodules → ANnoTation junction → npm/pip → portal build → Tauri build → run → verify). Do not improvise setup, and do NOT follow the older `docs/INSTALL.md` (stale).

## What this repo is
**CIM Hybrid Edge Platform** — a Windows monorepo: a **Tauri v2** desktop shell (in-repo at `apps/host-tauri`, app `cim-light`; the runnable binary `apps/host-tauri/prebuilt/cim-light.exe` is **NOT committed** — build it on a non-WDAC machine via `scripts/win/build-shell.bat` and copy it into `prebuilt/`) that loads a pre-built **React portal** (`apps/portal-react/dist`) and spawns a **Python FastAPI/Streamlit engine** (`sidecar/python-engine/engine.py`). CV tools/plugins load at runtime.

## Where the rules live
- **[`INSTALL.md`](INSTALL.md)** (repo root) — the setup/build/run runbook. Read this to install.
- **[`CLAUDE.md`](CLAUDE.md)** — project & collaboration rules (Traditional Chinese; startup chain, WDAC decisions, tool-dev rules). Follow it for any code work.

## Two gotchas to know BEFORE you open INSTALL.md
- **Python 3.11 only** — install/test everything with `py -3.11`; the repo's bare `python` may be `.venv-xanylabeling` (no pytest/fastapi). Do NOT use `npm run test:python`.
- **Clone with `--recurse-submodules`** — submodules are ONLY `vendor/AI4BI`, `vendor/LV` (branch `uihuang_dev`), `plugins/cim-modules`. **Labeling (ANnoTation) is a directory JUNCTION, not a submodule** — `INSTALL.md` step 4 handles it. The Tauri shell now lives IN-REPO at `apps/host-tauri`. The runnable `apps/host-tauri/prebuilt/cim-light.exe` is **NOT committed** (17MB blob out of git): build it on a machine WITHOUT WDAC enforce via `scripts/win/build-shell.bat` (`cargo build --release` → copies into `prebuilt/`), then copy the exe onto the target box. Once the exe is in `prebuilt/`, daily use needs no sibling clone / npm install / Rust toolchain (a copied-in unsigned exe runs under WDAC). Do not re-litigate WDAC.
