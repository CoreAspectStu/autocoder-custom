"""
Test Executor - Execute Playwright tests and capture artifacts

This module is responsible for running Playwright tests and collecting
test artifacts including screenshots, videos, and console logs.
"""

import subprocess
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
import urllib.request
import urllib.error
import asyncio

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import TestExecutionError, handle_errors

# Feature #173: Real-time progress updates
try:
    from custom.uat_gateway.realtime.websocket_server import get_websocket_server
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False

# Feature #271: Temporary file cleanup
try:
    from custom.uat_gateway.utils.temp_file_manager import TempFileManager, CleanupConfig
    TEMP_CLEANUP_AVAILABLE = True
except ImportError:
    TEMP_CLEANUP_AVAILABLE = False

# Playwright types for type hints (only for type checking, not runtime)
if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class ConsoleMessage:
    """Represents a single console message from browser"""
    level: str  # 'error', 'warning', 'info', 'log', 'debug'
    text: str
    timestamp: float
    url: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "level": self.level,
            "text": self.text,
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat(),
            "url": self.url,
            "line": self.line,
            "column": self.column
        }


@dataclass
class TestArtifact:
    """Represents a test artifact (screenshot, video, trace, etc.)"""
    artifact_type: str  # 'screenshot', 'video', 'trace', 'console_log'
    path: str
    timestamp: datetime
    test_name: str
    scenario_type: Optional[str] = None  # 'happy_path' or 'error_path'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "artifact_type": self.artifact_type,
            "path": str(self.path),
            "timestamp": self.timestamp.isoformat(),
            "test_name": self.test_name,
            "scenario_type": self.scenario_type
        }


@dataclass
class TestResult:
    """Represents the result of a single test execution"""
    test_name: str
    passed: bool
    duration_ms: int
    error_message: Optional[str] = None
    error_stack: Optional[str] = None
    artifacts: List[TestArtifact] = field(default_factory=list)
    console_logs: List[ConsoleMessage] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    video_path: Optional[str] = None
    trace_path: Optional[str] = None
    retry_count: int = 0  # Feature #56: Number of times this test was retried
    retry_of: Optional[str] = None  # Feature #56: If this is a retry, which test is it a retry of
    journey_id: Optional[str] = None  # Feature #69: Journey this test belongs to
    timestamp: Optional[datetime] = None  # Feature #291: When the test was executed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_id": getattr(self, 'test_id', None),  # Feature #327: Include test_id if available
            "test_name": self.test_name,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "error_stack": self.error_stack,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "console_logs": [log.to_dict() for log in self.console_logs],
            "screenshot_path": str(self.screenshot_path) if self.screenshot_path else None,
            "video_path": str(self.video_path) if self.video_path else None,
            "trace_path": str(self.trace_path) if self.trace_path else None,
            "retry_count": self.retry_count,  # Feature #56
            "retry_of": self.retry_of,  # Feature #56
            "journey_id": self.journey_id,  # Feature #69
            "timestamp": self.timestamp.isoformat() if self.timestamp else None  # Feature #291
        }

    def has_console_errors(self) -> bool:
        """Check if test has any console errors"""
        return any(log.level == 'error' for log in self.console_logs)

    def has_console_warnings(self) -> bool:
        """Check if test has any console warnings"""
        return any(log.level == 'warning' for log in self.console_logs)

    def get_console_errors(self) -> List[ConsoleMessage]:
        """Get all console errors"""
        return [log for log in self.console_logs if log.level == 'error']

    def get_console_warnings(self) -> List[ConsoleMessage]:
        """Get all console warnings"""
        return [log for log in self.console_logs if log.level == 'warning']


@dataclass
class ExecutionSummary:
    """Summary of test execution results"""
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate: float
    results: List[TestResult]

    @classmethod
    def from_results(cls, results: List[TestResult]) -> "ExecutionSummary":
        """Create summary from list of test results"""
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0.0

        return cls(
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            pass_rate=pass_rate,
            results=results
        )


@dataclass
class ViewportConfig:
    """Configuration for a single viewport dimension (Feature #60)"""
    name: str  # e.g., "mobile", "tablet", "desktop"
    width: int
    height: int
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "description": self.description
        }


@dataclass
class ExecutionConfig:
    """Configuration for test execution"""
    test_directory: str = "output/tests"
    output_directory: str = "output"
    base_url: str = "http://localhost:3000"
    headless: bool = True
    browser: str = "chromium"  # chromium, firefox, webkit
    timeout_ms: int = 30000
    screenshot_on_failure: bool = True
    video_on_failure: bool = True
    trace_on_failure: bool = True
    collect_console_logs: bool = True
    parallel_workers: int = 1
    retries: int = 0
    # Feature #61: HTML report generation
    generate_html_report: bool = False  # If True, generate HTML report
    html_report_dir: str = "playwright-report"  # Directory for HTML report
    # Feature #60: Multiple viewport support for responsive testing
    viewports: List[ViewportConfig] = field(default_factory=lambda: [
        ViewportConfig(name="mobile", width=375, height=667, description="iPhone SE"),
        ViewportConfig(name="tablet", width=768, height=1024, description="iPad"),
        ViewportConfig(name="desktop", width=1920, height=1080, description="Full HD")
    ])
    enable_multi_viewport: bool = False  # If True, run tests at all viewport sizes
    # Feature #173: Real-time progress updates via WebSocket
    enable_progress_updates: bool = True  # If True, send progress updates via WebSocket
    websocket_host: str = "localhost"  # WebSocket server host
    websocket_port: int = 8001  # WebSocket server port


# ============================================================================
# Test Executor
# ============================================================================

