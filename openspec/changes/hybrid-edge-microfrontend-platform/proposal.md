# Change: Hybrid Edge Micro-Frontend Platform

## Why

CIM users need desktop-grade access to local compute and files while still
benefiting from web-based UI development, Kubernetes deployment, and microservice
scalability. A pure browser runtime cannot reliably satisfy native file access,
Python library compatibility, and local compute orchestration requirements.

## What Changes

Introduce a dual-mode application platform:

- A local Electron host that owns lifecycle management, native file access, and
  embedded portal navigation.
- A Python sidecar engine packaged as `engine.exe`, launched by Electron, and
  responsible for serving local Streamlit-based tools.
- A DB-driven dynamic tool mode where reviewed Python scripts are loaded,
  verified, and executed locally.
- A React micro-frontend mode where external enterprise applications are embedded
  by iframe and coordinated through `window.postMessage`.
- A GitOps-oriented script publishing model where reviewed Python tools are
  synchronized into the database.

## Scope

In scope:

- Phase 1 planning for Python sidecar foundation.
- Phase 2 planning for Electron host lifecycle management.
- Phase 3 planning for React iframe communication.
- Security requirements for script signatures and iframe messages.
- Packaging and runtime constraints for CPU-only local deployment.

Out of scope for the initial implementation:

- Full database schema implementation.
- Production CI/CD pipeline implementation.
- Complete enterprise authentication service.
- Kubernetes deployment manifests for child React applications.
- Final installer or auto-update mechanism.

## Impact

- Adds a local desktop runtime layer that must be installed on user machines.
- Introduces Python packaging and binary lifecycle concerns.
- Requires clear trust boundaries between host, local sidecar, DB scripts, and
  remote iframe applications.
- Establishes a contract for future low-code tools and enterprise
  micro-frontends.

## Discussion Points

- API gateway is planned as FastAPI for the first implementation.
- Script signature verification is deferred for the first implementation.
- Streamlit scripts are planned to execute with a subprocess-per-tool model.
- The first implementation allows one active tool subprocess at a time.
- Mode 1 Streamlit and Mode 2 React micro-frontends are both embedded with
  iframes.
- The first implementation uses SQLite or mock data through a DB adapter
  interface.
- Local file access is limited to user-selected files or directories.
- The first target platform is Windows only.
- The first packaging tool is electron-builder.
- Development packaging may use a portable build before a formal installer is
  introduced.
- The repository should use a monorepo structure.
- Authentication can use a mock JWT token for the first implementation.
- Development logs should be written under the project/app directory.
- Portable build logs should be written beside the portable executable under a
  `logs/` directory.
- The first implementation should include one sample Streamlit tool.
- Sidecar shutdown should prefer graceful shutdown through FastAPI before using
  forced process termination.
