"""
Systemd Service Management Router
==================================

Provides API endpoints for managing the autocoder-ui.service:
- Get service status and resource usage
- Start/stop/restart service
- View service logs
- Manage resource limits dynamically
"""

import subprocess
import json
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import psutil

router = APIRouter(tags=["systemd"])

SERVICE_NAME = "autocoder-ui.service"
SERVICE_FILE = Path.home() / ".config/systemd/user" / SERVICE_NAME


# Pydantic models for request/response
class ServiceStatus(BaseModel):
    """Systemd service status."""
    active_state: str = Field(description="active, inactive, or failed")
    sub_state: str = Field(description="running, dead, etc.")
    memory_current: float = Field(description="Current memory usage in GB")
    memory_limit: float = Field(description="Memory limit in GB")
    cpu_quota: int = Field(description="CPU quota in percent (200% = 2 cores)")
    cpu_usage: float = Field(description="Current CPU usage percent")
    tasks_current: int = Field(description="Current process count")
    tasks_max: int = Field(description="Maximum process count")
    restart_count: int = Field(description="Number of restarts")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime in seconds")


class ResourceLimits(BaseModel):
    """Resource limits for the service."""
    cpu_quota: int = Field(description="CPU quota in percent (100 = 1 core)", ge=50, le=800)
    memory_max: int = Field(description="Memory limit in GB", ge=4, le=128)
    tasks_max: int = Field(description="Maximum process count", ge=50, le=500)


