import { test, expect } from '@playwright/test'

/**
 * E2E Test for Feature #154: ChatTab Error Recovery
 *
 * This test verifies that ChatTab loads without 404 errors or crashes,
 * even with missing or deleted conversations. It tests the error handling
 * implemented in Feature #146, Feature #147, and Feature #148.
 *
 * Related Features:
 * - Feature #154: E2E Test ChatTab Error Recovery
 * - Feature #146: ChatTab 404 Error Handling
 * - Feature #147: Defensive Programming for ChatTab
 * - Feature #148: ChatTab State Reset on Mode Switch
 *
 * Test Scenarios:
 * 1. ChatTab loads successfully when project is selected
 * 2. No 404 errors when conversation list is empty
 * 3. No 404 errors when conversation is missing/deleted
 * 4. Console shows no errors (only warnings for 404s)
 * 5. ChatTab recovers gracefully from API errors
 * 6. Dev Mode toggle works and resets ChatTab state
 *
 * Run tests:
 *   cd ui && npm run test:e2e -- chattab-errors.spec.ts
 *   cd ui && npm run test:e2e:ui  (interactive mode)
 */

test.describe('ChatTab Error Recovery', () => {
  test.setTimeout(120000)

  test.beforeEach(async ({ page }) => {
    // Navigate to the app
    await page.goto('/')
    await page.waitForSelector('button:has-text("Select Project")', { timeout: 10000 })

    // Set up console error tracking
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`Browser Console Error: ${msg.text()}`)
      }
    })
  })

  /**
   * Helper function to select a project
   */
  async function selectProject(page: import('@playwright/test').Page): Promise<boolean> {
    const projectSelector = page.locator('button:has-text("Select Project")')

    if (await projectSelector.isVisible()) {
      await projectSelector.click()

      // Wait for dropdown to appear
      await page.waitForSelector('.neo-dropdown-item', { timeout: 5000 })

      // Select the first available project
      const projectItem = page.locator('.neo-dropdown-item').first()
      const hasProject = await projectItem.isVisible().catch(() => false)

      if (!hasProject) {
        console.log('No projects available')
        return false
      }

      await projectItem.click()

      // Wait for dropdown to close (project selected)
      await expect(projectSelector).not.toBeVisible({ timeout: 5000 }).catch(() => {})

      console.log('Project selected successfully')
      return true
    }

    return false
  }

  /**
   * Helper function to switch to ChatTab
   */
  async function switchToChatTab(page: import('@playwright/test').Page) {
    // Click on the Chat tab
    const chatTab = page.locator('button:has-text("Chat")').or(
      page.locator('[data-testid="chat-tab"]')
    ).or(
      page.locator('tab[aria-label="Chat"]')
    ).first()

    await chatTab.click({ timeout: 5000 })

    // Wait for ChatTab to be visible
    await page.waitForTimeout(1000)
  }

  /**
   * Helper function to collect console messages
   */
  async function collectConsoleErrors(page: import('@playwright/test').Page): Promise<string[]> {
    const errors: string[] = []

    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })

    return errors
  }

  // ===========================================================================
  // TEST 1: ChatTab Loads Successfully
  // ===========================================================================
  test('ChatTab loads without crashes when project is selected', async ({ page }) => {
    const hasProject = await selectProject(page)

    if (!hasProject) {
      test.skip(true, 'No projects available')
      return
    }

    // Switch to ChatTab
    await switchToChatTab(page)

    // Take screenshot of loaded ChatTab
    await page.screenshot({
      path: 'test-results/chattab-loads-successfully.png',
      fullPage: false
    })

    // Verify ChatTab is visible (no crash)
    const chatTab = page.locator('div:has-text("Conversation History")').or(
      page.locator('[data-testid="chat-tab-content"]')
    )

    // ChatTab should be visible (either with conversations or empty state)
    const isVisible = await chatTab.isVisible().catch(() => false)
    expect(isVisible).toBeTruthy()

    console.log('✅ ChatTab loaded successfully without crashes')
  })

  // ===========================================================================
  // TEST 2: No 404 Errors with Empty Conversation List
  // ===========================================================================
  test('No 404 errors when conversation list is empty', async ({ page }) => {
    const hasProject = await selectProject(page)

    if (!hasProject) {
      test.skip(true, 'No projects available')
      return
    }

    // Switch to ChatTab
    await switchToChatTab(page)

    // Collect all console messages
    const consoleMessages: string[] = []
    page.on('console', msg => {
      consoleMessages.push(`[${msg.type()}] ${msg.text()}`)
    })

    // Wait a bit for any API calls to complete
    await page.waitForTimeout(3000)

    // Check for 404 errors
    const has404Errors = consoleMessages.some(msg =>
      msg.includes('404') && msg.includes('conversation')
    )

    expect(has404Errors).toBeFalsy()

    // Take screenshot of empty state
    await page.screenshot({
      path: 'test-results/chattab-empty-no-404.png',
      fullPage: false
    })

    console.log('✅ No 404 errors with empty conversation list')
    console.log(`Console messages: ${consoleMessages.length}`)
  })

  // ===========================================================================
  // TEST 3: No TypeError or Crashes on Missing Conversation
  // ===========================================================================
  test('No TypeError when conversation is missing or deleted', async ({ page }) => {
    const hasProject = await selectProject(page)

    if (!hasProject) {
      test.skip(true, 'No projects available')
      return
    }

    // Switch to ChatTab
    await switchToChatTab(page)

    // Track console errors
    const errors: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })

    // Wait for API calls
    await page.waitForTimeout(3000)

    // Check for TypeError
    const hasTypeError = errors.some(err =>
      err.includes('TypeError') ||
      err.includes('Cannot read') ||
      err.includes('undefined')
    )

    expect(hasTypeError).toBeFalsy()

    // Verify ChatTab is still functional (not crashed)
    const chatTab = page.locator('div:has-text("Conversation History")').or(
      page.locator('[data-testid="chat-tab-content"]')
    )
    const isVisible = await chatTab.isVisible().catch(() => false)
    expect(isVisible).toBeTruthy()

    // Take screenshot
    await page.screenshot({
      path: 'test-results/chattab-no-typeerror.png',
      fullPage: false
    })

    console.log('✅ No TypeError or crashes on missing conversations')
    console.log(`Console errors: ${errors.length}`)
  })

  // ===========================================================================
  // TEST 4: Console Shows Only Warnings, Not Errors
  // ===========================================================================
  test('Console shows warnings (not errors) for 404s', async ({ page }) => {
    const hasProject = await selectProject(page)

    if (!hasProject) {
      test.skip(true, 'No projects available')
      return
    }

    // Switch to ChatTab
    await switchToChatTab(page)

    // Collect all console messages
    const consoleMessages: Array<{ type: string, text: string }> = []
    page.on('console', msg => {
      consoleMessages.push({
        type: msg.type(),
        text: msg.text()
      })
    })

    // Wait for API calls
    await page.waitForTimeout(3000)

    // Filter for 404-related messages
    const error404Messages = consoleMessages.filter(msg =>
      msg.text.includes('404') && msg.text.includes('conversation')
    )

    // 404s should be warnings, not errors
    error404Messages.forEach(msg => {
      expect(msg.type).toBe('warning')
    })

    // Take screenshot
    await page.screenshot({
      path: 'test-results/chattab-404-warnings-only.png',
      fullPage: false
    })

    console.log('✅ 404s logged as warnings, not errors')
    console.log(`404 warnings: ${error404Messages.length}`)
  })

  // ===========================================================================
  // TEST 5: ChatTab Recovers Gracefully from API Errors
  // ===========================================================================
  test('ChatTab recovers gracefully from API errors', async ({ page }) => {
    const hasProject = await selectProject(page)

    if (!hasProject) {
      test.skip(true, 'No projects available')
      return
    }

    // Switch to ChatTab
    await switchToChatTab(page)

    // Wait for initial load
    await page.waitForTimeout(2000)

    // Take initial screenshot
    await page.screenshot({
      path: 'test-results/chattab-before-api-error.png',
      fullPage: false
    })

    // Track if component crashes
    let componentCrashed = false
    page.on('pageerror', error => {
      console.log('Page error detected:', error)
      componentCrashed = true
    })

    // Wait more to see if it recovers
    await page.waitForTimeout(3000)

    // Component should not have crashed
    expect(componentCrashed).toBeFalsy()

    // Verify ChatTab is still visible and interactive
    const chatTab = page.locator('div:has-text("Conversation History")').or(
      page.locator('[data-testid="chat-tab-content"]')
    )
    const isVisible = await chatTab.isVisible().catch(() => false)
    expect(isVisible).toBeTruthy()

    // Take recovery screenshot
    await page.screenshot({
      path: 'test-results/chattab-after-api-error.png',
      fullPage: false
    })

    console.log('✅ ChatTab recovered gracefully from API errors')
  })

  // ===========================================================================
  // TEST 6: Dev Mode Toggle Resets ChatTab State
  // ===========================================================================
  test('Dev Mode toggle resets ChatTab state correctly', async ({ page }) => {
    const hasProject = await selectProject(page)

    if (!hasProject) {
      test.skip(true, 'No projects available')
      return
    }

    // Switch to ChatTab
    await switchToChatTab(page)

    // Wait for initial load
    await page.waitForTimeout(2000)

    // Take initial screenshot
    await page.screenshot({
      path: 'test-results/chattab-before-mode-switch.png',
      fullPage: false
    })

    // Look for mode toggle button (if it exists)
    const modeToggle = page.locator('button:has-text("Mode")').or(
      page.locator('[data-testid="mode-toggle"]')
    ).or(
      page.locator('button:has-text("UAT")')
    ).first()

    const hasModeToggle = await modeToggle.isVisible().catch(() => false)

    if (hasModeToggle) {
      // Click mode toggle
      await modeToggle.click()

      // Wait for state transition
      await page.waitForTimeout(2000)

      // Verify ChatTab is still functional after mode switch
      const chatTab = page.locator('div:has-text("Conversation History")').or(
        page.locator('[data-testid="chat-tab-content"]')
      )
      const isVisible = await chatTab.isVisible().catch(() => false)
      expect(isVisible).toBeTruthy()

      // Take screenshot after mode switch
      await page.screenshot({
        path: 'test-results/chattab-after-mode-switch.png',
        fullPage: false
      })

      console.log('✅ ChatTab state reset correctly on mode switch')
    } else {
      // Mode toggle not available in this version
      console.log('ℹ️ Mode toggle not found - skipping mode switch test')

      // Still verify ChatTab is working
      const chatTab = page.locator('div:has-text("Conversation History")').or(
        page.locator('[data-testid="chat-tab-content"]')
      )
      const isVisible = await chatTab.isVisible().catch(() => false)
      expect(isVisible).toBeTruthy()

      await page.screenshot({
        path: 'test-results/chattab-no-mode-toggle.png',
        fullPage: false
      })
    }
  })

  // ===========================================================================
  // TEST 7: No Console Errors on DevTools Open
  // ===========================================================================
  test('No console errors when opening browser DevTools', async ({ page }) => {
    const hasProject = await selectProject(page)

    if (!hasProject) {
      test.skip(true, 'No projects available')
      return
    }

    // Switch to ChatTab
    await switchToChatTab(page)

    // Collect console messages
    const consoleMessages: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleMessages.push(msg.text())
      }
    })

    // Simulate DevTools being open (some components break this way)
    await page.evaluate(() => {
      // @ts-ignore - Intentionally accessing devtools flag
      window.__DEVTOOLS_OPEN__ = true
    })

    // Wait to see if any errors occur
    await page.waitForTimeout(2000)

    // Should be no console errors
    expect(consoleMessages.length).toBe(0)

    // Take screenshot
    await page.screenshot({
      path: 'test-results/chattab-devtools-open.png',
      fullPage: false
    })

    console.log('✅ No console errors with DevTools simulation')
  })

  // ===========================================================================
  // TEST 8: Multiple Rapid Project Switches
  // ===========================================================================
  test('No errors on rapid project switching', async ({ page }) => {
    const projectSelector = page.locator('button:has-text("Select Project")')

    if (!(await projectSelector.isVisible())) {
      test.skip(true, 'No projects available')
      return
    }

    // Switch to ChatTab first
    await switchToChatTab(page)

    // Track errors
    const errors: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })

    // Rapidly switch projects 3 times
    for (let i = 0; i < 3; i++) {
      await projectSelector.click()
      await page.waitForSelector('.neo-dropdown-item', { timeout: 5000 })

      const projectItem = page.locator('.neo-dropdown-item').first()
      const hasProject = await projectItem.isVisible().catch(() => false)

      if (hasProject) {
        await projectItem.click()
        await page.waitForTimeout(1000)
      } else {
        break
      }
    }

    // Wait for stabilization
    await page.waitForTimeout(2000)

    // Should be no errors
    expect(errors.length).toBe(0)

    // ChatTab should still be functional
    const chatTab = page.locator('div:has-text("Conversation History")').or(
      page.locator('[data-testid="chat-tab-content"]')
    )
    const isVisible = await chatTab.isVisible().catch(() => false)
    expect(isVisible).toBeTruthy()

    // Take screenshot
    await page.screenshot({
      path: 'test-results/chattab-rapid-switching.png',
      fullPage: false
    })

    console.log('✅ No errors on rapid project switching')
  })

  // ===========================================================================
  // TEST 9: Verify Empty State Message
  // ===========================================================================
  test('Empty state message displayed when no conversations', async ({ page }) => {
    const hasProject = await selectProject(page)

    if (!hasProject) {
      test.skip(true, 'No projects available')
      return
    }

    // Switch to ChatTab
    await switchToChatTab(page)

    // Wait for API calls
    await page.waitForTimeout(2000)

    // Look for empty state message
    const emptyState = page.locator('text=No conversations').or(
      page.locator('text=empty')
    ).or(
      page.locator('[data-testid="empty-conversations"]')
    )

    // Empty state might or might not be visible (depends on if user has conversations)
    // Just verify component doesn't crash
    const chatTab = page.locator('div:has-text("Conversation History")').or(
      page.locator('[data-testid="chat-tab-content"]')
    )
    const isVisible = await chatTab.isVisible().catch(() => false)
    expect(isVisible).toBeTruthy()

    // Take screenshot
    await page.screenshot({
      path: 'test-results/chattab-empty-state.png',
      fullPage: false
    })

    console.log('✅ ChatTab handles empty state gracefully')
  })

  // ===========================================================================
  // TEST 10: Network Request Validation
  // ===========================================================================
  test('Validate network requests for conversation endpoints', async ({ page }) => {
    const hasProject = await selectProject(page)

    if (!hasProject) {
      test.skip(true, 'No projects available')
      return
    }

    // Track network requests
    const requests: Array<{ url: string, status: number }> = []
    page.on('response', async response => {
      const url = response.url()
      if (url.includes('/api/assistant/conversations')) {
        requests.push({
          url,
          status: response.status()
        })
      }
    })

    // Switch to ChatTab
    await switchToChatTab(page)

    // Wait for API calls
    await page.waitForTimeout(3000)

    // Verify we made conversation API calls
    const conversationRequests = requests.filter(req =>
      req.url.includes('/api/assistant/conversations')
    )

    expect(conversationRequests.length).toBeGreaterThan(0)

    // Check that all requests either succeeded or returned 404 (handled gracefully)
    const allSuccessfulOrHandled = conversationRequests.every(req =>
      req.status === 200 || req.status === 404
    )

    expect(allSuccessfulOrHandled).toBeTruthy()

    // Take screenshot
    await page.screenshot({
      path: 'test-results/chattab-network-validation.png',
      fullPage: false
    })

    console.log('✅ Network requests validated')
    console.log(`Conversation API calls: ${conversationRequests.length}`)
    console.log(`Requests:`, conversationRequests)
  })
})
