import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";

const PORTAL_URL_FILE = path.resolve(
  path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")),
  "../host-electron/.portal-url"
);
const REPO_ROOT = path.resolve(
  path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")),
  "../.."
);

export default defineConfig({
  resolve: {
    alias: {
      "@cim/shared-protocol": path.join(REPO_ROOT, "packages/shared-protocol/src/index.js"),
    },
  },
  plugins: [
    react(),
    {
      name: "write-portal-url",
      configureServer(server) {
        server.httpServer?.once("listening", () => {
          const addr = server.httpServer.address();
          const url = `http://127.0.0.1:${addr.port}`;
          fs.writeFileSync(PORTAL_URL_FILE, url, "utf8");
        });
      },
    },
  ],
  server: {
    host: "127.0.0.1",
    // No fixed port — OS picks any free port, plugin writes actual URL to .portal-url
  },
});
