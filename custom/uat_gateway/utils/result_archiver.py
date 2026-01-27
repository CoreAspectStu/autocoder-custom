"""
Result Archiver - Archive and manage old test results

This module provides functionality to:
- Store test results with timestamps
- Archive old results based on age or count
- Keep archived results accessible via API
- Maintain a clean active results list
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import shutil

# Add parent directory to path for imports

from uat_gateway.utils.logger import get_logger


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class TestResult:
    """Represents a single test result"""
    test_id: str
    test_name: str
    journey_id: str
    status: str  # 'passed', 'failed', 'skipped'
    timestamp: datetime
    duration_ms: int
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None  # Feature #364: User isolation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "journey_id": self.journey_id,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "user_id": self.user_id  # Feature #364: User isolation
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestResult':
        """Create from dictionary"""
        return cls(
            test_id=data["test_id"],
            test_name=data["test_name"],
            journey_id=data["journey_id"],
            status=data["status"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            duration_ms=data["duration_ms"],
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
            user_id=data.get("user_id")  # Feature #364: User isolation
        )


@dataclass
class ArchiveConfig:
    """Configuration for archiving behavior"""
    archive_age_days: int = 30  # Archive results older than this many days
    archive_after_count: int = 1000  # Archive when active results exceed this count
    max_active_results: int = 500  # Keep this many recent results active
    archive_dir: str = "archived_results"  # Directory for archived results


# ============================================================================
# Result Archiver
# ============================================================================

class ResultArchiver:
    """
    Manages archiving of old test results

    Features:
    - Stores test results with timestamps
    - Archives old results based on age or count
    - Maintains separate active and archived storage
    - Provides access to both active and archived results
    """

    def __init__(self, config: Optional[ArchiveConfig] = None):
        """
        Initialize the result archiver

        Args:
            config: Archiving configuration (uses defaults if not provided)
        """
        self.config = config or ArchiveConfig()
        self.logger = get_logger(__name__)

        # Storage
        self._active_results: Dict[str, TestResult] = {}  # test_id -> TestResult
        self._archived_results: Dict[str, TestResult] = {}  # test_id -> TestResult

        # Create archive directory
        self.archive_path = Path(self.config.archive_dir)
        self.archive_path.mkdir(parents=True, exist_ok=True)

        self.logger.info(
            f"ResultArchiver initialized: archive_age_days={self.config.archive_age_days}, "
            f"max_active_results={self.config.max_active_results}"
        )

    def add_result(self, result: TestResult) -> None:
        """
        Add a new test result

        Args:
            result: Test result to add
        """
        self._active_results[result.test_id] = result
        self.logger.debug(f"Added test result: {result.test_id} (status={result.status})")

    def get_result(self, test_id: str) -> Optional[TestResult]:
        """
        Get a test result by ID (checks both active and archived)

        Args:
            test_id: Test result ID

        Returns:
            Test result if found, None otherwise
        """
        # Check active results first
        if test_id in self._active_results:
            return self._active_results[test_id]

        # Check archived results
        if test_id in self._archived_results:
            return self._archived_results[test_id]

        return None

    def get_active_results(self, limit: Optional[int] = None) -> List[TestResult]:
        """
        Get all active (non-archived) results

        Args:
            limit: Optional limit on number of results to return

        Returns:
            List of active test results, sorted by timestamp (newest first)
        """
        results = sorted(
            self._active_results.values(),
            key=lambda r: r.timestamp,
            reverse=True
        )

        if limit:
            results = results[:limit]

        return results

    def get_archived_results(self, limit: Optional[int] = None) -> List[TestResult]:
        """
        Get all archived results

        Args:
            limit: Optional limit on number of results to return

        Returns:
            List of archived test results, sorted by timestamp (newest first)
        """
        results = sorted(
            self._archived_results.values(),
            key=lambda r: r.timestamp,
            reverse=True
        )

        if limit:
            results = results[:limit]

        return results

    def get_all_results(self, limit: Optional[int] = None) -> List[TestResult]:
        """
        Get all results (both active and archived)

        Args:
            limit: Optional limit on number of results to return

        Returns:
            List of all test results, sorted by timestamp (newest first)
        """
        all_results = {**self._active_results, **self._archived_results}
        results = sorted(
            all_results.values(),
            key=lambda r: r.timestamp,
            reverse=True
        )

        if limit:
            results = results[:limit]

        return results

    def archive_old_results(self) -> Dict[str, Any]:
        """
        Archive old results based on configured criteria

        Archiving criteria:
        1. Age-based: Archive results older than archive_age_days
        2. Count-based: If active results exceed archive_after_count,
           archive oldest results until max_active_results is reached

        Returns:
            Dictionary with archiving statistics
        """
        now = datetime.now()
        archived_by_age = []
        archived_by_count = []

        # Archive by age
        if self.config.archive_age_days > 0:
            cutoff_date = now - timedelta(days=self.config.archive_age_days)

            for test_id, result in list(self._active_results.items()):
                if result.timestamp < cutoff_date:
                    self._archived_results[test_id] = result
                    del self._active_results[test_id]
                    archived_by_age.append(test_id)

        # Archive by count (keep only max_active_results most recent)
        if len(self._active_results) > self.config.archive_after_count:
            # Sort by timestamp (oldest first) and archive excess
            sorted_results = sorted(
                self._active_results.items(),
                key=lambda x: x[1].timestamp
            )

            excess_count = len(self._active_results) - self.config.max_active_results

            for i in range(excess_count):
                test_id, result = sorted_results[i]
                if test_id in self._active_results:  # May have been archived by age
                    self._archived_results[test_id] = result
                    del self._active_results[test_id]
                    archived_by_count.append(test_id)

        # Save archived results to disk
        if archived_by_age or archived_by_count:
            self._save_archived_results()

        stats = {
            "archived_by_age_count": len(archived_by_age),
            "archived_by_count_count": len(archived_by_count),
            "total_archived": len(archived_by_age) + len(archived_by_count),
            "active_count": len(self._active_results),
            "archived_count": len(self._archived_results),
            "archived_ids": {
                "by_age": archived_by_age,
                "by_count": archived_by_count
            }
        }

        if stats["total_archived"] > 0:
            self.logger.info(
                f"Archived {stats['total_archived']} results "
                f"({stats['archived_by_age_count']} by age, "
                f"{stats['archived_by_count_count']} by count)"
            )

        return stats

    def _save_archived_results(self) -> None:
        """Save archived results to disk as JSON"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"archive_{timestamp}.json"
        filepath = self.archive_path / filename

        # Convert archived results to dict
        archived_data = {
            "archive_timestamp": datetime.now().isoformat(),
            "archived_results": [
                result.to_dict()
                for result in self._archived_results.values()
            ]
        }

        # Save to file
        with open(filepath, 'w') as f:
            json.dump(archived_data, f, indent=2)

        self.logger.info(f"Saved {len(self._archived_results)} archived results to {filepath}")

    def load_archived_results(self, filepath: Optional[str] = None) -> int:
        """
        Load archived results from disk

        Args:
            filepath: Path to archive file (if not specified, loads most recent)

        Returns:
            Number of results loaded
        """
        if filepath:
            archive_file = Path(filepath)
        else:
            # Find most recent archive file
            archive_files = sorted(self.archive_path.glob("archive_*.json"), reverse=True)
            if not archive_files:
                self.logger.warning("No archive files found")
                return 0
            archive_file = archive_files[0]

        # Load from file
        with open(archive_file, 'r') as f:
            data = json.load(f)

        # Load archived results
        count = 0
        for result_data in data.get("archived_results", []):
            result = TestResult.from_dict(result_data)
            self._archived_results[result.test_id] = result
            count += 1

        self.logger.info(f"Loaded {count} archived results from {archive_file}")
        return count

    def clear_archived_results(self) -> int:
        """
        Clear all archived results from memory

        Returns:
            Number of results cleared
        """
        count = len(self._archived_results)
        self._archived_results.clear()
        self.logger.info(f"Cleared {count} archived results from memory")
        return count

    def delete_result(self, test_id: str) -> bool:
        """
        Delete a specific test result from active or archived storage

        Feature #318: Support deleting individual test results
        This enables testing deleted record handling

        Args:
            test_id: ID of the test result to delete

        Returns:
            True if result was found and deleted, False if not found
        """
        # Try to delete from active results first
        if test_id in self._active_results:
            del self._active_results[test_id]
            self.logger.info(f"Deleted test result from active storage: {test_id}")
            return True

        # Try to delete from archived results
        if test_id in self._archived_results:
            del self._archived_results[test_id]
            self.logger.info(f"Deleted test result from archived storage: {test_id}")
            return True

        self.logger.warning(f"Test result not found for deletion: {test_id}")
        return False

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about results and archiving

        Returns:
            Dictionary with statistics
        """
        # Calculate pass rates
        active_passed = sum(1 for r in self._active_results.values() if r.status == "passed")
        archived_passed = sum(1 for r in self._archived_results.values() if r.status == "passed")

        active_pass_rate = (
            (active_passed / len(self._active_results) * 100)
            if self._active_results else 0
        )
        archived_pass_rate = (
            (archived_passed / len(self._archived_results) * 100)
            if self._archived_results else 0
        )

        # Find oldest and newest results
        all_results = list(self._active_results.values()) + list(self._archived_results.values())
        if all_results:
            sorted_results = sorted(all_results, key=lambda r: r.timestamp)
            oldest_result = sorted_results[0]
            newest_result = sorted_results[-1]
        else:
            oldest_result = None
            newest_result = None

        return {
            "active": {
                "count": len(self._active_results),
                "passed": active_passed,
                "failed": len(self._active_results) - active_passed,
                "pass_rate": round(active_pass_rate, 2)
            },
            "archived": {
                "count": len(self._archived_results),
                "passed": archived_passed,
                "failed": len(self._archived_results) - archived_passed,
                "pass_rate": round(archived_pass_rate, 2)
            },
            "total": {
                "count": len(self._active_results) + len(self._archived_results)
            },
            "config": {
                "archive_age_days": self.config.archive_age_days,
                "max_active_results": self.config.max_active_results,
                "archive_after_count": self.config.archive_after_count
            },
            "date_range": {
                "oldest": oldest_result.timestamp.isoformat() if oldest_result else None,
                "newest": newest_result.timestamp.isoformat() if newest_result else None
            }
        }


# ============================================================================
# Convenience Functions
# ============================================================================

def create_result_archiver(
    archive_age_days: int = 30,
    max_active_results: int = 500,
    archive_after_count: int = 1000
) -> ResultArchiver:
    """
    Create a result archiver with custom configuration

    Args:
        archive_age_days: Archive results older than this many days
        max_active_results: Keep this many recent results active
        archive_after_count: Archive when active results exceed this count

    Returns:
        Configured ResultArchiver instance
    """
    config = ArchiveConfig(
        archive_age_days=archive_age_days,
        max_active_results=max_active_results,
        archive_after_count=archive_after_count
    )
    return ResultArchiver(config)
