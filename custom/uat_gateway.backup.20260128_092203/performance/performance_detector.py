"""
Performance Detector - Track resource usage during test execution

This module provides performance monitoring capabilities for tracking
memory and CPU usage during UAT test execution.

Features:
- Memory usage tracking (RSS, VMS)
- CPU usage tracking (percentage)
- Resource trend recording
- Performance anomaly detection
- Historical data comparison

Feature #192: Performance detector tracks resource usage
Feature #191: Performance detector identifies likely causes
"""

import psutil
import threading
import time
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import deque
from enum import Enum
import logging
import json
from pathlib import Path

from custom.uat_gateway.utils.logger import get_logger


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class ResourceSnapshot:
    """Single snapshot of resource usage at a point in time"""
    timestamp: datetime
    memory_rss_mb: float  # Resident Set Size (actual physical memory used)
    memory_vms_mb: float  # Virtual Memory Size
    memory_percent: float  # Percentage of total physical memory
    cpu_percent: float  # CPU usage percentage
    cpu_count: int  # Number of CPU cores
    num_threads: int  # Number of threads
    open_files: int  # Number of open file descriptors

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "memory_rss_mb": round(self.memory_rss_mb, 2),
            "memory_vms_mb": round(self.memory_vms_mb, 2),
            "memory_percent": round(self.memory_percent, 2),
            "cpu_percent": round(self.cpu_percent, 2),
            "cpu_count": self.cpu_count,
            "num_threads": self.num_threads,
            "open_files": self.open_files
        }


@dataclass
class ResourceStats:
    """Aggregated statistics over a time period"""
    period_start: datetime
    period_end: datetime
    duration_seconds: float

    # Memory statistics
    memory_rss_avg_mb: float
    memory_rss_max_mb: float
    memory_rss_min_mb: float
    memory_rss_growth_mb: float  # Growth from start to end

    # CPU statistics
    cpu_avg_percent: float
    cpu_max_percent: float
    cpu_min_percent: float

    # Other statistics
    threads_avg: int
    threads_max: int
    open_files_avg: int
    open_files_max: int

    # Snapshot count
    total_snapshots: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "duration_seconds": round(self.duration_seconds, 2),
            "memory": {
                "rss_avg_mb": round(self.memory_rss_avg_mb, 2),
                "rss_max_mb": round(self.memory_rss_max_mb, 2),
                "rss_min_mb": round(self.memory_rss_min_mb, 2),
                "rss_growth_mb": round(self.memory_rss_growth_mb, 2)
            },
            "cpu": {
                "avg_percent": round(self.cpu_avg_percent, 2),
                "max_percent": round(self.cpu_max_percent, 2),
                "min_percent": round(self.cpu_min_percent, 2)
            },
            "threads": {
                "avg": self.threads_avg,
                "max": self.threads_max
            },
            "open_files": {
                "avg": self.open_files_avg,
                "max": self.open_files_max
            },
            "total_snapshots": self.total_snapshots
        }


@dataclass
class PerformanceAlert:
    """Alert for performance anomalies"""
    alert_type: str  # 'memory_leak', 'high_cpu', 'high_memory', 'file_descriptors'
    severity: str  # 'low', 'medium', 'high', 'critical'
    timestamp: datetime
    message: str
    current_value: float
    threshold: float
    snapshot: ResourceSnapshot

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "alert_type": self.alert_type,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "current_value": round(self.current_value, 2),
            "threshold": round(self.threshold, 2),
            "snapshot": self.snapshot.to_dict()
        }


class PerformanceCause(Enum):
    """Likely causes of performance issues (Feature #191)"""
    SLOW_SELECTOR = "slow_selector"
    NETWORK_LATENCY = "network_latency"
    DOM_COMPLEXITY = "dom_complexity"
    TIMEOUT_ISSUE = "timeout_issue"
    RESOURCE_LOAD = "resource_load"
    MEMORY_LEAK = "memory_leak"
    HIGH_CPU = "high_cpu"
    INSUFFICIENT_RESOURCES = "insufficient_resources"
    UNKNOWN = "unknown"


