"""
A11y Adapter - Integrate axe-core for WCAG compliance scanning

This module is responsible for:
- Scanning pages for accessibility violations
- Categorizing violations by impact level
- Tracking WCAG compliance level
- Generating accessibility reports
- Providing fix suggestions
- Scoring accessibility (0-100)
"""

import json
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger


# ============================================================================
# Data Models
# ============================================================================

class ImpactLevel(Enum):
    """Accessibility violation impact levels"""
    CRITICAL = "critical"
    SERIOUS = "serious"
    MODERATE = "moderate"
    MINOR = "minor"


class WCAGLevel(Enum):
    """WCAG compliance levels"""
    A = "A"
    AA = "AA"
    AAA = "AAA"


@dataclass
class AccessibilityViolation:
    """Represents a single accessibility violation"""
    rule_id: str  # e.g., 'color-contrast', 'image-alt'
    impact: ImpactLevel  # critical, serious, moderate, minor
    description: str  # Human-readable description
    help_text: str  # Detailed explanation
    help_url: str  # Link to documentation
    wcag_tags: List[str]  # e.g., ['wcag2a', 'wcag2aa', 'wcag21aa']
    selectors: List[str]  # CSS selectors of violating elements
    failure_summary: str  # Summary of the failure

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "rule_id": self.rule_id,
            "impact": self.impact.value,
            "description": self.description,
            "help_text": self.help_text,
            "help_url": self.help_url,
            "wcag_tags": self.wcag_tags,
            "selectors": self.selectors,
            "failure_summary": self.failure_summary
        }


@dataclass
class ScanResult:
    """Result of an accessibility scan"""
    test_name: str
    url: str
    timestamp: datetime
    passed: bool
    score: float  # 0-100
    violations: List[AccessibilityViolation]
    passes: List[Dict[str, Any]]  # Rules that passed
    incomplete: List[Dict[str, Any]]  # Rules that need manual review
    wcag_level: WCAGLevel
    total_violations: int = field(init=False)
    critical_count: int = field(init=False)
    serious_count: int = field(init=False)
    moderate_count: int = field(init=False)
    minor_count: int = field(init=False)

    def __post_init__(self):
        """Calculate violation counts by impact"""
        self.total_violations = len(self.violations)
        self.critical_count = sum(1 for v in self.violations if v.impact == ImpactLevel.CRITICAL)
        self.serious_count = sum(1 for v in self.violations if v.impact == ImpactLevel.SERIOUS)
        self.moderate_count = sum(1 for v in self.violations if v.impact == ImpactLevel.MODERATE)
        self.minor_count = sum(1 for v in self.violations if v.impact == ImpactLevel.MINOR)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "url": self.url,
            "timestamp": self.timestamp.isoformat(),
            "passed": self.passed,
            "score": self.score,
            "violations": [v.to_dict() for v in self.violations],
            "passes": self.passes,
            "incomplete": self.incomplete,
            "wcag_level": self.wcag_level.value,
            "total_violations": self.total_violations,
            "critical_count": self.critical_count,
            "serious_count": self.serious_count,
            "moderate_count": self.moderate_count,
            "minor_count": self.minor_count
        }


# ============================================================================
# A11y Adapter Implementation
# ============================================================================

