"""
Feature Database Backup System
==============================

Automatically backs up features.db when changes are made.
Implements rolling backups with configurable retention.

Usage:
    from api.database_backup import backup_features_db

    # Automatic backup before modifications
    backup_features_db(project_path)

    # Restore from a specific backup
    restore_from_backup(project_path, backup_file)
"""

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# Configuration
BACKUP_DIR_NAME = ".feature_backups"
MAX_BACKUPS = 20  # Keep last 20 backups
COMPRESS_AFTER_DAYS = 7  # Compress backups older than 7 days


def get_backup_dir(project_path: Path) -> Path:
    """
    Get the backup directory for a project.

    Args:
        project_path: Path to the project directory

    Returns:
        Path to the backup directory
    """
    backup_dir = project_path / BACKUP_DIR_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def backup_features_db(
    project_path: Path,
    reason: str = "auto"
) -> Optional[Path]:
    """
    Create a timestamped backup of features.db.

    Args:
        project_path: Path to the project directory
        reason: Reason for backup (e.g., "before_feature_create", "before_update")

    Returns:
        Path to the created backup file, or None if backup failed
    """
    features_db = project_path / "features.db"

    if not features_db.exists():
        return None

    try:
        # Verify database is readable before backing up
        conn = sqlite3.connect(str(features_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM features")
        feature_count = cursor.fetchone()[0]
        conn.close()

        # Create backup filename with timestamp and reason
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_filename = f"features_{feature_count}_{timestamp}_{reason}.db"
        backup_path = get_backup_dir(project_path) / backup_filename

        # Copy the database
        shutil.copy2(features_db, backup_path)

        # Create metadata file
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "feature_count": feature_count,
            "original_file": str(features_db),
            "original_size": features_db.stat().st_size,
            "backup_size": backup_path.stat().st_size
        }

        metadata_path = backup_path.with_suffix(".json")
        import json
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Cleanup old backups
        cleanup_old_backups(project_path)

        return backup_path

    except Exception as e:
        print(f"Warning: Failed to backup {features_db}: {e}")
        return None


def cleanup_old_backups(
    project_path: Path,
    keep: int = MAX_BACKUPS
) -> List[Path]:
    """
    Remove old backups, keeping only the most recent ones.

    Args:
        project_path: Path to the project directory
        keep: Number of backups to keep (default: MAX_BACKUPS)

    Returns:
        List of removed backup paths
    """
    backup_dir = get_backup_dir(project_path)

    if not backup_dir.exists():
        return []

    try:
        # Get all .db backup files (not metadata .json files)
        backups = sorted(
            backup_dir.glob("features_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True  # Newest first
        )

        # Remove old backups beyond keep limit
        removed = []
        for old_backup in backups[keep:]:
            # Also remove corresponding metadata file
            metadata_file = old_backup.with_suffix(".json")
            if metadata_file.exists():
                metadata_file.unlink()

            old_backup.unlink()
            removed.append(old_backup)

        return removed

    except Exception as e:
        print(f"Warning: Failed to cleanup old backups: {e}")
        return []


def list_backups(project_path: Path) -> List[dict]:
    """
    List all available backups with metadata.

    Args:
        project_path: Path to the project directory

    Returns:
        List of backup info dictionaries
    """
    backup_dir = get_backup_dir(project_path)

    if not backup_dir.exists():
        return []

    backups = []
    import json

    for backup_file in sorted(backup_dir.glob("features_*.db"), reverse=True):
        metadata_file = backup_file.with_suffix(".json")

        metadata = {
            "filename": backup_file.name,
            "path": str(backup_file),
            "size_mb": round(backup_file.stat().st_size / (1024**2), 2),
            "timestamp": None,
            "reason": None,
            "feature_count": None
        }

        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    data = json.load(f)
                    metadata.update(data)
            except Exception:
                pass  # Use default values

        backups.append(metadata)

    return backups


def restore_from_backup(
    project_path: Path,
    backup_file: str | Path
) -> bool:
    """
    Restore features.db from a backup.

    Args:
        project_path: Path to the project directory
        backup_file: Name or path of the backup file

    Returns:
        True if restore succeeded, False otherwise
    """
    features_db = project_path / "features.db"
    backup_dir = get_backup_dir(project_path)

    # If backup_file is just a name, find it in backup dir
    if isinstance(backup_file, str) and not Path(backup_file).is_absolute():
        backup_path = backup_dir / backup_file
    else:
        backup_path = Path(backup_file)

    if not backup_path.exists():
        print(f"Backup file not found: {backup_path}")
        return False

    try:
        # Create a backup of current (possibly corrupted) database before restoring
        if features_db.exists():
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            emergency_backup = backup_dir / f"features_emergency_{timestamp}.db"
            shutil.copy2(features_db, emergency_backup)
            print(f"Emergency backup created: {emergency_backup.name}")

        # Restore from backup
        shutil.copy2(backup_path, features_db)

        # Verify restored database is readable
        conn = sqlite3.connect(str(features_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM features")
        count = cursor.fetchone()[0]
        conn.close()

        print(f"Restored {count} features from {backup_path.name}")
        return True

    except Exception as e:
        print(f"Failed to restore from backup: {e}")
        return False


def get_latest_backup(project_path: Path) -> Optional[Path]:
    """
    Get the most recent backup file.

    Args:
        project_path: Path to the project directory

    Returns:
        Path to the latest backup, or None if no backups exist
    """
    backup_dir = get_backup_dir(project_path)

    if not backup_dir.exists():
        return None

    try:
        backups = list(backup_dir.glob("features_*.db"))
        if backups:
            return max(backups, key=lambda p: p.stat().st_mtime)
        return None
    except Exception:
        return None


def backup_project_summary(project_path: Path) -> dict:
    """
    Get a summary of backup status for a project.

    Args:
        project_path: Path to the project directory

    Returns:
        Dictionary with backup summary
    """
    features_db = project_path / "features.db"
    backup_dir = get_backup_dir(project_path)

    summary = {
        "features_db_exists": features_db.exists(),
        "backup_dir_exists": backup_dir.exists(),
        "backup_count": len(list(backup_dir.glob("features_*.db"))) if backup_dir.exists() else 0,
        "latest_backup": None,
        "total_backup_size_mb": 0
    }

    if backup_dir.exists():
        latest = get_latest_backup(project_path)
        if latest:
            summary["latest_backup"] = {
                "filename": latest.name,
                "timestamp": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(),
                "size_mb": round(latest.stat().st_size / (1024**2), 2)
            }

        total_size = sum(f.stat().st_size for f in backup_dir.glob("features_*.db"))
        summary["total_backup_size_mb"] = round(total_size / (1024**2), 2)

    return summary