class TestExecutor:
    """
    Executes Playwright tests and captures artifacts

    Responsibilities:
    - Verify dev server is running
    - Launch browser context
    - Run test suite
    - Capture screenshots on failure
    - Record video on failure
    - Collect console logs
    - Return structured results
    """

    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.logger = get_logger("test_executor")
        self.config = config or ExecutionConfig()
        self._test_results: List[TestResult] = []
        self._console_messages: List[ConsoleMessage] = []

        # Feature #173: WebSocket progress updates
        self._websocket_server = None
        if self.config.enable_progress_updates and WEBSOCKET_AVAILABLE:
            try:
                self._websocket_server = get_websocket_server(
                    host=self.config.websocket_host,
                    port=self.config.websocket_port
                )
                self.logger.info(
                    f"✓ WebSocket progress updates enabled "
                    f"(ws://{self.config.websocket_host}:{self.config.websocket_port})"
                )
            except Exception as e:
                self.logger.warning(f"Failed to initialize WebSocket server: {e}")
                self._websocket_server = None
        elif self.config.enable_progress_updates and not WEBSOCKET_AVAILABLE:
            self.logger.warning("WebSocket progress updates requested but websockets library not available")

        # Feature #271: Temporary file cleanup
        self._temp_file_manager = None
        if TEMP_CLEANUP_AVAILABLE:
            try:
                cleanup_config = CleanupConfig(
                    auto_cleanup_after_test=True,  # Clean up after each test run
                    max_age_days=1,  # Remove files older than 1 day
                    keep_recent_count=10  # Keep 10 most recent temp dirs
                )
                self._temp_file_manager = TempFileManager(config=cleanup_config)
                self.logger.info("✓ Temporary file cleanup enabled")
            except Exception as e:
                self.logger.warning(f"Failed to initialize temp file manager: {e}")
                self._temp_file_manager = None

    @handle_errors(component="test_executor", reraise=True)
    def verify_server_running(self, url: Optional[str] = None) -> bool:
        """
        Verify that the dev server is running

        Args:
            url: Optional URL to check (defaults to config.base_url)

        Returns:
            True if server is running, False otherwise
        """
        target_url = url or self.config.base_url

        try:
            self.logger.info(f"Checking if server is running at {target_url}")
            req = urllib.request.Request(
                target_url,
                headers={'User-Agent': 'UAT-Gateway/1.0'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    self.logger.info(f"✓ Server is running at {target_url}")
                    return True
                return False
        except urllib.error.URLError as e:
            self.logger.error(f"✗ Server not running at {target_url}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"✗ Error checking server: {e}")
            return False

    @handle_errors(component="test_executor", reraise=True)
    def run_tests(
        self,
        test_file: Optional[str] = None,
        test_pattern: Optional[str] = None,
        config_file: Optional[str] = None
    ) -> List[TestResult]:
        """
        Run Playwright tests and collect results

        Feature #55 implementation: Handles test timeouts gracefully
        Feature #60 implementation: Supports multiple viewports for responsive testing

        Args:
            test_file: Specific test file to run (optional)
            test_pattern: Pattern to match test files (optional)
            config_file: Playwright config file to use (optional)

        Returns:
            List of TestResult objects

        Raises:
            TestExecutionError: If test execution fails catastrophically
        """
        self.logger.info("Starting test execution...")

        # Feature #271: Start tracking temp files before test execution
        if self._temp_file_manager:
            self._temp_file_manager.start_test_tracking()

        # Verify server is running
        if not self.verify_server_running():
            raise TestExecutionError(
                "Dev server is not running. Please start the server before running tests.",
                component="test_executor",
                context={"base_url": self.config.base_url}
            )

        # Feature #60: Check if multi-viewport testing is enabled
        if self.config.enable_multi_viewport and len(self.config.viewports) > 0:
            return self._run_tests_multi_viewport(test_file, test_pattern, config_file)

        # Prepare output directories
        self._prepare_output_directories()

        # Build Playwright command
        cmd = self._build_playwright_command(test_file, test_pattern, config_file)

        self.logger.info(f"Running Playwright command: {' '.join(cmd)}")

        # Execute tests and capture output
        try:
            start_time = datetime.now()

            # Run Playwright tests
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_ms / 1000 + 60,  # Add buffer for test startup
                cwd=str(Path.cwd())
            )

            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            self.logger.info(f"Playwright execution completed in {duration_ms}ms")

            # Parse test results
            self._parse_test_results(result, duration_ms)

            # Collect console logs
            self._collect_console_logs()

            # Collect artifacts
            self._collect_artifacts()

            self.logger.info(
                f"Test execution complete: "
                f"{len([r for r in self._test_results if r.passed])} passed, "
                f"{len([r for r in self._test_results if not r.passed])} failed"
            )

            # Feature #271: Clean up temp files after test execution
            if self._temp_file_manager:
                cleanup_stats = self._temp_file_manager.end_test_tracking_and_cleanup()
                if cleanup_stats.cleaned_dirs > 0:
                    self.logger.info(
                        f"✓ Cleaned up {cleanup_stats.cleaned_dirs} temp directories, "
                        f"freed {cleanup_stats.freed_space_bytes / (1024*1024):.1f}MB"
                    )

            return self._test_results

        except subprocess.TimeoutExpired as e:
            # Feature #55: Handle timeout gracefully
            self.logger.error(f"Test execution timed out after {self.config.timeout_ms}ms")

            # Create a timeout result
            timeout_result = TestResult(
                test_name="test_suite_timeout",
                passed=False,
                duration_ms=self.config.timeout_ms,
                error_message=f"Test execution exceeded timeout of {self.config.timeout_ms}ms",
                error_stack="TimeoutExpired: Test suite did not complete within allocated time"
            )
            self._test_results.append(timeout_result)

            # Continue with artifact collection even on timeout
            self._collect_console_logs()
            self._collect_artifacts()

            # Feature #271: Clean up temp files even on timeout
            if self._temp_file_manager:
                cleanup_stats = self._temp_file_manager.end_test_tracking_and_cleanup()
                if cleanup_stats.cleaned_dirs > 0:
                    self.logger.info(
                        f"✓ Cleaned up {cleanup_stats.cleaned_dirs} temp directories after timeout"
                    )

            return self._test_results

        except Exception as e:
            self.logger.error(f"Test execution failed: {e}")

            # Feature #271: Clean up temp files even on error
            if self._temp_file_manager:
                try:
                    cleanup_stats = self._temp_file_manager.end_test_tracking_and_cleanup()
                    if cleanup_stats.cleaned_dirs > 0:
                        self.logger.info(
                            f"✓ Cleaned up {cleanup_stats.cleaned_dirs} temp directories after error"
                        )
                except Exception as cleanup_error:
                    self.logger.warning(f"Failed to clean up temp files: {cleanup_error}")

            raise TestExecutionError(
                f"Failed to execute tests: {str(e)}",
                component="test_executor",
                context={"error": str(e)}
            )

    def _prepare_output_directories(self) -> None:
        """Create output directories if they don't exist"""
        output_path = Path(self.config.output_directory)
        (output_path / "screenshots").mkdir(parents=True, exist_ok=True)
        (output_path / "videos").mkdir(parents=True, exist_ok=True)
        (output_path / "traces").mkdir(parents=True, exist_ok=True)
        (output_path / "console_logs").mkdir(parents=True, exist_ok=True)
        (output_path / "reports").mkdir(parents=True, exist_ok=True)

        self.logger.debug("Output directories prepared")

    def _run_tests_multi_viewport(
        self,
        test_file: Optional[str] = None,
        test_pattern: Optional[str] = None,
        config_file: Optional[str] = None
    ) -> List[TestResult]:
        """
        Run tests at multiple viewport sizes (Feature #60)

        This method executes the same test suite at each configured viewport,
        allowing for responsive design testing across different screen sizes.

        Args:
            test_file: Specific test file to run (optional)
            test_pattern: Pattern to match test files (optional)
            config_file: Playwright config file to use (optional)

        Returns:
            List of TestResult objects from all viewport executions
        """
        self.logger.info(
            f"Multi-viewport testing enabled: {len(self.config.viewports)} viewport(s)"
        )

        all_results: List[TestResult] = []

        # Run tests at each viewport
        for viewport in self.config.viewports:
            self.logger.info(
                f"Running tests at viewport: {viewport.name} "
                f"({viewport.width}x{viewport.height})"
            )

            # Create viewport-specific output directory
            viewport_output_dir = str(
                Path(self.config.output_directory) / f"viewport-{viewport.name}"
            )

            # Create a temporary config with this viewport
            temp_config = ExecutionConfig(
                test_directory=self.config.test_directory,
                output_directory=viewport_output_dir,
                base_url=self.config.base_url,
                headless=self.config.headless,
                browser=self.config.browser,
                timeout_ms=self.config.timeout_ms,
                screenshot_on_failure=self.config.screenshot_on_failure,
                video_on_failure=self.config.video_on_failure,
                trace_on_failure=self.config.trace_on_failure,
                collect_console_logs=self.config.collect_console_logs,
                parallel_workers=self.config.parallel_workers,
                retries=self.config.retries,
                viewports=[viewport],  # Single viewport for this run
                enable_multi_viewport=False  # Prevent recursion
            )

            # Create a temporary executor for this viewport
            temp_executor = TestExecutor(config=temp_config)

            # Prepare output directories for this viewport
            temp_executor._prepare_output_directories()

            # Create viewport-specific Playwright config
            viewport_config_file = temp_executor._create_viewport_playwright_config(viewport)

            # Build Playwright command with viewport-specific config
            cmd = temp_executor._build_playwright_command_with_viewport(
                viewport, test_file, test_pattern, viewport_config_file
            )

            self.logger.info(f"Running Playwright command: {' '.join(cmd)}")

            # Execute tests for this viewport
            try:
                start_time = datetime.now()

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout_ms / 1000 + 60,
                    cwd=str(Path.cwd())
                )

                end_time = datetime.now()
                duration_ms = int((end_time - start_time).total_seconds() * 1000)

                self.logger.info(
                    f"Viewport {viewport.name} execution completed in {duration_ms}ms"
                )

                # Parse test results and tag them with viewport info
                temp_executor._parse_test_results(result, duration_ms)

                # Add viewport prefix to test names
                for test_result in temp_executor._test_results:
                    test_result.test_name = f"[{viewport.name}] {test_result.test_name}"

                all_results.extend(temp_executor._test_results)

                # Collect artifacts for this viewport
                temp_executor._collect_console_logs()
                temp_executor._collect_artifacts()

            except subprocess.TimeoutExpired as e:
                self.logger.error(
                    f"Viewport {viewport.name} test execution timed out"
                )

                timeout_result = TestResult(
                    test_name=f"[{viewport.name}] test_suite_timeout",
                    passed=False,
                    duration_ms=self.config.timeout_ms,
                    error_message=f"Test execution exceeded timeout at {viewport.name} viewport",
                    timestamp=datetime.now()  # Feature #291
                )
                all_results.append(timeout_result)

            except Exception as e:
                self.logger.error(
                    f"Viewport {viewport.name} test execution failed: {e}"
                )

                error_result = TestResult(
                    test_name=f"[{viewport.name}] test_suite_error",
                    passed=False,
                    duration_ms=0,
                    error_message=str(e),
                    timestamp=datetime.now()  # Feature #291
                )
                all_results.append(error_result)

        # Merge results back into main results
        self._test_results.extend(all_results)

        # Log summary
        passed = len([r for r in all_results if r.passed])
        failed = len([r for r in all_results if not r.passed])

        self.logger.info(
            f"Multi-viewport testing complete: "
            f"{len(self.config.viewports)} viewport(s), "
            f"{passed} passed, {failed} failed"
        )

        return all_results

    def _build_playwright_command_with_viewport(
        self,
        viewport: ViewportConfig,
        test_file: Optional[str] = None,
        test_pattern: Optional[str] = None,
        config_file: Optional[str] = None
    ) -> List[str]:
        """
        Build Playwright test command with specific viewport (Feature #60)

        Args:
            viewport: Viewport configuration to use
            test_file: Specific test file to run
            test_pattern: Pattern to match test files
            config_file: Playwright config file path

        Returns:
            List of command arguments
        """
        cmd = ["npx", "playwright", "test"]

        # Add config file if specified
        if config_file:
            cmd.extend(["--config", config_file])

        # Add retry count
        if self.config.retries > 0:
            cmd.extend([f"--retries={self.config.retries}"])

        # Add specific test file if specified
        if test_file:
            cmd.append(test_file)

        # Feature #61: Add reporter configuration
        # Support multiple reporters: HTML for human viewing, JSON for parsing
        if self.config.generate_html_report:
            # Use both HTML and JSON reporters
            cmd.extend(["--reporter=html,json"])
            self.logger.info(f"HTML report generation enabled: {self.config.html_report_dir}")
        else:
            # Use only JSON reporter for programmatic parsing
            cmd.extend(["--reporter=json"])

        # Add output directory
        cmd.extend([f"--output-dir={self.config.output_directory}"])

        # Feature #60: Add viewport configuration via environment variables
        # Playwright will read these from the environment
        env_vars = {
            "VIEWPORT_WIDTH": str(viewport.width),
            "VIEWPORT_HEIGHT": str(viewport.height),
            "VIEWPORT_NAME": viewport.name
        }

        # Store env vars for subprocess execution
        # Note: These would need to be passed to subprocess.run(env=...)
        # For now, we'll create a custom playwright config file

        return cmd

    def _create_viewport_playwright_config(self, viewport: ViewportConfig) -> str:
        """
        Create a Playwright config file with specific viewport settings (Feature #60)

        Args:
            viewport: Viewport configuration

        Returns:
            Path to the created config file
        """
        config_content = f"""// Auto-generated Playwright config for viewport: {viewport.name}
// {viewport.description or 'No description'}
module.exports = {{
  use: {{
    viewport: {{ width: {viewport.width}, height: {viewport.height} }},
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  }},
  projects: [
    {{
      name: '{viewport.name}',
      use: {{
        viewport: {{ width: {viewport.width}, height: {viewport.height} }},
      }},
    }},
  ],
}}
"""

        # Write config to temporary file
        config_path = Path(self.config.output_directory) / f"playwright.config.{viewport.name}.js"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'w') as f:
            f.write(config_content)

        self.logger.debug(f"Created Playwright config: {config_path}")
        return str(config_path)

    def _build_playwright_command(
        self,
        test_file: Optional[str] = None,
        test_pattern: Optional[str] = None,
        config_file: Optional[str] = None
    ) -> List[str]:
        """
        Build Playwright test command

        Feature #56: Includes retry configuration for flaky tests
        Feature #57: Supports parallel execution with multiple workers

        Args:
            test_file: Specific test file to run
            test_pattern: Pattern to match test files
            config_file: Playwright config file path

        Returns:
            List of command arguments
        """
        cmd = ["npx", "playwright", "test"]

        # Add config file if specified
        if config_file:
            cmd.extend(["--config", config_file])

        # Feature #193: Add browser project selection for cross-browser testing
        if self.config.browser and self.config.browser in ["chromium", "firefox", "webkit"]:
            cmd.extend([f"--project={self.config.browser}"])
            self.logger.info(f"Browser selected: {self.config.browser}")

        # Feature #57: Add parallel workers configuration
        if self.config.parallel_workers > 1:
            cmd.extend([f"--workers={self.config.parallel_workers}"])
            self.logger.info(f"Parallel execution enabled with {self.config.parallel_workers} workers")
        else:
            self.logger.info(f"Sequential execution (single worker)")

        # Feature #56: Add retry count for flaky tests
        if self.config.retries > 0:
            cmd.extend([f"--retries={self.config.retries}"])
            self.logger.info(f"Configured retries: {self.config.retries}")

        # Add specific test file if specified
        if test_file:
            cmd.append(test_file)

        # Feature #61: Add reporter configuration
        # Support multiple reporters: HTML for human viewing, JSON for parsing
        if self.config.generate_html_report:
            # Use both HTML and JSON reporters
            cmd.extend(["--reporter=html,json"])
            self.logger.info(f"HTML report generation enabled: {self.config.html_report_dir}")
        else:
            # Use only JSON reporter for programmatic parsing
            cmd.extend(["--reporter=json"])

        # Add output directory (note: playwright uses --output flag, not --output-dir)
        cmd.extend(["--output", self.config.output_directory])

        return cmd

    def _detect_browser_crash(self, error_output: str) -> bool:
        """
        Detect if error output indicates a browser crash

        Feature #58: Browser crash detection

        Args:
            error_output: Error output from subprocess

        Returns:
            True if browser crash is detected, False otherwise
        """
        if not error_output:
            return False

        crash_indicators = [
            # Browser process crashes
            'browser crashed',
            'browser has been closed',
            'browser disconnected',
            'target closed',
            'segmentation fault',
            'segfault',
            'core dumped',
            # Process termination signals
            'killed',
            'terminated',
            'signal 9',  # SIGKILL
            'signal 11',  # SIGSEGV
            'signal 15',  # SIGTERM
            'signal 6',   # SIGABRT
            # Playwright-specific crash messages
            'playwright crashed',
            'browser process exited',
            'browser not launched',
            'failed to launch browser',
            # Connection errors
            'connection lost',
            'connection closed',
            'websocket closed',
            'browser connection lost'
        ]

        error_lower = error_output.lower()
        return any(indicator in error_lower for indicator in crash_indicators)

    def _parse_test_results(self, result: subprocess.CompletedProcess, duration_ms: int) -> None:
        """
        Parse Playwright test results from output

        Feature #55: Detects and marks timeout failures
        Feature #58: Detects and handles browser crashes

        Args:
            result: Subprocess result from Playwright
            duration_ms: Total execution duration
        """
        self.logger.info("Parsing test results...")

        # Try to parse JSON output from stdout
        try:
            # Playwright JSON reporter outputs a single JSON object to stdout
            # Try to parse the entire stdout as one JSON object
            try:
                test_data = json.loads(result.stdout.strip())

                # Parse test suites
                if 'suites' in test_data:
                    self._parse_test_suites(test_data['suites'], test_data.get('stats', {}))

                # Parse individual tests (if at top level)
                if 'tests' in test_data:
                    self._parse_tests(test_data['tests'], test_data.get('stats', {}))

            except json.JSONDecodeError as e:
                # If that fails, try line-by-line (for other reporter formats)
                self.logger.debug(f"Could not parse as single JSON, trying line-by-line: {e}")

                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if not line.strip():
                        continue

                    try:
                        test_data = json.loads(line)

                        # Parse test suites
                        if 'suites' in test_data:
                            self._parse_test_suites(test_data['suites'], test_data.get('stats', {}))

                        # Parse individual tests
                        if 'tests' in test_data:
                            self._parse_tests(test_data['tests'], test_data.get('stats', {}))

                    except json.JSONDecodeError:
                        # Not a JSON line, skip
                        continue

        except Exception as e:
            self.logger.warning(f"Failed to parse JSON output: {e}")

            # Fallback: Create a single result based on exit code
            # Feature #55: Detect timeout from error message
            # Feature #58: Detect browser crash from error message
            error_message = result.stderr or result.stdout

            # Check for timeout indicators
            is_timeout = any(
                indicator in error_message.lower()
                for indicator in ['timeout', 'timed out', 'exceeded timeout']
            )

            # Feature #58: Check for browser crash indicators
            is_browser_crash = self._detect_browser_crash(error_message)

            test_result = TestResult(
                test_name="test_suite",
                passed=(result.returncode == 0),
                duration_ms=duration_ms,
                error_message=error_message if result.returncode != 0 else None,
                error_stack=error_message if result.returncode != 0 else None
            )

            # Feature #55: Mark timeout clearly
            if is_timeout:
                test_result.error_message = f"Test timeout: {self.config.timeout_ms}ms exceeded"
                test_result.error_stack = "TimeoutError: Test execution exceeded the configured timeout"

            # Feature #58: Mark browser crash clearly
            if is_browser_crash:
                test_result.error_message = f"Browser crash detected: {error_message}"
                test_result.error_stack = "BrowserCrashError: " + error_message
                self.logger.error(f"Browser crash detected: {error_message}")

            self._test_results.append(test_result)

        # Feature #58: If no results were parsed, check for crashes and other errors
        if not self._test_results and result.returncode != 0:
            error_output = result.stderr or result.stdout

            # Feature #55: Detect timeout from stderr
            if 'timeout' in error_output.lower() or 'timed out' in error_output.lower():
                timeout_result = TestResult(
                    test_name="test_timeout",
                    passed=False,
                    duration_ms=duration_ms,
                    error_message=f"Test execution timed out after {duration_ms}ms",
                    error_stack="TimeoutError: " + error_output,
                    timestamp=datetime.now()  # Feature #291
                )
                self._test_results.append(timeout_result)

            # Feature #58: Detect browser crash from stderr
            elif self._detect_browser_crash(error_output):
                crash_result = TestResult(
                    test_name="test_browser_crash",
                    passed=False,
                    duration_ms=duration_ms,
                    error_message=f"Browser crash detected: {error_output}",
                    error_stack="BrowserCrashError: " + error_output,
                    timestamp=datetime.now()  # Feature #291
                )
                self._test_results.append(crash_result)
                self.logger.error("Browser crash detected and marked as failed")

            # Feature #58: Any other non-zero exit code with no output is likely a crash
            elif not result.stdout.strip() and result.returncode != 0:
                crash_result = TestResult(
                    test_name="test_execution_failed",
                    passed=False,
                    duration_ms=duration_ms,
                    error_message=f"Test execution failed with exit code {result.returncode}",
                    error_stack=error_output if error_output else f"Process exited with code {result.returncode}",
                    timestamp=datetime.now()  # Feature #291
                )
                self._test_results.append(crash_result)
                self.logger.error(f"Test execution failed with exit code {result.returncode}")

    def _parse_test_suites(self, suites: List[Dict], stats: Dict) -> None:
        """Parse test suites from JSON output"""
        for suite in suites:
            # Parse specs in suite
            if 'specs' in suite:
                for spec in suite['specs']:
                    self._parse_tests(spec.get('tests', []), stats)

    def _parse_tests(self, tests: List[Dict], stats: Dict) -> None:
        """
        Parse individual tests from JSON output

        Feature #56: Extracts retry information from test results
        """
        for test in tests:
            # Feature #55: Check for timeout in test results
            test_name = test.get('title', 'unknown')

            # Check if test passed - compare expected status with actual status
            # The 'expected' field indicates what status was expected
            # The 'results[0].status' field indicates the actual status
            expected_status = test.get('expectedStatus', 'passed')
            actual_status = test.get('results', [{}])[0].get('status', 'failed') if 'results' in test and len(test['results']) > 0 else 'failed'

            # Test passes if expected status matches actual status
            # For passing tests: expectedStatus='passed', status='passed'
            # For skipped tests: expectedStatus='skipped', status='skipped'
            # Test fails if they don't match or if status is 'failed'/'timedOut'
            passed = (
                actual_status == 'passed' or
                (expected_status == 'skipped' and actual_status == 'skipped') or
                test.get('ok', False)  # The 'ok' field directly indicates pass/fail
            )

            # Get duration from test results
            duration_ms = 0
            if 'results' in test and len(test['results']) > 0:
                duration_ms = test['results'][0].get('duration', 0)

            # Feature #56: Extract retry information
            retry_count = test.get('retry', 0)  # Playwright provides this
            retry_of = None  # Could be derived from test annotations if needed

            # Get error information
            error_message = None
            error_stack = None

            if not passed and 'results' in test and len(test['results']) > 0:
                result = test['results'][0]

                # Check for timeout in errors
                if 'errors' in result:
                    errors = result['errors']
                    if errors:
                        error_message = errors[0].get('message', 'Test failed')
                        error_stack = errors[0].get('stack', '')

                        # Feature #55: Detect timeout from error message
                        if 'timeout' in error_message.lower():
                            error_message = f"Test timed out after {duration_ms}ms"
                            error_stack = f"TimeoutError: {error_message}"

            test_result = TestResult(
                test_name=test_name,
                passed=passed,
                duration_ms=int(duration_ms),
                error_message=error_message,
                error_stack=error_stack,
                retry_count=retry_count,  # Feature #56
                retry_of=retry_of,  # Feature #56
                timestamp=datetime.now()  # Feature #291
            )

            self._test_results.append(test_result)

            # Feature #56: Log retry information
            log_msg = f"Parsed test result: {test_name} - {'PASSED' if passed else 'FAILED'}"
            if retry_count > 0:
                log_msg += f" (retry {retry_count})"
            self.logger.debug(log_msg)

    @handle_errors(component="test_executor", reraise=False)
    def _collect_console_logs(self) -> None:
        """
        Collect console logs from browser during test execution

        This method collects console messages that were captured during
        test execution and associates them with the appropriate test results.
        """
        self.logger.info("Collecting console logs...")

        # Look for console log files in output directory
        console_logs_dir = Path(self.config.output_directory) / "console_logs"

        if not console_logs_dir.exists():
            self.logger.warning("Console logs directory not found")
            return

        # Find all console log JSON files
        log_files = list(console_logs_dir.glob("*.json"))

        if not log_files:
            self.logger.info("No console log files found")
            return

        # Process each log file
        for log_file in log_files:
            try:
                with open(log_file, 'r') as f:
                    log_data = json.load(f)

                # Extract test name from filename
                test_name = log_file.stem

                # Find matching test result
                test_result = None
                for result in self._test_results:
                    if test_name in result.test_name:
                        test_result = result
                        break

                # Parse console messages
                if "console_logs" in log_data:
                    for msg_data in log_data["console_logs"]:
                        console_msg = ConsoleMessage(
                            level=msg_data.get("level", "info"),
                            text=msg_data.get("text", ""),
                            timestamp=msg_data.get("timestamp", datetime.now().timestamp()),
                            url=msg_data.get("url"),
                            line=msg_data.get("line"),
                            column=msg_data.get("column")
                        )

                        # Add to test result if found, otherwise store globally
                        if test_result:
                            test_result.console_logs.append(console_msg)
                        else:
                            self._console_messages.append(console_msg)

                self.logger.debug(f"Collected {len(log_data.get('console_logs', []))} console messages from {log_file.name}")

            except Exception as e:
                self.logger.error(f"Error reading console log file {log_file}: {e}")

        self.logger.info(f"Collected console logs from {len(log_files)} test(s)")

    def _collect_artifacts(self) -> None:
        """Collect test artifacts (screenshots, videos, traces)"""
        self.logger.info("Collecting test artifacts...")

        output_path = Path(self.config.output_directory)

        # Collect screenshots
        screenshots_dir = output_path / "screenshots"
        if screenshots_dir.exists():
            for screenshot_path in screenshots_dir.glob("*.png"):
                # Find matching test result
                test_name = screenshot_path.stem
                for result in self._test_results:
                    if test_name in result.test_name or result.test_name in test_name:
                        result.screenshot_path = str(screenshot_path)
                        result.artifacts.append(TestArtifact(
                            artifact_type="screenshot",
                            path=str(screenshot_path),
                            timestamp=datetime.fromtimestamp(screenshot_path.stat().st_mtime),
                            test_name=result.test_name
                        ))
                        break

        # Collect videos
        videos_dir = output_path / "videos"
        if videos_dir.exists():
            for video_path in videos_dir.glob("*.webm"):
                test_name = video_path.stem
                for result in self._test_results:
                    if test_name in result.test_name or result.test_name in test_name:
                        result.video_path = str(video_path)
                        result.artifacts.append(TestArtifact(
                            artifact_type="video",
                            path=str(video_path),
                            timestamp=datetime.fromtimestamp(video_path.stat().st_mtime),
                            test_name=result.test_name
                        ))
                        break

        # Collect traces
        traces_dir = output_path / "traces"
        if traces_dir.exists():
            for trace_path in traces_dir.glob("*.zip"):
                test_name = trace_path.stem
                for result in self._test_results:
                    if test_name in result.test_name or result.test_name in test_name:
                        result.trace_path = str(trace_path)
                        result.artifacts.append(TestArtifact(
                            artifact_type="trace",
                            path=str(trace_path),
                            timestamp=datetime.fromtimestamp(trace_path.stat().st_mtime),
                            test_name=result.test_name
                        ))
                        break

        self.logger.info(f"Collected artifacts for {len([r for r in self._test_results if r.artifacts])} test(s)")

    def get_test_results(self) -> List[TestResult]:
        """Get all test results"""
        return self._test_results

    def get_console_messages(self) -> List[ConsoleMessage]:
        """Get all collected console messages"""
        return self._console_messages

    def get_console_errors(self) -> List[ConsoleMessage]:
        """Get all console errors across all tests"""
        return [
            msg for msg in self._console_messages
            if msg.level == 'error'
        ]

    def get_console_warnings(self) -> List[ConsoleMessage]:
        """Get all console warnings across all tests"""
        return [
            msg for msg in self._console_messages
            if msg.level == 'warning'
        ]

    def generate_report(self) -> Dict[str, Any]:
        """Generate a summary report of test execution"""
        total_tests = len(self._test_results)
        passed_tests = len([r for r in self._test_results if r.passed])
        failed_tests = total_tests - passed_tests

        # Count console issues
        total_errors = sum(len(r.get_console_errors()) for r in self._test_results)
        total_warnings = sum(len(r.get_console_warnings()) for r in self._test_results)

        report = {
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "pass_rate": f"{(passed_tests / total_tests * 100):.1f}%" if total_tests > 0 else "0%",
                "total_console_errors": total_errors,
                "total_console_warnings": total_warnings
            },
            "test_results": [r.to_dict() for r in self._test_results],
            "console_logs": [msg.to_dict() for msg in self._console_messages],
            "timestamp": datetime.now().isoformat()
        }

        return report

    def save_report(self, output_path: Optional[str] = None) -> str:
        """
        Save test execution report to file

        Args:
            output_path: Optional path to save report (defaults to output/reports/test-report.json)

        Returns:
            Path to saved report file
        """
        if output_path is None:
            output_path = str(Path(self.config.output_directory) / "reports" / "test-report.json")

        report = self.generate_report()

        # Ensure directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Write report
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)

        self.logger.info(f"Test report saved to {output_path}")
        return output_path


