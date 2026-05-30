const puppeteer = require('puppeteer');

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
async function shot(page, name) {
  await page.screenshot({ path: `scripts/${name}.png`, fullPage: true });
  console.log(`[screenshot] ${name}.png`);
}

(async () => {
  // Step 1: Start cv-framework via Electron portal
  const electron = await puppeteer.connect({ browserURL: 'http://localhost:9222', defaultViewport: null });
  const pages = await electron.pages();
  const portalPage = pages.find(p => !p.url().startsWith('devtools://')) ?? pages[0];
  console.log(`[portal] ${portalPage.url()}`);

  await portalPage.waitForSelector('.toolSelect', { timeout: 10000 });
  await portalPage.select('.toolSelect', 'cv-framework');
  await wait(300);
  await portalPage.click('button:not(.btn-danger)');
  await wait(4000);
  await shot(portalPage, 'e2e-01-portal-started');

  // Get Streamlit URLs from IPC log
  const logRes = await fetch('http://127.0.0.1:19222/dev/log');
  const logText = await logRes.text();
  const inputMatch = logText.match(/input_url=(http:\/\/127\.0\.0\.1:\d+)/);
  const outputMatch = logText.match(/output_url=(http:\/\/127\.0\.0\.1:\d+)/);
  const inputUrl = inputMatch?.[1];
  const outputUrl = outputMatch?.[1];
  console.log(`[input-url]  ${inputUrl}`);
  console.log(`[output-url] ${outputUrl}`);

  if (!inputUrl) { console.error('No input URL found in log'); await electron.disconnect(); return; }

  // Step 2: Operate Input Streamlit directly
  const stBrowser = await puppeteer.launch({ headless: true });
  const stPage = await stBrowser.newPage();
  await stPage.setViewport({ width: 1280, height: 900 });

  await stPage.goto(inputUrl, { waitUntil: 'networkidle0', timeout: 20000 });
  await wait(2000);
  await shot(stPage, 'e2e-02-input-loaded');

  // Check module options
  const opts = await stPage.$$eval('option', os => os.map(o => o.text));
  console.log('[module options]', opts);

  const imgIdx = opts.findIndex(o => o.includes('影像資訊'));
  if (imgIdx >= 0) {
    const selects = await stPage.$$('select');
    await selects[0].select(String(imgIdx));
    await wait(2000);
    await shot(stPage, 'e2e-03-module-selected');
    console.log('[module] 影像資訊讀取 selected ✅');
  } else {
    console.log('[module] 影像資訊讀取 not in options:', opts);
  }

  // Type memo
  await wait(500);
  const textInputs = await stPage.$$('input[type=text]');
  console.log(`[memo inputs] ${textInputs.length}`);
  if (textInputs.length > 0) {
    await textInputs[0].click({ clickCount: 3 });
    await textInputs[0].type('E2E 自動測試');
    await wait(500);
    console.log('[memo] typed ✅');
  }

  // Click ▶ 執行
  const clicked = await stPage.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('執行'));
    if (btn) { btn.click(); return true; }
    return false;
  });
  console.log(`[execute] ${clicked ? 'clicked ✅' : 'not found ❌'}`);

  await wait(4000);
  await shot(stPage, 'e2e-04-after-execute');

  // Step 3: Check Output Streamlit
  if (outputUrl) {
    const outPage = await stBrowser.newPage();
    await outPage.setViewport({ width: 1280, height: 900 });
    await outPage.goto(outputUrl, { waitUntil: 'networkidle0', timeout: 20000 });
    await wait(2000);
    await shot(outPage, 'e2e-05-output-loaded');

    const outText = await outPage.evaluate(() => document.body.innerText);
    console.log('[output text]', outText.slice(0, 400));

    // Check result table exists
    const tables = await outPage.$$('table');
    console.log(`[output tables] ${tables.length} found ${tables.length > 0 ? '✅' : '❌'}`);
  }

  // Step 4: Check Portal switched to Output tab
  await shot(portalPage, 'e2e-06-portal-after-execute');
  const activeTab = await portalPage.$eval('.tab.active', el => el.innerText).catch(() => 'unknown');
  console.log(`[portal active tab] "${activeTab}"`);

  await stBrowser.close();

  // Stop tool
  const stopBtn = await portalPage.$('.btn-danger');
  if (stopBtn) { await stopBtn.click(); }
  await electron.disconnect();

  console.log('\n✅ E2E done. Check scripts/e2e-*.png');
})();
