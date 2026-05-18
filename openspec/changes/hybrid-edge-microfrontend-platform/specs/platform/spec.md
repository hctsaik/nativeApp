# Platform Specification

## ADDED Requirements

### Requirement: Electron host shell

The system SHALL use Electron as the local desktop host for the CIM platform.

#### Scenario: App startup launches the host

- WHEN the user opens the desktop application
- THEN the Electron main process SHALL initialize the React portal
- AND prepare local sidecar lifecycle management

### Requirement: Dual-mode operation

The system SHALL support both DB-driven local tools and enterprise
micro-frontends.

#### Scenario: User opens low-code tool mode

- WHEN the user selects a DB-driven tool
- THEN the portal SHALL display the local Streamlit runtime in an iframe

#### Scenario: User opens enterprise micro-frontend mode

- WHEN the user selects an enterprise application
- THEN the portal SHALL embed the configured React application through an iframe

### Requirement: Local native capability boundary

The system SHALL use Electron and the Python sidecar for local native capability
needs instead of relying on browser-only APIs.

#### Scenario: Local compute is required

- WHEN a tool needs local compute or local file access
- THEN the request SHALL be handled by the trusted local runtime
- AND not by unrestricted iframe JavaScript

### Requirement: Windows-first delivery

The first implementation SHALL target Windows desktop deployment.

#### Scenario: Sidecar is packaged

- WHEN the sidecar is packaged for the first implementation
- THEN the output SHALL be a Windows executable named `engine.exe`

### Requirement: Monorepo project structure

The first implementation SHALL use a monorepo project structure.

#### Scenario: Repository is scaffolded

- WHEN the initial project scaffold is created
- THEN it SHALL include `apps/host-electron`
- AND it SHALL include `apps/portal-react`
- AND it SHALL include `sidecar/python-engine`
- AND it SHALL include `packages/shared-protocol`

### Requirement: User-mediated local file access

The first implementation SHALL only grant local file access through explicit
user file or directory selection.

#### Scenario: Tool needs a local file

- WHEN a tool needs a local file or directory
- THEN the host SHALL require the user to select the file or directory
- AND the trusted local runtime SHALL receive only the approved path
