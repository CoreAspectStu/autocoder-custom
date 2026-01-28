"""
Journey Persistence Module for UAT Gateway

Provides file-based persistence for journeys, ensuring data survives
server restarts. Uses JSON file storage with automatic save/load.

Feature #379: Data survives application restart
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import threading
import atexit

logger = logging.getLogger(__name__)


class JourneyPersistence:
    """
    Manages persistent storage for journeys using JSON files.

    Provides automatic save/load functionality with thread-safe operations.
    Data is persisted to disk immediately on changes and loaded on startup.
    """

    def __init__(self, storage_file: str = "journeys_data.json"):
        """
        Initialize journey persistence manager.

        Args:
            storage_file: Path to JSON file for journey storage
        """
        self.storage_file = Path(storage_file)
        self._lock = threading.RLock()
        self._journeys: Dict[str, Dict[str, Any]] = {}

        # Load existing data on startup
        self._load()

        # Register cleanup on exit
        atexit.register(self._cleanup)

    def _load(self) -> None:
        """
        Load journeys from storage file.

        Reads the JSON file and populates the in-memory cache.
        Creates empty storage if file doesn't exist.
        """
        with self._lock:
            try:
                if self.storage_file.exists():
                    logger.info(f"Loading journeys from {self.storage_file}")
                    with open(self.storage_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self._journeys = data.get("journeys", {})
                    logger.info(f"Loaded {len(self._journeys)} journeys from storage")
                else:
                    logger.info(f"No existing journey storage found at {self.storage_file}")
                    logger.info("Creating new journey storage")
                    self._journeys = {}
                    self._save()
            except Exception as e:
                logger.error(f"Error loading journeys from {self.storage_file}: {e}")
                logger.warning("Starting with empty journey store")
                self._journeys = {}

    def _save(self) -> None:
        """
        Save journeys to storage file.

        Writes the current in-memory journeys to disk as JSON.
        Uses atomic write with temporary file to prevent corruption.
        """
        with self._lock:
            try:
                # Create backup if file exists
                if self.storage_file.exists():
                    backup_path = self.storage_file.with_suffix(
                        f'.json.bak.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                    )
                    try:
                        import shutil
                        shutil.copy2(self.storage_file, backup_path)
                        logger.debug(f"Created backup: {backup_path.name}")
                    except Exception as e:
                        logger.warning(f"Could not create backup: {e}")

                # Write to temporary file first (atomic write)
                temp_file = self.storage_file.with_suffix('.json.tmp')
                data = {
                    "version": "1.0",
                    "updated_at": datetime.now().isoformat(),
                    "journey_count": len(self._journeys),
                    "journeys": self._journeys
                }

                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # Atomic rename
                temp_file.replace(self.storage_file)
                logger.debug(f"Saved {len(self._journeys)} journeys to {self.storage_file}")

            except Exception as e:
                logger.error(f"Error saving journeys to {self.storage_file}: {e}")
                raise

    def _cleanup(self) -> None:
        """Cleanup on exit - ensure data is saved"""
        logger.info("JourneyPersistence cleanup - saving data")
        self._save()

    # =========================================================================
    # Public API - Journey CRUD Operations
    # =========================================================================

    def get_all_journeys(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all journeys.

        Returns:
            Dictionary mapping journey_id to journey data
        """
        with self._lock:
            return dict(self._journeys)

    def get_journey(self, journey_id: str) -> Dict[str, Any] | None:
        """
        Get a specific journey by ID.

        Args:
            journey_id: Unique journey identifier

        Returns:
            Journey data dict or None if not found
        """
        with self._lock:
            return self._journeys.get(journey_id)

    def create_journey(self, journey_id: str, journey_data: Dict[str, Any]) -> None:
        """
        Create a new journey.

        Args:
            journey_id: Unique journey identifier
            journey_data: Journey data to store
        """
        with self._lock:
            if journey_id in self._journeys:
                raise ValueError(f"Journey {journey_id} already exists")

            self._journeys[journey_id] = journey_data
            self._save()
            logger.info(f"Created journey {journey_id}: {journey_data.get('name', 'unnamed')}")

    def update_journey(self, journey_id: str, journey_data: Dict[str, Any]) -> None:
        """
        Update an existing journey.

        Args:
            journey_id: Unique journey identifier
            journey_data: Updated journey data
        """
        with self._lock:
            if journey_id not in self._journeys:
                raise ValueError(f"Journey {journey_id} not found")

            self._journeys[journey_id] = journey_data
            self._save()
            logger.info(f"Updated journey {journey_id}: {journey_data.get('name', 'unnamed')}")

    def delete_journey(self, journey_id: str) -> None:
        """
        Delete a journey.

        Args:
            journey_id: Unique journey identifier
        """
        with self._lock:
            if journey_id not in self._journeys:
                raise ValueError(f"Journey {journey_id} not found")

            journey_name = self._journeys[journey_id].get('name', 'unnamed')
            del self._journeys[journey_id]
            self._save()
            logger.info(f"Deleted journey {journey_id}: {journey_name}")

    def journey_exists(self, journey_id: str) -> bool:
        """
        Check if a journey exists.

        Args:
            journey_id: Unique journey identifier

        Returns:
            True if journey exists, False otherwise
        """
        with self._lock:
            return journey_id in self._journeys

    def get_journey_count(self) -> int:
        """
        Get the total number of journeys.

        Returns:
            Number of journeys in storage
        """
        with self._lock:
            return len(self._journeys)

    def clear_all_journeys(self) -> None:
        """
        Clear all journeys (use with caution).

        This is primarily used for testing.
        """
        with self._lock:
            count = len(self._journeys)
            self._journeys = {}
            self._save()
            logger.warning(f"Cleared all {count} journeys")


# Global instance for the application
_journey_persistence: JourneyPersistence | None = None


def get_journey_persistence(storage_file: str = "journeys_data.json") -> JourneyPersistence:
    """
    Get the global journey persistence instance.

    Args:
        storage_file: Path to storage file (only used on first call)

    Returns:
        JourneyPersistence instance
    """
    global _journey_persistence
    if _journey_persistence is None:
        _journey_persistence = JourneyPersistence(storage_file)
    return _journey_persistence
