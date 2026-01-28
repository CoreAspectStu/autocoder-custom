"""
Performance Adapter - Package initialization

Exports the main PerformanceAdapter class and related data models.
"""

from .performance_adapter import (
    PerformanceAdapter,
    PerformanceMetricType,
    ResourceTiming,
    NavigationTiming,
    PerformanceMetric,
    PageLoadMeasurement,
    PerformanceThreshold,
    ThresholdViolation,
    PerformanceReport
)

__all__ = [
    'PerformanceAdapter',
    'PerformanceMetricType',
    'ResourceTiming',
    'NavigationTiming',
    'PerformanceMetric',
    'PageLoadMeasurement',
    'PerformanceThreshold',
    'ThresholdViolation',
    'PerformanceReport'
]
