#!/usr/bin/env python3
"""
Migration script to add 'mode' column to assistant.db conversations table.

This adds a 'mode' column (default 'dev') to separate Dev and UAT conversation contexts.
Run this once per project to update existing assistant.db files.

Usage:
    python assistant_db_add_mode_column.py /path/to/project/directory
"""

import sys
from pathlib import Path

def add_mode_column(project_dir: Path) -> bool:
    """Add mode column to existing assistant.db."""
    try:
        # Import SQLAlchemy
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        db_path = project_dir / "assistant.db"
        if not db_path.exists():
            print(f"❌ No assistant.db found at {db_path}")
            return False

        print(f"📂 Migrating {db_path}...")

        # Create engine
        engine = create_engine(f"sqlite:///{db_path}")

        # Check if column already exists
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA table_info(conversations)"))
            columns = [row[1] for row in result.fetchall()]
            if 'mode' in columns:
                print("✅ Column 'mode' already exists - nothing to do")
                return True

        # Add the column
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE conversations ADD COLUMN mode VARCHAR(10) DEFAULT 'dev' NOT NULL"))
            conn.commit()

        # Create index on mode for performance
        with engine.connect() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_conversations_mode ON conversations (mode)"))
            conn.commit()

        print("✅ Successfully added 'mode' column to conversations table")
        print(f"   - All existing conversations set to mode='dev'")
        print(f"   - New UAT conversations will use mode='uat'")

        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python assistant_db_add_mode_column.py <project_directory>")
        print("\nExample:")
        print("  python assistant_db_add_mode_column.py /home/stu/.autocoder/projects/my-project")
        sys.exit(1)

    project_dir = Path(sys.argv[1])

    if not project_dir.exists():
        print(f"❌ Project directory does not exist: {project_dir}")
        sys.exit(1)

    if not project_dir.is_dir():
        print(f"❌ Path is not a directory: {project_dir}")
        sys.exit(1)

    success = add_mode_column(project_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
