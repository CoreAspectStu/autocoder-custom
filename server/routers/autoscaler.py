"""
AutoScaler Router
=================

Provides HTTP API endpoints for the intelligent autoscaling system:
- Get autoscaler status and current metrics
- View scaling history
- Control mode (enabled/disabled/manual)
- Manual scaling override
- Configuration management
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.autoscaler import (
    AutoScaler,
    AutoscalerConfig,
    ScalingAction,
    ScalingMode,
    ScalingPolicy,
    get_autoscaler,
)
from ..utils.resource_monitor import ResourceMetrics

router = APIRouter(tags=["autoscaler"])

# Database path
AUTOSCALER_DB = Path.home() / ".autocoder" / "autoscaler.db"


# ============================================================================
# Pydantic Models
# ============================================================================


class AutoscalerStatus(BaseModel):
    """Current autoscaler status."""
    mode: str = Field(description="enabled, disabled, or manual")
    policy: str = Field(description="conservative, balanced, or aggressive")
    is_running: bool = Field(description="True if monitoring loop is active")
    current_limits: dict = Field(description="Current resource limits")
    last_scale_time: Optional[str] = Field(None, description="ISO timestamp of last scale action")
    scale_up_count: int = Field(description="Consecutive scale-up triggers")
    scale_down_count: int = Field(description="Consecutive scale-down triggers")


class ResourceMetricsResponse(BaseModel):
    """Current resource usage metrics."""
    timestamp: str = Field(description="ISO timestamp")
    cpu_percent: float = Field(description="CPU usage percentage")
    cpu_cores_used: float = Field(description="CPU cores in use")
    memory_gb: float = Field(description="Memory usage in GB")
    process_count: int = Field(description="Process count")
    agent_count: int = Field(description="Number of coding agents running")
    testing_agent_count: int = Field(description="Number of testing agents running")
    api_quota_remaining: int = Field(description="Remaining API quota prompts")
    features_pending: int = Field(description="Number of features pending")


class ScalingActionResponse(BaseModel):
    """Historical scaling action."""
    id: int = Field(description="Action ID")
    timestamp: str = Field(description="ISO timestamp")
    action: str = Field(description="scale_up, scale_down, manual, or emergency_stop")
    trigger_type: str = Field(description="threshold, prediction, queue, manual, or emergency")
    reason: str = Field(description="Human-readable reason")
    old_limits: dict = Field(description="Limits before scaling")
    new_limits: dict = Field(description="Limits after scaling")
    status: str = Field(description="success, failed, or rolled_back")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class ManualScaleRequest(BaseModel):
    """Manual scaling request."""
    cpu_quota: int = Field(description="CPU quota in percent (100 = 1 core)", ge=100, le=800)
    memory_max: int = Field(description="Memory limit in GB", ge=8, le=192)
    tasks_max: int = Field(description="Maximum process count", ge=100, le=1500)
    reason: str = Field(description="Reason for manual scaling")


class AutoscalerConfigResponse(BaseModel):
    """Autoscaler configuration."""
    mode: str = Field(description="enabled, disabled, or manual")
    policy: str = Field(description="conservative, balanced, or aggressive")
    scale_up_cpu_percent: int = Field(description="CPU threshold for scale-up")
    scale_up_memory_percent: int = Field(description="Memory threshold for scale-up")
    scale_up_tasks_percent: int = Field(description="Tasks threshold for scale-up")
    scale_down_cpu_percent: int = Field(description="CPU threshold for scale-down")
    scale_down_memory_percent: int = Field(description="Memory threshold for scale-down")
    scale_down_tasks_percent: int = Field(description="Tasks threshold for scale-down")
    check_interval_seconds: int = Field(description="Metrics polling interval")
    scale_cooldown_seconds: int = Field(description="Minimum time between scale actions")
    consecutive_scale_up_checks: int = Field(description="Required consecutive breaches for scale-up")
    consecutive_scale_down_checks: int = Field(description="Required consecutive breaches for scale-down")
    scale_up_factor: float = Field(description="Multiplier for scale-up")
    scale_down_factor: float = Field(description="Multiplier for scale-down")
    min_cpu_quota: int = Field(description="Minimum CPU quota")
    max_cpu_quota: int = Field(description="Maximum CPU quota")
    min_memory_max: int = Field(description="Minimum memory limit")
    max_memory_max: int = Field(description="Maximum memory limit")
    min_tasks_max: int = Field(description="Minimum task limit")
    max_tasks_max: int = Field(description="Maximum task limit")
    system_cpu_cores: int = Field(description="CPU cores reserved for system")
    system_memory_gb: int = Field(description="Memory reserved for system (GB)")
    system_processes: int = Field(description="Processes reserved for system")


class SetModeRequest(BaseModel):
    """Set autoscaler mode request."""
    mode: str = Field(description="enabled, disabled, or manual")


class SetPolicyRequest(BaseModel):
    """Set scaling policy request."""
    policy: str = Field(description="conservative, balanced, or aggressive")


class SetConfigRequest(BaseModel):
    """Update autoscaler configuration."""
    mode: Optional[str] = Field(None, description="enabled, disabled, or manual")
    policy: Optional[str] = Field(None, description="conservative, balanced, or aggressive")
    scale_up_cpu_percent: Optional[int] = Field(None, ge=50, le=100)
    scale_up_memory_percent: Optional[int] = Field(None, ge=50, le=100)
    scale_up_tasks_percent: Optional[int] = Field(None, ge=50, le=100)
    scale_down_cpu_percent: Optional[int] = Field(None, ge=10, le=80)
    scale_down_memory_percent: Optional[int] = Field(None, ge=10, le=80)
    scale_down_tasks_percent: Optional[int] = Field(None, ge=10, le=80)
    check_interval_seconds: Optional[int] = Field(None, ge=10, le=300)
    scale_cooldown_seconds: Optional[int] = Field(None, ge=60, le=3600)
    consecutive_scale_up_checks: Optional[int] = Field(None, ge=1, le=10)
    consecutive_scale_down_checks: Optional[int] = Field(None, ge=1, le=20)
    scale_up_factor: Optional[float] = Field(None, ge=1.1, le=3.0)
    scale_down_factor: Optional[float] = Field(None, ge=0.3, le=0.9)
    min_cpu_quota: Optional[int] = Field(None, ge=100, le=200)
    max_cpu_quota: Optional[int] = Field(None, ge=200, le=800)
    min_memory_max: Optional[int] = Field(None, ge=4, le=16)
    max_memory_max: Optional[int] = Field(None, ge=32, le=256)
    min_tasks_max: Optional[int] = Field(None, ge=50, le=200)
    max_tasks_max: Optional[int] = Field(None, ge=200, le=2000)


# ============================================================================
# Status Endpoints
# ============================================================================


@router.get("/api/autoscaler/status", response_model=AutoscalerStatus)
async def get_autoscaler_status():
    """
    Get current autoscaler status.

    Returns:
        Autoscaler status including mode, policy, current limits, and counters
    """
    autoscaler = get_autoscaler()
    return autoscaler.get_status()


@router.get("/api/autoscaler/metrics", response_model=ResourceMetricsResponse)
async def get_current_metrics():
    """
    Get current resource usage metrics.

    Returns:
        Current ResourceMetrics snapshot
    """
    from ..utils.resource_monitor import get_resource_monitor

    try:
        monitor = get_resource_monitor()
        metrics = monitor.collect_metrics()

        return ResourceMetricsResponse(
            timestamp=metrics.timestamp.isoformat(),
            cpu_percent=metrics.cpu_percent,
            cpu_cores_used=metrics.cpu_cores_used,
            memory_gb=metrics.memory_gb,
            process_count=metrics.process_count,
            agent_count=metrics.agent_count,
            testing_agent_count=metrics.testing_agent_count,
            api_quota_remaining=metrics.api_quota_remaining,
            features_pending=metrics.features_pending,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/autoscaler/history", response_model=list[ScalingActionResponse])
async def get_scaling_history(limit: int = 20):
    """
    Get scaling history.

    Args:
        limit: Maximum number of history entries to return (default: 20)

    Returns:
        List of recent scaling actions
    """
    conn = sqlite3.connect(AUTOSCALER_DB)
    try:
        cursor = conn.execute(
            """
            SELECT id, timestamp, action, trigger_type, reason,
                   old_cpu_quota, old_memory_max, old_tasks_max,
                   new_cpu_quota, new_memory_max, new_tasks_max,
                   status, error_message
            FROM autoscaler_history
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )

        history = []
        for row in cursor.fetchall():
            history.append(
                ScalingActionResponse(
                    id=row[0],
                    timestamp=row[1],
                    action=row[2],
                    trigger_type=row[3],
                    reason=row[4],
                    old_limits={
                        "cpu_quota": row[5],
                        "memory_max": row[6],
                        "tasks_max": row[7],
                    },
                    new_limits={
                        "cpu_quota": row[8],
                        "memory_max": row[9],
                        "tasks_max": row[10],
                    },
                    status=row[11],
                    error_message=row[12],
                )
            )

        return history
    finally:
        conn.close()


