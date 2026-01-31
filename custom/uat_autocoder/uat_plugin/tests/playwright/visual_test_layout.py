"""
Visual Test: Layout Verification

Tests visual layout and takes screenshots.
"""

from playwright.sync_api import Page, expect
import time

def test_visual_layout_verification(page: Page):
    """Test visual layout of example.com"""
    start_time = time.time()

    # Navigate to page
    page.goto("https://example.com")

    # Wait for page to stabilize
    page.wait_for_load_state("networkidle")

    # Take full page screenshot
    page.screenshot(path="visual_test_full_page.png", full_page=True)

    # Take viewport screenshot
    page.screenshot(path="visual_test_viewport.png")

    # Verify main heading is visible and styled
    h1 = page.locator("h1")
    expect(h1).to_be_visible()
    expect(h1).to_have_css("display", "block")

    # Verify paragraph is visible
    p = page.locator("p")
    expect(p).to_be_visible()

    # Verify link is visible
    a = page.locator("a")
    expect(a).to_be_visible()
    expect(a).to_have_attribute("href", "https://www.iana.org/domains/example")

    duration = time.time() - start_time
    print(f"Visual test completed in {duration:.2f}s")

    return {
        "status": "passed",
        "duration": duration,
        "screenshots": [
            "visual_test_full_page.png",
            "visual_test_viewport.png"
        ]
    }
