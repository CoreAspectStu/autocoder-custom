const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('http://localhost:8888');
  await page.waitForTimeout(3000);

  // Get all buttons
  const buttons = await page.locator('button').allTextContents();
  console.log('Button text contents:');
  for (const text of buttons) {
    if (text.trim()) console.log(`  - "${text.trim()}"`);
  }

  await browser.close();
})();