@router.get("/api/autoscaler/config", response_model=AutoscalerConfigResponse)
async def get_autoscaler_config():
    """
    Get autoscaler configuration.

    Returns:
        Current autoscaler configuration
    """
    config = AutoscalerConfig.load()
    return AutoscalerConfigResponse(
        mode=config.mode.value,
        policy=config.policy.value,
        scale_up_cpu_percent=config.scale_up_cpu_percent,
        scale_up_memory_percent=config.scale_up_memory_percent,
        scale_up_tasks_percent=config.scale_up_tasks_percent,
        scale_down_cpu_percent=config.scale_down_cpu_percent,
        scale_down_memory_percent=config.scale_down_memory_percent,
        scale_down_tasks_percent=config.scale_down_tasks_percent,
        check_interval_seconds=config.check_interval_seconds,
        scale_cooldown_seconds=config.scale_cooldown_seconds,
        consecutive_scale_up_checks=config.consecutive_scale_up_checks,
        consecutive_scale_down_checks=config.consecutive_scale_down_checks,
        scale_up_factor=config.scale_up_factor,
        scale_down_factor=config.scale_down_factor,
        min_cpu_quota=config.min_cpu_quota,
        max_cpu_quota=config.max_cpu_quota,
        min_memory_max=config.min_memory_max,
        max_memory_max=config.max_memory_max,
        min_tasks_max=config.min_tasks_max,
        max_tasks_max=config.max_tasks_max,
        system_cpu_cores=config.system_cpu_cores,
        system_memory_gb=config.system_memory_gb,
        system_processes=config.system_processes,
    )


