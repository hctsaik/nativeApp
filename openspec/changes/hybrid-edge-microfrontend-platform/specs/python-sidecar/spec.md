# Python Sidecar Specification

## ADDED Requirements

### Requirement: CPU-only Python runtime

The sidecar SHALL be packaged with CPU-only Python dependencies.

#### Scenario: Dependency set is prepared

- WHEN dependencies are installed for packaging
- THEN the dependency list SHALL include `streamlit`, `requests`, `pandas`,
  `numpy`, `scipy`, `Pillow`, `matplotlib`, `scikit-learn`, and
  `opencv-python-headless`
- AND it SHALL NOT require GPU-specific packages

### Requirement: Packaged engine executable

The sidecar SHALL be packageable as `engine.exe`.

#### Scenario: Packaging is run

- WHEN PyInstaller packaging completes successfully
- THEN the output SHALL include an executable named `engine.exe`
- AND the executable SHALL be suitable for placement in Electron application
  resources

### Requirement: Script verification extension point

The sidecar SHALL keep script verification behind an explicit extension point,
but first implementation does not need to enforce DB script signatures.

#### Scenario: Verification is disabled for first implementation

- WHEN the engine loads a script during the first implementation
- THEN the engine MAY execute it without signature verification
- AND the execution path SHALL remain structured so verification can be added
  later

#### Scenario: Verification is added in a later phase

- WHEN signature verification is enabled
- THEN unsigned or mismatched scripts SHALL fail closed before execution

### Requirement: Health readiness signal

The sidecar SHALL expose a readiness signal for the Electron host.

#### Scenario: Sidecar is ready

- WHEN the sidecar has started successfully
- THEN Electron SHALL be able to determine that the sidecar is ready before
  navigating users to local Streamlit content

### Requirement: Single active tool subprocess

The first implementation SHALL support one active Streamlit tool subprocess at a
time.

#### Scenario: User switches tools

- WHEN a user opens another Streamlit tool while one is already active
- THEN the system SHALL stop or replace the previous tool subprocess before
  starting the next one

### Requirement: Sample Streamlit validation tool

The first implementation SHALL include one sample Streamlit tool for end-to-end
validation.

#### Scenario: User opens sample tool

- WHEN the user opens the sample Streamlit tool
- THEN the tool SHALL allow CSV-based validation
- AND SHALL display basic pandas summary output
- AND SHALL render a simple chart
