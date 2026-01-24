"""
Analytics Router
================

Provides time-series data for project activity tracking:
- Features created over time
- Features completed over time
- Agent activity over time
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from fastapi import APIRouter

# Add root to path for registry import
import sys
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from registry import list_registered_projects

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics/features/{project_name}")
async def get_features_over_time(
    project_name: str,
    days: int = 30,
    granularity: str = "day"
) -> dict:
    """
    Get feature creation and completion trends over time.

    Args:
        project_name: Name of the project
        days: Number of days to look back (default: 30)
        granularity: Time bucket size - 'day' or 'week' (default: 'day')

    Returns:
        {
            "project": str,
            "period": {"start": date, "end": date, "days": int},
            "created": [{"date": str, "count": int}, ...],
            "completed": [{"date": str, "count": int}, ...],
            "cumulative": {
                "created": [{"date": str, "total": int}, ...],
                "completed": [{"date": str, "total": int}, ...]
            }
        }
    """
    projects = list_registered_projects()
    if project_name not in projects:
        return {"error": f"Project '{project_name}' not found"}

    project_path = Path(projects[project_name]["path"])
    features_db = project_path / "features.db"

    if not features_db.exists():
        return {
            "project": project_name,
            "period": {"start": None, "end": None, "days": 0},
            "created": [],
            "completed": [],
            "cumulative": {"created": [], "completed": []}
        }

    conn = sqlite3.connect(features_db)

    # Determine date format based on granularity
    date_format = "%Y-%m-%d" if granularity == "day" else "%Y-W%W"
    date_trunc = "date" if granularity == "day" else "strftime('%Y-W%W', "

    # Calculate period
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Query features created over time
    created_query = f"""
        SELECT
            strftime('{date_format}', created_at) as date,
            COUNT(*) as count
        FROM features
        WHERE created_at IS NOT NULL
            AND created_at >= datetime('{start_date.isoformat()}')
        GROUP BY date
        ORDER BY date
    """

    # Query features completed over time
    completed_query = f"""
        SELECT
            strftime('{date_format}', completed_at) as date,
            COUNT(*) as count
        FROM features
        WHERE completed_at IS NOT NULL
            AND completed_at >= datetime('{start_date.isoformat()}')
        GROUP BY date
        ORDER BY date
    """

    created_raw = conn.execute(created_query).fetchall()
    completed_raw = conn.execute(completed_query).fetchall()

    conn.close()

    # Convert to list of dicts
    created = [{"date": row[0], "count": row[1]} for row in created_raw]
    completed = [{"date": row[0], "count": row[1]} for row in completed_raw]

    # Calculate cumulative totals
    created_cumulative = []
    completed_cumulative = []

    created_total = 0
    completed_total = 0

    # Get all unique dates
    all_dates = sorted(set([r["date"] for r in created] + [r["date"] for r in completed]))

    for date in all_dates:
        created_count = next((r["count"] for r in created if r["date"] == date), 0)
        completed_count = next((r["count"] for r in completed if r["date"] == date), 0)

        created_total += created_count
        completed_total += completed_count

        created_cumulative.append({"date": date, "total": created_total})
        completed_cumulative.append({"date": date, "total": completed_total})

    return {
        "project": project_name,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days
        },
        "created": created,
        "completed": completed,
        "cumulative": {
            "created": created_cumulative,
            "completed": completed_cumulative
        }
    }


@router.get("/api/analytics/throughput/{project_name}")
async def get_throughput_stats(
    project_name: str,
    days: int = 30
) -> dict:
    """
    Get throughput statistics for a project.

    Args:
        project_name: Name of the project
        days: Number of days to analyze (default: 30)

    Returns:
        {
            "project": str,
            "period_days": int,
            "features_completed": int,
            "features_created": int,
            "completion_rate": float (features_completed / features_created),
            "average_per_day": float,
            "current_streak": int (days with completions),
            "total_features": int,
            "percentage_complete": float
        }
    """
    projects = list_registered_projects()
    if project_name not in projects:
        return {"error": f"Project '{project_name}' not found"}

    project_path = Path(projects[project_name]["path"])
    features_db = project_path / "features.db"

    if not features_db.exists():
        return {
            "project": project_name,
            "period_days": days,
            "features_completed": 0,
            "features_created": 0,
            "completion_rate": 0.0,
            "average_per_day": 0.0,
            "current_streak": 0,
            "total_features": 0,
            "percentage_complete": 0.0
        }

    conn = sqlite3.connect(features_db)

    # Calculate period
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Features completed in period
    completed_result = conn.execute("""
        SELECT COUNT(*)
        FROM features
        WHERE completed_at IS NOT NULL
            AND completed_at >= datetime(?)
    """, (start_date.isoformat(),)).fetchone()

    features_completed = completed_result[0] if completed_result else 0

    # Features created in period
    created_result = conn.execute("""
        SELECT COUNT(*)
        FROM features
        WHERE created_at IS NOT NULL
            AND created_at >= datetime(?)
    """, (start_date.isoformat(),)).fetchone()

    features_created = created_result[0] if created_result else 0

    # Total stats
    total_result = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN passes = 1 THEN 1 ELSE 0 END) as passing
        FROM features
    """).fetchone()

    total_features = total_result[0] if total_result else 0
    total_passing = total_result[1] if total_result else 0

    # Calculate completion streak
    streak_query = """
        SELECT DISTINCT date(completed_at) as completion_date
        FROM features
        WHERE completed_at IS NOT NULL
            AND completed_at >= datetime(?)
        ORDER BY completion_date DESC
    """

    streak_results = conn.execute(streak_query, (start_date.isoformat(),)).fetchall()

    # Calculate consecutive days
    current_streak = 0
    if streak_results:
        current_streak = 1
        for i in range(len(streak_results) - 1):
            date1 = datetime.strptime(streak_results[i][0], "%Y-%m-%d")
            date2 = datetime.strptime(streak_results[i + 1][0], "%Y-%m-%d")
            if (date1 - date2).days == 1:
                current_streak += 1
            else:
                break

    conn.close()

    # Calculate metrics
    completion_rate = (features_completed / features_created) if features_created > 0 else 0.0
    average_per_day = features_completed / days
    percentage_complete = (total_passing / total_features) if total_features > 0 else 0.0

    return {
        "project": project_name,
        "period_days": days,
        "features_completed": features_completed,
        "features_created": features_created,
        "completion_rate": round(completion_rate, 2),
        "average_per_day": round(average_per_day, 2),
        "current_streak": current_streak,
        "total_features": total_features,
        "percentage_complete": round(percentage_complete * 100, 2)
    }


