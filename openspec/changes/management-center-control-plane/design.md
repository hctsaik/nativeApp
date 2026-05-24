# Design: Management Center Control Plane

## Overview

The first control-plane increment introduces read-only insight functions and a
Dashboard tab. The insight functions live outside Streamlit so they can be unit
tested and later reused by FastAPI management endpoints.

## Dashboard Data

The Dashboard summarizes:

- Current environment mode: `DEV` or `PROD`
- Total visible tools, Prod-enabled tools, archived tools
- Published module count and Prod readiness warnings
- Sheet reference warnings
- Sidecar `/runtime` and `/diagnostics` payloads when `CIM_CONTROL_PORT` is set

## Prod Readiness

A tool is considered Prod-ready when:

- It is enabled.
- If it is a module, it has an active `tool_versions` snapshot.
- If it is Prod-enabled, its active snapshot is present.

A Sheet is considered Prod-ready when:

- Every referenced plugin exists in `tools`.
- Every referenced plugin is enabled.
- If the Sheet is Prod-enabled, every referenced module is also Prod-enabled.
- If the Sheet is Prod-enabled and references a module, the referenced module
  has an active snapshot.

## Module Preflight

Module preflight checks the filesystem source used for publishing:

- `plugin.yaml` exists.
- `{short_id}_input.py`, `{short_id}_process.py`, and `{short_id}_output.py`
  exist.
- The process layer does not import Streamlit.

The publish action uses this preflight as a gate. A module with failing
preflight checks cannot be published to Prod from the Management Center.

## Publish Metadata

Publish requires operator-provided metadata:

- `changelog`: what changed in this published snapshot
- `author`: who is publishing the snapshot

These values are stored in `tool_versions.changelog` and
`tool_versions.author`.

## Version Diff And Publish Summary

Before publishing, the Management Center compares the current filesystem module
snapshot with the active Prod snapshot:

- added files
- removed files
- changed files
- unchanged files

The diff is a file-level summary, not a full source-code diff. After publish,
the audit event stores the new version id, file count, whether `plugin.yaml` was
included, and the pre-publish diff summary.

## Sheet Prod Gate

The Sheet Prod toggle validates the target Sheet before enabling Prod. A Sheet
cannot be enabled in Prod when any tab references a missing, archived,
non-Prod-enabled, or unpublished module.

## Audit Log

Management Center records critical local administrative actions into
`audit_events`:

- publish / rollback
- archive / restore
- Prod enable / disable
- Sheet create / update / delete
- Sheet Dev/Prod enable / disable

Each audit event stores timestamp, actor, action, target type, target id, and a
JSON details payload. The first increment stores events locally in SQLite and
shows recent events in the System tab.

## Integrity Checks

The Dashboard and System tab expose read-only integrity checks:

- tool readiness issues
- Sheet reference issues
- multiple active versions for one tool
- version rows whose tool no longer exists

These checks are informational first. Later changes can reuse them as API
preflight gates or repair workflows.

## Integrity Repair Actions

The System tab exposes conservative repair actions for integrity issues:

- Disable Prod for a tool that is Prod-enabled but not release-ready.
- Disable Prod for a Sheet with failing Prod references.
- Normalize multiple active versions by keeping the newest active version.
- Delete orphan `tool_versions` rows that point to a missing tool.

Repair actions are admin-only and write audit events.

## Management Permission Enforcement

This increment adds local role enforcement for Management Center write actions.
`AuthProvider.get_current_role()` reads `CIM_USER_ROLE` when set, defaulting to
`admin`. Non-admin roles can view the Management Center but write actions are
disabled in the UI.

This is not a replacement for enterprise identity. It is a local enforcement
step that keeps the permission model testable until the platform has a real
identity source.

## Tool Management UX

The Tool Management tab adds filters and a compact overview table so operators
can find tools by category and release status before opening detailed actions.

## Future Path

The insight module is intentionally UI-independent. Later changes can expose the
same checks through sidecar management APIs and use them as publish gates.
