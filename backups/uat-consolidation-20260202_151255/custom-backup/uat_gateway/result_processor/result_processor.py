"""
Result Processor - Process test results and determine next actions

This module is responsible for:
- Calculating pass rates
- Identifying failure patterns
- Detecting flaky tests
- Generating summary reports
- Determining action (notify/retry/fix)
- Creating bug cards for failures
"""

import sys
import json
from pathlib import Path
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import Counter, defaultdict
import re

# Add parent directory to path for imports

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import TestExecutionError, handle_errors
from uat_gateway.test_executor.test_executor import TestResult, ConsoleMessage


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class FailurePattern:
    """Represents a pattern of test failures"""
    pattern_name: str  # e.g., 'selector_not_found', 'timeout', 'assertion_failed'
    count: int
    affected_tests: List[str]
    common_error_message: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "pattern_name": self.pattern_name,
            "count": self.count,
            "affected_tests": self.affected_tests,
            "common_error_message": self.common_error_message,
            "suggestion": self.suggestion
        }


@dataclass
class PassRateMetrics:
    """Pass/fail rate metrics for test results"""
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate: float  # Percentage (0-100)
    fail_rate: float  # Percentage (0-100)
    pass_rate_formatted: str  # e.g., "75.5%"
    fail_rate_formatted: str  # e.g., "24.5%"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "pass_rate": round(self.pass_rate, 2),
            "fail_rate": round(self.fail_rate, 2),
            "pass_rate_formatted": self.pass_rate_formatted,
            "fail_rate_formatted": self.fail_rate_formatted
        }


@dataclass
class FlakyTest:
    """Represents a test that produces inconsistent results"""
    test_name: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    flaky_score: float  # 0-100, higher = more flaky
    variance: str  # 'low', 'medium', 'high'
    suggestion: Optional[str] = None  # Feature #204: Suggestion for fixing flakiness

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "total_runs": self.total_runs,
            "passed_runs": self.passed_runs,
            "failed_runs": self.failed_runs,
            "flaky_score": round(self.flaky_score, 2),
            "variance": self.variance,
            "suggestion": self.suggestion  # Feature #204
        }


@dataclass
class Bug:
    """Represents a bug found during testing"""
    bug_id: str  # Unique identifier
    test_name: str  # Test that found this bug
    failure_type: str  # e.g., 'selector_not_found', 'timeout', 'assertion_failed', 'network_error'
    severity: str  # 'critical', 'high', 'medium', 'low'
    priority: int  # 1-10, 1 is highest priority
    error_message: Optional[str] = None
    suggestion: Optional[str] = None
    estimated_fix_time_minutes: Optional[int] = None  # Feature #72: Estimated time to fix (in minutes)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "bug_id": self.bug_id,
            "test_name": self.test_name,
            "failure_type": self.failure_type,
            "severity": self.severity,
            "priority": self.priority,
            "error_message": self.error_message,
            "suggestion": self.suggestion,
            "estimated_fix_time_minutes": self.estimated_fix_time_minutes,  # Feature #72
            "status": self.status.value,
            "fixed_at": self.fixed_at.isoformat() if self.fixed_at else None,
            "fixed_by": self.fixed_by,
            "fix_notes": self.fix_notes,
            "created_at": self.created_at.isoformat()
        }



class BugCardStatus(Enum):
    """Status of a bug card through its lifecycle"""
    OPEN = "open"  # Bug newly created
    IN_PROGRESS = "in_progress"  # Someone is working on it
    FIXED = "fixed"  # Fix has been implemented, awaiting verification
    VERIFIED = "verified"  # Fix has been verified by tests
    CLOSED = "closed"  # Bug is fully resolved and documented
    REOPENED = "reopened"  # Bug was marked fixed but tests failed again


@dataclass
class BugCard:
    """Enhanced bug report with artifacts and assignment information (Feature #67)"""
    card_id: str  # Unique identifier (e.g., "BUG-CARD-20250126-001")
    test_name: str  # Test that found this bug
    failure_type: str  # e.g., 'selector_not_found', 'timeout', 'assertion_failed', 'network_error'
    severity: str  # 'critical', 'high', 'medium', 'low'
    priority: int  # 1-10, 1 is highest priority
    error_message: Optional[str] = None
    suggestion: Optional[str] = None
    screenshot_path: Optional[str] = None  # Path to failure screenshot
    video_path: Optional[str] = None  # Path to failure video recording
    trace_path: Optional[str] = None  # Path to Playwright trace file
    assignee: Optional[str] = None  # Assigned developer/team
    labels: List[str] = field(default_factory=list)  # Labels for categorization
    status: BugCardStatus = BugCardStatus.OPEN  # Feature #89: Current status
    fixed_at: Optional[datetime] = None  # Feature #89: When fix was implemented
    fixed_by: Optional[str] = None  # Feature #89: Who fixed the bug
    fix_notes: Optional[str] = None  # Feature #89: Notes about the fix
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "card_id": self.card_id,
            "test_name": self.test_name,
            "failure_type": self.failure_type,
            "severity": self.severity,
            "priority": self.priority,
            "error_message": self.error_message,
            "suggestion": self.suggestion,
            "screenshot_path": self.screenshot_path,
            "video_path": self.video_path,
            "trace_path": self.trace_path,
            "assignee": self.assignee,
            "labels": self.labels,
            "status": self.status.value,
            "fixed_at": self.fixed_at.isoformat() if self.fixed_at else None,
            "fixed_by": self.fixed_by,
            "fix_notes": self.fix_notes,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class JourneyResult:
    """Represents aggregated results for a single journey - Feature #69"""
    journey_id: str
    journey_name: Optional[str] = None
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    pass_rate: float = 0.0  # Percentage (0-100)
    fail_rate: float = 0.0  # Percentage (0-100)
    status: str = "unknown"  # 'passed', 'failed', 'mixed'
    test_names: List[str] = field(default_factory=list)  # Names of tests in this journey
    total_duration_ms: int = 0  # Total duration of all tests in this journey

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "journey_id": self.journey_id,
            "journey_name": self.journey_name,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "pass_rate": round(self.pass_rate, 2),
            "fail_rate": round(self.fail_rate, 2),
            "status": self.status,
            "test_names": self.test_names,
            "total_duration_ms": self.total_duration_ms
        }


@dataclass
class PassRateSnapshot:
    """Historical snapshot of pass rates - Feature #70"""
    timestamp: datetime
    pass_rate: float  # Percentage (0-100)
    total_tests: int
    passed_tests: int
    failed_tests: int
    run_id: Optional[str] = None  # Identifier for this test run

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "pass_rate": round(self.pass_rate, 2),
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "run_id": self.run_id
        }


@dataclass
class TrendAnalysis:
    """Analysis of pass rate trends over time - Feature #70"""
    trend_direction: str  # 'improving', 'stable', 'regressing'
    trend_percentage: float  # Percentage change (positive = improvement)
    current_pass_rate: float
    baseline_pass_rate: float  # Average of historical data
    snapshot_count: int  # Number of historical snapshots
    is_significant: bool  # Whether trend is statistically significant
    confidence: float  # Confidence level (0-1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "trend_direction": self.trend_direction,
            "trend_percentage": round(self.trend_percentage, 2),
            "current_pass_rate": round(self.current_pass_rate, 2),
            "baseline_pass_rate": round(self.baseline_pass_rate, 2),
            "snapshot_count": self.snapshot_count,
            "is_significant": self.is_significant,
            "confidence": round(self.confidence, 2)
        }


@dataclass
class KnownIssue:
    """Represents a known bug or issue that should not trigger new alerts - Feature #71"""
    issue_id: str  # Unique identifier (e.g., "KNOWN-001")
    test_name: str  # Test that triggers this issue
    failure_type: str  # e.g., 'selector_not_found', 'timeout', 'assertion_failed', 'network_error'
    error_signature: str  # Unique signature to match failures (e.g., error message pattern)
    severity: str  # 'critical', 'high', 'medium', 'low'
    status: str  # 'open', 'in_progress', 'resolved', 'wontfix'
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None  # Additional context about the issue
    occurrence_count: int = 0  # How many times this issue has occurred

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "issue_id": self.issue_id,
            "test_name": self.test_name,
            "failure_type": self.failure_type,
            "error_signature": self.error_signature,
            "severity": self.severity,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "notes": self.notes,
            "occurrence_count": self.occurrence_count
        }

    def matches_failure(self, test_result: 'TestResult') -> bool:
        """
        Check if this known issue matches a test failure

        Args:
            test_result: Test result to check

        Returns:
            True if this issue matches the failure
        """
        if test_result.passed:
            return False

        # Check test name
        if test_result.test_name != self.test_name:
            return False

        # Check if error signature matches
        if test_result.error_message and self.error_signature:
            return self.error_signature.lower() in test_result.error_message.lower()

        # Check failure type if no signature match
        if hasattr(test_result, 'failure_type') and test_result.failure_type:
            return test_result.failure_type == self.failure_type

        return False


