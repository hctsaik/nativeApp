import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const __dirname = path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Z]:)/, "$1");
const require = createRequire(import.meta.url);
const APP_ROOT = path.resolve(__dirname, "..");
const PACKAGE_JSON = JSON.parse(fs.readFileSync(path.join(APP_ROOT, "package.json"), "utf8"));

// ---------------------------------------------------------------------------
// Root Cause Documentation
//
// When Claude Code CLI (or any tool that uses the Electron binary as Node.js)
// sets ELECTRON_RUN_AS_NODE=1, Electron ignores its normal browser-process
// initialisation and behaves as a plain Node.js process.  In that mode,
// `require('electron')` resolves to the npm package's index.js, which returns
// the PATH to the electron binary as a string instead of the API object.
// That causes `const { ipcMain } = require('electron')` to yield undefined,
// crashing main.js at module load time.
// ---------------------------------------------------------------------------

describe("ELECTRON_RUN_AS_NODE symptom", () => {
  it("require('electron') returns a string path when running outside Electron runtime", () => {
    // This test itself runs under plain Node.js (vitest), which simulates
    // what happens when ELECTRON_RUN_AS_NODE=1 is set and the Electron
    // binary runs as Node.  Asserting this documents the symptom.
    const electronValue = require("electron");
    expect(typeof electronValue).toBe("string");
    expect(electronValue).toMatch(/electron(\.exe)?$/i);
  });

  it("the string returned by require('electron') is not an object with ipcMain", () => {
    const electronValue = require("electron");
    expect(electronValue).not.toHaveProperty("ipcMain");
    expect(electronValue).not.toHaveProperty("app");
    expect(electronValue).not.toHaveProperty("BrowserWindow");
  });
});

// ---------------------------------------------------------------------------
// Fix: launch-electron.js
// ---------------------------------------------------------------------------

describe("launch-electron.js", () => {
  const launcherPath = path.join(APP_ROOT, "launch-electron.js");
  const launcherSource = fs.readFileSync(launcherPath, "utf8");

  it("exists at the app root", () => {
    expect(fs.existsSync(launcherPath)).toBe(true);
  });

  it("requires the 'electron' package to resolve the binary path", () => {
    expect(launcherSource).toMatch(/require\(['"]electron['"]\)/);
  });

  it("deletes ELECTRON_RUN_AS_NODE from the child environment", () => {
    expect(launcherSource).toContain("delete env.ELECTRON_RUN_AS_NODE");
  });

  it("passes the cleaned env to the spawned Electron process", () => {
    expect(launcherSource).toContain("env,");
  });

  it("env cloning + deletion leaves ELECTRON_RUN_AS_NODE undefined", () => {
    const fakeParentEnv = { ...process.env, ELECTRON_RUN_AS_NODE: "1", OTHER: "keep" };
    const childEnv = Object.assign({}, fakeParentEnv);
    delete childEnv.ELECTRON_RUN_AS_NODE;

    expect(childEnv.ELECTRON_RUN_AS_NODE).toBeUndefined();
    expect(childEnv.OTHER).toBe("keep");
  });
});

// ---------------------------------------------------------------------------
// Fix: dev script wiring
// ---------------------------------------------------------------------------

describe("package.json dev script", () => {
  const devScript = PACKAGE_JSON.scripts.dev;
  const devWaitPath = path.join(APP_ROOT, "dev-wait-portal.js");
  const devWaitSource = fs.readFileSync(devWaitPath, "utf8");

  it("is defined", () => {
    expect(typeof devScript).toBe("string");
  });

  it("runs the portal dev server and then the Electron wait launcher", () => {
    expect(devScript).toContain("npm --prefix ../portal-react run dev");
    expect(devScript).toContain("node dev-wait-portal.js");
  });

  it("does not call 'electron .' directly (which would inherit ELECTRON_RUN_AS_NODE)", () => {
    // 'electron .' without the launcher would inherit the env var from the
    // parent process and cause the ipcMain-undefined crash.
    expect(devScript).not.toMatch(/(?<![a-zA-Z])electron \./);
  });

  it("uses the portal URL file instead of a hardcoded Vite port", () => {
    expect(devWaitSource).toContain(".portal-url");
    expect(devWaitSource).toContain("process.env.PORTAL_DEV_URL = portalUrl");
  });

  it("launches Electron only after Vite has written its URL", () => {
    expect(devWaitSource).toContain('require("./launch-electron.js")');
    expect(devWaitSource).toContain("fs.existsSync(URL_FILE)");
  });
});

describe("LabelMe_Dino external launcher wiring", () => {
  const mainPath = path.join(APP_ROOT, "src", "main.js");
  const mainSource = fs.readFileSync(mainPath, "utf8");
  const buildResources = PACKAGE_JSON.build.extraResources;

  it("passes LABELME_DINO_EXE into the sidecar environment", () => {
    expect(mainSource).toContain("LABELME_DINO_EXE");
    expect(mainSource).toContain("labelMeDinoEnv()");
  });

  it("passes LABELME_DINO_RUNTIME in development", () => {
    expect(mainSource).toContain("LABELME_DINO_RUNTIME");
    expect(mainSource).toContain("LabelMe_Dino_launcher");
  });

  it("passes external annotator executable paths in development", () => {
    expect(mainSource).toContain("LABELME_EXE");
    expect(mainSource).toContain("XANYLABELING_EXE");
    expect(mainSource).toContain("CIM_REPO_ROOT");
  });

  it("packages the launcher as an extra resource outside asar", () => {
    expect(buildResources).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          from: "../../LabelMe_Dino/dist/LabelMe_Dino_launcher",
          to: "labelme-dino",
        }),
      ]),
    );
  });
});

describe("bundled standalone Python wiring (per-tool venv base in frozen)", () => {
  const mainPath = path.join(APP_ROOT, "src", "main.js");
  const mainSource = fs.readFileSync(mainPath, "utf8");
  const buildResources = PACKAGE_JSON.build.extraResources;

  it("injects CIM_PYTHON into the sidecar environment", () => {
    expect(mainSource).toContain("CIM_PYTHON");
    expect(mainSource).toContain("bundledPythonEnv()");
  });

  it("resolves the bundled python from resources/python/python.exe", () => {
    expect(mainSource).toContain("bundledPython()");
    expect(mainSource).toMatch(/resourcesPath,\s*["']python["']/);
  });

  it("lets an explicit CIM_PYTHON in the environment win", () => {
    expect(mainSource).toContain("if (process.env.CIM_PYTHON) return {}");
  });

  it("packages the standalone Python as an extra resource outside asar", () => {
    expect(buildResources).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ from: "python-runtime/python", to: "python" }),
      ]),
    );
  });
});
