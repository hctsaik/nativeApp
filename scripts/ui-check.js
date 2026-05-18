const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });

  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0', timeout: 15000 });

  // Screenshot
  await page.screenshot({ path: 'scripts/ui-check.png', fullPage: true });

  // Check: Top Bar text
  const topBarText = await page.$eval('.top-bar, header, #top-bar, [class*="top"]', el => el.innerText).catch(() => 'NOT FOUND');
  console.log('[Top Bar text]', topBarText.slice(0, 200));

  // Check: Choose File button should NOT exist
  const chooseFileBtn = await page.$('button[class*="choose"], button[class*="file"]');
  const chooseFileByText = await page.$$eval('button', btns =>
    btns.filter(b => b.innerText.toLowerCase().includes('choose file')).map(b => b.innerText)
  );
  console.log('[Choose File button]', chooseFileByText.length > 0 ? `FOUND: ${chooseFileByText}` : 'NOT FOUND (correct)');

  // Check: tool select / dropdown
  const selects = await page.$$eval('select, [class*="select"], [class*="dropdown"]', els => els.map(el => el.outerHTML.slice(0, 100)));
  console.log('[Tool dropdowns]', selects.length, 'found');
  selects.forEach((s, i) => console.log(`  [${i}]`, s));

  // Check: tabs (Input / Output)
  const tabs = await page.$$eval('[class*="tab"]', els => els.map(el => el.innerText?.trim()).filter(Boolean));
  console.log('[Tabs]', tabs);

  // All buttons on page
  const buttons = await page.$$eval('button', btns => btns.map(b => b.innerText?.trim()).filter(Boolean));
  console.log('[All buttons]', buttons);

  await browser.close();
  console.log('\nScreenshot saved: scripts/ui-check.png');
})();
