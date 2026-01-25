#!/usr/bin/env python3
"""
MCP Server for AutoScaler
=========================

Provides tools for intelligent resource autoscaling.

Tools:
- autoscaler_set_mode: Enable/disable autoscaling or set manual mode
- autoscaler_get_status: Get current autoscaler status and metrics
- autoscaler_manual_scale: Manually set resource limits
- autoscaler_get_history: View scaling action history
- autoscaler_set_policy: Set scaling policy (conservative/balanced/aggressive)
- autoscaler_set_config: Update autoscaler configuration thresholds
- autoscaler_get_prediction: Get predicted future resource needs (Phase 2+)

Usage:
    The autoscaler monitors CPU, memory, and process usage from cgroup v2.
    It automatically scales systemd service limits (CPUQuota, MemoryMax, TasksMax)
    based on workload patterns while maintaining headroom for system operations.

Example:
    # Enable autoscaling with balanced policy
    autoscaler_set_mode(mode="enabled")

    # Check status
    autoscaler_get_status()

    # Manually override for complex feature
    autoscaler_set_mode(mode="manual")
    autoscaler_manual_scale(cpu_quota=600, memory_max=96, tasks_max=750, reason="Complex AI feature")

    # Re-enable autoscaling
    autoscaler_set_mode(mode="enabled")
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.services.autoscaler import (
    AutoScaler,
    AutoscalerConfig,
    ScalingMode,
    ScalingPolicy,
    get_autoscaler,
)
from server.utils.resource_monitor import get_resource_monitor


# ============================================================================
# Pydantic Models
# ============================================================================


class SetModeInput(BaseModel):
    """Input for setting autoscaler mode."""
    mode: Literal["enabled", "disabled", "manual"] = Field(
        ...,
        description="Autoscaler mode: enabled (automatic), disabled (off), manual (user-controlled)"
    )


class SetPolicyInput(BaseModel):
    """Input for setting scaling policy."""
    policy: Literal["conservative", "balanced", "aggressive"] = Field(
        ...,
        description="Scaling policy: conservative (stable), balanced (default), aggressive (performance)"
    )


class ManualScaleInput(BaseModel):
    """Input for manual scaling."""
    cpu_quota: int = Field(
        ...,
        ge=100,
        le=800,
        description="CPU quota in percent (100 = 1 core, 800 = 8 cores)"
    )
    memory_max: int = Field(
        ...,
        ge=8,
        le=192,
        description="Memory limit in GB (8-192)"
    )
    tasks_max: int = Field(
        ...,
        ge=100,
        le=1500,
        description="Maximum process count (100-1500)"
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Human-readable reason for manual scaling"
    )


class GetHistoryInput(BaseModel):
    """Input for getting scaling history."""
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of history entries to return"
    )


# ============================================================================
# MCP Server Setup
# ============================================================================


@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Initialize autoscaler on startup."""
    # Initialize singleton (creates database if needed)
    _ = get_autoscaler()
    yield


# Initialize the MCP server
mcp = FastMCP("autoscaler", lifespan=server_lifespan)


# ============================================================================
# Control Tools
# ============================================================================


@mcp.tool()
def autoscaler_set_mode(mode: str) -> str:
    """Set the autoscaler operational mode.

    Use this to enable or disable automatic scaling, or switch to manual control.

    Args:
        mode: Operational mode
            - "enabled": Automatic scaling based on thresholds (default)
            - "disabled": Autoscaler off, limits stay at current values
            - "manual": User controls limits via autoscaler_manual_scale

    Returns:
        JSON with success status and current mode

    Example:
        # Enable automatic scaling
        autoscaler_set_mode(mode="enabled")

        # Disable autoscaling temporarily
        autoscaler_set_mode(mode="disabled")

        # Take manual control
        autoscaler_set_mode(mode="manual")
    """
    autoscaler = get_autoscaler()

    try:
        scaling_mode = ScalingMode(mode)
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid mode: {mode}. Must be: enabled, disabled, or manual"
        }

    success = autoscaler.set_mode(scaling_mode)

    if not success:
        return {
            "success": False,
            "error": "Failed to save configuration to database"
        }

    return {
        "success": True,
        "mode": mode,
        "message": f"Autoscaler mode set to {mode}"
    }