class A11yAdapter:
    """
    Accessibility testing adapter using axe-core

    This adapter handles:
    - Scanning pages for accessibility violations
    - Categorizing violations by impact
    - Tracking WCAG compliance
    - Generating accessibility reports
    - Calculating accessibility scores
    """

    def __init__(
        self,
        output_dir: str = "a11y/reports",
        wcag_level: WCAGLevel = WCAGLevel.AA,
        timeout: int = 30000
    ):
        """
        Initialize the A11y Adapter

        Args:
            output_dir: Directory to store accessibility reports
            wcag_level: WCAG compliance level to target (A, AA, or AAA)
            timeout: Timeout for accessibility scans in milliseconds
        """
        self.logger = get_logger(__name__)
        self.output_dir = Path(output_dir)
        self.wcag_level = wcag_level
        self.timeout = timeout

        # Create output directory
        self._setup_directories()

        self.logger.info(f"A11yAdapter initialized with output_dir={output_dir}, wcag_level={wcag_level.value}")

    def _setup_directories(self):
        """Create necessary directories if they don't exist"""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info("A11y output directory created/verified")
        except Exception as e:
            self.logger.error(f"Failed to create directories: {e}")
            raise

    def scan_page(
        self,
        page: Any,  # Playwright Page object
        test_name: str,
        url: Optional[str] = None,
        include_selectors: Optional[List[str]] = None,
        exclude_selectors: Optional[List[str]] = None
    ) -> ScanResult:
        """
        Scan a page for accessibility violations (Feature #115)

        Args:
            page: Playwright Page object
            test_name: Name of the test
            url: URL being scanned (optional, will get from page if not provided)
            include_selectors: CSS selectors to include in scan (optional)
            exclude_selectors: CSS selectors to exclude from scan (optional)

        Returns:
            ScanResult with violations, score, and compliance info
        """
        try:
            self.logger.info(f"Starting accessibility scan for test: {test_name}")

            # Get URL from page if not provided
            if url is None:
                url = page.url
                self.logger.info(f"Using URL from page: {url}")

            # Import AxeBuilder dynamically (Playwright integration)
            from custom.uat_gateway.utils.playwright_helper import inject_axe, run_axe_scan

            # Inject axe-core and run scan
            axe_results = run_axe_scan(
                page,
                include_selectors=include_selectors,
                exclude_selectors=exclude_selectors,
                wcag_level=self.wcag_level.value
            )

            # Parse results into ScanResult
            scan_result = self._parse_axe_results(
                axe_results,
                test_name,
                url
            )

            # Save report to file
            self._save_report(scan_result)

            self.logger.info(
                f"Accessibility scan complete: {scan_result.score}/100, "
                f"{scan_result.total_violations} violations"
            )

            return scan_result

        except Exception as e:
            self.logger.error(f"Accessibility scan failed: {e}")
            # Return a failed result
            return ScanResult(
                test_name=test_name,
                url=url or page.url,
                timestamp=datetime.now(),
                passed=False,
                score=0.0,
                violations=[],
                passes=[],
                incomplete=[],
                wcag_level=self.wcag_level
            )

    def _parse_axe_results(
        self,
        axe_results: Dict[str, Any],
        test_name: str,
        url: str
    ) -> ScanResult:
        """
        Parse axe-core results into ScanResult

        Args:
            axe_results: Raw results from axe-core
            test_name: Name of the test
            url: URL that was scanned

        Returns:
            Parsed ScanResult object
        """
        # Parse violations
        violations = []
        for v in axe_results.get("violations", []):
            # Extract failure summaries from nodes (where axe-core puts them)
            # Aggregate up to 3 unique failure summaries
            failure_summaries = set()
            for node in v.get("nodes", []):
                if "failureSummary" in node:
                    failure_summaries.add(node["failureSummary"])
                    if len(failure_summaries) >= 3:
                        break

            # Combine summaries or use violation-level summary
            failure_summary = v.get("failureSummary", "")
            if not failure_summary and failure_summaries:
                failure_summary = "\n\n".join(sorted(failure_summaries))
            elif failure_summaries:
                # Append node-specific details if violation-level summary exists
                failure_summary = failure_summary + "\n\n" + "\n\n".join(sorted(failure_summaries))

            violation = AccessibilityViolation(
                rule_id=v["id"],
                impact=ImpactLevel(v.get("impact", "moderate")),
                description=v["description"],
                help_text=v["help"],
                help_url=v["helpUrl"],
                wcag_tags=v.get("tags", []),
                selectors=[node["target"] for node in v.get("nodes", [])],
                failure_summary=failure_summary
            )
            violations.append(violation)

        # Calculate score (0-100 based on violations)
        score = self._calculate_score(violations)

        # Determine if passed (no critical or serious violations)
        passed = all(
            v.impact not in [ImpactLevel.CRITICAL, ImpactLevel.SERIOUS]
            for v in violations
        )

        return ScanResult(
            test_name=test_name,
            url=url,
            timestamp=datetime.now(),
            passed=passed,
            score=score,
            violations=violations,
            passes=axe_results.get("passes", []),
            incomplete=axe_results.get("incomplete", []),
            wcag_level=self.wcag_level
        )

    def _calculate_score(self, violations: List[AccessibilityViolation]) -> float:
        """
        Calculate accessibility score (0-100)

        Score is calculated based on violation impact:
        - Critical: -25 points each
        - Serious: -15 points each
        - Moderate: -5 points each
        - Minor: -1 point each

        Args:
            violations: List of accessibility violations

        Returns:
            Score from 0-100
        """
        score = 100.0

        for v in violations:
            if v.impact == ImpactLevel.CRITICAL:
                score -= 25
            elif v.impact == ImpactLevel.SERIOUS:
                score -= 15
            elif v.impact == ImpactLevel.MODERATE:
                score -= 5
            elif v.impact == ImpactLevel.MINOR:
                score -= 1

        return max(0.0, min(100.0, score))

    def _save_report(self, scan_result: ScanResult):
        """
        Save accessibility scan report to JSON file

        Args:
            scan_result: Scan result to save
        """
        try:
            timestamp_str = scan_result.timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"{scan_result.test_name}_{timestamp_str}.json"
            filepath = self.output_dir / filename

            with open(filepath, 'w') as f:
                json.dump(scan_result.to_dict(), f, indent=2)

            self.logger.info(f"Accessibility report saved to {filepath}")

        except Exception as e:
            self.logger.error(f"Failed to save report: {e}")

    def get_violations_by_impact(
        self,
        violations: List[AccessibilityViolation],
        impact: ImpactLevel
    ) -> List[AccessibilityViolation]:
        """
        Filter violations by impact level

        Args:
            violations: List of violations to filter
            impact: Impact level to filter by

        Returns:
            Filtered list of violations
        """
        return [v for v in violations if v.impact == impact]

    def get_fix_suggestions(self, violation: AccessibilityViolation) -> str:
        """
        Get fix suggestion for a violation with actionable steps and code examples (Feature #119)

        Args:
            violation: Violation to get suggestion for

        Returns:
            Fix suggestion text with actionable steps and code examples
        """
        # Flatten selectors (they're stored as lists of CSS selector arrays)
        selector_strings = []
        for selector_list in violation.selectors[:5]:
            if isinstance(selector_list, list):
                selector_strings.append(' '.join(selector_list))
            else:
                selector_strings.append(str(selector_list))

        # Get rule-specific fix suggestions with code examples
        rule_fixes = self._get_rule_specific_fix(violation.rule_id)

        # Format WCAG tags for display
        wcag_criteria = self._format_wcag_tags(violation.wcag_tags)

        # Build comprehensive suggestion
        suggestion = f"""
## Fix for {violation.rule_id}

**Issue:** {violation.description}
**Impact:** {violation.impact.value.upper()}

### What to do:
{violation.help_text}

### WCAG Criteria:
{wcag_criteria}

### Affected Elements:
{chr(10).join(f"- {selector}" for selector in selector_strings)}

### How to Fix:
{rule_fixes}

### Documentation:
📖 {violation.help_url}

---
**Why this matters:** Accessibility violations prevent users with disabilities from using your content effectively. Fixing these issues improves user experience for everyone and ensures legal compliance with accessibility standards.
""".strip()

        return suggestion

    def _get_rule_specific_fix(self, rule_id: str) -> str:
        """
        Get rule-specific fix suggestions with code examples (Feature #119)

        Args:
            rule_id: The accessibility rule ID

        Returns:
            Detailed fix instructions with code examples
        """
        # Rule-specific fix suggestions with before/after code examples
        fix_suggestions = {
            "image-alt": """
Add an `alt` attribute to all `img` elements. The alt text should:
- Describe the image's content and function
- Be concise (typically 125 characters or less)
- Be empty (alt="") for decorative images

**Example:**

```html
<!-- Before: Missing alt text -->
<img src="logo.png" class="logo">

<!-- After: With descriptive alt text -->
<img src="logo.png" class="logo" alt="Company Logo">

<!-- Before: Decorative image -->
<img src="decorative-line.png">

<!-- After: Decorative image marked appropriately -->
<img src="decorative-line.png" alt="" role="presentation">
```

**For complex images:**
```html
<!-- Image with detailed information -->
<img src="sales-chart.png" alt="Bar chart showing Q1 sales increased by 25% compared to previous quarter" longdesc="sales-chart-details.html">
```""",

            "color-contrast": """
Ensure text and background colors have sufficient contrast ratio:
- **4.5:1** for normal text (less than 18pt or 14pt bold)
- **3:1** for large text (18pt+ or 14pt bold+)
- **3:1** for UI components and graphical objects

**Example:**

```css
/* Before: Insufficient contrast */
.low-contrast-text {
  color: #999;  /* Light gray on white */
  background: #fff;
}

/* After: Sufficient contrast (ratio > 4.5:1) */
.good-contrast-text {
  color: #333;  /* Dark gray on white */
  background: #fff;
}

/* Alternative: Use darker background */
.high-contrast-text {
  color: #fff;  /* White on dark gray */
  background: #333;
}
```

**Testing:**
Use online tools to verify contrast ratios:
- WebAIM Contrast Checker: https://webaim.org/resources/contrastchecker/
- Chrome DevTools Color Picker (shows contrast ratio)""",

            "label": """
Associate form inputs with explicit labels using one of these methods:

**Method 1: Use the `for` attribute (Recommended)**

```html
<!-- Before: No label -->
<input type="text" id="email" placeholder="Email">

<!-- After: Explicit label -->
<label for="email">Email Address:</label>
<input type="text" id="email" name="email">
```

**Method 2: Wrap the input**

```html
<!-- Before: Unlabeled input -->
<input type="text" id="name">

<!-- After: Wrapped in label -->
<label>
  Full Name:
  <input type="text" id="name" name="name">
</label>
```

**Method 3: Use aria-label for icon-only buttons**

```html
<!-- Before: No accessible name -->
<button type="submit">
  <i class="icon-search"></i>
</button>

<!-- After: With aria-label -->
<button type="submit" aria-label="Search">
  <i class="icon-search"></i>
</button>
```

**Note:** `placeholder` is NOT a substitute for `label`""",

            "button-name": """
Ensure buttons have discernible, accessible text content:

**Method 1: Use visible text**

```html
<!-- Before: Icon-only button with no text -->
<button class="submit">
  <i class="icon-check"></i>
</button>

<!-- After: With visible text -->
<button class="submit">
  <i class="icon-check"></i>
  Submit Form
</button>
```

**Method 2: Use aria-label for icon buttons**

```html
<!-- Before: Icon button with no accessible name -->
<button class="close">
  <i class="icon-x"></i>
</button>

<!-- After: With aria-label -->
<button class="close" aria-label="Close dialog">
  <i class="icon-x"></i>
</button>
```

**Method 3: Use aria-labelledby for complex buttons**

```html
<button aria-labelledby="close-btn-title">
  <span id="close-btn-title">Close</span>
  <i class="icon-x"></i>
</button>
```

**Method 4: Use title attribute (fallback only)**

```html
<button title="Close window">
  <i class="icon-x"></i>
</button>
```""",

            "heading-order": """
Maintain a logical heading hierarchy without skipping levels:

**Correct heading order:**
```html
<h1>Page Title</h1>
  <h2>Section 1</h2>
    <h3>Subsection 1.1</h3>
    <h3>Subsection 1.2</h3>
  <h2>Section 2</h2>
    <h3>Subsection 2.1</h3>
      <h4>Detail 2.1.1</h4>
```

**Incorrect:**
```html
<h1>Page Title</h1>
  <h3>Subsection</h3>  <!-- Skipped h2 -->
```

**Fixes for common issues:**
```html
<!-- If you need different styling, use CSS, not heading levels -->
<h1 style="font-size: 1.5rem;">Small Heading</h1>

<!-- For non-heading content, use other elements -->
<div class="section-title">Not a Heading</div>
```

**Remember:** Headings convey structure, not appearance. Use CSS for styling.""",

            "aria-allowed-attr": """
Ensure ARIA attributes are used correctly according to the ARIA specification:

```html
<!-- Before: Invalid ARIA attribute -->
<div role="button" aria-invalid="true">Click me</div>

<!-- After: Valid ARIA attribute -->
<button aria-pressed="false">Toggle me</button>
```

**Always check:**
- The ARIA role supports the attribute
- The attribute value is valid for that role
- Native HTML elements are preferred over ARIA""",

            "aria-required-attr": """
Ensure required ARIA attributes are present when using ARIA roles:

```html
<!-- Before: Missing required aria-label -->
<button role="closebutton">
  <i class="icon-x"></i>
</button>

<!-- After: With required aria-label -->
<button role="closebutton" aria-label="Close">
  <i class="icon-x"></i>
</button>
```

**Common required attributes:**
- `role="dialog"` requires `aria-labelledby` or `aria-label`
- `role="button"` requires accessible name (text or aria-label)
- `role="listbox"` requires `aria-activedescendant` or use of `aria-selected`""",

            "empty-heading": """
Headings should not be empty. They must have discernible text content:

```html
<!-- Before: Empty heading -->
<h1></h1>

<!-- After: With content -->
<h1>Page Title</h1>

<!-- For screen-reader-only content: -->
<h1>
  <span class="sr-only">Dashboard</span>
</h1>
```

**If the heading is purely visual:**
```html
<!-- Don't use empty headings, use a div instead -->
<div class="page-header">
  <!-- decorative content only -->
</div>
```""",

            "list": """
Lists must be properly structured with list items:

```html
<!-- Before: Divs instead of list items -->
<div class="list">
  <div>Item 1</div>
  <div>Item 2</div>
</div>

<!-- After: Proper list structure -->
<ul class="list">
  <li>Item 1</li>
  <li>Item 2</li>
</ul>
```

**For definition lists:**
```html
<dl>
  <dt>Term</dt>
  <dd>Definition</dd>
</dl>
```""",

            "listitem": """
List items must be direct children of list elements:

```html
<!-- Before: Invalid nesting -->
<ul>
  <div>
    <li>Item 1</li>
  </div>
</ul>

<!-- After: Valid structure -->
<ul>
  <li>Item 1</li>
  <li>Item 2</li>
</ul>
```

**Nested lists:**
```html
<ul>
  <li>Item 1</li>
  <li>Item 2
    <ul>  <!-- Nested list must be inside a li -->
      <li>Nested Item 2.1</li>
    </ul>
  </li>
</ul>
```"""
        }

        # Return rule-specific fix, or generic advice if rule not found
        return fix_suggestions.get(
            rule_id,
            f"""
1. Review the violation details above
2. Check the documentation link for specific guidance
3. Update your code to address the accessibility issue
4. Re-test to verify the fix

**General approach:**
- Ensure all interactive elements have accessible names
- Provide text alternatives for non-text content
- Ensure sufficient color contrast
- Use proper HTML semantics
- Test with keyboard and screen readers

**Resources:**
- WCAG 2.1 Guidelines: https://www.w3.org/WAI/WCAG21/quickref/
- WebAIM Checklist: https://webaim.org/standards/wcag/checklist
- axe-core Rule Documentation: https://dequeuniversity.com/rules/axe/4.8/
"""
        )

    def _format_wcag_tags(self, tags: List[str]) -> str:
        """
        Format WCAG tags for human-readable display (Feature #119)

        Args:
            tags: List of WCAG tags from axe-core

        Returns:
            Formatted WCAG criteria string
        """
        if not tags:
            return "Not specified"

        # Map common WCAG tags to readable descriptions
        wcag_descriptions = {
            "wcag2a": "WCAG 2.0 Level A",
            "wcag2aa": "WCAG 2.0 Level AA",
            "wcag2aaa": "WCAG 2.0 Level AAA",
            "wcag21a": "WCAG 2.1 Level A",
            "wcag21aa": "WCAG 2.1 Level AA",
            "wcag21aaa": "WCAG 2.1 Level AAA",
            "wcag22a": "WCAG 2.2 Level A",
            "wcag22aa": "WCAG 2.2 Level AA",
            "wcag22aaa": "WCAG 2.2 Level AAA",
        }

        # Format each tag
        formatted_tags = []
        for tag in tags:
            if tag in wcag_descriptions:
                formatted_tags.append(f"- {wcag_descriptions[tag]}")
            elif tag.startswith("wcag"):
                # Generic WCAG tag formatting
                formatted_tags.append(f"- {tag.upper()}")
            else:
                formatted_tags.append(f"- {tag}")

        return "\n".join(formatted_tags)

    def generate_summary_report(
        self,
        scan_results: List[ScanResult]
    ) -> Dict[str, Any]:
        """
        Generate summary report from multiple scan results

        Args:
            scan_results: List of scan results to summarize

        Returns:
            Summary report dictionary
        """
        total_tests = len(scan_results)
        passed_tests = sum(1 for r in scan_results if r.passed)
        avg_score = sum(r.score for r in scan_results) / total_tests if total_tests > 0 else 0

        total_violations = sum(r.total_violations for r in scan_results)
        critical_count = sum(r.critical_count for r in scan_results)
        serious_count = sum(r.serious_count for r in scan_results)
        moderate_count = sum(r.moderate_count for r in scan_results)
        minor_count = sum(r.minor_count for r in scan_results)

        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "pass_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            "average_score": avg_score,
            "total_violations": total_violations,
            "critical_count": critical_count,
            "serious_count": serious_count,
            "moderate_count": moderate_count,
            "minor_count": minor_count,
            "wcag_level": self.wcag_level.value,
            "timestamp": datetime.now().isoformat()
        }
