const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://localhost:8888');
  await page.waitForTimeout(3000);

  // Select the "default" project (or first available)
  try {
    await page.selectOption('#project-selector', 'default');
    console.log('Selected default project');
    await page.waitForTimeout(2000);
  } catch (e) {
    console.log('Could not select project:', e.message);
  }

  // Check for mode indicators
  const modeBadge = await page.locator('text=/UAT Mode|Dev Mode/').count();
  console.log(`Mode badge found: ${modeBadge > 0 ? 'YES' : 'NO'}`);

  // Get all button titles and text
  const buttons = await page.locator('button').all();
  console.log('\nButtons found:');
  for (const btn of buttons) {
    const title = await btn.getAttribute('title');
    const text = await btn.textContent();
    if (text && text.trim()) {
      console.log(`  - Text: "${text.trim()}" | Title: "${title || 'none'}"`);
    }
  }

  // Check for UAT-specific elements
  const uatModeElements = await page.locator('[data-testid="uat-mode-toggle"]').count();
  console.log(`\nUAT Mode toggle element: ${uatModeElements > 0 ? 'FOUND' : 'NOT FOUND'}`);

  await browser.close();
})();
