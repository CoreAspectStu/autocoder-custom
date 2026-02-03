#!/usr/bin/env python3
"""
Verification script for Feature #18: Test Planner queries features.db

This script verifies that:
1. Test Planner Agent can connect to features.db
2. Test Planner Agent can query for passing features
3. Query returns correct feature data structure
4. Query filters correctly (only passing features)
5. Results include id, name, category fields
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_database_connection():
    """Test 1: Verify database can be connected to."""
    print("\n" + "=" * 60)
    print("TEST 1: Database Connection")
    print("=" * 60)

    try:
        from custom.uat_plugin.database import get_db_manager

        db = get_db_manager()
        print(f"✓ Database manager created")
        print(f"  Features DB path: {db.features_db_path}")
        print(f"  UAT Tests DB path: {db.uat_db_path}")

        # Check if features.db exists
        if os.path.exists(db.features_db_path):
            print(f"✓ features.db exists at {db.features_db_path}")
            return True
        else:
            print(f"✗ features.db not found at {db.features_db_path}")
            return False

    except Exception as e:
        print(f"✗ Error connecting to database: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_query_passing_features():
    """Test 2: Verify query for passing features works."""
    print("\n" + "=" * 60)
    print("TEST 2: Query Passing Features")
    print("=" * 60)

    try:
        from custom.uat_plugin.database import get_passing_features

        features = get_passing_features()
        print(f"✓ Query executed successfully")
        print(f"  Total passing features found: {len(features)}")

        if len(features) > 0:
            print(f"\n  First 5 features:")
            for feature in features[:5]:
                print(f"    - #{feature['id']}: {feature['name']} ({feature['category']})")
            if len(features) > 5:
                print(f"    ... and {len(features) - 5} more")
            return True
        else:
            print(f"  Note: No passing features found (expected for new project)")
            return True  # Not a failure - just means no features are passing yet

    except Exception as e:
        print(f"✗ Error querying passing features: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_feature_data_structure():
    """Test 3: Verify returned features have correct structure."""
    print("\n" + "=" * 60)
    print("TEST 3: Feature Data Structure")
    print("=" * 60)

    try:
        from custom.uat_plugin.database import get_passing_features

        features = get_passing_features()

        if len(features) == 0:
            print("  ⚠ No passing features to check (skipping structure check)")
            return True

        # Check first feature has required fields
        feature = features[0]
        required_fields = ['id', 'name', 'category', 'description', 'passes', 'in_progress']

        missing_fields = []
        for field in required_fields:
            if field not in feature:
                missing_fields.append(field)

        if missing_fields:
            print(f"✗ Missing required fields: {', '.join(missing_fields)}")
            print(f"  Available fields: {', '.join(feature.keys())}")
            return False
        else:
            print(f"✓ Feature has all required fields:")
            print(f"  - id: {feature['id']}")
            print(f"  - name: {feature['name']}")
            print(f"  - category: {feature['category']}")
            print(f"  - description: {feature['description'][:50]}...")
            print(f"  - passes: {feature['passes']}")
            print(f"  - in_progress: {feature['in_progress']}")
            return True

    except Exception as e:
        print(f"✗ Error checking feature structure: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_passing_filter():
    """Test 4: Verify only passing features are returned."""
    print("\n" + "=" * 60)
    print("TEST 4: Passing Filter Verification")
    print("=" * 60)

    try:
        from custom.uat_plugin.database import get_passing_features

        features = get_passing_features()

        if len(features) == 0:
            print("  ⚠ No passing features to check (skipping filter verification)")
            return True

        # Check all returned features have passes=True
        non_passing = [f for f in features if not f.get('passes', False)]

        if non_passing:
            print(f"✗ Found {len(non_passing)} non-passing features in results:")
            for feature in non_passing:
                print(f"    - #{feature['id']}: {feature['name']} (passes={feature['passes']})")
            return False
        else:
            print(f"✓ All {len(features)} returned features have passes=True")
            return True

    except Exception as e:
        print(f"✗ Error verifying passing filter: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_feature_statistics():
    """Test 5: Verify feature statistics query."""
    print("\n" + "=" * 60)
    print("TEST 5: Feature Statistics")
    print("=" * 60)

    try:
        from custom.uat_plugin.database import get_feature_statistics

        stats = get_feature_statistics()
        print(f"✓ Statistics query successful:")
        print(f"  - Total features: {stats['total']}")
        print(f"  - Passing features: {stats['passing']}")
        print(f"  - In progress features: {stats['in_progress']}")

        # Verify stats make sense
        if stats['passing'] > stats['total']:
            print(f"✗ Error: More passing than total features!")
            return False

        if stats['total'] > 0 and stats['passing'] == 0 and stats['in_progress'] == 0:
            print(f"  ⚠ All features are pending (expected for new project)")

        return True

    except Exception as e:
        print(f"✗ Error getting feature statistics: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_test_planner_integration():
    """Test 6: Verify Test Planner Agent uses database correctly."""
    print("\n" + "=" * 60)
    print("TEST 6: Test Planner Agent Integration")
    print("=" * 60)

    try:
        from custom.uat_plugin.test_planner import TestPlannerAgent

        # Create agent
        agent = TestPlannerAgent()
        print(f"✓ Test Planner Agent created")

        # Get completed features via agent
        completed_features = agent.db.query_passing_features()
        print(f"✓ Agent queried features.db successfully")
        print(f"  Found {len(completed_features)} completed features")

        # Verify agent can access feature data
        if len(completed_features) > 0:
            feature = completed_features[0]
            print(f"✓ Agent can access feature details:")
            print(f"  - Feature ID: {feature['id']}")
            print(f"  - Feature name: {feature['name']}")
            print(f"  - Feature category: {feature['category']}")

        return True

    except Exception as e:
        print(f"✗ Error in Test Planner integration: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("FEATURE #18 VERIFICATION")
    print("Test Planner queries features.db")
    print("=" * 60)

    tests = [
        ("Database Connection", test_database_connection),
        ("Query Passing Features", test_query_passing_features),
        ("Feature Data Structure", test_feature_data_structure),
        ("Passing Filter", test_passing_filter),
        ("Feature Statistics", test_feature_statistics),
        ("Test Planner Integration", test_test_planner_integration),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ Test '{test_name}' crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Feature #18 is working correctly.")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed. Review output above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
