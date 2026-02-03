"""
Database backup and recovery system for UAT AutoCoder Plugin.

Provides automated backup creation, restoration, and verification for uat_tests.db.
Supports both full database backups and table-level exports.
"""

import os
import sqlite3
import shutil
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager


class BackupManager:
    """
    Manages backup and recovery operations for uat_tests.db.

    Features:
    - Full database backups (SQLite file copy)
    - JSON exports for portability
    - Backup verification (checksums, record counts)
    - Automatic rotation (keep last N backups)
    - Restore with validation
    """

    def __init__(self, db_path: Optional[str] = None, backup_dir: Optional[str] = None):
        """
        Initialize backup manager.

        Args:
            db_path: Path to uat_tests.db (default: ~/.autocoder/uat_tests.db)
            backup_dir: Directory to store backups (default: ./.uat_backups)
        """
        self.db_path = db_path or os.path.expanduser('~/.autocoder/uat_tests.db')
        self.backup_dir = backup_dir or os.path.join(os.getcwd(), '.uat_backups')

        # Ensure backup directory exists
        os.makedirs(self.backup_dir, exist_ok=True)

        # Maximum backups to keep (per type)
        self.max_backups = 10

    def create_backup(self, backup_name: Optional[str] = None, include_json: bool = True) -> Dict[str, Any]:
        """
        Create a full database backup.

        Args:
            backup_name: Optional custom name for backup (default: auto-generated timestamp)
            include_json: Whether to create JSON export alongside SQLite backup

        Returns:
            Dictionary with backup metadata (path, size, checksum, record_counts)

        Raises:
            FileNotFoundError: If database file doesn't exist
            IOError: If backup cannot be created
        """
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        # Generate backup name
        if backup_name is None:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            backup_name = f"uat_tests_{timestamp}"

        # Backup file paths
        backup_db_path = os.path.join(self.backup_dir, f"{backup_name}.db")
        backup_json_path = os.path.join(self.backup_dir, f"{backup_name}.json")
        backup_meta_path = os.path.join(self.backup_dir, f"{backup_name}.meta")

        # Get database statistics before backup
        stats_before = self._get_db_stats()

        # Create SQLite backup (file copy)
        shutil.copy2(self.db_path, backup_db_path)

        # Verify backup was created
        if not os.path.exists(backup_db_path):
            raise IOError(f"Backup file not created: {backup_db_path}")

        # Calculate checksums
        db_checksum = self._calculate_checksum(self.db_path)
        backup_checksum = self._calculate_checksum(backup_db_path)

        # Create JSON export if requested
        json_size = 0
        if include_json:
            json_size = self._export_to_json(backup_json_path)

        # Create metadata file
        metadata = {
            'backup_name': backup_name,
            'created_at': datetime.now().isoformat(),
            'db_path': self.db_path,
            'backup_db_path': backup_db_path,
            'backup_json_path': backup_json_path if include_json else None,
            'original_size': os.path.getsize(self.db_path),
            'backup_size': os.path.getsize(backup_db_path),
            'json_size': json_size,
            'original_checksum': db_checksum,
            'backup_checksum': backup_checksum,
            'checksums_match': db_checksum == backup_checksum,
            'record_counts': stats_before,
            'backup_type': 'full'
        }

        with open(backup_meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Rotate old backups
        self._rotate_backups()

        return metadata

    def restore_backup(self, backup_name: str, verify: bool = True) -> Dict[str, Any]:
        """
        Restore database from a backup.

        Args:
            backup_name: Name of backup to restore (without .db extension)
            verify: Whether to verify restore integrity (default: True)

        Returns:
            Dictionary with restore metadata

        Raises:
            FileNotFoundError: If backup doesn't exist
            IOError: If restore fails
            ValueError: If verification fails
        """
        backup_db_path = os.path.join(self.backup_dir, f"{backup_name}.db")
        backup_meta_path = os.path.join(self.backup_dir, f"{backup_name}.meta")

        # Verify backup exists
        if not os.path.exists(backup_db_path):
            raise FileNotFoundError(f"Backup not found: {backup_db_path}")

        # Load metadata
        metadata = {}
        if os.path.exists(backup_meta_path):
            with open(backup_meta_path, 'r') as f:
                metadata = json.load(f)

        # Calculate checksum before restore
        backup_checksum = self._calculate_checksum(backup_db_path)

        # Create safety backup of current database
        if os.path.exists(self.db_path):
            safety_timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            safety_backup = os.path.join(self.backup_dir, f"pre_restore_safety_{safety_timestamp}.db")
            shutil.copy2(self.db_path, safety_backup)

        # Restore from backup
        shutil.copy2(backup_db_path, self.db_path)

        # Verify restore
        restore_checksum = self._calculate_checksum(self.db_path)
        restore_stats = self._get_db_stats() if verify else None

        if verify:
            # Checksum verification
            if backup_checksum != restore_checksum:
                raise ValueError(
                    f"Checksum mismatch after restore: "
                    f"backup={backup_checksum}, restored={restore_checksum}"
                )

            # Verify database integrity
            if not self._verify_integrity():
                raise ValueError("Database integrity check failed after restore")

            # Record count verification (if metadata available)
            if metadata and 'record_counts' in metadata:
                expected_counts = metadata['record_counts']
                actual_counts = restore_stats
                if expected_counts != actual_counts:
                    raise ValueError(
                        f"Record count mismatch after restore: "
                        f"expected={expected_counts}, actual={actual_counts}"
                    )

        return {
            'backup_name': backup_name,
            'restored_at': datetime.now().isoformat(),
            'backup_checksum': backup_checksum,
            'restored_checksum': restore_checksum,
            'checksums_match': backup_checksum == restore_checksum,
            'record_counts': restore_stats,
            'safety_backup': safety_backup if os.path.exists(self.db_path) else None,
            'verification_passed': verify
        }

    def list_backups(self) -> List[Dict[str, Any]]:
        """
        List all available backups.

        Returns:
            List of backup metadata dictionaries
        """
        backups = []

        for file in os.listdir(self.backup_dir):
            if file.endswith('.meta'):
                meta_path = os.path.join(self.backup_dir, file)
                try:
                    with open(meta_path, 'r') as f:
                        metadata = json.load(f)
                        backups.append(metadata)
                except (json.JSONDecodeError, IOError):
                    # Skip corrupted metadata files
                    continue

        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return backups

    def delete_backup(self, backup_name: str) -> bool:
        """
        Delete a backup and all associated files.

        Args:
            backup_name: Name of backup to delete (without extension)

        Returns:
            True if deleted, False if not found
        """
        deleted = False

        # Delete backup files
        for ext in ['.db', '.json', '.meta']:
            file_path = os.path.join(self.backup_dir, f"{backup_name}{ext}")
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted = True

        return deleted

    def _get_db_stats(self) -> Dict[str, int]:
        """
        Get record counts for all tables.

        Returns:
            Dictionary with table names and row counts
        """
        if not os.path.exists(self.db_path):
            return {}

        stats = {}
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()

            for (table_name,) in tables:
                cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                count = cursor.fetchone()[0]
                stats[table_name] = count
        finally:
            conn.close()

        return stats

    def _calculate_checksum(self, file_path: str) -> str:
        """
        Calculate SHA256 checksum of a file.

        Args:
            file_path: Path to file

        Returns:
            Hexadecimal checksum string
        """
        sha256 = hashlib.sha256()

        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)

        return sha256.hexdigest()

    def _export_to_json(self, output_path: str) -> int:
        """
        Export all database data to JSON file.

        Args:
            output_path: Path to output JSON file

        Returns:
            Size of exported file in bytes
        """
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        export_data = {}

        try:
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()

            for (table_name,) in tables:
                # Skip internal tables
                if table_name.startswith('sqlite_'):
                    continue

                # Export all rows
                cursor.execute(f"SELECT * FROM `{table_name}`")
                rows = cursor.fetchall()

                export_data[table_name] = [dict(row) for row in rows]

        finally:
            conn.close()

        # Write to JSON file
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        return os.path.getsize(output_path)

    def _verify_integrity(self) -> bool:
        """
        Verify database integrity using PRAGMA integrity_check.

        Returns:
            True if integrity check passes, False otherwise
        """
        if not os.path.exists(self.db_path):
            return False

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            return result[0] == 'ok'
        except Exception:
            return False
        finally:
            conn.close()

    def _rotate_backups(self) -> None:
        """
        Rotate old backups, keeping only the most recent ones.
        """
        backups = self.list_backups()

        if len(backups) <= self.max_backups:
            return

        # Delete oldest backups
        backups_to_delete = backups[self.max_backups:]
        for backup in backups_to_delete:
            backup_name = backup.get('backup_name')
            if backup_name:
                self.delete_backup(backup_name)


