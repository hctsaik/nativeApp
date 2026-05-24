# Design: Management Center UX Cleanup

## 1. Workflow-Oriented Navigation

The Management Center uses task-oriented tabs instead of mixing health,
release, repair, and system tasks in the same places:

| Tab | Purpose |
| --- | --- |
| `Health` | Read-only runtime, release readiness, and data consistency summary. |
| `Tools` | Select one active tool, review publish checks, publish module snapshots, and control module Prod visibility. |
| `Sheets` | Compose Sheet definitions and control Sheet Dev/Prod visibility. |
| `Repairs` | Review and apply data consistency repairs. |
| `Audit & Backup` | Export database backup and review recent audit events. |

`Health` does not run repair actions. It produces an `Action Required` list with
the affected area, target, issue, and next step.

## 2. Product Vocabulary

The UI uses distinct labels for different release concepts:

| Concept | UI label | Meaning |
| --- | --- | --- |
| `enabled_prod` | `Prod visibility` | Whether the tool is shown in Prod mode. |
| Active row in `tool_versions` | `Active snapshot` | The snapshot Prod code loading uses. |
| Preflight | `Publish checks` | File and layering checks before a snapshot can be created. |
| Integrity | `Data consistency` | Database relationship consistency, not tool quality. |

Turning off Prod visibility does not delete or roll back the active snapshot.
The UI says this explicitly after the action.

## 3. Tools Page

The active overview table is read-only. It shows:

- ID
- Name
- Category
- Prod visibility
- Active snapshot
- Checks
- Issues

Inactive tools are shown in a separate section below the active list. Prod
visibility changes are no longer applied by editing the overview table. The
operator selects a tool from `Manage`, then uses the single `Prod Control`
panel.

For modules, the control panel shows:

1. Publish checks status.
2. Snapshot diff summary against the active snapshot.
3. `Publish snapshot and enable Prod`.
4. `Enable Prod visibility` or `Turn off Prod visibility`.
5. Launch and version history actions.

Enabling Prod visibility for an unpublished module is blocked with a clear
message to publish a snapshot first. Sheet tools can appear in the Tools
overview, but Sheet Prod visibility is changed only in `Sheets`, where the
operator can see the Sheet tabs and reference readiness together.

## 4. Repairs Page

Data consistency repairs are centralized in `Repairs`. Each issue presents the
target, message, and concrete repair action:

- Turn off Prod visibility for this tool.
- Turn off Prod visibility for this Sheet.
- Keep newest active snapshot.
- Delete orphan version rows.

Repair actions require a confirmation dialog.

## 5. Confirmation For High-Risk Actions

The following actions show a confirmation dialog before writing:

- rollback snapshot
- archive tool
- restore tool
- delete Sheet
- repair data consistency issue

## 6. Deferred Work

The next cleanup should extract view models from `management_runner.py` so the
Streamlit layer only renders data prepared by UI-independent helpers.