# ============================================================================
# Async Browser Context Management (Feature #49)
# ============================================================================

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
    PLAYWRIGHT_ASYNC_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_ASYNC_AVAILABLE = False


@dataclass
class BrowserContextConfig:
    """Configuration for browser context creation"""
    viewport_width: int = 1280
    viewport_height: int = 720
    locale: str = "en-US"
    timezone_id: str = "America/New_York"
    user_agent: Optional[str] = None
    bypass_csp: bool = False
    ignore_https_errors: bool = False
    accept_downloads: bool = False
    java_script_enabled: bool = True


@dataclass
class AsyncExecutionContext:
    """Context for async test execution"""
    browser: Optional[Any] = None
    browser_context: Optional[Any] = None
    page: Optional[Any] = None
    playwright: Optional[Any] = None
    base_url: str = "http://localhost:3000"


class AsyncBrowserExecutor:
    """
    Async browser executor for direct Playwright control (Feature #49)

    This class provides async methods for launching browsers and creating contexts
    with specific configurations (viewport, locale, timezone).

    Responsibilities:
    - Launch browser instances (chromium, firefox, webkit)
    - Create browser contexts with proper settings
    - Configure viewport dimensions
    - Configure locale for internationalization
    - Configure timezone for time-sensitive tests
    - Manage browser lifecycle
    """

    def __init__(self,
                 browser_type: str = "chromium",
                 headless: bool = True,
                 context_config: Optional[BrowserContextConfig] = None):
        """
        Initialize async browser executor

        Args:
            browser_type: Type of browser (chromium, firefox, webkit)
            headless: Whether to run browser in headless mode
            context_config: Optional browser context configuration

        Raises:
            TestExecutionError: If Playwright is not available
        """
        if not PLAYWRIGHT_ASYNC_AVAILABLE:
            raise TestExecutionError(
                "Playwright async API not available. Install with: pip install playwright",
                component="test_executor"
            )

        self.browser_type = browser_type
        self.headless = headless
        self.context_config = context_config or BrowserContextConfig()
        self.logger = get_logger("test_executor")
        self._playwright_context = None
        self._browser = None
        self._browser_context = None
        self._page = None

    async def launch_browser(self) -> AsyncExecutionContext:
        """
        Launch browser and create context with proper settings

        Feature #49 implementation:
        - Launches browser instance
        - Creates browser context
        - Configures viewport
        - Configures locale
        - Configures timezone

        Returns:
            AsyncExecutionContext with browser and page objects

        Raises:
            TestExecutionError: If browser launch fails
        """
        self.logger.info(f"Launching {self.browser_type} browser...")

        # Start Playwright
        playwright = await async_playwright().start()
        self._playwright_context = playwright

        # Launch browser based on type
        if self.browser_type.lower() == "chromium":
            browser = await playwright.chromium.launch(headless=self.headless)
        elif self.browser_type.lower() == "firefox":
            browser = await playwright.firefox.launch(headless=self.headless)
        elif self.browser_type.lower() == "webkit":
            browser = await playwright.webkit.launch(headless=self.headless)
        else:
            raise TestExecutionError(
                f"Unsupported browser type: {self.browser_type}",
                component="test_executor",
                context={"browser_type": self.browser_type}
            )

        self._browser = browser
        self.logger.info(f"Browser launched: {self.browser_type}")

        # Create context with configuration
        context = await browser.new_context(
            viewport={
                "width": self.context_config.viewport_width,
                "height": self.context_config.viewport_height
            },
            locale=self.context_config.locale,
            timezone_id=self.context_config.timezone_id,
            user_agent=self.context_config.user_agent,
            bypass_csp=self.context_config.bypass_csp,
            ignore_https_errors=self.context_config.ignore_https_errors,
            accept_downloads=self.context_config.accept_downloads,
            java_script_enabled=self.context_config.java_script_enabled,
        )

        self._browser_context = context
        self.logger.info(
            f"Browser context created: "
            f"viewport={self.context_config.viewport_width}x{self.context_config.viewport_height}, "
            f"locale={self.context_config.locale}, "
            f"timezone={self.context_config.timezone_id}"
        )

        # Create page
        page = await context.new_page()
        self._page = page
        self.logger.info("Browser page created")

        # Return execution context
        return AsyncExecutionContext(
            browser=browser,
            browser_context=context,
            page=page,
            playwright=playwright
        )

    async def close_browser(self) -> None:
        """Close browser and cleanup resources"""
        if self._page:
            await self._page.close()
            self.logger.debug("Page closed")

        if self._browser_context:
            await self._browser_context.close()
            self.logger.debug("Browser context closed")

        if self._browser:
            await self._browser.close()
            self.logger.debug("Browser closed")

        if self._playwright_context:
            await self._playwright_context.stop()
            self.logger.debug("Playwright stopped")

        # Reset references
        self._page = None
        self._browser_context = None
        self._browser = None
        self._playwright_context = None

        self.logger.info("Browser and all resources cleaned up")

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> None:
        """
        Navigate to a URL

        Args:
            url: URL to navigate to
            wait_until: When to consider navigation succeeded

        Raises:
            TestExecutionError: If navigation fails or browser not launched
        """
        if not self._page:
            raise TestExecutionError(
                "Browser not launched. Call launch_browser() first",
                component="test_executor"
            )

        self.logger.info(f"Navigating to: {url}")

        try:
            await self._page.goto(url, wait_until=wait_until)
            self.logger.info(f"Successfully navigated to: {url}")
        except Exception as e:
            raise TestExecutionError(
                f"Failed to navigate to {url}: {str(e)}",
                component="test_executor",
                context={"url": url, "error": str(e)}
            )

    async def screenshot(self, path: str) -> None:
        """
        Capture screenshot of current page

        Args:
            path: Path where screenshot will be saved

        Raises:
            TestExecutionError: If screenshot fails
        """
        if not self._page:
            raise TestExecutionError(
                "Browser not launched. Call launch_browser() first",
                component="test_executor"
            )

        try:
            await self._page.screenshot(path=path)
            self.logger.info(f"Screenshot saved: {path}")
        except Exception as e:
            raise TestExecutionError(
                f"Failed to capture screenshot: {str(e)}",
                component="test_executor"
            )

    @property
    def is_launched(self) -> bool:
        """Check if browser is currently launched"""
        return self._browser is not None

    @property
    def page(self) -> Optional[Any]:
        """Get the current page object"""
        return self._page

    @property
    def context(self) -> Optional[Any]:
        """Get the current browser context"""
        return self._browser_context

    async def clear_browser_state(self) -> None:
        """
        Clear all browser state between tests (Feature #59)

        This method ensures no state leaks between tests by clearing:
        - All cookies
        - All localStorage data
        - All sessionStorage data

        Raises:
            TestExecutionError: If browser context is not available
        """
        if not self._browser_context:
            raise TestExecutionError(
                "Browser context not available. Call launch_browser() first",
                component="test_executor"
            )

        self.logger.info("Clearing browser state between tests...")

        # Clear all cookies
        await self._browser_context.clear_cookies()
        self.logger.debug("✓ Cookies cleared")

        # Clear localStorage
        await self._page.evaluate("""() => {
            window.localStorage.clear();
        }""")
        self.logger.debug("✓ localStorage cleared")

        # Clear sessionStorage
        await self._page.evaluate("""() => {
            window.sessionStorage.clear();
        }""")
        self.logger.debug("✓ sessionStorage cleared")

        self.logger.info("Browser state cleared successfully")

    async def get_cookies(self) -> List[Dict[str, Any]]:
        """
        Get all cookies from current browser context

        Returns:
            List of cookie dictionaries

        Raises:
            TestExecutionError: If browser context is not available
        """
        if not self._browser_context:
            raise TestExecutionError(
                "Browser context not available. Call launch_browser() first",
                component="test_executor"
            )

        cookies = await self._browser_context.cookies()
        return cookies

    async def get_local_storage_items(self) -> Dict[str, str]:
        """
        Get all items from localStorage

        Returns:
            Dictionary of localStorage key-value pairs

        Raises:
            TestExecutionError: If page is not available
        """
        if not self._page:
            raise TestExecutionError(
                "Page not available. Call launch_browser() first",
                component="test_executor"
            )

        storage = await self._page.evaluate("""() => {
            const items = {};
            for (let i = 0; i < window.localStorage.length; i++) {
                const key = window.localStorage.key(i);
                items[key] = window.localStorage.getItem(key);
            }
            return items;
        }""")

        return storage

    async def get_session_storage_items(self) -> Dict[str, str]:
        """
        Get all items from sessionStorage

        Returns:
            Dictionary of sessionStorage key-value pairs

        Raises:
            TestExecutionError: If page is not available
        """
        if not self._page:
            raise TestExecutionError(
                "Page not available. Call launch_browser() first",
                component="test_executor"
            )

        storage = await self._page.evaluate("""() => {
            const items = {};
            for (let i = 0; i < window.sessionStorage.length; i++) {
                const key = window.sessionStorage.key(i);
                items[key] = window.sessionStorage.getItem(key);
            }
            return items;
        }""")

        return storage

    async def set_viewport(self, width: int, height: int) -> None:
        """
        Set viewport size dynamically (Feature #60)

        This method allows changing the viewport size during test execution,
        which is useful for testing responsive designs at multiple screen sizes.

        Args:
            width: Viewport width in pixels
            height: Viewport height in pixels

        Raises:
            TestExecutionError: If page is not available
        """
        if not self._page:
            raise TestExecutionError(
                "Page not available. Call launch_browser() first",
                component="test_executor"
            )

        await self._page.set_viewport_size({"width": width, "height": height})
        self.logger.info(f"Viewport set to {width}x{height}")

    async def get_viewport_size(self) -> Dict[str, int]:
        """
        Get current viewport size (Feature #60)

        Returns:
            Dictionary with 'width' and 'height' keys

        Raises:
            TestExecutionError: If page is not available
        """
        if not self._page:
            raise TestExecutionError(
                "Page not available. Call launch_browser() first",
                component="test_executor"
            )

        viewport_size = await self._page.evaluate("""() => {
            return {
                width: window.innerWidth,
                height: window.innerHeight
            };
        }""")

        return viewport_size
