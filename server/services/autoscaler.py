"""
AutoScaler Service
==================

Intelligent resource autoscaling service for AutoCoder.

Monitors resource usage and automatically adjusts systemd service limits
(CPU quota, memory, process count) based on workload patterns.

Features:
- Threshold-based scaling (MVP)
- Trend-aware scaling (Phase 2)
- Predictive scaling with ML (Phase 3)
- Graceful degradation with rollback
- Manual override support
"""

import asyncio
import os
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..utils.resource_monitor import ResourceMetrics


# Configuration
AUTOSCALER_DB = Path.home() / ".autocoder" / "autoscaler.db"
AUTOSCALER_DB.parent.mkdir(parents=True, exist_ok=True)


class ScalingMode(str, Enum):
    """Autoscaler operational mode."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    MANUAL = "manual"


class ScalingPolicy(str, Enum):
    """Autoscaling policy profiles."""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


@dataclass
class ScalingAction:
    """Represents a scaling action that was taken."""
    timestamp: datetime
    action: str  # scale_up, scale_down, none, manual, emergency_stop
    trigger_type: str  # threshold, prediction, queue, manual, emergency
    reason: str
    old_limits: dict
    new_limits: dict
    status: str  # success, failed, rolled_back
    error_message: Optional[str] = None


@dataclass
class AutoscalerConfig:
    """Autoscaler configuration."""
    mode: ScalingMode = ScalingMode.ENABLED
    policy: ScalingPolicy = ScalingPolicy.BALANCED

    # Threshold triggers
    scale_up_cpu_percent: int = 85
    scale_up_memory_percent: int = 80
    scale_up_tasks_percent: int = 85

    scale_down_cpu_percent: int = 40
    scale_down_memory_percent: int = 50
    scale_down_tasks_percent: int = 30

    # Timing
    check_interval_seconds: int = 30
    scale_cooldown_seconds: int = 300  # 5 minutes

    # Consecutive checks required
    consecutive_scale_up_checks: int = 3
    consecutive_scale_down_checks: int = 10

    # Scale factors
    scale_up_factor: float = 1.5
    scale_down_factor: float = 0.6

    # Hard limits
    min_cpu_quota: int = 100  # 1 core
    max_cpu_quota: int = 800  # 8 cores
    min_memory_max: int = 8    # 8GB
    max_memory_max: int = 192  # 192GB
    min_tasks_max: int = 100
    max_tasks_max: int = 1500

    # System reserves
    system_cpu_cores: int = 1
    system_memory_gb: int = 8
    system_processes: int = 50

    @classmethod
    def load(cls) -> "AutoscalerConfig":
        """Load configuration from database."""
        conn = sqlite3.connect(AUTOSCALER_DB)
        try:
            cursor = conn.execute(
                "SELECT * FROM autoscaler_config WHERE id = 1"
            )
            row = cursor.fetchone()
            if row:
                return cls(
                    mode=ScalingMode(row[1] or "enabled"),
                    policy=ScalingPolicy(row[2] or "balanced"),
                    scale_up_cpu_percent=row[3] or 85,
                    scale_up_memory_percent=row[4] or 80,
                    scale_up_tasks_percent=row[5] or 85,
                    scale_down_cpu_percent=row[6] or 40,
                    scale_down_memory_percent=row[7] or 50,
                    scale_down_tasks_percent=row[8] or 30,
                    check_interval_seconds=row[9] or 30,
                    scale_cooldown_seconds=row[10] or 300,
                    consecutive_scale_up_checks=row[11] or 3,
                    consecutive_scale_down_checks=row[12] or 10,
                    scale_up_factor=row[13] or 1.5,
                    scale_down_factor=row[14] or 0.6,
                    min_cpu_quota=row[15] or 100,
                    max_cpu_quota=row[16] or 800,
                    min_memory_max=row[17] or 8,
                    max_memory_max=row[18] or 192,
                    min_tasks_max=row[19] or 100,
                    max_tasks_max=row[20] or 1500,
                    system_cpu_cores=row[21] or 1,
                    system_memory_gb=row[22] or 8,
                    system_processes=row[23] or 50,
                )
        finally:
            conn.close()

        # Return defaults if not configured
        return cls()

    def save(self) -> bool:
        """Save configuration to database."""
        conn = sqlite3.connect(AUTOSCALER_DB)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO autoscaler_config
                (id, mode, policy,
                 scale_up_cpu_percent, scale_up_memory_percent, scale_up_tasks_percent,
                 scale_down_cpu_percent, scale_down_memory_percent, scale_down_tasks_percent,
                 check_interval_seconds, scale_cooldown_seconds,
                 consecutive_scale_up_checks, consecutive_scale_down_checks,
                 scale_up_factor, scale_down_factor,
                 min_cpu_quota, max_cpu_quota,
                 min_memory_max, max_memory_max,
                 min_tasks_max, max_tasks_max,
                 system_cpu_cores, system_memory_gb, system_processes)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.mode.value,
                    self.policy.value,
                    self.scale_up_cpu_percent,
                    self.scale_up_memory_percent,
                    self.scale_up_tasks_percent,
                    self.scale_down_cpu_percent,
                    self.scale_down_memory_percent,
                    self.scale_down_tasks_percent,
                    self.check_interval_seconds,
                    self.scale_cooldown_seconds,
                    self.consecutive_scale_up_checks,
                    self.consecutive_scale_down_checks,
                    self.scale_up_factor,
                    self.scale_down_factor,
                    self.min_cpu_quota,
                    self.max_cpu_quota,
                    self.min_memory_max,
                    self.max_memory_max,
                    self.min_tasks_max,
                    self.max_tasks_max,
                    self.system_cpu_cores,
                    self.system_memory_gb,
                    self.system_processes,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to save autoscaler config: {e}")
            return False
        finally:
            conn.close()


class ThresholdScaler:
    """
    Threshold-based autoscaler (MVP implementation).

    Scales resources when usage thresholds are breached for consecutive checks.
    Implements hysteresis to prevent thrashing.
    """

    def __init__(self, config: AutoscalerConfig):
        self.config = config
        self.scale_up_count = 0
        self.scale_down_count = 0
        self.last_scale_time: Optional[datetime] = None
        self.metrics_history = []

    def check_metrics(self, metrics: ResourceMetrics) -> Optional[str]:
        """
        Check metrics and determine if scaling is needed.

        Args:
            metrics: Current resource metrics

        Returns:
            "scale_up", "scale_down", or None
        """
        # Check scale UP conditions
        scale_up = (
            metrics.cpu_percent > self.config.scale_up_cpu_percent or
            metrics.memory_gb > (self.config.max_memory_max * self.config.scale_up_memory_percent / 100) or
            (metrics.process_count / self.config.max_tasks_max * 100) > self.config.scale_up_tasks_percent
        )

        if scale_up:
            self.scale_up_count += 1
            if self.scale_up_count >= self.config.consecutive_scale_up_checks:
                return "scale_up"
        else:
            self.scale_up_count = 0

        # Check scale DOWN conditions (all must be true)
        scale_down = (
            metrics.cpu_percent < self.config.scale_down_cpu_percent and
            metrics.memory_gb < (self.config.max_memory_max * self.config.scale_down_memory_percent / 100) and
            (metrics.process_count / self.config.max_tasks_max * 100) < self.config.scale_down_tasks_percent
        )

        if scale_down:
            self.scale_down_count += 1
            if self.scale_down_count >= self.config.consecutive_scale_down_checks:
                return "scale_down"
        else:
            self.scale_down_count = 0

        return None

    def calculate_new_limits(self, current_limits: dict, direction: str) -> dict:
        """
        Calculate new resource limits based on current usage.

        Args:
            current_limits: Current {cpu_quota, memory_max, tasks_max}
            direction: "scale_up" or "scale_down"

        Returns:
            New limits dict
        """
        current_cpu = current_limits["cpu_quota"]
        current_memory = current_limits["memory_max"]
        current_tasks = current_limits["tasks_max"]

        if direction == "scale_up":
            # Scale UP with headroom
            new_cpu = int(current_cpu * self.config.scale_up_factor)
            new_memory = int(current_memory * 1.25)  # Less aggressive memory scaling
            new_tasks = int(current_tasks * self.config.scale_up_factor)

        elif direction == "scale_down":
            # Scale DOWN
            new_cpu = int(current_cpu * self.config.scale_down_factor)
            new_memory = int(current_memory * self.config.scale_down_factor)
            new_tasks = int(current_tasks * self.config.scale_down_factor)

        else:
            return current_limits

        # Enforce hard limits
        new_cpu = max(self.config.min_cpu_quota, min(new_cpu, self.config.max_cpu_quota))
        new_memory = max(self.config.min_memory_max, min(new_memory, self.config.max_memory_max))
        new_tasks = max(self.config.min_tasks_max, min(new_tasks, self.config.max_tasks_max))

        # Round to nice numbers
        new_cpu = round_to_nearest(new_cpu, 50)
        new_memory = round_to_nearest(new_memory, 8)
        new_tasks = round_to_nearest(new_tasks, 50)

        return {
            "cpu_quota": new_cpu,
            "memory_max": new_memory,
            "tasks_max": new_tasks,
        }


def round_to_nearest(value: int, multiple: int) -> int:
    """Round value to nearest multiple."""
    return ((value + multiple // 2) // multiple) * multiple


class AutoScaler:
    """
    Main autoscaling service.

    Orchestrates resource monitoring, threshold evaluation, and limit updates.
    """

    def __init__(self):
        self.is_running = False
        self.current_limits = {}
        self.last_scale_time = None  # Track last scaling action
        self._init_db()  # Initialize database FIRST
        self.config = AutoscalerConfig.load()  # THEN load config
        self.scaler = ThresholdScaler(self.config)

    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(AUTOSCALER_DB)
        try:
            # Config table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS autoscaler_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    mode TEXT DEFAULT 'enabled',
                    policy TEXT DEFAULT 'balanced',
                    scale_up_cpu_percent INTEGER DEFAULT 85,
                    scale_up_memory_percent INTEGER DEFAULT 80,
                    scale_up_tasks_percent INTEGER DEFAULT 85,
                    scale_down_cpu_percent INTEGER DEFAULT 40,
                    scale_down_memory_percent INTEGER DEFAULT 50,
                    scale_down_tasks_percent INTEGER DEFAULT 30,
                    check_interval_seconds INTEGER DEFAULT 30,
                    scale_cooldown_seconds INTEGER DEFAULT 300,
                    consecutive_scale_up_checks INTEGER DEFAULT 3,
                    consecutive_scale_down_checks INTEGER DEFAULT 10,
                    scale_up_factor REAL DEFAULT 1.5,
                    scale_down_factor REAL DEFAULT 0.6,
                    min_cpu_quota INTEGER DEFAULT 100,
                    max_cpu_quota INTEGER DEFAULT 800,
                    min_memory_max INTEGER DEFAULT 8,
                    max_memory_max INTEGER DEFAULT 192,
                    min_tasks_max INTEGER DEFAULT 100,
                    max_tasks_max INTEGER DEFAULT 1500,
                    system_cpu_cores INTEGER DEFAULT 1,
                    system_memory_gb INTEGER DEFAULT 8,
                    system_processes INTEGER DEFAULT 50
                )
            """)

            # Metrics history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS autoscaler_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    cpu_percent REAL NOT NULL,
                    memory_gb REAL NOT NULL,
                    process_count INTEGER NOT NULL,
                    agent_count INTEGER NOT NULL,
                    testing_agent_count INTEGER NOT NULL,
                    api_quota_remaining INTEGER NOT NULL,
                    features_pending INTEGER NOT NULL
                )
            """)

            # Scale history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS autoscaler_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    action TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    old_cpu_quota INTEGER NOT NULL,
                    old_memory_max INTEGER NOT NULL,
                    old_tasks_max INTEGER NOT NULL,
                    new_cpu_quota INTEGER NOT NULL,
                    new_memory_max INTEGER NOT NULL,
                    new_tasks_max INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT
                )
            """)

            # Insert default config if not exists
            conn.execute(
                "INSERT OR IGNORE INTO autoscaler_config (id) VALUES (1)"
            )

            conn.commit()
        finally:
            conn.close()

    def get_current_limits(self) -> dict:
        """Get current resource limits from systemd service file."""
        try:
            from server.routers.systemd import SERVICE_FILE

            if not SERVICE_FILE.exists():
                return {
                    "cpu_quota": 200,
                    "memory_max": 32,
                    "tasks_max": 250,
                }

            content = SERVICE_FILE.read_text()
            import re

            # Parse CPUQuota
            match = re.search(r'CPUQuota=(\d+)%', content)
            cpu_quota = int(match.group(1)) if match else 200

            # Parse MemoryMax
            match = re.search(r'MemoryMax=(\d+)G?', content)
            memory_max = int(match.group(1)) if match else 32

            # Parse TasksMax
            match = re.search(r'TasksMax=(\d+)', content)
            tasks_max = int(match.group(1)) if match else 250

            return {
                "cpu_quota": cpu_quota,
                "memory_max": memory_max,
                "tasks_max": tasks_max,
            }

        except Exception as e:
            print(f"Error reading limits: {e}")
            return {
                "cpu_quota": 200,
                "memory_max": 32,
                "tasks_max": 250,
            }

    async def update_limits(self, new_limits: dict) -> bool:
        """
        Update systemd service file with new resource limits.

        Args:
            new_limits: Dict with cpu_quota, memory_max, tasks_max

        Returns:
            True if successful, False otherwise
        """
        try:
            from server.routers.systemd import SERVICE_FILE

            # Backup current file
            backup_file = SERVICE_FILE.with_suffix('.service.backup')
            backup_file.write_text(SERVICE_FILE.read_text())

            # Read and update content
            content = SERVICE_FILE.read_text()

            # Update CPUQuota
            content = re.sub(
                r'CPUQuota=\d+%',
                f'CPUQuota={new_limits["cpu_quota"]}%',
                content
            )

            # Update MemoryMax
            content = re.sub(
                r'MemoryMax=\d+G?',
                f'MemoryMax={new_limits["memory_max"]}G',
                content
            )

            # Update TasksMax
            content = re.sub(
                r'TasksMax=\d+',
                f'TasksMax={new_limits["tasks_max"]}',
                content
            )

            # Write updated file
            SERVICE_FILE.write_text(content)

            # Reload systemd and restart service
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                check=True,
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["systemctl", "--user", "restart", "autocoder-ui.service"],
                check=True,
                capture_output=True,
                timeout=30,
            )

            return True

        except Exception as e:
            print(f"Failed to update limits: {e}")

            # Rollback
            try:
                if backup_file.exists():
                    backup_file.rename(SERVICE_FILE)
            except Exception:
                pass

            return False

    def log_action(self, action: ScalingAction):
        """Log a scaling action to database."""
        conn = sqlite3.connect(AUTOSCALER_DB)
        try:
            conn.execute(
                """
                INSERT INTO autoscaler_history
                (timestamp, action, trigger_type, reason,
                 old_cpu_quota, old_memory_max, old_tasks_max,
                 new_cpu_quota, new_memory_max, new_tasks_max,
                 status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.timestamp,
                    action.action,
                    action.trigger_type,
                    action.reason,
                    action.old_limits["cpu_quota"],
                    action.old_limits["memory_max"],
                    action.old_limits["tasks_max"],
                    action.new_limits["cpu_quota"],
                    action.new_limits["memory_max"],
                    action.new_limits["tasks_max"],
                    action.status,
                    action.error_message,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def should_scale(self) -> bool:
        """
        Check if scaling is allowed (cooldown period passed).

        Returns:
            True if scaling is allowed, False if in cooldown
        """
        if self.last_scale_time is None:
            return True

        elapsed = (datetime.utcnow() - self.last_scale_time).total_seconds()
        return elapsed >= self.config.scale_cooldown_seconds

    async def run_monitoring_loop(self):
        """
        Main monitoring loop - runs indefinitely.

        Polls metrics, checks thresholds, executes scaling actions.
        """
        from server.utils.resource_monitor import get_resource_monitor

        try:
            monitor = get_resource_monitor()

            while self.is_running:
                # Collect metrics (TODO: get agent counts from orchestrator)
                metrics = monitor.collect_metrics(
                    agent_count=0,  # TODO: Get from parallel_orchestrator
                    testing_agent_count=0,
                    api_quota_remaining=0,  # TODO: Get from quota_budget
                    features_pending=0,  # TODO: Get from features db
                )

                # Store metrics in database
                conn = sqlite3.connect(AUTOSCALER_DB)
                try:
                    conn.execute(
                        """
                        INSERT INTO autoscaler_metrics
                        (timestamp, cpu_percent, memory_gb, process_count,
                         agent_count, testing_agent_count, api_quota_remaining, features_pending)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            metrics.timestamp,
                            metrics.cpu_percent,
                            metrics.memory_gb,
                            metrics.process_count,
                            metrics.agent_count,
                            metrics.testing_agent_count,
                            metrics.api_quota_remaining,
                            metrics.features_pending,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

                # Check if we should scale
                if self.config.mode == ScalingMode.ENABLED and self.should_scale():
                    self.current_limits = self.get_current_limits()

                    # Check thresholds
                    direction = self.scaler.check_metrics(metrics)

                    if direction and self.should_scale():
                        # Calculate new limits
                        new_limits = self.scaler.calculate_new_limits(
                            self.current_limits,
                            direction
                        )

                        # Execute scaling action
                        old_limits = self.current_limits.copy()

                        success = await self.update_limits(new_limits)

                        # Log the action
                        action = ScalingAction(
                            timestamp=datetime.utcnow(),
                            action=direction,
                            trigger_type="threshold",
                            reason=f"Thresholds breached: CPU={metrics.cpu_percent:.1f}%, "
                                   f"Memory={metrics.memory_gb:.1f}GB, "
                                   f"Processes={metrics.process_count}",
                            old_limits=old_limits,
                            new_limits=new_limits,
                            status="success" if success else "failed",
                            error_message=None if success else "Service restart failed",
                        )

                        self.log_action(action)

                        if success:
                            self.current_limits = new_limits
                            self.last_scale_time = datetime.utcnow()

                        # Reset counters
                        self.scaler.scale_up_count = 0
                        self.scaler.scale_down_count = 0

                # Wait for next check
                await asyncio.sleep(self.config.check_interval_seconds)

        except asyncio.CancelledError:
            print("Autoscaler monitoring loop cancelled")
        except Exception as e:
            print(f"Error in monitoring loop: {e}")
            await asyncio.sleep(self.config.check_interval_seconds)

    def start(self):
        """Start the autoscaler service."""
        if self.is_running:
            return False

        self.is_running = True
        return True

    def stop(self):
        """Stop the autoscaler service."""
        self.is_running = False
        return True

    def set_mode(self, mode: ScalingMode) -> bool:
        """Set the operational mode."""
        self.config.mode = mode
        return self.config.save()

    def set_policy(self, policy: ScalingPolicy) -> bool:
        """Set the scaling policy."""
        self.config.policy = policy
        # Adjust thresholds based on policy
        if policy == ScalingPolicy.CONSERVATIVE:
            self.config.scale_up_cpu_percent = 90
            self.config.scale_up_memory_percent = 85
            self.config.consecutive_scale_up_checks = 5
            self.config.scale_cooldown_seconds = 600
            self.config.scale_up_factor = 1.3
        elif policy == ScalingPolicy.AGGRESSIVE:
            self.config.scale_up_cpu_percent = 75
            self.config.scale_up_memory_percent = 70
            self.config.consecutive_scale_up_checks = 2
            self.config.scale_cooldown_seconds = 120
            self.config.scale_up_factor = 2.0
        else:  # BALANCED
            self.config.scale_up_cpu_percent = 85
            self.config.scale_up_memory_percent = 80
            self.config.consecutive_scale_up_checks = 3
            self.config.scale_cooldown_seconds = 300
            self.config.scale_up_factor = 1.5

        return self.config.save()

    def get_status(self) -> dict:
        """Get current autoscaler status."""
        return {
            "mode": self.config.mode.value,
            "policy": self.config.policy.value,
            "is_running": self.is_running,
            "current_limits": self.get_current_limits(),
            "last_scale_time": self.last_scale_time.isoformat() if self.last_scale_time else None,
            "scale_up_count": self.scaler.scale_up_count,
            "scale_down_count": self.scaler.scale_down_count,
        }


# Singleton instance
_global_autoscaler: Optional[AutoScaler] = None


def get_autoscaler() -> AutoScaler:
    """
    Get global AutoScaler singleton.

    Returns:
        AutoScaler instance
    """
    global _global_autoscaler

    if _global_autoscaler is None:
        _global_autoscaler = AutoScaler()

    return _global_autoscaler
