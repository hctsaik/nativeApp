const { app, BrowserWindow, dialog, ipcMain } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const net = require("net");
const path = require("path");

const APP_NAME = "CIM Hybrid Edge Platform";
const MOCK_JWT = "mock.jwt.token";
const DEV_LOG_PORT = 19222;

let mainWindow;
let sidecarProcess;
let sidecarControlPort;
let logDir;
let isStoppingSidecar = false;
let recentEvents = [];

function rootDir() {
  return path.resolve(__dirname, "../../..");
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function resolveLogDir() {
  if (app.isPackaged) {
    return path.join(path.dirname(process.execPath), "logs");
  }
  return path.join(rootDir(), "apps", "host-electron", "logs");
}

function purgeStaleLogs(logFile, retainDays = 3) {
  if (!fs.existsSync(logFile)) return;
  const cutoff = Date.now() - retainDays * 24 * 60 * 60 * 1000;
  const lines = fs.readFileSync(logFile, "utf8").split("\n").filter(Boolean);
  const kept = lines.filter((line) => {
    const match = line.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
    if (!match) return true;
    return new Date(match[1]).getTime() >= cutoff;
  });
  fs.writeFileSync(logFile, kept.join("\n") + (kept.length ? "\n" : ""), "utf8");
}

function appendLog(message) {
  const line = `${new Date().toISOString()} ${message}\n`;
  ensureDir(logDir);
  const logFile = path.join(logDir, "host.log");
  fs.appendFileSync(logFile, line, "utf8");
  recentEvents.push(line.trimEnd());
  if (recentEvents.length > 200) recentEvents.shift();
}

function startDevLogServer() {
  if (app.isPackaged) return;
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://localhost`);
    if (url.pathname === "/dev/log") {
      const n = parseInt(url.searchParams.get("n") ?? "50");
      const lines = recentEvents.slice(-Math.min(n, 200));
      res.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
      res.end(lines.join("\n") + "\n");
    } else if (url.pathname === "/dev/status") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ logDir, sidecarControlPort, CIM_DEV_MODE: process.env.CIM_DEV_MODE ?? "(not set)", devMode: (process.env.CIM_DEV_MODE ?? "").trim() !== "0", recentEvents: recentEvents.slice(-20) }));
    } else if (url.pathname === "/dev/tools") {
      if (!sidecarControlPort) {
        res.writeHead(503, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "sidecar not ready" }));
        return;
      }
      requestJson("GET", "/tools").then((tools) => {
        res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
        res.end(JSON.stringify(tools, null, 2));
      }).catch((err) => {
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: err.message }));
      });
    } else {
      res.writeHead(404);
      res.end("Not found");
    }
  });
  server.on("error", (err) => {
    if (err.code === "EADDRINUSE") {
      appendLog(`[dev-log-server] port ${DEV_LOG_PORT} already in use, skipping`);
    } else {
      appendLog(`[dev-log-server] error: ${err.message}`);
    }
  });
  server.listen(DEV_LOG_PORT, "127.0.0.1", () => {
    appendLog(`[dev-log-server] listening on http://127.0.0.1:${DEV_LOG_PORT}/dev/log`);
  });
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = address.port;
      server.close(() => resolve(port));
    });
  });
}

function requestJson(method, urlPath, body) {
  return new Promise((resolve, reject) => {
    const payload = body ? Buffer.from(JSON.stringify(body)) : null;
    const request = http.request(
      {
        hostname: "127.0.0.1",
        port: sidecarControlPort,
        path: urlPath,
        method,
        headers: payload
          ? {
              "Content-Type": "application/json",
              "Content-Length": payload.length
            }
          : undefined
      },
      (response) => {
        let data = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          data += chunk;
        });
        response.on("end", () => {
          if (response.statusCode < 200 || response.statusCode >= 300) {
            reject(new Error(`HTTP ${response.statusCode}: ${data}`));
            return;
          }
          resolve(data ? JSON.parse(data) : {});
        });
      }
    );
    request.on("error", reject);
    if (payload) {
      request.write(payload);
    }
    request.end();
  });
}

async function waitForSidecarReady(timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const health = await requestJson("GET", "/health");
      if (health.status === "ok") {
        return;
      }
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }
  throw new Error("Sidecar readiness timed out");
}

async function startSidecar() {
  sidecarControlPort = await findFreePort();
  logDir = resolveLogDir();
  ensureDir(logDir);
  purgeStaleLogs(path.join(logDir, "host.log"));

  const candidates = sidecarCandidates();
  let lastError;

  for (const candidate of candidates) {
    let candidateProcess;
    try {
      appendLog(`Starting sidecar: ${candidate.command} ${candidate.args.join(" ")}`);
      candidateProcess = spawnSidecar(candidate);
      attachSidecarLogging(candidateProcess);
      sidecarProcess = candidateProcess;
      await waitForCandidateReady(candidateProcess, app.isPackaged ? 90000 : 20000);
      appendLog(`Sidecar ready on port ${sidecarControlPort}`);
      return;
    } catch (error) {
      lastError = error;
      appendLog(`Sidecar start candidate failed: ${error.message}`);
      if (candidateProcess && !candidateProcess.killed) {
        candidateProcess.kill();
      }
      sidecarProcess = null;
    }
  }

  if (!sidecarProcess) {
    throw lastError ?? new Error("No sidecar start candidate succeeded");
  }
}

