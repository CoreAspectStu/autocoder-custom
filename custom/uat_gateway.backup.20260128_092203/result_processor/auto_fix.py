"""
Auto-Fix Module - Automatically apply safe fixes to test failures

This module is responsible for:
- Identifying auto-fixable failures (low-risk issues)
- Applying safe fixes without human intervention
- Updating test files with corrected selectors/values
- Re-running tests to verify fixes work
- Tracking fix success/failure rates

Feature #181: Auto-fix applies safe fixes automatically
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import TestExecutionError, handle_errors
from custom.uat_gateway.test_executor.test_executor import TestResult


# ============================================================================
# Data Models
# ============================================================================

class FixType(Enum):
    """Types of auto-fixes that can be applied"""
    SELECTOR_TYPO = "selector_typo"  # Fix typos in selectors
    SELECTOR_ALTERNATIVE = "selector_alternative"  # Try alternative selectors
    TIMEOUT_INCREASE = "timeout_increase"  # Increase timeout values
    WAIT_STRATEGY = "wait_strategy"  # Add wait strategies
    VALUE_CORRECTION = "value_correction"  # Fix assertion values


class FixStatus(Enum):
    """Status of an auto-fix attempt"""
    PENDING = "pending"  # Fix not yet applied
    APPLIED = "applied"  # Fix applied, awaiting verification
    VERIFIED = "verified"  # Fix applied and test passed
    FAILED = "failed"  # Fix applied but test still failed
    SKIPPED = "skipped"  # Fix not applied (too risky or not applicable)


@dataclass
class AutoFixResult:
    """Result of an auto-fix attempt"""
    test_name: str
    fix_type: FixType
    original_selector: Optional[str] = None
    fixed_selector: Optional[str] = None
    original_code: Optional[str] = None
    fixed_code: Optional[str] = None
    status: FixStatus = FixStatus.PENDING
    confidence: float = 0.0  # 0-1, how confident we are this will work
    risk_level: str = "low"  # 'low', 'medium', 'high'
    error_message: Optional[str] = None
    verification_result: Optional[TestResult] = None
    applied_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "fix_type": self.fix_type.value,
            "original_selector": self.original_selector,
            "fixed_selector": self.fixed_selector,
            "original_code": self.original_code,
            "fixed_code": self.fixed_code,
            "status": self.status.value,
            "confidence": round(self.confidence, 2),
            "risk_level": self.risk_level,
            "error_message": self.error_message,
            "verification_result": self.verification_result.to_dict() if self.verification_result else None,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None
        }


@dataclass
class SelectorSuggestion:
    """Suggested alternative selector"""
    selector: str
    strategy: str  # 'id', 'class', 'data-testid', 'text', 'aria-label'
    confidence: float  # 0-1
    reason: str


# ============================================================================
# Auto-Fix Engine
# ============================================================================

class AutoFixEngine:
    """
    Analyzes test failures and applies safe fixes automatically

    Feature #181 Implementation:
    - Detects selector failures
    - Identifies safe-to-fix issues (low-risk)
    - Applies fixes to test files
    - Re-runs tests to verify
    - Tracks success/failure rates
    """

    # Safe fix patterns (low-risk issues)
    SAFE_FIX_PATTERNS = {
        'selector_typo': [
            # Common typos in selectors
            (r'([a-z])([A-Z])', r'\1-\2'),  # missing hyphen in kebab-case
            (r'([a-z]+)([0-9]+)', r'\1-\2'),  # missing hyphen before number
            (r'\s+', '-'),  # spaces instead of hyphens
            (r'_{2,}', '_'),  # multiple underscores
        ],
        'case_mismatch': [
            # CSS is case-insensitive for classes, but we should fix typos
            (r'Button', 'button'),
            (r'Input', 'input'),
            (r'Form', 'form'),
        ]
    }

    # Alternative selector strategies to try
    ALTERNATIVE_STRATEGIES = [
        'data-testid',
        'aria-label',
        'text content',
        'title attribute',
        'id attribute',
    ]

    def __init__(self):
        self.logger = get_logger("auto_fix")
        self.fix_history: List[AutoFixResult] = []
        self.total_fixes_attempted = 0
        self.total_fixes_succeeded = 0

    @handle_errors
    def analyze_failure(self, test_result: TestResult) -> Optional[AutoFixResult]:
        """
        Analyze a test failure to determine if it can be auto-fixed

        Args:
            test_result: Failed test result

        Returns:
            AutoFixResult if fixable, None if not fixable
        """
        self.logger.info(f"Analyzing failure for: {test_result.test_name}")

        # Check if this is a selector failure
        if not self._is_selector_failure(test_result):
            self.logger.info("Not a selector failure, cannot auto-fix")
            return None

        # Extract selector from error message
        selector = self._extract_selector(test_result.error_message)
        if not selector:
            self.logger.warning("Could not extract selector from error")
            return None

        # Determine fix type and confidence
        fix_type, confidence, risk_level = self._determine_fix_type(
            test_result.error_message, selector
        )

        # Only fix low-risk issues with decent confidence
        if risk_level != 'low' or confidence < 0.5:
            self.logger.info(f"Fix too risky or low confidence (risk={risk_level}, confidence={confidence})")
            return None

        # Create auto-fix result
        result = AutoFixResult(
            test_name=test_result.test_name,
            fix_type=fix_type,
            original_selector=selector,
            status=FixStatus.PENDING,
            confidence=confidence,
            risk_level=risk_level
        )

        self.logger.info(f"Auto-fix candidate found: {fix_type.value} (confidence={confidence})")
        return result

    @handle_errors
    def apply_fix(self, fix_result: AutoFixResult, test_file_path: str) -> bool:
        """
        Apply an auto-fix to a test file

        Args:
            fix_result: Auto-fix result with fix details
            test_file_path: Path to test file to modify

        Returns:
            True if fix applied successfully, False otherwise
        """
        self.logger.info(f"Applying fix to {fix_result.test_name}")

        try:
            # Read test file
            test_path = Path(test_file_path)
            if not test_path.exists():
                raise FileNotFoundError(f"Test file not found: {test_file_path}")

            original_content = test_path.read_text()
            fix_result.original_code = original_content

            # Apply fix based on type
            if fix_result.fix_type == FixType.SELECTOR_TYPO:
                fixed_content = self._fix_selector_typo(
                    original_content,
                    fix_result.original_selector
                )
            elif fix_result.fix_type == FixType.SELECTOR_ALTERNATIVE:
                # Generate alternative selector if not already set
                if not fix_result.fixed_selector:
                    suggestions = self.generate_selector_suggestions(
                        fix_result.original_selector
                    )
                    if suggestions:
                        fix_result.fixed_selector = suggestions[0].selector
                        self.logger.info(f"Generated alternative: {fix_result.fixed_selector}")

                fixed_content = self._apply_alternative_selector(
                    original_content,
                    fix_result.original_selector,
                    fix_result.fixed_selector or ""
                )
            elif fix_result.fix_type == FixType.TIMEOUT_INCREASE:
                fixed_content = self._increase_timeout(original_content)
            elif fix_result.fix_type == FixType.WAIT_STRATEGY:
                fixed_content = self._add_wait_strategy(
                    original_content,
                    fix_result.original_selector
                )
            else:
                self.logger.warning(f"Unsupported fix type: {fix_result.fix_type}")
                return False

            # Verify something changed
            if fixed_content == original_content:
                self.logger.warning("Fix resulted in no changes to file")
                return False

            # Write fixed content
            test_path.write_text(fixed_content)
            fix_result.fixed_code = fixed_content
            fix_result.status = FixStatus.APPLIED
            fix_result.applied_at = datetime.now()

            self.logger.info(f"Fix applied successfully to {test_file_path}")
            self.total_fixes_attempted += 1
            return True

        except Exception as e:
            self.logger.error(f"Failed to apply fix: {e}")
            fix_result.error_message = str(e)
            fix_result.status = FixStatus.FAILED
            return False

    @handle_errors
    def verify_fix(self, fix_result: AutoFixResult, verification_result: TestResult) -> bool:
        """
        Verify that an auto-fix worked by checking test result

        Args:
            fix_result: Auto-fix result that was applied
            verification_result: Test result from re-running the test

        Returns:
            True if fix worked (test passed), False otherwise
        """
        self.logger.info(f"Verifying fix for {fix_result.test_name}")

        fix_result.verification_result = verification_result
        fix_result.verified_at = datetime.now()

        if verification_result.passed:
            fix_result.status = FixStatus.VERIFIED
            self.total_fixes_succeeded += 1
            self.logger.info(f"✅ Fix verified: {fix_result.test_name} now passes")
            return True
        else:
            fix_result.status = FixStatus.FAILED
            self.logger.warning(f"❌ Fix failed: {fix_result.test_name} still fails")
            return False

    def get_success_rate(self) -> float:
        """Calculate auto-fix success rate"""
        if self.total_fixes_attempted == 0:
            return 0.0
        return (self.total_fixes_succeeded / self.total_fixes_attempted) * 100

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _is_selector_failure(self, test_result: TestResult) -> bool:
        """Check if failure is due to selector issue"""
        if not test_result.error_message:
            return False

        error_msg_lower = test_result.error_message.lower()
        selector_keywords = [
            'selector',
            'element not found',
            'timeout',
            'waiting for',
            'did not resolve'
        ]

        return any(keyword in error_msg_lower for keyword in selector_keywords)

    def _extract_selector(self, error_message: str) -> Optional[str]:
        """Extract selector from error message"""
        # Try various patterns for selector extraction
        patterns = [
            r"selector\s+'([^']+)'",  # 'selector'
            r"selector\s+\"([^\"]+)\"",  # "selector"
            r"element\s+'([^']+)'",  # 'element'
            r"waiting for selector\s+'([^']+)'",
            r"TimeoutError:.*'([^']+)'",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_message)
            if match:
                return match.group(1)

        return None

    def _determine_fix_type(self, error_message: str, selector: str) -> Tuple[FixType, float, str]:
        """
        Determine fix type, confidence, and risk level

        Returns:
            Tuple of (fix_type, confidence, risk_level)

        Feature #183: Enhanced risk assessment for complex failures
        - Detects complex selectors (nested, nth-child, multiple matches)
        - Detects race conditions and async issues
        - Returns high/medium risk for cases requiring human intervention
        - Returns low risk only for safe, simple fixes
        """
        error_msg_lower = error_message.lower()
        selector_lower = selector.lower()

        # COMPLEX CASES: High risk - require human intervention
        # Feature #183: Detect complex selector patterns
        complex_selector_patterns = [
            'nth-child',  # Complex positional selectors
            'nth-of-type',  # Complex positional selectors
            'data-reactroot',  # React-specific selectors
            '>',  # Nested combinators (child selectors)
            '+',  # Adjacent sibling selectors
            '~',  # General sibling selectors
            '::',  # Pseudo-elements
        ]

        if any(pattern in selector_lower for pattern in complex_selector_patterns):
            self.logger.info(f"Complex selector detected: {selector[:50]}...")
            return FixType.SELECTOR_ALTERNATIVE, 0.2, 'high'

        # Multiple element matches - requires manual selector refinement
        if 'multiple elements' in error_msg_lower or 'matched multiple' in error_msg_lower:
            self.logger.info("Multiple element match detected")
            return FixType.SELECTOR_ALTERNATIVE, 0.3, 'high'

        # Complex navigation or page crashes
        if 'navigation' in error_msg_lower or 'crashed' in error_msg_lower:
            self.logger.info("Navigation/crash error detected")
            return FixType.SELECTOR_ALTERNATIVE, 0.2, 'high'

        # API/Network timeouts - medium risk (require understanding of backend)
        if 'waiting for response' in error_msg_lower or ('/api/' in error_msg_lower and 'timeout' in error_msg_lower):
            self.logger.info("API/network timeout detected")
            return FixType.TIMEOUT_INCREASE, 0.3, 'medium'

        # Race conditions or async issues
        if 'race condition' in error_msg_lower or 'async' in error_msg_lower:
            self.logger.info("Race condition detected")
            return FixType.TIMEOUT_INCREASE, 0.3, 'medium'

        # SAFE CASES: Low risk - can auto-fix
        # Check for obvious typos (high confidence, low risk)
        if 'typo' in error_msg_lower or '--' in selector or '__' in selector:
            return FixType.SELECTOR_TYPO, 0.8, 'low'

        # Check for timeout issues (medium confidence, low risk)
        # Feature #185: Use WAIT_STRATEGY for selector timeout issues
        if 'timeout' in error_msg_lower and not any(pattern in selector_lower for pattern in complex_selector_patterns):
            # For selector timeout issues, use WAIT_STRATEGY (more reliable than just increasing timeout)
            if 'selector' in error_msg_lower or 'waiting for' in error_msg_lower:
                return FixType.WAIT_STRATEGY, 0.7, 'low'
            return FixType.TIMEOUT_INCREASE, 0.6, 'low'

        # Generic selector issue (lower confidence, but still low risk if we try alternatives)
        # Feature #183: Only low risk for simple class/id selectors
        if ('selector' in error_msg_lower or 'not found' in error_msg_lower):
            # Check if selector is simple (just class or id)
            if selector.startswith('.') or selector.startswith('#'):
                # Simple selector - safe to try alternatives
                return FixType.SELECTOR_ALTERNATIVE, 0.5, 'low'
            else:
                # Complex selector - requires human intervention
                return FixType.SELECTOR_ALTERNATIVE, 0.3, 'medium'

        # Unknown issue type (low confidence, medium risk)
        return FixType.SELECTOR_ALTERNATIVE, 0.3, 'medium'

    def _fix_selector_typo(self, content: str, selector: str) -> str:
        """Fix common typos in selector"""
        # Fix common typos in the specific selector
        fixed_selector = selector

        # Pattern 1: Double hyphens to single hyphen
        if '--' in fixed_selector:
            fixed_selector = re.sub(r'-{2,}', '-', fixed_selector)

        # Pattern 2: Spaces to hyphens
        if ' ' in fixed_selector:
            fixed_selector = re.sub(r'\s+', '-', fixed_selector)

        # Pattern 3: Double underscores to single
        if '__' in fixed_selector:
            fixed_selector = re.sub(r'_{2,}', '_', fixed_selector)

        # Pattern 4: Missing hyphen between letter and number (camelCase in CSS)
        # e.g., "login2" -> "login-2", "btnSubmit" -> "btn-submit"
        fixed_selector = re.sub(r'([a-z])([A-Z])', r'\1-\2', fixed_selector)
        fixed_selector = fixed_selector.lower()  # CSS selectors are case-insensitive

        # Only replace if selector actually changed
        if fixed_selector != selector:
            # Use the enhanced replacement logic from _apply_alternative_selector
            content = self._apply_alternative_selector(content, selector, fixed_selector)

        return content

    def _apply_alternative_selector(self, content: str, old_selector: str, new_selector: str) -> str:
        """Replace old selector with new alternative selector"""
        if not new_selector:
            return content

        # Escape special regex characters in selector
        escaped_old = re.escape(old_selector)

        # Replace selector in content (handle multiple patterns)
        # Pattern 1: selector='.xxx' or selector=".xxx"
        content = content.replace(f"selector='{old_selector}'", f"selector='{new_selector}'")
        content = content.replace(f'selector="{old_selector}"', f'selector="{new_selector}"')

        # Pattern 2: Bare string selectors '.xxx' or ".xxx"
        # Use regex to replace bare strings in function calls like page.click('.xxx')
        def replace_bare_single(match):
            # Preserve the quote style
            return f"'{new_selector}'"

        def replace_bare_double(match):
            return f'"{new_selector}"'

        # Replace bare single-quoted selectors
        content = re.sub(f"'{escaped_old}'", replace_bare_single, content)
        # Replace bare double-quoted selectors
        content = re.sub(f'"{escaped_old}"', replace_bare_double, content)

        return content

    def _increase_timeout(self, content: str) -> str:
        """Increase timeout values in test"""
        # Find timeout patterns and increase by 50%
        # Match: timeout: <number>, { timeout: <number> }, waitForSelector(..., { timeout: <number> })

        def increase_timeout(match):
            timeout_value = int(match.group(1))
            increased = int(timeout_value * 1.5)
            return f"{increased}{match.group(2)}"

        # More specific patterns for timeout values
        # Pattern 1: timeout: 30000 or timeout:30000
        content = re.sub(r'timeout:\s*(\d+)(ms)?', lambda m: f"timeout: {int(m.group(1)) * 1.5}{m.group(2) or ''}", content)

        # Pattern 2: { timeout: 30000 } format
        content = re.sub(r'\{\s*timeout:\s*(\d+)(ms)?\s*\}', lambda m: f"{{ timeout: {int(m.group(1)) * 1.5}{m.group(2) or ''} }}", content)

        return content

    def _add_wait_strategy(self, content: str, selector: str) -> str:
        """
        Add wait strategies for timing-related failures

        This method adds appropriate wait strategies before element interactions
        to handle timing issues, race conditions, and slow rendering.

        Args:
            content: Original test code
            selector: The selector that's causing timing issues

        Returns:
            Modified test code with wait strategies added
        """
        lines = content.split('\n')
        modified_lines = []
        selector_escaped = re.escape(selector)

        # Pattern to match Playwright interactions with the selector
        interaction_patterns = [
            rf'\.click\([\'"]{selector_escaped}[\'"]\)',
            rf'\.fill\([\'"]{selector_escaped}[\'"]',
            rf'\.type\([\'"]{selector_escaped}[\'"]',
            rf'page\.locator\([\'"]{selector_escaped}[\'"]\)',
            rf'await page\.\$?\([\'"]{selector_escaped}[\'"]\)',
        ]

        i = 0
        while i < len(lines):
            line = lines[i]
            modified_lines.append(line)

            # Check if this line has an interaction with the problematic selector
            has_interaction = any(re.search(pattern, line) for pattern in interaction_patterns)

            if has_interaction:
                # Check if there's already a wait before this interaction
                has_wait = False
                if i > 0:
                    prev_lines = '\n'.join(lines[max(0, i-3):i])
                    has_wait = 'waitForSelector' in prev_lines or 'waitFor' in prev_lines

                if not has_wait:
                    # Determine best wait strategy based on context
                    wait_strategy = self._determine_wait_strategy(line, selector)

                    # Add wait before the interaction
                    indent = len(line) - len(line.lstrip())
                    indent_str = ' ' * indent

                    # Insert wait strategy
                    modified_lines.insert(-1, f"{indent_str}{wait_strategy}")
                    self.logger.info(f"Added wait strategy for selector: {selector}")

            i += 1

        return '\n'.join(modified_lines)

    def _determine_wait_strategy(self, interaction_line: str, selector: str) -> str:
        """
        Determine the best wait strategy for a given interaction

        Args:
            interaction_line: The line with the element interaction
            selector: The problematic selector

        Returns:
            Wait strategy code as string
        """
        # Strategy 1: waitForSelector with state (most common)
        if '.click(' in interaction_line or '.fill(' in interaction_line or '.type(' in interaction_line:
            return f"""// Auto-fix: Wait for element to be ready