# ============================================================================
# Control Endpoints
# ============================================================================


@router.post("/api/autoscaler/mode")
async def set_autoscaler_mode(request: SetModeRequest):
    """
    Set autoscaler operational mode.

    Args:
        request: Mode (enabled, disabled, manual)

    Returns:
        Success status
    """
    autoscaler = get_autoscaler()

    try:
        mode = ScalingMode(request.mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {request.mode}. Must be: enabled, disabled, or manual",
        )

    success = autoscaler.set_mode(mode)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    return {"success": True, "mode": mode.value}


@router.post("/api/autoscaler/policy")
async def set_autoscaler_policy(request: SetPolicyRequest):
    """
    Set scaling policy profile.

    Args:
        request: Policy (conservative, balanced, aggressive)

    Returns:
        Success status with applied thresholds
    """
    autoscaler = get_autoscaler()

    try:
        policy = ScalingPolicy(request.policy)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid policy: {request.policy}. Must be: conservative, balanced, or aggressive",
        )

    success = autoscaler.set_policy(policy)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    # Return updated thresholds
    config = autoscaler.config
    return {
        "success": True,
        "policy": policy.value,
        "scale_up_cpu_percent": config.scale_up_cpu_percent,
        "scale_up_memory_percent": config.scale_up_memory_percent,
        "scale_cooldown_seconds": config.scale_cooldown_seconds,
        "scale_up_factor": config.scale_up_factor,
    }


@router.post("/api/autoscaler/scale")
async def manual_scale(request: ManualScaleRequest):
    """
    Manually scale resources.

    Args:
        request: New resource limits with reason

    Returns:
        Success status
    """
    autoscaler = get_autoscaler()

    # Switch to manual mode if not already
    if autoscaler.config.mode != ScalingMode.MANUAL:
        autoscaler.set_mode(ScalingMode.MANUAL)

    # Calculate new limits
    new_limits = {
        "cpu_quota": request.cpu_quota,
        "memory_max": request.memory_max,
        "tasks_max": request.tasks_max,
    }

    # Get current limits
    old_limits = autoscaler.get_current_limits()

    # Apply new limits
    success = await autoscaler.update_limits(new_limits)

    # Log the action
    action = ScalingAction(
        timestamp=datetime.utcnow(),
        action="manual",
        trigger_type="manual",
        reason=request.reason,
        old_limits=old_limits,
        new_limits=new_limits,
        status="success" if success else "failed",
        error_message=None if success else "Service restart failed",
    )
    autoscaler.log_action(action)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update resource limits")

    return {
        "success": True,
        "old_limits": old_limits,
        "new_limits": new_limits,
        "reason": request.reason,
    }


