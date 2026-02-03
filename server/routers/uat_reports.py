"""
UAT Reports Router

Provides functionality for generating and exporting UAT test reports.
Supports multiple formats: HTML, PDF, JSON, CSV, and Markdown.
"""

import io
import csv
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path
from enum import Enum
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/uat", tags=["uat-reports"])


# ============================================================================
# Types
# ============================================================================

from enum import Enum


class ReportFormat(str, Enum):
    HTML = "html"
    PDF = "pdf"
    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ReportRequest(BaseModel):
    """Request model for generating a report."""
    cycle_id: str
    format: ReportFormat
    include_details: bool = True
    include_failures: bool = True
    include_screenshots: bool = False
    title: Optional[str] = None


class TestResultSummary(BaseModel):
    """Summary of a test result."""
    test_id: str
    test_name: str
    status: str
    duration_seconds: float
    score: Optional[float] = None
    error: Optional[str] = None


class JourneyReport(BaseModel):
    """Report data for a journey."""
    journey_id: str
    journey_name: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate: float
    duration_seconds: float
    test_results: List[TestResultSummary]


class UATReportData(BaseModel):
    """Complete UAT report data."""
    cycle_id: str
    cycle_name: str
    started_at: str
    completed_at: str
    total_duration_seconds: float
    total_journeys: int
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate: float
    journeys: List[JourneyReport]


# ============================================================================
# Report Generators
# ============================================================================

