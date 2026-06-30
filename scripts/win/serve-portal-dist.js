#!/usr/bin/env node
/**
 * Static file server for the PRE-BUILT CIM portal (apps/portal-react/dist).
 *
 * WHY: On WDAC-enforced machines the unsigned esbuild.exe that Vite spawns is
 * blocked ("An Application Control policy has blocked this file"), so the normal
 * `npm run dev` (vite dev server) cannot start, and Electron never launches.
 * This serves the already-built dist instead so the dev Electron can load it via
 * PORTAL_DEV_URL, bypassing vite/esbuild entirely. See start-dev-nowdac.bat and
 * docs note on the WDAC/esbuild block.
 *
 * Caveat: serves a pre-built bundle (no HMR; portal source changes are NOT
 * reflected until rebuilt on a machine where esbuild is allowed). The engine and
 * all backend logic still run from current source.
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

// scripts/win -> repo root is two levels up.
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const DIST = path.join(REPO_ROOT, "apps", "portal-react", "dist");
const PORT = Number(process.env.STATIC_PORT || 5173);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".map": "application/json; charset=utf-8",
};

if (!fs.existsSync(path.join(DIST, "index.html"))) {
  console.error(`[static-portal] No pre-built portal at ${DIST}`);
  console.error("[static-portal] Build it on a machine where esbuild is allowed:");
  console.error("[static-portal]   npm --prefix apps/portal-react run build");
  process.exit(1);
}

const server = http.createServer((req, res) => {
  let urlPath = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
  if (urlPath === "/" || urlPath === "") urlPath = "/index.html";
  const filePath = path.join(DIST, urlPath);
  if (!filePath.startsWith(DIST)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }
  fs.readFile(filePath, (err, data) => {
    if (err) {
      // SPA fallback: serve index.html for unknown non-asset routes.
      if (!path.extname(urlPath)) {
        fs.readFile(path.join(DIST, "index.html"), (e2, idx) => {
          if (e2) { res.writeHead(404); res.end("Not found"); return; }
          res.writeHead(200, { "Content-Type": MIME[".html"] });
          res.end(idx);
        });
        return;
      }
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
    res.end(data);
  });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`[static-portal] serving ${DIST}`);
  console.log(`[static-portal] http://127.0.0.1:${PORT}  (Ctrl+C to stop)`);
});
server.on("error", (e) => {
  if (e.code === "EADDRINUSE") {
    console.error(`[static-portal] port ${PORT} already in use`);
  } else {
    console.error(`[static-portal] error: ${e.message}`);
  }
  process.exit(1);
});
