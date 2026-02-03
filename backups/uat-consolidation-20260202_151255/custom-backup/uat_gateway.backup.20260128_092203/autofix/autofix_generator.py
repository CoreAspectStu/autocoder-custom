"""
Auto-Fix Generator - Generate actionable fix suggestions for test failures

This module is responsible for:
- Analyzing test failures
- Generating fix suggestions with code examples
- Providing explanations for why fixes work
- Ranking suggestions by likelihood of success

Phase 4 Advanced Feature: Auto-fix resolves 60% of selector failures
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from custom.uat_gateway.utils.logger import get_logger


# ============================================================================
# Data Models
# ============================================================================

class FixType(Enum):
    """Types of fixes that can be suggested"""
    SELECTOR_FIX = "selector_fix"
    WAIT_FIX = "wait_fix"
    ASSERTION_FIX = "assertion_fix"
    NETWORK_FIX = "network_fix"
    VISUAL_FIX = "visual_fix"
    A11Y_FIX = "a11y_fix"
    CODE_PATTERN_FIX = "code_pattern_fix"


class Confidence(Enum):
    """Confidence level in the fix suggestion"""
    HIGH = "high"  # Very likely to work
    MEDIUM = "medium"  # Might work
    LOW = "low"  # Worth trying but less certain


@dataclass
class FixSuggestion:
    """
    Represents a fix suggestion for a test failure

    Attributes:
        fix_type: Type of fix being suggested
        title: Short title describing the fix
        description: Detailed explanation of the problem and solution
        code_example: Code showing how to implement the fix (before/after)
        confidence: How likely this fix is to work
        estimated_effort: Estimated time to apply fix (in minutes)
        references: Links to documentation or related issues
        tags: Additional metadata tags
    """
    fix_type: FixType
    title: str
    description: str
    code_example: str  # Before/after code examples
    confidence: Confidence
    estimated_effort: int  # Minutes
    references: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "fix_type": self.fix_type.value,
            "title": self.title,
            "description": self.description,
            "code_example": self.code_example,
            "confidence": self.confidence.value,
            "estimated_effort_minutes": self.estimated_effort,
            "references": self.references,
            "tags": self.tags
        }


@dataclass
class FixAnalysis:
    """
    Complete analysis and fix suggestions for a test failure

    Attributes:
        test_name: Name of the failing test
        failure_type: Type of failure (selector_not_found, timeout, etc.)
        error_message: The actual error message
        root_cause: Analysis of why the failure occurred
        suggestions: List of fix suggestions ordered by likelihood
        recommended_action: Best suggestion to try first
    """
    test_name: str
    failure_type: str
    error_message: str
    root_cause: str
    suggestions: List[FixSuggestion] = field(default_factory=list)
    recommended_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "failure_type": self.failure_type,
            "error_message": self.error_message,
            "root_cause": self.root_cause,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "recommended_action": self.recommended_action
        }


# ============================================================================
# Auto-Fix Generator
# ============================================================================

class AutoFixGenerator:
    """
    Generates actionable fix suggestions for test failures

    This is the main class for Feature #180: "Auto-fix generates fix suggestions"

    It analyzes test failures and provides:
    1. Clear explanations of what went wrong
    2. Before/after code examples showing the fix
    3. Confidence ratings for each suggestion
    4. Estimated effort to apply fixes
    5. References to documentation
    """

    def __init__(self):
        """Initialize the auto-fix generator"""
        self.logger = get_logger(__name__)

        # Predefined fix patterns for common failures
        self._init_fix_patterns()

    def _init_fix_patterns(self):
        """Initialize fix patterns for common failure types"""
        self.selector_fixes = {
            "class_selector": {
                "pattern": r'\.[\w-]+',
                "title": "Use more stable selector strategy",
                "description": "CSS class selectors are fragile because classes can change with styling updates. Use data-testid or aria attributes instead.",
                "code_before": "await page.click('.submit-button');",
                "code_after": """// Add data-testid to your element:
// <button data-testid="submit-button">Submit</button>

