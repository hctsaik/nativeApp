const puppeteer = require('puppeteer');

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
async function shot(page, name) {
  await page.screenshot({ path: `scripts/${name}.png`, fullPage: true });
  console.log(`[screenshot] ${name}.png`);
}

async function selectStreamlitOption(page, containerSelector, optionText) {
  const container = await page.$(containerSelector);
  if (!container) return false;
  await container.click();
  // Wait for option list to appear
  const option = await page.waitForSelector(
    `[role="option"]:has-text("${optionText}"), li:has-text("${optionText}")`,
    { timeout: 8000 }
  ).catch(async () => {
    // Fallback: find by text content
    return page.$$('[role="option"]').then(items =>
      items.find(async el => (await el.evaluate(n => n.innerText))?.includes(optionText))
    );
  });
  if (!option) return false;
  await option.click();
  await wait(1000);
  return true;
}

(async () => {
  // ── Step 1: Start cv-framework via Portal ─────────────────
  const electron = await puppeteer.connect({ browserURL: 'http://localhost:9222', defaultViewport: null });
  const pages = await electron.pages();
  const portal = pages.find(p => !p.url().startsWith('devtools://')) ?? pages[0];

  await portal.waitForSelector('.toolSelect', { timeout: 10000 });
  await portal.select('.toolSelect', 'cv-framework');
  await wait(300);
  await portal.click('button:not(.btn-danger)');
  console.log('[portal] cv-framework starting...');
  await wait(5000);
  await shot(portal, 'run-01-portal');

  // ── Step 2: Read URLs directly from Portal iframe src ─────
  await portal.waitForSelector('iframe[title="Input"]', { timeout: 15000 });
  const inputUrl = await portal.$eval('iframe[title="Input"]', el => el.src).catch(() => null);
  const outputUrl = await portal.$eval('iframe[title="Output"]', el => el.src).catch(() => null);
  console.log(`[input-url]  ${inputUrl}`);
  console.log(`[output-url] ${outputUrl}`);
  if (!inputUrl) { console.error('No input iframe found'); await electron.disconnect(); return; }

  // ── Step 3: Operate Input Streamlit ──────────────────────
  const stBrowser = await puppeteer.launch({ headless: true, protocolTimeout: 120000 });
  const inputPage = await stBrowser.newPage();
  await inputPage.setViewport({ width: 1280, height: 900 });
  await inputPage.goto(inputUrl, { waitUntil: 'networkidle0', timeout: 20000 });
  // Wait for Streamlit to finish initial render (spinner gone, sidebar visible)
  await inputPage.waitForSelector('[data-testid="stSidebar"]', { timeout: 20000 });
  await wait(2000);
  await shot(inputPage, 'run-02-input');

  // Select 影像資訊讀取
  const selected = await selectStreamlitOption(
    inputPage,
    '[data-testid="stSidebar"] [data-baseweb="select"]',
    '影像資訊讀取'
  );
  console.log(`[module] ${selected ? '影像資訊讀取 ✅' : 'failed ❌'}`);
  await wait(2000);
  await shot(inputPage, 'run-03-module-selected');

  // Type memo
  const memoInput = await inputPage.$('input[aria-label="Memo / 備註"]').catch(() => null)
    || await inputPage.$('input[type=text]').catch(() => null);
  if (memoInput) {
    await memoInput.click({ clickCount: 3 });
    await memoInput.type('全流程驗收測試');
    console.log('[memo] typed ✅');
  }
  await wait(400);
  await shot(inputPage, 'run-04-memo');

  // Click ▶ 執行
  const executed = await inputPage.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('執行'));
    if (btn) { btn.click(); return true; }
    return false;
  });
  console.log(`[execute] ${executed ? 'clicked ✅' : 'not found ❌'}`);
  await wait(5000);
  await shot(inputPage, 'run-05-after-execute');

  const msg = await inputPage.$eval('[data-testid="stAlert"]', el => el.innerText).catch(() => '');
  console.log(`[execute msg] ${msg || '(none)'}`);

  // ── Step 4: Portal switches to Output tab? ────────────────
  await wait(1000);
  await shot(portal, 'run-06-portal-output-tab');
  const activeTab = await portal.$eval('.tab.active', el => el.innerText.trim()).catch(() => 'unknown');
  console.log(`[portal active tab] "${activeTab}"`);

  // ── Step 5: Output Streamlit ──────────────────────────────
  const outPage = await stBrowser.newPage();
  await outPage.setViewport({ width: 1280, height: 900 });
  await outPage.goto(outputUrl, { waitUntil: 'networkidle0', timeout: 20000 });
  await wait(5000);
  await shot(outPage, 'run-07-output');

  const outText = await outPage.evaluate(() => document.body.innerText);
  console.log('[output]', outText.slice(0, 400));

  // ── Cleanup ───────────────────────────────────────────────
  await stBrowser.close();
  const stopBtn = await portal.$('.btn-danger').catch(() => null);
  if (stopBtn) { await stopBtn.click(); }
  await electron.disconnect();
  console.log('\n✅ Done. Check scripts/run-*.png');
})();
