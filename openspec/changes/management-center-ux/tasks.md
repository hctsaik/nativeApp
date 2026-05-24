# Tasks: Management Center UX Cleanup

## Implementation

- [x] Write OpenSpec proposal and design.
- [x] Rename the primary tabs to workflow-oriented areas.
- [x] Make Health read-only and move repair actions out of Health.
- [x] Add an Action Required list with issue and next-step guidance.
- [x] Remove inline Prod checkbox writes from the overview table.
- [x] Add a single selected-tool Prod Control panel.
- [x] Show active tools in the main list and inactive tools in a separate section.
- [x] Keep Sheet Prod visibility changes in Sheets with the Sheet Prod gate.
- [x] Add confirmation dialogs for rollback, archive, restore, Sheet delete, and repair.
- [x] Rename release concepts to Prod visibility, Active snapshot, Publish checks, and Data consistency.
- [x] Move data consistency repairs into the Repairs tab.
- [x] Keep audit events and backup under Audit & Backup.
- [x] Update regression tests for the new UX contract.

## Testing

- [x] Focused compile check for `management_runner.py`.
- [x] Focused source-level regression tests.
- [x] Full Python test suite.
- [x] Streamlit smoke test for Management Center startup.
