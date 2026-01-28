import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for testing production server on port 8888
 * This does NOT start a dev server - assumes server is already running
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // Run sequentially for stability
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:8888',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // No webServer - we test against running production server
})
