"""
Resource Monitor - Cgroup Metrics Collector
============================================

Collects real-time system resource usage from cgroup v2 for autoscaling.
Reads CPU, memory, and process metrics from /sys/fs/cgroup/.

This module provides the data foundation for all autoscaling decisions.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil


@dataclass
class ResourceMetrics:
    """Snapshot of current resource usage."""
    timestamp: datetime
    cpu_percent: float
    cpu_cores_used: float
    memory_gb: float
    process_count: int
    agent_count: int = 0
    testing_agent_count: int = 0
    api_quota_remaining: int = 0
    features_pending: int = 0


class ResourceMonitor:
    """
    Collects resource usage metrics from cgroup v2.

    Polls cgroup files for CPU, memory, and process counts.
    """

    # cgroup v2 paths
    CGROUP_PATH = Path("/sys/fs/cgroup")

    # Service name to find our cgroup
    SERVICE_NAME = "autocoder-ui.service"

    def __init__(self):
        """Initialize the resource monitor."""
        self.cgroup_path = self._find_cgroup()
        if not self.cgroup_path:
            raise RuntimeError(
                f"Could not find cgroup for {self.SERVICE_NAME}. "
                "Is the service running?"
            )

    def _find_cgroup(self) -> Optional[Path]:
        """
        Find the cgroup path for autocoder-ui.service.

        Searches through /sys/fs/cgroup for the service cgroup.
        """
        try:
            # Search for service name in cgroup paths
            for cgroup_file in self.CGROUP_PATH.rglob("*"):
                if self.SERVICE_NAME in str(cgroup_file):
                    # Found it - return the directory
                    if cgroup_file.is_dir():
                        return cgroup_file
                    # Otherwise it's a file, check parent
                    return cgroup_file.parent
        except Exception:
            pass

        return None

    def read_memory_current(self) -> float:
        """
        Read current memory usage in GB from cgroup.

        Returns:
            Memory usage in GB
        """
        if not self.cgroup_path:
            return 0.0

        try:
            # Try cgroup v2 first
            memory_file = self.cgroup_path / "memory.current"
            if memory_file.exists():
                bytes_used = int(memory_file.read_text().strip())
                return bytes_used / (1024**3)  # Convert to GB
            else:
                # Fallback to v1 path
                usage_file = self.cgroup_path / "memory.usage_in_bytes"
                if usage_file.exists():
                    bytes_used = int(usage_file.read_text().strip())
                    return bytes_used / (1024**3)
        except Exception:
            pass

        return 0.0

    def read_memory_max(self) -> float:
        """
        Read memory limit in GB from cgroup.

        Returns:
            Memory limit in GB
        """
        if not self.cgroup_path:
            return 32.0  # Default from service file

        try:
            # Try cgroup v2 first
            max_file = self.cgroup_path / "memory.max"
            if max_file.exists():
                max_str = max_file.read_text().strip()
                if max_str == "max":
                    return 251.0  # No limit (system total)
                else:
                    max_bytes = int(max_str)
                    return max_bytes / (1024**3)
            else:
                # Fallback to v1 path
                limit_file = self.cgroup_path / "memory.limit_in_bytes"
                if limit_file.exists():
                    max_bytes = int(limit_file.read_text().strip())
                    return max_bytes / (1024**3)
        except Exception:
            pass

        return 32.0  # Default fallback

    def read_cpu_stat(self) -> tuple[float, int]:
        """
        Read CPU usage and throttle from cgroup.

        Returns:
            (cpu_usage_percent, cpu_quota_percent)
        """
        if not self.cgroup_path:
            return psutil.cpu_percent(interval=0.5), 200

        try:
            # Read CPU usage
            cpu_stat = self.cgroup_path / "cpu.stat"
            if cpu_stat.exists():
                content = cpu_stat.read_text().strip()
                # Parse: usage_usec user_usec system_usec
                parts = content.split()
                if len(parts) >= 2:
                    usage_usec = int(parts[0])
                    total_usec = usage_usec + int(parts[1])
                    if total_usec > 0:
                        cpu_usage = (usage_usec / total_usec) * 100
                    else:
                        cpu_usage = 0.0
                else:
                    cpu_usage = 0.0
            else:
                cpu_usage = psutil.cpu_percent(interval=0.5)

            # Read CPU quota (if set)
            cpu_quota = None
            quota_file = self.cgroup_path / "cpu.max"
            if quota_file.exists():
                quota_str = quota_file.read_text().strip()
                if quota_str == "max":
                    cpu_quota = 100 * 100  # No limit (all cores)
                else:
                    cpu_quota = int(quota_str)
            else:
                cpu_quota = 200  # Default from service file

            return cpu_usage, cpu_quota

        except Exception:
            return psutil.cpu_percent(interval=0.5), 200

    def read_process_count(self) -> int:
        """
        Read current process count from cgroup.

        Returns:
            Number of processes in cgroup
        """
        if not self.cgroup_path:
            # Fallback: count all Python processes
            try:
                return len([
                    p for p in psutil.process_iter(['name'])
                    if p.info['name'] in ['python', 'python3', 'uvicorn']
                ])
            except Exception:
                return 0

        try:
            # Try cgroup v2
            pids_file = self.cgroup_path / "cgroup.procs"
            if pids_file.exists():
                pids = pids_file.read_text().strip().split('\n')
                return len([p for p in pids if p.strip()])
            else:
                # Fallback to psutil
                return len([
                    p for p in psutil.process_iter(['name'])
                    if p.info['name'] in ['python', 'python3', 'uvicorn']
                ])
        except Exception:
            return 0

    def collect_metrics(self,
                       agent_count: int = 0,
                       testing_agent_count: int = 0,
                       api_quota_remaining: int = 0,
                       features_pending: int = 0) -> ResourceMetrics:
        """
        Collect a complete snapshot of resource metrics.

        Args:
            agent_count: Current number of coding agents running
            testing_agent_count: Current number of testing agents running
            api_quota_remaining: Remaining API quota prompts
            features_pending: Number of features pending

        Returns:
            ResourceMetrics snapshot
        """
        cpu_usage, cpu_quota = self.read_cpu_stat()
        memory_current = self.read_memory_current()
        process_count = self.read_process_count()

        return ResourceMetrics(
            timestamp=datetime.utcnow(),
            cpu_percent=cpu_usage,
            cpu_cores_used=cpu_quota / 100,  # Convert % to cores
            memory_gb=memory_current,
            process_count=process_count,
            agent_count=agent_count,
            testing_agent_count=testing_agent_count,
            api_quota_remaining=api_quota_remaining,
            features_pending=features_pending,
        )

    def get_system_totals(self) -> dict:
        """
        Get total system resources (entire machine).

        Returns:
            Dict with total CPU cores and memory
        """
        return {
            "cpu_cores_total": psutil.cpu_count(logical=False),
            "memory_gb_total": psutil.virtual_memory().total / (1024**3),
        }


async def monitoring_loop(monitor: ResourceMonitor,
                        interval_seconds: int = 30,
                        callback=None):
    """
    Run the monitoring loop indefinitely.

    Args:
        monitor: ResourceMonitor instance
        interval_seconds: How often to collect metrics (default: 30s)
        callback: Optional async function called with each metrics snapshot
    """
    while True:
        try:
            # Collect metrics (agent counts would come from orchestrator)
            metrics = monitor.collect_metrics()

            # Call callback if provided
            if callback:
                await callback(metrics)

            # Wait for next interval
            await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            break
        except Exception as e:
            # Log error but continue monitoring
            print(f"Error in monitoring loop: {e}")
            await asyncio.sleep(interval_seconds)


# Singleton instance
_global_monitor: Optional[ResourceMonitor] = None


def get_resource_monitor() -> ResourceMonitor:
    """
    Get global ResourceMonitor singleton.

    Returns:
        ResourceMonitor instance

    Raises:
        RuntimeError if service cgroup not found
    """
    global _global_monitor

    if _global_monitor is None:
        _global_monitor = ResourceMonitor()

    return _global_monitor
