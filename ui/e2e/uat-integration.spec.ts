import { test, expect } from '@playwright/test';

test.describe('UAT Gateway UI Integration', () => {
  // Use the production server on port 8888
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:8888');
    await page.waitForLoadState('domcontentloaded');

    // Step 1: Select a project
    const projectButton = page.getByRole('button', { name: /select project/i });
    await projectButton.click();
    await page.waitForTimeout(500);

    // Click on the first project button
    const projectButtons = page.locator('button').filter({ hasText: /\d+\/\d+/ });
    const count = await projectButtons.count();

    if (count > 0) {
      await projectButtons.first().click();
    }

    await page.waitForTimeout(2000);

    // Step 2: Enable DevLayer mode (required for Pipeline Dashboard)
    const devLayerButton = page.getByRole('button', { name: /toggle devlayer|devlayer/i }).first();
    const devLayerCount = await devLayerButton.count();

    if (devLayerCount > 0) {
      await devLayerButton.click();
      await page.waitForTimeout(1000);
    }

    // Step 3: Switch to Pipeline Dashboard view
    const dashboardButton = page.getByRole('button', { name: /pipeline dashboard/i });
    const dashboardCount = await dashboardButton.count();

    if (dashboardCount > 0) {
      await dashboardButton.click();
    }

    // Wait for Pipeline Dashboard to load
    await page.waitForTimeout(2000);
  });

  test('should load the AutoCoder UI', async ({ page }) => {
    // Page should load without errors
    await expect(page).toHaveTitle(/AutoCoder/i);
  });

  test('should display UAT button in Pipeline Dashboard', async ({ page }) => {
    // Look for the "Run UAT Tests" button - it's in the PipelineDashboard component
    const uatButton = page.locator('button').filter({ hasText: /run uat tests/i }).first();

    // Button should exist and be visible
    await expect(uatButton).toBeVisible({ timeout: 15000 });
  });

  test('should open UAT modal when button clicked', async ({ page }) => {
    // Find and click the UAT button
    const uatButton = page.locator('button').filter({ hasText: /run uat tests/i }).first();
    await uatButton.click();

    // Modal should appear
    const modal = page.locator('[class*="modal"], [role="dialog"], [class*="Modal"]').first();
    await expect(modal).toBeVisible({ timeout: 5000 });
  });

  test('should display test options in modal', async ({ page }) => {
    // Open UAT modal
    const uatButton = page.locator('button').filter({ hasText: /run uat tests/i }).first();
    await uatButton.click();
    await page.waitForTimeout(500);

    // Check for preset tests - use locator() to avoid strict mode violations
    await expect(page.locator('button').filter({ hasText: 'Smoke Test' }).first()).toBeVisible();
    await expect(page.locator('button').filter({ hasText: 'Regression Test' }).first()).toBeVisible();
  });

  test('should show UAT status in dashboard', async ({ page }) => {
    // Look for UAT Pass Rate section
    const uatSection = page.getByText('UAT Pass Rate').or(page.getByText('UAT'));
    await expect(uatSection.first()).toBeVisible({ timeout: 15000 });
  });
});

test.describe('UAT API Endpoints', () => {
  // Use API testing without page context
  test('GET /api/uat/test-options should return valid data', async ({ request }) => {
    const response = await request.get('http://localhost:8888/api/uat/test-options');

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data).toHaveProperty('journey_types');
    expect(data).toHaveProperty('scenario_types');
    expect(data).toHaveProperty('preset_tests');
  });

  test('GET /api/uat/status should return status', async ({ request }) => {
    const response = await request.get('http://localhost:8888/api/uat/status/uat-autocoder');

    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data).toHaveProperty('is_running');
  });
});
