#!/usr/bin/env node
/**
 * Waits for Vite to write .portal-url, then launches Electron with that URL.
 * Replaces the hardcoded `wait-on http://127.0.0.1:5173` approach so that
 * Vite can use any free port without coordination issues.
 */
const fs = require("fs");
const path = require("path");

const URL_FILE = path.join(__dirname, ".portal-url");
const TIMEOUT_MS = 60_000;
const POLL_MS = 200;

const startedAt = Date.now();

function poll() {
  if (fs.existsSync(URL_FILE)) {
    const stat = fs.statSync(URL_FILE);
    // Accept the file only if it was written after this script started
    // (avoids picking up a stale file from a previous run)
    if (stat.mtimeMs >= startedAt - 2000) {
      const portalUrl = fs.readFileSync(URL_FILE, "utf8").trim();
      console.log(`[dev-wait-portal] Portal ready at ${portalUrl}`);
      process.env.PORTAL_DEV_URL = portalUrl;
      require("./launch-electron.js");
      return;
    }
  }
  if (Date.now() - startedAt > TIMEOUT_MS) {
    console.error("[dev-wait-portal] Timed out waiting for Vite to start");
    process.exit(1);
  }
  setTimeout(poll, POLL_MS);
}

poll();
