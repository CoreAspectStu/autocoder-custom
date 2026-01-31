#!/usr/bin/env python3
"""
Enhanced verification script for Feature #18 with real test data.

This script:
1. Creates 20 test features in features.db
2. Marks 12 features as passing
3. Marks 8 features as not passing
4. Runs Test Planner Agent
5. Verifies agent returns exactly 12 passing features
6. Verifies results include id, name, category
"""

import sys
import os
import sqlite3
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def setup_test_data():
    """Create test features in features.db."""
    print("\n" + "=" * 60)
    print("SETTING UP TEST DATA")
    print("=" * 60)

    db_path = project_root / 'features.db'

    # Backup existing database
    if db_path.exists():
        backup_path = project_root / 'features.db.backup'
        print(f"Backing up existing database to {backup_path}")
        import shutil
        shutil.copy(db_path, backup_path)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check if features table exists, if not create it
    cursor.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name='features'
    """)

    if not cursor.fetchone():
        print("Creating features table...")
        cursor.execute("""
            CREATE TABLE features (
                id INTEGER PRIMARY KEY,
                priority INTEGER NOT NULL,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                steps TEXT NOT NULL,
                passes BOOLEAN NOT NULL DEFAULT 0,
                in_progress BOOLEAN NOT NULL DEFAULT 0,
                dependencies TEXT NOT NULL,
                complexity_score INTEGER,
                created_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
    else:
        print("Features table already exists, clearing test data...")
        # Delete any existing test features (those with "TEST_" in name)
        cursor.execute("DELETE FROM features WHERE name LIKE 'TEST_%'")
        conn.commit()

    # Create 20 test features
    print("Creating 20 test features...")

    passing_features = []
    non_passing_features = []

    for i in range(1, 21):
        is_passing = i <= 12  # First 12 are passing
        feature_name = f"TEST_Feature_{i:02d}"
        category = ['Database', 'MCP Server', 'Test Planner', 'Orchestrator', 'API'][i % 5]

        cursor.execute("""
            INSERT INTO features
            (priority, category, name, description, steps, passes, in_progress, dependencies, complexity_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            i,
            category,
            feature_name,
            f"Test feature {i} for verification",
            '[]',  # Empty steps JSON array
            1 if is_passing else 0,  # passes
            0,  # in_progress
            '[]',  # Empty dependencies JSON array
            i % 5 + 1  # complexity score
        ))

        if is_passing:
            passing_features.append((i, feature_name, category))
        else:
            non_passing_features.append((i, feature_name, category))

    conn.commit()
    conn.close()

    print(f"✓ Created {len(passing_features)} passing features")
    print(f"✓ Created {len(non_passing_features)} non-passing features")

    print("\nPassing features:")
    for fid, name, cat in passing_features[:5]:
        print(f"  - #{fid}: {name} ({cat})")
    if len(passing_features) > 5:
        print(f"  ... and {len(passing_features) - 5} more")

    return passing_features, non_passing_features


def run_verification(passing_features, non_passing_features):
    """Run the actual verification tests."""
    print("\n" + "=" * 60)
    print("RUNNING VERIFICATION TESTS")
    print("=" * 60)

    from custom.uat_plugin.database import get_passing_features, get_feature_statistics
    from custom.uat_plugin.test_planner import TestPlannerAgent

    all_passed = True

    # Test 1: Query returns correct count
    print("\nTest 1: Verify query returns exactly 12 passing features")
    results = get_passing_features()
    expected_count = len(passing_features)

    if len(results) == expected_count:
        print(f"✓ PASS: Query returned {len(results)} features (expected {expected_count})")
    else:
        print(f"✗ FAIL: Query returned {len(results)} features (expected {expected_count})")
        all_passed = False

    # Test 2: All returned features are actually passing
    print("\nTest 2: Verify all returned features have passes=True")
    non_passing_in_results = [f for f in results if not f.get('passes', False)]

    if not non_passing_in_results:
        print(f"✓ PASS: All {len(results)} returned features have passes=True")
    else:
        print(f"✗ FAIL: Found {len(non_passing_in_results)} non-passing features in results")
        all_passed = False

    # Test 3: Results include required fields
    print("\nTest 3: Verify results include id, name, category")
    if len(results) > 0:
        missing_fields = []
        required_fields = ['id', 'name', 'category']

        for field in required_fields:
            if field not in results[0]:
                missing_fields.append(field)

        if not missing_fields:
            print("✓ PASS: All required fields present (id, name, category)")
            print(f"  Sample feature:")
            print(f"    - ID: {results[0]['id']}")
            print(f"    - Name: {results[0]['name']}")
            print(f"    - Category: {results[0]['category']}")
        else:
            print(f"✗ FAIL: Missing fields: {', '.join(missing_fields)}")
            all_passed = False
    else:
        print("⚠ SKIP: No features returned to check fields")

    # Test 4: Feature statistics match
    print("\nTest 4: Verify feature statistics")
    stats = get_feature_statistics()

    if stats['passing'] == len(passing_features):
        print(f"✓ PASS: Statistics show {stats['passing']} passing features (correct)")
    else:
        print(f"✗ FAIL: Statistics show {stats['passing']} passing features (expected {len(passing_features)})")
        all_passed = False

    # Test 5: Test Planner Agent can use the data
    print("\nTest 5: Verify Test Planner Agent connects and queries features.db")
    try:
        agent = TestPlannerAgent()
        completed = agent.db.query_passing_features()

        if len(completed) == len(passing_features):
            print(f"✓ PASS: Test Planner queried {len(completed)} features (correct)")
        else:
            print(f"✗ FAIL: Test Planner queried {len(completed)} features (expected {len(passing_features)})")
            all_passed = False
    except Exception as e:
        print(f"✗ FAIL: Test Planner error: {e}")
        all_passed = False

    return all_passed


def cleanup_test_data():
    """Remove test features from database."""
    print("\n" + "=" * 60)
    print("CLEANING UP TEST DATA")
    print("=" * 60)

    db_path = project_root / 'features.db'
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Delete test features
    cursor.execute("DELETE FROM features WHERE name LIKE 'TEST_%'")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"✓ Deleted {deleted} test features from database")

    # Restore backup if it exists
    backup_path = project_root / 'features.db.backup'
    if backup_path.exists():
        print(f"Note: Backup file exists at {backup_path}")
        print("      (can be restored manually if needed)")


def main():
    """Run the complete verification with test data."""
    print("\n" + "=" * 60)
    print("FEATURE #18 ENHANCED VERIFICATION")
    print("Test Planner queries features.db with real data")
    print("=" * 60)

    try:
        # Setup test data
        passing, non_passing = setup_test_data()

        # Run verification
        all_passed = run_verification(passing, non_passing)

        # Cleanup
        cleanup_test_data()

        # Summary
        print("\n" + "=" * 60)
        print("FINAL RESULT")
        print("=" * 60)

        if all_passed:
            print("\n🎉 ALL VERIFICATION TESTS PASSED!")
            print("\nFeature #18 is working correctly:")
            print("  ✓ Test Planner Agent connects to features.db")
            print("  ✓ Query filters for passing features correctly")
            print("  ✓ Query returns exactly 12 features (as created)")
            print("  ✓ Results include id, name, category fields")
            return 0
        else:
            print("\n⚠ SOME TESTS FAILED - Review output above")
            return 1

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
