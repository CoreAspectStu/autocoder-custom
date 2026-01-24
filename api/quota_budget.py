"""
API Quota Budget Tracker
========================

Tracks Claude Code API usage against the 5-hour rolling window quota limit.
Provides real-time quota visibility and safe concurrency calculations.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class QuotaBudget:
    """
    Tracks API quota usage with 5-hour rolling window.

    Max 20x Plan Limits:
    - 200-800 prompts per 5-hour window (varies by complexity)
    - Conservative assumption: 400 prompts per 5 hours
    """

    # Conservative quota limit for Max 20x plan (Anthropic)
    # GLM has much higher limits - override via env var if needed
    DEFAULT_QUOTA_LIMIT = 400  # prompts per 5-hour window

    # Allow override via environment variable
    import os
    if os.getenv("ANTHROPIC_BASE_URL", "").startswith("https://api.z.ai"):
        # GLM via Zhipu AI has much higher quotas
        DEFAULT_QUOTA_LIMIT = 10000  # Much higher limit for GLM

    # Time window for quota tracking (in hours)
    QUOTA_WINDOW_HOURS = 5

    def __init__(self, db_path: Optional[Path] = None, quota_limit: Optional[int] = None):
        """
        Initialize quota tracker.

        Args:
            db_path: Path to SQLite database (default: ~/.autocoder/quota.db)
            quota_limit: Custom quota limit (default: 400 prompts per 5 hours)
        """
        if db_path is None:
            db_path = Path.home() / ".autocoder" / "quota.db"

        self.db_path = db_path
        self.quota_limit = quota_limit or self.DEFAULT_QUOTA_LIMIT

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Create quota_log table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quota_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompts_used INTEGER NOT NULL DEFAULT 1,
                    project_name TEXT,
                    agent_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index for fast rolling window queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_quota_timestamp
                ON quota_log(timestamp)
            """)

            conn.commit()
        finally:
            conn.close()

    def track_usage(
        self,
        model: str,
        prompts_used: int = 1,
        project_name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        """
        Record API usage.

        Args:
            model: Model used (e.g., "sonnet-4", "haiku")
            prompts_used: Number of prompts consumed (default: 1)
            project_name: Optional project identifier
            agent_id: Optional agent identifier
        """
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO quota_log (timestamp, model, prompts_used, project_name, agent_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    model,
                    prompts_used,
                    project_name,
                    agent_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_usage_5h(self) -> int:
        """
        Get total prompts used in the last 5 hours.

        Returns:
            Number of prompts used in 5-hour rolling window
        """
        cutoff = datetime.utcnow() - timedelta(hours=self.QUOTA_WINDOW_HOURS)
        cutoff_str = cutoff.isoformat()

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT COALESCE(SUM(prompts_used), 0)
                FROM quota_log
                WHERE timestamp > ?
                """,
                (cutoff_str,),
            )
            result = cursor.fetchone()
            return result[0] if result else 0
        finally:
            conn.close()

    def get_remaining_5h(self) -> int:
        """
        Get remaining prompts available in current 5-hour window.

        Returns:
            Number of prompts remaining (0 if quota exhausted)
        """
        used = self.get_usage_5h()
        remaining = max(0, self.quota_limit - used)
        return remaining

    def get_usage_percentage(self) -> float:
        """
        Get quota usage as percentage (0-100).

        Returns:
            Percentage of quota used in current window
        """
        used = self.get_usage_5h()
        return (used / self.quota_limit) * 100 if self.quota_limit > 0 else 0

    def is_quota_available(self, prompts_needed: int = 1) -> bool:
        """
        Check if quota is available for requested prompts.

        Args:
            prompts_needed: Number of prompts required

        Returns:
            True if quota available, False if exhausted
        """
        remaining = self.get_remaining_5h()
        return remaining >= prompts_needed

    def calculate_safe_concurrency(self, prompts_per_agent: int = 20) -> int:
        """
        Calculate safe agent concurrency based on remaining quota.

        Args:
            prompts_per_agent: Estimated prompts per agent (default: 20)

        Returns:
            Safe number of concurrent agents (minimum 0)
        """
        remaining = self.get_remaining_5h()
        safe_concurrency = remaining // prompts_per_agent
        return max(0, safe_concurrency)

    def cleanup_old_entries(self):
        """
        Delete quota log entries older than 5 hours.
        Run periodically to keep database small.
        """
        cutoff = datetime.utcnow() - timedelta(hours=self.QUOTA_WINDOW_HOURS)
        cutoff_str = cutoff.isoformat()

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                DELETE FROM quota_log
                WHERE timestamp <= ?
                """,
                (cutoff_str,),
            )
            conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """
        Get comprehensive quota statistics.

        Returns:
            Dictionary with quota stats: used, remaining, percentage, limit
        """
        used = self.get_usage_5h()
        remaining = self.get_remaining_5h()
        percentage = self.get_usage_percentage()

        return {
            "used": used,
            "remaining": remaining,
            "percentage": percentage,
            "limit": self.quota_limit,
            "window_hours": self.QUOTA_WINDOW_HOURS,
        }


# Singleton instance for global access
_global_quota_budget: Optional[QuotaBudget] = None


def get_quota_budget() -> QuotaBudget:
    """
    Get global QuotaBudget singleton instance.

    Returns:
        Global QuotaBudget instance
    """
    global _global_quota_budget
    if _global_quota_budget is None:
        _global_quota_budget = QuotaBudget()
    return _global_quota_budget