await page.click('[data-testid="submit-button"]');""",
                "confidence": Confidence.HIGH,
                "effort": 5
            },
            "id_selector": {
                "pattern": r'#[\w-]+',
                "title": "Verify ID selector exists and is unique",
                "description": "ID selectors are specific but can fail if the ID is dynamically generated or not present in DOM.",
                "code_before": "await page.click('#login-btn');",
                "code_after": """// Wait for element to be present first
await page.waitForSelector('#login-btn', { state: 'attached' });
await page.click('#login-btn');

// Or use a more robust selector:
await page.click('button[type="submit"]');""",
                "confidence": Confidence.MEDIUM,
                "effort": 3
            },
            "text_selector": {
                "pattern": r'text=.*',
                "title": "Text-based selector may fail with i18n or content changes",
                "description": "Text selectors break when content changes or with internationalization. Use semantic attributes instead.",
                "code_before": "await page.click(text='Submit');",
                "code_after": """// Use data-testid or aria attributes:
// <button aria-label="Submit form">Submit</button>

await page.click('[aria-label="Submit form"]');

// Or:
await page.click('button:has-text("Submit")");""",
                "confidence": Confidence.HIGH,
                "effort": 5
            }
        }

        self.wait_fixes = {
            "timeout_not_found": {
                "title": "Increase timeout or add explicit wait",
                "description": "Element didn't appear within default timeout. Add explicit wait for the element to be present/visible.",
                "code_before": """await page.click('.slow-button');""",
                "code_after": """// Wait for element to be ready
await page.waitForSelector('.slow-button', {
    state: 'visible',  // or 'attached', 'hidden'
    timeout: 30000  // Increase timeout if needed
});
await page.click('.slow-button');

// Better: Wait for specific condition
await page.waitForFunction(() => {
    const btn = document.querySelector('.slow-button');
    return btn && !btn.disabled;
});
await page.click('.slow-button');""",
                "confidence": Confidence.HIGH,
                "effort": 5
            },
            "race_condition": {
                "title": "Handle asynchronous state changes",
                "description": "Test is running before the application is ready. Add proper waits for network responses or state updates.",
                "code_before": """await page.click('.load-data');
await page.click('.process-button');  // Fails: data not loaded yet""",
                "code_after": """// Wait for network response
await page.click('.load-data');
await page.waitForResponse(resp =>
    resp.url().includes('/api/data') && resp.status() === 200
);
await page.click('.process-button');

// Or wait for UI update
await page.click('.load-data');
await page.waitForSelector('.data-loaded', { state: 'visible' });
await page.click('.process-button');""",
                "confidence": Confidence.HIGH,
                "effort": 10
            }
        }

        self.assertion_fixes = {
            "text_mismatch": {
                "title": "Handle dynamic or whitespace variations in text",
                "description": "Text assertions can fail due to extra whitespace, timing, or dynamic content. Use more flexible matching.",
                "code_before": """const text = await page.textContent('.message');
expect(text).toBe('Success');  // Fails: actual is "Success " or "Success!" """,
                "code_after": """// Trim whitespace
const text = await page.textContent('.message');
expect(text.trim()).toBe('Success');

// Or use partial matching
const text = await page.textContent('.message');
expect(text).toContain('Success');

// Or use regex for flexibility
const text = await page.textContent('.message');
expect(text).toMatch(/success/i);""",
                "confidence": Confidence.HIGH,
                "effort": 3
            },
            "count_mismatch": {
                "title": "Use more flexible element counting",
                "description": "Element count assertions can fail due to timing or dynamic rendering. Wait for stable state.",
                "code_before": """const items = await page.$$('.list-item');
expect(items.length).toBe(5);  // Fails: actual is 0 or 10""",
                "code_after": """// Wait for expected count
await page.waitForFunction(() =>
    document.querySelectorAll('.list-item').length === 5
);

// Or use minimum count
await page.waitForFunction((expectedCount) =>
    document.querySelectorAll('.list-item').length >= expectedCount,
    {}, 5
);

// Or be flexible about exact count
const items = await page.$$('.list-item');
expect(items.length).toBeGreaterThanOrEqual(5);""",
                "confidence": Confidence.MEDIUM,
                "effort": 8
            }
        }

        self.network_fixes = {
            "api_error": {
                "title": "Handle API failures gracefully or mock responses",
                "description": "API calls can fail due to server issues, auth, or rate limiting. Add proper error handling or use MSW.",
                "code_before": """await page.click('.fetch-data');
// Fails: API returns 500 or 401""",
                "code_after": """// Option 1: Wait and check for error message
await page.click('.fetch-data');
await page.waitForSelector('.error-message', { timeout: 5000 })
    .then(() => console.log('API error occurred'))
    .catch(() => console.log('API succeeded'));

// Option 2: Mock the API response with MSW
// In msw-handlers.ts:
const handlers = [
  rest.get('/api/data', (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.json({ success: true, data: [] })
    );
  }),
];

// Option 3: Route to API and handle response
const response = await page.waitForResponse(resp =>
    resp.url().includes('/api/data')
);
const data = await response.json();
expect(data).toBeDefined();""",
                "confidence": Confidence.MEDIUM,
                "effort": 15
            }
        }

        self.visual_fixes = {
            "layout_shift": {
                "title": "Wait for layout to stabilize before capturing",
                "description": "Visual tests fail when elements shift during render. Add explicit waits for layout stability.",
                "code_before": """await page.goto('/page');
await expect(page).toHaveScreenshot();  // Fails: layout shifts""",
                "code_after": """// Wait for layout stability
await page.goto('/page');

// Wait for fonts to load
await page.evaluate(() => document.fonts.ready);

// Wait for images to load
await page.waitForFunction(() => {
    const images = document.querySelectorAll('img');
    return Array.from(images).every(img => img.complete);
});

// Wait for specific layout element
await page.waitForSelector('.main-content', { state: 'visible' });

// Small delay for animations
await page.waitForTimeout(500);

await expect(page).toHaveScreenshot();""",
                "confidence": Confidence.HIGH,
                "effort": 10
            },
            "color_change": {
                "title": "Account for dynamic styling or theme changes",
                "description": "Visual tests can fail due to theming, hover states, or dynamic styles. Use consistent test conditions.",
                "code_before": """await page.goto('/page');
await expect(page).toHaveScreenshot();  // Fails: colors differ""",
                "code_after": """// Disable animations and transitions
await page.addInitScript(() => {
    window.addEventListener('load', () => {
        document.body.classList.add('disable-animations');
    });
});

// Use consistent theme
await page.goto('/page?theme=light');
await page.evaluate(() => {
    document.body.setAttribute('data-theme', 'light');
});

// Wait for theme to apply
await page.waitForSelector('[data-theme="light"]');

await expect(page).toHaveScreenshot();""",
                "confidence": Confidence.MEDIUM,
                "effort": 10
            }
        }

    def generate_fixes(self, test_name: str, failure_type: str, error_message: str) -> FixAnalysis:
        """
        Generate fix suggestions for a test failure (Feature #180)

        This is the main method that:
        1. Analyzes the failure to determine root cause
        2. Generates actionable fix suggestions
        3. Provides code examples (before/after)
        4. Rates confidence and estimates effort

        Args:
            test_name: Name of the failing test
            failure_type: Type of failure (selector_not_found, timeout, etc.)
            error_message: The error message from the test

        Returns:
            FixAnalysis with suggestions and recommendations
        """
        self.logger.info(f"Generating fixes for {test_name}: {failure_type}")

        # Determine root cause
        root_cause = self._analyze_root_cause(failure_type, error_message)

        # Generate suggestions based on failure type
        suggestions = self._generate_suggestions(failure_type, error_message)

        # Determine recommended action
        recommended = self._get_recommendation(suggestions)

        return FixAnalysis(
            test_name=test_name,
            failure_type=failure_type,
            error_message=error_message,
            root_cause=root_cause,
            suggestions=suggestions,
            recommended_action=recommended
        )

    def _analyze_root_cause(self, failure_type: str, error_message: str) -> str:
        """Analyze the failure and determine root cause"""
        if failure_type == "selector_not_found":
            if "timeout" in error_message.lower():
                return "Element selector exists but element didn't appear within timeout period. This is likely a timing issue or the element is conditionally rendered."
            elif "did not resolve" in error_message.lower():
                return "Selector syntax is valid but no matching elements were found. The element may not exist in the DOM or the selector is incorrect."
            else:
                return "Element could not be found in the DOM. This could be due to incorrect selector, timing issues, or the element not being rendered."

        elif failure_type == "timeout":
            if "waiting for selector" in error_message.lower():
                return "Test timed out while waiting for an element to appear. The element may be slow to render, conditionally displayed, or the selector is incorrect."
            elif "navigation" in error_message.lower():
                return "Test timed out during navigation. The page may be slow to load or there's a network issue."
            else:
                return "Test execution exceeded time limit. This could be due to slow operations, infinite loops, or waiting for conditions that never occur."

        elif failure_type == "assertion_failed":
            if "expected" in error_message.lower() and "got" in error_message.lower():
                return "Actual value doesn't match expected value. This could be due to timing, data changes, or incorrect expectations."
            else:
                return "Assertion condition failed. The expected state was not achieved."

        elif failure_type == "network_error":
            if "500" in error_message or "502" in error_message or "503" in error_message:
                return "Server error occurred. The backend API may be down or experiencing issues."
            elif "401" in error_message or "403" in error_message:
                return "Authentication or authorization error. The test may lack proper credentials."
            elif "404" in error_message:
                return "Endpoint not found. The API route may have changed or doesn't exist."
            else:
                return "Network request failed. Could be connectivity, CORS, or server issues."

        else:
            return f"Unknown failure type: {failure_type}"

    def _generate_suggestions(self, failure_type: str, error_message: str) -> List[FixSuggestion]:
        """Generate fix suggestions based on failure type"""
        suggestions = []

        if failure_type == "selector_not_found":
            suggestions.extend(self._get_selector_fixes(error_message))
        elif failure_type == "timeout":
            suggestions.extend(self._get_timeout_fixes(error_message))
        elif failure_type == "assertion_failed":
            suggestions.extend(self._get_assertion_fixes(error_message))
        elif failure_type == "network_error":
            suggestions.extend(self._get_network_fixes(error_message))
        else:
            # Generic suggestion for unknown failures
            suggestions.append(FixSuggestion(
                fix_type=FixType.CODE_PATTERN_FIX,
                title="Review test and application code",
                description=f"Review the test code and application code to understand why the failure occurred. Check browser logs, network tab, and console for additional clues.",
                code_example=f"""// Error: {error_message}

// Steps to debug:
// 1. Run test in headed mode:
//    await page.screenshot({{ path: 'debug.png' }})
// 2. Check console:
//    page.on('console', msg => console.log(msg.text()))
// 3. Add breakpoints:
//    await page.pause()
// 4. Verify element exists:
//    await page.$$('.selector')""",
                confidence=Confidence.LOW,
                estimated_effort=15,
                tags=["debug", "manual-review"]
            ))

        return suggestions

    def _get_selector_fixes(self, error_message: str) -> List[FixSuggestion]:
        """Get selector-specific fix suggestions"""
        suggestions = []

        # Check for class selector
        if re.search(r'\.[\w-]+', error_message):
            fix = self.selector_fixes["class_selector"]
            suggestions.append(FixSuggestion(
                fix_type=FixType.SELECTOR_FIX,
                title=fix["title"],
                description=fix["description"],
                code_example=f"BEFORE:\n{fix['code_before']}\n\nAFTER:\n{fix['code_after']}",
                confidence=fix["confidence"],
                estimated_effort=fix["effort"],
                references=[
                    "https://playwright.dev/python/docs/selectors",
                    "https://testing-library.com/docs/queries/about/#priority"
                ],
                tags=["selector", "stability"]
            ))

        # Check for ID selector
        if re.search(r'#[\w-]+', error_message):
            fix = self.selector_fixes["id_selector"]
            suggestions.append(FixSuggestion(
                fix_type=FixType.SELECTOR_FIX,
                title=fix["title"],
                description=fix["description"],
                code_example=f"BEFORE:\n{fix['code_before']}\n\nAFTER:\n{fix['code_after']}",
                confidence=fix["confidence"],
                estimated_effort=fix["effort"],
                references=[
                    "https://playwright.dev/python/docs/selectors"
                ],
                tags=["selector", "timing"]
            ))

        # Check for text selector
        if "text=" in error_message or "gettext" in error_message.lower():
            fix = self.selector_fixes["text_selector"]
            suggestions.append(FixSuggestion(
                fix_type=FixType.SELECTOR_FIX,
                title=fix["title"],
                description=fix["description"],
                code_example=f"BEFORE:\n{fix['code_before']}\n\nAFTER:\n{fix['code_after']}",
                confidence=fix["confidence"],
                estimated_effort=fix["effort"],
                references=[
                    "https://playwright.dev/python/docs/text-input"
                ],
                tags=["selector", "i18n"]
            ))

        # Add generic selector advice
        suggestions.append(FixSuggestion(
            fix_type=FixType.SELECTOR_FIX,
            title="Use Playwright's code generator to find robust selectors",
            description="Use Playwright's codegen tool to automatically generate stable selectors for your elements. This interactive tool records your actions and creates selectors optimized for reliability. Run it to identify the most stable selectors by analyzing the DOM structure and get recommendations for data-testid, aria attributes, or role-based selectors over fragile CSS classes.",
            code_example="""# Run codegen in terminal
playwright codegen https://your-app.com

# This will open a browser and record your actions,
# generating selectors that are optimized for reliability
# Click on elements in the UI and see the generated code

# Best practices:
# - Prefer data-testid attributes
# - Use aria labels for accessibility
# - Use role-based selectors (button, link)
# - Avoid CSS classes that change with styling
# - Avoid dynamic IDs (auto-generated)""",
            confidence=Confidence.HIGH,
            estimated_effort=5,
            references=["https://playwright.dev/python/docs/codegen"],
            tags=["selector", "tooling"]
        ))

        return suggestions

    def _get_timeout_fixes(self, error_message: str) -> List[FixSuggestion]:
        """Get timeout-specific fix suggestions"""
        suggestions = []

        if "waiting for selector" in error_message.lower():
            suggestions.append(FixSuggestion(
                fix_type=FixType.WAIT_FIX,
                title=self.wait_fixes["timeout_not_found"]["title"],
                description=self.wait_fixes["timeout_not_found"]["description"],
                code_example=f"BEFORE:\n{self.wait_fixes['timeout_not_found']['code_before']}\n\nAFTER:\n{self.wait_fixes['timeout_not_found']['code_after']}",
                confidence=self.wait_fixes["timeout_not_found"]["confidence"],
                estimated_effort=self.wait_fixes["timeout_not_found"]["effort"],
                references=[
                    "https://playwright.dev/python/docs/actionability",
                    "https://playwright.dev/python/docs/waits"
                ],
                tags=["timeout", "wait"]
            ))

        # Race condition fix
        suggestions.append(FixSuggestion(
            fix_type=FixType.WAIT_FIX,
            title=self.wait_fixes["race_condition"]["title"],
            description=self.wait_fixes["race_condition"]["description"],
            code_example=f"BEFORE:\n{self.wait_fixes['race_condition']['code_before']}\n\nAFTER:\n{self.wait_fixes['race_condition']['code_after']}",
            confidence=self.wait_fixes["race_condition"]["confidence"],
            estimated_effort=self.wait_fixes["race_condition"]["effort"],
            references=[
                "https://playwright.dev/python/docs/handling-timeouts"
            ],
            tags=["timeout", "async", "race-condition"]
        ))

        return suggestions

    def _get_assertion_fixes(self, error_message: str) -> List[FixSuggestion]:
        """Get assertion-specific fix suggestions"""
        suggestions = []

        # Check for text/value mismatch (look for "expected", "got", "but", etc.)
        error_lower = error_message.lower()
        if any(keyword in error_lower for keyword in ["text", "expected", "got", "but", "value"]):
            suggestions.append(FixSuggestion(
                fix_type=FixType.ASSERTION_FIX,
                title=self.assertion_fixes["text_mismatch"]["title"],
                description=self.assertion_fixes["text_mismatch"]["description"],
                code_example=f"BEFORE:\n{self.assertion_fixes['text_mismatch']['code_before']}\n\nAFTER:\n{self.assertion_fixes['text_mismatch']['code_after']}",
                confidence=self.assertion_fixes["text_mismatch"]["confidence"],
                estimated_effort=self.assertion_fixes["text_mismatch"]["effort"],
                references=[
                    "https://jestjs.io/docs/using-matchers"
                ],
                tags=["assertion", "text"]
            ))

        if "length" in error_lower or "count" in error_lower:
            suggestions.append(FixSuggestion(
                fix_type=FixType.ASSERTION_FIX,
                title=self.assertion_fixes["count_mismatch"]["title"],
                description=self.assertion_fixes["count_mismatch"]["description"],
                code_example=f"BEFORE:\n{self.assertion_fixes['count_mismatch']['code_before']}\n\nAFTER:\n{self.assertion_fixes['count_mismatch']['code_after']}",
                confidence=self.assertion_fixes["count_mismatch"]["confidence"],
                estimated_effort=self.assertion_fixes["count_mismatch"]["effort"],
                references=[
                    "https://playwright.dev/python/docs/assertions"
                ],
                tags=["assertion", "count", "timing"]
            ))

        return suggestions

    def _get_network_fixes(self, error_message: str) -> List[FixSuggestion]:
        """Get network-specific fix suggestions"""
        suggestions = []

        if any(code in error_message for code in ["500", "502", "503", "401", "403", "404"]):
            suggestions.append(FixSuggestion(
                fix_type=FixType.NETWORK_FIX,
                title=self.network_fixes["api_error"]["title"],
                description=self.network_fixes["api_error"]["description"],
                code_example=f"BEFORE:\n{self.network_fixes['api_error']['code_before']}\n\nAFTER:\n{self.network_fixes['api_error']['code_after']}",
                confidence=self.network_fixes["api_error"]["confidence"],
                estimated_effort=self.network_fixes["api_error"]["effort"],
                references=[
                    "https://playwright.dev/python/docs/network",
                    "https://mswjs.io/"
                ],
                tags=["network", "api", "mocking"]
            ))

        return suggestions

    def _get_recommendation(self, suggestions: List[FixSuggestion]) -> Optional[str]:
        """Get the recommended action based on suggestions"""
        if not suggestions:
            return "Review test logs and application code to diagnose the issue"

        # Sort by confidence (HIGH first) and effort (quickest first)
        sorted_suggestions = sorted(
            suggestions,
            key=lambda s: (
                0 if s.confidence == Confidence.HIGH else 1 if s.confidence == Confidence.MEDIUM else 2,
                s.estimated_effort
            )
        )

        top_suggestion = sorted_suggestions[0]
        return f"Try: {top_suggestion.title} (Estimated effort: {top_suggestion.estimated_effort} minutes)"


# ============================================================================
# Convenience Functions
# ============================================================================

def generate_fix_suggestions(test_name: str, failure_type: str, error_message: str) -> FixAnalysis:
    """
    Convenience function to generate fix suggestions

    This is the main entry point for Feature #180

    Args:
        test_name: Name of the failing test
        failure_type: Type of failure
        error_message: The error message

    Returns:
        FixAnalysis with actionable suggestions
    """
    generator = AutoFixGenerator()
    return generator.generate_fixes(test_name, failure_type, error_message)
