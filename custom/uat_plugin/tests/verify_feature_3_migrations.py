#!/usr/bin/env python3
"""
Verification Test for Feature #3: Database Migration System

This test verifies that:
1. Migrations directory exists with migration files
2. Initial migration creates all tables
3. Migration upgrade to latest version works
4. All tables and columns exist after migration
5. Migration downgrade one version works
6. Downgrade verification (tables dropped correctly)
7. Upgrade again restores schema

Usage:
    python3 verify_feature_3_migrations.py
"""

import os
import sys
import sqlite3
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ANSI color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_header(text):
    """Print a formatted header."""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")


def print_test(name):
    """Print test name."""
    print(f"{YELLOW}TEST:{RESET} {name}")


def print_pass(message):
    """Print passing test."""
    print(f"{GREEN}✓ PASS:{RESET} {message}")


def print_fail(message):
    """Print failing test."""
    print(f"{RED}✗ FAIL:{RESET} {message}")


def test_migrations_directory_exists():
    """Test 1: Check for migrations/ directory with migration files."""
    print_test("Migrations directory exists with migration files")

    migrations_dir = Path(__file__).parent.parent / 'migrations'

    if not migrations_dir.exists():
        print_fail("Migrations directory does not exist")
        return False

    print_pass(f"Migrations directory exists: {migrations_dir}")

    # Check for required files
    required_files = [
        'alembic.ini',
        'env.py',
        'script.py.mako',
        'manager.py'
    ]

    for file in required_files:
        file_path = migrations_dir / file
        if not file_path.exists():
            print_fail(f"Required file missing: {file}")
            return False
        print_pass(f"Required file exists: {file}")

    # Check for versions directory
    versions_dir = migrations_dir / 'versions'
    if not versions_dir.exists():
        print_fail("Versions directory does not exist")
        return False

    print_pass(f"Versions directory exists: {versions_dir}")

    # Check for initial migration
    initial_migration = versions_dir / '001_initial_schema.py'
    if not initial_migration.exists():
        print_fail("Initial migration file (001_initial_schema.py) does not exist")
        return False

    print_pass(f"Initial migration exists: {initial_migration}")

    return True


def test_initial_migration():
    """Test 2: Verify initial migration creates all tables."""
    print_test("Initial migration creates all tables")

    # Create a temporary database for testing
    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, 'test_uat.db')

    try:
        # Import migration manager
        from migrations.manager import MigrationManager

        # Override database path for testing
        original_db = os.path.expanduser('~/.autocoder/uat_tests.db')

        # Create migration manager with test database
        mgr = MigrationManager()
        mgr.config.set_main_option('sqlalchemy.url', f'sqlite:///{test_db}')

        # Run migration to create schema
        print("  → Running initial migration...")
        mgr.upgrade('head')

        # Connect to database and check tables
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()

        # Check uat_test_features table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='uat_test_features'")
        if not cursor.fetchone():
            print_fail("uat_test_features table was not created")
            conn.close()
            return False
        print_pass("uat_test_features table created")

        # Check uat_test_plan table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='uat_test_plan'")
        if not cursor.fetchone():
            print_fail("uat_test_plan table was not created")
            conn.close()
            return False
        print_pass("uat_test_plan table created")

        # Check alembic_version table (created by Alembic)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        if not cursor.fetchone():
            print_fail("alembic_version table was not created")
            conn.close()
            return False
        print_pass("alembic_version table created")

        conn.close()
        return True

    finally:
        # Cleanup
        if os.path.exists(test_db):
            os.remove(test_db)
        shutil.rmtree(temp_dir)


def test_tables_and_columns():
    """Test 3: Verify all tables and columns exist after migration."""
    print_test("All tables and columns exist after migration")

    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, 'test_uat.db')

    try:
        from migrations.manager import MigrationManager

        # Create schema
        mgr = MigrationManager()
        mgr.config.set_main_option('sqlalchemy.url', f'sqlite:///{test_db}')
        mgr.upgrade('head')

        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()

        # Expected columns for uat_test_features
        expected_features_columns = [
            'id', 'priority', 'phase', 'journey', 'scenario', 'description',
            'test_type', 'test_file', 'steps', 'expected_result', 'status',
            'dependencies', 'result', 'devlayer_card_id', 'started_at',
            'completed_at', 'created_at'
        ]

        # Get actual columns
        cursor.execute("PRAGMA table_info(uat_test_features)")
        actual_columns = [row[1] for row in cursor.fetchall()]

        # Check all expected columns exist
        for col in expected_features_columns:
            if col not in actual_columns:
                print_fail(f"Column '{col}' missing from uat_test_features")
                conn.close()
                return False
        print_pass(f"All {len(expected_features_columns)} columns exist in uat_test_features")

        # Expected columns for uat_test_plan
        expected_plan_columns = [
            'id', 'project_name', 'cycle_id', 'total_features_completed',
            'journeys_identified', 'recommended_phases', 'test_prd',
            'approved', 'created_at'
        ]

        cursor.execute("PRAGMA table_info(uat_test_plan)")
        actual_columns = [row[1] for row in cursor.fetchall()]

        for col in expected_plan_columns:
            if col not in actual_columns:
                print_fail(f"Column '{col}' missing from uat_test_plan")
                conn.close()
                return False
        print_pass(f"All {len(expected_plan_columns)} columns exist in uat_test_plan")

        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='uat_test_features'")
        indexes = [row[0] for row in cursor.fetchall()]

        expected_indexes = ['ix_uat_test_features_priority', 'ix_uat_test_features_phase',
                          'ix_uat_test_features_journey', 'ix_uat_test_features_status']

        for idx in expected_indexes:
            if idx not in indexes:
                print_fail(f"Index '{idx}' missing from uat_test_features")
                conn.close()
                return False
        print_pass(f"All {len(expected_indexes)} indexes exist on uat_test_features")

        conn.close()
        return True

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)
        shutil.rmtree(temp_dir)


