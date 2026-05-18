#!/usr/bin/env node
const { spawn } = require("child_process");
const path = require("path");

const electronPath = require("electron");
const env = Object.assign({}, process.env);
delete env.ELECTRON_RUN_AS_NODE;

const debugArgs = process.env.ELECTRON_DEBUG ? ["--remote-debugging-port=9222"] : [];

const child = spawn(electronPath, [...debugArgs, "."], {
  cwd: __dirname,
  env,
  stdio: "inherit"
});

child.on("close", (code) => process.exit(code ?? 0));
