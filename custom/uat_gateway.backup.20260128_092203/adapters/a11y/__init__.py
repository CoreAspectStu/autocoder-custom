"""
A11y Adapter Package

Exports accessibility testing components
"""

from custom.uat_gateway.adapters.a11y.a11y_adapter import (
    A11yAdapter,
    AccessibilityViolation,
    ScanResult,
    ImpactLevel,
    WCAGLevel
)

__all__ = [
    "A11yAdapter",
    "AccessibilityViolation",
    "ScanResult",
    "ImpactLevel",
    "WCAGLevel"
]
