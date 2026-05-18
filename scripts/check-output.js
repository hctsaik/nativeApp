const puppeteer = require('puppeteer');

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }
async function shot(page, name) {
  await page.screenshot({ path: `scripts/${name}.png`, fullPage: true });
  console.log(`[screenshot] ${name}.png`);
}

// Click a Streamlit selectbox and pick an option by partial text
async function selectStreamlitOption(page, containerSelector, optionText) {
  const container = await page.$(containerSelector);
  if (!container) { console.log(`[warn] container not found: ${containerSelector}`); return false; }

  await container.click();
  await wait(600);

  // Options appear in a listbox overlay
  const found = await page.evaluate((text) => {
    const items = Array.from(document.querySelectorAll('[role="option"], li'));
    const match = items.find(el => el.innerText?.includes(text));
    if (match) { match.click(); return true; }
    return false;
  }, optionText);

  await wait(800);
  return found;
}

(async () => {
  // Get URLs from IPC log
  const logRes = await fetch('http://127.0.0.1:19222/dev/log');
  const logText = await logRes.text();
  const inputMatch = logText.match(/input_url=(http:\/\/127\.0\.0\.1:\d+)/g);
  const outputMatch = logText.match(/output_url=(http:\/\/127\.0\.0\.1:\d+)/g);
  // Last occurrence is the current session
  const inputUrl = inputMatch?.at(-1)?.split('=')[1];
  const outputUrl = outputMatch?.at(-1)?.split('=')[1];
  console.log(`[input-url]  ${inputUrl}`);
  console.log(`[output-url] ${outputUrl}`);

  const browser = await puppeteer.launch({ headless: true, protocolTimeout: 60000 });

  // ── Input Streamlit ───────────────────────────────────────
  const inputPage = await browser.newPage();
  await inputPage.setViewport({ width: 1280, height: 900 });
  await inputPage.goto(inputUrl, { waitUntil: 'networkidle0', timeout: 20000 });
  await wait(2000);

  // Click "選擇模組" dropdown and pick 影像資訊讀取
  const selected = await selectStreamlitOption(
    inputPage,
    '[data-testid="stSidebar"] [data-baseweb="select"]',
    '影像資訊讀取'
  );
  console.log(`[module select] ${selected ? '影像資訊讀取 ✅' : 'failed ❌'}`);

  await wait(2000);
  await shot(inputPage, 'out-01-module-selected');

  // Type memo in text input
  const memoInput = await inputPage.$('input[aria-label="Memo / 備註"]').catch(() => null)
    || await inputPage.$('input[type=text]').catch(() => null);
  if (memoInput) {
    await memoInput.click({ clickCount: 3 });
    await memoInput.type('E2E 自動測試 002');
    await wait(400);
    console.log('[memo] typed ✅');
  } else {
    console.log('[memo] input not found');
  }

  await shot(inputPage, 'out-02-memo-typed');

  // Click ▶ 執行
  const clicked = await inputPage.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button'))
      .find(b => b.innerText.includes('執行'));
    if (btn) { btn.click(); return true; }
    return false;
  });
  console.log(`[execute] ${clicked ? 'clicked ✅' : 'not found ❌'}`);

  await wait(4000);
  await shot(inputPage, 'out-03-after-execute');

  const successMsg = await inputPage.$eval('[data-testid="stAlert"]', el => el.innerText).catch(() => null);
  console.log(`[execute msg] ${successMsg ?? '(none)'}`);

  // ── Output Streamlit ──────────────────────────────────────
  const outPage = await browser.newPage();
  await outPage.setViewport({ width: 1280, height: 900 });
  await outPage.goto(outputUrl, { waitUntil: 'networkidle0', timeout: 20000 });
  await wait(3000);
  await shot(outPage, 'out-04-output-page');

  const outText = await outPage.evaluate(() => document.body.innerText);
  console.log('[output text]', outText.slice(0, 500));

  const tables = await outPage.$$('table, [data-testid="stTable"]');
  console.log(`[output table] ${tables.length > 0 ? 'FOUND ✅' : 'NOT FOUND ❌'}`);

  await browser.close();
  console.log('\n✅ Done. Check scripts/out-*.png');
})();