await page.waitForSelector('{selector}', {{ state: 'visible', timeout: 30000 }});"""

        # Strategy 2: waitForFunction for complex conditions
        elif 'locator' in interaction_line.lower():
            return f"""// Auto-fix: Wait for element to be attached
await page.waitForSelector('{selector}', {{ state: 'attached', timeout: 30000 }});"""

        # Strategy 3: Generic wait with response check
        else:
            return f"""// Auto-fix: Wait for element
await page.waitForSelector('{selector}', {{ timeout: 30000 }});"""

    def generate_selector_suggestions(
        self,
        selector: str,
        page_content: Optional[str] = None
    ) -> List[SelectorSuggestion]:
        """
        Generate alternative selector suggestions

        Args:
            selector: Failed selector
            page_content: Optional HTML page content for analysis

        Returns:
            List of selector suggestions
        """
        suggestions = []

        # Strategy 1: Try data-testid
        if 'data-testid' not in selector.lower():
            testid_selector = f"[data-testid=\"{selector.replace('#', '').replace('.', '')}\"]"
            suggestions.append(SelectorSuggestion(
                selector=testid_selector,
                strategy='data-testid',
                confidence=0.7,
                reason='More stable than class selectors'
            ))

        # Strategy 2: Try aria-label
        if 'aria-label' not in selector.lower():
            aria_selector = f"[aria-label=\"{selector.replace('#', '').replace('.', '')}\"]"
            suggestions.append(SelectorSuggestion(
                selector=aria_selector,
                strategy='aria-label',
                confidence=0.6,
                reason='Accessibility attribute, more stable'
            ))

        # Strategy 3: Try ID (if using class)
        if selector.startswith('.'):
            id_selector = f"#{selector[1:]}"
            suggestions.append(SelectorSuggestion(
                selector=id_selector,
                strategy='id',
                confidence=0.5,
                reason='ID selectors are faster'
            ))

        return suggestions
