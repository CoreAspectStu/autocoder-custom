"""
Prerequisite Validator - Check system requirements before UAT execution

This module validates all prerequisites before running the UAT cycle:
- Dependencies (all components initialized)
- Server availability (dev server is running)
- Tool installation (Playwright, Node.js, etc.)
- Kanban API (if configured)
- File system permissions
"""

import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import OrchestratorError


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class PrerequisiteCheck:
    """Result of a single prerequisite check"""
    name: str  # e.g., "server_running", "playwright_installed"
    description: str  # Human-readable description
    passed: bool
    message: str  # Success or error message
    critical: bool = True  # If True, failure blocks execution
    duration_ms: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "description": self.description,
            "passed": self.passed,
            "message": self.message,
            "critical": self.critical,
            "duration_ms": self.duration_ms
        }


@dataclass
class ValidationResult:
    """Result of all prerequisite checks"""
    all_passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    critical_failures: int
    checks: List[PrerequisiteCheck] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "all_passed": self.all_passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "critical_failures": self.critical_failures,
            "timestamp": self.timestamp.isoformat(),
            "checks": [check.to_dict() for check in self.checks]
        }

    def get_summary(self) -> str:
        """Get human-readable summary"""
        lines = [
            "=" * 70,
            "PREREQUISITE VALIDATION",
            "=" * 70,
            f"Total: {self.passed_checks}/{self.total_checks} checks passed"
        ]

        if self.critical_failures > 0:
            lines.append(f"CRITICAL: {self.critical_failures} critical failures block execution")

        lines.append("")

        # Group checks by status
        passed = [c for c in self.checks if c.passed]
        failed = [c for c in self.checks if not c.passed]

        if passed:
            lines.append("✓ Passed checks:")
            for check in passed:
                lines.append(f"  ✓ {check.description}: {check.message}")

        if failed:
            lines.append("")
            lines.append("✗ Failed checks:")
            for check in failed:
                critical_mark = "CRITICAL " if check.critical else ""
                lines.append(f"  ✗ {critical_mark}{check.description}: {check.message}")

        lines.append("=" * 70)

        return "\n".join(lines)


# ============================================================================
# Prerequisite Validator
# ============================================================================

