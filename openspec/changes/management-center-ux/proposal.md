# Proposal: Management Center UX Cleanup

## Problem Statement

The Management Center has enough control-plane capability, but the UI makes
operators infer too much:

- Publish, Prod visibility, checks, and active snapshots appear similar even
  though they are different operations or states.
- Readiness and data consistency information appears in several places.
- Prod visibility can be changed from too many surfaces, increasing the chance
  of accidental changes.
- Health metrics do not clearly say what the operator should do next.

## Goals

- Make the first screen explain what needs attention and where to handle it.
- Keep Health read-only.
- Use one selected-tool control panel for Prod visibility changes.
- Use consistent vocabulary:
  `Prod visibility`, `Active snapshot`, `Publish checks`, and
  `Data consistency`.
- Centralize repair actions in one place.

## Non-Goals

- Full visual redesign.
- Replacing Streamlit with React.
- Extracting all view models in this slice.
- Implementing enterprise identity or permission editing.

## User Stories

1. As an operator, I can open Health and immediately see whether runtime,
   release readiness, or data consistency needs attention.

2. As an operator, I can select one tool in Tools and see exactly whether it
   has an active snapshot, whether publish checks pass, and which Prod action is
   allowed.

3. As an operator, I cannot accidentally make an unpublished module visible in
   Prod from an inline table checkbox.

4. As an operator, I can review and run data consistency repairs from a single
   Repairs page.
