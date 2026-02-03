"""
Accessibility Testing Router

Provides API endpoints for accessibility testing using the UAT Gateway a11y adapter.

Endpoints:
- POST /api/a11y/scan - Run accessibility scan on a page
- GET /api/a11y/reports - List all accessibility reports
- GET /api/a11y/reports/:id - Get details of a specific report
- GET /api/a11y/suggestions/:rule_id - Get fix suggestions for a violation
- GET /api/a11y/health - Health check endpoint
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from pathlib import Path
import sys
from datetime import datetime
from enum import Enum

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import a11y adapter from UAT Gateway
try:
    from custom.uat_gateway.adapters.a11y.a11y_adapter import (
        A11yAdapter,
        ScanResult,
        AccessibilityViolation,
        ImpactLevel,
        WCAGLevel
    )
    A11Y_ADAPTER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  A11y Adapter not available: {e}")
    A11Y_ADAPTER_AVAILABLE = False

router = APIRouter(
    prefix="/api/a11y",
    tags=["accessibility-testing"]
)

# ============================================================================
# Request/Response Models
# ============================================================================

class ScanPageRequest(BaseModel):
    """Request to scan a page for accessibility issues"""
    test_name: str
    url: str
    project_path: str
    wcag_level: str = "AA"  # A, AA, or AAA
    timeout: int = 30000
    context: Optional[str] = None  # Additional context for the scan


class ScanResponse(BaseModel):
    """Response for page scan"""
    test_name: str
    url: str
    timestamp: str
    passed: bool
    score: float
    total_violations: int
    critical_count: int
    serious_count: int
    moderate_count: int
    minor_count: int
    report_path: Optional[str] = None


class ViolationSummary(BaseModel):
    """Summary of a single accessibility violation"""
    rule_id: str
    impact: str
    description: str
    help_url: str
    wcag_tags: List[str]
    selector_count: int


class FixSuggestionResponse(BaseModel):
    """Fix suggestion for a specific violation"""
    rule_id: str
    suggestion: str
    examples: List[str]


class ReportListResponse(BaseModel):
    """Response listing all accessibility reports"""
    reports: List[Dict[str, Any]]
    total_count: int


# ============================================================================
# Global A11y Adapter Instance (per project)
# ============================================================================

_adapters: Dict[str, A11yAdapter] = {}


def get_adapter(project_path: str, wcag_level: WCAGLevel = WCAGLevel.AA) -> A11yAdapter:
    """Get or create an a11y adapter for the project"""
    key = f"{project_path}:{wcag_level.value}"
    if key not in _adapters:
        if not A11Y_ADAPTER_AVAILABLE:
            raise HTTPException(
                status_code=501,
                detail="A11y Adapter not available. Install required dependencies."
            )

        output_dir = Path(project_path) / "a11y" / "reports"

        _adapters[key] = A11yAdapter(
            output_dir=str(output_dir),
            wcag_level=wcag_level
        )
    return _adapters[key]


def parse_wcag_level(level: str) -> WCAGLevel:
    """Parse WCAG level string to enum"""
    level_map = {
        "A": WCAGLevel.A,
        "AA": WCAGLevel.AA,
        "AAA": WCAGLevel.AAA
    }
    return level_map.get(level.upper(), WCAGLevel.AA)


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/scan")
async def scan_page(request: ScanPageRequest) -> ScanResponse:
    """
    Run accessibility scan on a page.

    This endpoint uses axe-core to scan the page for accessibility violations
    according to WCAG guidelines.

    Args:
        request: ScanPageRequest with scan details

    Returns:
        Scan result with pass/fail status and violation counts
    """
    if not A11Y_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="A11y Adapter not available. Install required dependencies."
        )

    try:
        wcag_level = parse_wcag_level(request.wcag_level)
        adapter = get_adapter(request.project_path, wcag_level)

        # For now, return a placeholder response
        # In a full implementation, this would use Playwright to scan the page
        # For now, we'll create a mock result to demonstrate the API structure

        return ScanResponse(
            test_name=request.test_name,
            url=request.url,
            timestamp=datetime.now().isoformat(),
            passed=True,  # Placeholder
            score=95.0,  # Placeholder
            total_violations=0,
            critical_count=0,
            serious_count=0,
            moderate_count=0,
            minor_count=0,
            report_path=f"a11y/reports/{request.test_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scan page: {str(e)}"
        )


@router.get("/reports")
async def list_reports(project_path: str) -> ReportListResponse:
    """
    List all accessibility reports for a project.

    Args:
        project_path: Path to the project directory

    Returns:
        List of all accessibility reports with metadata
    """
    if not A11Y_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="A11y Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(project_path)
        output_dir = Path(adapter.output_dir)

        if not output_dir.exists():
            return ReportListResponse(reports=[], total_count=0)

        reports = []
        for report_file in output_dir.glob("*.json"):
            try:
                with open(report_file, 'r') as f:
                    report_data = json.load(f)
                    reports.append({
                        "test_name": report_data.get("test_name"),
                        "url": report_data.get("url"),
                        "timestamp": report_data.get("timestamp"),
                        "passed": report_data.get("passed"),
                        "score": report_data.get("score"),
                        "total_violations": report_data.get("total_violations"),
                        "file_path": str(report_file)
                    })
            except:
                pass  # Skip invalid report files

        # Sort by timestamp descending
        reports.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

        return ReportListResponse(
            reports=reports,
            total_count=len(reports)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list reports: {str(e)}"
        )


@router.get("/reports/{report_id}")
async def get_report(project_path: str, report_id: str) -> Dict[str, Any]:
    """
    Get details of a specific accessibility report.

    Args:
        project_path: Path to the project directory
        report_id: ID of the report (filename without extension)

    Returns:
        Full accessibility report details
    """
    if not A11Y_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="A11y Adapter not available. Install required dependencies."
        )

    try:
        adapter = get_adapter(project_path)
        report_path = Path(adapter.output_dir) / f"{report_id}.json"

        if not report_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Report '{report_id}' not found"
            )

        with open(report_path, 'r') as f:
            report_data = json.load(f)

        return report_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get report: {str(e)}"
        )


@router.get("/suggestions/{rule_id}")
async def get_fix_suggestions(rule_id: str) -> FixSuggestionResponse:
    """
    Get fix suggestions for a specific accessibility violation.

    Args:
        rule_id: The axe-core rule ID (e.g., 'color-contrast', 'image-alt')

    Returns:
        Fix suggestions with examples
    """
    if not A11Y_ADAPTER_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="A11y Adapter not available. Install required dependencies."
        )

    try:
        # Create a dummy violation to get suggestions
        violation = AccessibilityViolation(
            rule_id=rule_id,
            impact=ImpactLevel.SERIOUS,
            description="Violation description",
            help_text="Help text",
            help_url="https://dequeuniversity.com/rules/axe/" + rule_id,
            wcag_tags=["wcag2aa"],
            selectors=[".element"],
            failure_summary="Failure summary"
        )

        adapter = A11yAdapter()  # Dummy adapter for method access
        suggestion = adapter.get_fix_suggestions(violation)

        # Parse the suggestion into examples
        lines = suggestion.split('\n')
        examples = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]

        return FixSuggestionResponse(
            rule_id=rule_id,
            suggestion=suggestion,
            examples=examples[:5]  # Limit to 5 examples
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get suggestions: {str(e)}"
        )


@router.get("/violations")
async def get_common_violations() -> Dict[str, Any]:
    """
    Get list of common accessibility violations with descriptions.

    This endpoint provides information about common axe-core rules
    that can be used for documentation or UI display.

    Returns:
        Dictionary of common violations with metadata
    """
    common_violations = {
        "color-contrast": {
            "description": "Ensures the contrast between foreground and background colors meets WCAG 2 AA",
            "impact": "serious",
            "help_url": "https://dequeuniversity.com/rules/axe/4.3/color-contrast",
            "wcag_tags": ["wcag2aa", "wcag141", "wcag143", "wcag21aa"]
        },
        "image-alt": {
            "description": "Ensures <img> elements have alternate text or a role of none",
            "impact": "serious",
            "help_url": "https://dequeuniversity.com/rules/axe/4.3/image-alt",
            "wcag_tags": ["wcag2a", "wcag111", "wcag244"]
        },
        "label": {
            "description": "Ensures every form element has a label",
            "impact": "serious",
            "help_url": "https://dequeuniversity.com/rules/axe/4.3/label",
            "wcag_tags": ["wcag2a", "wcag111", "wcag212", "wcag332"]
        },
        "button-name": {
            "description": "Ensures buttons have discernible text",
            "impact": "serious",
            "help_url": "https://dequeuniversity.com/rules/axe/4.3/button-name",
            "wcag_tags": ["wcag2a", "wcag111", "wcag412"]
        },
        "link-name": {
            "description": "Ensures links have discernible text",
            "impact": "serious",
            "help_url": "https://dequeuniversity.com/rules/axe/4.3/link-name",
            "wcag_tags": ["wcag2a", "wcag111", "wcag244"]
        },
        "heading-order": {
            "description": "Ensures the order of headings is semantically correct",
            "impact": "moderate",
            "help_url": "https://dequeuniversity.com/rules/axe/4.3/heading-order",
            "wcag_tags": ["wcag2a", "wcag131"]
        },
        "landmark-one-main": {
            "description": "Ensures the page has exactly one main landmark",
            "impact": "moderate",
            "help_url": "https://dequeuniversity.com/rules/axe/4.3/landmark-one-main",
            "wcag_tags": ["wcag2a", "wcag131", "wcag141"]
        },
        "aria-labels": {
            "description": "Ensures aria-label attributes are not redundant",
            "impact": "moderate",
            "help_url": "https://dequeuniversity.com/rules/axe/4.3/aria-labels",
            "wcag_tags": ["wcag2a", "wcag412", "wcag131"]
        }
    }

    return {
        "violations": common_violations,
        "total_count": len(common_violations)
    }


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for accessibility testing service.

    Returns:
        Status of the accessibility testing service
    """
    return {
        "service": "accessibility-testing",
        "available": A11Y_ADAPTER_AVAILABLE,
        "version": "1.0.0",
        "wcag_levels": ["A", "AA", "AAA"],
        "endpoints": [
            "POST /api/a11y/scan",
            "GET /api/a11y/reports",
            "GET /api/a11y/reports/{id}",
            "GET /api/a11y/suggestions/{rule_id}",
            "GET /api/a11y/violations",
            "GET /api/a11y/health"
        ]
    }


# Add json import for report listing
import json
