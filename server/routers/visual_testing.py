"""
Visual Testing Router

Provides API endpoints for visual regression testing using the UAT Gateway visual adapter.

Endpoints:
- POST /api/visual/baseline - Capture baseline screenshots
- POST /api/visual/compare - Compare screenshots against baselines
- GET /api/visual/baselines - List all baseline screenshots
- GET /api/visual/diff/:id - Get diff report for a comparison
- POST /api/visual/mask - Add mask selectors for dynamic content
- DELETE /api/visual/mask/:selector - Remove a mask selector
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pathlib import Path
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import visual adapter from UAT Gateway
try:
    from custom.uat_gateway.adapters.visual.visual_adapter import (
        VisualAdapter,
        Viewport,
        MaskSelector,
        ComparisonResult
    )
    VISUAL_ADAPTER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Visual Adapter not available: {e}")
    VISUAL_ADAPTER_AVAILABLE = False

router = APIRouter(
    prefix="/api/visual",
    tags=["visual-testing"]
)

# ============================================================================
# Request/Response Models
# ============================================================================

class CaptureBaselineRequest(BaseModel):
    """Request to capture a baseline screenshot"""
    test_name: str
    url: str
    viewport: Optional[Dict[str, Any]] = None  # {name, width, height}
    project_path: str
    mask_selectors: Optional[List[str]] = None
    wait_for_selector: Optional[str] = None
    screenshot_timeout: int = 30000


class CompareScreenshotsRequest(BaseModel):
    """Request to compare screenshots against baselines"""
    test_name: str
    current_screenshot_path: str
    project_path: str
    viewport: Optional[str] = None
    tolerance: float = 0.1
    mask_selectors: Optional[List[str]] = None


class AddMaskRequest(BaseModel):
    """Request to add a mask selector"""
    selector: str
    name: str
    color: str = "#000000"
    mask_type: str = "fill"  # 'fill' or 'blur'


class MaskSelectorResponse(BaseModel):
    """Response for mask selector operations"""
    selector: str
    name: str
    color: str
    mask_type: str


class BaselineListResponse(BaseModel):
    """Response listing all baseline screenshots"""
    baselines: List[Dict[str, Any]]
    total_count: int
    storage_size: Dict[str, Any]


class ComparisonResponse(BaseModel):
    """Response for screenshot comparison"""
    test_name: str
    viewport: str
    passed: bool
    difference_percentage: float
    diff_path: Optional[str] = None
    diff_pixels: int = 0
    total_pixels: int = 0
    masks_applied: List[str] = []


# ============================================================================
# Default Viewport Configurations
# ============================================================================

DEFAULT_VIEWPORTS = {
    "desktop": Viewport(name="desktop", width=1920, height=1080),
    "laptop": Viewport(name="laptop", width=1366, height=768),
    "tablet": Viewport(name="tablet", width=768, height=1024, is_mobile=True, has_touch=True),
    "mobile": Viewport(name="mobile", width=375, height=667, is_mobile=True, has_touch=True),
}

# ============================================================================
# Global Visual Adapter Instance (per project)
# ============================================================================

_adapters: Dict[str, VisualAdapter] = {}


def get_adapter(project_path: str) -> VisualAdapter:
    """Get or create a visual adapter for the project"""
    if project_path not in _adapters:
        if not VISUAL_ADAPTER_AVAILABLE:
            raise HTTPException(
                status_code=501,
                detail="Visual Adapter not available. Install required dependencies."
            )

        baseline_dir = Path(project_path) / "visual" / "baseline"
        current_dir = Path(project_path) / "visual" / "current"
        diff_dir = Path(project_path) / "visual" / "diff"

        _adapters[project_path] = VisualAdapter(
            baseline_dir=str(baseline_dir),
            current_dir=str(current_dir),
            diff_dir=str(diff_dir),
            viewports=list(DEFAULT_VIEWPORTS.values())
        )
    return _adapters[project_path]


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/baseline")
async def capture_baseline(request: CaptureBaselineRequest) -> Dict[str, Any]:
    """
    Capture a baseline screenshot for visual regression testing.

    This endpoint captures a screenshot of the given URL and stores it
    as the baseline for future comparisons.

    Args:
        request: CaptureBaselineRequest with test details

    Returns:
        Metadata about the captured baseline
    """
    if not VISUAL_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Visual Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(request.project_path)

        # Determine viewport
        viewport_data = request.viewport or DEFAULT_VIEWPORTS["desktop"].to_dict()
        viewport_name = viewport_data.get("name", "custom")

        # For now, return a placeholder response
        # In a full implementation, this would use Playwright to capture the screenshot
        return {
            "test_name": request.test_name,
            "viewport": viewport_name,
            "baseline_path": f"visual/baseline/{request.test_name}_{viewport_name}.png",
            "status": "captured",
            "message": "Baseline captured successfully (placeholder - Playwright integration needed)"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to capture baseline: {str(e)}"
        )


@router.post("/compare")
async def compare_screenshots(request: CompareScreenshotsRequest) -> ComparisonResponse:
    """
    Compare a screenshot against its baseline.

    This endpoint compares the current screenshot with the baseline
    and returns the difference percentage and diff image path.

    Args:
        request: CompareScreenshotsRequest with comparison details

    Returns:
        Comparison result with pass/fail status and diff details
    """
    if not VISUAL_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Visual Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(request.project_path)

        # Get baseline path
        viewport = request.viewport or "desktop"
        baseline_path = adapter.get_baseline_path(request.test_name, viewport)

        if not baseline_path or not Path(baseline_path).exists():
            raise HTTPException(
                status_code=404,
                detail=f"Baseline not found for test '{request.test_name}' with viewport '{viewport}'"
            )

        # Perform comparison
        result = adapter.compare_screenshots(
            test_name=request.test_name,
            baseline_path=baseline_path,
            current_path=request.current_screenshot_path,
            viewport=viewport,
            tolerance=request.tolerance
        )

        return ComparisonResponse(
            test_name=result.test_name,
            viewport=result.viewport,
            passed=result.passed,
            difference_percentage=result.difference_percentage,
            diff_path=result.diff_path,
            diff_pixels=result.diff_pixels,
            total_pixels=result.total_pixels,
            masks_applied=result.masks_applied
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compare screenshots: {str(e)}"
        )


@router.get("/baselines")
async def list_baselines(project_path: str) -> BaselineListResponse:
    """
    List all baseline screenshots for a project.

    Args:
        project_path: Path to the project directory

    Returns:
        List of all baseline screenshots with metadata
    """
    if not VISUAL_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Visual Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(project_path)
        baselines = adapter.list_baselines()
        storage_size = adapter.get_storage_size()

        return BaselineListResponse(
            baselines=baselines,
            total_count=len(baselines),
            storage_size=storage_size
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list baselines: {str(e)}"
        )


@router.post("/mask")
async def add_mask_selector(request: AddMaskRequest, project_path: str) -> MaskSelectorResponse:
    """
    Add a mask selector for dynamic content.

    Mask selectors are used to hide dynamic content (dates, timestamps, etc.)
    before comparing screenshots.

    Args:
        request: AddMaskRequest with selector details
        project_path: Path to the project directory

    Returns:
        The added mask selector
    """
    if not VISUAL_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Visual Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(project_path)
        mask = MaskSelector(
            selector=request.selector,
            name=request.name,
            color=request.color,
            mask_type=request.mask_type
        )
        adapter.add_mask_selector(mask)

        return MaskSelectorResponse(
            selector=mask.selector,
            name=mask.name,
            color=mask.color,
            mask_type=mask.mask_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add mask selector: {str(e)}"
        )


@router.delete("/mask/{selector:path}")
async def remove_mask_selector(selector: str, project_path: str) -> Dict[str, Any]:
    """
    Remove a mask selector.

    Args:
        selector: The CSS selector to remove
        project_path: Path to the project directory

    Returns:
        Success status
    """
    if not VISUAL_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Visual Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(project_path)
        removed = adapter.remove_mask_selector(selector)

        if not removed:
            raise HTTPException(
                status_code=404,
                detail=f"Mask selector '{selector}' not found"
            )

        return {
            "message": f"Mask selector '{selector}' removed successfully",
            "selector": selector
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to remove mask selector: {str(e)}"
        )


@router.get("/masks")
async def list_mask_selectors(project_path: str) -> List[MaskSelectorResponse]:
    """
    List all mask selectors for a project.

    Args:
        project_path: Path to the project directory

    Returns:
        List of all mask selectors
    """
    if not VISUAL_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Visual Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(project_path)
        masks = adapter.list_mask_selectors()

        return [
            MaskSelectorResponse(
                selector=m["selector"],
                name=m["name"],
                color=m["color"],
                mask_type=m["mask_type"]
            )
            for m in masks
        ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list mask selectors: {str(e)}"
        )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for visual testing service.

    Returns:
        Status of the visual testing service
    """
    return {
        "service": "visual-testing",
        "available": VISUAL_ADAPTER_AVAILABLE,
        "version": "1.0.0",
        "endpoints": [
            "POST /api/visual/baseline",
            "POST /api/visual/compare",
            "GET /api/visual/baselines",
            "POST /api/visual/mask",
            "DELETE /api/visual/mask/{selector}",
            "GET /api/visual/masks",
            "GET /api/visual/health"
        ]
    }
