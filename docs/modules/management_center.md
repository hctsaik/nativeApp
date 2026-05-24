# Management Center

## Overview

| Field | Value |
| --- | --- |
| `tool_id` | `management-center` |
| Runner | `sidecar/python-engine/tools/management_runner.py` |
| Purpose | Local admin console for release readiness, module snapshots, Prod visibility, Sheet composition, data consistency repairs, audit, and backup. |

## Operator Workflow

| Tab | Purpose |
| --- | --- |
| `Health` | Read-only runtime, release readiness, and data consistency summary. Shows `Action Required` rows with next-step guidance. |
| `Tools` | The selected tool action panel appears above the active tools table. Selecting one table row updates that single action panel for Prod visibility, order, snapshot, publish, launch, archive, and lifecycle controls. Inactive tools have a separate restore section. |
| `Runs & Usage` | Recent tool launches and usage summary. Shows run status, duration, ports, PID, log path, and 1-90 day usage counts. |
| `Sheets` | Select one Sheet and edit its ordered step table. The page shows concise Prod readiness summaries in the action panel and per-step readiness labels in the table. |
| `Repairs` | Review and apply data consistency repairs. Repair actions require confirmation. |
| `Audit & Database` | Review recent audit events and backend status. SQLite mode includes a local JSON backup/dry-run tool; Oracle mode delegates backup and restore to the DBA/Oracle policy. |

## Vocabulary

- `Prod visibility`: whether a tool or Sheet appears when the app runs in Prod mode.
- `Active snapshot`: the current published module snapshot loaded by Prod.
- `Publish checks`: file and layer checks before a module snapshot can be created.
- `Data consistency`: database relationship issues that may need repair.

Turning off Prod visibility does not delete or roll back the active snapshot.

## Release And Prod Rules

Publishing a module from `Tools` creates a new active snapshot and enables Prod
visibility for that module. Enabling Prod visibility without publishing is
blocked for unpublished modules.

`Tools > Import / New Module` supports two creation paths:

- `Upload Module Zip`: validates an uploaded module package in memory and imports it as
  an active DB snapshot with Prod visibility off. Existing module IDs require an
  explicit update choice.
- `New Module`: creates a development scaffold under `scripts/module_NNN` with
  `plugin.yaml`, input/process/output skeletons, and README.

Release is intentionally split. `Create snapshot` writes an active snapshot and
leaves Prod visibility unchanged. `Enable Prod visibility` exposes the active
snapshot after readiness checks pass. `Snapshot + Prod` remains available as a
one-click shortcut for reviewed filesystem modules.

## Module Zip Package

The first supported package format is:

```text
module_012/
  plugin.yaml
  012_input.py
  012_process.py
  012_output.py
  README.md
```

The importer rejects unsafe paths, nested files, blocked executable file types,
large files, suspicious compression ratios, invalid IDs, invalid versions,
unsupported runners, Python syntax errors, blocked imports/calls, and Streamlit
imports in the process layer. Uploaded packages are not executed during import
and do not install dependencies.

Sheet Prod visibility must go through the Sheet gate. A Sheet cannot be shown in
Prod when a referenced tool is missing, archived, hidden from Prod, or when a
referenced module has no active snapshot. Sheet tools can appear in the Tools
overview, but Sheet Prod changes are controlled in `Sheets` so Sheet composition
and visibility are handled in one place.

Step edits are draft changes until `Save Sheet` is pressed. `Discard edits`
throws away unsaved step/name/description changes and reloads the saved Sheet.
When a Sheet has unsaved changes, Prod visibility changes are disabled until the
operator saves or discards the draft. Repeated readiness details for the same
step are grouped into one short status, such as `Needs release`.

High-risk actions use confirmation dialogs:

- rollback snapshot
- archive or restore tool
- delete unpublished draft tool catalog entry
- delete Sheet
- repair data consistency issue

`Delete unpublished draft` is intentionally narrow. It is allowed only when the
module has no snapshots, is not visible in Prod, and is not referenced by any
Sheet. It removes the management catalog entry only; source files are left on
disk.

## Runs And Usage

The sidecar records a `tool_runs` row when a regular, Sheet, or external tool is
successfully launched. Stopping the active tool closes the run with status
`stopped`. The Management Center uses these rows to show recent launches and
usage counts.

This is the first operational usage layer. Result-level success/failure inside
Streamlit modules still needs a future execution-complete hook so completed and
failed application runs can be distinguished from stopped sessions.

## Audit And Database

`Audit & Database` is backend-aware. Audit remains visible for every backend
because management actions still need an operator trail.

SQLite/dev mode shows a local JSON backup download and restore dry-run. The
dry-run validates table names and row counts without writing to the database.
Full SQLite restore execution should add schema compatibility checks,
transaction rollback, and an automatic pre-restore backup.

Oracle/prod mode does not expose JSON backup or restore controls. Oracle backup,
restore, retention, and disaster recovery are managed outside Management Center
by DBA-controlled policy such as RMAN, storage snapshots, and approved restore
procedures.

## Runtime Database

The sidecar resolves the management database in this order:

1. `CIM_TOOLS_DB`, when set.
2. `<log-dir>/data/tools.sqlite`, when the sidecar is started with `--log-dir`.
3. `sidecar/python-engine/config/tools.sqlite` as a local fallback.

Electron passes a persistent log directory, so packaged publish, rollback,
Sheet, and audit state should survive restarts.

## Architecture

Platform management database access is routed through the `ManagementStore`
behavior port in `management_store.py`. The default implementation is
`SQLiteManagementStore`; Oracle support is represented by
`OracleManagementStore` but still needs production schema/migration settings.

Write workflows are coordinated through `ManagementUseCases` where possible:

- publish snapshot and enable Prod visibility
- rollback
- tool Prod visibility changes
- Sheet Dev/Prod gates
- Sheet create/update/delete
- data consistency repair

SQLite schema creation and legacy compatibility live in
`SQLiteManagementSchema`. The sidecar startup path now initializes the same
schema service used by Management Center tests and stores.

## Packaging Notes

The Electron source fallback must include the management modules:

- `management_insights.py`
- `management_schema.py`
- `management_store.py`
- `management_use_cases.py`
- `management_oracle_store.py`

If packaged `engine.exe` is unavailable, the fallback source sidecar depends on
these files.
