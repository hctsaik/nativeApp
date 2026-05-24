# Change: Management Center Control Plane

## Why

The current Management Center can publish tools, toggle Prod visibility, edit
Sheets, and export database JSON. As the platform grows, operators need a
single control plane that shows platform health and release readiness before
changing Dev/Prod state.

## What Changes

- Add a Management Center dashboard for mode, tool, version, Sheet, and runtime
  status.
- Add Prod readiness checks for tools and Sheets.
- Add module preflight checks for required layer files and manifests.
- Surface sidecar runtime and diagnostics from existing local control APIs.
- Keep this first increment local and read-only except for existing operations.

## Out Of Scope

- Enterprise login, SSO, or external identity providers.
- Full management API migration for every DB write.
- Code signing enforcement.
- Backup restore/import.

## Impact

- `sidecar/python-engine/tools/management_runner.py`
- `sidecar/python-engine/management_insights.py`
- `sidecar/python-engine/tests/test_management_insights.py`
- `docs/modules/management_center.md`
