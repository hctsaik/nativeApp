// E2E 地基驗證:Playwright 經 CDP 連 Tauri WebView2,驅動 portal、起一個工具、檢查 iframe 真算繪。
import { chromium } from "playwright-core";

const CDP = process.env.CDP_URL || "http://127.0.0.1:9222";
const TOOL = process.argv[2] || "sheet-edge-analysis";

function log(...a) { console.log(...a); }

const browser = await chromium.connectOverCDP(CDP);
try {
  const ctx = browser.contexts()[0];
  const page = ctx.pages().find((p) => p.url().includes("tauri.localhost")) || ctx.pages()[0];
  await page.bringToFront().catch(() => {});

  // 蒐集 console error(對抗性:抓 WebView2 內的 JS 錯誤)
  const consoleErrors = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => consoleErrors.push("pageerror: " + e.message));

  log("page url:", page.url());
  const brand = await page.textContent(".top-bar-brand").catch(() => null);
  log("brand:", brand);

  // shim:listTools
  const tools = await page.evaluate(async () => (await window.cimHost.listTools()).map((x) => x.tool_id));
  log("listTools count:", tools.length);

  // 工具下拉選項
  const opts = await page.$$eval(".toolSelect option", (els) => els.map((e) => e.value).filter(Boolean));
  log("dropdown options:", JSON.stringify(opts));

  // 選工具 + 按 Start
  await page.selectOption(".toolSelect", TOOL);
  log("selected:", TOOL, "→ clicking Start");
  await page.click('button:has-text("Start")');

  // 等工具狀態變 running / iframe 出現(最多 35s）
  await page.waitForTimeout(25000);

  // 檢查 iframe 內容
  const frames = page.frames().filter((f) => f.url().startsWith("http://127.0.0.1"));
  log("tool iframes:", frames.length, frames.map((f) => f.url()));
  let verdict = "NO_IFRAME";
  for (const f of frames) {
    try {
      const bodyText = (await f.locator("body").innerText({ timeout: 3000 }).catch(() => "")) || "";
      const hasStApp = await f.locator('[data-testid="stApp"]').count().catch(() => 0);
      const notFound = bodyText.includes("Not Found") || bodyText.trim() === "404: Not Found";
      log(`  frame ${f.url()} -> stApp=${hasStApp} notFound=${notFound} bodyLen=${bodyText.length} sample="${bodyText.slice(0,60).replace(/\n/g,' ')}"`);
      if (hasStApp > 0 && !notFound) verdict = "RENDERED";
      else if (notFound && verdict !== "RENDERED") verdict = "NOT_FOUND";
    } catch (e) { log("  frame read err:", e.message); }
  }

  log("CONSOLE_ERRORS:", consoleErrors.length, JSON.stringify(consoleErrors.slice(0, 5)));
  log("VERDICT:", verdict);
} finally {
  await browser.close(); // 只斷 CDP 連線,不關 app
}