class PrerequisiteValidator:
    """
    Validates system prerequisites before UAT execution

    Checks:
    1. Dependencies - All required components initialized
    2. Server availability - Dev server responding
    3. Tool installation - Playwright, Node.js installed
    4. Kanban API - API reachable (if configured)
    5. File system - Read/write permissions
    """

    def __init__(self, base_url: str = "http://localhost:3000"):
        self.logger = get_logger("prerequisite_validator")
        self.base_url = base_url
        self.checks: List[PrerequisiteCheck] = []

    def validate_all(
        self,
        components: Optional[Dict[str, any]] = None,
        kanban_config: Optional[Dict[str, str]] = None
    ) -> ValidationResult:
        """
        Run all prerequisite checks

        Args:
            components: Dict of component instances to validate
            kanban_config: Optional kanban API config

        Returns:
            ValidationResult with all check results
        """
        self.logger.info("Starting prerequisite validation...")
        start_time = datetime.now()

        self.checks = []

        # Critical checks (must all pass)
        dep_check = self._check_dependencies(components)
        self.checks.append(dep_check)

        server_check = self._check_server_availability()
        self.checks.append(server_check)

        tools_check = self._check_tool_installation()
        self.checks.append(tools_check)

        fs_check = self._check_filesystem_permissions()
        self.checks.append(fs_check)

        # Optional checks (warn only)
        if kanban_config:
            kanban_check = self._check_kanban_api(kanban_config)
            self.checks.append(kanban_check)

        # Calculate results
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.passed)
        failed = total - passed
        critical_failed = sum(1 for c in self.checks if not c.passed and c.critical)

        all_passed = critical_failed == 0

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        result = ValidationResult(
            all_passed=all_passed,
            total_checks=total,
            passed_checks=passed,
            failed_checks=failed,
            critical_failures=critical_failed,
            checks=self.checks
        )

        # Log summary
        self.logger.info(result.get_summary())

        if not all_passed:
            raise OrchestratorError(
                f"Prerequisite validation failed: {critical_failed} critical failures",
                context={"validation_result": result.to_dict()}
            )

        return result

    def _check_dependencies(self, components: Optional[Dict[str, any]]) -> PrerequisiteCheck:
        """Check all required components are initialized"""
        start = datetime.now()

        if not components:
            return PrerequisiteCheck(
                name="dependencies",
                description="Component dependencies",
                passed=False,
                message="No components provided to validate",
                critical=True
            )

        required = {
            "journey_extractor": "JourneyExtractor",
            "test_generator": "TestGenerator",
            "test_executor": "TestExecutor",
            "result_processor": "ResultProcessor"
        }

        missing = []
        for key, class_name in required.items():
            if key not in components or components[key] is None:
                missing.append(class_name)

        duration_ms = (datetime.now() - start).total_seconds() * 1000

        if missing:
            return PrerequisiteCheck(
                name="dependencies",
                description="Component dependencies",
                passed=False,
                message=f"Missing components: {', '.join(missing)}",
                critical=True,
                duration_ms=duration_ms
            )

        return PrerequisiteCheck(
            name="dependencies",
            description="Component dependencies",
            passed=True,
            message=f"All {len(required)} required components initialized",
            critical=True,
            duration_ms=duration_ms
        )

    def _check_server_availability(self) -> PrerequisiteCheck:
        """Check if dev server is running and accessible"""
        start = datetime.now()

        try:
            self.logger.info(f"Checking server at {self.base_url}")
            req = urllib.request.Request(
                self.base_url,
                headers={'User-Agent': 'UAT-Gateway/1.0'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    duration_ms = (datetime.now() - start).total_seconds() * 1000
                    return PrerequisiteCheck(
                        name="server_running",
                        description="Server availability",
                        passed=True,
                        message=f"Server responding at {self.base_url}",
                        critical=True,
                        duration_ms=duration_ms
                    )
                else:
                    duration_ms = (datetime.now() - start).total_seconds() * 1000
                    return PrerequisiteCheck(
                        name="server_running",
                        description="Server availability",
                        passed=False,
                        message=f"Server returned status {response.status}",
                        critical=True,
                        duration_ms=duration_ms
                    )
        except urllib.error.URLError as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return PrerequisiteCheck(
                name="server_running",
                description="Server availability",
                passed=False,
                message=f"Server not accessible: {e}",
                critical=True,
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return PrerequisiteCheck(
                name="server_running",
                description="Server availability",
                passed=False,
                message=f"Error checking server: {e}",
                critical=True,
                duration_ms=duration_ms
            )

    def _check_tool_installation(self) -> PrerequisiteCheck:
        """Check if required tools are installed"""
        start = datetime.now()

        tools_to_check = [
            ("node", "Node.js"),
            ("npm", "npm"),
            ("playwright", "Playwright (Python)"),
        ]

        missing_tools = []
        installed_tools = []

        for cmd, name in tools_to_check:
            try:
                if cmd == "playwright":
                    # Check Python playwright (simple import check, version is optional)
                    result = subprocess.run(
                        [sys.executable, "-c", "import playwright"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        installed_tools.append(f"{name} (installed)")
                    else:
                        missing_tools.append(name)
                    if result.returncode == 0:
                        version = result.stdout.strip()
                        installed_tools.append(f"{name} {version}")
                    else:
                        missing_tools.append(name)
                else:
                    # Check system command
                    result = subprocess.run(
                        [cmd, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        version = result.stdout.strip().split('\n')[0]
                        installed_tools.append(f"{name} ({version})")
                    else:
                        missing_tools.append(name)
            except subprocess.TimeoutExpired:
                missing_tools.append(f"{name} (timeout)")
            except FileNotFoundError:
                missing_tools.append(name)
            except Exception as e:
                missing_tools.append(f"{name} ({str(e)})")

        duration_ms = (datetime.now() - start).total_seconds() * 1000

        if missing_tools:
            return PrerequisiteCheck(
                name="tool_installation",
                description="Tool installation",
                passed=False,
                message=f"Missing tools: {', '.join(missing_tools)}",
                critical=True,
                duration_ms=duration_ms
            )

        return PrerequisiteCheck(
            name="tool_installation",
            description="Tool installation",
            passed=True,
            message=f"All tools installed: {', '.join(installed_tools)}",
            critical=True,
            duration_ms=duration_ms
        )

    def _check_filesystem_permissions(self) -> PrerequisiteCheck:
        """Check if we have required filesystem permissions"""
        start = datetime.now()

        # Test write permission in current directory
        test_file = Path(".prerequisite_test")
        try:
            test_file.write_text("test")
            test_file.unlink()
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return PrerequisiteCheck(
                name="filesystem_permissions",
                description="File system permissions",
                passed=True,
                message="Read/write permissions verified",
                critical=True,
                duration_ms=duration_ms
            )
        except PermissionError as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return PrerequisiteCheck(
                name="filesystem_permissions",
                description="File system permissions",
                passed=False,
                message=f"Permission denied: {e}",
                critical=True,
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return PrerequisiteCheck(
                name="filesystem_permissions",
                description="File system permissions",
                passed=False,
                message=f"Error: {e}",
                critical=True,
                duration_ms=duration_ms
            )

    def _check_kanban_api(self, kanban_config: Dict[str, str]) -> PrerequisiteCheck:
        """Check if Kanban API is accessible (non-critical)"""
        start = datetime.now()

        api_url = kanban_config.get("api_url")
        api_token = kanban_config.get("api_token")

        if not api_url or not api_token:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return PrerequisiteCheck(
                name="kanban_api",
                description="Kanban API connectivity",
                passed=False,
                message="Kanban API not configured",
                critical=False,  # Not critical - can run without Kanban
                duration_ms=duration_ms
            )

        # Try to reach the API
        try:
            req = urllib.request.Request(
                api_url,
                headers={'Authorization': f'Bearer {api_token}'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status in [200, 401]:  # 401 means API is up, just bad token
                    duration_ms = (datetime.now() - start).total_seconds() * 1000
                    return PrerequisiteCheck(
                        name="kanban_api",
                        description="Kanban API connectivity",
                        passed=True,
                        message=f"Kanban API accessible at {api_url}",
                        critical=False,
                        duration_ms=duration_ms
                    )
                else:
                    duration_ms = (datetime.now() - start).total_seconds() * 1000
                    return PrerequisiteCheck(
                        name="kanban_api",
                        description="Kanban API connectivity",
                        passed=False,
                        message=f"API returned status {response.status}",
                        critical=False,
                        duration_ms=duration_ms
                    )
        except urllib.error.URLError as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return PrerequisiteCheck(
                name="kanban_api",
                description="Kanban API connectivity",
                passed=False,
                message=f"Kanban API not accessible: {e}",
                critical=False,
                duration_ms=duration_ms
            )
        except Exception as e:
            duration_ms = (datetime.now() - start).total_seconds() * 1000
            return PrerequisiteCheck(
                name="kanban_api",
                description="Kanban API connectivity",
                passed=False,
                message=f"Error: {e}",
                critical=False,
                duration_ms=duration_ms
            )
