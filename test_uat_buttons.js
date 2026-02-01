const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Navigate to the app
  await page.goto('http://localhost:8888');

  // Wait for page to load
  await page.waitForTimeout(2000);

  // Check for mode toggle button
  const modeToggle = await page.locator('button[title="Switch to UAT Mode"]').count();
  console.log(`Mode toggle button found: ${modeToggle > 0 ? 'YES' : 'NO'}`);

  // Check for "Add UAT Test" button with visible text
  const addUATBtn = await page.locator('button').filter({ hasText: 'Add UAT Test' }).count();
  console.log(`Add UAT Test button with text: ${addUATBtn > 0 ? 'FOUND (BAD!)' : 'NOT FOUND (GOOD!)'}`);

  // Check for "Start UAT" button with visible text
  const startUATBtn = await page.locator('button').filter({ hasText: 'Start UAT' }).count();
  console.log(`Start UAT button with text: ${startUATBtn > 0 ? 'FOUND (BAD!)' : 'NOT FOUND (GOOD!)'}`);

  // Count icon buttons
  const iconBtns = await page.locator('button.neo-btn').count();
  console.log(`Total neo buttons: ${iconBtns}`);

  await browser.close();
})();