def generate_html_report(data: UATReportData) -> str:
    """Generate an HTML report."""
    title = data.cycle_name or f"UAT Test Report - {data.cycle_id}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; }}
        .header h1 {{ margin: 0; font-size: 28px; }}
        .header .meta {{ margin-top: 10px; opacity: 0.9; font-size: 14px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; padding: 30px; background: #f8f9fa; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 8px; border-left: 4px solid #667eea; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
        .stat-card.passed {{ border-left-color: #10b981; }}
        .stat-card.failed {{ border-left-color: #ef4444; }}
        .stat-card .value {{ font-size: 32px; font-weight: bold; color: #1f2937; }}
        .stat-card .label {{ font-size: 14px; color: #6b7280; margin-top: 5px; }}
        .journeys {{ padding: 30px; }}
        .journey-card {{ border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 20px; overflow: hidden; }}
        .journey-header {{ background: #f9fafb; padding: 15px 20px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center; }}
        .journey-header h3 {{ margin: 0; font-size: 18px; }}
        .journey-stats {{ display: flex; gap: 20px; font-size: 14px; }}
        .journey-stats span {{ color: #6b7280; }}
        .journey-stats strong {{ color: #1f2937; }}
        .test-list {{ padding: 0; list-style: none; }}
        .test-item {{ padding: 12px 20px; border-bottom: 1px solid #f3f4f6; display: flex; justify-content: space-between; align-items: center; }}
        .test-item:last-child {{ border-bottom: none; }}
        .test-item.passed {{ border-left: 3px solid #10b981; }}
        .test-item.failed {{ border-left: 3px solid #ef4444; background: #fef2f2; }}
        .status-badge {{ padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
        .status-badge.passed {{ background: #d1fae5; color: #065f46; }}
        .status-badge.failed {{ background: #fee2e2; color: #991b1b; }}
        .footer {{ padding: 20px 30px; text-align: center; color: #6b7280; font-size: 14px; border-top: 1px solid #e5e7eb; }}
        .progress-bar {{ width: 100%; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; margin-top: 10px; }}
        .progress-fill {{ height: 100%; background: linear-gradient(90deg, #10b981, #34d399); transition: width 0.3s; }}
        @media print {{ body {{ background: white; }} .container {{ box-shadow: none; }} }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="meta">
                Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')} |
                Duration: {data.total_duration_seconds:.1f}s |
                Tests: {data.passed_tests}/{data.total_tests} passed
            </div>
        </div>

        <div class="summary">
            <div class="stat-card">
                <div class="value">{data.total_tests}</div>
                <div class="label">Total Tests</div>
            </div>
            <div class="stat-card passed">
                <div class="value">{data.passed_tests}</div>
                <div class="label">Passed</div>
            </div>
            <div class="stat-card failed">
                <div class="value">{data.failed_tests}</div>
                <div class="label">Failed</div>
            </div>
            <div class="stat-card">
                <div class="value">{data.pass_rate:.1f}%</div>
                <div class="label">Pass Rate</div>
            </div>
            <div class="stat-card">
                <div class="value">{data.total_journeys}</div>
                <div class="label">Journeys</div>
            </div>
        </div>

        <div class="journeys">"""

    for journey in data.journeys:
        status_class = "passed" if journey.pass_rate == 100 else "failed" if journey.pass_rate < 70 else ""
        html += f"""
            <div class="journey-card">
                <div class="journey-header">
                    <h3>{journey.journey_name}</h3>
                    <div class="journey-stats">
                        <span><strong>{journey.passed_tests}</strong> passed</span>
                        <span><strong>{journey.failed_tests}</strong> failed</span>
                        <span><strong>{journey.pass_rate:.1f}%</strong> pass rate</span>
                    </div>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {journey.pass_rate}%"></div>
                </div>
                <ul class="test-list">"""

        for test in journey.test_results:
            status_class = "passed" if test.status == "passed" else "failed"
            html += f"""
                    <li class="test-item {status_class}">
                        <div>
                            <strong>{test.test_name}</strong>
                            {f'<div style="color: #dc2626; font-size: 13px; margin-top: 4px;">{test.error}</div>' if test.error else ''}
                        </div>
                        <div style="text-align: right;">
                            <span class="status-badge {status_class}">{test.status.upper()}</span>
                            <div style="font-size: 12px; color: #6b7280; margin-top: 4px;">{test.duration_seconds:.2f}s</div>
                        </div>
                    </li>"""

        html += """
                </ul>
            </div>"""

    html += f"""
        </div>

        <div class="footer">
            <p>UAT Test Report generated by AutoCoder UAT Gateway</p>
            <p style="margin-top: 5px; font-size: 12px;">{data.cycle_id} | {data.started_at} to {data.completed_at}</p>
        </div>
    </div>
</body>
</html>"""

    return html


def generate_markdown_report(data: UATReportData) -> str:
    """Generate a Markdown report."""
    title = data.cycle_name or f"UAT Test Report - {data.cycle_id}"

    md = f"""# {title}

**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
**Cycle ID:** {data.cycle_id}
**Duration:** {data.total_duration_seconds:.1f} seconds
**Period:** {data.started_at} to {data.completed_at}

---

## Summary

| Metric | Value |
|--------|-------|
| Total Journeys | {data.total_journeys} |
| Total Tests | {data.total_tests} |
| Passed | ✅ {data.passed_tests} |
| Failed | ❌ {data.failed_tests} |
| Pass Rate | {data.pass_rate:.1f}% |

---

"""

    for journey in data.journeys:
        md += f"""## {journey.journey_name}

- **Journey ID:** {journey.journey_id}
- **Tests:** {journey.passed_tests}/{journey.total_tests} passed
- **Pass Rate:** {journey.pass_rate:.1f}%
- **Duration:** {journey.duration_seconds:.1f}s

### Test Results

| Test | Status | Duration | Score |
|------|--------|----------|-------|
"""
        for test in journey.test_results:
            status_emoji = "✅" if test.status == "passed" else "❌"
            score_str = f"{test.score:.1f}%" if test.score else "N/A"
            error_str = f" - {test.error}" if test.error else ""
            md += f"| {test.test_name} | {status_emoji} {test.status}{error_str} | {test.duration_seconds:.2f}s | {score_str} |\n"

        md += "\n"

    md += f"""
---

*Report generated by AutoCoder UAT Gateway*
*Cycle: {data.cycle_id}*
"""

    return md


def generate_csv_report(data: UATReportData) -> str:
    """Generate a CSV report."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header rows with summary
    writer.writerow(["UAT Test Report", data.cycle_name or data.cycle_id])
    writer.writerow(["Generated", datetime.now().isoformat()])
    writer.writerow(["Cycle ID", data.cycle_id])
    writer.writerow(["Total Journeys", data.total_journeys])
    writer.writerow(["Total Tests", data.total_tests])
    writer.writerow(["Passed Tests", data.passed_tests])
    writer.writerow(["Failed Tests", data.failed_tests])
    writer.writerow(["Pass Rate", f"{data.pass_rate:.1f}%"])
    writer.writerow(["Duration (s)", f"{data.total_duration_seconds:.1f}"])
    writer.writerow([])  # Empty row

    # Test results header
    writer.writerow(["Journey", "Journey ID", "Test", "Test ID", "Status", "Duration (s)", "Score", "Error"])

    # Test results
    for journey in data.journeys:
        for test in journey.test_results:
            writer.writerow([
                journey.journey_name,
                journey.journey_id,
                test.test_name,
                test.test_id,
                test.status,
                f"{test.duration_seconds:.2f}",
                f"{test.score:.1f}" if test.score else "",
                test.error or ""
            ])

    return output.getvalue()


def generate_json_report(data: UATReportData) -> str:
    """Generate a JSON report."""
    report = {
        "report_type": "UAT Test Report",
        "cycle_id": data.cycle_id,
        "cycle_name": data.cycle_name,
        "generated_at": datetime.now().isoformat(),
        "started_at": data.started_at,
        "completed_at": data.completed_at,
        "duration_seconds": data.total_duration_seconds,
        "summary": {
            "total_journeys": data.total_journeys,
            "total_tests": data.total_tests,
            "passed_tests": data.passed_tests,
            "failed_tests": data.failed_tests,
            "pass_rate": data.pass_rate
        },
        "journeys": [
            {
                "journey_id": j.journey_id,
                "journey_name": j.journey_name,
                "total_tests": j.total_tests,
                "passed_tests": j.passed_tests,
                "failed_tests": j.failed_tests,
                "pass_rate": j.pass_rate,
                "duration_seconds": j.duration_seconds,
                "test_results": [
                    {
                        "test_id": t.test_id,
                        "test_name": t.test_name,
                        "status": t.status,
                        "duration_seconds": t.duration_seconds,
                        "score": t.score,
                        "error": t.error
                    }
                    for t in j.test_results
                ]
            }
            for j in data.journeys
        ]
    }
    return json.dumps(report, indent=2)


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/reports/generate", response_class=Response)
async def generate_report(request: ReportRequest) -> Response:
    """
    Generate and download a UAT test report.

    Supported formats: html, pdf, json, csv, markdown
    """
    # In a real implementation, this would fetch data from the database
    # For now, return a sample report structure
    sample_data = UATReportData(
        cycle_id=request.cycle_id,
        cycle_name=f"UAT Test Cycle {request.cycle_id}",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        total_duration_seconds=300.0,
        total_journeys=3,
        total_tests=45,
        passed_tests=42,
        failed_tests=3,
        pass_rate=93.3,
        journeys=[
            JourneyReport(
                journey_id="journey-1",
                journey_name="User Authentication Flow",
                total_tests=15,
                passed_tests=15,
                failed_tests=0,
                pass_rate=100.0,
                duration_seconds=120.0,
                test_results=[
                    TestResultSummary(
                        test_id="test-1",
                        test_name="Login with valid credentials",
                        status="passed",
                        duration_seconds=2.5,
                        score=95.0
                    ),
                    TestResultSummary(
                        test_id="test-2",
                        test_name="Login with invalid credentials",
                        status="passed",
                        duration_seconds=1.8,
                        score=100.0
                    )
                ]
            ),
            JourneyReport(
                journey_id="journey-2",
                journey_name="Shopping Cart Flow",
                total_tests=20,
                passed_tests=18,
                failed_tests=2,
                pass_rate=90.0,
                duration_seconds=150.0,
                test_results=[
                    TestResultSummary(
                        test_id="test-3",
                        test_name="Add item to cart",
                        status="failed",
                        duration_seconds=3.2,
                        error="Element not found: #add-to-cart-button"
                    )
                ]
            )
        ]
    )

    content_type_map = {
        "html": "text/html",
        "pdf": "application/pdf",
        "json": "application/json",
        "csv": "text/csv",
        "markdown": "text/markdown"
    }

    extension_map = {
        "html": "html",
        "pdf": "pdf",
        "json": "json",
        "csv": "csv",
        "markdown": "md"
    }

    format = request.format
    content_type = content_type_map.get(format, "text/plain")
    extension = extension_map.get(format, "txt")
    filename = f"uat-report-{request.cycle_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{extension}"

    # Generate the report content
    if format == "html":
        content = generate_html_report(sample_data)
    elif format == "json":
        content = generate_json_report(sample_data)
    elif format == "csv":
        content = generate_csv_report(sample_data)
    elif format == "markdown":
        content = generate_markdown_report(sample_data)
    elif format == "pdf":
        # PDF generation would require additional dependencies (weasyprint, reportlab, etc.)
        # For now, return HTML with a note
        content = "<html><body><h1>PDF generation requires additional dependencies</h1><p>Please use HTML format instead.</p></body></html>"
        content_type = "text/html"
        filename = filename.replace(".pdf", ".html")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/reports/formats")
async def get_supported_formats():
    """Get list of supported report formats."""
    return {
        "formats": [
            {"value": "html", "label": "HTML Report", "description": "Interactive HTML document with styling"},
            {"value": "json", "label": "JSON Data", "description": "Machine-readable JSON format"},
            {"value": "csv", "label": "CSV Spreadsheet", "description": "Comma-separated values for Excel"},
            {"value": "markdown", "label": "Markdown", "description": "Markdown text format"},
            {"value": "pdf", "label": "PDF Document", "description": "Printable PDF (requires additional dependencies)"}
        ]
    }


@router.post("/reports/preview", response_class=HTMLResponse)
async def preview_report(request: ReportRequest) -> HTMLResponse:
    """
    Generate a preview of the report as HTML.
    Returns HTML directly in the response for iframe preview.
    """
    sample_data = UATReportData(
        cycle_id=request.cycle_id,
        cycle_name=f"UAT Test Cycle {request.cycle_id}",
        started_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
        total_duration_seconds=300.0,
        total_journeys=3,
        total_tests=45,
        passed_tests=42,
        failed_tests=3,
        pass_rate=93.3,
        journeys=[]
    )

    html = generate_html_report(sample_data)
    return HTMLResponse(content=html)


__all__ = ["router"]