@router.get("/api/analytics/summary")
async def get_all_projects_summary(days: int = 30) -> dict:
    """
    Get analytics summary for all projects.

    Args:
        days: Number of days to analyze (default: 30)

    Returns:
        {
            "period_days": int,
            "projects": [
                {
                    "name": str,
                    "features_completed": int,
                    "features_created": int,
                    "completion_rate": float,
                    "total_features": int,
                    "percentage_complete": float
                },
                ...
            ],
            "totals": {
                "features_completed": int,
                "features_created": int,
                "projects_active": int
            }
        }
    """
    projects = list_registered_projects()
    summaries = []

    total_completed = 0
    total_created = 0
    active_projects = 0

    for project_name in projects.keys():
        result = await get_throughput_stats(project_name, days)
        if "error" not in result:
            summaries.append({
                "name": project_name,
                "features_completed": result["features_completed"],
                "features_created": result["features_created"],
                "completion_rate": result["completion_rate"],
                "total_features": result["total_features"],
                "percentage_complete": result["percentage_complete"]
            })

            total_completed += result["features_completed"]
            total_created += result["features_created"]
            if result["features_completed"] > 0:
                active_projects += 1

    return {
        "period_days": days,
        "projects": summaries,
        "totals": {
            "features_completed": total_completed,
            "features_created": total_created,
            "projects_active": active_projects
        }
    }
