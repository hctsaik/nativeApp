// RWD 驗證:啟動 cim-light → 選 sheet-annotation → 在 data-source 填合成資料集路徑 →
// 執行 → 切到「標注工作台」→ 在工作台多尺寸截圖,驗證明細圖變大、不再切半 letterbox。
// 每個關鍵步驟都截圖(即使某步失敗也能看到當下畫面)。
import { chromium } from "playwright-core";
import { spawn, execSync } from "node:child_process";
import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { DEFAULTS } from "./lib.mjs";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PORT = 9341;
const OUT = "C:/code/claude/nativeApp_Light/5_PG_Develop/e2e/rwd-runs/verify";
const DATASET = "C:/Users/hctsa/AppData/Local/Temp/claude/c--code-claude-ANnoTation/2cf17a44-588f-4368-85b8-def384571ca3/scratchpad/realset";
mkdirSync(join(OUT, "logs"), { recursive: true });

const env = {
  ...process.env,
  CIM_ENGINE_EXE: DEFAULTS.enginePy, CIM_ENGINE_PYTHON: DEFAULTS.python,
  PYTHONUTF8: "1", CIM_REPO_ROOT: DEFAULTS.repo,
  XANYLABELING_EXE: join(DEFAULTS.repo, ".venv-xanylabeling", "Scripts", "xanylabeling.exe"),
  ISAT_EXE: "isat-sam",
  WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS: `--remote-debugging-port=${PORT}`,
  WEBVIEW2_USER_DATA_FOLDER: join(OUT, "wv2"),
};
const out = { steps: [], shots: [], error: null };
const log = (m) => { out.steps.push(m); console.log("STEP", m); };
const child = spawn(DEFAULTS.exe, [], { cwd: OUT, env, stdio: "ignore" });
const logFile = join(OUT, "logs", "host.log");
const stFrame = (page) => page.frames().find((f) => f.url().startsWith("http://127.0.0.1"));
async function frameWith(page, text) {
  for (const fr of page.frames()) {
    if (!fr.url().startsWith("http://127.0.0.1")) continue;
    if (await fr.locator(`text=${text}`).first().count().catch(() => 0)) return fr;
  }
  return null;
}

