#!/usr/bin/env node
const { spawn } = require("child_process");

const electronPath = process.env.CIM_ELECTRON_PATH || require("electron");
const env = Object.assign({}, process.env);
delete env.ELECTRON_RUN_AS_NODE;

const debugArgs = process.env.ELECTRON_DEBUG ? ["--remote-debugging-port=9222"] : [];

let child;
try {
  child = spawn(electronPath, [...debugArgs, "."], {
    cwd: __dirname,
    env,
    stdio: "inherit"
  });
} catch (error) {
  console.error(`[launch-electron] Failed to start Electron: ${error.message}`);
  console.error(`[launch-electron] Electron path: ${electronPath}`);
  console.error(
    "[launch-electron] On Windows, `spawn UNKNOWN` often means App Control, " +
    "antivirus, or an allow-list policy blocked electron.exe. Try running the " +
    "path above with `--version`, or set CIM_ELECTRON_PATH to an approved Electron binary."
  );
  process.exit(1);
}

child.on("error", (error) => {
  console.error(`[launch-electron] Electron process error: ${error.message}`);
  console.error(`[launch-electron] Electron path: ${electronPath}`);
  process.exit(1);
});

child.on("close", (code) => process.exit(code ?? 0));
