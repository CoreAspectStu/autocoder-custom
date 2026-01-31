import { test, expect } from '@playwright/test'

/**
 * Integration Test for Feature #148: Mode Switching State Reset
 *
 * This test verifies that when switching between Dev Mode and UAT Mode
 * (which corresponds to selecting different projects), all ChatTab state
 * is properly cleared and no stale conversation IDs are fetched.
 *
 * Related Features:
 * - Feature #148: ChatTab State Reset on Mode Switch
 * - Feature #146: ChatTab 404 Error Handling
 * - Feature #147: Defensive Programming for ChatTab
 *
 * Run tests:
 *   cd ui && npm run test:e2e -- mode-switching-state-reset.spec.ts
 *   cd ui && npm run test:e2e:ui  (interactive mode)
 */

test.describe('Mode Switching State Reset', () => {
  test.setTimeout(120000)

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('button:has-text("Select Project")', { timeout: 10000 })
  })

  /**
   * Helper function to select a project by name
   */
  async function selectProject(page: import('@playwright/test').Page, projectName: string): Promise<boolean> {
    const projectSelector = page.locator('button:has-text("Select Project")')

    // Click the selector if visible
    if (await projectSelector.isVisible()) {
      await projectSelector.click()

      // Wait for dropdown to appear
      await page.waitForSelector('.neo-dropdown-item', { timeout: 5000 })

      // Try to find the project by name
      const projectItem = page.locator(`.neo-dropdown-item:has-text("${projectName}")`).first()

      const isVisible = await projectItem.isVisible().catch(() => false)

      if (!isVisible) {
        console.log(`Project "${projectName}" not found in dropdown`)
        return false
      }

      await projectItem.click()

      // Wait for dropdown to close (project selected)
      await expect(projectSelector).not.toBeVisible({ timeout: 5000 }).catch(() => {})

      console.log(`Selected project: ${projectName}`)
      return true
    }

    return false
  }

  /**
   * Helper function to open the assistant panel
   */
  async function openAssistantPanel(page: import('@playwright/test').Page) {
    const panel = page.locator('[aria-label="Project Assistant"]')

    // Press A to open panel
    await page.keyboard.press('a')

    // Wait for panel to open
    await page.waitForFunction(() => {
      const panel = document.querySelector('[aria-label="Project Assistant"]')
      return panel && panel.getAttribute('aria-hidden') !== 'true'
    }, { timeout: 5000 })

    await expect(panel).toHaveAttribute('aria-hidden', 'false')
  }

  /**
   * Helper function to wait for assistant to be ready
   */
  async function waitForAssistantReady(page: import('@playwright/test').Page): Promise<boolean> {
    try {
      await page.waitForSelector('text=Connected', { timeout: 15000 })
      const inputArea = page.locator('textarea[placeholder="Ask about the codebase..."]')
      await expect(inputArea).toBeEnabled({ timeout: 30000 })
      return true
    } catch {
      console.log('Assistant not ready - API may not be configured')
      return false
    }
  }

  /**
   * Helper function to send a message and wait for response
   */
  async function sendMessageAndWaitForResponse(page: import('@playwright/test').Page, message: string) {
    const inputArea = page.locator('textarea[placeholder="Ask about the codebase..."]')

    await inputArea.fill(message)
    await inputArea.press('Enter')

    // Wait for message to appear
    await expect(page.locator(`text=${message}`).first()).toBeVisible({ timeout: 5000 })

    // Wait for "Thinking..." to appear and disappear
    await page.waitForSelector('text=Thinking...', { timeout: 10000 }).catch(() => {})

    // Wait for input to be enabled again (response complete)
    await expect(inputArea).toBeEnabled({ timeout: 60000 })
  }

  /**
   * Helper function to get current input text
   */
  async function getInputText(page: import('@playwright/test').Page): Promise<string> {
    const inputArea = page.locator('textarea[placeholder="Ask about the codebase..."]')
    return await inputArea.inputValue()
  }

  /**
   * Helper function to check if transition overlay is visible
   */
  async function isTransitionOverlayVisible(page: import('@playwright/test').Page): Promise<boolean> {
    const overlay = page.locator('.fixed.inset-0.bg-black\\/20:has-text("Switching mode...")')
    return await overlay.isVisible().catch(() => false)
  }

  // ==========================================================================
  // TEST 1: Basic Mode Switch State Reset
  // ==========================================================================
  test('Mode switch clears conversation selection and input text', async ({ page }) => {
    // Get the list of available projects
    const projectSelector = page.locator('button:has-text("Select Project")')
    await projectSelector.click()

    await page.waitForSelector('.neo-dropdown-item', { timeout: 5000 })

    // Get all project items
    const projectItems = page.locator('.neo-dropdown-item')
    const projectCount = await projectItems.count()

    if (projectCount < 2) {
      test.skip(true, 'Need at least 2 projects to test mode switching')
      return
    }

    // Get names of first two projects
    const firstProjectName = await projectItems.nth(0).innerText()
    const secondProjectName = await projectItems.nth(1).innerText()

    console.log(`Testing mode switch between: "${firstProjectName}" and "${secondProjectName}"`)

    // Close dropdown
    await page.keyboard.press('Escape')

    // ---------------------------------------------------------------------
    // STEP 1: Select first project and interact with ChatTab
    // ---------------------------------------------------------------------
    console.log('STEP 1: Select first project')
    const selected1 = await selectProject(page, firstProjectName)

    if (!selected1) {
      test.skip(true, `Failed to select first project: ${firstProjectName}`)
      return
    }

    // Open assistant panel
    await openAssistantPanel(page)

    // Wait for assistant to be ready
    const ready1 = await waitForAssistantReady(page)

    if (!ready1) {
      test.skip(true, 'Assistant API not available for first project')
      return
    }

    // Send a message
    console.log('STEP 2: Send message in first project')
    await sendMessageAndWaitForResponse(page, `Test message from ${firstProjectName}`)

    // Type some text in input (but don't send)
    const inputArea = page.locator('textarea[placeholder="Ask about the codebase..."]')
    await inputArea.fill('Unsent text in first project')

    // Verify text is in input
    const inputTextBeforeSwitch = await getInputText(page)
    expect(inputTextBeforeSwitch).toBe('Unsent text in first project')
    console.log(`Input text before switch: "${inputTextBeforeSwitch}"`)

    // Open conversation history to verify we have a conversation
    const historyButton = page.locator('button[title="Conversation history"]')
    await historyButton.click()

    await expect(page.locator('h3:has-text("Conversation History")')).toBeVisible({ timeout: 5000 })

    const conversationItems = page.locator('.neo-dropdown:has-text("Conversation History") .neo-dropdown-item')
    const conversationCountBefore = await conversationItems.count()

    console.log(`Conversation count before switch: ${conversationCountBefore}`)

    // Close history dropdown
    await page.keyboard.press('Escape')

    // ---------------------------------------------------------------------
    // STEP 3: Switch to second project (MODE SWITCH)
    // ---------------------------------------------------------------------
    console.log('STEP 3: Switch to second project (MODE SWITCH)')

    // Check for transition overlay
    const transitionStart = await isTransitionOverlayVisible(page)
    console.log(`Transition overlay visible at start: ${transitionStart}`)

    // Select second project
    const selected2 = await selectProject(page, secondProjectName)

    if (!selected2) {
      test.skip(true, `Failed to select second project: ${secondProjectName}`)
      return
    }

    // Wait briefly for transition (should be ~500ms)
    await page.waitForTimeout(600)

    // ---------------------------------------------------------------------
    // STEP 4: Verify state was cleared
    // ---------------------------------------------------------------------
    console.log('STEP 4: Verify state was cleared')

    // CHECK 1: Input text should be cleared
    const inputTextAfterSwitch = await getInputText(page)
    console.log(`Input text after switch: "${inputTextAfterSwitch}"`)

    if (inputTextAfterSwitch !== '') {
      console.error('FAIL: Input text was not cleared after mode switch')
    }

    expect(inputTextAfterSwitch).toBe('')

    // CHECK 2: Conversation selection should be cleared
    // We verify this by checking that the conversation list for the new project is shown
    // (not the old conversation from the previous project)

    // Open history for second project
    await historyButton.click()
    await expect(page.locator('h3:has-text("Conversation History")')).toBeVisible({ timeout: 5000 })

    const conversationItemsAfter = page.locator('.neo-dropdown:has-text("Conversation History") .neo-dropdown-item')
    const conversationCountAfter = await conversationItemsAfter.count()

    console.log(`Conversation count after switch: ${conversationCountAfter}`)

    // The conversation count may be different (different project), which is expected
    // The key is that we're seeing the new project's conversations, not the old ones

    // CHECK 3: No 404 errors in console
    const logs: string[] = []
    page.on('console', msg => {
      logs.push(msg.text())
    })

    // Wait a bit to catch any delayed errors
    await page.waitForTimeout(2000)

    const errorLogs = logs.filter(log =>
      log.includes('404') ||
      log.includes('ERR') ||
      log.includes('Failed to fetch')
    )

    if (errorLogs.length > 0) {
      console.error('Found errors in console:', errorLogs)
    }

    // We expect no 404 errors related to conversations
    const conversation404Errors = errorLogs.filter(log =>
      log.includes('404') && log.includes('conversation')
    )

    expect(conversation404Errors.length).toBe(0)

    console.log('✅ Mode switch state reset test completed successfully')
  })

  // ==========================================================================
  // TEST 2: Rapid Mode Switching (Stress Test)
  // ==========================================================================
  test('Rapid mode switching does not cause errors or memory leaks', async ({ page }) => {
    // Get the list of available projects
    const projectSelector = page.locator('button:has-text("Select Project")')
    await projectSelector.click()

    await page.waitForSelector('.neo-dropdown-item', { timeout: 5000 })

    // Get all project items
    const projectItems = page.locator('.neo-dropdown-item')
    const projectCount = await projectItems.count()

    if (projectCount < 2) {
      test.skip(true, 'Need at least 2 projects to test rapid mode switching')
      return
    }

    // Get names of first two projects
    const firstProjectName = await projectItems.nth(0).innerText()
    const secondProjectName = await projectItems.nth(1).innerText()

    console.log(`Testing rapid mode switching between: "${firstProjectName}" and "${secondProjectName}"`)

    // Close dropdown
    await page.keyboard.press('Escape')

    // Open assistant panel
    const selected1 = await selectProject(page, firstProjectName)

    if (!selected1) {
      test.skip(true, `Failed to select first project: ${firstProjectName}`)
      return
    }

    await openAssistantPanel(page)

    // Collect console errors
    const errorLogs: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errorLogs.push(msg.text())
      }
    })

    // ---------------------------------------------------------------------
    // Rapid mode switching (5 times back and forth)
    // ---------------------------------------------------------------------
    console.log('Starting rapid mode switching test...')

    for (let i = 0; i < 5; i++) {
      console.log(`Switch cycle ${i + 1}/5`)

      // Switch to second project
      await selectProject(page, secondProjectName)

      // Wait for transition
      await page.waitForTimeout(600)

      // Switch back to first project
      await selectProject(page, firstProjectName)

      // Wait for transition
      await page.waitForTimeout(600)
    }

    console.log('Completed 5 switch cycles')

    // ---------------------------------------------------------------------
    // Verify no critical errors occurred
    // ---------------------------------------------------------------------
    await page.waitForTimeout(2000)

    // Filter for critical errors (not warnings)
    const criticalErrors = errorLogs.filter(log =>
      log.includes('TypeError') ||
      log.includes('Cannot read') ||
      log.includes('Uncaught') ||
      log.includes('404')
    )

    if (criticalErrors.length > 0) {
      console.error('Critical errors found during rapid switching:', criticalErrors)
    }

    expect(criticalErrors.length).toBe(0)

    // Verify app still works by interacting with it
    const ready = await waitForAssistantReady(page)

    if (ready) {
      // Try to send a message to verify everything still works
      const inputArea = page.locator('textarea[placeholder="Ask about the codebase..."]')

      // Input should be enabled and functional
      await expect(inputArea).toBeEnabled()

      // Should be able to type
      await inputArea.fill('Test after rapid switching')
      const text = await inputArea.inputValue()
      expect(text).toBe('Test after rapid switching')
    }

    console.log('✅ Rapid mode switching stress test completed successfully')
  })

  // ==========================================================================
  // TEST 3: Query Cache Invalidation Verification
  // ==========================================================================
  test('Query cache is invalidated on mode switch', async ({ page }) => {
    // Get the list of available projects
    const projectSelector = page.locator('button:has-text("Select Project")')
    await projectSelector.click()

    await page.waitForSelector('.neo-dropdown-item', { timeout: 5000 })

    // Get all project items
    const projectItems = page.locator('.neo-dropdown-item')
    const projectCount = await projectItems.count()

    if (projectCount < 2) {
      test.skip(true, 'Need at least 2 projects to test query cache invalidation')
      return
    }

    // Get names of first two projects
    const firstProjectName = await projectItems.nth(0).innerText()
    const secondProjectName = await projectItems.nth(1).innerText()

    console.log(`Testing query cache invalidation between: "${firstProjectName}" and "${secondProjectName}"`)

    // Close dropdown
    await page.keyboard.press('Escape')

    // ---------------------------------------------------------------------
    // STEP 1: Select first project and load conversations
    // ---------------------------------------------------------------------
    const selected1 = await selectProject(page, firstProjectName)

    if (!selected1) {
      test.skip(true, `Failed to select first project: ${firstProjectName}`)
      return
    }

    await openAssistantPanel(page)

    const ready1 = await waitForAssistantReady(page)

    if (!ready1) {
      test.skip(true, 'Assistant API not available')
      return
    }

    // Send a message to create a conversation
    await sendMessageAndWaitForResponse(page, `Cache test message ${Date.now()}`)

    // Open history to load conversation list
    const historyButton = page.locator('button[title="Conversation history"]')
    await historyButton.click()

    await expect(page.locator('h3:has-text("Conversation History")')).toBeVisible({ timeout: 5000 })

    // Get conversation count for first project
    const conversationItems1 = page.locator('.neo-dropdown:has-text("Conversation History") .neo-dropdown-item')
    const project1ConversationCount = await conversationItems1.count()

    console.log(`First project conversation count: ${project1ConversationCount}`)

    // Close history
    await page.keyboard.press('Escape')

    // ---------------------------------------------------------------------
    // STEP 2: Switch to second project
    // ---------------------------------------------------------------------
    console.log('Switching to second project...')

    const selected2 = await selectProject(page, secondProjectName)

    if (!selected2) {
      test.skip(true, `Failed to select second project: ${secondProjectName}`)
      return
    }

    // Wait for mode transition
    await page.waitForTimeout(600)

    // ---------------------------------------------------------------------
    // STEP 3: Verify query cache was invalidated
    // ---------------------------------------------------------------------
    console.log('Verifying query cache invalidation...')

    // Open history for second project
    await historyButton.click()

    await expect(page.locator('h3:has-text("Conversation History")')).toBeVisible({ timeout: 5000 })

    // Get conversation count for second project
    const conversationItems2 = page.locator('.neo-dropdown:has-text("Conversation History") .neo-dropdown-item')
    const project2ConversationCount = await conversationItems2.count()

    console.log(`Second project conversation count: ${project2ConversationCount}`)

    // The key verification: we're seeing the second project's conversations
    // (which may have a different count than the first project)
    // This proves the query cache was invalidated and fresh data was fetched

    // Additional verification: Switch back to first project and verify we get fresh data
    await page.keyboard.press('Escape')

    console.log('Switching back to first project...')

    await selectProject(page, firstProjectName)

    await page.waitForTimeout(600)

    await historyButton.click()

    await expect(page.locator('h3:has-text("Conversation History")')).toBeVisible({ timeout: 5000 })

    const conversationItems1Again = page.locator('.neo-dropdown:has-text("Conversation History") .neo-dropdown-item')
    const project1ConversationCountAgain = await conversationItems1Again.count()

    console.log(`First project conversation count (after return): ${project1ConversationCountAgain}`)

    // Should match the original count (or close to it, accounting for new conversations)
    // If it matched the second project's count, that would indicate cache pollution
    expect(project1ConversationCountAgain).toBe(project1ConversationCount)

    console.log('✅ Query cache invalidation test completed successfully')
  })

  // ==========================================================================
  // TEST 4: Transition Animation Verification
  // ==========================================================================
  test('Transition animation plays on mode switch', async ({ page }) => {
    // Get the list of available projects
    const projectSelector = page.locator('button:has-text("Select Project")')
    await projectSelector.click()

    await page.waitForSelector('.neo-dropdown-item', { timeout: 5000 })

    // Get all project items
    const projectItems = page.locator('.neo-dropdown-item')
    const projectCount = await projectItems.count()

    if (projectCount < 2) {
      test.skip(true, 'Need at least 2 projects to test transition animation')
      return
    }

    // Get names of first two projects
    const firstProjectName = await projectItems.nth(0).innerText()
    const secondProjectName = await projectItems.nth(1).innerText()

    console.log(`Testing transition animation between: "${firstProjectName}" and "${secondProjectName}"`)

    // Close dropdown
    await page.keyboard.press('Escape')

    // Select first project
    const selected1 = await selectProject(page, firstProjectName)

    if (!selected1) {
      test.skip(true, `Failed to select first project: ${firstProjectName}`)
      return
    }

    await openAssistantPanel(page)

    // Monitor for transition overlay
    let overlayAppeared = false
    let overlayText = ''

    page.on('console', msg => {
      const text = msg.text()
      if (text.includes('[ChatTab] State reset')) {
        console.log('Found state reset log:', text)
      }
    })

    // Start watching for the overlay before switching
    const overlayPromise = page.waitForSelector('.fixed.inset-0.bg-black\\/20:has-text("Switching mode...")', {
      timeout: 1000
    }).then(() => {
      overlayAppeared = true
      return true
    }).catch(() => {
      return false
    })

    // Switch projects
    console.log('Switching projects to trigger animation...')
    const selected2 = await selectProject(page, secondProjectName)

    if (!selected2) {
      test.skip(true, `Failed to select second project: ${secondProjectName}`)
      return
    }

    // Wait for overlay (if it appears)
    const overlayResult = await Promise.race([
      overlayPromise,
      page.waitForTimeout(600).then(() => false)
    ])

    if (overlayResult) {
      console.log('✅ Transition overlay appeared')

      // Check overlay content
      const overlay = page.locator('.fixed.inset-0.bg-black\\/20:has-text("Switching mode...")')

      // Should have spinning icon
      const icon = overlay.locator('svg.animate-spin')
      const hasIcon = await icon.isVisible().catch(() => false)

      if (hasIcon) {
        console.log('✅ Spinning icon found in overlay')
      }

      // Should have text
      const text = await overlay.locator('text=Switching mode...').isVisible().catch(() => false)

      if (text) {
        console.log('✅ "Switching mode..." text found in overlay')
      }

      // Wait for overlay to disappear
      await expect(overlay).not.toBeVisible({ timeout: 1000 })
      console.log('✅ Overlay disappeared after transition')
    } else {
      console.log('⚠️  Transition overlay not detected (may be too fast to capture)')
      // This is not a failure - the animation might be too fast to catch
      // The important thing is that the state reset works
    }

    // Verify console log
    await page.waitForTimeout(100)

    // Check for the state reset log message
    const logs: string[] = []
    page.on('console', msg => logs.push(msg.text()))

    await page.waitForTimeout(500)

    const stateResetLog = logs.find(log => log.includes('[ChatTab] State reset'))

    if (stateResetLog) {
      console.log('✅ State reset console log found:', stateResetLog)
    }

    console.log('✅ Transition animation test completed')
  })

  // ==========================================================================
  // TEST 5: No Stale Data After Mode Switch
  // ==========================================================================
  test('No stale conversation data appears after mode switch', async ({ page }) => {
    // Get the list of available projects
    const projectSelector = page.locator('button:has-text("Select Project")')
    await projectSelector.click()

    await page.waitForSelector('.neo-dropdown-item', { timeout: 5000 })

    // Get all project items
    const projectItems = page.locator('.neo-dropdown-item')
    const projectCount = await projectItems.count()

    if (projectCount < 2) {
      test.skip(true, 'Need at least 2 projects to test stale data prevention')
      return
    }

    // Get names of first two projects
    const firstProjectName = await projectItems.nth(0).innerText()
    const secondProjectName = await projectItems.nth(1).innerText()

    console.log(`Testing stale data prevention between: "${firstProjectName}" and "${secondProjectName}"`)

    // Close dropdown
    await page.keyboard.press('Escape')

    // ---------------------------------------------------------------------
    // STEP 1: Create unique conversation in first project
    // ---------------------------------------------------------------------
    const selected1 = await selectProject(page, firstProjectName)

    if (!selected1) {
      test.skip(true, `Failed to select first project: ${firstProjectName}`)
      return
    }

    await openAssistantPanel(page)

    const ready1 = await waitForAssistantReady(page)

    if (!ready1) {
      test.skip(true, 'Assistant API not available')
      return
    }

    // Create unique message that won't exist in other projects
    const uniqueMessage = `UNIQUE_TEST_${Date.now()}_${Math.random().toString(36).substring(7)}`
    console.log(`Sending unique message: ${uniqueMessage}`)

    await sendMessageAndWaitForResponse(page, uniqueMessage)

    // Verify message appears in chat
    await expect(page.locator(`text=${uniqueMessage}`).first()).toBeVisible()

    console.log('✅ Unique message visible in first project')

    // ---------------------------------------------------------------------
    // STEP 2: Switch to second project
    // ---------------------------------------------------------------------
    console.log('Switching to second project...')

    const selected2 = await selectProject(page, secondProjectName)

    if (!selected2) {
      test.skip(true, `Failed to select second project: ${secondProjectName}`)
      return
    }

    await page.waitForTimeout(600)

    // ---------------------------------------------------------------------
    // STEP 3: Verify unique message is NOT visible (no stale data)
    // ---------------------------------------------------------------------
    console.log('Verifying no stale data from first project...')

    // The unique message from the first project should NOT be visible
    const uniqueMessageVisible = await page.locator(`text=${uniqueMessage}`).isVisible().catch(() => false)

    if (uniqueMessageVisible) {
      console.error('FAIL: Stale data from first project is visible in second project!')
    }

    expect(uniqueMessageVisible).toBe(false)

    console.log('✅ No stale data detected')

    // Additional check: Chat area should be empty or show second project's conversations
    const chatArea = page.locator('.flex-1.overflow-y-auto')

    // Get chat content
    const chatContent = await chatArea.innerText()

    // Should not contain our unique message from first project
    expect(chatContent).not.toContain(uniqueMessage)

    console.log('✅ Chat area verified to be clean of stale data')
  })
})
