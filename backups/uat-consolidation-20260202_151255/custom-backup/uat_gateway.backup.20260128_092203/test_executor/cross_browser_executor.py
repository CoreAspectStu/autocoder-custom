"""
Cross-Browser Executor - Validate browser compatibility

This module provides functionality to execute tests across multiple browsers
and generate compatibility reports showing which browsers pass/fail.

Feature #197: Cross-browser executor validates browser compatibility
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import TestExecutionError, handle_errors

# Import AsyncBrowserExecutor
try:
    from custom.uat_gateway.test_executor.test_executor import (
        AsyncBrowserExecutor,
        BrowserContextConfig,
        TestResult
    )
    ASYNC_BROWSER_AVAILABLE = True
except ImportError:
    ASYNC_BROWSER_AVAILABLE = False


class BrowserType(Enum):
    """Supported browser types for cross-browser testing"""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


@dataclass
class BrowserTestResult:
    """Result of a test execution in a specific browser"""
    browser_type: str
    test_name: str
    passed: bool
    duration_ms: int
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "browser_type": self.browser_type,
            "test_name": self.test_name,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class CompatibilityReport:
    """Report summarizing browser compatibility test results"""
    total_tests: int
    total_browsers: int
    browser_results: Dict[str, List[BrowserTestResult]]  # browser_type -> results
    compatibility_score: float  # 0.0 to 100.0
    differences: List[Dict[str, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        # Calculate pass rate per browser
        browser_stats = {}
        for browser, results in self.browser_results.items():
            passed = sum(1 for r in results if r.passed)
            total = len(results)
            browser_stats[browser] = {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": (passed / total * 100) if total > 0 else 0.0
            }

        return {
            "total_tests": self.total_tests,
            "total_browsers": self.total_browsers,
            "compatibility_score": round(self.compatibility_score, 2),
            "browser_stats": browser_stats,
            "differences": self.differences,
            "generated_at": self.generated_at.isoformat()
        }

    def get_markdown_summary(self) -> str:
        """Generate a Markdown summary of the compatibility report"""
        lines = [
            "# Cross-Browser Compatibility Report",
            f"",
            f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## Summary",
            f"",
            f"- **Total Tests:** {self.total_tests}",
            f"- **Total Browsers:** {self.total_browsers}",
            f"- **Compatibility Score:** {self.compatibility_score:.1f}%",
            f""
        ]

        # Browser-specific statistics
        lines.append("## Results by Browser")
        lines.append("")

        for browser, results in self.browser_results.items():
            passed = sum(1 for r in results if r.passed)
            total = len(results)
            pass_rate = (passed / total * 100) if total > 0 else 0.0

            status_icon = "✅" if pass_rate == 100 else "⚠️" if pass_rate >= 50 else "❌"

            lines.append(f"### {status_icon} {browser.capitalize()}")
            lines.append(f"- Passed: {passed}/{total} ({pass_rate:.1f}%)")
            lines.append("")

        # Differences between browsers
        if self.differences:
            lines.append("## Differences Detected")
            lines.append("")
            lines.append("The following tests behaved differently across browsers:")
            lines.append("")

            for diff in self.differences:
                lines.append(f"### {diff['test_name']}")
                lines.append(f"- Passed in: {', '.join(diff['passed_in'])}")
                lines.append(f"- Failed in: {', '.join(diff['failed_in'])}")
                if diff.get('error_details'):
                    lines.append(f"- Errors:")
                    for browser, error in diff['error_details'].items():
                        lines.append(f"  - {browser}: {error}")
                lines.append("")

        return "\n".join(lines)


class CrossBrowserExecutor:
    """
    Execute tests across multiple browsers and validate compatibility

    This class orchestrates test execution across multiple browser types
    (chromium, firefox, webkit) and generates compatibility reports.

    Responsibilities:
    - Run tests in multiple browsers
    - Collect results from each browser
    - Detect differences in behavior
    - Calculate compatibility score
    - Generate compatibility reports
    """

    def __init__(
        self,
        browsers: Optional[List[str]] = None,
        headless: bool = True,
        context_config: Optional[BrowserContextConfig] = None
    ):
        """
        Initialize cross-browser executor

        Args:
            browsers: List of browser types to test (default: all supported)
            headless: Whether to run browsers in headless mode
            context_config: Optional browser context configuration

        Raises:
            TestExecutionError: If AsyncBrowserExecutor is not available
        """
        if not ASYNC_BROWSER_AVAILABLE:
            raise TestExecutionError(
                "AsyncBrowserExecutor not available. Cannot run cross-browser tests.",
                component="cross_browser_executor"
            )

        self.logger = get_logger("cross_browser_executor")

        # Default to all supported browsers if none specified
        if browsers is None:
            browsers = [b.value for b in BrowserType]
        else:
            # Validate browser types
            for browser in browsers:
                if browser not in [b.value for b in BrowserType]:
                    raise TestExecutionError(
                        f"Unsupported browser type: {browser}",
                        component="cross_browser_executor",
                        context={"browser": browser, "supported": [b.value for b in BrowserType]}
                    )

        self.browsers = browsers
        self.headless = headless
        self.context_config = context_config or BrowserContextConfig()
        self.executors: Dict[str, AsyncBrowserExecutor] = {}
        self.results: Dict[str, List[BrowserTestResult]] = {}

        self.logger.info(
            f"Cross-browser executor initialized with browsers: {', '.join(browsers)}"
        )

    async def initialize_executors(self) -> None:
        """
        Initialize browser executors for all configured browsers

        Raises:
            TestExecutionError: If executor initialization fails
        """
        self.logger.info("Initializing browser executors...")

        for browser_type in self.browsers:
            try:
                executor = AsyncBrowserExecutor(
                    browser_type=browser_type,
                    headless=self.headless,
                    context_config=self.context_config
                )
                self.executors[browser_type] = executor
                self.logger.debug(f"✓ {browser_type} executor initialized")
            except Exception as e:
                raise TestExecutionError(
                    f"Failed to initialize {browser_type} executor: {str(e)}",
                    component="cross_browser_executor",
                    context={"browser": browser_type, "error": str(e)}
                )

        self.logger.info(f"✓ All {len(self.executors)} browser executors initialized")

    async def launch_browsers(self) -> None:
        """
        Launch all configured browsers

        Raises:
            TestExecutionError: If browser launch fails
        """
        self.logger.info("Launching browsers...")

        for browser_type, executor in self.executors.items():
            try:
                await executor.launch_browser()
                self.logger.info(f"✓ {browser_type} launched")
            except Exception as e:
                raise TestExecutionError(
                    f"Failed to launch {browser_type}: {str(e)}",
                    component="cross_browser_executor",
                    context={"browser": browser_type, "error": str(e)}
                )

        self.logger.info(f"✓ All {len(self.executors)} browsers launched")

    async def close_browsers(self) -> None:
        """Close all browser executors and cleanup resources"""
        self.logger.info("Closing browsers...")

        for browser_type, executor in self.executors.items():
            try:
                await executor.close_browser()
                self.logger.debug(f"✓ {browser_type} closed")
            except Exception as e:
                self.logger.warning(f"Failed to close {browser_type}: {e}")

        self.executors.clear()
        self.logger.info("All browsers closed")

    async def _run_test_in_browser(
        self,
        browser_type: str,
        executor: AsyncBrowserExecutor,
        test_name: str,
        test_func: callable,
        **kwargs
    ) -> BrowserTestResult:
        """
        Run a test in a single browser

        This helper method executes a test in one browser and is designed
        to be called in parallel via asyncio.gather().

        Args:
            browser_type: Type of browser (chromium, firefox, webkit)
            executor: Browser executor for this browser
            test_name: Name of the test
            test_func: Async test function to execute
            **kwargs: Additional arguments to pass to test function

        Returns:
            BrowserTestResult for this browser
        """
        start_time = datetime.now()

        try:
            # Execute test function with the browser's page object
            await test_func(executor.page, **kwargs)

            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            result = BrowserTestResult(
                browser_type=browser_type,
                test_name=test_name,
                passed=True,
                duration_ms=duration_ms
            )

            self.logger.info(f"✓ {browser_type}: {test_name} passed ({duration_ms}ms)")

        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            result = BrowserTestResult(
                browser_type=browser_type,
                test_name=test_name,
                passed=False,
                duration_ms=duration_ms,
                error_message=str(e)
            )

            self.logger.error(f"✗ {browser_type}: {test_name} failed - {str(e)}")

        return result

    async def run_test(
        self,
        test_name: str,
        test_func: callable,
        **kwargs
    ) -> Dict[str, BrowserTestResult]:
        """
        Run a single test across all browsers in parallel

        Tests run simultaneously across all browsers using asyncio.gather(),
        significantly reducing total execution time compared to sequential execution.

        Args:
            test_name: Name of the test
            test_func: Async test function to execute
            **kwargs: Additional arguments to pass to test function

        Returns:
            Dictionary mapping browser_type to test result
        """
        self.logger.info(f"Running test '{test_name}' across {len(self.browsers)} browsers in parallel...")

        # Create tasks for all browsers
        tasks = [
            self._run_test_in_browser(browser_type, executor, test_name, test_func, **kwargs)
            for browser_type, executor in self.executors.items()
        ]

        # Execute all tests in parallel and wait for all to complete
        results_list = await asyncio.gather(*tasks)

        # Convert list back to dictionary
        results: Dict[str, BrowserTestResult] = {}
        for result in results_list:
            results[result.browser_type] = result

            # Store in master results dict
            if result.browser_type not in self.results:
                self.results[result.browser_type] = []
            self.results[result.browser_type].append(result)

        return results

    async def run_tests(
        self,
        tests: List[Tuple[str, callable]]
    ) -> Dict[str, List[BrowserTestResult]]:
        """
        Run multiple tests across all browsers

        Args:
            tests: List of (test_name, test_func) tuples

        Returns:
            Dictionary mapping browser_type to list of test results
        """
        self.logger.info(f"Running {len(tests)} tests across {len(self.browsers)} browsers...")

        for test_name, test_func in tests:
            await self.run_test(test_name, test_func)

        total_results = sum(len(results) for results in self.results.values())
        self.logger.info(
            f"Completed {total_results} test executions "
            f"({len(tests)} tests × {len(self.browsers)} browsers)"
        )

        return self.results

    def calculate_compatibility_score(self) -> float:
        """
        Calculate overall compatibility score across all browsers and tests

        Score calculation:
        - For each test, check if it passes in ALL browsers
        - Compatibility score = (tests passing in all browsers / total tests) * 100

        Returns:
            Compatibility score from 0.0 to 100.0
        """
        if not self.results:
            return 0.0

        # Group results by test name
        test_groups: Dict[str, Dict[str, BrowserTestResult]] = {}

        for browser_type, results in self.results.items():
            for result in results:
                if result.test_name not in test_groups:
                    test_groups[result.test_name] = {}
                test_groups[result.test_name][browser_type] = result

        # Count tests that pass in ALL browsers
        tests_passing_everywhere = 0
        total_tests = len(test_groups)

        for test_name, browser_results in test_groups.items():
            # Test passes everywhere if it passes in all configured browsers
            all_passed = all(
                result.passed
                for result in browser_results.values()
            )
            if all_passed:
                tests_passing_everywhere += 1

        # Calculate score
        compatibility_score = (tests_passing_everywhere / total_tests * 100) if total_tests > 0 else 0.0

        self.logger.info(
            f"Compatibility score: {compatibility_score:.1f}% "
            f"({tests_passing_everywhere}/{total_tests} tests pass in all browsers)"
        )

        return compatibility_score

    def detect_differences(self) -> List[Dict[str, Any]]:
        """
        Detect tests that behave differently across browsers

        Returns:
            List of differences with test name, browsers where it passed/failed
        """
        differences = []

        # Group results by test name
        test_groups: Dict[str, Dict[str, BrowserTestResult]] = {}

        for browser_type, results in self.results.items():
            for result in results:
                if result.test_name not in test_groups:
                    test_groups[result.test_name] = {}
                test_groups[result.test_name][browser_type] = result

        # Find tests with different results across browsers
        for test_name, browser_results in test_groups.items():
            passed_in = [browser for browser, result in browser_results.items() if result.passed]
            failed_in = [browser for browser, result in browser_results.items() if not result.passed]

            # Test has differences if it passes in some browsers but not others
            if passed_in and failed_in:
                diff = {
                    "test_name": test_name,
                    "passed_in": passed_in,
                    "failed_in": failed_in,
                    "error_details": {}
                }

                # Add error messages from failed browsers
                for browser in failed_in:
                    if browser_results[browser].error_message:
                        diff["error_details"][browser] = browser_results[browser].error_message

                differences.append(diff)
                self.logger.warning(
                    f"Difference detected in '{test_name}': "
                    f"passed in {passed_in}, failed in {failed_in}"
                )

        return differences

    def generate_compatibility_report(self) -> CompatibilityReport:
        """
        Generate a comprehensive compatibility report

        Returns:
            CompatibilityReport with all test results, score, and differences
        """
        self.logger.info("Generating compatibility report...")

        # Calculate total unique tests
        test_names = set()
        for results in self.results.values():
            for result in results:
                test_names.add(result.test_name)
        total_tests = len(test_names)

        # Calculate compatibility score
        compatibility_score = self.calculate_compatibility_score()

        # Detect differences
        differences = self.detect_differences()

        report = CompatibilityReport(
            total_tests=total_tests,
            total_browsers=len(self.browsers),
            browser_results=self.results,
            compatibility_score=compatibility_score,
            differences=differences
        )

        self.logger.info(
            f"✓ Compatibility report generated: "
            f"{compatibility_score:.1f}% compatibility score"
        )

        return report

    async def execute_compatibility_tests(
        self,
        tests: List[Tuple[str, callable]]
    ) -> CompatibilityReport:
        """
        Execute full compatibility test workflow

        This is a convenience method that:
        1. Initializes executors
        2. Launches browsers
        3. Runs all tests
        4. Generates compatibility report
        5. Closes browsers

        Args:
            tests: List of (test_name, test_func) tuples

        Returns:
            CompatibilityReport with results

        Raises:
            TestExecutionError: If any step fails
        """
        try:
            # Initialize
            await self.initialize_executors()

            # Launch browsers
            await self.launch_browsers()

            # Run tests
            await self.run_tests(tests)

            # Generate report
            report = self.generate_compatibility_report()

            return report

        finally:
            # Always cleanup
            await self.close_browsers()


@handle_errors(component="cross_browser_executor", reraise=False)
def create_compatibility_report(
    results: Dict[str, List[BrowserTestResult]],
    browsers: List[str]
) -> CompatibilityReport:
    """
    Create a compatibility report from existing results

    This is a convenience function for creating reports without
    running the full executor workflow.

    Args:
        results: Dictionary of browser_type -> test results
        browsers: List of browser types tested

    Returns:
        CompatibilityReport
    """
    executor = CrossBrowserExecutor(browsers=browsers)
    executor.results = results

    return executor.generate_compatibility_report()
