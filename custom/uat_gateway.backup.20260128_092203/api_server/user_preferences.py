"""
User Preferences Module for UAT Gateway

Provides persistent user preference storage with JSON file backend.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict, field
import threading
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class UserPreference:
    """A single user preference with metadata"""

    key: str
    value: Any
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPreference':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class UserPreferences:
    """Container for all user preferences"""

    user_id: str
    preferences: Dict[str, UserPreference] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def get(self, key: str, default: Any = None) -> Any:
        """Get a preference value"""
        if key not in self.preferences:
            return default
        return self.preferences[key].value

    def set(self, key: str, value: Any) -> None:
        """Set a preference value"""
        now = datetime.now().isoformat()

        if key in self.preferences:
            # Update existing preference
            self.preferences[key].value = value
            self.preferences[key].updated_at = now
        else:
            # Create new preference
            self.preferences[key] = UserPreference(
                key=key,
                value=value,
                created_at=now,
                updated_at=now
            )

        self.updated_at = now

    def delete(self, key: str) -> bool:
        """Delete a preference"""
        if key in self.preferences:
            del self.preferences[key]
            self.updated_at = datetime.now().isoformat()
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "user_id": self.user_id,
            "preferences": {
                key: pref.to_dict()
                for key, pref in self.preferences.items()
            },
            "updated_at": self.updated_at,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserPreferences':
        """Create from dictionary"""
        prefs = cls(
            user_id=data["user_id"],
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            created_at=data.get("created_at", datetime.now().isoformat())
        )

        for key, pref_data in data.get("preferences", {}).items():
            prefs.preferences[key] = UserPreference.from_dict(pref_data)

        return prefs

    def get_all(self) -> Dict[str, Any]:
        """Get all preference values as simple dict"""
        return {
            key: pref.value
            for key, pref in self.preferences.items()
        }


class UserPreferencesManager:
    """
    Manages persistent storage of user preferences

    Uses thread-safe JSON file storage with automatic backups.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize the preferences manager

        Args:
            storage_dir: Directory to store preference files (default: ./state/preferences)
        """
        if storage_dir is None:
            storage_dir = Path("./state/preferences")

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.preferences_file = self.storage_dir / "user_preferences.json"
        self.backup_dir = self.storage_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)

        self._cache: Dict[str, UserPreferences] = {}
        self._lock = threading.Lock()

        # Load existing preferences
        self._load_all()

        logger.info(f"UserPreferencesManager initialized with storage: {self.storage_dir}")

    def _get_user_file_path(self, user_id: str) -> Path:
        """Get the preferences file path for a specific user"""
        # Hash user_id for safe filename
        safe_id = hashlib.md5(user_id.encode()).hexdigest()[:16]
        return self.storage_dir / f"user_{safe_id}.json"

    def _load_all(self) -> None:
        """Load all user preferences from storage"""
        with self._lock:
            self._cache.clear()

            # Load all user preference files
            for file_path in self.storage_dir.glob("user_*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        prefs = UserPreferences.from_dict(data)
                        self._cache[prefs.user_id] = prefs
                        logger.debug(f"Loaded preferences for user: {prefs.user_id}")
                except Exception as e:
                    logger.error(f"Failed to load preferences from {file_path}: {e}")

            logger.info(f"Loaded {len(self._cache)} user preferences from storage")

    def _save_user(self, prefs: UserPreferences) -> None:
        """Save user preferences to file"""
        file_path = self._get_user_file_path(prefs.user_id)

        try:
            # Create backup if file exists
            if file_path.exists():
                backup_path = self.backup_dir / f"{file_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                shutil.copy2(file_path, backup_path)

            # Save to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(prefs.to_dict(), f, indent=2, ensure_ascii=False)

            logger.debug(f"Saved preferences for user: {prefs.user_id}")

        except Exception as e:
            logger.error(f"Failed to save preferences for user {prefs.user_id}: {e}")
            raise

    def get_user_preferences(self, user_id: str) -> UserPreferences:
        """
        Get preferences for a user

        Args:
            user_id: User identifier

        Returns:
            UserPreferences object (creates new if doesn't exist)
        """
        with self._lock:
            if user_id not in self._cache:
                # Create new preferences for user
                self._cache[user_id] = UserPreferences(user_id=user_id)
                logger.info(f"Created new preferences for user: {user_id}")

            return self._cache[user_id]

    def get_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        """
        Get a specific preference value

        Args:
            user_id: User identifier
            key: Preference key
            default: Default value if not found

        Returns:
            Preference value or default
        """
        prefs = self.get_user_preferences(user_id)
        return prefs.get(key, default)

    def set_preference(self, user_id: str, key: str, value: Any, auto_save: bool = True) -> None:
        """
        Set a preference value

        Args:
            user_id: User identifier
            key: Preference key
            value: Preference value
            auto_save: Whether to save immediately
        """
        with self._lock:
            prefs = self.get_user_preferences(user_id)
            prefs.set(key, value)

            if auto_save:
                self._save_user(prefs)

            logger.info(f"Set preference for user {user_id}: {key} = {value}")

    def set_preferences(self, user_id: str, preferences: Dict[str, Any], auto_save: bool = True) -> None:
        """
        Set multiple preference values

        Args:
            user_id: User identifier
            preferences: Dictionary of preferences to set
            auto_save: Whether to save immediately
        """
        with self._lock:
            prefs = self.get_user_preferences(user_id)

            for key, value in preferences.items():
                prefs.set(key, value)

            if auto_save:
                self._save_user(prefs)

            logger.info(f"Set {len(preferences)} preferences for user: {user_id}")

    def delete_preference(self, user_id: str, key: str, auto_save: bool = True) -> bool:
        """
        Delete a preference

        Args:
            user_id: User identifier
            key: Preference key
            auto_save: Whether to save immediately

        Returns:
            True if deleted, False if didn't exist
        """
        with self._lock:
            prefs = self.get_user_preferences(user_id)
            deleted = prefs.delete(key)

            if deleted and auto_save:
                self._save_user(prefs)

            if deleted:
                logger.info(f"Deleted preference for user {user_id}: {key}")

            return deleted

    def get_all_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Get all preferences for a user

        Args:
            user_id: User identifier

        Returns:
            Dictionary of all preferences
        """
        prefs = self.get_user_preferences(user_id)
        return prefs.get_all()

    def reset_user_preferences(self, user_id: str, auto_save: bool = True) -> None:
        """
        Reset all preferences for a user

        Args:
            user_id: User identifier
            auto_save: Whether to save immediately
        """
        with self._lock:
            prefs = UserPreferences(user_id=user_id)
            self._cache[user_id] = prefs

            if auto_save:
                self._save_user(prefs)

            logger.info(f"Reset all preferences for user: {user_id}")

    def delete_user_preferences(self, user_id: str) -> bool:
        """
        Delete all preferences for a user

        Args:
            user_id: User identifier

        Returns:
            True if deleted, False if didn't exist
        """
        with self._lock:
            if user_id not in self._cache:
                return False

            # Remove from cache
            del self._cache[user_id]

            # Delete file
            file_path = self._get_user_file_path(user_id)
            if file_path.exists():
                file_path.unlink()

            logger.info(f"Deleted all preferences for user: {user_id}")
            return True

    def save_all(self) -> None:
        """Save all cached preferences to disk"""
        with self._lock:
            for prefs in self._cache.values():
                self._save_user(prefs)

            logger.info(f"Saved {len(self._cache)} user preferences to disk")

    def get_all_users(self) -> List[str]:
        """
        Get list of all users with preferences

        Returns:
            List of user IDs
        """
        with self._lock:
            return list(self._cache.keys())


# Singleton instance for use in API
_global_manager: Optional[UserPreferencesManager] = None


def get_preferences_manager(storage_dir: Optional[Path] = None) -> UserPreferencesManager:
    """
    Get the global preferences manager instance

    Args:
        storage_dir: Storage directory (only used on first call)

    Returns:
        UserPreferencesManager instance
    """
    global _global_manager

    if _global_manager is None:
        _global_manager = UserPreferencesManager(storage_dir=storage_dir)

    return _global_manager


# Import shutil for backup functionality
import shutil