@dataclass
class QuarantinedTest:
    """Represents a test that has been quarantined due to consistent flakiness - Feature #203"""
    test_name: str  # Name of the quarantined test
    quarantine_id: str  # Unique identifier (e.g., "QUARANTINE-001")
    flaky_score: float  # Flaky score at time of quarantine (0-100)
    total_runs: int  # Total runs before quarantine
    passed_runs: int  # Passed runs before quarantine
    failed_runs: int  # Failed runs before quarantine
    variance: str  # 'low', 'medium', 'high'
    quarantined_at: datetime = field(default_factory=datetime.now)
    reason: str = "Consistently flaky test"
    resolved_at: Optional[datetime] = None  # When test was removed from quarantine
    notes: Optional[str] = None  # Additional context about the quarantine

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "quarantine_id": self.quarantine_id,
            "flaky_score": round(self.flaky_score, 2),
            "total_runs": self.total_runs,
            "passed_runs": self.passed_runs,
            "failed_runs": self.failed_runs,
            "variance": self.variance,
            "quarantined_at": self.quarantined_at.isoformat(),
            "reason": self.reason,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "notes": self.notes
        }


@dataclass
class FlakyHealthSnapshot:
    """Historical snapshot of flaky test health - Feature #205"""
    timestamp: datetime  # When this snapshot was taken
    flaky_count: int  # Number of flaky tests at this time
    flaky_percentage: float  # Percentage of tests that are flaky (0-100)
    total_tests: int  # Total number of tests

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "flaky_count": self.flaky_count,
            "flaky_percentage": round(self.flaky_percentage, 2),
            "total_tests": self.total_tests
        }


@dataclass
class FlakyHealthReport:
    """Overall health report for flaky tests - Feature #205"""
    flaky_count: int  # Current number of flaky tests
    flaky_percentage: float  # Current percentage of flaky tests (0-100)
    flaky_percentage_formatted: str  # Formatted string (e.g., "25.5%")
    total_tests: int  # Total number of tests
    trend_direction: str  # 'improving', 'stable', 'worsening', 'unknown'
    trend_percentage: float  # Percentage change in flakiness (negative = improvement)
    health_status: str  # 'excellent', 'good', 'fair', 'poor', 'critical'
    historical_snapshots: List[FlakyHealthSnapshot]  # Historical data points
    snapshot_count: int  # Number of historical snapshots
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "flaky_count": self.flaky_count,
            "flaky_percentage": round(self.flaky_percentage, 2),
            "flaky_percentage_formatted": self.flaky_percentage_formatted,
            "total_tests": self.total_tests,
            "trend_direction": self.trend_direction,
            "trend_percentage": round(self.trend_percentage, 2),
            "health_status": self.health_status,
            "historical_snapshots": [s.to_dict() for s in self.historical_snapshots],
            "snapshot_count": self.snapshot_count,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ProcessedResult:
    """Complete processed result with metrics and patterns"""
    metrics: PassRateMetrics
    failure_patterns: List[FailurePattern]
    flaky_tests: List[FlakyTest]
    action: str  # 'notify', 'retry', 'fix'
    reason: str
    bugs: List[Bug] = field(default_factory=list)  # Feature #68: prioritized bugs
    journey_results: List[JourneyResult] = field(default_factory=list)  # Feature #69: Journey-level aggregation
    trend_analysis: Optional[TrendAnalysis] = None  # Feature #70: Historical trend analysis
    known_issues: List[KnownIssue] = field(default_factory=list)  # Feature #71: Known issues that were filtered out
    new_failures: List[TestResult] = field(default_factory=list)  # Feature #71: Failures not matching known issues
    performance_regressions: List = field(default_factory=list)  # Feature #188: performance regressions
    quarantined_tests: List[QuarantinedTest] = field(default_factory=list)  # Feature #203: Quarantined flaky tests
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "metrics": self.metrics.to_dict(),
            "failure_patterns": [p.to_dict() for p in self.failure_patterns],
            "flaky_tests": [t.to_dict() for t in self.flaky_tests],
            "action": self.action,
            "reason": self.reason,
            "bugs": [b.to_dict() for b in self.bugs],  # Feature #68
            "journey_results": [j.to_dict() for j in self.journey_results],  # Feature #69
            "known_issues": [k.to_dict() for k in self.known_issues],  # Feature #71
            "new_failure_count": len(self.new_failures),  # Feature #71
            "quarantined_tests": [q.to_dict() for q in self.quarantined_tests],  # Feature #203
            "timestamp": self.timestamp.isoformat()
        }
        # Add trend analysis if available (Feature #70)
        if self.trend_analysis:
            result["trend_analysis"] = self.trend_analysis.to_dict()
        return result


# ============================================================================
# Result Processor
# ============================================================================

