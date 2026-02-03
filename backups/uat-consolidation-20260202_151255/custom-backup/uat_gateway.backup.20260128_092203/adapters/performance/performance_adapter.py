"""
Performance Adapter - Measure page load performance metrics

This module is responsible for:
- Measuring page load times
- Capturing resource timing data
- Tracking navigation timing
- Analyzing performance bottlenecks
- Generating performance reports
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import AdapterError, handle_errors


# ============================================================================
# Data Models
# ============================================================================

class PerformanceMetricType(Enum):
    """Types of performance metrics"""
    PAGE_LOAD = "page_load"
    DOM_CONTENT_LOADED = "dom_content_loaded"
    FIRST_PAINT = "first_paint"
    FIRST_CONTENTFUL_PAINT = "first_contentful_paint"
    LARGEST_CONTENTFUL_PAINT = "largest_contentful_paint"
    FIRST_INPUT_DELAY = "first_input_delay"
    CUMULATIVE_LAYOUT_SHIFT = "cumulative_layout_shift"
    TIME_TO_INTERACTIVE = "time_to_interactive"
    TOTAL_BLOCKING_TIME = "total_blocking_time"


@dataclass
class ResourceTiming:
    """Represents timing data for a single resource"""
    name: str  # Resource URL
    resource_type: str  # 'script', 'stylesheet', 'image', 'fetch', 'xhr', etc.
    duration: float  # Total duration in milliseconds
    transfer_size: int  # Size in bytes
    encoded_body_size: int  # Encoded body size in bytes
    decoded_body_size: int  # Decoded body size in bytes
    start_time: float  # When resource started loading (relative to navigation start)
    response_end: float  # When response was received

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "resource_type": self.resource_type,
            "duration": round(self.duration, 2),
            "transfer_size": self.transfer_size,
            "encoded_body_size": self.encoded_body_size,
            "decoded_body_size": self.decoded_body_size,
            "start_time": round(self.start_time, 2),
            "response_end": round(self.response_end, 2)
        }


@dataclass
class NavigationTiming:
    """Navigation timing metrics for a page load"""
    navigation_start: float = 0.0
    dom_complete: float = 0.0
    dom_content_loaded: float = 0.0
    load_event_end: float = 0.0
    fetch_start: float = 0.0
    domain_lookup_start: float = 0.0
    domain_lookup_end: float = 0.0
    connect_start: float = 0.0
    connect_end: float = 0.0
    request_start: float = 0.0
    response_start: float = 0.0
    response_end: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "navigation_start": round(self.navigation_start, 2),
            "dom_complete": round(self.dom_complete, 2),
            "dom_content_loaded": round(self.dom_content_loaded, 2),
            "load_event_end": round(self.load_event_end, 2),
            "fetch_start": round(self.fetch_start, 2),
            "domain_lookup_start": round(self.domain_lookup_start, 2),
            "domain_lookup_end": round(self.domain_lookup_end, 2),
            "connect_start": round(self.connect_start, 2),
            "connect_end": round(self.connect_end, 2),
            "request_start": round(self.request_start, 2),
            "response_start": round(self.response_start, 2),
            "response_end": round(self.response_end, 2)
        }


@dataclass
class PerformanceMetric:
    """A single performance metric measurement"""
    metric_type: PerformanceMetricType
    value: float  # Metric value in milliseconds
    name: str  # Human-readable name
    description: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    url: str = ""  # URL where metric was collected

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "metric_type": self.metric_type.value,
            "value": round(self.value, 2),
            "name": self.name,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "url": self.url
        }


@dataclass
class PageLoadMeasurement:
    """Complete page load performance measurement"""
    url: str
    page_title: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    navigation_timing: Optional[NavigationTiming] = None
    metrics: List[PerformanceMetric] = field(default_factory=list)
    resources: List[ResourceTiming] = field(default_factory=list)
    total_load_time_ms: float = 0.0
    dom_content_loaded_ms: float = 0.0
    first_paint_ms: Optional[float] = None
    first_contentful_paint_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "url": self.url,
            "page_title": self.page_title,
            "timestamp": self.timestamp.isoformat(),
            "navigation_timing": self.navigation_timing.to_dict() if self.navigation_timing else None,
            "metrics": [m.to_dict() for m in self.metrics],
            "resources": [r.to_dict() for r in self.resources],
            "total_load_time_ms": round(self.total_load_time_ms, 2),
            "dom_content_loaded_ms": round(self.dom_content_loaded_ms, 2),
            "first_paint_ms": round(self.first_paint_ms, 2) if self.first_paint_ms else None,
            "first_contentful_paint_ms": round(self.first_contentful_paint_ms, 2) if self.first_contentful_paint_ms else None
        }


@dataclass
class PerformanceThreshold:
    """Performance threshold for evaluation"""
    metric_type: PerformanceMetricType
    threshold_ms: float  # Threshold value in milliseconds
    comparison: str  # 'less_than', 'greater_than', 'equals'
    severity: str = 'warning'  # 'info', 'warning', 'error', 'critical'
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "metric_type": self.metric_type.value,
            "threshold_ms": self.threshold_ms,
            "comparison": self.comparison,
            "severity": self.severity,
            "description": self.description
        }


@dataclass
class ThresholdViolation:
    """Represents a threshold violation"""
    metric_type: PerformanceMetricType
    actual_value: float
    threshold_value: float
    severity: str
    description: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "metric_type": self.metric_type.value,
            "actual_value": round(self.actual_value, 2),
            "threshold_value": round(self.threshold_value, 2),
            "severity": self.severity,
            "description": self.description,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class PerformanceReport:
    """Performance evaluation report"""
    url: str
    timestamp: datetime
    measurement: PageLoadMeasurement
    violations: List[ThresholdViolation]
    score: float  # Overall performance score (0-100)
    grade: str  # 'A', 'B', 'C', 'D', 'F'
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "url": self.url,
            "timestamp": self.timestamp.isoformat(),
            "measurement": self.measurement.to_dict(),
            "violations": [v.to_dict() for v in self.violations],
            "score": round(self.score, 2),
            "grade": self.grade,
            "recommendations": self.recommendations
        }


# ============================================================================
# Performance Adapter Implementation
# ============================================================================

class PerformanceAdapter:
    """
    Performance measurement adapter for page load metrics

    This adapter handles:
    - Measuring page load times
    - Capturing resource timing data
    - Evaluating performance against thresholds
    - Generating performance reports
    """

    def __init__(
        self,
        thresholds: Optional[List[PerformanceThreshold]] = None,
        enable_resource_timing: bool = True,
        enable_navigation_timing: bool = True
    ):
        """
        Initialize the Performance Adapter

        Args:
            thresholds: List of performance thresholds to evaluate
            enable_resource_timing: Enable resource timing capture
            enable_navigation_timing: Enable navigation timing capture
        """
        self.logger = get_logger(__name__)
        self.enable_resource_timing = enable_resource_timing
        self.enable_navigation_timing = enable_navigation_timing
        self.thresholds = thresholds or self._default_thresholds()
        self.measurements: List[PageLoadMeasurement] = []

        self.logger.info("PerformanceAdapter initialized")

    def _default_thresholds(self) -> List[PerformanceThreshold]:
        """
        Get default performance thresholds

        Web Vitals thresholds (Google Core Web Vitals):
        - LCP (Largest Contentful Paint): < 2.5s good, < 4s needs improvement
        - FID (First Input Delay): < 100ms good, < 300ms needs improvement
        - CLS (Cumulative Layout Shift): < 0.1 good, < 0.25 needs improvement
        - FCP (First Contentful Paint): < 1.8s good
        - TTI (Time to Interactive): < 3.8s good
        - Page Load: < 3s good, < 5s acceptable

        Returns:
            List of default performance thresholds
        """
        return [
            PerformanceThreshold(
                metric_type=PerformanceMetricType.PAGE_LOAD,
                threshold_ms=3000,
                comparison='less_than',
                severity='warning',
                description="Page load time should be under 3 seconds"
            ),
            PerformanceThreshold(
                metric_type=PerformanceMetricType.DOM_CONTENT_LOADED,
                threshold_ms=2000,
                comparison='less_than',
                severity='info',
                description="DOM Content Loaded should be under 2 seconds"
            ),
            PerformanceThreshold(
                metric_type=PerformanceMetricType.FIRST_CONTENTFUL_PAINT,
                threshold_ms=1800,
                comparison='less_than',
                severity='warning',
                description="First Contentful Paint should be under 1.8 seconds"
            ),
            PerformanceThreshold(
                metric_type=PerformanceMetricType.LARGEST_CONTENTFUL_PAINT,
                threshold_ms=2500,
                comparison='less_than',
                severity='critical',
                description="Largest Contentful Paint should be under 2.5 seconds"
            ),
            PerformanceThreshold(
                metric_type=PerformanceMetricType.FIRST_INPUT_DELAY,
                threshold_ms=100,
                comparison='less_than',
                severity='critical',
                description="First Input Delay should be under 100ms"
            ),
            PerformanceThreshold(
                metric_type=PerformanceMetricType.CUMULATIVE_LAYOUT_SHIFT,
                threshold_ms=0.1,
                comparison='less_than',
                severity='critical',
                description="Cumulative Layout Shift should be under 0.1"
            ),
            PerformanceThreshold(
                metric_type=PerformanceMetricType.TIME_TO_INTERACTIVE,
                threshold_ms=3800,
                comparison='less_than',
                severity='warning',
                description="Time to Interactive should be under 3.8 seconds"
            )
        ]

    @handle_errors(component="performance_adapter", reraise=True)
    def measure_from_timing_data(
        self,
        url: str,
        timing_data: Dict[str, Any],
        performance_entries: Optional[List[Dict[str, Any]]] = None
    ) -> PageLoadMeasurement:
        """
        Create performance measurement from browser timing data

        Feature #189 implementation:
        - Run test with navigation
        - Check load time
        - Verify load time is recorded
        - Verify resource timing is captured
        - Verify timing is accurate

        Args:
            url: URL that was measured
            timing_data: Navigation timing data from browser
            performance_entries: Optional performance entries (resource timing, paint timing, etc.)

        Returns:
            PageLoadMeasurement with captured metrics

        Raises:
            AdapterError: If timing data is invalid
        """
        self.logger.info(f"Measuring performance for: {url}")

        measurement = PageLoadMeasurement(url=url)

        # Extract navigation timing
        if timing_data:
            measurement.navigation_timing = NavigationTiming(
                navigation_start=timing_data.get('navigationStart', 0),
                dom_complete=timing_data.get('domComplete', 0),
                dom_content_loaded=timing_data.get('domContentLoadedEventEnd', 0),
                load_event_end=timing_data.get('loadEventEnd', 0),
                fetch_start=timing_data.get('fetchStart', 0),
                domain_lookup_start=timing_data.get('domainLookupStart', 0),
                domain_lookup_end=timing_data.get('domainLookupEnd', 0),
                connect_start=timing_data.get('connectStart', 0),
                connect_end=timing_data.get('connectEnd', 0),
                request_start=timing_data.get('requestStart', 0),
                response_start=timing_data.get('responseStart', 0),
                response_end=timing_data.get('responseEnd', 0)
            )

            # Calculate key metrics (all relative to navigation_start)
            nav_start = timing_data.get('navigationStart', 0)

            # Total page load time (from navigation start to load event end)
            if 'loadEventEnd' in timing_data:
                measurement.total_load_time_ms = timing_data['loadEventEnd'] - nav_start

            # DOM Content Loaded time
            if 'domContentLoadedEventEnd' in timing_data:
                measurement.dom_content_loaded_ms = timing_data['domContentLoadedEventEnd'] - nav_start

        # Process performance entries if provided
        if performance_entries:
            for entry in performance_entries:
                entry_type = entry.get('entryType', '')

                # Paint timing entries
                if entry_type == 'paint':
                    name = entry.get('name', '')
                    start_time = entry.get('startTime', 0)

                    if name == 'first-paint':
                        measurement.first_paint_ms = start_time
                        measurement.metrics.append(PerformanceMetric(
                            metric_type=PerformanceMetricType.FIRST_PAINT,
                            value=start_time,
                            name="First Paint",
                            description="First pixel rendered to screen",
                            url=url
                        ))
                    elif name == 'first-contentful-paint':
                        measurement.first_contentful_paint_ms = start_time
                        measurement.metrics.append(PerformanceMetric(
                            metric_type=PerformanceMetricType.FIRST_CONTENTFUL_PAINT,
                            value=start_time,
                            name="First Contentful Paint",
                            description="First meaningful content rendered",
                            url=url
                        ))

                # Resource timing entries
                elif entry_type == 'resource' and self.enable_resource_timing:
                    resource = ResourceTiming(
                        name=entry.get('name', ''),
                        resource_type=self._determine_resource_type(entry.get('name', '')),
                        duration=entry.get('duration', 0),
                        transfer_size=entry.get('transferSize', 0),
                        encoded_body_size=entry.get('encodedBodySize', 0),
                        decoded_body_size=entry.get('decodedBodySize', 0),
                        start_time=entry.get('startTime', 0),
                        response_end=entry.get('responseEnd', 0)
                    )
                    measurement.resources.append(resource)

                # Navigation timing entries (alternative source)
                elif entry_type == 'navigation' and self.enable_navigation_timing:
                    if not measurement.navigation_timing:
                        measurement.navigation_timing = NavigationTiming(
                            navigation_start=entry.get('startTime', 0),
                            dom_complete=entry.get('domComplete', 0),
                            dom_content_loaded=entry.get('domContentLoadedEventEnd', 0),
                            load_event_end=entry.get('loadEventEnd', 0),
                            response_start=entry.get('responseStart', 0),
                            response_end=entry.get('responseEnd', 0)
                        )

                # Largest Contentful Paint
                elif entry_type == 'largest-contentful-paint':
                    lcp_value = entry.get('startTime', 0)
                    measurement.metrics.append(PerformanceMetric(
                        metric_type=PerformanceMetricType.LARGEST_CONTENTFUL_PAINT,
                        value=lcp_value,
                        name="Largest Contentful Paint",
                        description="Time to render largest content element",
                        url=url
                    ))

                # First Input Delay
                elif entry_type == 'first-input':
                    fid_value = entry.get('processingStart', 0) - entry.get('startTime', 0)
                    measurement.metrics.append(PerformanceMetric(
                        metric_type=PerformanceMetricType.FIRST_INPUT_DELAY,
                        value=fid_value,
                        name="First Input Delay",
                        description="Delay from user input to browser response",
                        url=url
                    ))

                # Layout Shift
                elif entry_type == 'layout-shift':
                    # Cumulative Layout Shift is calculated separately
                    pass

        # Add key metrics to measurement
        if measurement.total_load_time_ms > 0:
            measurement.metrics.append(PerformanceMetric(
                metric_type=PerformanceMetricType.PAGE_LOAD,
                value=measurement.total_load_time_ms,
                name="Page Load Time",
                description="Total time to load page completely",
                url=url
            ))

        if measurement.dom_content_loaded_ms > 0:
            measurement.metrics.append(PerformanceMetric(
                metric_type=PerformanceMetricType.DOM_CONTENT_LOADED,
                value=measurement.dom_content_loaded_ms,
                name="DOM Content Loaded",
                description="Time when DOM is ready and styles loaded",
                url=url
            ))

        # Store measurement
        self.measurements.append(measurement)

        self.logger.info(
            f"Performance measured for {url}: "
            f"Load: {measurement.total_load_time_ms:.2f}ms, "
            f"DCL: {measurement.dom_content_loaded_ms:.2f}ms, "
            f"Resources: {len(measurement.resources)}"
        )

        return measurement

    def _determine_resource_type(self, resource_url: str) -> str:
        """
        Determine resource type from URL

        Args:
            resource_url: URL of the resource

        Returns:
            Resource type string
        """
        url_lower = resource_url.lower()

        if '.js' in resource_url:
            return 'script'
        elif '.css' in resource_url:
            return 'stylesheet'
        elif any(ext in url_lower for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']):
            return 'image'
        elif any(ext in url_lower for ext in ['.woff', '.woff2', '.ttf', '.eot']):
            return 'font'
        elif '/api/' in resource_url or 'xhr' in url_lower:
            return 'xhr'
        elif 'fetch' in url_lower:
            return 'fetch'
        else:
            return 'other'

    @handle_errors(component="performance_adapter", reraise=False)
    def evaluate_performance(
        self,
        measurement: PageLoadMeasurement
    ) -> PerformanceReport:
        """
        Evaluate performance measurement against thresholds

        Args:
            measurement: Performance measurement to evaluate

        Returns:
            PerformanceReport with evaluation results
        """
        self.logger.info(f"Evaluating performance for: {measurement.url}")

        violations: List[ThresholdViolation] = []

        # Check each metric against thresholds
        for metric in measurement.metrics:
            for threshold in self.thresholds:
                if threshold.metric_type == metric.metric_type:
                    violated = False

                    if threshold.comparison == 'less_than':
                        violated = metric.value > threshold.threshold_ms
                    elif threshold.comparison == 'greater_than':
                        violated = metric.value < threshold.threshold_ms
                    elif threshold.comparison == 'equals':
                        violated = metric.value == threshold.threshold_ms

                    if violated:
                        violations.append(ThresholdViolation(
                            metric_type=metric.metric_type,
                            actual_value=metric.value,
                            threshold_value=threshold.threshold_ms,
                            severity=threshold.severity,
                            description=threshold.description
                        ))

        # Calculate performance score (0-100)
        score = self._calculate_performance_score(measurement, violations)

        # Determine grade
        grade = self._calculate_grade(score)

        # Generate recommendations
        recommendations = self._generate_recommendations(measurement, violations)

        report = PerformanceReport(
            url=measurement.url,
            timestamp=datetime.now(),
            measurement=measurement,
            violations=violations,
            score=score,
            grade=grade,
            recommendations=recommendations
        )

        self.logger.info(
            f"Performance evaluation complete: {measurement.url} - "
            f"Score: {score:.1f}/100, Grade: {grade}, "
            f"Violations: {len(violations)}"
        )

        return report

    def _calculate_performance_score(
        self,
        measurement: PageLoadMeasurement,
        violations: List[ThresholdViolation]
    ) -> float:
        """
        Calculate overall performance score (0-100)

        Scoring based on Web Vitals:
        - LCP: 25% weight
        - FID: 25% weight
        - CLS: 25% weight
        - FCP: 15% weight
        - TTI: 10% weight

        Args:
            measurement: Performance measurement
            violations: Threshold violations

        Returns:
            Score from 0-100
        """
        if not measurement.metrics:
            return 50.0  # Neutral score if no metrics

        scores = []

        for metric in measurement.metrics:
            metric_score = 100.0

            # Find applicable thresholds
            for threshold in self.thresholds:
                if threshold.metric_type == metric.metric_type:
                    if threshold.comparison == 'less_than':
                        if metric.value <= threshold.threshold_ms:
                            metric_score = 100.0
                        elif metric.value <= threshold.threshold_ms * 1.5:
                            # Partial score (50-100)
                            ratio = (metric.value - threshold.threshold_ms) / (threshold.threshold_ms * 0.5)
                            metric_score = 100.0 - (ratio * 50.0)
                        else:
                            # Poor score (<50)
                            metric_score = max(25.0, 100.0 - ((metric.value / threshold.threshold_ms) * 50.0))

            scores.append(metric_score)

        # Average score
        if scores:
            return sum(scores) / len(scores)

        return 50.0

    def _calculate_grade(self, score: float) -> str:
        """
        Calculate letter grade from score

        Args:
            score: Performance score (0-100)

        Returns:
            Letter grade: A, B, C, D, or F
        """
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'

    def _generate_recommendations(
        self,
        measurement: PageLoadMeasurement,
        violations: List[ThresholdViolation]
    ) -> List[str]:
        """
        Generate performance improvement recommendations

        Args:
            measurement: Performance measurement
            violations: Threshold violations

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Analyze resource loading
        if measurement.resources:
            # Find large resources
            large_resources = [
                r for r in measurement.resources
                if r.transfer_size > 500000  # > 500KB
            ]

            if large_resources:
                recommendations.append(
                    f"Optimize {len(large_resources)} large resources (>500KB). "
                    "Consider compression, lazy loading, or format optimization."
                )

            # Find slow resources
            slow_resources = [
                r for r in measurement.resources
                if r.duration > 1000  # > 1 second
            ]

            if slow_resources:
                recommendations.append(
                    f"{len(slow_resources)} resources took over 1 second to load. "
                    "Consider CDN, preloading, or reducing dependencies."
                )

        # Check specific metrics
        if measurement.total_load_time_ms > 3000:
            recommendations.append(
                f"Page load time ({measurement.total_load_time_ms:.0f}ms) exceeds 3s. "
                "Optimize critical rendering path and reduce blocking resources."
            )

        if measurement.dom_content_loaded_ms > 2000:
            recommendations.append(
                f"DOM Content Loaded ({measurement.dom_content_loaded_ms:.0f}ms) exceeds 2s. "
                "Defer non-critical CSS and JavaScript."
            )

        # Check LCP
        lcp_metric = next(
            (m for m in measurement.metrics if m.metric_type == PerformanceMetricType.LARGEST_CONTENTFUL_PAINT),
            None
        )
        if lcp_metric and lcp_metric.value > 2500:
            recommendations.append(
                f"Largest Contentful Paint ({lcp_metric.value:.0f}ms) exceeds 2.5s. "
                "Optimize images and reduce JavaScript execution time."
            )

        # Check FID
        fid_metric = next(
            (m for m in measurement.metrics if m.metric_type == PerformanceMetricType.FIRST_INPUT_DELAY),
            None
        )
        if fid_metric and fid_metric.value > 100:
            recommendations.append(
                f"First Input Delay ({fid_metric.value:.0f}ms) exceeds 100ms. "
                "Break up long JavaScript tasks and reduce main thread work."
            )

        if not recommendations:
            recommendations.append("No major performance issues detected. Great job!")

        return recommendations

    def get_measurements(self, url: Optional[str] = None) -> List[PageLoadMeasurement]:
        """
        Get stored measurements, optionally filtered by URL

        Args:
            url: Optional URL to filter by

        Returns:
            List of measurements
        """
        if url:
            return [m for m in self.measurements if m.url == url]
        return self.measurements.copy()

    def get_slowest_pages(self, limit: int = 10) -> List[PageLoadMeasurement]:
        """
        Get slowest loading pages

        Args:
            limit: Maximum number of results

        Returns:
            List of measurements sorted by load time (slowest first)
        """
        sorted_measurements = sorted(
            self.measurements,
            key=lambda m: m.total_load_time_ms,
            reverse=True
        )
        return sorted_measurements[:limit]

    def generate_performance_summary(self) -> Dict[str, Any]:
        """
        Generate summary of all performance measurements

        Returns:
            Summary statistics
        """
        if not self.measurements:
            return {
                'total_measurements': 0,
                'avg_load_time_ms': 0,
                'slowest_page': None,
                'fastest_page': None
            }

        load_times = [m.total_load_time_ms for m in self.measurements if m.total_load_time_ms > 0]

        return {
            'total_measurements': len(self.measurements),
            'avg_load_time_ms': sum(load_times) / len(load_times) if load_times else 0,
            'min_load_time_ms': min(load_times) if load_times else 0,
            'max_load_time_ms': max(load_times) if load_times else 0,
            'slowest_page': self.measurements[0].url if self.measurements else None,
            'fastest_page': self.measurements[-1].url if self.measurements else None,
            'total_resources_tracked': sum(len(m.resources) for m in self.measurements)
        }

    def export_measurements(
        self,
        output_path: str,
        format: str = 'json'
    ) -> None:
        """
        Export measurements to file

        Args:
            output_path: Path to output file
            format: Export format ('json' or 'csv')
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if format == 'json':
            data = {
                'timestamp': datetime.now().isoformat(),
                'summary': self.generate_performance_summary(),
                'measurements': [m.to_dict() for m in self.measurements]
            }

            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)

        elif format == 'csv':
            # Simple CSV export
            import csv
            with open(output_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'URL', 'Timestamp', 'Load Time (ms)', 'DCL (ms)',
                    'FCP (ms)', 'Resources Count'
                ])

                for m in self.measurements:
                    writer.writerow([
                        m.url,
                        m.timestamp.isoformat(),
                        round(m.total_load_time_ms, 2),
                        round(m.dom_content_loaded_ms, 2),
                        round(m.first_contentful_paint_ms, 2) if m.first_contentful_paint_ms else '',
                        len(m.resources)
                    ])

        self.logger.info(f"Exported {len(self.measurements)} measurements to {output_path}")
