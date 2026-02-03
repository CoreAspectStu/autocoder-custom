"""
Functional Test: Form Interaction

Tests form filling and submission behavior.
"""

from playwright.sync_api import Page, expect
import time

def test_functional_form_interaction(page: Page):
    """Test form interaction on a demo site"""
    start_time = time.time()

    # Navigate to a form demo page
    page.goto("https://www.lambdatest.com/selenium-playground/simple-form-demo")

    # Fill in the form
    page.fill("input[name='value1']", "10")
    page.fill("input[name='value2']", "5")

    # Click the Get Total button
    page.click("button[id='button1']")

    # Wait for result
    page.wait_for_selector("#result", state="visible")

    # Verify result
    result = page.locator("#result")
    expect(result).to_be_visible()

    duration = time.time() - start_time
    print(f"Functional test completed in {duration:.2f}s")

    return {
        "status": "passed",
        "duration": duration,
        "form_values": {"value1": "10", "value2": "5"}
    }
