// RWD 擷取:啟動 cim-light 隔離實例 → 連 CDP → 選工具按 Start → 等渲染 →
// 對多個視窗尺寸截圖 + 量版面指標(水平溢出/浪費空間/關鍵面板尺寸)。
// 用法: node e2e/rwd-capture.mjs <toolId=sheet-annotation> <cdpPort=9340> <outDir=e2e/rwd-runs/<tool>>
import { chromium } from "playwright-core";
import { spawn, execSync } from "node:child_process";
import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { DEFAULTS } from "./lib.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const TOOL = process.argv[2] || "sheet-annotation";
const PORT = parseInt(process.argv[3] || "9340", 10);
const OUT = resolve(process.argv[4] || `e2e/rwd-runs/${TOOL}`);
mkdirSync(join(OUT, "logs"), { recursive: true });

// RWD 斷點(寬×高)。涵蓋超寬桌機→小筆電,逼出版面在各尺寸的表現。
const VIEWPORTS = [
  { w: 2560, h: 1440, tag: "2560x1440-ultrawide" },
  { w: 1920, h: 1080, tag: "1920x1080-fhd" },
  { w: 1600, h: 900, tag: "1600x900" },
  { w: 1366, h: 768, tag: "1366x768-laptop" },
  { w: 1280, h: 720, tag: "1280x720" },
  { w: 1024, h: 768, tag: "1024x768-small" },
];

const env = {
  ...process.env,
  CIM_ENGINE_EXE: DEFAULTS.enginePy,
  CIM_ENGINE_PYTHON: DEFAULTS.python,
  PYTHONUTF8: "1",
  CIM_REPO_ROOT: DEFAULTS.repo,
  XANYLABELING_EXE: join(DEFAULTS.repo, ".venv-xanylabeling", "Scripts", "xanylabeling.exe"),
  ISAT_EXE: "isat-sam",
  WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${PORT}`,
  WEBVIEW2_USER_DATA_FOLDER: join(OUT, "wv2"),
};

const out = { tool: TOOL, port: PORT, outDir: OUT, enginePort: null, rendered: false, shots: [], error: null };
const child = spawn(DEFAULTS.exe, [], { cwd: OUT, env, stdio: "ignore" });
const logFile = join(OUT, "logs", "host.log");

function metricsInFrame() {
  // 在 Streamlit frame 內量版面。回傳水平溢出、主內容用寬、關鍵面板與圖片尺寸。
  const de = document.documentElement;
  const vw = window.innerWidth, vh = window.innerHeight;
  const rect = (sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; };
  const cols = [...document.querySelectorAll('[data-testid="stColumn"],[data-testid="column"]')].map((e) => { const r = e.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) }; });
  const imgs = [...document.querySelectorAll('img')].map((e) => { const r = e.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), natural: e.naturalWidth + "x" + e.naturalHeight }; }).filter((m) => m.w > 60);
  const block = document.querySelector('[data-testid="stMainBlockContainer"],[data-testid="block-container"],.main .block-container');
  const blockRect = block ? block.getBoundingClientRect() : null;
  return {
    vw, vh,
    scrollW: de.scrollWidth, clientW: de.clientWidth,
    horizontalOverflowPx: Math.max(0, de.scrollWidth - de.clientWidth),
    mainBlock: blockRect ? { w: Math.round(blockRect.width), leftGap: Math.round(blockRect.x), rightGap: Math.round(vw - (blockRect.x + blockRect.width)) } : null,
    mainBlockWidthPct: blockRect ? Math.round((blockRect.width / vw) * 100) : null,
    columns: cols.slice(0, 8),
    biggestImage: imgs.sort((a, b) => b.w * b.h - a.w * a.h)[0] || null,
    nImages: imgs.length,
    horizontalScrollbar: de.scrollWidth > de.clientWidth + 2,
  };
}

(async () => {
  try {
    // 1) 等 engine ready
    const t0 = Date.now();
    while (Date.now() - t0 < 80000) {
      await sleep(1000);
      if (child.exitCode !== null) throw new Error(`app exited early code=${child.exitCode}`);
      if (existsSync(logFile)) {
        const m = readFileSync(logFile, "utf8").match(/Sidecar ready on port (\d+)/g);
        if (m) { out.enginePort = m[m.length - 1].match(/(\d+)/)[1]; break; }
      }
    }
    if (!out.enginePort) throw new Error("engine 80s 未就緒");

    // 2) 連 CDP、等 portal
    let browser = null, page = null;
    const dl = Date.now() + 45000;
    while (Date.now() < dl && !page) {
      try {
        if (!browser) browser = await chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
        const ctx = browser.contexts()[0];
        const p = ctx && ctx.pages().find((x) => x.url().includes("tauri.localhost"));
        if (p) {
          const ok = await p.waitForFunction(() => { const s = document.querySelector(".toolSelect"); return s && s.options.length > 0; }, { timeout: 6000 }).then(() => true).catch(() => false);
          if (ok) page = p;
        }
      } catch {}
      if (!page) await sleep(1500);
    }
    if (!page) throw new Error("portal 未就緒(toolSelect 空)");

    // 3) 選工具 + Start + 等渲染
    await page.selectOption(".toolSelect", TOOL);
    await page.click('button:has-text("Start")');
    await page.waitForTimeout(26000);

    const frame = page.frames().find((f) => f.url().startsWith("http://127.0.0.1"));
    if (frame) {
      const stApp = await frame.locator('[data-testid="stApp"]').count().catch(() => 0);
      out.rendered = stApp > 0;
    }

    // 4) 多視窗尺寸:resize → 截圖 + 量版面
    for (const v of VIEWPORTS) {
      await page.setViewportSize({ width: v.w, height: v.h });
      await page.waitForTimeout(2500); // 等 Streamlit reflow
      const png = join(OUT, `${v.tag}.png`);
      await page.screenshot({ path: png });
      let metrics = null;
      try { const f = page.frames().find((f) => f.url().startsWith("http://127.0.0.1")); if (f) metrics = await f.evaluate(metricsInFrame); } catch (e) { metrics = { evalError: String(e).slice(0, 120) }; }
      out.shots.push({ tag: v.tag, w: v.w, h: v.h, png, metrics });
    }
    if (browser) await browser.close();
  } catch (e) {
    out.error = String(e && e.message ? e.message : e).slice(0, 300);
  } finally {
    try { execSync(`taskkill /PID ${child.pid} /T /F`, { stdio: "ignore" }); } catch {}
    try { child.kill(); } catch {}
  }
  writeFileSync(join(OUT, "rwd.json"), JSON.stringify(out, null, 2));
  console.log("RESULT_JSON " + JSON.stringify(out));
})();