def _run_systemctl(command: list[str]) -> str:
    """
    Run systemctl command and return output.

    Args:
        command: Command to run (e.g., ['systemctl', '--user', 'show', ...])

    Returns:
        Command output as string

    Raises:
        HTTPException: Command fails
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Command failed: {e.stderr}"
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500,
            detail="Command timed out"
        )


def _get_service_property(property_name: str) -> str:
    """Get a single systemctl property value."""
    output = _run_systemctl([
        "systemctl", "--user", "show", SERVICE_NAME,
        "--property", property_name,
        "--value"
    ])
    return output.strip()


def _get_cgroup_memory_usage() -> tuple[float, float]:
    """
    Get current and max memory from cgroup.

    Returns:
        (current_memory_gb, max_memory_gb)
    """
    try:
        # Try cgroup v2 first
        memory_path = Path("/sys/fs/cgroup/user.slice/user-1000.slice")
        if not memory_path.exists():
            # Fallback to cgroup v1
            memory_path = Path("/sys/fs/cgroup/memory")

        # Find autocoder-ui.service cgroup
        for cgroup_path in memory_path.rglob("*"):
            if "autocoder-ui.service" in str(cgroup_path) and cgroup_path.is_dir():
                # Current memory usage
                current_file = cgroup_path / "memory.current"
                max_file = cgroup_path / "memory.max"

                if current_file.exists():
                    current_bytes = int(current_file.read_text().strip())
                    current_gb = current_bytes / (1024**3)
                else:
                    # Fallback to v1 path
                    usage_file = cgroup_path / "memory.usage_in_bytes"
                    if usage_file.exists():
                        current_bytes = int(usage_file.read_text().strip())
                        current_gb = current_bytes / (1024**3)
                    else:
                        current_gb = 0.0

                if max_file.exists():
                    max_str = max_file.read_text().strip()
                    if max_str == "max":
                        max_gb = 251.0  # System total
                    else:
                        max_bytes = int(max_str)
                        max_gb = max_bytes / (1024**3)
                else:
                    # Fallback to v1 path
                    limit_file = cgroup_path / "memory.limit_in_bytes"
                    if limit_file.exists():
                        max_bytes = int(limit_file.read_text().strip())
                        max_gb = max_bytes / (1024**3)
                    else:
                        max_gb = 32.0  # Default from service file

                return current_gb, max_gb

        # Fallback: use service file limits
        return 0.0, 32.0

    except Exception:
        # Final fallback
        return 0.0, 32.0


@router.get("/api/systemd/status", response_model=ServiceStatus)
async def get_service_status():
    """
    Get systemd service status and resource usage.

    Returns comprehensive status including:
    - Service state (active/inactive/failed)
    - Current resource usage (CPU, memory, processes)
    - Resource limits from cgroup
    - Restart count and uptime
    """
    # Get service state
    active_state = _get_service_property("ActiveState")
    sub_state = _get_service_property("SubState")

    # Get restart count
    restart_count = int(_get_service_property("NRestarts") or "0")

    # Get uptime
    uptime_timestamp = _get_service_property("StateChangeTimestamp")
    uptime_seconds = None
    if uptime_timestamp and uptime_timestamp != "0" and uptime_timestamp.isdigit():
        import time
        uptime_microseconds = int(uptime_timestamp)
        uptime_seconds = (time.time() * 1_000_000 - uptime_microseconds) / 1_000_000
        if uptime_seconds < 0:
            uptime_seconds = None

    # Get resource limits from service file
    cpu_quota = 200  # Default
    memory_limit = 32  # Default
    tasks_max = 250  # Default

    if SERVICE_FILE.exists():
        content = SERVICE_FILE.read_text()

        # Parse CPUQuota
        match = re.search(r'CPUQuota=(\d+)%', content)
        if match:
            cpu_quota = int(match.group(1))

        # Parse MemoryMax
        match = re.search(r'MemoryMax=(\d+)G?', content)
        if match:
            memory_limit = int(match.group(1))

        # Parse TasksMax
        match = re.search(r'TasksMax=(\d+)', content)
        if match:
            tasks_max = int(match.group(1))

    # Get current resource usage
    memory_current, _ = _get_cgroup_memory_usage()
    cpu_usage = psutil.cpu_percent(interval=0.5)

    # Get process count (if service is running)
    tasks_current = 0
    if active_state == "active":
        try:
            # Count processes in cgroup
            cgroup_path = Path("/proc/self/cgroup")
            if cgroup_path.exists():
                cgroup_content = cgroup_path.read_text()
                if "autocoder-ui.service" in cgroup_content:
                    # We're in the cgroup, count all Python processes
                    tasks_current = len([
                        p for p in psutil.process_iter()
                        if p.name() in ['python', 'python3', 'uvicorn']
                    ])
        except Exception:
            pass

    return ServiceStatus(
        active_state=active_state,
        sub_state=sub_state,
        memory_current=round(memory_current, 2),
        memory_limit=float(memory_limit),
        cpu_quota=cpu_quota,
        cpu_usage=round(cpu_usage, 1),
        tasks_current=tasks_current,
        tasks_max=tasks_max,
        restart_count=restart_count,
        uptime_seconds=uptime_seconds,
    )


@router.post("/api/systemd/start")
async def start_service():
    """
    Start the autocoder-ui.service.

    Validates service is not already running before starting.
    """
    # Check if already active
    try:
        active_state = _get_service_property("ActiveState")
        if active_state == "active":
            return {
                "success": False,
                "message": "Service is already running"
            }
    except Exception:
        pass  # Service might not exist yet, proceed with start

    try:
        _run_systemctl(["systemctl", "--user", "start", SERVICE_NAME])
        return {
            "success": True,
            "message": "Service started successfully"
        }
    except HTTPException as e:
        return {
            "success": False,
            "message": f"Failed to start service: {e.detail}"
        }


@router.post("/api/systemd/stop")
async def stop_service():
    """
    Stop the autocoder-ui.service.

    Validates service is running before stopping.
    """
    # Check if service is running
    try:
        active_state = _get_service_property("ActiveState")
        if active_state != "active":
            return {
                "success": False,
                "message": "Service is not running"
            }
    except Exception:
        return {
            "success": False,
            "message": "Service not found"
        }

    try:
        _run_systemctl(["systemctl", "--user", "stop", SERVICE_NAME])
        return {
            "success": True,
            "message": "Service stopped successfully"
        }
    except HTTPException as e:
        return {
            "success": False,
            "message": f"Failed to stop service: {e.detail}"
        }


@router.post("/api/systemd/restart")
async def restart_service():
    """
    Restart the autocoder-ui.service.

    Stops and starts the service, applying any configuration changes.
    """
    try:
        _run_systemctl(["systemctl", "--user", "restart", SERVICE_NAME])
        return {
            "success": True,
            "message": "Service restarted successfully"
        }
    except HTTPException as e:
        return {
            "success": False,
            "message": f"Failed to restart service: {e.detail}"
        }


@router.get("/api/systemd/logs")
async def get_service_logs(lines: int = 100):
    """
    Get systemd journal logs for the service.

    Args:
        lines: Number of log lines to retrieve (max 1000)
    """
    lines = min(lines, 1000)

    try:
        output = _run_systemctl([
            "journalctl", "--user", "-u", SERVICE_NAME,
            "-n", str(lines),
            "--no-pager"
        ])

        # Parse log lines
        log_lines = []
        for line in output.strip().split('\n'):
            if line.strip():
                log_lines.append(line)

        return {
            "logs": log_lines,
            "count": len(log_lines)
        }

    except HTTPException as e:
        return {
            "logs": [],
            "count": 0,
            "error": e.detail
        }


@router.get("/api/systemd/limits", response_model=ResourceLimits)
async def get_resource_limits():
    """
    Get current resource limits for the service.

    Returns the CPU quota, memory limit, and task limit.
    """
    cpu_quota = 200  # Default
    memory_max = 32  # Default
    tasks_max = 250  # Default

    if SERVICE_FILE.exists():
        content = SERVICE_FILE.read_text()

        # Parse CPUQuota
        match = re.search(r'CPUQuota=(\d+)%', content)
        if match:
            cpu_quota = int(match.group(1))

        # Parse MemoryMax
        match = re.search(r'MemoryMax=(\d+)G?', content)
        if match:
            memory_max = int(match.group(1))

        # Parse TasksMax
        match = re.search(r'TasksMax=(\d+)', content)
        if match:
            tasks_max = int(match.group(1))

    return ResourceLimits(
        cpu_quota=cpu_quota,
        memory_max=memory_max,
        tasks_max=tasks_max
    )


@router.put("/api/systemd/limits")
async def update_resource_limits(limits: ResourceLimits):
    """
    Update resource limits for the service.

    WARNING: This requires a service restart to apply changes.

    Process:
    1. Validate limits
    2. Backup current service file
    3. Update service file with new limits
    4. Reload systemd daemon
    5. Restart service
    6. Rollback on failure

    Args:
        limits: New resource limits to apply

    Returns:
        Success status and message
    """
    if not SERVICE_FILE.exists():
        return {
            "success": False,
            "message": "Service file not found - cannot update limits"
        }

    # Read current service file
    content = SERVICE_FILE.read_text()

    # Backup original file
    backup_file = SERVICE_FILE.with_suffix('.service.backup')
    try:
        backup_file.write_text(content)
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to create backup: {e}"
        }

    # Update CPUQuota
    content = re.sub(r'CPUQuota=\d+%', f'CPUQuota={limits.cpu_quota}%', content)

    # Update MemoryMax
    content = re.sub(r'MemoryMax=\d+G?', f'MemoryMax={limits.memory_max}G', content)

    # Update TasksMax
    content = re.sub(r'TasksMax=\d+', f'TasksMax={limits.tasks_max}', content)

    # Write updated file
    try:
        SERVICE_FILE.write_text(content)
    except Exception as e:
        # Restore backup
        backup_file.rename(SERVICE_FILE)
        return {
            "success": False,
            "message": f"Failed to write service file: {e}"
        }

    # Reload systemd daemon
    try:
        _run_systemctl(["systemctl", "--user", "daemon-reload"])
    except HTTPException as e:
        # Restore backup
        backup_file.rename(SERVICE_FILE)
        _run_systemctl(["systemctl", "--user", "daemon-reload"])
        return {
            "success": False,
            "message": f"Failed to reload systemd: {e.detail}"
        }

    # Restart service to apply changes
    try:
        _run_systemctl(["systemctl", "--user", "restart", SERVICE_NAME])
    except HTTPException as e:
        # Don't rollback on restart failure - limits are applied
        return {
            "success": True,
            "message": f"Limits updated but service failed to restart: {e.detail}"
        }

    return {
        "success": True,
        "message": f"Resource limits updated: CPU={limits.cpu_quota}%, Memory={limits.memory_max}GB, Tasks={limits.tasks_max}. Service restarted.",
        "limits": limits.model_dump()
    }
