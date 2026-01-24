#!/usr/bin/env python3
"""
Add timestamp tracking to features databases.

This migration adds:
- created_at: When the feature was added to the backlog
- completed_at: When the feature was marked as passing

Run this for each project to enable analytics.
"""

import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime

# Ensure we're running from the autocoder root
script_path = Path(__file__).resolve()
autocoder_root = script_path.parent.parent
os.chdir(autocoder_root)
if str(autocoder_root) not in sys.path:
    sys.path.insert(0, str(autocoder_root))


def migrate_features_db(db_path: Path) -> bool:
    """Add timestamp columns to features table."""
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(features)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'created_at' in columns and 'completed_at' in columns:
            print(f"✅ {db_path.name}: Timestamps already exist")
            conn.close()
            return True

        # Add created_at column (no default for SQLite ALTER TABLE)
        if 'created_at' not in columns:
            cursor.execute("""
                ALTER TABLE features
                ADD COLUMN created_at DATETIME
            """)
            # Set current time for all existing features
            cursor.execute("""
                UPDATE features
                SET created_at = CURRENT_TIMESTAMP
                WHERE created_at IS NULL
            """)
            print(f"✅ Added created_at to {db_path.name}")

        # Add completed_at column
        if 'completed_at' not in columns:
            cursor.execute("""
                ALTER TABLE features
                ADD COLUMN completed_at DATETIME
            """)
            print(f"✅ Added completed_at to {db_path.name}")

        # For features that are already passing, set completed_at to now
        cursor.execute("""
            UPDATE features
            SET completed_at = CURRENT_TIMESTAMP
            WHERE passes = 1 AND completed_at IS NULL
        """)
        updated = cursor.rowcount
        if updated > 0:
            print(f"   Set completed_at for {updated} already-passing features")

        conn.commit()
        conn.close()

        print(f"✅ {db_path.name}: Migration complete")
        return True

    except Exception as e:
        print(f"❌ Error migrating {db_path.name}: {e}")
        return False


def main():
    """Migrate all registered projects."""
    from registry import list_registered_projects

    projects = list_registered_projects()
    if not projects:
        print("❌ No projects found in registry")
        sys.exit(1)

    print(f"Found {len(projects)} projects")
    print("=" * 50)

    success_count = 0
    for name, info in projects.items():
        project_path = Path(info.get("path", ""))
        features_db = project_path / "features.db"

        if not features_db.exists():
            print(f"⚠️  {name}: No features.db found")
            continue

        if migrate_features_db(features_db):
            success_count += 1
        print()

    print("=" * 50)
    print(f"✅ Migrated {success_count}/{len(projects)} projects")


if __name__ == "__main__":
    main()
