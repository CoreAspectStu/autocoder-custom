"""
Reports Router
==============

Provides comprehensive reporting for AutoCoder projects:
- Weekly reports (7-day summary)
- Monthly reports (30-day summary)
- System health metrics
- Project progress tracking
"""

import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter

# Add root to path for registry import
import sys
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from registry import list_registered_projects

router = APIRouter(tags=["reports"])


def get_system_metrics() -> dict:
    """Get system-wide metrics including CPU, memory, ECC errors."""
    try:
        # CPU and load average
        load1, load5, load15 = subprocess.getoutput("uptime | awk -F'load average:' '{print $2}'").strip().split(',')
        load_avg = {
            "1min": float(load1.strip()),
            "5min": float(load5.strip()),
            "15min": float(load15.strip())
        }

        # Memory
        mem_info = subprocess.getoutput("free -m | grep Mem").split()
        memory = {
            "total_gb": round(int(mem_info[1]) / 1024, 1),
            "used_gb": round(int(mem_info[2]) / 1024, 1),
            "free_gb": round(int(mem_info[3]) / 1024, 1),
            "percent_used": round((int(mem_info[2]) / int(mem_info[1])) * 100, 1)
        }

        # ECC errors
        ecc_errors = 0
        try:
            ecc_errors = int(subprocess.getoutput("cat /sys/devices/system/edac/mc/mc0/csrow6/ce_count 2>/dev/null || echo 0").strip())
        except:
            pass

        # Agent count
        agent_count = int(subprocess.getoutput("pgrep -fc 'autonomous_agent_demo.py.*coding' || echo 0").strip())

        return {
            "load_average": load_avg,
            "memory": memory,
            "ecc_errors": ecc_errors,
            "active_agents": agent_count
        }
    except Exception as e:
        return {"error": str(e)}


def get_project_report(project_name: str, days: int) -> dict:
    """Get detailed report for a single project."""
    projects = list_registered_projects()
    if project_name not in projects:
        return {"error": f"Project '{project_name}' not found"}

    project_path = Path(projects[project_name]["path"])
    features_db = project_path / "features.db"

    if not features_db.exists():
        return {
            "name": project_name,
            "status": "No database",
            "features_completed": 0,
            "features_total": 0,
            "percentage": 0
        }

    conn = sqlite3.connect(features_db)

    # Calculate period
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Total stats
    total_result = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN passes = 1 THEN 1 ELSE 0 END) as passing
        FROM features
    """).fetchone()

    total_features = total_result[0] if total_result else 0
    total_passing = total_result[1] if total_result else 0

    # Completed in period
    completed_result = conn.execute("""
        SELECT COUNT(*)
        FROM features
        WHERE completed_at IS NOT NULL
            AND completed_at >= datetime(?)
    """, (start_date.isoformat(),)).fetchone()

    completed_in_period = completed_result[0] if completed_result else 0

    # Created in period
    created_result = conn.execute("""
        SELECT COUNT(*)
        FROM features
        WHERE created_at IS NOT NULL
            AND created_at >= datetime(?)
    """, (start_date.isoformat(),)).fetchone()

    created_in_period = created_result[0] if created_result else 0

    # Failed/Blocked count
    failed_result = conn.execute("""
        SELECT COUNT(*)
        FROM features
        WHERE passes = 0 AND retries >= 3
    """).fetchone()

    failed_count = failed_result[0] if failed_result else 0

    # In-progress count
    in_progress_result = conn.execute("""
        SELECT COUNT(*)
        FROM features
        WHERE passes = 0 AND retries < 3
    """).fetchone()

    in_progress_count = in_progress_result[0] if in_progress_result else 0

    # Last activity
    last_activity = conn.execute("""
        SELECT MAX(completed_at)
        FROM features
        WHERE completed_at IS NOT NULL
    """).fetchone()[0]

    conn.close()

    return {
        "name": project_name,
        "path": str(project_path),
        "features_total": total_features,
        "features_passing": total_passing,
        "features_failed": failed_count,
        "features_in_progress": in_progress_count,
        "percentage_complete": round((total_passing / total_features * 100) if total_features > 0 else 0, 1),
        "completed_in_period": completed_in_period,
        "created_in_period": created_in_period,
        "last_activity": last_activity,
        "status": "Active" if completed_in_period > 0 else "Idle"
    }


@router.get("/api/reports/weekly")
async def get_weekly_report():
    """
    Generate a comprehensive weekly report (7 days).

    Returns:
        {
            "report_type": "weekly",
            "period": {"start": date, "end": date, "days": 7},
            "generated_at": timestamp,
            "system": {...},
            "projects": [...],
            "summary": {...}
        }
    """
    return await _generate_report(days=7, report_type="weekly")


@router.get("/api/reports/monthly")
async def get_monthly_report():
    """
    Generate a comprehensive monthly report (30 days).

    Returns:
        {
            "report_type": "monthly",
            "period": {"start": date, "end": date, "days": 30},
            "generated_at": timestamp,
            "system": {...},
            "projects": [...],
            "summary": {...}
        }
    """
    return await _generate_report(days=30, report_type="monthly")


async def _generate_report(days: int, report_type: str) -> dict:
    """Internal function to generate a report."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Get all project reports
    projects = list_registered_projects()
    project_reports = []

    total_completed = 0
    total_features = 0
    total_passing = 0
    active_projects = 0

    for project_name in projects.keys():
        report = get_project_report(project_name, days)
        if "error" not in report:
            project_reports.append(report)
            total_completed += report["completed_in_period"]
            total_features += report["features_total"]
            total_passing += report["features_passing"]
            if report["status"] == "Active":
                active_projects += 1

    # Get system metrics
    system = get_system_metrics()

    # Calculate summary
    overall_percentage = (total_passing / total_features * 100) if total_features > 0 else 0
    avg_per_day = total_completed / days

    return {
        "report_type": report_type,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days
        },
        "generated_at": datetime.utcnow().isoformat(),
        "system": system,
        "projects": project_reports,
        "summary": {
            "total_features": total_features,
            "total_passing": total_passing,
            "overall_percentage": round(overall_percentage, 1),
            "completed_in_period": total_completed,
            "active_projects": active_projects,
            "average_per_day": round(avg_per_day, 1)
        }
    }