(async () => {
  try {
    let t0 = Date.now();
    while (Date.now() - t0 < 80000) {
      await sleep(1000);
      if (child.exitCode !== null) throw new Error(`app exited code=${child.exitCode}`);
      if (existsSync(logFile)) { const m = readFileSync(logFile, "utf8").match(/Sidecar ready on port (\d+)/g); if (m) { log("engine ready " + m[m.length - 1]); break; } }
    }
    let browser = null, page = null;
    const dl = Date.now() + 45000;
    while (Date.now() < dl && !page) {
      try { if (!browser) browser = await chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
        const p = browser.contexts()[0]?.pages().find((x) => x.url().includes("tauri.localhost"));
        if (p && await p.waitForFunction(() => document.querySelector(".toolSelect")?.options.length > 0, { timeout: 6000 }).then(() => 1).catch(() => 0)) page = p;
      } catch {} if (!page) await sleep(1500);
    }
    if (!page) throw new Error("portal 未就緒");
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.selectOption(".toolSelect", "sheet-annotation");
    await page.click('button:has-text("Start")');
    await page.waitForTimeout(26000);
    log("tool started");

    let f = stFrame(page);
    if (!f) throw new Error("無 streamlit frame");
    await page.screenshot({ path: join(OUT, "step1_datasource.png") });

    // 1) 填資料夾路徑 + 執行
    let filled = false;
    for (const sel of ['input[placeholder="C:/path/to/images"]', 'input[aria-label*="路徑"]', 'input[type="text"]']) {
      const loc = f.locator(sel).first();
      if (await loc.count().catch(() => 0)) { await loc.fill(DATASET).catch(() => {}); await loc.press("Tab").catch(() => {}); filled = true; log("filled path via " + sel); break; }
    }
    if (!filled) log("WARN: 找不到路徑輸入框");
    await page.waitForTimeout(1000);
    const execBtn = f.locator('button:has-text("執行")').first();
    if (await execBtn.count().catch(() => 0)) { await execBtn.click().catch(() => {}); log("clicked 執行"); }
    else log("WARN: 找不到 執行 按鈕");
    await page.waitForTimeout(14000); // 等掃描建 manifest
    f = stFrame(page) || f;
    await page.screenshot({ path: join(OUT, "step2_after_execute.png") });

    // 2) 切到「標注工作台」(先試 page,再試各 frame)
    let navOk = false;
    for (const ctx of [page, ...page.frames()]) {
      const loc = ctx.locator('text=標注工作台').first();
      if (await loc.count().catch(() => 0)) { await loc.click({ timeout: 4000 }).catch(() => {}); navOk = true; log("clicked 標注工作台"); break; }
    }
    if (!navOk) log("WARN: 找不到 標注工作台 nav");
    await page.waitForTimeout(9000); // 等 標注工作台 Input 頁
    // 依內容挑「標注工作台」那個 frame(portal 有多個 127.0.0.1 iframe)
    let wf = (await frameWith(page, "標注類別")) || stFrame(page);
    await page.screenshot({ path: join(OUT, "d1_input.png") });
    let target = wf.locator('textarea[placeholder*="scratch"]').first();
    if (!(await target.count().catch(() => 0))) target = wf.locator("textarea").first();
    if (await target.count().catch(() => 0)) {
      await target.click().catch(() => {});
      await page.keyboard.type("door\nopenedDoor", { delay: 25 }).catch(() => {});
      await page.keyboard.press("Tab").catch(() => {}); // blur → Streamlit commit
      log("typed categories into 標注工作台 frame");
    } else log("WARN: 類別 textarea 仍找不到");
    await page.waitForTimeout(4000);
    wf = (await frameWith(page, "標注類別")) || wf;
    await page.screenshot({ path: join(OUT, "d2_typed.png") });
    const runBtn = wf.locator('button:has-text("執行")');
    log("執行 buttons=" + (await runBtn.count().catch(() => 0)));
    await runBtn.first().click().catch(() => {});
    log("clicked 執行(workbench)");
    await page.waitForTimeout(24000); // 等 Output 工作台 render
    await page.screenshot({ path: join(OUT, "d3_after_run.png") });

    // 3) 多尺寸截工作台 + 量(用含「圖片列表」的 frame)
    for (const v of [{ w: 2560, h: 1440 }, { w: 1366, h: 768 }, { w: 1024, h: 768 }]) {
      await page.setViewportSize({ width: v.w, height: v.h });
      await page.waitForTimeout(4000);
      const png = join(OUT, `workbench_${v.w}x${v.h}.png`);
      await page.screenshot({ path: png });
      let metrics = null;
      try {
        const gf = (await frameWith(page, "圖片列表")) || (await frameWith(page, "標注類別")) || stFrame(page);
        if (gf) metrics = await gf.evaluate(() => { const imgs = [...document.querySelectorAll('img')].map(e => { const r = e.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), nat: e.naturalWidth + "x" + e.naturalHeight }; }).filter(m => m.w > 80); return { fw: document.documentElement.clientWidth, nImages: imgs.length, biggest: imgs.sort((a, b) => b.w * b.h - a.w * a.h)[0] || null }; });
      } catch (e) { metrics = { err: String(e).slice(0, 100) }; }
      out.shots.push({ tag: `${v.w}x${v.h}`, png, metrics });
      log(`workbench ${v.w}x${v.h}: ` + JSON.stringify(metrics));
      if (v.w <= 1366) { // 捲到明細圖,證明小尺寸下圖仍大(關掉 P2 的 below-fold caveat)
        try { const gf2 = (await frameWith(page, "圖片列表")) || stFrame(page); await gf2.locator("img").last().scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => {}); } catch {}
        await page.mouse.wheel(0, 700).catch(() => {});
        await page.waitForTimeout(1700);
        await page.screenshot({ path: join(OUT, `workbench_${v.w}x${v.h}_scrolled.png`) });
        log(`scrolled shot ${v.w}`);
      }
    }

    // 4) 情境:版面比例(大圖/並排/標準)+ 原圖切換,都在 2560 拍
    await page.setViewportSize({ width: 2560, height: 1440 });
    await page.waitForTimeout(2500);
    let wf2 = (await frameWith(page, "圖片列表")) || stFrame(page);
    for (const [re, file] of [[/大圖/, "scn_ratio_large.png"], [/並排/, "scn_ratio_side.png"], [/標準/, "scn_ratio_std.png"]]) {
      try { const r = wf2.getByText(re).first(); if (await r.count().catch(() => 0)) { await r.click().catch(() => {}); await page.waitForTimeout(4000); await page.screenshot({ path: join(OUT, file) }); log("captured " + file); } } catch {}
      wf2 = (await frameWith(page, "圖片列表")) || wf2;
    }
    try {
      let og = wf2.locator('[data-testid="stRadio"] label').filter({ hasText: "原圖" }).first();
      if (!(await og.count().catch(() => 0))) og = wf2.locator("label").filter({ hasText: "原圖" }).first();
      if (await og.count().catch(() => 0)) {
        await og.scrollIntoViewIfNeeded().catch(() => {});
        await og.click({ force: true }).catch(() => {});
        await page.waitForTimeout(4500);
        await page.screenshot({ path: join(OUT, "scn_original.png") });
        log("captured scn_original.png (原圖 state)");
      } else log("WARN: 原圖 radio 找不到");
    } catch (e) { log("原圖 err " + String(e).slice(0, 80)); }

    if (browser) await browser.close();
  } catch (e) { out.error = String(e?.message || e).slice(0, 300); }
  finally { try { execSync(`taskkill /PID ${child.pid} /T /F`, { stdio: "ignore" }); } catch {} try { child.kill(); } catch {} }
  writeFileSync(join(OUT, "verify.json"), JSON.stringify(out, null, 2));
  console.log("RESULT_JSON " + JSON.stringify(out));
})();
