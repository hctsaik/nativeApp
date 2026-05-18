const puppeteer = require('puppeteer');
const path = require('path');

const SHOT = f => path.join(__dirname, f);

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
async function shot(page, name) {
  await page.screenshot({ path: SHOT(`${name}.png`), fullPage: true });
  console.log(`[screenshot] ${name}.png`);
}

(async () => {
  const browser = await puppeteer.connect({ browserURL: 'http://localhost:9222', defaultViewport: null });
  const pages = await browser.pages();
  const page = pages.find(p => !p.url().startsWith('devtools://')) ?? pages[0];
  console.log(`[target] ${page.url()}`);

  await page.waitForSelector('.toolSelect', { timeout: 10000 });

  // Verify module_002 is in tool options (cv-framework module list is inside Streamlit, not top dropdown)
  const options = await page.$$eval('.toolSelect option', opts => opts.map(o => o.value));
  console.log(`[top-dropdown options]`, options);

  // Select cv-framework and start
  await page.select('.toolSelect', 'cv-framework');
  await wait(500);
  console.log('[action] Start cv-framework...');
  await page.click('button:not(.btn-danger)');
  await wait(5000); // wait for Streamlit to load
  await shot(page, 'm002-01-started');

  // Check iframe loaded
  const iframe = await page.$('iframe[title="Input"]');
  if (!iframe) { console.log('[ERROR] No input iframe found'); await browser.disconnect(); return; }
  console.log('[input-iframe] FOUND ✅');

  // Get iframe content
  const frame = await iframe.contentFrame();
  if (!frame) { console.log('[ERROR] Cannot access iframe content'); await browser.disconnect(); return; }

  // Wait for Streamlit to render inside iframe
  await frame.waitForSelector('.stApp', { timeout: 15000 }).catch(() => console.log('[warn] .stApp not found, trying anyway'));
  await wait(2000);
  await shot(page, 'm002-02-streamlit-loaded');

  // Look for module selector in sidebar
  const sidebarText = await frame.$eval('[data-testid="stSidebar"]', el => el.innerText).catch(() => 'no sidebar');
  console.log(`[sidebar text] ${sidebarText.slice(0, 200)}`);

  // Select 影像資訊讀取 in sidebar dropdown if present
  const selects = await frame.$$('select');
  console.log(`[selects in iframe] ${selects.length}`);
  for (const sel of selects) {
    const opts = await sel.$$eval('option', os => os.map(o => o.innerText));
    console.log('  options:', opts);
    if (opts.some(o => o.includes('影像資訊讀取'))) {
      console.log('[action] selecting 影像資訊讀取...');
      await sel.select(opts.findIndex(o => o.includes('影像資訊讀取')).toString());
      await wait(2000);
      break;
    }
  }

  await shot(page, 'm002-03-module-selected');

  // Type memo
  const memoInput = await frame.$('input[type="text"], textarea').catch(() => null);
  if (memoInput) {
    await memoInput.click();
    await memoInput.type('Puppeteer 自動測試');
    console.log('[memo] typed ✅');
    await wait(500);
  } else {
    console.log('[memo] input not found');
  }

  await shot(page, 'm002-04-memo-typed');

  // Click ▶ 執行
  const execBtn = await frame.$('button[kind="primary"], button[data-testid="baseButton-primary"]').catch(() => null);
  if (execBtn) {
    console.log('[action] clicking ▶ 執行...');
    await execBtn.click();
    await wait(4000);
    await shot(page, 'm002-05-after-execute');
    console.log('[execute] clicked ✅');
  } else {
    // Try by text
    const allBtns = await frame.$$eval('button', bs => bs.map(b => b.innerText.trim()));
    console.log('[buttons in iframe]', allBtns);
  }

  // Stop tool
  const stopBtn = await page.$('.btn-danger');
  if (stopBtn) { await stopBtn.click(); await wait(500); }

  await browser.disconnect();
  console.log('\n✅ Done. Check scripts/m002-*.png');
})();
