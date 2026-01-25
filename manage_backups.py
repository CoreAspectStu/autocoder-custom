#!/usr/bin/env python3
"""
Feature Database Backup Management Script
==========================================

Command-line tool to manage features.db backups.

Usage:
    python manage_backups.py list              # List all backups
    python manage_backups.py status             # Show backup status
    python manage_backups.py backup             # Create manual backup
    python manage_backups.py restore <file>     # Restore from backup
    python manage_backups.py cleanup            # Remove old backups
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from api.database_backup import (
    backup_features_db,
    list_backups,
    restore_from_backup,
    backup_project_summary,
    cleanup_old_backups,
)


def cmd_list(args):
    """List all backups for a project."""
    project_path = Path(args.project)

    if not project_path.exists():
        print(f"❌ Project path does not exist: {project_path}")
        return 1

    backups = list_backups(project_path)

    if not backups:
        print(f"No backups found for {project_path.name}")
        return 0

    print(f"\n📦 Backups for {project_path.name}:\n")

    for backup in backups:
        status = "✅" if backup["feature_count"] else "⚠️"
        print(f"{status} {backup['filename']}")
        print(f"   Features: {backup['feature_count']}")
        print(f"   Size: {backup['size_mb']} MB")
        if backup.get("timestamp"):
            print(f"   Created: {backup['timestamp']}")
        if backup.get("reason"):
            print(f"   Reason: {backup['reason']}")
        print()

    return 0


def cmd_status(args):
    """Show backup status summary."""
    project_path = Path(args.project)

    if not project_path.exists():
        print(f"❌ Project path does not exist: {project_path}")
        return 1

    summary = backup_project_summary(project_path)

    print(f"\n📊 Backup Status for {project_path.name}:\n")
    print(f"Features DB exists: {'✅' if summary['features_db_exists'] else '❌'}")
    print(f"Backup directory: {'✅' if summary['backup_dir_exists'] else '❌'}")
    print(f"Total backups: {summary['backup_count']}")
    print(f"Total size: {summary['total_backup_size_mb']} MB")

    if summary["latest_backup"]:
        print(f"\n📅 Latest Backup:")
        print(f"   File: {summary['latest_backup']['filename']}")
        print(f"   Size: {summary['latest_backup']['size_mb']} MB")
        print(f"   Created: {summary['latest_backup']['timestamp']}")
    else:
        print("\n⚠️  No backups found")

    return 0


def cmd_backup(args):
    """Create a manual backup."""
    project_path = Path(args.project)
    reason = args.reason or "manual"

    if not project_path.exists():
        print(f"❌ Project path does not exist: {project_path}")
        return 1

    print(f"Creating backup for {project_path.name}...")

    backup_path = backup_features_db(project_path, reason=reason)

    if backup_path:
        print(f"✅ Backup created: {backup_path.name}")
        print(f"   Size: {backup_path.stat().st_size / 1024:.1f} KB")
        return 0
    else:
        print("❌ Backup failed")
        return 1


def cmd_restore(args):
    """Restore from a backup."""
    project_path = Path(args.project)
    backup_file = args.backup

    if not project_path.exists():
        print(f"❌ Project path does not exist: {project_path}")
        return 1

    print(f"Restoring {project_path.name} from {backup_file}...")
    print("⚠️  Current features.db will be backed up as emergency backup")

    if restore_from_backup(project_path, backup_file):
        print("✅ Restore completed successfully")
        return 0
    else:
        print("❌ Restore failed")
        return 1


def cmd_cleanup(args):
    """Remove old backups beyond retention limit."""
    project_path = Path(args.project)
    keep = args.keep

    if not project_path.exists():
        print(f"❌ Project path does not exist: {project_path}")
        return 1

    print(f"Cleaning up old backups (keeping last {keep})...")

    removed = cleanup_old_backups(project_path, keep=keep)

    if removed:
        print(f"✅ Removed {len(removed)} old backup(s):")
        for backup in removed:
            print(f"   - {backup.name}")
        return 0
    else:
        print("✅ No old backups to remove")
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Manage features.db backups",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python manage_backups.py list /path/to/project
  python manage_backups.py status /path/to/project
  python manage_backups.py backup /path/to/project --reason "before_changes"
  python manage_backups.py restore /path/to/project features_598_20260125.db
  python manage_backups.py cleanup /path/to/project --keep 10
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    subparsers.add_parser("list", help="List all backups")
    parser.set_defaults(func=cmd_list)

    # status command
    subparsers.add_parser("status", help="Show backup status")
    parser.set_defaults(func=cmd_status)

    # backup command
    backup_parser = subparsers.add_parser("backup", help="Create a manual backup")
    backup_parser.add_argument("project", help="Path to project directory")
    backup_parser.add_argument("--reason", default="manual", help="Reason for backup")
    parser.set_defaults(func=cmd_backup)

    # restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("project", help="Path to project directory")
    restore_parser.add_argument("backup", help="Backup file to restore from")
    parser.set_defaults(func=cmd_restore)

    # cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Remove old backups")
    cleanup_parser.add_argument("project", help="Path to project directory")
    cleanup_parser.add_argument("--keep", type=int, default=20, help="Number of backups to keep (default: 20)")
    parser.set_defaults(func=cmd_cleanup)

    # Parse arguments
    args = parser.parse_args()

    if not hasattr(args, 'func'):
        parser.print_help()
        return 1

    # Set project argument for list/status commands if not provided
    if args.command in ["list", "status"] and not hasattr(args, "project"):
        # Try to get from environment
        import os
        project = os.environ.get("PROJECT_DIR")
        if not project:
            print("❌ Error: project path required (or set PROJECT_DIR environment variable)")
            parser.print_help()
            return 1
        args.project = project

    # Execute command
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