@mcp.tool()
def autoscaler_set_policy(policy: str) -> str:
    """Set the scaling policy profile.

    Policies pre-configure thresholds for different use cases:
    - conservative: Stable, minimal scaling (90% CPU threshold, 10 min cooldown)
    - balanced: Default (85% CPU threshold, 5 min cooldown)
    - aggressive: Performance-focused (75% CPU threshold, 2 min cooldown)

    Args:
        policy: Policy name (conservative, balanced, aggressive)

    Returns:
        JSON with success status and applied thresholds

    Example:
        # Use conservative policy for production stability
        autoscaler_set_policy(policy="conservative")

        # Use aggressive policy for development speed
        autoscaler_set_policy(policy="aggressive")
    """
    autoscaler = get_autoscaler()

    try:
        scaling_policy = ScalingPolicy(policy)
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid policy: {policy}. Must be: conservative, balanced, or aggressive"
        }

    success = autoscaler.set_policy(scaling_policy)

    if not success:
        return {
            "success": False,
            "error": "Failed to save configuration to database"
        }

    config = autoscaler.config

    return {
        "success": True,
        "policy": policy,
        "thresholds": {
            "scale_up_cpu_percent": config.scale_up_cpu_percent,
            "scale_up_memory_percent": config.scale_up_memory_percent,
            "scale_cooldown_seconds": config.scale_cooldown_seconds,
            "scale_up_factor": config.scale_up_factor,
        }
    }


@mcp.tool()
def autoscaler_manual_scale(
    cpu_quota: int,
    memory_max: int,
    tasks_max: int,
    reason: str
) -> str:
    """Manually set resource limits.

    Automatically switches to manual mode if not already active.
    Use this when you know the upcoming workload needs specific resources.

    Args:
        cpu_quota: CPU quota in percent (100 = 1 core, 800 = 8 cores max)
        memory_max: Memory limit in GB (8-192)
        tasks_max: Maximum process count (100-1500)
        reason: Human-readable reason for this scaling action

    Returns:
        JSON with old limits, new limits, and status

    Example:
        # Allocate more resources for complex AI feature
        autoscaler_manual_scale(
            cpu_quota=600,
            memory_max=96,
            tasks_max=750,
            reason="Complex AI feature requiring heavy computation"
        )

        # Reduce resources for lightweight maintenance
        autoscaler_manual_scale(
            cpu_quota=200,
            memory_max=16,
            tasks_max=200,
            reason="Low-priority maintenance tasks"
        )
    """
    autoscaler = get_autoscaler()

    # Switch to manual mode if needed
    if autoscaler.config.mode != ScalingMode.MANUAL:
        autoscaler.set_mode(ScalingMode.MANUAL)

    # Get current limits
    old_limits = autoscaler.get_current_limits()

    # Calculate new limits
    new_limits = {
        "cpu_quota": cpu_quota,
        "memory_max": memory_max,
        "tasks_max": tasks_max,
    }

    # Apply limits asynchronously
    async def apply_limits():
        return await autoscaler.update_limits(new_limits)

    # Run async function in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success = loop.run_until_complete(apply_limits())
    finally:
        loop.close()

    if not success:
        return {
            "success": False,
            "error": "Failed to update resource limits (service restart failed)"
        }

    return {
        "success": True,
        "old_limits": old_limits,
        "new_limits": new_limits,
        "reason": reason,
        "message": f"Resource limits updated: {cpu_quota}% CPU, {memory_max}GB RAM, {tasks_max} tasks"
    }


# ============================================================================
# Query Tools
# ============================================================================


@mcp.tool()
def autoscaler_get_status() -> str:
    """Get current autoscaler status and metrics.

    Returns the current mode, policy, resource limits, and recent metrics.

    Returns:
        JSON with:
        - mode: enabled/disabled/manual
        - policy: conservative/balanced/aggressive
        - is_running: True if monitoring loop active
        - current_limits: Current resource limits
        - last_scale_time: ISO timestamp of last scale action
        - scale_up_count: Consecutive scale-up triggers
        - scale_down_count: Consecutive scale-down triggers

    Example:
        status = autoscaler_get_status()
        # Check if autoscaler is enabled
        if status["mode"] == "enabled":
            # View current limits
            print(status["current_limits"])
    """
    autoscaler = get_autoscaler()
    return autoscaler.get_status()


