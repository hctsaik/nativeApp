# Design

## Overview

The platform has three cooperating layers:

1. Electron host
2. Python sidecar engine
3. React micro-frontend applications

Electron is the trusted local shell. It starts and stops the local Python engine,
hosts the React portal, mediates native desktop capabilities, and embeds external
enterprise applications.

The Python engine exposes local Streamlit tools and, later, local compute APIs.
The micro-frontend layer provides enterprise-grade React applications that can be
deployed independently.

## Runtime Topology

```text
User Desktop
  Electron Host
    React Portal
      Mode 1 iframe: local Streamlit at dynamic localhost port
      Mode 2 iframe: enterprise React app on K8s
    Node main process
      starts/stops engine.exe
      watches health and process lifecycle
  Python Sidecar
    engine.exe
      loads approved script metadata
      keeps a future script verification extension point
      serves Streamlit runtime
      calls local compute/API services
```

## Phase 1: Python Sidecar

The sidecar starts with a minimal `engine.py` foundation:

- declares the golden Python dependencies in `requirements.txt`;
- starts a Streamlit-compatible runtime entrypoint;
- loads script metadata from a DB adapter abstraction;
- leaves script signature verification as a later phase;
- exposes a simple health endpoint or startup signal for Electron;
- remains CPU-only and uses `opencv-python-headless`.

The first implementation may use SQLite, file-backed mock data, or in-memory
mock data, but the design must keep the DB adapter boundary explicit.

The current implementation seeds a runtime SQLite tool registry under the
sidecar log/data directory and keeps the bundled sample tool registered there.

Only one active tool subprocess is required for the first implementation.

## Phase 2: Electron Host

Electron owns the sidecar lifecycle:

- locate packaged `engine.exe` from the application resources directory;
- start it during application startup;
- allocate available localhost ports dynamically;
- wait for local health readiness before navigating to mode 1;
- use a longer readiness timeout for packaged builds because PyInstaller onefile
  startup can spend time extracting bundled resources;
- terminate the process when the app exits;
- request graceful shutdown through FastAPI before forced termination;
- handle abnormal exits with visible error state and logs;
- avoid orphaned background processes.

The host should separate main-process sidecar management from renderer UI code.

## Phase 3: React iframe Communication

Mode 2 uses iframe embedding for enterprise React apps.

Mode 1 also uses iframe embedding for local Streamlit content.

The host portal and child app communicate through `window.postMessage`:

- portal sends authentication context such as JWT token;
- child app acknowledges readiness before sensitive data is sent;
- child app emits route change events;
- portal updates its own URL or navigation state;
- both sides validate `origin`, `source`, and message schema.

## Security Model

### Local File Access

For the first implementation, local file access is only granted through explicit
user selection. The host should provide file or directory picker flows and pass
approved paths to the trusted local runtime. iframe applications should not be
allowed to scan arbitrary local paths.

The current implementation synchronizes host-selected file paths to the sidecar
through `/selected-paths`. Streamlit tools receive the selected paths file path
through environment variables and may read only those user-selected paths.

### Script Verification

Script signature verification is not part of the first implementation. The
design should keep a verification boundary so this can be added later without
rewriting the sidecar execution model.

Future recommended direction:

- CI/CD signs reviewed script content after merge to `main`;
- DB stores script content, signature, signing metadata, version, and source
  commit;
- engine verifies with a public key bundled with the app or retrieved from a
  trusted configuration channel.

### iframe Messaging

`postMessage` must never use unrestricted trust.

Recommended direction:

- maintain an allowlist of child app origins;
- use typed message envelopes;
- ignore unknown message types;
- avoid logging JWT values;
- send token only after child app sends a trusted `READY` message.

## Packaging Notes

The sidecar should be packaged with PyInstaller. The expected output is
`engine.exe`, copied into the Electron resource directory during packaging.

The Python dependency set must avoid GPU builds and GUI-conflicting OpenCV
packages. `opencv-python-headless` is required.

The first supported platform is Windows.

Electron packaging should use `electron-builder`. During development and early
validation, a portable Windows build is acceptable before introducing a formal
installer.

Packaging scripts should support both the current machine architecture and an
explicit Windows x64 portable target. The x64 target is intended for typical
Windows production or factory PCs.

The current portable executable filename is shared across architectures, so
successive architecture builds may overwrite the top-level portable executable
in `release/`.

The packaged Electron app should include:

- `resources/engine/engine.exe`;
- `resources/portal/index.html`;
- `resources/portal/assets/*`.

## Repository Structure

The project should use a monorepo so the Electron host, React portal, Python
sidecar, and shared message protocol can evolve together.

Recommended structure:

```text
apps/
  host-electron/
  portal-react/
sidecar/
  python-engine/
packages/
  shared-protocol/
```

## Authentication

The first implementation may use a mock JWT token. The iframe communication
contract should still use the same `AUTH_TOKEN` message shape expected by future
real authentication.

## Logging

Log locations depend on runtime mode:

- Development: write logs under the project or app directory for easy debugging.
- Portable build: write logs beside the portable executable under `logs/`.

Installer-based production logging can be decided later.

## Sample Tool

The first implementation should include one sample Streamlit tool for
end-to-end validation. Recommended behavior:

- allow user-selected CSV input;
- load data with pandas;
- show table summary statistics;
- render a simple matplotlib chart;
- demonstrate a local FastAPI request path where appropriate.

## Verification Status

Current implementation has been validated with:

- JavaScript dependency install;
- Python dependency install;
- React portal production build;
- Python syntax compilation;
- development sidecar smoke test for health, tool start, tool stop, and
  shutdown;
- SQLite tool registry smoke test;
- selected-paths API smoke test;
- PyInstaller output generation for `engine.exe`;
- electron-builder portable package generation;
- electron-builder x64 portable package generation;
- packaged `engine.exe` smoke test for health and graceful shutdown;
- packaged Electron app sidecar readiness smoke test;
- Python unit test suite (32 tests, all passing) covering SQLiteToolAdapter,
  SelectedPathStore, ToolRegistry, wait_for_port, and all FastAPI routes;
- JavaScript unit test suite (17 tests, all passing) covering MessageTypes,
  createMessage, and isProtocolMessage in the shared-protocol package.

## Testing

Run tests with:

```bash
# Python sidecar (requires pytest and httpx)
npm run test:python

# JavaScript shared-protocol
npm test
```

Troubleshooting note: if a packaged Electron executable exits immediately and
prints a Node.js version for `--version`, check for `ELECTRON_RUN_AS_NODE=1`.
That environment variable forces Electron to run as Node and prevents the
desktop host from loading.

Windows 11 Smart App Control can still block newly generated unsigned or
locally-signed executables. Development validation should use `npm run dev` or a
machine/policy that permits generated binaries; production packaging should use
a proper trusted code-signing certificate.
