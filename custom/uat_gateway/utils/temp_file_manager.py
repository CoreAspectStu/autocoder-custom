"""
Temporary File Manager - Manage cleanup of temporary test files

This module provides functionality to track and clean up temporary files
created during test execution, including:
- Playwright artifact directories (playwright-artifacts-*)
- Test-specific temp directories
- Browser context data
- Video and screenshot temp files

Feature #271: Cleans up temporary test files
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import TestExecutionError, handle_errors


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class TempFileStats:
    """Statistics about temporary files"""
    total_temp_dirs: int = 0
    total_temp_files: int = 0
    total_size_bytes: int = 0
    cleaned_dirs: int = 0
    cleaned_files: int = 0
    freed_space_bytes: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "total_temp_dirs": self.total_temp_dirs,
            "total_temp_files": self.total_temp_files,
            "total_size_mb": round(self.total_size_bytes / (1024 * 1024), 2),
            "cleaned_dirs": self.cleaned_dirs,
            "cleaned_files": self.cleaned_files,
            "freed_space_mb": round(self.freed_space_bytes / (1024 * 1024), 2),
            "errors": self.errors
        }


@dataclass
class CleanupConfig:
    """Configuration for temp file cleanup"""
    # Age-based cleanup: Remove files older than this many days
    max_age_days: int = 1

    # Size-based cleanup: Remove if temp dir exceeds this size (MB)
    max_temp_size_mb: int = 500

    # Count-based cleanup: Keep only this many recent temp dirs
    keep_recent_count: int = 10

    # Patterns to identify temp directories
    temp_dir_patterns: List[str] = field(default_factory=lambda: [
        "playwright-artifacts-*",
        "playwright-",
        "test-",
        "tmp*",
        ".tmp*"
    ])

    # Paths to search for temp files
    search_paths: List[str] = field(default_factory=lambda: [
        "/tmp",
        tempfile.gettempdir()
    ])

    # Whether to clean up immediately after test execution
    auto_cleanup_after_test: bool = True


# ============================================================================
# Temporary File Manager
# ============================================================================

class TempFileManager:
    """
    Manages cleanup of temporary files created during test execution

    Feature #271: Tracks and cleans up temporary test files

    Responsibilities:
    - Scan for temporary directories created by tests
    - Track age and size of temp files
    - Clean up old temp files based on policy
    - Provide statistics on cleanup operations
    """

    def __init__(self, config: Optional[CleanupConfig] = None):
        """
        Initialize temp file manager

        Args:
            config: Optional cleanup configuration
        """
        self.logger = get_logger("temp_file_manager")
        self.config = config or CleanupConfig()
        self._tracked_temp_dirs: Set[Path] = set()
        self._test_start_time: Optional[datetime] = None

    @handle_errors(component="temp_file_manager", reraise=False)
    def start_test_tracking(self) -> None:
        """
        Mark the start of a test execution

        Records the timestamp so temp files created during this
        test run can be identified and cleaned up later.
        """
        self._test_start_time = datetime.now()
        self.logger.debug("Started tracking test execution")

        # Scan for existing temp directories before test
        self._scan_existing_temp_dirs()

    def _scan_existing_temp_dirs(self) -> None:
        """Scan for existing temp directories before test execution"""
        self.logger.debug("Scanning for existing temp directories...")

        for search_path in self.config.search_paths:
            search_path_obj = Path(search_path)
            if not search_path_obj.exists():
                continue

            # Look for temp directories matching patterns
            for pattern in self.config.temp_dir_patterns:
                for temp_dir in search_path_obj.glob(pattern):
                    if temp_dir.is_dir():
                        self._tracked_temp_dirs.add(temp_dir)

        self.logger.debug(f"Found {len(self._tracked_temp_dirs)} existing temp directories")

    @handle_errors(component="temp_file_manager", reraise=False)
    def end_test_tracking_and_cleanup(self) -> TempFileStats:
        """
        End test tracking and clean up temp files

        This method:
        1. Identifies new temp directories created during test
        2. Cleans them up if auto_cleanup_after_test is enabled
        3. Returns statistics about cleanup operation

        Returns:
            TempFileStats with cleanup statistics
        """
        if self._test_start_time is None:
            self.logger.warning("No test tracking in progress (start_test_tracking not called)")
            return TempFileStats()

        self.logger.info("Test execution completed - checking for temp files...")

        # Scan for temp directories created during test
        new_temp_dirs = self._find_new_temp_dirs()

        stats = TempFileStats(
            total_temp_dirs=len(new_temp_dirs)
        )

        if self.config.auto_cleanup_after_test and new_temp_dirs:
            self.logger.info(f"Auto-cleanup enabled: cleaning up {len(new_temp_dirs)} temp directories")
            stats = self._cleanup_temp_dirs(new_temp_dirs, stats)
        elif new_temp_dirs:
            self.logger.info(f"Auto-cleanup disabled: found {len(new_temp_dirs)} temp directories")
            for temp_dir in new_temp_dirs:
                size = self._get_dir_size(temp_dir)
                stats.total_size_bytes += size
                stats.total_temp_files += self._count_files(temp_dir)
                self.logger.info(f"  - {temp_dir} ({self._format_size(size)})")

        # Reset tracking
        self._test_start_time = None
        self._tracked_temp_dirs.clear()

        return stats

    def _find_new_temp_dirs(self) -> List[Path]:
        """Find temp directories created during test execution"""
        new_temp_dirs = []

        current_temp_dirs = set()

        for search_path in self.config.search_paths:
            search_path_obj = Path(search_path)
            if not search_path_obj.exists():
                continue

            for pattern in self.config.temp_dir_patterns:
                for temp_dir in search_path_obj.glob(pattern):
                    if temp_dir.is_dir():
                        current_temp_dirs.add(temp_dir)

                        # Check if this is a new directory (created after test start)
                        if self._test_start_time:
                            creation_time = datetime.fromtimestamp(temp_dir.stat().st_ctime)
                            if creation_time >= self._test_start_time:
                                new_temp_dirs.append(temp_dir)
                                self.logger.debug(f"New temp directory: {temp_dir}")

        return new_temp_dirs

    @handle_errors(component="temp_file_manager", reraise=False)
    def cleanup_old_temp_files(self, max_age_days: Optional[int] = None) -> TempFileStats:
        """
        Clean up old temporary files based on age policy

        Args:
            max_age_days: Optional override for max age (uses config default if not specified)

        Returns:
            TempFileStats with cleanup statistics
        """
        age_threshold = max_age_days or self.config.max_age_days
        cutoff_time = datetime.now() - timedelta(days=age_threshold)

        self.logger.info(f"Cleaning up temp files older than {age_threshold} days...")

        stats = TempFileStats()

        for search_path in self.config.search_paths:
            search_path_obj = Path(search_path)
            if not search_path_obj.exists():
                continue

            for pattern in self.config.temp_dir_patterns:
                for temp_dir in search_path_obj.glob(pattern):
                    if not temp_dir.is_dir():
                        continue

                    stats.total_temp_dirs += 1

                    # Check if directory is old enough to clean up
                    mtime = datetime.fromtimestamp(temp_dir.stat().st_mtime)

                    if mtime < cutoff_time:
                        size = self._get_dir_size(temp_dir)
                        stats.total_size_bytes += size
                        stats.total_temp_files += self._count_files(temp_dir)

                        self.logger.info(
                            f"Cleaning up old temp directory: {temp_dir.name} "
                            f"(age: {(datetime.now() - mtime).days} days, "
                            f"size: {self._format_size(size)})"
                        )

                        # Remove the directory
                        try:
                            shutil.rmtree(temp_dir)
                            stats.cleaned_dirs += 1
                            stats.freed_space_bytes += size
                            self.logger.debug(f"✓ Removed: {temp_dir}")
                        except Exception as e:
                            error_msg = f"Failed to remove {temp_dir}: {e}"
                            stats.errors.append(error_msg)
                            self.logger.error(error_msg)

        self._log_summary(stats)
        return stats

    @handle_errors(component="temp_file_manager", reraise=False)
    def cleanup_temp_files_by_size(self, max_size_mb: Optional[int] = None) -> TempFileStats:
        """
        Clean up temp files based on size policy

        Removes temp directories until total size is below threshold,
        removing the oldest/largest directories first.

        Args:
            max_size_mb: Optional override for max size (uses config default if not specified)

        Returns:
            TempFileStats with cleanup statistics
        """
        size_threshold_mb = max_size_mb or self.config.max_temp_size_mb
        size_threshold_bytes = size_threshold_mb * 1024 * 1024

        self.logger.info(f"Cleaning up temp files if size exceeds {size_threshold_mb}MB...")

        stats = TempFileStats()

        # Find all temp directories with their sizes
        temp_dirs_with_size = []

        for search_path in self.config.search_paths:
            search_path_obj = Path(search_path)
            if not search_path_obj.exists():
                continue

            for pattern in self.config.temp_dir_patterns:
                for temp_dir in search_path_obj.glob(pattern):
                    if not temp_dir.is_dir():
                        continue

                    size = self._get_dir_size(temp_dir)
                    mtime = datetime.fromtimestamp(temp_dir.stat().st_mtime)

                    stats.total_temp_dirs += 1
                    stats.total_size_bytes += size
                    stats.total_temp_files += self._count_files(temp_dir)

                    temp_dirs_with_size.append((temp_dir, size, mtime))

        # Check if total size exceeds threshold
        total_size = sum(size for _, size, _ in temp_dirs_with_size)

        if total_size <= size_threshold_bytes:
            self.logger.info(
                f"Total temp size ({self._format_size(total_size)}) "
                f"is below threshold ({size_threshold_mb}MB) - no cleanup needed"
            )
            return stats

        self.logger.info(
            f"Total temp size ({self._format_size(total_size)}) "
            f"exceeds threshold ({size_threshold_mb}MB) - cleaning up..."
        )

        # Sort by modification time (oldest first) then by size (largest first)
        temp_dirs_with_size.sort(key=lambda x: (x[2], -x[1]))

        # Remove directories until size is below threshold
        for temp_dir, size, mtime in temp_dirs_with_size:
            if stats.total_size_bytes - stats.freed_space_bytes <= size_threshold_bytes:
                break

            try:
                shutil.rmtree(temp_dir)
                stats.cleaned_dirs += 1
                stats.freed_space_bytes += size
                self.logger.info(
                    f"✓ Removed {temp_dir.name} "
                    f"(age: {(datetime.now() - mtime).days} days, "
                    f"size: {self._format_size(size)})"
                )
            except Exception as e:
                error_msg = f"Failed to remove {temp_dir}: {e}"
                stats.errors.append(error_msg)
                self.logger.error(error_msg)

        self._log_summary(stats)
        return stats

    @handle_errors(component="temp_file_manager", reraise=False)
    def cleanup_keep_recent(self, keep_count: Optional[int] = None) -> TempFileStats:
        """
        Clean up temp files, keeping only the most recent ones

        Args:
            keep_count: Optional override for number of recent dirs to keep

        Returns:
            TempFileStats with cleanup statistics
        """
        keep = keep_count or self.config.keep_recent_count

        self.logger.info(f"Cleaning up temp files, keeping {keep} most recent...")

        stats = TempFileStats()

        # Find all temp directories with their modification times
        temp_dirs_with_mtime = []

        for search_path in self.config.search_paths:
            search_path_obj = Path(search_path)
            if not search_path_obj.exists():
                continue

            for pattern in self.config.temp_dir_patterns:
                for temp_dir in search_path_obj.glob(pattern):
                    if not temp_dir.is_dir():
                        continue

                    mtime = datetime.fromtimestamp(temp_dir.stat().st_mtime)
                    size = self._get_dir_size(temp_dir)

                    stats.total_temp_dirs += 1
                    stats.total_size_bytes += size
                    stats.total_temp_files += self._count_files(temp_dir)

                    temp_dirs_with_mtime.append((temp_dir, mtime, size))

        # Sort by modification time (newest first)
        temp_dirs_with_mtime.sort(key=lambda x: x[1], reverse=True)

        # Keep the N most recent, remove the rest
        dirs_to_remove = temp_dirs_with_mtime[keep:]

        for temp_dir, mtime, size in dirs_to_remove:
            try:
                shutil.rmtree(temp_dir)
                stats.cleaned_dirs += 1
                stats.freed_space_bytes += size
                self.logger.info(
                    f"✓ Removed {temp_dir.name} "
                    f"(age: {(datetime.now() - mtime).days} days, "
                    f"size: {self._format_size(size)})"
                )
            except Exception as e:
                error_msg = f"Failed to remove {temp_dir}: {e}"
                stats.errors.append(error_msg)
                self.logger.error(error_msg)

        self._log_summary(stats)
        return stats

    def _cleanup_temp_dirs(self, temp_dirs: List[Path], stats: TempFileStats) -> TempFileStats:
        """Clean up specific temp directories"""
        for temp_dir in temp_dirs:
            size = self._get_dir_size(temp_dir)
            stats.total_size_bytes += size
            stats.total_temp_files += self._count_files(temp_dir)

            try:
                shutil.rmtree(temp_dir)
                stats.cleaned_dirs += 1
                stats.freed_space_bytes += size
                self.logger.info(f"✓ Cleaned up: {temp_dir} ({self._format_size(size)})")
            except Exception as e:
                error_msg = f"Failed to remove {temp_dir}: {e}"
                stats.errors.append(error_msg)
                self.logger.error(error_msg)

        self._log_summary(stats)
        return stats

    def _get_dir_size(self, path: Path) -> int:
        """Get total size of a directory in bytes"""
        total_size = 0
        try:
            for item in path.rglob('*'):
                if item.is_file():
                    total_size += item.stat().st_size
        except Exception:
            pass  # Some files may not be accessible
        return total_size

    def _count_files(self, path: Path) -> int:
        """Count total number of files in a directory"""
        count = 0
        try:
            for item in path.rglob('*'):
                if item.is_file():
                    count += 1
        except Exception:
            pass
        return count

    def _format_size(self, size_bytes: int) -> str:
        """Format size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"

    def _log_summary(self, stats: TempFileStats) -> None:
        """Log cleanup summary"""
        self.logger.info("=" * 60)
        self.logger.info("Temp File Cleanup Summary:")
        self.logger.info(f"  Total temp dirs found: {stats.total_temp_dirs}")
        self.logger.info(f"  Dirs cleaned: {stats.cleaned_dirs}")
        self.logger.info(f"  Files affected: {stats.total_temp_files}")
        self.logger.info(f"  Space freed: {self._format_size(stats.freed_space_bytes)}")

        if stats.errors:
            self.logger.warning(f"  Errors encountered: {len(stats.errors)}")
            for error in stats.errors[:3]:  # Log first 3 errors
                self.logger.warning(f"    - {error}")

        self.logger.info("=" * 60)


# ============================================================================
# Convenience Functions
# ============================================================================

def create_temp_manager() -> TempFileManager:
    """Create a temp file manager with default configuration"""
    return TempFileManager()


def cleanup_temp_files() -> TempFileStats:
    """
    Convenience function to clean up temp files with default settings

    Returns:
        TempFileStats with cleanup statistics
    """
    manager = TempFileManager()
    return manager.cleanup_old_temp_files()