@router.get("/api/reports/slack/{report_type}")
async def get_slack_formatted_report(report_type: str = "weekly"):
    """
    Get a report formatted for Slack posting.

    Args:
        report_type: Either 'weekly' (7 days) or 'monthly' (30 days)

    Returns:
        {
            "text": "Slack formatted message",
            "blocks": [...]
        }
    """
    days = 7 if report_type == "weekly" else 30
    report = await _generate_report(days, report_type)

    # Format for Slack
    period_emoji = "📅" if report_type == "weekly" else "📆"

    text = f"""{period_emoji} *AutoCoder {report_type.capitalize()} Report*

*Period:* Last {days} days ({report['period']['start'][:10]} to {report['period']['end'][:10]})

📊 *Overall Progress:*
• {report['summary']['total_passing']}/{report['summary']['total_features']} features passing ({report['summary']['overall_percentage']}%)
• {report['summary']['completed_in_period']} features completed this {report_type}
• {report['summary']['average_per_day']} avg features/day
• {report['summary']['active_projects']} active projects

💻 *System Health:*
• Load: {report['system']['load_average']['1min']} / {report['system']['load_average']['5min']} / {report['system']['load_average']['15min']}
• Memory: {report['system']['memory']['used_gb']}GB / {report['system']['memory']['total_gb']}GB ({report['system']['memory']['percent_used']}%)
• ECC Errors: {report['system']['ecc_errors']} correctable
• Active Agents: {report['system']['active_agents']}
"""

    # Add project details
    if report['projects']:
        text += "\n📁 *Projects:*\n"
        for p in report['projects']:
            status_emoji = "✅" if p['status'] == "Active" else "💤"
            text += f"{status_emoji} *{p['name']}*: {p['features_passing']}/{p['features_total']} ({p['percentage_complete']}%)"
            if p['completed_in_period'] > 0:
                text += f" - +{p['completed_in_period']} this {report_type}"
            text += "\n"

    return {
        "text": text,
        "report": report
    }
