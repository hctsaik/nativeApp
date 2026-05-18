const puppeteer = require('puppeteer');

(async () => {
  // Get the Streamlit input URL from the IPC log
  const logRes = await fetch('http://127.0.0.1:19222/dev/log');
  const logText = await logRes.text();
  const match = logText.match(/input_url=(http:\/\/127\.0\.0\.1:\d+)/);
  const streamlitUrl = match ? match[1] : 'http://127.0.0.1:55180';
  console.log(`[streamlit-url] ${streamlitUrl}`);

  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });

  await page.goto(streamlitUrl, { waitUntil: 'networkidle0', timeout: 20000 });
  await page.screenshot({ path: 'scripts/m002-01.png' });
  console.log('[1] Streamlit loaded');

  const bodyText = await page.evaluate(() => document.body.innerText);
  console.log('[body]', bodyText.slice(0, 300));

  // Check options for module selector
  const opts = await page.$$eval('option', os => os.map(o => o.text));
  console.log('[options]', opts);

  // Select 影像資訊讀取
  const imgInfoIdx = opts.findIndex(o => o.includes('影像資訊'));
  if (imgInfoIdx >= 0) {
    const selects = await page.$$('select');
    if (selects.length > 0) {
      await selects[0].select(String(imgInfoIdx));
      await new Promise(r => setTimeout(r, 2500));
      await page.screenshot({ path: 'scripts/m002-02.png' });
      console.log('[2] module selected');
    }
  } else {
    console.log('[!] options:', opts);
  }

  // Type memo
  await new Promise(r => setTimeout(r, 1000));
  const inputs = await page.$$('input[type=text]');
  console.log('[text inputs]', inputs.length);
  if (inputs.length > 0) {
    await inputs[0].click({ clickCount: 3 });
    await inputs[0].type('Puppeteer 自動測試');
    await new Promise(r => setTimeout(r, 500));
    await page.screenshot({ path: 'scripts/m002-03.png' });
    console.log('[3] memo typed');
  }

  // Click ▶ 執行 button
  const btnClicked = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const execBtn = btns.find(b => b.innerText.includes('執行'));
    if (execBtn) { execBtn.click(); return true; }
    return false;
  });
  console.log(`[execute btn] ${btnClicked ? 'clicked ✅' : 'not found ❌'}`);

  if (btnClicked) {
    await new Promise(r => setTimeout(r, 4000));
    await page.screenshot({ path: 'scripts/m002-04.png' });
    console.log('[4] after execute');
  }

  await browser.close();
  console.log('Done.');
})();