@mcp.tool()
def autoscaler_get_metrics() -> str:
    """Get current resource usage metrics from cgroup.

    Returns real-time CPU, memory, and process usage.

    Returns:
        JSON with:
        - timestamp: ISO timestamp of measurement
        - cpu_percent: CPU usage percentage
        - cpu_cores_used: CPU cores in use
        - memory_gb: Memory usage in GB
        - process_count: Process count
        - agent_count: Number of coding agents running
        - testing_agent_count: Number of testing agents running
        - api_quota_remaining: Remaining API quota
        - features_pending: Number of features pending

    Example:
        metrics = autoscaler_get_metrics()

        # Check if we're approaching limits
        if metrics["cpu_percent"] > 80:
            print("WARNING: CPU usage high")

        # Check memory pressure
        if metrics["memory_gb"] > 24:
            print("WARNING: Memory usage high")
    """
    try:
        monitor = get_resource_monitor()
        metrics = monitor.collect_metrics()

        return {
            "timestamp": metrics.timestamp.isoformat(),
            "cpu_percent": metrics.cpu_percent,
            "cpu_cores_used": metrics.cpu_cores_used,
            "memory_gb": metrics.memory_gb,
            "process_count": metrics.process_count,
            "agent_count": metrics.agent_count,
            "testing_agent_count": metrics.testing_agent_count,
            "api_quota_remaining": metrics.api_quota_remaining,
            "features_pending": metrics.features_pending,
        }
    except RuntimeError as e:
        return {
            "error": f"Resource monitor not available: {e}"
        }


@mcp.tool()
def autoscaler_get_history(limit: int = 20) -> str:
    """Get history of scaling actions.

    Shows when and why the autoscaler scaled resources.

    Args:
        limit: Maximum number of entries to return (default: 20, max: 100)

    Returns:
        JSON list of scaling actions with:
        - timestamp: ISO timestamp
        - action: scale_up, scale_down, manual, emergency_stop
        - trigger_type: threshold, prediction, queue, manual, emergency
        - reason: Human-readable explanation
        - old_limits: Limits before scaling
        - new_limits: Limits after scaling
        - status: success, failed, rolled_back
        - error_message: Error details if failed

    Example:
        history = autoscaler_get_history(limit=10)

        for action in history:
            print(f"{action['timestamp']}: {action['action']}")
            print(f"  Reason: {action['reason']}")
            print(f"  {action['old_limits']} -> {action['new_limits']}")
    """
    import sqlite3
    from pathlib import Path

    AUTOSCALER_DB = Path.home() / ".autocoder" / "autoscaler.db"
    limit = max(1, min(limit, 100))

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
            history.append({
                "id": row[0],
                "timestamp": row[1],
                "action": row[2],
                "trigger_type": row[3],
                "reason": row[4],
                "old_limits": {
                    "cpu_quota": row[5],
                    "memory_max": row[6],
                    "tasks_max": row[7],
                },
                "new_limits": {
                    "cpu_quota": row[8],
                    "memory_max": row[9],
                    "tasks_max": row[10],
                },
                "status": row[11],
                "error_message": row[12],
            })

        return history
    finally:
        conn.close()


