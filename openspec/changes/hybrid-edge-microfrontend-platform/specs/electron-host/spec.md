# Electron Host Specification

## ADDED Requirements

### Requirement: Sidecar startup lifecycle

The Electron host SHALL start the packaged Python sidecar during application
startup.

#### Scenario: Application starts normally

- WHEN Electron starts
- THEN the main process SHALL locate `engine.exe`
- AND start it as a background child process
- AND wait for readiness before opening local tool content

### Requirement: Dynamic local port allocation

The Electron host SHALL allocate available localhost ports dynamically for local
runtime services.

#### Scenario: Default port is unavailable

- WHEN a preferred local port is already in use
- THEN the host SHALL choose another available localhost port
- AND pass the selected port to the sidecar or tool runtime

### Requirement: Sidecar shutdown lifecycle

The Electron host SHALL terminate the Python sidecar when the application exits.

#### Scenario: Application closes normally

- WHEN the user closes the application
- THEN Electron SHALL request graceful sidecar shutdown through FastAPI
- AND SHALL use a forced process termination fallback if graceful shutdown times
  out

### Requirement: Sidecar failure handling

The Electron host SHALL detect abnormal sidecar failure.

#### Scenario: Sidecar exits unexpectedly

- WHEN the sidecar process exits unexpectedly
- THEN the host SHALL record diagnostic information
- AND the renderer SHALL show a recoverable error state

### Requirement: Runtime log locations

The host SHALL write logs to a runtime-appropriate location.

#### Scenario: Development runtime

- WHEN the app runs in development
- THEN logs SHALL be written under the project or app directory

#### Scenario: Portable build runtime

- WHEN the app runs as a portable build
- THEN logs SHALL be written beside the portable executable under `logs/`
