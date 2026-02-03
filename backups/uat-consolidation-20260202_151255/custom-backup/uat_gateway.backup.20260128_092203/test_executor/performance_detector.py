"""
Performance Detector - Track and analyze test execution times

Feature #186: Performance detector tracks execution times

This module is responsible for:
- Measuring and recording test execution times
- Storing execution times in state history
- Analyzing performance trends over time
- Detecting performance regressions
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum

import sys
from pathlib import Path as PathLib

# Add parent directory to path for imports
sys.path.insert(0, str(PathLib(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import TestExecutionError, handle_errors
from custom.uat_gateway.test_executor.test_executor import TestResult
from custom.uat_gateway.state_manager.state_manager import StateManager, ExecutionRecord


# ============================================================================
# Data Models
# ============================================================================

class PerformanceTrend(Enum):
    """Performance trend over time"""
    IMPROVING = "improving"  # Getting faster
    STABLE = "stable"  # Within expected variance
    DEGRADING = "degrading"  # Getting slower
    UNKNOWN = "unknown"  # Not enough data


@dataclass
class TestPerformanceMetric:
    """
    Performance metrics for a single test

    Feature #186: Track individual test execution times
    """
    test_name: str
    avg_duration_ms: float
    min_duration_ms: float
    max_duration_ms: float
    sample_count: int
    last_execution: str  # ISO timestamp
    trend: PerformanceTrend = PerformanceTrend.UNKNOWN

    # For trend analysis
    recent_avg_ms: float = 0.0  # Average of last 3 runs
    baseline_avg_ms: float = 0.0  # Average of all historical runs

    # Regression detection
    regression_threshold_percent: float = 20.0  # Flag if 20% slower than baseline
    is_regression: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2),
            "max_duration_ms": round(self.max_duration_ms, 2),
            "sample_count": self.sample_count,
            "last_execution": self.last_execution,
            "trend": self.trend.value,
            "recent_avg_ms": round(self.recent_avg_ms, 2),
            "baseline_avg_ms": round(self.baseline_avg_ms, 2),
            "regression_threshold_percent": round(self.regression_threshold_percent, 2),
            "is_regression": self.is_regression
        }


@dataclass
class PerformanceSummary:
    """
    Summary of performance across all tests

    Feature #186: Aggregate performance metrics
    """
    total_tests: int
    total_executions: int
    total_duration_ms: float
    avg_duration_ms: float
    slowest_test: Optional[str]
    fastest_test: Optional[str]
    slowest_test_duration_ms: float
    fastest_test_duration_ms: float
    timestamp: str

    # Performance distribution
    fast_tests_count: int  # < 500ms
    medium_tests_count: int  # 500ms - 2000ms
    slow_tests_count: int  # > 2000ms

    # Regression warnings
    regression_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "total_tests": self.total_tests,
            "total_executions": self.total_executions,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "slowest_test": self.slowest_test,
            "fastest_test": self.fastest_test,
            "slowest_test_duration_ms": round(self.slowest_test_duration_ms, 2),
            "fastest_test_duration_ms": round(self.fastest_test_duration_ms, 2),
            "timestamp": self.timestamp,
            "fast_tests_count": self.fast_tests_count,
            "medium_tests_count": self.medium_tests_count,
            "slow_tests_count": self.slow_tests_count,
            "regression_count": self.regression_count
        }


# ============================================================================
# Performance Detector
# ============================================================================

class PerformanceDetector:
    """
    Tracks and analyzes test execution performance

    Feature #186: "Performance detector tracks execution times"

    Responsibilities:
    - Collect execution times from test results
    - Store metrics in state history
    - Analyze performance trends
    - Detect performance regressions
    - Generate performance reports
    """

    def __init__(self, state_manager: Optional[StateManager] = None):
        """
        Initialize performance detector

        Args:
            state_manager: Optional StateManager for loading historical data
        """
        self.logger = get_logger("performance_detector")
        self.state_manager = state_manager or StateManager()

        # Performance thresholds (milliseconds)
        self.fast_threshold_ms = 500.0
        self.medium_threshold_ms = 2000.0
        self.regression_threshold_percent = 20.0

        # Cached metrics
        self._test_metrics: Dict[str, TestPerformanceMetric] = {}
        self._history_loaded = False

    @handle_errors(component="performance_detector", reraise=True)
    def track_execution_times(
        self,
        results: List[TestResult],
        run_id: Optional[str] = None
    ) -> List[TestPerformanceMetric]:
        """
        Track execution times from test results

        Feature #186: "Check execution times"
        Feature #186: "Verify each test time is recorded"

        Args:
            results: List of test results with durations
            run_id: Optional run ID for this execution

        Returns:
            List of performance metrics for each test

        Raises:
            TestExecutionError: If tracking fails
        """
        self.logger.info(f"Tracking execution times for {len(results)} tests...")

        if not results:
            self.logger.warning("No test results to track")
            return []

        # Verify each test has duration recorded
        metrics = []
        for result in results:
            if result.duration_ms is None:
                self.logger.warning(
                    f"Test {result.test_name} missing duration, using 0"
                )
                result.duration_ms = 0

            self.logger.debug(
                f"  {result.test_name}: {result.duration_ms}ms "
                f"({'PASS' if result.passed else 'FAIL'})"
            )

        # Calculate metrics for this run
        for result in results:
            metric = self._calculate_metric(result, run_id)
            metrics.append(metric)

        self.logger.info(
            f"Tracked execution times: {len(metrics)} tests, "
            f"avg {sum(m.avg_duration_ms for m in metrics) / len(metrics):.2f}ms"
        )

        return metrics

    def _calculate_metric(
        self,
        result: TestResult,
        run_id: Optional[str]
    ) -> TestPerformanceMetric:
        """
        Calculate performance metric for a single test

        Args:
            result: Test result
            run_id: Run ID for this execution

        Returns:
            TestPerformanceMetric for this test
        """
        # Load historical data for trend analysis
        if not self._history_loaded:
            self._load_historical_metrics()

        test_name = result.test_name
        duration_ms = result.duration_ms

        # Get or create metric entry
        if test_name not in self._test_metrics:
            self._test_metrics[test_name] = TestPerformanceMetric(
                test_name=test_name,
                avg_duration_ms=duration_ms,
                min_duration_ms=duration_ms,
                max_duration_ms=duration_ms,
                sample_count=1,
                last_execution=datetime.now().isoformat()
            )
        else:
            # Update existing metric
            existing = self._test_metrics[test_name]
            existing.sample_count += 1

            # Update average (running average)
            existing.avg_duration_ms = (
                (existing.avg_duration_ms * (existing.sample_count - 1) + duration_ms)
                / existing.sample_count
            )

            # Update min/max
            if duration_ms < existing.min_duration_ms:
                existing.min_duration_ms = duration_ms
            if duration_ms > existing.max_duration_ms:
                existing.max_duration_ms = duration_ms

            existing.last_execution = datetime.now().isoformat()

        # Calculate trend and detect regression
        self._analyze_trend(test_name)

        return self._test_metrics[test_name]

    def _analyze_trend(self, test_name: str) -> None:
        """
        Analyze performance trend for a test

        Args:
            test_name: Name of the test to analyze
        """
        metric = self._test_metrics[test_name]

        # Need at least 3 samples for trend analysis
        if metric.sample_count < 3:
            metric.trend = PerformanceTrend.UNKNOWN
            return

        # Load historical execution records
        history = self.state_manager.query_history(
            HistoryQuery(limit=50)  # Last 50 runs
        )

        # Collect all durations for this test
        all_durations = []
        for record in history:
            for test_result in record.results:
                if test_result.get('test_name') == test_name:
                    all_durations.append(test_result.get('duration_ms', 0))

        if len(all_durations) < 3:
            metric.trend = PerformanceTrend.UNKNOWN
            return

        # Calculate baseline (all historical data)
        metric.baseline_avg_ms = sum(all_durations) / len(all_durations)

        # Calculate recent average (last 3 samples)
        recent_durations = all_durations[-3:]
        metric.recent_avg_ms = sum(recent_durations) / len(recent_durations)

        # Determine trend
        diff_percent = (
            (metric.recent_avg_ms - metric.baseline_avg_ms)
            / metric.baseline_avg_ms * 100
        )

        if diff_percent > self.regression_threshold_percent:
            metric.trend = PerformanceTrend.DEGRADING
            metric.is_regression = True
        elif diff_percent < -self.regression_threshold_percent:
            metric.trend = PerformanceTrend.IMPROVING
        else:
            metric.trend = PerformanceTrend.STABLE

    def generate_summary(
        self,
        results: Optional[List[TestResult]] = None
    ) -> PerformanceSummary:
        """
        Generate performance summary

        Feature #186: Aggregate execution time statistics

        Args:
            results: Optional list of recent test results

        Returns:
            PerformanceSummary with aggregate metrics
        """
        # Load all historical metrics
        self._load_historical_metrics()

        if not self._test_metrics:
            return PerformanceSummary(
                total_tests=0,
                total_executions=0,
                total_duration_ms=0.0,
                avg_duration_ms=0.0,
                slowest_test=None,
                fastest_test=None,
                slowest_test_duration_ms=0.0,
                fastest_test_duration_ms=0.0,
                timestamp=datetime.now().isoformat(),
                fast_tests_count=0,
                medium_tests_count=0,
                slow_tests_count=0
            )

        # Calculate aggregate metrics
        total_tests = len(self._test_metrics)
        total_executions = sum(m.sample_count for m in self._test_metrics.values())
        total_duration = sum(
            m.avg_duration_ms * m.sample_count
            for m in self._test_metrics.values()
        )

        # Find slowest and fastest tests
        slowest_test = max(
            self._test_metrics.items(),
            key=lambda x: x[1].avg_duration_ms
        )
        fastest_test = min(
            self._test_metrics.items(),
            key=lambda x: x[1].avg_duration_ms
        )

        # Count by speed category
        fast_tests = sum(
            1 for m in self._test_metrics.values()
            if m.avg_duration_ms < self.fast_threshold_ms
        )
        medium_tests = sum(
            1 for m in self._test_metrics.values()
            if self.fast_threshold_ms <= m.avg_duration_ms < self.medium_threshold_ms
        )
        slow_tests = sum(
            1 for m in self._test_metrics.values()
            if m.avg_duration_ms >= self.medium_threshold_ms
        )

        # Count regressions
        regression_count = sum(
            1 for m in self._test_metrics.values()
            if m.is_regression
        )

        return PerformanceSummary(
            total_tests=total_tests,
            total_executions=total_executions,
            total_duration_ms=total_duration,
            avg_duration_ms=total_duration / total_executions if total_executions > 0 else 0,
            slowest_test=slowest_test[0],
            fastest_test=fastest_test[0],
            slowest_test_duration_ms=slowest_test[1].avg_duration_ms,
            fastest_test_duration_ms=fastest_test[1].avg_duration_ms,
            timestamp=datetime.now().isoformat(),
            fast_tests_count=fast_tests,
            medium_tests_count=medium_tests,
            slow_tests_count=slow_tests,
            regression_count=regression_count
        )

    def _load_historical_metrics(self) -> None:
        """Load historical performance metrics from state manager"""
        if self._history_loaded:
            return

        try:
            # Query execution history
            history = self.state_manager.query_history(HistoryQuery(limit=100))

            # Process each execution record
            for record in history:
                for test_result in record.results:
                    test_name = test_result.get('test_name')
                    duration_ms = test_result.get('duration_ms', 0)

                    if test_name not in self._test_metrics:
                        self._test_metrics[test_name] = TestPerformanceMetric(
                            test_name=test_name,
                            avg_duration_ms=duration_ms,
                            min_duration_ms=duration_ms,
                            max_duration_ms=duration_ms,
                            sample_count=1,
                            last_execution=record.timestamp
                        )
                    else:
                        # Update existing metric
                        metric = self._test_metrics[test_name]
                        metric.sample_count += 1

                        # Update running average
                        metric.avg_duration_ms = (
                            (metric.avg_duration_ms * (metric.sample_count - 1) + duration_ms)
                            / metric.sample_count
                        )

                        # Update min/max
                        if duration_ms < metric.min_duration_ms:
                            metric.min_duration_ms = duration_ms
                        if duration_ms > metric.max_duration_ms:
                            metric.max_duration_ms = duration_ms

            self._history_loaded = True
            self.logger.debug(f"Loaded historical metrics for {len(self._test_metrics)} tests")

        except Exception as e:
            self.logger.warning(f"Failed to load historical metrics: {e}")
            self._history_loaded = True  # Don't retry

    def get_test_metrics(self, test_name: str) -> Optional[TestPerformanceMetric]:
        """
        Get performance metrics for a specific test

        Args:
            test_name: Name of the test

        Returns:
            TestPerformanceMetric if found, None otherwise
        """
        self._load_historical_metrics()
        return self._test_metrics.get(test_name)

    def get_all_metrics(self) -> Dict[str, TestPerformanceMetric]:
        """
        Get all test performance metrics

        Returns:
            Dictionary mapping test names to metrics
        """
        self._load_historical_metrics()
        return self._test_metrics.copy()

    def detect_regressions(
        self,
        threshold_percent: Optional[float] = None
    ) -> List[TestPerformanceMetric]:
        """
        Detect performance regressions

        Args:
            threshold_percent: Optional threshold (defaults to 20%)

        Returns:
            List of metrics with regression detected
        """
        threshold = threshold_percent or self.regression_threshold_percent

        regressions = []
        for metric in self._test_metrics.values():
            if metric.is_regression:
                regressions.append(metric)

        return regressions

    def generate_report(self) -> str:
        """
        Generate a human-readable performance report

        Returns:
            Formatted report string
        """
        summary = self.generate_summary()
        lines = [
            "=" * 70,
            "PERFORMANCE REPORT",
            "=" * 70,
            f"Generated: {summary.timestamp}",
            "",
            "OVERALL METRICS",
            "-" * 70,
            f"Total Tests: {summary.total_tests}",
            f"Total Executions: {summary.total_executions}",
            f"Average Duration: {summary.avg_duration_ms:.2f}ms",
            f"Total Duration: {summary.total_duration_ms / 1000:.2f}s",
            "",
            "SPEED DISTRIBUTION",
            "-" * 70,
            f"Fast (< {self.fast_threshold_ms}ms): {summary.fast_tests_count}",
            f"Medium ({self.fast_threshold_ms}-{self.medium_threshold_ms}ms): {summary.medium_tests_count}",
            f"Slow (> {self.medium_threshold_ms}ms): {summary.slow_tests_count}",
            "",
            "EXTREMES",
            "-" * 70,
        ]

        if summary.fastest_test:
            lines.append(f"Fastest Test: {summary.fastest_test} ({summary.fastest_test_duration_ms:.2f}ms)")
        if summary.slowest_test:
            lines.append(f"Slowest Test: {summary.slowest_test} ({summary.slowest_test_duration_ms:.2f}ms)")

        lines.append("")

        # Regressions
        if summary.regression_count > 0:
            lines.extend([
                "REGRESSION WARNINGS",
                "-" * 70,
                f"{summary.regression_count} test(s) showing performance degradation",
                ""
            ])

            regressions = self.detect_regressions()
            for metric in regressions[:10]:  # Show top 10
                lines.append(
                    f"  {metric.test_name}: "
                    f"{metric.recent_avg_ms:.2f}ms vs {metric.baseline_avg_ms:.2f}ms baseline"
                )

        lines.append("=" * 70)

        return "\n".join(lines)


# Import for type hints
from custom.uat_gateway.state_manager.state_manager import HistoryQuery
