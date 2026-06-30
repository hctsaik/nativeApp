// E2E 核心:啟動一個「隔離」的 Tauri 實例(獨立 WebView2 user-data + CDP port + log dir +
// engine),用 Playwright 經 CDP 驅動 portal 起指定工具,判斷是否真算繪 Streamlit,最後拆除。
// 供 run-tool.mjs(單工具)與 run-all.mjs(全套)共用。
import { chromium } from "playwright-core";
import { spawn, execSync } from "node:child_process";
import { readFileSync, existsSync, mkdirSync } from "node:fs";
import { join, isAbsolute, resolve } from "node:path";

// portal 選單可見、可獨立 Start 的工具(category app/sheet/management)。
// 要重新確認清單:啟動 app 後在 DevTools 跑 `[...document.querySelector('.toolSelect').options].map(o=>o.value)`。
export const MENU_TOOLS = [
  "sheet-edge-analysis",
  "management-center",
  "sheet-annotation",
  "app-ai4bi",
  "app-lv",
];

export const DEFAULTS = {
  exe: "C:\\code\\claude\\nativeApp_Light\\5_PG_Develop\\src-tauri\\target\\debug\\cim-light.exe",
  repo: "C:\\code\\claude\\nativeApp",
  python: "C:\\Users\\hctsa\\AppData\\Local\\Python\\pythoncore-3.11-64\\python.exe",
  enginePy: "C:\\code\\claude\\nativeApp\\sidecar\\python-engine\\engine.py",
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * 測一個工具。回傳 result 物件(含 verdict / attribution / 證據)。
 *   verdict: RENDERED | NOT_FOUND | NO_IFRAME | PORTAL_NOT_READY | TOOL_NOT_IN_MENU | ENGINE_NOT_READY | DRIVER_ERROR
 *   attribution: PASS | ENV_BLOCKED | INCONCLUSIVE | INFRA
 */
export async function testTool(toolId, cdpPort, workDir, opts = {}) {
  const cfg = { ...DEFAULTS, ...opts };
  const wd = isAbsolute(workDir) ? workDir : resolve(process.cwd(), workDir);
  mkdirSync(wd, { recursive: true });
  const logFile = join(wd, "logs", "host.log");
  const result = {
    toolId, cdpPort: String(cdpPort), enginePort: null, verdict: "UNKNOWN",
    attribution: "INFRA", frames: [], consoleErrorCount: 0, health: null,
    rootStatus: null, durationMs: null, evidence: "", rootCause: "", error: null,
  };
  const t0 = Date.now();

  const env = {
    ...process.env,
    CIM_ENGINE_EXE: cfg.enginePy,
    CIM_ENGINE_PYTHON: cfg.python,
    PYTHONUTF8: "1",
    CIM_REPO_ROOT: cfg.repo,
    XANYLABELING_EXE: join(cfg.repo, ".venv-xanylabeling", "Scripts", "xanylabeling.exe"),
    ISAT_EXE: "isat-sam",
    WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${cdpPort}`,
    WEBVIEW2_USER_DATA_FOLDER: join(wd, "wv2"), // 多實例隔離必需,否則共用同一 WebView2 程序
  };
  const child = spawn(cfg.exe, [], { cwd: wd, env, stdio: "ignore" });

  async function getReadyPage(timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    let browser = null;
    while (Date.now() < deadline) {
      try {
        if (!browser) browser = await chromium.connectOverCDP(`http://127.0.0.1:${cdpPort}`);
        const ctx = browser.contexts()[0];
        const page = ctx && ctx.pages().find((p) => p.url().includes("tauri.localhost"));
        if (page) {
          const ok = await page
            .waitForFunction(() => { const s = document.querySelector(".toolSelect"); return s && s.options.length > 0; }, { timeout: 6000 })
            .then(() => true).catch(() => false);
          if (ok) return { browser, page };
        }
      } catch { /* 重試 */ }
      await sleep(1500);
    }
    return { browser, page: null };
  }

  // 1) 等 engine ready
  const startWait = Date.now();
  while (Date.now() - startWait < 75000) {
    await sleep(1000);
    if (child.exitCode !== null) { result.error = `app exited early code=${child.exitCode}`; break; }
    if (existsSync(logFile)) {
      const m = readFileSync(logFile, "utf8").match(/Sidecar ready on port (\d+)/g);
      if (m) { result.enginePort = m[m.length - 1].match(/(\d+)/)[1]; break; }
    }
  }

  if (!result.enginePort) {
    result.verdict = "ENGINE_NOT_READY";
    result.attribution = "INFRA";
    result.rootCause = result.error || "engine 75s 內未就緒";
  } else {
    let browser = null;
    try {
      const got = await getReadyPage(40000);
      browser = got.browser;
      const page = got.page;
      if (!page) {
        result.verdict = "PORTAL_NOT_READY";
        result.attribution = "INCONCLUSIVE";
      } else {
        const consoleErrors = [];
        page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 200)); });
        page.on("pageerror", (e) => consoleErrors.push("pageerror:" + e.message.slice(0, 200)));

        const optsList = await page.$$eval(".toolSelect option", (els) => els.map((e) => e.value).filter(Boolean));
        if (!optsList.includes(toolId)) {
          result.verdict = "TOOL_NOT_IN_MENU";
          result.attribution = "INFRA";
          result.rootCause = "options=" + JSON.stringify(optsList);
        } else {
          await page.selectOption(".toolSelect", toolId);
          await page.click('button:has-text("Start")');
          await page.waitForTimeout(opts.toolWaitMs ?? 26000);

          const frames = page.frames().filter((f) => f.url().startsWith("http://127.0.0.1"));
          let verdict = "NO_IFRAME";
          for (const f of frames) {
            const body = await f.locator("body").innerText({ timeout: 3000 }).catch(() => "");
            const stApp = await f.locator('[data-testid="stApp"]').count().catch(() => 0);
            const nf = body.includes("Not Found") || body.trim().startsWith("404");
            result.frames.push({ url: f.url(), stApp, notFound: nf, bodyLen: body.length, sample: body.slice(0, 120).replace(/\s+/g, " ") });
            if (stApp > 0 && !nf) verdict = "RENDERED";
            else if (nf && verdict !== "RENDERED") verdict = "NOT_FOUND";
          }
          if (frames[0]) {
            const u = new URL(frames[0].url());
            try { result.health = (await fetch(`http://127.0.0.1:${u.port}/_stcore/health`)).status; } catch {}
            try { result.rootStatus = (await fetch(`http://127.0.0.1:${u.port}/`)).status; } catch {}
            result.evidence = result.frames[0].sample;
          }
          result.verdict = verdict;
          // 歸因
          if (verdict === "RENDERED") result.attribution = "PASS";
          else if (verdict === "NOT_FOUND" && result.health === 200) { result.attribution = "ENV_BLOCKED"; result.rootCause = "Streamlit 核心起(health 200)但工具頁缺失 → engine/外掛打包或依賴,非 Tauri"; }
          else result.attribution = "INCONCLUSIVE";
        }
        result.consoleErrorCount = consoleErrors.length;
        result.consoleErrors = consoleErrors.slice(0, 8);
      }
      if (browser) await browser.close();
    } catch (e) {
      result.verdict = "DRIVER_ERROR";
      result.attribution = "INFRA";
      result.error = String(e && e.message ? e.message : e).slice(0, 300);
    }
  }

  // 2) 拆除:整棵程序樹(cim-light → engine.py → streamlit×N)硬殺,避免 auto-restart 換 port 的孤兒
  try { execSync(`taskkill /PID ${child.pid} /T /F`, { stdio: "ignore" }); } catch {}
  try { child.kill(); } catch {}

  result.durationMs = Date.now() - t0;
  return result;
}
