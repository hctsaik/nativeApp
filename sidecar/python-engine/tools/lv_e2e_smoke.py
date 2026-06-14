"""End-to-end smoke test: prove the LV ('app-lv') app really launches via the engine.

Why this exists
---------------
The portal cannot be driven by a plain browser/Playwright here: it needs the
Electron `preload` bridge (`window.nativeApi` → IPC) to list/start tools, so a
Chromium pointed at the Vite URL is a dead end, and no cim-gui MCP server is
connected in this environment. The authoritative question — "does LV actually
start and serve its UI?" — is fully answerable at the engine + HTTP layer, which
is exactly what the portal iframe ultimately points at.

What it verifies (the LV-specific bits that can't be vouched by app-ai4bi):
  1. engine boots standalone and registers `app-lv` (category "app") from YAML.
  2. POST /tools/app-lv/start succeeds → ToolStartResponse shape (single URL,
     category app, run_id) — exercises _start_app + per-tool venv PYTHONPATH
     injection + `runner: lv` resolution + port orchestration + wait_for_port.
  3. the returned URL serves a LIVE Streamlit: GET /_stcore/health == "ok".
  4. LV's *whole* app.py import graph resolves in the engine's runtime-equivalent
     environment (base interpreter + the per-tool venv's site-packages prepended
     on PYTHONPATH): we `import app` so every top-level import runs — the 14 venv
     packages (torch/transformers/umap/…), streamlit+pandas from platform core,
     tkinter, and LV's flat sibling modules (interaction/_utils/manifest/…). This
     is the faithful proof that app.py would run when a browser session connects:
     a plain `GET /` only returns Streamlit's static SPA shell (page_title from
     set_page_config is applied client-side, so it is NOT in the raw HTML and
     cannot be asserted), and the script body only executes per websocket session.
  5. engine.log has no Traceback / "did not become ready".
  6. POST /tools/stop cleans up.

Golden path deliberately avoids model weights (LV_MODELS_DIR/LV_INCEPTION_DIR may
be empty): first-render only does set_page_config + toolbar + tab names;
load_model only fires on user "Run". So no weights are required to prove launch.

Prereq: run tools/lv_prebuild_deps.py first so the per-tool venv exists and the
engine's prewarm hits the fingerprint (otherwise the first /start blocks on a
multi-GB pip install).

Usage (from repo root):
    py -3.11 sidecar/python-engine/tools/lv_e2e_smoke.py
Exit code 0 = PASS, non-zero = FAIL.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

_ENGINE_ROOT = Path(__file__).resolve().parents[1]  # sidecar/python-engine
_ENGINE_PY = _ENGINE_ROOT / "engine.py"
_TOOL_ID = "app-lv"
_LV_SCRIPTS = _ENGINE_ROOT / "vendor" / "LV" / "scripts"
_VENV_SITE = _ENGINE_ROOT / ".tool-venvs" / _TOOL_ID / "Lib" / "site-packages"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http(method: str, url: str, timeout: float = 10.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def _wait_engine(base: str, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _ = _http("GET", f"{base}/health", timeout=3.0)
            if status == 200:
                return True
        except (urllib.error.URLError, ConnectionError, socket.timeout, OSError):
            pass
        time.sleep(0.5)
    return False


def _verify_lv_import_graph() -> tuple[bool, str]:
    """Import LV's app.py in the engine's runtime-equivalent env.

    The engine spawns LV with the base interpreter (which carries platform-core
    streamlit+pandas) and prepends the per-tool venv's site-packages on
    PYTHONPATH (torch/transformers/umap/…). We replicate that exactly, then
    `import app` so every top-level import in app.py runs (heavy deps + tkinter +
    LV's flat sibling modules) without executing main(). Success == the whole
    import graph resolves in the env LV actually runs under.
    """
    if not _VENV_SITE.exists():
        return False, f"per-tool venv missing ({_VENV_SITE}); run lv_prebuild_deps.py first"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(_VENV_SITE) + (os.pathsep + existing if existing else "")
    code = ("import sys; sys.path.insert(0, r'%s'); import app; "
            "print('IMPORT_OK main=' + str(callable(getattr(app, 'main', None))))"
            % str(_LV_SCRIPTS))
    try:
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(_LV_SCRIPTS),
                              env=env, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"runner error: {exc}"
    if proc.returncode == 0 and "IMPORT_OK" in proc.stdout:
        return True, proc.stdout.strip().splitlines()[-1]
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, " | ".join(tail[-3:]) if tail else f"exit {proc.returncode}"


class _Checks:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def ok(self, cond: bool, label: str, detail: str = "") -> None:
        mark = "PASS" if cond else "FAIL"
        print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
        if not cond:
            self.failures.append(label)


def main() -> int:
    checks = _Checks()
    log_dir = Path(tempfile.mkdtemp(prefix="lv_e2e_"))
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    engine_log = log_dir / "engine.log"

    print(f"[lv-e2e] engine root : {_ENGINE_ROOT}")
    print(f"[lv-e2e] control port: {port}")
    print(f"[lv-e2e] log dir     : {log_dir}")

    env_python = sys.executable  # base py-3.11 running this harness
    proc = subprocess.Popen(
        [env_python, str(_ENGINE_PY), "--control-port", str(port),
         "--log-dir", str(log_dir), "--rebuild-catalog"],
        cwd=str(_ENGINE_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    tool_url = ""
    try:
        print("[lv-e2e] waiting for engine /health …")
        if not _wait_engine(base):
            checks.ok(False, "engine boots and /health responds")
            return _finish(checks, proc, engine_log)
        checks.ok(True, "engine boots and /health responds")

        # 1) catalog registration
        status, body = _http("GET", f"{base}/tools", timeout=15.0)
        tools = json.loads(body) if status == 200 else []
        lv = next((t for t in tools if t.get("tool_id") == _TOOL_ID), None)
        checks.ok(lv is not None, f"{_TOOL_ID} registered in /tools",
                  f"category={lv.get('category') if lv else 'N/A'}")

        # 2) start the app (generous timeout; fingerprint should make prewarm fast,
        #    but torch/transformers import on first launch is slow)
        print(f"[lv-e2e] POST /tools/{_TOOL_ID}/start (up to 240s)…")
        t0 = time.time()
        status, body = _http("POST", f"{base}/tools/{_TOOL_ID}/start", timeout=240.0)
        dt = round(time.time() - t0, 1)
        started = status == 200
        checks.ok(started, f"POST /tools/{_TOOL_ID}/start -> 200", f"{dt}s status={status}")
        if not started:
            print(f"         body: {body[:500]}")
            return _finish(checks, proc, engine_log)

        resp = json.loads(body)
        tool_url = resp.get("input_url", "")
        checks.ok(resp.get("category") == "app", "response category == app",
                  str(resp.get("category")))
        checks.ok(bool(tool_url) and resp.get("input_url") == resp.get("output_url"),
                  "single URL (input_url == output_url)", tool_url)
        checks.ok(bool(resp.get("run_id")), "run_id present", str(resp.get("run_id")))

        # 3) live Streamlit health
        health_ok = False
        for _ in range(20):
            try:
                s, b = _http("GET", f"{tool_url}/_stcore/health", timeout=5.0)
                if s == 200 and "ok" in b.lower():
                    health_ok = True
                    break
            except (urllib.error.URLError, ConnectionError, socket.timeout, OSError):
                pass
            time.sleep(1.0)
        checks.ok(health_ok, "LV Streamlit /_stcore/health == ok")

        # 4a) the raw shell IS served (200) — sanity that the port is HTTP-live
        s, _ = _http("GET", f"{tool_url}/", timeout=8.0)
        checks.ok(s == 200, "LV serves its HTTP shell (GET / -> 200)", f"status={s}")

        # 4b) LV's whole app.py import graph resolves in the runtime-equivalent env
        graph_ok, detail = _verify_lv_import_graph()
        checks.ok(graph_ok, "LV app.py full import graph loads (base + per-tool venv)", detail)

        # 6) stop
        s, _ = _http("POST", f"{base}/tools/stop", timeout=30.0)
        checks.ok(s == 200, "POST /tools/stop -> 200", f"status={s}")

    finally:
        pass

    return _finish(checks, proc, engine_log)


def _finish(checks: "_Checks", proc: subprocess.Popen, engine_log: Path) -> int:
    # 5) engine log sanity
    log_text = ""
    if engine_log.exists():
        log_text = engine_log.read_text(encoding="utf-8", errors="replace")
    bad = [m for m in ("Traceback (most recent call last)", "did not become ready")
           if m in log_text]
    checks.ok(not bad, "engine.log has no Traceback / readiness failure",
              ("found: " + ", ".join(bad)) if bad else "clean")

    # graceful shutdown
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    print()
    if checks.failures:
        print(f"[lv-e2e] RESULT: FAIL ({len(checks.failures)} check(s)): "
              + ", ".join(checks.failures))
        if log_text:
            tail = "\n".join(log_text.splitlines()[-25:])
            print("---- engine.log (tail) ----")
            print(tail)
        return 1
    print("[lv-e2e] RESULT: PASS — LV launches and serves its UI end-to-end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
