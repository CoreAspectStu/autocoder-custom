"""
Add status_history column to uat_test_features table.

Migration script to add status tracking for Feature #20.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def upgrade():
    """Add status_history column to uat_test_features table."""
    db_path = Path.home() / ".autocoder" / "uat_autocoder" / "uat_tests.db"

    if not db_path.exists():
        logger.warning(f"Database not found at {db_path}")
        print(f"⚠ Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(uat_test_features)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'status_history' in columns:
            print("✓ status_history column already exists")
            return

        # Add status_history column
        cursor.execute("""
            ALTER TABLE uat_test_features
            ADD COLUMN status_history JSON
        """)

        conn.commit()
        print("✓ Added status_history column to uat_test_features")

        # Verify the column was added
        cursor.execute("PRAGMA table_info(uat_test_features)")
        columns = [col[1] for col in cursor.fetchall()]
        assert 'status_history' in columns, "Column was not added"

        print(f"✓ Verified: status_history column exists in {len(columns)} columns")

    except sqlite3.OperationalError as e:
        logger.error(f"Failed to add column: {e}")
        print(f"✗ Failed to add column: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print("Adding status_history column to uat_test_features...")
    upgrade()
    print("Migration complete!")
