"""
Performance Detector - Detect performance regressions in test execution times

This module is responsible for:
- Tracking historical execution times per test
- Calculating baseline durations
- Detecting significant slowdowns
- Flagging performance regressions
- Generating performance reports

Feature #188: Performance detector detects significant slowdowns
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import json

# Add parent directory to path for imports

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import TestExecutionError, handle_errors
from uat_gateway.test_executor.test_executor import TestResult


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class PerformanceSnapshot:
    """Historical snapshot of test execution time"""
    timestamp: datetime
    test_name: str
    duration_ms: int
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "test_name": self.test_name,
            "duration_ms": self.duration_ms,
            "run_id": self.run_id
        }


@dataclass
class PerformanceBaseline:
    """Baseline performance metrics for a test"""
    test_name: str
    avg_duration_ms: float  # Average duration
    min_duration_ms: int  # Fastest execution
    max_duration_ms: int  # Slowest execution
    sample_count: int  # Number of samples
    std_dev_ms: float  # Standard deviation
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "min_duration_ms": self.min_duration_ms,
            "max_duration_ms": self.max_duration_ms,
            "sample_count": self.sample_count,
            "std_dev_ms": round(self.std_dev_ms, 2),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class PerformanceRegression:
    """Represents a detected performance regression"""
    test_name: str
    current_duration_ms: int
    baseline_duration_ms: float
    slowdown_percentage: float  # Percentage increase (e.g., 50.0 for 50% slower)
    severity: str  # 'minor', 'moderate', 'severe'
    threshold_exceeded: float  # The threshold that was exceeded (e.g., 50.0 for 50%)
    detected_at: datetime
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "current_duration_ms": self.current_duration_ms,
            "baseline_duration_ms": round(self.baseline_duration_ms, 2),
            "slowdown_percentage": round(self.slowdown_percentage, 2),
            "severity": self.severity,
            "threshold_exceeded": round(self.threshold_exceeded, 2),
            "detected_at": self.detected_at.isoformat(),
            "run_id": self.run_id
        }


# ============================================================================
# Performance Detector
# ============================================================================

class PerformanceDetector:
    """
    Detect performance regressions in test execution times

    Feature #188 implementation:
    - Tracks historical execution times
    - Calculates baselines for each test
    - Detects significant slowdowns
    - Flags performance regressions
    """

    # Severity thresholds for slowdowns
    SEVERE_THRESHOLD = 100.0  # 100%+ slower = severe
    MODERATE_THRESHOLD = 50.0  # 50%+ slower = moderate
    MINOR_THRESHOLD = 25.0  # 25%+ slower = minor

    # Minimum samples required to establish baseline
    MIN_BASELINE_SAMPLES = 3

    def __init__(self, slowdown_threshold: float = 50.0):
        """
        Initialize performance detector

        Args:
            slowdown_threshold: Percentage threshold for flagging slowdowns (default: 50.0)
        """
        self.logger = get_logger("performance_detector")
        self.slowdown_threshold = slowdown_threshold

        # Storage for historical data
        self._snapshots: Dict[str, List[PerformanceSnapshot]] = defaultdict(list)
        self._baselines: Dict[str, PerformanceBaseline] = {}

        self.logger.info(
            f"PerformanceDetector initialized with slowdown_threshold={slowdown_threshold}%"
        )

    @handle_errors(component="performance_detector", reraise=False)
    def record_execution(self, test_result: TestResult, run_id: Optional[str] = None) -> PerformanceSnapshot:
        """
        Record a test execution time

        Feature #188: Introduce slowdown

        Args:
            test_result: Test result with duration
            run_id: Optional run identifier

        Returns:
            PerformanceSnapshot object
        """
        snapshot = PerformanceSnapshot(
            timestamp=datetime.now(),
            test_name=test_result.test_name,
            duration_ms=test_result.duration_ms,
            run_id=run_id
        )

        self._snapshots[test_result.test_name].append(snapshot)

        self.logger.debug(
            f"Recorded execution: {test_result.test_name} = {test_result.duration_ms}ms"
        )

        return snapshot

    @handle_errors(component="performance_detector", reraise=False)
    def get_snapshots(
        self,
        test_name: str,
        limit: Optional[int] = None
    ) -> List[PerformanceSnapshot]:
        """
        Get historical snapshots for a test

        Args:
            test_name: Name of the test
            limit: Optional maximum number of snapshots to return

        Returns:
            List of PerformanceSnapshot objects, most recent first
        """
        if test_name not in self._snapshots:
            return []

        snapshots = self._snapshots[test_name].copy()
        # Reverse to get most recent first
        snapshots.reverse()

        if limit:
            snapshots = snapshots[:limit]

        return snapshots

    @handle_errors(component="performance_detector", reraise=True)
    def calculate_baseline(self, test_name: str) -> Optional[PerformanceBaseline]:
        """
        Calculate performance baseline for a test

        Feature #188: Run tests

        Args:
            test_name: Name of the test

        Returns:
            PerformanceBaseline object if enough samples exist, None otherwise
        """
        snapshots = self._snapshots.get(test_name, [])

        if len(snapshots) < self.MIN_BASELINE_SAMPLES:
            self.logger.debug(
                f"Insufficient samples for baseline '{test_name}': "
                f"{len(snapshots)} < {self.MIN_BASELINE_SAMPLES}"
            )
            return None

        # Extract durations
        durations = [s.duration_ms for s in snapshots]

        # Calculate statistics
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)

        # Calculate standard deviation
        variance = sum((d - avg_duration) ** 2 for d in durations) / len(durations)
        std_dev = variance ** 0.5

        # Use earliest and latest timestamps
        created_at = min(s.timestamp for s in snapshots)
        updated_at = max(s.timestamp for s in snapshots)

        baseline = PerformanceBaseline(
            test_name=test_name,
            avg_duration_ms=avg_duration,
            min_duration_ms=min_duration,
            max_duration_ms=max_duration,
            sample_count=len(snapshots),
            std_dev_ms=std_dev,
            created_at=created_at,
            updated_at=updated_at
        )

        # Cache baseline
        self._baselines[test_name] = baseline

        self.logger.info(
            f"Baseline calculated for '{test_name}': "
            f"avg={avg_duration:.0f}ms, min={min_duration}ms, max={max_duration}ms "
            f"(n={len(snapshots)})"
        )

        return baseline

    @handle_errors(component="performance_detector", reraise=True)
    def detect_slowdown(
        self,
        test_result: TestResult,
        run_id: Optional[str] = None
    ) -> Optional[PerformanceRegression]:
        """
        Detect if a test has slowed down significantly

        Feature #188: Verify slowdown is detected

        Args:
            test_result: Current test result
            run_id: Optional run identifier

        Returns:
            PerformanceRegression object if slowdown detected, None otherwise
        """
        # Get or calculate baseline
        baseline = self._baselines.get(test_result.test_name)

        if not baseline:
            baseline = self.calculate_baseline(test_result.test_name)

        if not baseline:
            # No baseline available - can't detect regression
            self.logger.debug(
                f"No baseline available for '{test_result.test_name}' - "
                "cannot detect regression"
            )
            return None

        # Calculate slowdown percentage
        current_duration = test_result.duration_ms
        baseline_duration = baseline.avg_duration_ms

        if baseline_duration == 0:
            self.logger.warning(f"Baseline duration is zero for '{test_result.test_name}'")
            return None

        slowdown_pct = ((current_duration - baseline_duration) / baseline_duration) * 100

        # Check if slowdown exceeds threshold
        if slowdown_pct < self.slowdown_threshold:
            # No significant slowdown
            self.logger.debug(
                f"No slowdown detected for '{test_result.test_name}': "
                f"{slowdown_pct:+.1f}% (threshold: {self.slowdown_threshold}%)"
            )
            return None

        # Determine severity
        if slowdown_pct >= self.SEVERE_THRESHOLD:
            severity = 'severe'
        elif slowdown_pct >= self.MODERATE_THRESHOLD:
            severity = 'moderate'
        else:
            severity = 'minor'

        # Create regression object
        regression = PerformanceRegression(
            test_name=test_result.test_name,
            current_duration_ms=current_duration,
            baseline_duration_ms=baseline_duration,
            slowdown_percentage=slowdown_pct,
            severity=severity,
            threshold_exceeded=self.slowdown_threshold,
            detected_at=datetime.now(),
            run_id=run_id
        )

        self.logger.warning(
            f"⚠️  PERFORMANCE REGRESSION DETECTED: '{test_result.test_name}'\n"
            f"   Current: {current_duration}ms\n"
            f"   Baseline: {baseline_duration:.0f}ms\n"
            f"   Slowdown: {slowdown_pct:+.1f}%\n"
            f"   Severity: {severity}"
        )

        return regression

    @handle_errors(component="performance_detector", reraise=False)
    def check_all_regressions(
        self,
        results: List[TestResult],
        run_id: Optional[str] = None
    ) -> List[PerformanceRegression]:
        """
        Check all test results for performance regressions

        Feature #188: Verify regression is flagged

        Args:
            results: List of test results
            run_id: Optional run identifier

        Returns:
            List of PerformanceRegression objects
        """
        regressions: List[PerformanceRegression] = []

        self.logger.info(f"Checking {len(results)} tests for performance regressions...")

        for result in results:
            # Record this execution
            self.record_execution(result, run_id)

            # Check for regression
            regression = self.detect_slowdown(result, run_id)

            if regression:
                regressions.append(regression)

        # Sort by slowdown percentage (most severe first)
        regressions.sort(key=lambda r: r.slowdown_percentage, reverse=True)

        if regressions:
            self.logger.warning(
                f"Detected {len(regressions)} performance regression(s)"
            )
        else:
            self.logger.info("No performance regressions detected")

        return regressions

    @handle_errors(component="performance_detector", reraise=False)
    def get_slowdown_amount(self, test_name: str) -> Optional[float]:
        """
        Get the current slowdown amount for a test

        Feature #188: Verify slowdown amount is shown

        Args:
            test_name: Name of the test

        Returns:
            Slowdown percentage (e.g., 50.0 for 50% slower) or None if no baseline
        """
        baseline = self._baselines.get(test_name)

        if not baseline:
            baseline = self.calculate_baseline(test_name)

        if not baseline:
            return None

        # Get most recent snapshot
        snapshots = self.get_snapshots(test_name, limit=1)

        if not snapshots:
            return None

        current_duration = snapshots[0].duration_ms
        baseline_duration = baseline.avg_duration_ms

        if baseline_duration == 0:
            return None

        slowdown_pct = ((current_duration - baseline_duration) / baseline_duration) * 100

        return slowdown_pct

    def get_all_baselines(self) -> List[PerformanceBaseline]:
        """
        Get all calculated baselines

        Returns:
            List of PerformanceBaseline objects
        """
        # Calculate baselines for any tests that don't have them yet
        for test_name in self._snapshots:
            if test_name not in self._baselines:
                self.calculate_baseline(test_name)

        return list(self._baselines.values())

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the performance detector

        Returns:
            Dictionary with statistics
        """
        total_snapshots = sum(len(snaps) for snaps in self._snapshots.values())
        total_baselines = len(self._baselines)

        return {
            "total_tests_tracked": len(self._snapshots),
            "total_snapshots": total_snapshots,
            "total_baselines": total_baselines,
            "slowdown_threshold": self.slowdown_threshold,
            "min_baseline_samples": self.MIN_BASELINE_SAMPLES
        }

    def clear_history(self, test_name: Optional[str] = None) -> None:
        """
        Clear history for a specific test or all tests

        Args:
            test_name: Optional test name to clear. If None, clears all history.
        """
        if test_name:
            if test_name in self._snapshots:
                del self._snapshots[test_name]
            if test_name in self._baselines:
                del self._baselines[test_name]
            self.logger.info(f"Cleared history for '{test_name}'")
        else:
            self._snapshots.clear()
            self._baselines.clear()
            self.logger.info("Cleared all history")

    def export_state(self) -> Dict[str, Any]:
        """
        Export performance detector state for persistence

        Returns:
            Dictionary containing all state
        """
        return {
            "slowdown_threshold": self.slowdown_threshold,
            "snapshots": {
                test_name: [s.to_dict() for s in snapshots]
                for test_name, snapshots in self._snapshots.items()
            },
            "baselines": {
                test_name: baseline.to_dict()
                for test_name, baseline in self._baselines.items()
            }
        }

    def import_state(self, state: Dict[str, Any]) -> None:
        """
        Import performance detector state from persistence

        Args:
            state: Dictionary containing exported state
        """
        self.slowdown_threshold = state.get("slowdown_threshold", 50.0)

        # Import snapshots
        for test_name, snapshots_data in state.get("snapshots", {}).items():
            self._snapshots[test_name] = [
                PerformanceSnapshot(
                    timestamp=datetime.fromisoformat(s["timestamp"]),
                    test_name=s["test_name"],
                    duration_ms=s["duration_ms"],
                    run_id=s.get("run_id")
                )
                for s in snapshots_data
            ]

        # Import baselines
        for test_name, baseline_data in state.get("baselines", {}).items():
            self._baselines[test_name] = PerformanceBaseline(
                test_name=baseline_data["test_name"],
                avg_duration_ms=baseline_data["avg_duration_ms"],
                min_duration_ms=baseline_data["min_duration_ms"],
                max_duration_ms=baseline_data["max_duration_ms"],
                sample_count=baseline_data["sample_count"],
                std_dev_ms=baseline_data["std_dev_ms"],
                created_at=datetime.fromisoformat(baseline_data["created_at"]),
                updated_at=datetime.fromisoformat(baseline_data["updated_at"])
            )

        self.logger.info(
            f"Imported state: {len(self._snapshots)} tests, "
            f"{len(self._baselines)} baselines"
        )
