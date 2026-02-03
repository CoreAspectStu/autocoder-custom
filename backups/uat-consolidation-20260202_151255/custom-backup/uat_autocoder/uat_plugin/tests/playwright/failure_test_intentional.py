"""
Failure Test: Intentional Failure

Tests error handling and artifact capture on failure.
"""

from playwright.sync_api import Page, expect
import time

def test_failure_intentional_error(page: Page):
    """Test that intentionally fails to verify error handling"""
    start_time = time.time()

    # Navigate to page
    page.goto("https://example.com")

    # Take screenshot before failure
    page.screenshot(path="failure_test_before.png")

    # Intentionally fail - expect wrong title
    try:
        expect(page).to_have_title("This Title Does Not Exist", timeout=5000)
    except Exception as e:
        # Take screenshot after failure
        page.screenshot(path="failure_test_after.png")

        # Return failure details
        duration = time.time() - start_time
        print(f"Failure test completed in {duration:.2f}s")

        return {
            "status": "failed",
            "error": str(e),
            "duration": duration,
            "screenshots": [
                "failure_test_before.png",
                "failure_test_after.png"
            ],
            "error_type": "AssertionError"
        }

    # If we get here, the test passed when it shouldn't have
    return {
        "status": "passed",
        "error": "Test should have failed but didn't"
    }
