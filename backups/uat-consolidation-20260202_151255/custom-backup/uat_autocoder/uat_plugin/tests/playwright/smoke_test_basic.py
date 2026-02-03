"""
Smoke Test: Basic Page Load

A simple smoke test that verifies a page loads successfully.
"""

from playwright.sync_api import Page, expect
import time

def test_smoke_basic_page_load(page: Page):
    """Test that example.com loads successfully"""
    start_time = time.time()

    # Navigate to page
    page.goto("https://example.com")

    # Verify title
    expect(page).to_have_title("Example Domain")

    # Verify h1 exists
    h1 = page.locator("h1")
    expect(h1).to_have_text("Example Domain")

    duration = time.time() - start_time
    print(f"Smoke test completed in {duration:.2f}s")

    return {
        "status": "passed",
        "duration": duration,
        "screenshot": "smoke_test_screenshot.png"
    }