// Path to the standalone Python bundled with a packaged release (see
// scripts/win/fetch-standalone-python.ps1 + package.json extraResources).
// Used as the base interpreter for per-tool venvs: the frozen engine.exe has a
// read-only embedded Python and cannot `-m venv` itself, so a tool that declares
// `requires:` needs a real external Python. Bundling one means a clean factory
// machine needs no separately-installed Python. Returns null if not present
// (e.g. dev, or a build that skipped the fetch step).
function bundledPython() {
  if (!app.isPackaged) return null;
  const py = path.join(process.resourcesPath, "python", "python.exe");
  return fs.existsSync(py) ? py : null;
}

function sidecarCandidates() {
  if (app.isPackaged) {
    const engineExe = path.join(process.resourcesPath, "engine", "engine.exe");
    const sourceEngine = path.join(process.resourcesPath, "sidecar-source", "engine.py");
    return [
      {
        command: engineExe,
        args: ["--control-port", String(sidecarControlPort), "--log-dir", logDir],
        cwd: path.dirname(engineExe)
      },
      {
        // Source-engine fallback: prefer the bundled Python so it also works on
        // a machine without a system Python; then PYTHON env, then PATH.
        command: process.env.PYTHON ?? bundledPython() ?? "python",
        args: [sourceEngine, "--control-port", String(sidecarControlPort), "--log-dir", logDir],
        cwd: path.dirname(sourceEngine)
      }
    ];
  }

  const enginePath = path.join(rootDir(), "sidecar", "python-engine", "engine.py");
  return [
    {
      command: process.env.PYTHON ?? "python",
      args: [enginePath, "--control-port", String(sidecarControlPort), "--log-dir", logDir],
      cwd: path.dirname(enginePath)
    }
  ];
}

function labelMeDinoEnv() {
  const env = {};
  if (app.isPackaged) {
    env.LABELME_DINO_EXE = path.join(process.resourcesPath, "labelme-dino", "LabelMe_Dino.exe");
  } else {
    const repoRoot = rootDir();
    const dinoRoot = path.join(repoRoot, "LabelMe_Dino");
    env.LABELME_DINO_EXE = path.join(repoRoot, "external_exe", "LabelMe_Dino_launcher", "LabelMe_Dino.exe");
    env.LABELME_DINO_RUNTIME = path.join(dinoRoot, ".venv");
    env.LABELME_EXE = path.join(dinoRoot, ".venv", "Scripts", "labelme.exe");
    env.XANYLABELING_EXE = path.join(repoRoot, ".venv-xanylabeling", "Scripts", "xanylabeling.exe");
    env.ISAT_EXE = process.env.ISAT_EXE || "isat-sam";
    env.CIM_REPO_ROOT = repoRoot;
  }
  return env;
}

// Inject CIM_PYTHON for packaged builds so the frozen engine's per-tool
// dependency resolver (core/tool_deps.base_python) uses the bundled Python to
// build venvs. Skipped when no bundled Python is present (resolver then falls
// back to py -3.11 / python on PATH, as before). An explicit CIM_PYTHON in the
// environment always wins.
function bundledPythonEnv() {
  if (process.env.CIM_PYTHON) return {};
  const py = bundledPython();
  return py ? { CIM_PYTHON: py } : {};
}

function spawnSidecar(candidate) {
  return spawn(candidate.command, candidate.args, {
    cwd: candidate.cwd,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, ...labelMeDinoEnv(), ...bundledPythonEnv(), PYTHONUTF8: "1" },
    windowsHide: true
  });
}

function attachSidecarLogging(processHandle) {
  processHandle.stdout.on("data", (data) => appendLog(`[sidecar stdout] ${data.toString().trimEnd()}`));
  processHandle.stderr.on("data", (data) => appendLog(`[sidecar stderr] ${data.toString().trimEnd()}`));
  processHandle.on("exit", (code, signal) => {
    appendLog(`Sidecar exited code=${code} signal=${signal}`);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("sidecar-exited", { code, signal });
    }
    if (!isStoppingSidecar && mainWindow && !mainWindow.isDestroyed()) {
      appendLog("Sidecar crashed unexpectedly — auto-restarting in 3 s");
      mainWindow.webContents.send("sidecar-restarting", {});
      setTimeout(async () => {
        try {
          await startSidecar();
          appendLog("Sidecar auto-restarted successfully");
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send("sidecar-ready", {});
          }
        } catch (err) {
          appendLog(`Sidecar auto-restart failed: ${err.message}`);
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send("sidecar-restart-failed", { error: err.message });
          }
        }
      }, 3000);
    }
  });
}

