"""
Emergency Stop Router
====================

Provides emergency stop functionality to immediately kill all
AutoCoder processes, agents, and browsers when things go wrong.
"""

import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import psutil

router = APIRouter(tags=["emergency"])


class EmergencyStatus(BaseModel):
    """Status check for potential issues requiring emergency stop."""
    total_processes: int = Field(description="Total AutoCoder-related processes")
    warning_level: str = Field(description="normal, warning, or critical")
    issues: list[str] = Field(description="List of detected issues")


class EmergencyStopResult(BaseModel):
    """Result of emergency stop operation."""
    killed_count: int = Field(description="Number of processes killed")
    terminated_count: int = Field(description="Processes terminated gracefully")
    force_killed_count: int = Field(description="Processes force-killed")
    lock_files_removed: int = Field(description="Lock files cleaned up")
    agents_reset: int = Field(description="Agents reset from in_progress state")


def find_all_autocoder_processes():
    """
    Enumerate all AutoCoder-related processes.

    Returns:
        List of psutil.Process objects
    """
    processes = []

    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])

            # Check if process is AutoCoder-related
            if any(pattern in cmdline.lower() for pattern in [
                'autonomous_agent_demo',
                'parallel_orchestrator',
                'uvicorn server.main:app',
                'playwright',
                'mcp_server',
                'coding_agent',
                'testing_agent',
            ]):
                processes.append(proc)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return processes


def kill_process_tree_batch(processes: list[psutil.Process], timeout: float = 5.0):
    """
    Kill multiple process trees with timeout.

    Args:
        processes: List of processes to kill
        timeout: Seconds to wait for graceful termination

    Returns:
        dict with statistics
    """
    terminated = []
    killed = []

    for proc in processes:
        try:
            # Try graceful termination first
            proc.terminate()

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Wait for graceful termination
    import time
    start = time.time()
    remaining = []

    for proc in processes:
        try:
            if proc.is_running():
                if time.time() - start < timeout:
                    remaining.append(proc)
                    terminated.append(proc)
                else:
                    # Timeout exceeded, force kill
                    proc.kill()
                    killed.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Force kill any remaining processes
    for proc in remaining:
        try:
            if proc.is_running():
                proc.kill()
                killed.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return {
        "terminated_count": len(terminated),
        "force_killed_count": len(killed),
        "total_count": len(terminated) + len(killed),
    }


def cleanup_lock_files():
    """
    Remove all .agent.lock files from registered projects.

    Returns:
        Number of lock files removed
    """
    count = 0

    try:
        from registry import list_registered_projects

        for project_name, project_info in list_registered_projects().items():
            project_path = Path(project_info.get("path", ""))
            lock_file = project_path / ".agent.lock"

            if lock_file.exists():
                try:
                    lock_file.unlink()
                    count += 1
                except Exception:
                    pass

    except Exception:
        pass

    return count


def reset_stuck_agents():
    """
    Reset all agents stuck in in_progress state.

    Returns:
        Number of agents reset
    """
    count = 0

    try:
        from registry import list_registered_projects
        from api.database import Feature, create_database, get_database_path

        for project_name, project_info in list_registered_projects().items():
            project_path = Path(project_info.get("path", ""))
            db_path = project_path / "features.db"

            if not db_path.exists():
                continue

            try:
                from sqlalchemy import create_engine, text
                engine = create_engine(f"sqlite:///{db_path}")

                with engine.connect() as conn:
                    result = conn.execute(
                        text("UPDATE features SET in_progress = 0 WHERE in_progress = 1")
                    )
                    count += result.rowcount

                    conn.commit()

            except Exception:
                pass

    except Exception:
        pass

    return count


@router.post("/api/emergency/stop", response_model=EmergencyStopResult)
async def emergency_stop():
    """
    EMERGENCY STOP - Kill ALL AutoCoder processes immediately.

    This will:
    1. Find all AutoCoder-related processes (agents, orchestrator, UI, browsers)
    2. Kill process trees (graceful → force kill)
    3. Remove all lock files
    4. Reset stuck agents in database
    5. Return summary of cleanup

    WARNING: This is destructive! All work will be lost.
    """
    # Find all processes
    processes = find_all_autocoder_processes()

    if not processes:
        return EmergencyStopResult(
            killed_count=0,
            terminated_count=0,
            force_killed_count=0,
            lock_files_removed=cleanup_lock_files(),
            agents_reset=reset_stuck_agents(),
        )

    # Kill processes
    stats = kill_process_tree_batch(processes)

    # Cleanup
    lock_files_removed = cleanup_lock_files()
    agents_reset = reset_stuck_agents()

    return EmergencyStopResult(
        killed_count=stats["total_count"],
        terminated_count=stats["terminated_count"],
        force_killed_count=stats["force_killed_count"],
        lock_files_removed=lock_files_removed,
        agents_reset=agents_reset,
    )


@router.get("/api/emergency/status", response_model=EmergencyStatus)
async def get_emergency_status():
    """
    Check for potential issues requiring emergency stop.

    Returns:
        Status with warning level and list of issues
    """
    processes = find_all_autocoder_processes()
    issues = []
    warning_level = "normal"

    # Process count warning
    if len(processes) > 200:
        issues.append(f"Process count critical: {len(processes)} (near 250 limit)")
        warning_level = "critical"
    elif len(processes) > 100:
        issues.append(f"Process count high: {len(processes)}")
        warning_level = "warning"

    # Memory usage check
    total_memory = 0
    for proc in processes:
        try:
            total_memory += proc.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    memory_gb = total_memory / (1024**3)

    if memory_gb > 16:
        issues.append(f"Memory usage critical: {memory_gb:.1f}GB")
        warning_level = "critical" if warning_level != "critical" else warning_level
    elif memory_gb > 8:
        issues.append(f"Memory usage high: {memory_gb:.1f}GB")
        warning_level = "warning" if warning_level == "normal" else warning_level

    # CPU usage check
    try:
        cpu_percent = psutil.cpu_percent(interval=1)

        if cpu_percent > 80:
            issues.append(f"CPU usage critical: {cpu_percent}%")
            warning_level = "critical" if warning_level != "critical" else warning_level
        elif cpu_percent > 50:
            issues.append(f"CPU usage high: {cpu_percent}%")
            warning_level = "warning" if warning_level == "normal" else warning_level

    except Exception:
        pass

    return EmergencyStatus(
        total_processes=len(processes),
        warning_level=warning_level,
        issues=issues,
    )


@router.post("/api/emergency/cleanup")
async def emergency_cleanup():
    """
    Cleanup orphaned lock files and reset stuck agents.

    Less destructive than full emergency stop - only cleans state,
    doesn't kill running processes.
    """
    lock_files_removed = cleanup_lock_files()
    agents_reset = reset_stuck_agents()

    return {
        "success": True,
        "lock_files_removed": lock_files_removed,
        "agents_reset": agents_reset,
        "message": f"Cleaned up {lock_files_removed} lock files and reset {agents_reset} stuck agents"
    }
