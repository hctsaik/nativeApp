# Tasks

## 1. Phase 1 - Python Sidecar Planning

- [x] Define `requirements.txt` with CPU-only golden dependencies.
- [x] Design `engine.py` entrypoint responsibilities.
- [x] Define DB script adapter interface.
- [x] Implement runtime SQLite tool adapter seed.
- [x] Define script metadata shape: id, version, content, signature, commit,
  author, approval timestamp.
- [x] Defer signature verification flow while preserving an extension point.
- [x] Define Streamlit launch strategy using subprocess-per-tool.
- [x] Limit first implementation to one active tool subprocess at a time.
- [x] Define and implement one sample Streamlit validation tool.
- [x] Define local health/readiness signal for Electron.
- [x] Define PyInstaller packaging command and expected output layout.

## 2. Phase 2 - Electron Host Planning

- [x] Define Electron project structure.
- [x] Define main-process sidecar manager module.
- [x] Define engine executable path resolution for development and production.
- [x] Define dynamic localhost port allocation.
- [x] Define startup sequence and readiness timeout behavior.
- [x] Define shutdown sequence for graceful termination and forced kill fallback.
- [x] Confirm shutdown strategy: FastAPI graceful shutdown endpoint, then forced
  kill fallback.
- [x] Define abnormal sidecar exit handling.
- [x] Define logging location and minimum diagnostic fields.
- [x] Confirm development log location: project/app directory.
- [x] Confirm portable build log location: portable executable sibling `logs/`.
- [x] Define renderer routing between mode 1 and mode 2.
- [x] Confirm packaging tool: electron-builder.
- [x] Confirm development package type: portable build.
- [x] Add Windows x64 portable packaging script.

## 3. Phase 3 - React iframe Communication Planning

- [x] Define portal iframe component responsibilities.
- [x] Define child app bootstrap listener responsibilities.
- [x] Define message envelope schema.
- [x] Define allowed message types: `CHILD_READY`, `AUTH_TOKEN`,
  `ROUTE_CHANGED`, `HOST_NAVIGATE`, `ERROR`.
- [x] Define origin allowlist strategy.
- [x] Define token transfer timing and refresh behavior.
- [x] Define route synchronization behavior.
- [x] Define failure states for unavailable child app or rejected origin.

## 4. Security and GitOps Planning

- [x] Defer signing mechanism to a later phase.
- [x] Defer key ownership and rotation process to a later phase.
- [ ] Define CI/CD flow from reviewed Python file to DB update.
- [ ] Define rollback/version selection behavior.
- [ ] Define audit log requirements.
- [x] Define policy for local file access exposure.
- [x] Implement host-selected file path synchronization to sidecar.
- [x] Confirm first implementation local file access policy: user-selected files
  or directories only.

## 5. Discussion and Acceptance

- [x] Confirm API gateway language direction: FastAPI.
- [x] Confirm script execution isolation model: subprocess-per-tool.
- [x] Confirm database technology assumptions: SQLite/mock through DB adapter.
- [x] Confirm target OS: Windows first.
- [x] Confirm installer expectations: development portable first; formal
  installer later.
- [x] Confirm repository strategy: monorepo.
- [x] Confirm first implementation auth source: mock JWT token.
- [x] Confirm sample Streamlit tool requirement.
- [x] Confirm Mode 1 Streamlit embedding: iframe.
- [x] Confirm Mode 2 React micro-frontend embedding: iframe.
- [x] Confirm DB assumption: SQLite/mock through DB adapter interface.
- [x] Confirm port strategy: dynamic available localhost port.
- [x] Confirm first implementation active tool limit: one active tool.
- [x] Confirm initial repository scaffold strategy: monorepo with
  `apps/host-electron`, `apps/portal-react`, `sidecar/python-engine`, and
  `packages/shared-protocol`.

## 6. Verification

- [x] Run JavaScript dependency install.
- [x] Run Python dependency install.
- [x] Run React production build.
- [x] Run Python compile check.
- [x] Run development sidecar smoke test.
- [x] Run SQLite tool registry smoke test.
- [x] Run selected-paths API smoke test.
- [x] Generate PyInstaller `engine.exe`.
- [x] Generate electron-builder portable package.
- [x] Generate electron-builder x64 portable package.
- [x] Run packaged `engine.exe` smoke test in an environment that allows
  generated executables.
- [x] Run packaged Electron app sidecar readiness smoke test.
- [x] Run Python unit test suite (32 tests passing).
- [x] Run JavaScript unit test suite (29 tests passing).

## 7. Post-First-Pass Improvements

- [x] Fix `run_streamlit_tool` to use `SQLiteToolAdapter` instead of
  `MockToolAdapter` so subprocess tool lookups stay consistent with the main
  process registry.
- [x] Add `wait_for_port` readiness check so `/tools/{id}/start` returns only
  after Streamlit is accepting connections.
- [x] Add Stop Tool IPC handler, preload method, and portal UI button.
- [x] Track active tool state in the portal; replace Start with Stop button
  while a tool is running.
- [x] Implement sidecar unexpected-exit error banner in the portal and disable
  tool controls when the sidecar is down.
- [x] Switch `.content` layout from CSS grid to flexbox so the error banner
  does not break the frameStage height calculation.
- [x] Add error handling (try/catch) to `openSelectedTool` and `stopActiveTool`
  in the portal.
- [x] Fix Electron dev startup failure caused by `ELECTRON_RUN_AS_NODE=1` being
  set in the Claude Code CLI environment: added `launch-electron.js` to strip
  the env var before spawning Electron, updated the dev script to use it.
- [x] Add `apps/host-electron/src/electron-env.test.js` (12 tests) documenting
  the root cause symptom and verifying the launcher fix; `npm test` now covers
  both `shared-protocol` (17) and `host-electron` (12) for 29 tests total.
