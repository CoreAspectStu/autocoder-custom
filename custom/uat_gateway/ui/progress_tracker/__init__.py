"""
Progress Tracker UI Components

This package provides dashboard components for tracking UAT progress:
- FailuresSummary: Summary of test failures with grouping and highlighting
- ProgressCard: Per-journey progress cards
- DashboardStats: Overall statistics
"""

from .failures_summary import (
    FailuresSummary,
    FailureInfo,
    FailureGroup,
    FailureCategory,
    FailureSeverity
)

__all__ = [
    "FailuresSummary",
    "FailureInfo",
    "FailureGroup",
    "FailureCategory",
    "FailureSeverity"
]