# ============================================================================
# Convenience Functions
# ============================================================================

def create_backup(backup_name: Optional[str] = None, include_json: bool = True) -> Dict[str, Any]:
    """
    Create a backup of uat_tests.db.

    Args:
        backup_name: Optional custom backup name
        include_json: Whether to create JSON export

    Returns:
        Backup metadata dictionary
    """
    manager = BackupManager()
    return manager.create_backup(backup_name, include_json)


def restore_backup(backup_name: str, verify: bool = True) -> Dict[str, Any]:
    """
    Restore uat_tests.db from a backup.

    Args:
        backup_name: Name of backup to restore
        verify: Whether to verify restore integrity

    Returns:
        Restore metadata dictionary
    """
    manager = BackupManager()
    return manager.restore_backup(backup_name, verify)


def list_backups() -> List[Dict[str, Any]]:
    """
    List all available backups.

    Returns:
        List of backup metadata dictionaries
    """
    manager = BackupManager()
    return manager.list_backups()


def delete_backup(backup_name: str) -> bool:
    """
    Delete a backup.

    Args:
        backup_name: Name of backup to delete

    Returns:
        True if deleted, False if not found
    """
    manager = BackupManager()
    return manager.delete_backup(backup_name)


if __name__ == '__main__':
    # Test backup functionality
    print("Testing UAT database backup and recovery...")

    manager = BackupManager()

    # Create backup
    print("\n1. Creating backup...")
    metadata = manager.create_backup()
    print(f"   ✓ Backup created: {metadata['backup_name']}")
    print(f"   ✓ Size: {metadata['backup_size']} bytes")
    print(f"   ✓ Checksums match: {metadata['checksums_match']}")
    print(f"   ✓ Record counts: {metadata['record_counts']}")

    # List backups
    print("\n2. Listing backups...")
    backups = manager.list_backups()
    print(f"   ✓ Found {len(backups)} backups:")
    for backup in backups[:3]:
        print(f"     - {backup['backup_name']} ({backup['created_at']})")

    # Verify integrity
    print("\n3. Verifying database integrity...")
    integrity_ok = manager._verify_integrity()
    print(f"   ✓ Integrity check: {'PASSED' if integrity_ok else 'FAILED'}")

    print("\n✅ Backup system test complete!")