@dataclass
class PerformanceIssue:
    """
    Represents a detected performance issue with likely cause (Feature #191)

    Extends PerformanceAlert with test-specific context and actionable suggestions
    """
    test_name: str
    current_duration_ms: int
    baseline_duration_ms: int
    slowdown_percentage: float
    severity: str  # "low", "medium", "high", "critical"
    likely_cause: PerformanceCause
    cause_description: str
    suggestions: List[str]
    detected_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "current_duration_ms": self.current_duration_ms,
            "baseline_duration_ms": self.baseline_duration_ms,
            "slowdown_percentage": round(self.slowdown_percentage, 2),
            "severity": self.severity,
            "likely_cause": self.likely_cause.value,
            "cause_description": self.cause_description,
            "suggestions": self.suggestions,
            "detected_at": self.detected_at.isoformat()
        }


# ============================================================================
# Performance Detector
# ============================================================================

class PerformanceDetector:
    """
    Tracks resource usage during test execution

    Features:
    - Automatic monitoring in background thread
    - Configurable sampling interval
    - Resource trend analysis
    - Performance anomaly detection
    - Historical data retention

    Usage:
        detector = PerformanceDetector()
        detector.start()

        # Run tests...

        detector.stop()
        stats = detector.get_statistics()
        snapshots = detector.get_snapshots()
        alerts = detector.get_alerts()
    """

    def __init__(
        self,
        sampling_interval: float = 1.0,  # Seconds between snapshots
        max_snapshots: int = 10000,  # Maximum snapshots to retain
        memory_leak_threshold_mb: float = 100.0,  # Memory growth threshold
        high_cpu_threshold: float = 80.0,  # CPU usage threshold (%)
        high_memory_threshold: float = 80.0,  # Memory usage threshold (%)
        max_file_descriptors: int = 1000  # File descriptor threshold
    ):
        self.logger = get_logger(__name__)
        self.sampling_interval = sampling_interval
        self.max_snapshots = max_snapshots

        # Thresholds for alerting
        self.memory_leak_threshold_mb = memory_leak_threshold_mb
        self.high_cpu_threshold = high_cpu_threshold
        self.high_memory_threshold = high_memory_threshold
        self.max_file_descriptors = max_file_descriptors

        # State
        self._process = psutil.Process()
        self._snapshots: deque[ResourceSnapshot] = deque(maxlen=max_snapshots)
        self._alerts: List[PerformanceAlert] = []
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._start_time: Optional[datetime] = None
        self._stop_time: Optional[datetime] = None

        # Callback for real-time updates
        self._on_snapshot_callback: Optional[Callable[[ResourceSnapshot], None]] = None

    def start(self) -> None:
        """Start monitoring resource usage in background thread"""
        if self._monitoring:
            self.logger.warning("Performance monitoring already started")
            return

        self._monitoring = True
        self._start_time = datetime.now()
        self._stop_time = None
        self._snapshots.clear()
        self._alerts.clear()

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="PerformanceDetector"
        )
        self._monitor_thread.start()

        self.logger.info(f"Performance monitoring started (interval: {self.sampling_interval}s)")

    def stop(self) -> None:
        """Stop monitoring resource usage"""
        if not self._monitoring:
            self.logger.warning("Performance monitoring not running")
            return

        self._monitoring = False

        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
            self._monitor_thread = None

        self._stop_time = datetime.now()
        self.logger.info("Performance monitoring stopped")

    def _monitor_loop(self) -> None:
        """Background thread that collects resource snapshots"""
        while self._monitoring:
            try:
                snapshot = self._take_snapshot()
                self._snapshots.append(snapshot)

                # Check for performance anomalies
                self._check_for_alerts(snapshot)

                # Call callback if registered
                if self._on_snapshot_callback:
                    try:
                        self._on_snapshot_callback(snapshot)
                    except Exception as e:
                        self.logger.error(f"Error in snapshot callback: {e}")

            except Exception as e:
                self.logger.error(f"Error taking resource snapshot: {e}")

            # Sleep until next snapshot
            time.sleep(self.sampling_interval)

    def _take_snapshot(self) -> ResourceSnapshot:
        """Take a snapshot of current resource usage"""
        try:
            # Memory info
            memory_info = self._process.memory_info()
            memory_rss_mb = memory_info.rss / (1024 * 1024)  # Convert to MB
            memory_vms_mb = memory_info.vms / (1024 * 1024)
            memory_percent = self._process.memory_percent()

            # CPU info
            cpu_percent = self._process.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()

            # Thread and file descriptor count
            num_threads = self._process.num_threads()
            try:
                open_files = len(self._process.open_files())
            except (psutil.AccessDenied, NotImplementedError):
                open_files = 0

            return ResourceSnapshot(
                timestamp=datetime.now(),
                memory_rss_mb=memory_rss_mb,
                memory_vms_mb=memory_vms_mb,
                memory_percent=memory_percent,
                cpu_percent=cpu_percent,
                cpu_count=cpu_count,
                num_threads=num_threads,
                open_files=open_files
            )
        except Exception as e:
            self.logger.error(f"Error collecting resource metrics: {e}")
            # Return snapshot with zeros on error
            return ResourceSnapshot(
                timestamp=datetime.now(),
                memory_rss_mb=0.0,
                memory_vms_mb=0.0,
                memory_percent=0.0,
                cpu_percent=0.0,
                cpu_count=0,
                num_threads=0,
                open_files=0
            )

    def _check_for_alerts(self, snapshot: ResourceSnapshot) -> None:
        """Check snapshot for performance anomalies"""
        # Need at least 10 snapshots to detect trends
        if len(self._snapshots) < 10:
            return

        # Check for memory leak (continuous growth)
        first_snapshot = self._snapshots[0]
        memory_growth = snapshot.memory_rss_mb - first_snapshot.memory_rss_mb

        if memory_growth > self.memory_leak_threshold_mb:
            alert = PerformanceAlert(
                alert_type="memory_leak",
                severity=self._calculate_severity(memory_growth, self.memory_leak_threshold_mb * 2),
                timestamp=snapshot.timestamp,
                message=f"Memory has grown by {memory_growth:.1f} MB since monitoring started",
                current_value=memory_growth,
                threshold=self.memory_leak_threshold_mb,
                snapshot=snapshot
            )
            self._alerts.append(alert)
            self.logger.warning(f"Memory leak detected: {memory_growth:.1f} MB growth")

        # Check for high CPU usage
        if snapshot.cpu_percent > self.high_cpu_threshold:
            alert = PerformanceAlert(
                alert_type="high_cpu",
                severity=self._calculate_severity(snapshot.cpu_percent, 95.0),
                timestamp=snapshot.timestamp,
                message=f"CPU usage is {snapshot.cpu_percent:.1f}%",
                current_value=snapshot.cpu_percent,
                threshold=self.high_cpu_threshold,
                snapshot=snapshot
            )
            self._alerts.append(alert)
            self.logger.warning(f"High CPU usage: {snapshot.cpu_percent:.1f}%")

        # Check for high memory usage
        if snapshot.memory_percent > self.high_memory_threshold:
            alert = PerformanceAlert(
                alert_type="high_memory",
                severity=self._calculate_severity(snapshot.memory_percent, 95.0),
                timestamp=snapshot.timestamp,
                message=f"Memory usage is {snapshot.memory_percent:.1f}%",
                current_value=snapshot.memory_percent,
                threshold=self.high_memory_threshold,
                snapshot=snapshot
            )
            self._alerts.append(alert)
            self.logger.warning(f"High memory usage: {snapshot.memory_percent:.1f}%")

        # Check for file descriptor leaks
        if snapshot.open_files > self.max_file_descriptors:
            alert = PerformanceAlert(
                alert_type="file_descriptors",
                severity=self._calculate_severity(snapshot.open_files, self.max_file_descriptors * 1.5),
                timestamp=snapshot.timestamp,
                message=f"Open file descriptors: {snapshot.open_files}",
                current_value=snapshot.open_files,
                threshold=self.max_file_descriptors,
                snapshot=snapshot
            )
            self._alerts.append(alert)
            self.logger.warning(f"High file descriptor count: {snapshot.open_files}")

    def _calculate_severity(self, value: float, critical_threshold: float) -> str:
        """Calculate alert severity based on value"""
        if value >= critical_threshold:
            return "critical"
        elif value >= critical_threshold * 0.8:
            return "high"
        elif value >= critical_threshold * 0.6:
            return "medium"
        else:
            return "low"

    # ==========================================================================
    # Feature #191: Identify Likely Causes of Performance Issues
    # ==========================================================================

    def identify_cause_from_alert(self, alert: PerformanceAlert, test_name: str = "unknown") -> PerformanceIssue:
        """
        Identify likely cause of performance issue from an alert

        Feature #191 implementation: Analyzes alerts to determine specific causes

        Args:
            alert: The performance alert
            test_name: Name of the test that triggered the alert

        Returns:
            PerformanceIssue with likely cause and suggestions
        """
        # Map alert type to performance cause
        cause_map = {
            "memory_leak": PerformanceCause.MEMORY_LEAK,
            "high_cpu": PerformanceCause.HIGH_CPU,
            "high_memory": PerformanceCause.INSUFFICIENT_RESOURCES,
            "file_descriptors": PerformanceCause.INSUFFICIENT_RESOURCES
        }

        likely_cause = cause_map.get(alert.alert_type, PerformanceCause.UNKNOWN)
        cause_description = self._get_cause_description_for_alert(alert, likely_cause)
        suggestions = self._get_suggestions_for_cause(likely_cause)

        return PerformanceIssue(
            test_name=test_name,
            current_duration_ms=0,  # Alerts don't track duration
            baseline_duration_ms=0,
            slowdown_percentage=0.0,
            severity=alert.severity,
            likely_cause=likely_cause,
            cause_description=cause_description,
            suggestions=suggestions,
            detected_at=alert.timestamp
        )

    def identify_cause_from_test_duration(
        self,
        test_name: str,
        duration_ms: int,
        baseline_ms: float,
        error_message: Optional[str] = None
    ) -> Optional[PerformanceIssue]:
        """
        Identify likely cause of slow test execution

        Feature #191 implementation: Analyzes test duration to identify causes

        Args:
            test_name: Name of the test
            duration_ms: Current execution duration
            baseline_ms: Baseline average duration
            error_message: Optional error message for context

        Returns:
            PerformanceIssue if significant slowdown detected, None otherwise
        """
        # Calculate slowdown percentage
        if baseline_ms == 0:
            return None

        slowdown_pct = ((duration_ms - baseline_ms) / baseline_ms) * 100

        # Only flag significant slowdowns (>30%)
        if slowdown_pct < 30:
            return None

        # Determine severity
        if slowdown_pct >= 100:
            severity = "critical"
        elif slowdown_pct >= 75:
            severity = "high"
        elif slowdown_pct >= 50:
            severity = "medium"
        else:
            severity = "low"

        # Identify likely cause
        likely_cause = self._identify_cause_from_duration(duration_ms, error_message, baseline_ms)
        cause_description = self._get_cause_description_for_duration(
            likely_cause, duration_ms, baseline_ms, slowdown_pct
        )
        suggestions = self._get_suggestions_for_cause(likely_cause)

        return PerformanceIssue(
            test_name=test_name,
            current_duration_ms=duration_ms,
            baseline_duration_ms=int(baseline_ms),
            slowdown_percentage=slowdown_pct,
            severity=severity,
            likely_cause=likely_cause,
            cause_description=cause_description,
            suggestions=suggestions
        )

    def _identify_cause_from_duration(
        self,
        duration_ms: int,
        error_message: Optional[str],
        baseline_ms: float
    ) -> PerformanceCause:
        """Identify likely cause based on duration and error message"""
        # Check error message for clues
        if error_message:
            error_lower = error_message.lower()

            # Network issues - check FIRST (more specific than timeout)
            if any(term in error_lower for term in ["networkerror", "network error", "connection", "500", "502", "503", "504"]):
                return PerformanceCause.NETWORK_LATENCY

            # API errors
            if any(term in error_lower for term in ["apierror", "api error", "server error"]):
                return PerformanceCause.NETWORK_LATENCY

            # Timeout issues - but only if not network-related
            if "timeout" in error_lower:
                if "selector" in error_lower or "element" in error_lower or "waiting for" in error_lower:
                    return PerformanceCause.SLOW_SELECTOR
                elif "network" in error_lower or "connection" in error_lower:
                    return PerformanceCause.NETWORK_LATENCY
                else:
                    return PerformanceCause.TIMEOUT_ISSUE

            # Resource loading
            if any(term in error_lower for term in ["load", "resource", "image", "script"]):
                return PerformanceCause.RESOURCE_LOAD

        # Analyze duration patterns
        # Very slow (>10s) suggests network/timeout issues
        if duration_ms > 10000:
            if baseline_ms < 5000:
                # Sudden spike to >10s suggests timeout or network
                return PerformanceCause.TIMEOUT_ISSUE
            else:
                return PerformanceCause.NETWORK_LATENCY

        # Moderate slowdown (2-5s) could be DOM complexity or selector issues
        if duration_ms > 2000:
            return PerformanceCause.DOM_COMPLEXITY

        # Default: unknown
        return PerformanceCause.UNKNOWN

    def _get_cause_description_for_alert(
        self,
        alert: PerformanceAlert,
        cause: PerformanceCause
    ) -> str:
        """Get description for resource-based alerts"""
        descriptions = {
            PerformanceCause.MEMORY_LEAK: (
                f"Memory usage has grown significantly during test execution. "
                f"Current growth: {alert.current_value:.1f} MB (threshold: {alert.threshold:.1f} MB). "
                f"This indicates a possible memory leak - objects are being allocated but not properly released."
            ),
            PerformanceCause.HIGH_CPU: (
                f"CPU usage is consistently high during test execution. "
                f"Current usage: {alert.current_value:.1f}% (threshold: {alert.threshold:.1f}%). "
                f"This could be due to inefficient loops, excessive computations, or busy-waiting."
            ),
            PerformanceCause.INSUFFICIENT_RESOURCES: (
                f"System resources are under pressure. "
                f"This could be insufficient memory, too many open file descriptors, "
                f"or overall system overload affecting test performance."
            ),
            PerformanceCause.UNKNOWN: (
                f"Performance anomaly detected but cause is unclear. "
                f"{alert.message}"
            )
        }

        return descriptions.get(cause, descriptions[PerformanceCause.UNKNOWN])

    def _get_cause_description_for_duration(
        self,
        cause: PerformanceCause,
        duration_ms: int,
        baseline_ms: float,
        slowdown_pct: float
    ) -> str:
        """Get description for duration-based issues"""
        descriptions = {
            PerformanceCause.SLOW_SELECTOR: (
                f"Test execution slowed by {slowdown_pct:.1f}% due to slow selector resolution. "
                f"Current time ({duration_ms}ms) is much higher than baseline ({baseline_ms:.0f}ms). "
                f"This could be due to complex CSS selectors, deep DOM traversal, "
                f"or waiting for elements that are slow to render."
            ),
            PerformanceCause.NETWORK_LATENCY: (
                f"Test execution slowed by {slowdown_pct:.1f}% due to network latency. "
                f"Current time ({duration_ms}ms) vs baseline ({baseline_ms:.0f}ms). "
                f"Slow API responses, large payloads, or network congestion are likely causes."
            ),
            PerformanceCause.DOM_COMPLEXITY: (
                f"Test execution slowed by {slowdown_pct:.1f}% due to DOM complexity. "
                f"Current time ({duration_ms}ms) vs baseline ({baseline_ms:.0f}ms). "
                f"High DOM complexity, frequent reflows/repaints, or many elements are slowing down the test."
            ),
            PerformanceCause.TIMEOUT_ISSUE: (
                f"Test execution slowed by {slowdown_pct:.1f}% due to timeout issues. "
                f"Current time ({duration_ms}ms) vs baseline ({baseline_ms:.0f}ms). "
                f"Tests are waiting too long for elements or operations that don't complete in time."
            ),
            PerformanceCause.RESOURCE_LOAD: (
                f"Test execution slowed by {slowdown_pct:.1f}% due to slow resource loading. "
                f"Current time ({duration_ms}ms) vs baseline ({baseline_ms:.0f}ms). "
                f"Large assets, unoptimized resources, or slow CDN delivery are delaying test execution."
            ),
            PerformanceCause.UNKNOWN: (
                f"Performance issue detected but cause is unclear. "
                f"Test execution time ({duration_ms}ms) is {slowdown_pct:.1f}% higher than baseline ({baseline_ms:.0f}ms). "
                f"Further investigation needed."
            )
        }

        return descriptions.get(cause, descriptions[PerformanceCause.UNKNOWN])

    def _get_suggestions_for_cause(self, cause: PerformanceCause) -> List[str]:
        """Get actionable suggestions for fixing the performance issue"""
        suggestions_map = {
            PerformanceCause.SLOW_SELECTOR: [
                "Use more specific and efficient selectors (e.g., data-testid attributes)",
                "Avoid complex XPath selectors that traverse the entire DOM",
                "Wait for specific elements instead of using arbitrary timeouts",
                "Consider using role-based selectors or aria labels",
                "Add explicit waits for elements that are slow to render"
            ],
            PerformanceCause.NETWORK_LATENCY: [
                "Check backend API performance and optimize slow endpoints",
                "Implement request caching where appropriate",
                "Use pagination to reduce payload sizes",
                "Optimize database queries that power API responses",
                "Consider using a CDN for static assets"
            ],
            PerformanceCause.DOM_COMPLEXITY: [
                "Reduce the number of DOM elements in the page",
                "Avoid deeply nested DOM structures",
                "Use virtual scrolling for long lists",
                "Implement lazy loading for off-screen content",
                "Minimize reflows and repaints by batching DOM updates"
            ],
            PerformanceCause.TIMEOUT_ISSUE: [
                "Verify that elements are actually being rendered",
                "Check for JavaScript errors that might block rendering",
                "Increase timeout values if the operation legitimately takes longer",
                "Add explicit waits for conditions instead of fixed timeouts",
                "Investigate application logs for errors or warnings"
            ],
            PerformanceCause.RESOURCE_LOAD: [
                "Optimize image sizes and use modern formats (WebP, AVIF)",
                "Minify and compress JavaScript and CSS files",
                "Implement code splitting to reduce initial bundle size",
                "Use lazy loading for images and below-the-fold content",
                "Leverage browser caching headers"
            ],
            PerformanceCause.MEMORY_LEAK: [
                "Check for event listeners that are not properly removed",
                "Verify closures are not retaining large objects",
                "Look for caches that grow without bounds",
                "Check for circular references in object graphs",
                "Use browser DevTools Memory profiler to identify leaked objects"
            ],
            PerformanceCause.HIGH_CPU: [
                "Check for infinite loops or excessive iterations",
                "Look for busy-waiting patterns that should use async/await",
                "Optimize expensive computations or move to web workers",
                "Reduce frequency of polling operations",
                "Use requestIdleCallback for non-critical work"
            ],
            PerformanceCause.INSUFFICIENT_RESOURCES: [
                "Close file handles and database connections when done",
                "Implement connection pooling for databases",
                "Reduce memory footprint by streaming instead of buffering",
                "Implement resource limits and cleanup procedures",
                "Consider scaling to larger hardware or optimizing resource usage"
            ],
            PerformanceCause.UNKNOWN: [
                "Run the test in headed mode to observe what's happening",
                "Check browser console for JavaScript errors",
                "Review network tab in browser DevTools for slow requests",
                "Take screenshots at various points to identify where slowdown occurs",
                "Compare with a passing test run to identify differences"
            ]
        }

        return suggestions_map.get(cause, suggestions_map[PerformanceCause.UNKNOWN])

    def get_snapshots(self) -> List[ResourceSnapshot]:
        """Get all collected resource snapshots"""
        return list(self._snapshots)

    def get_statistics(self) -> Optional[ResourceStats]:
        """
        Calculate aggregate statistics from all snapshots

        Returns None if no snapshots collected
        """
        if not self._snapshots:
            return None

        snapshots = list(self._snapshots)

        # Time period
        period_start = snapshots[0].timestamp
        period_end = snapshots[-1].timestamp
        duration_seconds = (period_end - period_start).total_seconds()

        # Memory statistics
        memory_rss_values = [s.memory_rss_mb for s in snapshots]
        memory_rss_avg = sum(memory_rss_values) / len(memory_rss_values)
        memory_rss_max = max(memory_rss_values)
        memory_rss_min = min(memory_rss_values)
        memory_rss_growth = memory_rss_values[-1] - memory_rss_values[0]

        # CPU statistics
        cpu_values = [s.cpu_percent for s in snapshots]
        cpu_avg = sum(cpu_values) / len(cpu_values)
        cpu_max = max(cpu_values)
        cpu_min = min(cpu_values)

        # Thread statistics
        thread_values = [s.num_threads for s in snapshots]
        threads_avg = int(sum(thread_values) / len(thread_values))
        threads_max = max(thread_values)

        # File descriptor statistics
        file_values = [s.open_files for s in snapshots]
        files_avg = int(sum(file_values) / len(file_values))
        files_max = max(file_values)

        return ResourceStats(
            period_start=period_start,
            period_end=period_end,
            duration_seconds=duration_seconds,
            memory_rss_avg_mb=memory_rss_avg,
            memory_rss_max_mb=memory_rss_max,
            memory_rss_min_mb=memory_rss_min,
            memory_rss_growth_mb=memory_rss_growth,
            cpu_avg_percent=cpu_avg,
            cpu_max_percent=cpu_max,
            cpu_min_percent=cpu_min,
            threads_avg=threads_avg,
            threads_max=threads_max,
            open_files_avg=files_avg,
            open_files_max=files_max,
            total_snapshots=len(snapshots)
        )

    def get_alerts(self) -> List[PerformanceAlert]:
        """Get all generated performance alerts"""
        return self._alerts.copy()

    def get_latest_snapshot(self) -> Optional[ResourceSnapshot]:
        """Get the most recent snapshot"""
        if not self._snapshots:
            return None
        return self._snapshots[-1]

    def is_monitoring(self) -> bool:
        """Check if monitoring is currently active"""
        return self._monitoring

    def set_snapshot_callback(self, callback: Callable[[ResourceSnapshot], None]) -> None:
        """
        Set callback function to be called on each snapshot

        Useful for real-time updates via WebSocket
        """
        self._on_snapshot_callback = callback

    def clear_alerts(self) -> None:
        """Clear all alerts"""
        self._alerts.clear()

    def get_duration_seconds(self) -> Optional[float]:
        """Get the duration of monitoring in seconds"""
        if not self._start_time:
            return None

        end_time = self._stop_time or datetime.now()
        return (end_time - self._start_time).total_seconds()


# ============================================================================
# Convenience Functions
# ============================================================================

def create_performance_detector(
    sampling_interval: float = 1.0,
    max_snapshots: int = 10000
) -> PerformanceDetector:
    """
    Factory function to create and configure a PerformanceDetector

    Args:
        sampling_interval: Seconds between resource snapshots
        max_snapshots: Maximum snapshots to retain in memory

    Returns:
        Configured PerformanceDetector instance
    """
    return PerformanceDetector(
        sampling_interval=sampling_interval,
        max_snapshots=max_snapshots
    )


def get_system_info() -> Dict[str, Any]:
    """
    Get static system information

    Returns information about CPU, memory, and system configuration
    that doesn't change during execution.
    """
    return {
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "cpu_freq_max": psutil.cpu_freq().max if psutil.cpu_freq() else None,
        "memory_total_mb": psutil.virtual_memory().total / (1024 * 1024),
        "memory_available_mb": psutil.virtual_memory().available / (1024 * 1024),
        "swap_total_mb": psutil.swap_memory().total / (1024 * 1024),
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat()
    }
