# AGENTS.md

> 🤖 **AI AGENT — to SET UP / INSTALL / BUILD this project you MUST read and execute the repo-root [`INSTALL.md`](INSTALL.md) top-to-bottom.**
> It is the single authoritative, ordered runbook (work-root → clone+submodules → ANnoTation junction → npm/pip → portal build → Tauri build → run → verify). Do not improvise setup, and do NOT follow the older `docs/INSTALL.md` (stale).

## What this repo is
**CIM Hybrid Edge Platform** — a Windows monorepo: a **Tauri v2** desktop shell (in-repo at `apps/host-tauri`, app `cim-light`, with a committed prebuilt binary `apps/host-tauri/prebuilt/cim-light.exe`) that loads a pre-built **React portal** (`apps/portal-react/dist`) and spawns a **Python FastAPI/Streamlit engine** (`sidecar/python-engine/engine.py`). CV tools/plugins load at runtime.

## Where the rules live
- **[`INSTALL.md`](INSTALL.md)** (repo root) — the setup/build/run runbook. Read this to install.
- **[`CLAUDE.md`](CLAUDE.md)** — project & collaboration rules (Traditional Chinese; startup chain, WDAC decisions, tool-dev rules). Follow it for any code work.

## Two gotchas to know BEFORE you open INSTALL.md
- **Python 3.11 only** — install/test everything with `py -3.11`; the repo's bare `python` may be `.venv-xanylabeling` (no pytest/fastapi). Do NOT use `npm run test:python`.
- **Clone with `--recurse-submodules`** — submodules are ONLY `vendor/AI4BI`, `vendor/LV` (branch `uihuang_dev`), `plugins/cim-modules`. **Labeling (ANnoTation) is a directory JUNCTION, not a submodule** — `INSTALL.md` step 4 handles it. The Tauri shell now lives IN-REPO at `apps/host-tauri` and ships with a committed prebuilt `apps/host-tauri/prebuilt/cim-light.exe` that runs as-is (no sibling clone, no npm install, no Rust toolchain for daily use). Rebuilding the Rust shell is rare and must be done on a machine WITHOUT WDAC enforce, then replace the prebuilt exe (do not re-litigate WDAC).
