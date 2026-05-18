const puppeteer = require('puppeteer');
const path = require('path');

const SCREENSHOT_DIR = path.join(__dirname);

async function shot(page, name) {
  const file = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`[screenshot] ${name}.png`);
}

async function wait(ms) {
  return new Promise(r => setTimeout(r, ms));
}

(async () => {
  const browser = await puppeteer.connect({
    browserURL: 'http://localhost:9222',
    defaultViewport: null
  });

  const pages = await browser.pages();
  console.log(`[pages] found ${pages.length}`);
  pages.forEach((p, i) => console.log(`  [${i}] ${p.url()}`));

  // Find the portal page (not devtools)
  const page = pages.find(p => !p.url().startsWith('devtools://')) ?? pages[0];
  console.log(`[target] ${page.url()}`);

  // Wait for React to render
  await page.waitForSelector('.toolbar', { timeout: 10000 });
  await shot(page, '01-initial');

  // ── Check Top Bar ──────────────────────────────────────────
  const brand = await page.$eval('.top-bar-brand', el => el.innerText).catch(() => 'NOT FOUND');
  console.log(`[top-bar-brand] "${brand}"`);

  const buttons = await page.$$eval('button', bs => bs.map(b => b.innerText.trim()));
  console.log(`[buttons]`, buttons);

  const chooseFile = buttons.filter(b => b.toLowerCase().includes('choose file'));
  console.log(`[choose-file] ${chooseFile.length === 0 ? 'NOT FOUND ✅' : 'FOUND ❌ ' + chooseFile}`);

  // ── Check tool dropdown ────────────────────────────────────
  const options = await page.$$eval('.toolSelect option', opts => opts.map(o => ({ value: o.value, text: o.innerText })));
  console.log(`[tool-options] ${options.length} found:`);
  options.forEach(o => console.log(`  - ${o.value}: ${o.text}`));

  // ── Start cv-framework ─────────────────────────────────────
  const cvFramework = options.find(o => o.value === 'cv-framework');
  if (cvFramework) {
    console.log('\n[action] selecting cv-framework...');
    await page.select('.toolSelect', 'cv-framework');
    await wait(500);
    await shot(page, '02-cv-framework-selected');

    console.log('[action] clicking Start Tool...');
    await page.click('button:not(.btn-danger)'); // Start Tool button
    await wait(3000);
    await shot(page, '03-cv-framework-started');

    const inputIframe = await page.$('iframe[title="Input"]');
    console.log(`[input-iframe] ${inputIframe ? 'FOUND ✅' : 'NOT FOUND ❌'}`);

    const iframeSrc = inputIframe
      ? await page.$eval('iframe[title="Input"]', el => el.src)
      : 'N/A';
    console.log(`[input-iframe-src] ${iframeSrc}`);

    // ── Stop tool ──────────────────────────────────────────
    await wait(1000);
    const stopBtn = await page.$('.btn-danger');
    if (stopBtn) {
      console.log('[action] clicking Stop...');
      await stopBtn.click();
      await wait(1000);
      await shot(page, '04-stopped');
    }
  } else {
    console.log('[cv-framework] NOT in dropdown ❌');
  }

  // ── Start opencv-tool ──────────────────────────────────────
  const opencvTool = options.find(o => o.value === 'opencv-tool');
  if (opencvTool) {
    console.log('\n[action] selecting opencv-tool...');
    await page.select('.toolSelect', 'opencv-tool');
    await wait(500);
    console.log('[action] clicking Start Tool...');
    await page.click('button:not(.btn-danger)');
    await wait(3000);
    await shot(page, '05-opencv-tool-started');

    const opencvIframe = await page.$('iframe[title="Input"]');
    console.log(`[opencv-iframe] ${opencvIframe ? 'FOUND ✅' : 'NOT FOUND ❌'}`);

    const stopBtn2 = await page.$('.btn-danger');
    if (stopBtn2) {
      await stopBtn2.click();
      await wait(1000);
    }
  } else {
    console.log('[opencv-tool] NOT in dropdown ❌');
  }

  await browser.disconnect();
  console.log('\n✅ Done. Check scripts/*.png for screenshots.');
})();