function waitForCandidateReady(processHandle, timeoutMs) {
  return Promise.race([
    waitForSidecarReady(timeoutMs),
    new Promise((_, reject) => {
      processHandle.once("error", (error) => reject(error));
      processHandle.once("exit", (code, signal) => {
        reject(new Error(`Sidecar exited before readiness code=${code} signal=${signal}`));
      });
    })
  ]);
}

async function stopSidecar() {
  if (!sidecarProcess || isStoppingSidecar) {
    return;
  }

  isStoppingSidecar = true;
  appendLog("Stopping sidecar");
  try {
    try {
      await Promise.race([
        requestJson("POST", "/shutdown"),
        new Promise((_, reject) => setTimeout(() => reject(new Error("Shutdown timeout")), 5000))
      ]);
    } catch (error) {
      appendLog(`Graceful shutdown failed: ${error.message}`);
    }

    if (!sidecarProcess.killed) {
      await new Promise((resolve) => {
        const timer = setTimeout(() => {
          appendLog("Forcing sidecar kill");
          sidecarProcess.kill();
          resolve();
        }, 5000);
        sidecarProcess.once("exit", () => {
          clearTimeout(timer);
          resolve();
        });
      });
    }
  } finally {
    sidecarProcess = null;
    isStoppingSidecar = false;
  }
}

function portalUrl() {
  if (!app.isPackaged) {
    return process.env.PORTAL_DEV_URL || "http://127.0.0.1:5173";
  }
  return `file://${path.join(process.resourcesPath, "portal", "index.html")}`;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    title: APP_NAME,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.maximize();
    mainWindow.show();
  });
  await mainWindow.loadURL(portalUrl());
}

ipcMain.on("renderer-log", (_event, level, message) => {
  appendLog(`[renderer:${level}] ${message}`);
});

ipcMain.handle("get-app-config", async () => {
  return {
    sidecarControlUrl: `http://127.0.0.1:${sidecarControlPort}`,
    mockJwt: MOCK_JWT,
    enterpriseAppUrl: "",
    allowedOrigins: ["*"],
    logDir,
    devMode: (process.env.CIM_DEV_MODE ?? "").trim() !== "0",
  };
});

ipcMain.handle("start-tool", async (_event, toolId) => {
  return requestJson("POST", `/tools/${encodeURIComponent(toolId)}/start`);
});

ipcMain.handle("start-sheet-tab", async (_event, pluginId) => {
  return requestJson("POST", `/tools/active/sheet-tab/${encodeURIComponent(pluginId)}/start`);
});

ipcMain.handle("list-tools", async () => {
  return requestJson("GET", "/tools");
});

ipcMain.handle("stop-tool", async () => {
  return requestJson("POST", "/tools/stop");
});

ipcMain.handle("get-tool-status", async () => {
  return requestJson("GET", "/tools/active/status");
});

ipcMain.handle("get-runtime-status", async () => {
  return requestJson("GET", "/runtime");
});

ipcMain.handle("get-diagnostics", async () => {
  return requestJson("GET", "/diagnostics");
});

ipcMain.handle("external-open-xanylabeling", async (_event, imageUrl, metadata) => {
  return requestJson("POST", "/external/open-xanylabeling", { image_url: imageUrl, metadata: metadata ?? {} });
});

ipcMain.handle("external-open-labeling-tool", async (_event, tool, imageUrl, metadata) => {
  return requestJson("POST", "/external/open-labeling-tool", { tool: tool ?? "x-anylabeling", image_url: imageUrl, metadata: metadata ?? {} });
});

ipcMain.handle("external-queue-image", async (_event, imageUrl, metadata) => {
  return requestJson("POST", "/external/queue-image", { image_url: imageUrl, metadata: metadata ?? {} });
});

ipcMain.handle("external-get-queue", async () => {
  return requestJson("GET", "/external/queue");
});

ipcMain.handle("external-dequeue", async (_event, itemId) => {
  return requestJson("DELETE", `/external/queue/${encodeURIComponent(itemId)}`);
});

ipcMain.handle("restart-sidecar", async () => {
  appendLog("Manual sidecar restart requested");
  if (sidecarProcess && !sidecarProcess.killed) {
    await stopSidecar();
  }
  await startSidecar();
  return {};
});

ipcMain.handle("choose-file", async (_event, options) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: options?.properties ?? ["openFile"]
  });
  if (!result.canceled) {
    await requestJson("POST", "/selected-paths", { paths: result.filePaths });
  }
  return {
    canceled: result.canceled,
    paths: result.filePaths
  };
});

app.whenReady().then(async () => {
  logDir = resolveLogDir();
  startDevLogServer();
  try {
    await startSidecar();
    await createWindow();
  } catch (error) {
    appendLog(`Startup failed: ${error.stack || error.message}`);
    dialog.showErrorBox(APP_NAME, `Startup failed: ${error.message}`);
    app.quit();
  }
});

app.on("before-quit", async (event) => {
  if (sidecarProcess) {
    event.preventDefault();
    await stopSidecar();
    app.quit();
  }
});

app.on("window-all-closed", () => {
  app.quit();
});
