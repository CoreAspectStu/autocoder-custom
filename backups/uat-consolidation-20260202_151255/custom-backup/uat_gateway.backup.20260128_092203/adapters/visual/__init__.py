"""
Visual Adapter Package

Exports visual regression testing components
"""

from custom.uat_gateway.adapters.visual.visual_adapter import (
    VisualAdapter,
    ScreenshotMetadata,
    Viewport,
    ComparisonResult
)

__all__ = [
    "VisualAdapter",
    "ScreenshotMetadata",
    "Viewport",
    "ComparisonResult"
]