class ResultProcessor:
    """
    Process test results and determine next actions

    Responsibilities:
    - Calculate pass/fail rates
    - Identify failure patterns
    - Detect flaky tests
    - Generate summary reports
    - Determine action (notify/retry/fix)
    - Detect performance regressions (Feature #188)
    """

    def __init__(self):
        self.logger = get_logger("result_processor")
        self._test_history: Dict[str, List[TestResult]] = defaultdict(list)
        self._known_issues: List[KnownIssue] = []  # Feature #71: Known issues database
        self._pass_rate_history: List[PassRateSnapshot] = []  # Feature #70: Historical pass rates
        self._known_issues_file = Path("state/known_issues.json")  # Feature #71: Persistence
        # self._load_known_issues()  # Feature #71: Load known issues on startup (TODO: implement)

        # Feature #188: Performance detector
        from uat_gateway.result_processor.performance_detector import PerformanceDetector
        self.performance_detector = PerformanceDetector(slowdown_threshold=50.0)

        # Feature #203: Quarantine management
        self._quarantined_tests: List[QuarantinedTest] = []  # Quarantined flaky tests
        self._quarantine_file = Path("state/quarantined_tests.json")  # Persistence

        # Feature #205: Flaky health tracking
        self._flaky_health_history: List[FlakyHealthSnapshot] = []  # Historical flaky health data

    @handle_errors(component="result_processor", reraise=True)
    def calculate_pass_rates(self, results: List[TestResult]) -> PassRateMetrics:
        """
        Calculate pass/fail rates from test results

        Feature #62 implementation:
        - Run test suite with mixed results
        - Process results
        - Verify pass rate is calculated
        - Verify fail rate is calculated
        - Verify calculations are accurate
        - Verify rates are percentages

        Args:
            results: List of test results

        Returns:
            PassRateMetrics object with calculated rates

        Raises:
            TestExecutionError: If results list is empty
        """
        if not results:
            raise TestExecutionError(
                "Cannot calculate pass rates from empty results list",
                component="result_processor"
            )

        self.logger.info(f"Calculating pass rates from {len(results)} test results...")

        # Count passed and failed tests
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.passed)
        failed_tests = total_tests - passed_tests

        # Calculate rates as percentages
        pass_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0.0
        fail_rate = (failed_tests / total_tests) * 100 if total_tests > 0 else 0.0

        # Format as strings with 1 decimal place
        pass_rate_formatted = f"{pass_rate:.1f}%"
        fail_rate_formatted = f"{fail_rate:.1f}%"

        metrics = PassRateMetrics(
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            pass_rate=pass_rate,
            fail_rate=fail_rate,
            pass_rate_formatted=pass_rate_formatted,
            fail_rate_formatted=fail_rate_formatted
        )

        self.logger.info(
            f"Pass rates calculated: "
            f"{passed_tests}/{total_tests} passed ({pass_rate_formatted}), "
            f"{failed_tests}/{total_tests} failed ({fail_rate_formatted})"
        )

        return metrics

    @handle_errors(component="result_processor", reraise=False)
    def identify_failure_patterns(self, results: List[TestResult]) -> List[FailurePattern]:
        """
        Identify common patterns in test failures

        Args:
            results: List of test results

        Returns:
            List of FailurePattern objects
        """
        self.logger.info("Identifying failure patterns...")

        failed_tests = [r for r in results if not r.passed]

        if not failed_tests:
            self.logger.info("No failed tests to analyze")
            return []

        patterns: List[FailurePattern] = []

        # Pattern 1: Selector not found
        selector_failures = []
        for test in failed_tests:
            if test.error_message and any(
                keyword in test.error_message.lower()
                for keyword in ['selector', 'not found', 'waiting for selector']
            ):
                selector_failures.append(test.test_name)

        if selector_failures:
            patterns.append(FailurePattern(
                pattern_name="selector_not_found",
                count=len(selector_failures),
                affected_tests=selector_failures,
                common_error_message="Element selector not found or timed out",
                suggestion="Verify selectors are correct and elements exist in DOM"
            ))

        # Pattern 2: Timeout failures
        timeout_failures = []
        for test in failed_tests:
            if test.error_message and 'timeout' in test.error_message.lower():
                timeout_failures.append(test.test_name)

        if timeout_failures:
            patterns.append(FailurePattern(
                pattern_name="timeout",
                count=len(timeout_failures),
                affected_tests=timeout_failures,
                common_error_message="Test execution exceeded timeout",
                suggestion="Increase timeout or optimize test execution"
            ))

        # Pattern 3: Assertion failures
        assertion_failures = []
        for test in failed_tests:
            if test.error_message and any(
                keyword in test.error_message.lower()
                for keyword in ['assert', 'expected', 'received']
            ):
                assertion_failures.append(test.test_name)

        if assertion_failures:
            patterns.append(FailurePattern(
                pattern_name="assertion_failed",
                count=len(assertion_failures),
                affected_tests=assertion_failures,
                common_error_message="Assertion condition not met",
                suggestion="Review test expectations and application behavior"
            ))

        # Pattern 4: Network errors
        network_failures = []
        for test in failed_tests:
            if test.error_message and any(
                keyword in test.error_message.lower()
                for keyword in ['network', 'connection', 'fetch', '404', '500']
            ):
                network_failures.append(test.test_name)

        if network_failures:
            patterns.append(FailurePattern(
                pattern_name="network_error",
                count=len(network_failures),
                affected_tests=network_failures,
                common_error_message="Network request failed",
                suggestion="Check server status and API endpoints"
            ))

        self.logger.info(f"Identified {len(patterns)} failure patterns")

        # Sort by count (most common first)
        patterns.sort(key=lambda p: p.count, reverse=True)

        return patterns

    def _determine_severity(self, failure_type: str, error_message: Optional[str] = None) -> str:
        """
        Determine severity level based on failure type and error message

        Feature #68: Severity levels
        - Critical: Data corruption, security issues, complete feature failure
        - High: Core functionality broken, API failures
        - Medium: UI issues, edge cases, timeouts
        - Low: Cosmetic issues, minor text problems

        Args:
            failure_type: Type of failure (e.g., 'selector_not_found', 'timeout')
            error_message: Optional error message for additional context

        Returns:
            Severity level: 'critical', 'high', 'medium', or 'low'
        """
        error_msg_lower = error_message.lower() if error_message else ""

        # Critical failures
        if failure_type == 'network_error':
            if any(keyword in error_msg_lower for keyword in ['500', 'database', 'corruption', 'security']):
                return 'critical'
            return 'high'

        if failure_type == 'assertion_failed':
            if any(keyword in error_msg_lower for keyword in ['authentication', 'authorization', 'security', 'permission']):
                return 'critical'
            if any(keyword in error_msg_lower for keyword in ['data', 'save', 'delete', 'update', 'create']):
                return 'high'
            return 'medium'

        # UI failures are generally medium priority (Feature #68)
        if failure_type == 'selector_not_found':
            # UI element failures - medium priority per Feature #68 requirements
            return 'medium'

        # Medium/Low priority failures
        if failure_type == 'timeout':
            # Timeouts are often transient
            return 'medium'

        # Default to medium
        return 'medium'

    def _severity_to_priority(self, severity: str) -> int:
        """
        Convert severity level to numeric priority (1-10, 1 is highest)

        Feature #68: Priority mapping
        - critical → 1-3
        - high → 4-6
        - medium → 7-8
        - low → 9-10

        Args:
            severity: Severity level string

        Returns:
            Numeric priority (1-10)
        """
        priority_map = {
            'critical': 2,  # Highest priority
            'high': 5,
            'medium': 8,
            'low': 10  # Lowest priority
        }
        return priority_map.get(severity, 8)  # Default to medium (8)


    def _estimate_fix_time(self, failure_type: str, severity: str, error_message: Optional[str] = None) -> int:
        """
        Estimate time to fix a bug in minutes

        Feature #72 implementation:
        - Simple failures (selector issues, simple assertions) have low estimates
        - Complex failures (network errors, critical issues) have high estimates
        - Estimates are based on failure type, severity, and error context

        Estimation logic:
        - selector_not_found: 10-30 minutes (simple selector fix)
        - timeout: 15-45 minutes (may require debugging performance)
        - assertion_failed: 20-60 minutes (depends on complexity)
        - network_error: 30-120 minutes (backend/API investigation)
        - unknown: 45-90 minutes (investigation needed)

        Severity multipliers:
        - low: 0.5x (quick cosmetic fix)
        - medium: 1.0x (standard fix time)
        - high: 1.5x (complex fix)
        - critical: 2.0x (critical system issue)

        Args:
            failure_type: Type of failure (e.g., 'selector_not_found', 'timeout')
            severity: Severity level ('critical', 'high', 'medium', 'low')
            error_message: Optional error message for additional context

        Returns:
            Estimated fix time in minutes
        """
        # Base time estimates for each failure type (in minutes)
        base_estimates = {
            'selector_not_found': 15,  # Simple selector fix
            'timeout': 30,  # May require debugging performance or increasing timeout
            'assertion_failed': 30,  # Depends on assertion complexity
            'network_error': 60,  # Backend/API investigation needed
            'unknown': 60  # Investigation required
        }

        # Get base estimate
        base_time = base_estimates.get(failure_type, 60)

        # Apply severity multiplier
        severity_multipliers = {
            'low': 0.5,
            'medium': 1.0,
            'high': 1.5,
            'critical': 2.0
        }
        multiplier = severity_multipliers.get(severity, 1.0)

        # Calculate estimated time
        estimated_time = int(base_time * multiplier)

        # Adjust based on error message context
        error_msg_lower = error_message.lower() if error_message else ""

        # Reduce time for obvious/simple issues
        if any(keyword in error_msg_lower for keyword in ['typo', 'spelling', 'capitalization', 'whitespace']):
            estimated_time = max(5, int(estimated_time * 0.3))  # Quick fix

        # Increase time for complex issues
        if any(keyword in error_msg_lower for keyword in ['database', 'migration', 'schema', 'authentication', 'authorization']):
            estimated_time = int(estimated_time * 1.5)  # Complex backend issue

        if any(keyword in error_msg_lower for keyword in ['race', 'intermittent', 'flaky', 'random']):
            estimated_time = int(estimated_time * 2.0)  # Hard to reproduce

        # Ensure minimum and maximum bounds
        estimated_time = max(5, min(estimated_time, 240))  # 5 min to 4 hours

        return estimated_time

    @handle_errors(component="result_processor", reraise=True)
    def create_bug_cards(self, results: List[TestResult]) -> List[BugCard]:
        """
        Create bug cards from test failures with artifacts and assignment info

        Feature #67 implementation:
        - Process failed test results
        - Create bug card for each failure
        - Include error details
        - Include screenshot/video/trace paths
        - Assign to appropriate developer/team
        - Add labels for categorization

        Args:
            results: List of test results

        Returns:
            List of BugCard objects sorted by priority (highest first)
        """
        self.logger.info("Creating bug cards from failures...")

        failed_tests = [r for r in results if not r.passed]
        bug_cards: List[BugCard] = []

        for idx, test in enumerate(failed_tests):
            # Determine failure type
            failure_type = 'unknown'
            if test.error_message:
                error_msg_lower = test.error_message.lower()
                if 'timeout' in error_msg_lower:
                    failure_type = 'timeout'
                elif any(keyword in error_msg_lower for keyword in ['selector', 'not found']):
                    failure_type = 'selector_not_found'
                elif any(keyword in error_msg_lower for keyword in ['assert', 'expected', 'received']):
                    failure_type = 'assertion_failed'
                elif any(keyword in error_msg_lower for keyword in ['network', 'connection', 'fetch', '404', '500']):
                    failure_type = 'network_error'

            # Determine severity
            severity = self._determine_severity(failure_type, test.error_message)

            # Calculate priority
            priority = self._severity_to_priority(severity)

            # Generate bug card ID
            card_id = f"BUG-CARD-{datetime.now().strftime('%Y%m%d')}-{idx + 1:03d}"

            # Generate suggestion based on failure type
            suggestions = {
                'selector_not_found': "Verify selector is correct and element exists in DOM",
                'timeout': "Increase timeout or optimize test execution",
                'assertion_failed': "Review test expectations and application behavior",
                'network_error': "Check server status and API endpoints",
                'unknown': "Investigate test failure and root cause"
            }
            suggestion = suggestions.get(failure_type, suggestions['unknown'])

            # Determine assignee based on failure type
            assignee_map = {
                'selector_not_found': 'frontend-team',
                'timeout': 'qa-team',
                'assertion_failed': 'frontend-team',
                'network_error': 'backend-team',
                'unknown': 'triage'
            }
            assignee = assignee_map.get(failure_type, 'triage')

            # Generate labels
            labels = [
                failure_type,
                severity,
                'automated-test-failure'
            ]

            # Add additional labels based on context
            if test.error_message:
                error_msg_lower = test.error_message.lower()
                if 'login' in error_msg_lower or 'auth' in error_msg_lower:
                    labels.append('authentication')
                if 'payment' in error_msg_lower or 'checkout' in error_msg_lower:
                    labels.append('payment')
                if 'api' in error_msg_lower:
                    labels.append('api')

            # Create bug card
            bug_card = BugCard(
                card_id=card_id,
                test_name=test.test_name,
                failure_type=failure_type,
                severity=severity,
                priority=priority,
                error_message=test.error_message,
                suggestion=suggestion,
                screenshot_path=test.screenshot_path,
                video_path=test.video_path,
                trace_path=test.trace_path,
                assignee=assignee,
                labels=labels
            )
            bug_cards.append(bug_card)

        # Sort by priority (lower number = higher priority)
        bug_cards.sort(key=lambda card: card.priority)

        self.logger.info(f"Created {len(bug_cards)} bug cards, sorted by priority")

        return bug_cards

    def create_bugs_from_failures(self, results: List[TestResult]) -> List[Bug]:
        """
        Create bug reports from test failures with severity and priority

        Feature #68 implementation:
        - Process various failures
        - Assign severity based on failure type
        - Calculate priority from severity
        - Generate actionable bug reports

        Args:
            results: List of test results

        Returns:
            List of Bug objects sorted by priority (highest first)
        """
        self.logger.info("Creating bug reports from failures...")

        failed_tests = [r for r in results if not r.passed]
        bugs: List[Bug] = []

        for idx, test in enumerate(failed_tests):
            # Determine failure type
            failure_type = 'unknown'
            if test.error_message:
                error_msg_lower = test.error_message.lower()
                if 'timeout' in error_msg_lower:
                    failure_type = 'timeout'
                elif any(keyword in error_msg_lower for keyword in ['selector', 'not found']):
                    failure_type = 'selector_not_found'
                elif any(keyword in error_msg_lower for keyword in ['assert', 'expected', 'received']):
                    failure_type = 'assertion_failed'
                elif any(keyword in error_msg_lower for keyword in ['network', 'connection', 'fetch', '404', '500']):
                    failure_type = 'network_error'

            # Determine severity
            severity = self._determine_severity(failure_type, test.error_message)

            # Calculate priority
            priority = self._severity_to_priority(severity)

            # Generate bug ID
            bug_id = f"BUG-{datetime.now().strftime('%Y%m%d')}-{idx + 1:03d}"

            # Generate suggestion based on failure type
            suggestions = {
                'selector_not_found': "Verify selector is correct and element exists in DOM",
                'timeout': "Increase timeout or optimize test execution",
                'assertion_failed': "Review test expectations and application behavior",
                'network_error': "Check server status and API endpoints",
                'unknown': "Investigate test failure and root cause"
            }
            suggestion = suggestions.get(failure_type, suggestions['unknown'])

            # Estimate fix time (Feature #72)
            estimated_time = self._estimate_fix_time(failure_type, severity, test.error_message)

            # Create bug
            bug = Bug(
                bug_id=bug_id,
                test_name=test.test_name,
                failure_type=failure_type,
                severity=severity,
                priority=priority,
                error_message=test.error_message,
                suggestion=suggestion,
                estimated_fix_time_minutes=estimated_time  # Feature #72
            )
            bugs.append(bug)

        # Sort by priority (lower number = higher priority)
        bugs.sort(key=lambda b: b.priority)

        self.logger.info(f"Created {len(bugs)} bug reports, sorted by priority")

        return bugs

    @handle_errors(component="result_processor", reraise=False)
    def prioritize_bugs(self, bugs: List[Bug]) -> Dict[str, List[Bug]]:
        """
        Prioritize and group bugs by severity level

        Feature #68 implementation:
        - Check bug priorities
        - Verify critical failures get high priority (1-3)
        - Verify UI failures get medium priority (7-8)
        - Verify minor failures get low priority (9-10)

        Args:
            bugs: List of Bug objects

        Returns:
            Dictionary grouping bugs by severity level:
            {
                'critical': [Bug, ...],
                'high': [Bug, ...],
                'medium': [Bug, ...],
                'low': [Bug, ...]
            }
        """
        self.logger.info(f"Prioritizing {len(bugs)} bugs by severity...")

        # Group bugs by severity
        prioritized: Dict[str, List[Bug]] = {
            'critical': [],
            'high': [],
            'medium': [],
            'low': []
        }

        for bug in bugs:
            severity = bug.severity
            if severity in prioritized:
                prioritized[severity].append(bug)
            else:
                # Unknown severity - treat as medium
                prioritized['medium'].append(bug)

        # Sort each group by priority (lower number = higher priority)
        for severity in prioritized:
            prioritized[severity].sort(key=lambda b: b.priority)

        # Log summary
        for severity in ['critical', 'high', 'medium', 'low']:
            count = len(prioritized[severity])
            if count > 0:
                self.logger.info(f"  {severity.upper()}: {count} bugs")

        return prioritized

    def _generate_flaky_test_suggestion(
        self,
        test_name: str,
        history: List[TestResult],
        flaky_score: float,
        variance: str
    ) -> str:
        """
        Generate actionable suggestion for fixing a flaky test

        Feature #204 implementation:
        - Analyzes failure patterns in test history
        - Identifies root cause of flakiness
        - Provides specific, actionable suggestions

        Args:
            test_name: Name of the flaky test
            history: Historical test results
            flaky_score: Flakiness score (0-100)
            variance: Variance level ('low', 'medium', 'high')

        Returns:
            Actionable suggestion for fixing the flaky test
        """
        # Analyze error messages from failed runs
        failed_runs = [r for r in history if not r.passed]
        error_messages = [r.error_message for r in failed_runs if r.error_message]

        # Count error types
        timeout_count = sum(1 for msg in error_messages if msg and 'timeout' in msg.lower())
        selector_count = sum(1 for msg in error_messages if msg and any(kw in msg.lower() for kw in ['selector', 'not found', 'waiting']))
        network_count = sum(1 for msg in error_messages if msg and any(kw in msg.lower() for kw in ['network', 'connection', 'fetch']))
        assertion_count = sum(1 for msg in error_messages if msg and any(kw in msg.lower() for kw in ['assert', 'expected', 'received']))

        # Analyze duration variance
        durations = [r.duration_ms for r in history]
        if durations:
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
            duration_variance = max_duration - avg_duration
        else:
            avg_duration = 0
            duration_variance = 0

        # Generate suggestion based on root cause analysis
        suggestion_parts = []

        # High variance with high flaky score suggests timing issues
        if variance == 'high' and flaky_score > 60:
            if timeout_count > 0:
                suggestion_parts.append("Test indicates timing-related flakiness, likely caused by race conditions with element loading.")

                # Check for high duration variance
                if duration_variance > avg_duration * 0.5:
                    suggestion_parts.append(
                        "Execution time varies significantly (+{:.0f}ms variance). "
                        "Add explicit waits (waitForSelector, waitForResponse) instead of fixed timeouts. "
                        "Consider using page.waitForLoadState('networkidle') for dynamic content."
                        .format(duration_variance)
                    )
                else:
                    suggestion_parts.append(
                        "Increase timeout or add retry logic with exponential backoff. "
                        "Use test.setTimeout() to extend default timeout for this test."
                    )

            elif selector_count > 0:
                suggestion_parts.append("Test fails intermittently due to selector issues.")
                suggestion_parts.append(
                    "Elements may not be ready when test runs. Add explicit waits: "
                    "await page.waitForSelector('selector', { state: 'attached' }) or "
                    "await page.waitForSelector('selector', { state: 'visible' }). "
                    "Verify selectors are stable and don't use dynamic attributes."
                )

        # Medium variance suggests race conditions or environmental issues
        elif variance == 'medium' or flaky_score >= 40:
            if network_count > 0:
                suggestion_parts.append("Test exhibits network-related flakiness.")
                suggestion_parts.append(
                    "API calls may be unreliable. Implement retry logic with exponential backoff. "
                    "Mock external API responses in tests using MSW (Mock Service Worker). "
                    "Add waitForResponse() to ensure API calls complete before assertions."
                )

            elif assertion_count > 0:
                suggestion_parts.append("Test fails intermittently on assertions.")
                suggestion_parts.append(
                    "Check for race conditions in application state. Add explicit waits before assertions. "
                    "Verify test data is properly isolated between runs. "
                    "Use expect(value).toBe(expected) with proper retries or soft assertions."
                )

            else:
                suggestion_parts.append("Test shows moderate flakiness with inconsistent failures.")
                suggestion_parts.append(
                    "Run test in isolation to identify dependencies on other tests. "
                    "Ensure proper test cleanup and teardown. "
                    "Check for shared state or database contamination between test runs."
                )

        # Low variance suggests occasional environmental issues
        elif variance == 'low':
            suggestion_parts.append("Test shows low-level flakiness.")
            suggestion_parts.append(
                "Failures may be due to resource contention or environmental issues. "
                "Run tests with --workers=1 flag to eliminate race conditions. "
                "Ensure adequate system resources (CPU, memory) during test execution. "
                "Check for background processes that may interfere with test execution."
            )

        # Default fallback suggestion
        if not suggestion_parts:
            suggestion_parts.append("Test exhibits inconsistent behavior across runs.")
            suggestion_parts.append(
                "Review test for asynchronous operations, timers, or external dependencies. "
                "Add explicit synchronization points and ensure deterministic test execution. "
                "Consider quarantining this test if flakiness persists after investigation."
            )

        # Combine suggestion parts
        full_suggestion = " ".join(suggestion_parts)

        # Add actionable next steps
        if flaky_score > 70:
            full_suggestion += " HIGH PRIORITY: Test is highly flaky (score: {:.1f}). Consider immediate investigation or quarantine.".format(flaky_score)
        elif flaky_score > 50:
            full_suggestion += " MEDIUM PRIORITY: Test shows significant flakiness (score: {:.1f}). Schedule investigation.".format(flaky_score)

        return full_suggestion

    @handle_errors(component="result_processor", reraise=False)
    def detect_flaky_tests(self, results: List[TestResult]) -> List[FlakyTest]:
        """
        Detect flaky tests from historical data

        Feature #204: Now includes suggestions for fixing flaky tests

        Args:
            results: List of test results (current run)

        Returns:
            List of FlakyTest objects with suggestions
        """
        self.logger.info("Detecting flaky tests...")

        flaky_tests: List[FlakyTest] = []

        # Update history with current results
        for result in results:
            self._test_history[result.test_name].append(result)

        # Analyze each test in history
        for test_name, history in self._test_history.items():
            if len(history) < 2:
                # Need at least 2 runs to detect flakiness
                continue

            total_runs = len(history)
            passed_runs = sum(1 for r in history if r.passed)
            failed_runs = total_runs - passed_runs

            # Calculate flaky score (0-100)
            # 0 = always passes or always fails (not flaky)
            # 100 = passes 50% of the time (maximum flakiness)
            pass_ratio = passed_runs / total_runs
            flaky_score = 100 * (1 - abs(pass_ratio - 0.5) * 2)  # Peaks at 50% pass rate

            # Determine variance level
            if flaky_score < 20:
                variance = 'low'
            elif flaky_score < 50:
                variance = 'medium'
            else:
                variance = 'high'

            # Only consider it flaky if score is significant
            if flaky_score >= 20:
                # Feature #204: Generate suggestion for this flaky test
                suggestion = self._generate_flaky_test_suggestion(
                    test_name, history, flaky_score, variance
                )

                flaky_tests.append(FlakyTest(
                    test_name=test_name,
                    total_runs=total_runs,
                    passed_runs=passed_runs,
                    failed_runs=failed_runs,
                    flaky_score=flaky_score,
                    variance=variance,
                    suggestion=suggestion  # Feature #204
                ))

        # Sort by flaky score (most flaky first)
        flaky_tests.sort(key=lambda t: t.flaky_score, reverse=True)

        self.logger.info(f"Detected {len(flaky_tests)} flaky tests with suggestions")

        return flaky_tests

    @handle_errors(component="result_processor", reraise=True)
    def determine_action(self, metrics: PassRateMetrics, patterns: List[FailurePattern]) -> Tuple[str, str]:
        """
        Determine next action based on results

        Args:
            metrics: Pass rate metrics
            patterns: Failure patterns

        Returns:
            Tuple of (action, reason) where action is 'notify', 'retry', or 'fix'
        """
        self.logger.info("Determining next action...")

        # Action logic:
        # - 'notify': Pass rate >= 80%, no critical failures
        # - 'retry': Pass rate 60-79%, or has timeout failures (may be transient)
        # - 'fix': Pass rate < 60%, or has selector/network failures (need code changes)

        if metrics.pass_rate >= 80:
            # Good enough to notify human
            action = 'notify'
            reason = f"Pass rate {metrics.pass_rate_formatted} meets threshold for human review"

        elif metrics.pass_rate >= 60:
            # Check if failures are likely transient (timeouts)
            has_timeouts = any(p.pattern_name == 'timeout' for p in patterns)
            has_selector_issues = any(p.pattern_name == 'selector_not_found' for p in patterns)

            if has_timeouts and not has_selector_issues:
                action = 'retry'
                reason = f"Pass rate {metrics.pass_rate_formatted} with timeout failures - may be transient, retrying"
            else:
                action = 'fix'
                reason = f"Pass rate {metrics.pass_rate_formatted} requires investigation and fixes"

        else:
            # Too many failures - need fixes
            action = 'fix'
            reason = f"Pass rate {metrics.pass_rate_formatted} below acceptable threshold - fixes required"

        self.logger.info(f"Action determined: {action} - {reason}")

        return action, reason

    @handle_errors(component="result_processor", reraise=False)
    def aggregate_by_journey(self, results: List[TestResult]) -> List[JourneyResult]:
        """
        Aggregate test results by journey

        Feature #69 implementation:
        - Process test results
        - Check journey grouping
        - Verify results are grouped by journey
        - Verify journey-level stats exist
        - Verify journey status is calculated

        Args:
            results: List of test results (each should have journey_id set)

        Returns:
            List of JourneyResult objects, one per journey
        """
        self.logger.info("Aggregating results by journey...")

        # Group results by journey_id
        journey_groups: Dict[str, List[TestResult]] = defaultdict(list)
        tests_without_journey = []

        for result in results:
            if result.journey_id:
                journey_groups[result.journey_id].append(result)
            else:
                tests_without_journey.append(result)

        if tests_without_journey:
            self.logger.warning(
                f"Found {len(tests_without_journey)} tests without journey_id"
            )

        # Create JourneyResult for each journey
        journey_results: List[JourneyResult] = []

        for journey_id, journey_tests in journey_groups.items():
            total_tests = len(journey_tests)
            passed_tests = sum(1 for t in journey_tests if t.passed)
            failed_tests = total_tests - passed_tests

            # Calculate rates
            pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0
            fail_rate = (failed_tests / total_tests * 100) if total_tests > 0 else 0.0

            # Determine status
            if passed_tests == total_tests:
                status = "passed"
            elif failed_tests == total_tests:
                status = "failed"
            else:
                status = "mixed"

            # Calculate total duration
            total_duration_ms = sum(t.duration_ms for t in journey_tests)

            # Get test names
            test_names = [t.test_name for t in journey_tests]

            journey_result = JourneyResult(
                journey_id=journey_id,
                journey_name=None,  # Could be enhanced to look up journey name
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                pass_rate=pass_rate,
                fail_rate=fail_rate,
                status=status,
                test_names=test_names,
                total_duration_ms=total_duration_ms
            )

            journey_results.append(journey_result)

        # Sort by journey_id for consistency
        journey_results.sort(key=lambda j: j.journey_id)

        self.logger.info(
            f"Aggregated {len(results)} tests into {len(journey_results)} journeys"
        )

        return journey_results

    @handle_errors(component="result_processor", reraise=False)
    def track_pass_rate_snapshot(
        self,
        metrics: PassRateMetrics,
        run_id: Optional[str] = None
    ) -> PassRateSnapshot:
        """
        Store a snapshot of current pass rates for historical tracking

        Feature #70 implementation:
        - Create snapshot from metrics
        - Store in history
        - Return snapshot for reference

        Args:
            metrics: Current pass rate metrics
            run_id: Optional identifier for this test run

        Returns:
            PassRateSnapshot object
        """
        snapshot = PassRateSnapshot(
            timestamp=datetime.now(),
            pass_rate=metrics.pass_rate,
            total_tests=metrics.total_tests,
            passed_tests=metrics.passed_tests,
            failed_tests=metrics.failed_tests,
            run_id=run_id
        )

        self._pass_rate_history.append(snapshot)
        self.logger.info(
            f"Tracked pass rate snapshot: {metrics.pass_rate_formatted} "
            f"({len(self._pass_rate_history)} total snapshots)"
        )

        return snapshot

    @handle_errors(component="result_processor", reraise=False)
    def get_pass_rate_history(self, limit: Optional[int] = None) -> List[PassRateSnapshot]:
        """
        Retrieve historical pass rate snapshots

        Feature #70 implementation:
        - Return all or limited history
        - Most recent first

        Args:
            limit: Optional maximum number of snapshots to return

        Returns:
            List of PassRateSnapshot objects, most recent first
        """
        history = self._pass_rate_history.copy()
        # Reverse to get most recent first
        history.reverse()

        if limit:
            history = history[:limit]

        return history

    @handle_errors(component="result_processor", reraise=False)
    def analyze_trends(self, current_pass_rate: float) -> Optional[TrendAnalysis]:
        """
        Analyze pass rate trends over time

        Feature #70 implementation:
        - Check historical data exists
        - Calculate baseline (average)
        - Determine trend direction
        - Calculate percentage change
        - Assess significance

        Args:
            current_pass_rate: Current pass rate (0-100)

        Returns:
            TrendAnalysis object if historical data exists, None otherwise
        """
        if len(self._pass_rate_history) < 2:
            self.logger.info(
                f"Insufficient historical data for trend analysis "
                f"({len(self._pass_rate_history)} snapshots)"
            )
            return None

        # Get historical pass rates (excluding current)
        historical_rates = [s.pass_rate for s in self._pass_rate_history]

        # Calculate baseline (average)
        baseline = sum(historical_rates) / len(historical_rates)

        # Calculate percentage change
        if baseline > 0:
            trend_percentage = ((current_pass_rate - baseline) / baseline) * 100
        else:
            trend_percentage = 0.0

        # Determine trend direction
        if trend_percentage > 5:
            trend_direction = 'improving'
        elif trend_percentage < -5:
            trend_direction = 'regressing'
        else:
            trend_direction = 'stable'

        # Assess significance based on magnitude and consistency
        # Significant if: 10%+ change OR consistent directional change
        is_significant = abs(trend_percentage) >= 10

        # Calculate confidence based on sample size
        # More snapshots = higher confidence
        snapshot_count = len(self._pass_rate_history)
        confidence = min(0.5 + (snapshot_count * 0.1), 0.95)

        analysis = TrendAnalysis(
            trend_direction=trend_direction,
            trend_percentage=trend_percentage,
            current_pass_rate=current_pass_rate,
            baseline_pass_rate=baseline,
            snapshot_count=snapshot_count,
            is_significant=is_significant,
            confidence=confidence
        )

        self.logger.info(
            f"Trend analysis: {trend_direction} ({trend_percentage:+.1f}%), "
            f"baseline={baseline:.1f}%, "
            f"significant={is_significant}"
        )

        return analysis

    @handle_errors(component="result_processor", reraise=False)
    def detect_improvement(self, current_pass_rate: float) -> bool:
        """
        Detect if current pass rate shows improvement over historical baseline

        Feature #70 implementation:
        - Compare current to historical average
        - Return True if significantly improved

        Args:
            current_pass_rate: Current pass rate (0-100)

        Returns:
            True if pass rate improved significantly, False otherwise
        """
        analysis = self.analyze_trends(current_pass_rate)

        if not analysis:
            return False

        is_improving = (
            analysis.trend_direction == 'improving' and
            analysis.is_significant
        )

        if is_improving:
            self.logger.info(
                f"Improvement detected: {analysis.trend_percentage:+.1f}% "
                f"(from {analysis.baseline_pass_rate:.1f}% to {analysis.current_pass_rate:.1f}%)"
            )

        return is_improving

    @handle_errors(component="result_processor", reraise=False)
    def detect_regression(self, current_pass_rate: float) -> bool:
        """
        Detect if current pass rate shows regression over historical baseline

        Feature #70 implementation:
        - Compare current to historical average
        - Return True if significantly regressed

        Args:
            current_pass_rate: Current pass rate (0-100)

        Returns:
            True if pass rate regressed significantly, False otherwise
        """
        analysis = self.analyze_trends(current_pass_rate)

        if not analysis:
            return False

        is_regressing = (
            analysis.trend_direction == 'regressing' and
            analysis.is_significant
        )

        if is_regressing:
            self.logger.warning(
                f"Regression detected: {analysis.trend_percentage:+.1f}% "
                f"(from {analysis.baseline_pass_rate:.1f}% to {analysis.current_pass_rate:.1f}%)"
            )

        return is_regressing

    @handle_errors(component="result_processor", reraise=True)
    def process_results(self, results: List[TestResult]) -> ProcessedResult:
        """
        Process test results completely

        This is the main entry point that:
        - Calculates pass rates (Feature #62)
        - Identifies failure patterns
        - Detects flaky tests
        - Determines next action
        - Returns complete processed result

        Args:
            results: List of test results

        Returns:
            ProcessedResult object with all analysis

        Raises:
            TestExecutionError: If processing fails
        """
        self.logger.info(f"Processing {len(results)} test results...")

        # Step 1: Calculate pass rates
        metrics = self.calculate_pass_rates(results)

        # Step 2: Identify failure patterns
        patterns = self.identify_failure_patterns(results)

        # Step 3: Detect flaky tests
        flaky = self.detect_flaky_tests(results)

        # Step 3.5: Filter known issues (Feature #71)
        new_failures, matched_known_issues = self.filter_known_issues(results)

        # Step 3.6: Create and prioritize bugs from NEW failures only (Feature #68)
        bugs = self.create_bugs_from_failures(new_failures)

        # Step 3.75: Aggregate results by journey (Feature #69)
        journey_results = self.aggregate_by_journey(results)

        # Step 3.9: Track pass rate snapshot for historical trends (Feature #70)
        run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.track_pass_rate_snapshot(metrics, run_id)

        # Step 3.95: Analyze trends (Feature #70)
        trend_analysis = self.analyze_trends(metrics.pass_rate)

        # Step 3.99: Check for performance regressions (Feature #188)
        performance_regressions = self.performance_detector.check_all_regressions(results, run_id)

        # Step 3.999: Auto-quarantine consistently flaky tests (Feature #203)
        quarantined_tests = self.auto_quarantine_flaky_tests(flaky)

        # Step 4: Determine action
        action, reason = self.determine_action(metrics, patterns)

        # Create processed result
        processed = ProcessedResult(
            metrics=metrics,
            failure_patterns=patterns,
            flaky_tests=flaky,
            action=action,
            reason=reason,
            bugs=bugs,  # Feature #68: prioritized bugs (only from new failures)
            journey_results=journey_results,  # Feature #69: journey-level aggregation
            trend_analysis=trend_analysis,  # Feature #70: historical trend analysis
            known_issues=matched_known_issues,  # Feature #71: known issues that were filtered out
            new_failures=new_failures,  # Feature #71: failures not matching known issues
            performance_regressions=performance_regressions,  # Feature #188: performance regressions
            quarantined_tests=quarantined_tests  # Feature #203: newly quarantined flaky tests
        )

        self.logger.info(
            f"Processing complete: "
            f"{metrics.pass_rate_formatted} pass rate, "
            f"{len(patterns)} failure patterns, "
            f"{len(flaky)} flaky tests, "
            f"{len(journey_results)} journeys, "
            f"{len(matched_known_issues)} known issues filtered, "
            f"{len(new_failures)} new failures, "
            f"{len(performance_regressions)} performance regressions, "
            f"{len(quarantined_tests)} newly quarantined, "
            f"action={action}"
        )

        return processed

    def generate_summary_report(self, processed: ProcessedResult) -> str:
        """
        Generate human-readable summary report

        Args:
            processed: ProcessedResult object

        Returns:
            Formatted summary string
        """
        lines = []
        lines.append("=" * 70)
        lines.append("TEST EXECUTION SUMMARY")
        lines.append("=" * 70)
        lines.append("")

        # Metrics
        lines.append("Pass/Fail Metrics:")
        lines.append(f"  Total Tests:  {processed.metrics.total_tests}")
        lines.append(f"  Passed:       {processed.metrics.passed_tests} ({processed.metrics.pass_rate_formatted})")
        lines.append(f"  Failed:       {processed.metrics.failed_tests} ({processed.metrics.fail_rate_formatted})")
        lines.append("")

        # Failure patterns
        if processed.failure_patterns:
            lines.append("Failure Patterns:")
            for pattern in processed.failure_patterns:
                lines.append(f"  • {pattern.pattern_name}: {pattern.count} tests")
                if pattern.suggestion:
                    lines.append(f"    Suggestion: {pattern.suggestion}")
            lines.append("")
        else:
            lines.append("✓ No failure patterns detected")
            lines.append("")

        # Flaky tests
        if processed.flaky_tests:
            lines.append(f"Flaky Tests ({len(processed.flaky_tests)}):")
            for flaky in processed.flaky_tests[:5]:  # Show top 5
                lines.append(f"  • {flaky.test_name}: {flaky.flaky_score:.1f}% flaky ({flaky.variance} variance)")
            if len(processed.flaky_tests) > 5:
                lines.append(f"  ... and {len(processed.flaky_tests) - 5} more")
            lines.append("")
        else:
            lines.append("✓ No flaky tests detected")
            lines.append("")

        # Action
        lines.append("Recommended Action:")
        lines.append(f"  {processed.action.upper()}: {processed.reason}")
        lines.append("")

        lines.append("=" * 70)

        return "\n".join(lines)

    # ========================================================================
    # Feature #71: Known Issues Management
    # ========================================================================

    def _load_known_issues(self) -> None:
        """
        Load known issues from JSON file

        Feature #71 implementation:
        - Loads known issues from state/known_issues.json
        - Creates file if it doesn't exist
        - Handles corrupted data gracefully
        """
        try:
            if self._known_issues_file.exists():
                with open(self._known_issues_file, 'r') as f:
                    data = json.load(f)

                # Reconstruct KnownIssue objects from dicts
                self._known_issues = [
                    KnownIssue(
                        issue_id=item['issue_id'],
                        test_name=item['test_name'],
                        failure_type=item['failure_type'],
                        error_signature=item['error_signature'],
                        severity=item['severity'],
                        status=item['status'],
                        created_at=datetime.fromisoformat(item['created_at']),
                        resolved_at=datetime.fromisoformat(item['resolved_at']) if item.get('resolved_at') else None,
                        notes=item.get('notes'),
                        occurrence_count=item.get('occurrence_count', 0)
                    )
                    for item in data
                ]

                self.logger.info(f"Loaded {len(self._known_issues)} known issues from {self._known_issues_file}")
            else:
                # Create empty known issues file
                self._known_issues = []
                self._save_known_issues()
                self.logger.info(f"Created new known issues file: {self._known_issues_file}")
        except Exception as e:
            self.logger.warning(f"Failed to load known issues: {e}. Starting with empty list.")
            self._known_issues = []

    def _save_known_issues(self) -> None:
        """
        Save known issues to JSON file

        Feature #71 implementation:
        - Saves known issues to state/known_issues.json
        - Creates directory if needed
        - Handles write errors gracefully
        """
        try:
            # Ensure directory exists
            self._known_issues_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert to list of dicts
            data = [issue.to_dict() for issue in self._known_issues]

            # Save to file
            with open(self._known_issues_file, 'w') as f:
                json.dump(data, f, indent=2)

            self.logger.debug(f"Saved {len(self._known_issues)} known issues to {self._known_issues_file}")
        except Exception as e:
            self.logger.error(f"Failed to save known issues: {e}")

    def add_known_issue(
        self,
        test_name: str,
        failure_type: str,
        error_signature: str,
        severity: str = 'medium',
        notes: Optional[str] = None
    ) -> KnownIssue:
        """
        Add a new known issue to the database

        Feature #71 implementation:
        - Creates new KnownIssue with unique ID
        - Adds to in-memory list
        - Persists to JSON file

        Args:
            test_name: Name of the failing test
            failure_type: Type of failure (e.g., 'timeout', 'selector_not_found')
            error_signature: Unique signature (error message pattern)
            severity: Severity level ('critical', 'high', 'medium', 'low')
            notes: Additional context

        Returns:
            The created KnownIssue object
        """
        # Generate unique ID
        issue_id = f"KNOWN-{len(self._known_issues) + 1:03d}"

        # Create known issue
        issue = KnownIssue(
            issue_id=issue_id,
            test_name=test_name,
            failure_type=failure_type,
            error_signature=error_signature,
            severity=severity,
            status='open',
            notes=notes
        )

        # Add to database
        self._known_issues.append(issue)

        # Persist
        self._save_known_issues()

        self.logger.info(f"Added known issue: {issue_id} - {test_name} ({failure_type})")

        return issue

    @handle_errors(component="result_processor", reraise=True)
    def filter_known_issues(self, results: List[TestResult]) -> Tuple[List[TestResult], List[KnownIssue]]:
        """
        Filter out test failures that match known issues

        Feature #71 implementation:
        - Compares each failure against known issues
        - Returns filtered results and matched known issues
        - Updates occurrence counts for matched issues

        Args:
            results: List of test results

        Returns:
            Tuple of (new_failures, matched_known_issues)
            - new_failures: Test results that don't match known issues
            - matched_known_issues: Known issues that matched failures
        """
        self.logger.info("Filtering known issues from test results...")

        # Get only failed tests
        failed_tests = [r for r in results if not r.passed]

        if not failed_tests:
            self.logger.info("No failed tests to filter")
            return [], []

        if not self._known_issues:
            self.logger.info("No known issues in database - all failures are new")
            return failed_tests, []

        matched_issues: List[KnownIssue] = []
        new_failures: List[TestResult] = []

        # Check each failed test against known issues
        for test_result in failed_tests:
            matched = False

            for known_issue in self._known_issues:
                # Skip resolved issues
                if known_issue.status == 'resolved':
                    continue

                # Check if this failure matches the known issue
                if known_issue.matches_failure(test_result):
                    matched = True
                    matched_issues.append(known_issue)

                    # Update occurrence count
                    known_issue.occurrence_count += 1

                    self.logger.debug(
                        f"Filtered known issue: {known_issue.issue_id} - "
                        f"{test_result.test_name} matched {known_issue.failure_type}"
                    )
                    break

            if not matched:
                # This is a new failure
                new_failures.append(test_result)

        self.logger.info(
            f"Filtered {len(matched_issues)} known issues, "
            f"{len(new_failures)} new failures remaining"
        )

        # Save updated occurrence counts
        if matched_issues:
            self._save_known_issues()

        return new_failures, matched_issues

    def get_known_issues(self, status: Optional[str] = None) -> List[KnownIssue]:
        """
        Get all known issues, optionally filtered by status

        Feature #71 implementation:
        - Returns all known issues
        - Can filter by status ('open', 'in_progress', 'resolved', 'wontfix')

        Args:
            status: Optional status filter

        Returns:
            List of KnownIssue objects
        """
        if status:
            return [issue for issue in self._known_issues if issue.status == status]
        return self._known_issues.copy()

    def resolve_known_issue(self, issue_id: str) -> bool:
        """
        Mark a known issue as resolved

        Feature #71 implementation:
        - Updates issue status to 'resolved'
        - Sets resolved_at timestamp
        - Persists changes

        Args:
            issue_id: ID of the issue to resolve

        Returns:
            True if issue was found and updated, False otherwise
        """
        for issue in self._known_issues:
            if issue.issue_id == issue_id:
                issue.status = 'resolved'
                issue.resolved_at = datetime.now()
                self._save_known_issues()
                self.logger.info(f"Resolved known issue: {issue_id}")
                return True

        self.logger.warning(f"Known issue not found: {issue_id}")
        return False

    # ========================================================================
    # Feature #203: Quarantine Management for Flaky Tests
    # ========================================================================

    def _load_quarantined_tests(self) -> None:
        """
        Load quarantined tests from JSON file

        Feature #203 implementation:
        - Loads quarantined tests from state/quarantined_tests.json
        - Creates file if it doesn't exist
        - Handles corrupted data gracefully
        """
        try:
            if self._quarantine_file.exists():
                with open(self._quarantine_file, 'r') as f:
                    data = json.load(f)

                # Reconstruct QuarantinedTest objects from dicts
                self._quarantined_tests = [
                    QuarantinedTest(
                        test_name=item['test_name'],
                        quarantine_id=item['quarantine_id'],
                        flaky_score=item['flaky_score'],
                        total_runs=item['total_runs'],
                        passed_runs=item['passed_runs'],
                        failed_runs=item['failed_runs'],
                        variance=item['variance'],
                        quarantined_at=datetime.fromisoformat(item['quarantined_at']),
                        reason=item.get('reason', 'Consistently flaky test'),
                        resolved_at=datetime.fromisoformat(item['resolved_at']) if item.get('resolved_at') else None,
                        notes=item.get('notes')
                    )
                    for item in data
                ]

                self.logger.info(f"Loaded {len(self._quarantined_tests)} quarantined tests from {self._quarantine_file}")
            else:
                # Create empty quarantine file
                self._quarantined_tests = []
                self._save_quarantined_tests()
                self.logger.info(f"Created new quarantine file: {self._quarantine_file}")
        except Exception as e:
            self.logger.warning(f"Failed to load quarantined tests: {e}. Starting with empty list.")
            self._quarantined_tests = []

    def _save_quarantined_tests(self) -> None:
        """
        Save quarantined tests to JSON file

        Feature #203 implementation:
        - Saves quarantined tests to state/quarantined_tests.json
        - Creates directory if needed
        - Handles write errors gracefully
        """
        try:
            # Ensure directory exists
            self._quarantine_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert to list of dicts
            data = [qt.to_dict() for qt in self._quarantined_tests]

            # Save to file
            with open(self._quarantine_file, 'w') as f:
                json.dump(data, f, indent=2)

            self.logger.debug(f"Saved {len(self._quarantined_tests)} quarantined tests to {self._quarantine_file}")
        except Exception as e:
            self.logger.error(f"Failed to save quarantined tests: {e}")

    def is_test_quarantined(self, test_name: str) -> bool:
        """
        Check if a test is currently quarantined

        Feature #203 implementation:
        - Returns True if test is in quarantine
        - Only active (non-resolved) quarantines are considered

        Args:
            test_name: Name of the test to check

        Returns:
            True if test is quarantined, False otherwise
        """
        for qt in self._quarantined_tests:
            if qt.test_name == test_name and qt.resolved_at is None:
                return True
        return False

    def get_quarantined_tests(self, include_resolved: bool = False) -> List[QuarantinedTest]:
        """
        Get all quarantined tests

        Feature #203 implementation:
        - Returns all quarantined tests
        - Can optionally include resolved quarantines

        Args:
            include_resolved: If True, include resolved quarantines

        Returns:
            List of QuarantinedTest objects
        """
        if include_resolved:
            return self._quarantined_tests.copy()
        # Only return active quarantines
        return [qt for qt in self._quarantined_tests if qt.resolved_at is None]

    @handle_errors(component="result_processor", reraise=True)
    def quarantine_flaky_test(
        self,
        flaky_test: FlakyTest,
        notes: Optional[str] = None
    ) -> Optional[QuarantinedTest]:
        """
        Quarantine a consistently flaky test

        Feature #203 implementation:
        - Creates QuarantinedTest record
        - Adds to in-memory list
        - Persists to JSON file
        - Only quarantines if flaky_score >= 50 (medium-high variance)

        Args:
            flaky_test: FlakyTest object to quarantine
            notes: Optional notes about the quarantine

        Returns:
            The created QuarantinedTest object, or None if test doesn't meet quarantine threshold
        """
        # Only quarantine tests with medium-high or high flakiness (score >= 50)
        if flaky_test.flaky_score < 50:
            self.logger.info(
                f"Test '{flaky_test.test_name}' has flaky score {flaky_test.flaky_score:.1f} "
                f"(below quarantine threshold of 50) - not quarantining"
            )
            return None

        # Check if already quarantined
        if self.is_test_quarantined(flaky_test.test_name):
            self.logger.info(
                f"Test '{flaky_test.test_name}' is already quarantined - skipping"
            )
            return None

        # Generate unique quarantine ID
        quarantine_id = f"QUARANTINE-{len(self._quarantined_tests) + 1:03d}"

        # Create quarantined test record
        quarantined = QuarantinedTest(
            test_name=flaky_test.test_name,
            quarantine_id=quarantine_id,
            flaky_score=flaky_test.flaky_score,
            total_runs=flaky_test.total_runs,
            passed_runs=flaky_test.passed_runs,
            failed_runs=flaky_test.failed_runs,
            variance=flaky_test.variance,
            reason=f"Consistently flaky test (score: {flaky_test.flaky_score:.1f}%)",
            notes=notes
        )

        # Add to quarantine list
        self._quarantined_tests.append(quarantined)

        # Persist
        self._save_quarantined_tests()

        self.logger.warning(
            f"⚠️  QUARANTINED: '{flaky_test.test_name}' (ID: {quarantine_id})\n"
            f"   Flaky Score: {flaky_test.flaky_score:.1f}%\n"
            f"   Runs: {flaky_test.total_runs} "
            f"({flaky_test.passed_runs} passed, {flaky_test.failed_runs} failed)\n"
            f"   Variance: {flaky_test.variance}"
        )

        return quarantined

    def resolve_quarantine(self, quarantine_id: str, notes: Optional[str] = None) -> bool:
        """
        Resolve a quarantine (release test back to main suite)

        Feature #203 implementation:
        - Updates quarantine status to resolved
        - Sets resolved_at timestamp
        - Persists changes

        Args:
            quarantine_id: ID of the quarantine to resolve
            notes: Optional notes about why quarantine was resolved

        Returns:
            True if quarantine was found and resolved, False otherwise
        """
        for qt in self._quarantined_tests:
            if qt.quarantine_id == quarantine_id and qt.resolved_at is None:
                qt.resolved_at = datetime.now()
                if notes:
                    qt.notes = f"{qt.notes}\n\nResolved: {notes}" if qt.notes else notes
                self._save_quarantined_tests()
                self.logger.info(f"Resolved quarantine: {quarantine_id} - Test '{qt.test_name}' released back to main suite")
                return True

        self.logger.warning(f"Quarantine not found or already resolved: {quarantine_id}")
        return False

    @handle_errors(component="result_processor", reraise=False)
    def auto_quarantine_flaky_tests(self, flaky_tests: List[FlakyTest]) -> List[QuarantinedTest]:
        """
        Automatically quarantine consistently flaky tests

        Feature #203 implementation:
        - Processes list of flaky tests
        - Quarantines those with score >= 50
        - Returns list of newly quarantined tests

        Args:
            flaky_tests: List of FlakyTest objects from detect_flaky_tests()

        Returns:
            List of QuarantinedTest objects for newly quarantined tests
        """
        newly_quarantined: List[QuarantinedTest] = []

        for flaky_test in flaky_tests:
            quarantined = self.quarantine_flaky_test(
                flaky_test,
                notes=f"Auto-quarantined due to consistent flakiness"
            )
            if quarantined:
                newly_quarantined.append(quarantined)

        if newly_quarantined:
            self.logger.warning(
                f"⚠️  Auto-quarantined {len(newly_quarantined)} flaky tests"
            )

        return newly_quarantined

    @handle_errors(component="result_processor", reraise=False)
    def filter_quarantined_tests(self, test_names: List[str]) -> Tuple[List[str], List[str]]:
        """
        Filter out quarantined tests from a list of test names

        Feature #203 implementation:
        - Separates tests into active and quarantined
        - Returns tuple of (active_tests, quarantined_tests)

        Args:
            test_names: List of test names to filter

        Returns:
            Tuple of (active_test_names, quarantined_test_names)
        """
        active_tests: List[str] = []
        quarantined_tests: List[str] = []

        for test_name in test_names:
            if self.is_test_quarantined(test_name):
                quarantined_tests.append(test_name)
            else:
                active_tests.append(test_name)

        if quarantined_tests:
            self.logger.info(
                f"Filtered out {len(quarantined_tests)} quarantined tests: "
                f"{', '.join(quarantined_tests[:5])}"
                + (f" and {len(quarantined_tests) - 5} more" if len(quarantined_tests) > 5 else "")
            )

        return active_tests, quarantined_tests

    # ========================================================================
    # Feature #205: Flaky Test Health Reporting
    # ========================================================================

    @handle_errors(component="result_processor", reraise=True)
    def get_flaky_health_report(self) -> FlakyHealthReport:
        """
        Generate a comprehensive health report for flaky tests

        Feature #205 implementation:
        - Reports flaky test count and percentage
        - Analyzes trends over time
        - Provides health status assessment
        - Includes historical snapshots

        Returns:
            FlakyHealthReport object with comprehensive health metrics
        """
        self.logger.info("Generating flaky test health report...")

        # Get current flaky tests
        current_flaky_tests = self.detect_flaky_tests([])  # Use existing history

        # Calculate current metrics
        flaky_count = len(current_flaky_tests)
        total_tests = len(self._test_history)

        if total_tests == 0:
            # No test data yet
            flaky_percentage = 0.0
        else:
            flaky_percentage = (flaky_count / total_tests) * 100

        flaky_percentage_formatted = f"{flaky_percentage:.1f}%"

        # Create current snapshot
        current_snapshot = FlakyHealthSnapshot(
            timestamp=datetime.now(),
            flaky_count=flaky_count,
            flaky_percentage=flaky_percentage,
            total_tests=total_tests
        )

        # Add to history (avoid duplicates for same timestamp)
        if not self._flaky_health_history or \
           (self._flaky_health_history and
            (datetime.now() - self._flaky_health_history[-1].timestamp).total_seconds() > 60):
            self._flaky_health_history.append(current_snapshot)

        # Analyze trends
        trend_direction, trend_percentage = self._analyze_flaky_trends(flaky_percentage)

        # Determine health status
        health_status = self._determine_health_status(flaky_percentage)

        # Create health report
        report = FlakyHealthReport(
            flaky_count=flaky_count,
            flaky_percentage=flaky_percentage,
            flaky_percentage_formatted=flaky_percentage_formatted,
            total_tests=total_tests,
            trend_direction=trend_direction,
            trend_percentage=trend_percentage,
            health_status=health_status,
            historical_snapshots=self._flaky_health_history.copy(),
            snapshot_count=len(self._flaky_health_history)
        )

        self.logger.info(
            f"Flaky health report: {flaky_count}/{total_tests} tests flaky "
            f"({flaky_percentage_formatted}), trend: {trend_direction} ({trend_percentage:+.1f}%), "
            f"status: {health_status}"
        )

        return report

    def _analyze_flaky_trends(self, current_percentage: float) -> Tuple[str, float]:
        """
        Analyze flaky test trends over time

        Args:
            current_percentage: Current flaky test percentage

        Returns:
            Tuple of (trend_direction, trend_percentage)
            - trend_direction: 'improving', 'stable', 'worsening', 'unknown'
            - trend_percentage: Percentage change (negative = improvement)
        """
        if len(self._flaky_health_history) < 2:
            # Not enough historical data
            return 'unknown', 0.0

        # Get historical percentages (excluding current)
        historical_percentages = [
            snapshot.flaky_percentage
            for snapshot in self._flaky_health_history[:-1]
        ]

        if not historical_percentages:
            return 'unknown', 0.0

        # Calculate baseline (average of historical data)
        baseline = sum(historical_percentages) / len(historical_percentages)

        # Calculate percentage change
        if baseline > 0:
            trend_percentage = ((current_percentage - baseline) / baseline) * 100
        else:
            trend_percentage = 0.0

        # Determine trend direction
        # Negative trend_percentage = improvement (fewer flaky tests)
        # Positive trend_percentage = worsening (more flaky tests)
        if abs(trend_percentage) < 5:
            trend_direction = 'stable'
        elif trend_percentage < -5:
            trend_direction = 'improving'  # Fewer flaky tests = good
        else:  # trend_percentage >= 5
            trend_direction = 'worsening'  # More flaky tests = bad

        return trend_direction, trend_percentage

    def _determine_health_status(self, flaky_percentage: float) -> str:
        """
        Determine overall health status based on flaky test percentage

        Health status thresholds:
        - excellent: 0-5% flaky tests
        - good: 5-10% flaky tests
        - fair: 10-20% flaky tests
        - poor: 20-30% flaky tests
        - critical: >30% flaky tests

        Args:
            flaky_percentage: Percentage of flaky tests (0-100)

        Returns:
            Health status string
        """
        if flaky_percentage <= 5:
            return 'excellent'
        elif flaky_percentage <= 10:
            return 'good'
        elif flaky_percentage <= 20:
            return 'fair'
        elif flaky_percentage <= 30:
            return 'poor'
        else:
            return 'critical'

    def track_flaky_health_snapshot(self) -> FlakyHealthSnapshot:
        """
        Create and track a snapshot of current flaky test health

        Feature #205 implementation:
        - Creates snapshot from current flaky test state
        - Stores in history for trend analysis
        - Returns snapshot for reference

        Returns:
            FlakyHealthSnapshot object
        """
        # Get current flaky tests
        current_flaky_tests = self.detect_flaky_tests([])

        # Calculate metrics
        flaky_count = len(current_flaky_tests)
        total_tests = len(self._test_history)
        flaky_percentage = (flaky_count / total_tests * 100) if total_tests > 0 else 0.0

        # Create snapshot
        snapshot = FlakyHealthSnapshot(
            timestamp=datetime.now(),
            flaky_count=flaky_count,
            flaky_percentage=flaky_percentage,
            total_tests=total_tests
        )

        # Add to history
        self._flaky_health_history.append(snapshot)

        self.logger.info(
            f"Tracked flaky health snapshot: {flaky_count}/{total_tests} flaky "
            f"({flaky_percentage:.1f}%), "
            f"({len(self._flaky_health_history)} total snapshots)"
        )

        return snapshot

    def get_flaky_health_history(self, limit: Optional[int] = None) -> List[FlakyHealthSnapshot]:
        """
        Retrieve historical flaky health snapshots

        Feature #205 implementation:
        - Returns all or limited history
        - Most recent first

        Args:
            limit: Optional maximum number of snapshots to return

        Returns:
            List of FlakyHealthSnapshot objects, most recent first
        """
        history = self._flaky_health_history.copy()
        # Reverse to get most recent first
        history.reverse()

        if limit:
            history = history[:limit]

        return history