@mcp.tool()
def autoscaler_get_config() -> str:
    """Get current autoscaler configuration.

    Returns all thresholds, limits, and settings.

    Returns:
        JSON with:
        - mode: enabled/disabled/manual
        - policy: conservative/balanced/aggressive
        - scale_up_*: Thresholds for scaling up
        - scale_down_*: Thresholds for scaling down
        - check_interval_seconds: How often to check metrics
        - scale_cooldown_seconds: Minimum time between scales
        - *_factor: Multipliers for scaling
        - min_*: Minimum resource limits
        - max_*: Maximum resource limits
        - system_*: Reserved system resources

    Example:
        config = autoscaler_get_config()

        # Check scale-up thresholds
        print(f"CPU threshold: {config['scale_up_cpu_percent']}%")
        print(f"Memory threshold: {config['scale_up_memory_percent']}%")
    """
    config = AutoscalerConfig.load()

    return {
        "mode": config.mode.value,
        "policy": config.policy.value,
        "scale_up_cpu_percent": config.scale_up_cpu_percent,
        "scale_up_memory_percent": config.scale_up_memory_percent,
        "scale_up_tasks_percent": config.scale_up_tasks_percent,
        "scale_down_cpu_percent": config.scale_down_cpu_percent,
        "scale_down_memory_percent": config.scale_down_memory_percent,
        "scale_down_tasks_percent": config.scale_down_tasks_percent,
        "check_interval_seconds": config.check_interval_seconds,
        "scale_cooldown_seconds": config.scale_cooldown_seconds,
        "consecutive_scale_up_checks": config.consecutive_scale_up_checks,
        "consecutive_scale_down_checks": config.consecutive_scale_down_checks,
        "scale_up_factor": config.scale_up_factor,
        "scale_down_factor": config.scale_down_factor,
        "min_cpu_quota": config.min_cpu_quota,
        "max_cpu_quota": config.max_cpu_quota,
        "min_memory_max": config.min_memory_max,
        "max_memory_max": config.max_memory_max,
        "min_tasks_max": config.min_tasks_max,
        "max_tasks_max": config.max_tasks_max,
        "system_cpu_cores": config.system_cpu_cores,
        "system_memory_gb": config.system_memory_gb,
        "system_processes": config.system_processes,
    }


@mcp.tool()
def autoscaler_set_config(
    scale_up_cpu_percent: int | None = None,
    scale_up_memory_percent: int | None = None,
    scale_up_tasks_percent: int | None = None,
    scale_down_cpu_percent: int | None = None,
    scale_down_memory_percent: int | None = None,
    scale_down_tasks_percent: int | None = None,
    check_interval_seconds: int | None = None,
    scale_cooldown_seconds: int | None = None,
    consecutive_scale_up_checks: int | None = None,
    consecutive_scale_down_checks: int | None = None,
    scale_up_factor: float | None = None,
    scale_down_factor: float | None = None
) -> str:
    """Update autoscaler configuration thresholds.

    All parameters are optional - only provide the ones you want to change.

    Args:
        scale_up_cpu_percent: CPU threshold for scale-up (50-100, default: 85)
        scale_up_memory_percent: Memory threshold for scale-up (50-100, default: 80)
        scale_up_tasks_percent: Tasks threshold for scale-up (50-100, default: 85)
        scale_down_cpu_percent: CPU threshold for scale-down (10-80, default: 40)
        scale_down_memory_percent: Memory threshold for scale-down (10-80, default: 50)
        scale_down_tasks_percent: Tasks threshold for scale-down (10-80, default: 30)
        check_interval_seconds: Metrics polling interval (10-300, default: 30)
        scale_cooldown_seconds: Minimum time between scales (60-3600, default: 300)
        consecutive_scale_up_checks: Required breaches for scale-up (1-10, default: 3)
        consecutive_scale_down_checks: Required breaches for scale-down (1-20, default: 10)
        scale_up_factor: Multiplier for scale-up (1.1-3.0, default: 1.5)
        scale_down_factor: Multiplier for scale-down (0.3-0.9, default: 0.6)

    Returns:
        JSON with updated configuration

    Example:
        # Make scale-up more aggressive
        autoscaler_set_config(
            scale_up_cpu_percent=75,
            consecutive_scale_up_checks=2,
            scale_cooldown_seconds=120
        )

        # Make scale-down more conservative
        autoscaler_set_config(
            scale_down_cpu_percent=30,
            consecutive_scale_down_checks=15
        )
    """
    config = AutoscalerConfig.load()

    # Update only provided fields
    if scale_up_cpu_percent is not None:
        config.scale_up_cpu_percent = max(50, min(100, scale_up_cpu_percent))
    if scale_up_memory_percent is not None:
        config.scale_up_memory_percent = max(50, min(100, scale_up_memory_percent))
    if scale_up_tasks_percent is not None:
        config.scale_up_tasks_percent = max(50, min(100, scale_up_tasks_percent))
    if scale_down_cpu_percent is not None:
        config.scale_down_cpu_percent = max(10, min(80, scale_down_cpu_percent))
    if scale_down_memory_percent is not None:
        config.scale_down_memory_percent = max(10, min(80, scale_down_memory_percent))
    if scale_down_tasks_percent is not None:
        config.scale_down_tasks_percent = max(10, min(80, scale_down_tasks_percent))
    if check_interval_seconds is not None:
        config.check_interval_seconds = max(10, min(300, check_interval_seconds))
    if scale_cooldown_seconds is not None:
        config.scale_cooldown_seconds = max(60, min(3600, scale_cooldown_seconds))
    if consecutive_scale_up_checks is not None:
        config.consecutive_scale_up_checks = max(1, min(10, consecutive_scale_up_checks))
    if consecutive_scale_down_checks is not None:
        config.consecutive_scale_down_checks = max(1, min(20, consecutive_scale_down_checks))
    if scale_up_factor is not None:
        config.scale_up_factor = max(1.1, min(3.0, scale_up_factor))
    if scale_down_factor is not None:
        config.scale_down_factor = max(0.3, min(0.9, scale_down_factor))

    # Save configuration
    success = config.save()

    if not success:
        return {
            "success": False,
            "error": "Failed to save configuration to database"
        }

    # Reload autoscaler config
    autoscaler = get_autoscaler()
    autoscaler.config = config

    return {
        "success": True,
        "config": {
            "scale_up_cpu_percent": config.scale_up_cpu_percent,
            "scale_up_memory_percent": config.scale_up_memory_percent,
            "scale_up_tasks_percent": config.scale_up_tasks_percent,
            "scale_down_cpu_percent": config.scale_down_cpu_percent,
            "scale_down_memory_percent": config.scale_down_memory_percent,
            "scale_down_tasks_percent": config.scale_down_tasks_percent,
            "check_interval_seconds": config.check_interval_seconds,
            "scale_cooldown_seconds": config.scale_cooldown_seconds,
            "consecutive_scale_up_checks": config.consecutive_scale_up_checks,
            "consecutive_scale_down_checks": config.consecutive_scale_down_checks,
            "scale_up_factor": config.scale_up_factor,
            "scale_down_factor": config.scale_down_factor,
        }
    }