@router.put("/api/autoscaler/config")
async def update_autoscaler_config(request: SetConfigRequest):
    """
    Update autoscaler configuration.

    Args:
        request: Configuration fields to update (all optional)

    Returns:
        Updated configuration
    """
    config = AutoscalerConfig.load()

    # Update only provided fields
    if request.mode is not None:
        try:
            config.mode = ScalingMode(request.mode)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode: {request.mode}",
            )

    if request.policy is not None:
        try:
            config.policy = ScalingPolicy(request.policy)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid policy: {request.policy}",
            )

    if request.scale_up_cpu_percent is not None:
        config.scale_up_cpu_percent = request.scale_up_cpu_percent
    if request.scale_up_memory_percent is not None:
        config.scale_up_memory_percent = request.scale_up_memory_percent
    if request.scale_up_tasks_percent is not None:
        config.scale_up_tasks_percent = request.scale_up_tasks_percent
    if request.scale_down_cpu_percent is not None:
        config.scale_down_cpu_percent = request.scale_down_cpu_percent
    if request.scale_down_memory_percent is not None:
        config.scale_down_memory_percent = request.scale_down_memory_percent
    if request.scale_down_tasks_percent is not None:
        config.scale_down_tasks_percent = request.scale_down_tasks_percent
    if request.check_interval_seconds is not None:
        config.check_interval_seconds = request.check_interval_seconds
    if request.scale_cooldown_seconds is not None:
        config.scale_cooldown_seconds = request.scale_cooldown_seconds
    if request.consecutive_scale_up_checks is not None:
        config.consecutive_scale_up_checks = request.consecutive_scale_up_checks
    if request.consecutive_scale_down_checks is not None:
        config.consecutive_scale_down_checks = request.consecutive_scale_down_checks
    if request.scale_up_factor is not None:
        config.scale_up_factor = request.scale_up_factor
    if request.scale_down_factor is not None:
        config.scale_down_factor = request.scale_down_factor
    if request.min_cpu_quota is not None:
        config.min_cpu_quota = request.min_cpu_quota
    if request.max_cpu_quota is not None:
        config.max_cpu_quota = request.max_cpu_quota
    if request.min_memory_max is not None:
        config.min_memory_max = request.min_memory_max
    if request.max_memory_max is not None:
        config.max_memory_max = request.max_memory_max
    if request.min_tasks_max is not None:
        config.min_tasks_max = request.min_tasks_max
    if request.max_tasks_max is not None:
        config.max_tasks_max = request.max_tasks_max

    # Save configuration
    success = config.save()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    # Reload autoscaler config
    autoscaler = get_autoscaler()
    autoscaler.config = config

    # Return updated configuration
    return get_autoscaler_config_response(config)


def get_autoscaler_config_response(config: AutoscalerConfig) -> AutoscalerConfigResponse:
    """Helper to convert config to response model."""
    return AutoscalerConfigResponse(
        mode=config.mode.value,
        policy=config.policy.value,
        scale_up_cpu_percent=config.scale_up_cpu_percent,
        scale_up_memory_percent=config.scale_up_memory_percent,
        scale_up_tasks_percent=config.scale_up_tasks_percent,
        scale_down_cpu_percent=config.scale_down_cpu_percent,
        scale_down_memory_percent=config.scale_down_memory_percent,
        scale_down_tasks_percent=config.scale_down_tasks_percent,
        check_interval_seconds=config.check_interval_seconds,
        scale_cooldown_seconds=config.scale_cooldown_seconds,
        consecutive_scale_up_checks=config.consecutive_scale_up_checks,
        consecutive_scale_down_checks=config.consecutive_scale_down_checks,
        scale_up_factor=config.scale_up_factor,
        scale_down_factor=config.scale_down_factor,
        min_cpu_quota=config.min_cpu_quota,
        max_cpu_quota=config.max_cpu_quota,
        min_memory_max=config.min_memory_max,
        max_memory_max=config.max_memory_max,
        min_tasks_max=config.min_tasks_max,
        max_tasks_max=config.max_tasks_max,
        system_cpu_cores=config.system_cpu_cores,
        system_memory_gb=config.system_memory_gb,
        system_processes=config.system_processes,
    )