def test_migration_downgrade():
    """Test 4: Migration downgrade one version works."""
    print_test("Migration downgrade one version works")

    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, 'test_uat.db')

    try:
        from migrations.manager import MigrationManager

        # Create schema
        mgr = MigrationManager()
        mgr.config.set_main_option('sqlalchemy.url', f'sqlite:///{test_db}')

        print("  → Upgrading to head...")
        mgr.upgrade('head')

        # Verify tables exist
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='uat_test_features'")
        has_features_before = cursor.fetchone() is not None
        conn.close()

        if not has_features_before:
            print_fail("Tables don't exist after upgrade")
            return False

        print_pass("Tables exist after upgrade")

        # Downgrade one version
        print("  → Downgrading one version...")
        mgr.downgrade('-1')

        # Verify tables are dropped
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='uat_test_features'")
        has_features_after = cursor.fetchone() is not None
        conn.close()

        if has_features_after:
            print_fail("Tables still exist after downgrade")
            return False

        print_pass("Tables dropped after downgrade")

        return True

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)
        shutil.rmtree(temp_dir)


def test_migration_upgrade_after_downgrade():
    """Test 5: Upgrade again restores schema after downgrade."""
    print_test("Upgrade again restores schema after downgrade")

    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, 'test_uat.db')

    try:
        from migrations.manager import MigrationManager

        mgr = MigrationManager()
        mgr.config.set_main_option('sqlalchemy.url', f'sqlite:///{test_db}')

        # Upgrade
        print("  → Initial upgrade...")
        mgr.upgrade('head')

        # Downgrade
        print("  → Downgrade...")
        mgr.downgrade('-1')

        # Upgrade again
        print("  → Re-upgrade...")
        result = mgr.upgrade('head')

        print_pass(f"Re-upgrade successful: {result}")

        # Verify tables exist again
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='uat_test_features'")
        if not cursor.fetchone():
            print_fail("uat_test_features table not restored after re-upgrade")
            conn.close()
            return False

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='uat_test_plan'")
        if not cursor.fetchone():
            print_fail("uat_test_plan table not restored after re-upgrade")
            conn.close()
            return False

        conn.close()
        print_pass("Tables restored after re-upgrade")

        return True

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)
        shutil.rmtree(temp_dir)


def test_migration_status():
    """Test 6: Migration status tracking works."""
    print_test("Migration status tracking works")

    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, 'test_uat.db')

    try:
        from migrations.manager import MigrationManager

        mgr = MigrationManager()
        mgr.config.set_main_option('sqlalchemy.url', f'sqlite:///{test_db}')

        # Check status before migration
        status = mgr.check_status()
        print(f"  → Status before migration: {status}")

        if status['current_revision'] is not None:
            print_fail("Current revision should be None before migration")
            return False

        print_pass("No current revision before migration")

        # Run migration
        mgr.upgrade('head')

        # Check status after migration
        status = mgr.check_status()
        print(f"  → Status after migration: {status}")

        if status['current_revision'] is None:
            print_fail("Current revision should not be None after migration")
            return False

        if status['current_revision'] != status['latest_revision']:
            print_fail(f"Current revision {status['current_revision']} != latest {status['latest_revision']}")
            return False

        if status['status'] != 'up to date':
            print_fail(f"Status should be 'up to date', got: {status['status']}")
            return False

        print_pass(f"Migration status correct: {status['current_revision']} (up to date)")

        return True

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)
        shutil.rmtree(temp_dir)


def main():
    """Run all verification tests."""
    print_header("FEATURE #3 VERIFICATION: Database Migration System")

    tests = [
        ("Migrations directory exists", test_migrations_directory_exists),
        ("Initial migration creates tables", test_initial_migration),
        ("All tables and columns exist", test_tables_and_columns),
        ("Migration downgrade works", test_migration_downgrade),
        ("Re-upgrade restores schema", test_migration_upgrade_after_downgrade),
        ("Migration status tracking", test_migration_status),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print_fail(f"Exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Print summary
    print_header("VERIFICATION SUMMARY")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print(f"\n{GREEN}✓ All tests passed! Feature #3 is complete.{RESET}")
        return 0
    else:
        print(f"\n{RED}✗ Some tests failed. Feature #3 needs work.{RESET}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
