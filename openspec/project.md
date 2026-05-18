# Project Overview

## Purpose

Build a hybrid edge-computing and micro-frontend platform for CIM environments.
The platform must combine local native compute and file access with enterprise
web delivery patterns.

## Architecture Direction

The system uses Electron as the desktop host, a local Python sidecar for dynamic
Streamlit tools, and React-based micro-frontends for enterprise applications.

Two operating modes are planned:

- DB-driven dynamic rendering mode for low-code internal tools.
- Enterprise micro-frontend mode for React applications deployed on Kubernetes.

## Technical Constraints

- Host shell: Electron + React.
- Dynamic UI engine: local Streamlit.
- Local compute core: Python packaged as `engine.exe`.
- API gateway: FastAPI in Python or Web API in C#.
- Runtime profile: CPU-only; avoid GPU dependencies.
- Python golden requirements: `streamlit`, `requests`, `pandas`, `numpy`,
  `scipy`, `Pillow`, `matplotlib`, `scikit-learn`, and
  `opencv-python-headless`.

## Security Principles

- Dynamic scripts must be verified before execution.
- Script updates should be traceable to reviewed GitOps workflows.
- Electron-to-sidecar communication should default to local-only network access.
- iframe communication must validate message origin and message shape.

