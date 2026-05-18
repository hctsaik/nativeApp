const puppeteer = require('puppeteer');

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
async function shot(page, name) {
  await page.screenshot({ path: `scripts/${name}.png`, fullPage: true });
  console.log(`[screenshot] ${name}.png`);
}

// Use page.evaluate() to avoid Runtime.callFunctionOn Electron timeout issues.
async function portalSelect(page, selector, value) {
  await page.evaluate((sel, val) => {
    const el = document.querySelector(sel);
    if (!el) throw new Error(`selector not found: ${sel}`);
    const nativeSetter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
    nativeSetter.call(el, val);
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }, selector, value);
}

async function portalEval(page, fn) {
  return page.evaluate(fn);
}

(async () => {
  // ── Step 1: Connect to Electron portal ────────────────────
  const electron = await puppeteer.connect({ browserURL: 'http://localhost:9222', defaultViewport: null, protocolTimeout: 120000 });
  const pages = await electron.pages();
  const portal = pages.find(p => !p.url().startsWith('devtools://')) ?? pages[0];

  await portal.waitForSelector('.toolSelect', { timeout: 10000 });
  const toolOptions = await portalEval(portal, () =>
    Array.from(document.querySelectorAll('.toolSelect option')).map(o => ({ value: o.value, text: o.text }))
  );
  console.log('[tools]', JSON.stringify(toolOptions));

  await portalSelect(portal, '.toolSelect', 'opencv-tool');
  await wait(500);

  await portalEval(portal, () => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => !b.classList.contains('btn-danger') && !b.disabled);
    btn?.click();
  });
  console.log('[portal] opencv-tool starting...');
  await wait(3000);
  await shot(portal, 'cv-01-portal-started');

  // ── Step 2: Read input URL (input tab is active by default) ─
  await portal.waitForSelector('iframe[title="Input"]', { timeout: 30000 });
  const inputUrl = await portalEval(portal, () =>
    document.querySelector('iframe[title="Input"]')?.src ?? null
  );
  console.log(`[input-url] ${inputUrl}`);

  // Switch portal to output tab to read outputUrl
  await portalEval(portal, () => {
    const tabs = Array.from(document.querySelectorAll('.tab'));
    const outTab = tabs.find(t => t.innerText.trim() === 'Output');
    outTab?.click();
  });
  await wait(1000);
  await portal.waitForSelector('iframe[title="Output"]', { timeout: 10000 });
  const outputUrl = await portalEval(portal, () =>
    document.querySelector('iframe[title="Output"]')?.src ?? null
  );
  console.log(`[output-url] ${outputUrl}`);

  // Switch back to input tab
  await portalEval(portal, () => {
    const tabs = Array.from(document.querySelectorAll('.tab'));
    const inTab = tabs.find(t => t.innerText.trim() === 'Input');
    inTab?.click();
  });
  await wait(500);
  await shot(portal, 'cv-02-portal-urls-read');

  if (!inputUrl) { console.error('No input URL'); await electron.disconnect(); return; }

  // ── Step 3: Operate Input Streamlit ──────────────────────
  const stBrowser = await puppeteer.launch({ headless: true, protocolTimeout: 120000 });
  const inputPage = await stBrowser.newPage();
  await inputPage.setViewport({ width: 1280, height: 900 });
  await inputPage.goto(inputUrl, { waitUntil: 'networkidle0', timeout: 30000 });
  await inputPage.waitForSelector('[data-testid="stSidebar"]', { timeout: 30000 });
  await wait(2000);
  await shot(inputPage, 'cv-03-input-loaded');

  const previewVisible = await inputPage.evaluate(() => !!document.querySelector('img'));
  console.log(`[preview] image present: ${previewVisible}`);

  const executed = await inputPage.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('執行'));
    if (btn) { btn.click(); return true; }
    return false;
  });
  console.log(`[execute] ${executed ? 'clicked ✅' : 'not found ❌'}`);

  await inputPage.waitForSelector('[data-testid="stAlert"], [data-testid="stSuccess"]', { timeout: 30000 }).catch(() => null);
  await wait(2000);
  await shot(inputPage, 'cv-04-after-execute');

  const msg = await inputPage.evaluate(() => {
    const el = document.querySelector('[data-testid="stAlert"], [data-testid="stSuccess"]');
    return el ? el.innerText : '';
  });
  console.log(`[execute msg] ${msg || '(none)'}`);

  // ── Step 4: Switch portal to output tab ────────────────────
  await portalEval(portal, () => {
    const tabs = Array.from(document.querySelectorAll('.tab'));
    const outTab = tabs.find(t => t.innerText.trim() === 'Output');
    outTab?.click();
  });
  await wait(1000);
  await shot(portal, 'cv-05-portal-output-tab');
  const activeTab = await portalEval(portal, () =>
    document.querySelector('.tab.active')?.innerText?.trim() ?? 'unknown'
  );
  console.log(`[portal active tab] "${activeTab}"`);

  // ── Step 5: Check Output Streamlit ───────────────────────
  if (!outputUrl) {
    console.error('No output URL — skipping output verification');
  } else {
    const outPage = await stBrowser.newPage();
    await outPage.setViewport({ width: 1280, height: 900 });
    await outPage.goto(outputUrl, { waitUntil: 'networkidle0', timeout: 30000 });
    await wait(5000);
    await shot(outPage, 'cv-06-output');

    const imgCount = await outPage.evaluate(() => document.querySelectorAll('img').length);
    console.log(`[output] image count: ${imgCount} (expect 2)`);

    const caption = await outPage.evaluate(() => {
      const el = document.querySelector('[data-testid="stCaptionContainer"], [data-testid="stMarkdown"]');
      return el ? el.innerText : '';
    });
    console.log(`[output caption] ${caption.slice(0, 120)}`);

    const pass = executed && imgCount >= 2;
    console.log(`\n${pass ? '✅' : '❌'} Done. Check scripts/cv-*.png`);

    await stBrowser.close();
    await portalEval(portal, () => { document.querySelector('.btn-danger')?.click(); });
    await electron.disconnect();
    process.exit(pass ? 0 : 1);
    return;
  }

  await stBrowser.close();
  await portalEval(portal, () => { document.querySelector('.btn-danger')?.click(); });
  await electron.disconnect();
  process.exit(executed ? 0 : 1);
})().catch(err => { console.error(err); process.exit(1); });