@mcp.tool()
def autoscaler_get_prediction() -> str:
    """Get predicted future resource needs (Phase 2+ feature).

    NOTE: This is a placeholder for Phase 2 (trend-based) and Phase 3 (ML-powered).
    Currently returns basic metrics and trend information.

    In future phases, this will provide:
    - Predicted CPU/memory usage at t+5min, t+15min
    - Trend analysis (increasing/decreasing/stable)
    - Confidence intervals
    - Scaling recommendations

    Returns:
        JSON with current metrics and placeholder prediction fields

    Example:
        prediction = autoscaler_get_prediction()

        # Current metrics (available now)
        print(f"Current CPU: {prediction['current']['cpu_percent']}%")

        # Future predictions (Phase 2+)
        # print(f"Predicted CPU (5min): {prediction['prediction_5min']['cpu_percent']}%")
    """
    try:
        monitor = get_resource_monitor()
        metrics = monitor.collect_metrics()

        return {
            "current": {
                "cpu_percent": metrics.cpu_percent,
                "memory_gb": metrics.memory_gb,
                "process_count": metrics.process_count,
                "timestamp": metrics.timestamp.isoformat(),
            },
            "prediction_5min": {
                "cpu_percent": None,  # Phase 2: Trend-based prediction
                "memory_gb": None,
                "confidence": None,
            },
            "prediction_15min": {
                "cpu_percent": None,  # Phase 3: ML-powered prediction
                "memory_gb": None,
                "confidence": None,
            },
            "trend": {
                "direction": None,  # Phase 2: increasing, decreasing, stable
                "strength": None,   # Phase 2: weak, moderate, strong
            },
            "recommendation": {
                "action": None,  # Phase 2: scale_up, scale_down, hold
                "reason": "Prediction features coming in Phase 2 (trend-based) and Phase 3 (ML-powered)",
            }
        }
    except RuntimeError as e:
        return {
            "error": f"Resource monitor not available: {e}"
        }


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
