# Label Manager Specification

## ADDED Requirements

### Requirement: Global label scan across manifest

The label manager SHALL scan all X-AnyLabeling JSON files in the current manifest
and return a consolidated view of every label in use.

#### Scenario: Labels are scanned

- WHEN the label manager executes for a manifest
- THEN it SHALL read every item's sidecar `.json` file
- AND SHALL count occurrences in both `shapes[].label` and `flags.classification`
- AND SHALL return a dict mapping each label to the list of file paths where it appears

### Requirement: Near-duplicate label detection

#### Scenario: Labels differ only by case or minor typo

- WHEN the label scan returns a label set
- THEN the system SHALL compute pairwise `SequenceMatcher` ratios
- AND SHALL surface label pairs with ratio greater than 0.8 and less than 1.0
  as near-duplicate warnings in the UI

### Requirement: Atomic rename across all files

#### Scenario: Annotator renames a label

- WHEN a rename action is confirmed
- THEN every affected `.json` file SHALL be updated with the new label name
  in both `shapes[].label` and `flags.classification`
- AND each file write SHALL use the `tmp + os.replace` pattern
- AND if the process is interrupted mid-rename, no file SHALL be left in a
  partially-written state

#### Scenario: New name is empty

- WHEN the annotator provides an empty string as the new name
- THEN the rename button SHALL be disabled
- AND no files SHALL be modified

### Requirement: Two-step confirmation for destructive actions

Rename, merge, and delete actions SHALL require a two-step confirmation.

#### Scenario: Rename is previewed

- WHEN the annotator clicks Preview
- THEN the UI SHALL show a warning stating how many files will be affected
- AND the Confirm button SHALL become enabled

#### Scenario: Confirm is not yet clicked

- WHEN Preview has not been clicked or was reset
- THEN the Confirm button SHALL be disabled

### Requirement: Merge collapses multiple labels into one

#### Scenario: Annotator merges source labels into a target label

- WHEN a merge action is confirmed with a list of source labels and a target label
- THEN every occurrence of each source label SHALL be replaced with the target label
- AND the replacement SHALL use the same atomic write pattern as rename

### Requirement: Delete removes label from all files

#### Scenario: Annotator deletes a label

- WHEN a delete action is confirmed
- THEN every shape with that label SHALL be removed from `shapes`
- AND any `flags.classification` equal to that label SHALL be cleared to an empty string
- AND the atomic write pattern SHALL be used for every modified file

### Requirement: Labels used only in flags are included

#### Scenario: Label exists only as a classification flag, not in shapes

- WHEN `flags.classification` contains a label that does not appear in any shape
- THEN that label SHALL still appear in the scan results
- AND SHALL be eligible for rename, merge, and delete operations
