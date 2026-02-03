#!/usr/bin/env python3
"""
Verification script for Feature #25:
"Orchestrator reads test plan from database"

This script creates a comprehensive test that verifies the Test Orchestrator
can read an approved test plan from the uat_test_plan table by cycle_id.

Verification Steps:
1. Create approved test plan in database with cycle_id='test-001'
2. Run orchestrator with cycle_id='test-001'
3. Verify orchestrator connects to uat_tests.db
4. Verify orchestrator reads test plan record
5. Verify orchestrator validates approved=true
6. Verify orchestrator retrieves test_prd document
7. Verify orchestrator parses test_prd successfully
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add custom directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DatabaseManager, UATTestPlan, get_db_manager
from orchestrator import TestOrchestrator, create_orchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_test_plan_data():
    """Create sample test plan data for testing."""
    return {
        'project_name': 'UAT AutoCoder Plugin',
        'cycle_id': 'test-001',
        'total_features_completed': 16,
        'journeys_identified': [
            'authentication',
            'payment',
            'onboarding',
            'admin',
            'reporting'
        ],
        'recommended_phases': [
            'smoke',
            'functional',
            'regression',
            'uat'
        ],
        'test_prd': '''# UAT Test Plan - Cycle test-001

## Test Phases

### Smoke Tests
Quick smoke tests to verify core functionality:
- User can log in
- Dashboard loads
- Basic navigation works

### Functional Tests
Test each user journey in detail:
- Authentication flow
- Payment processing
- User onboarding
- Admin functions
- Report generation

### Regression Tests
Verify existing features still work:
- All completed features
- Integration points
- Data consistency

### UAT Tests
End-to-end user acceptance testing:
- Real-world scenarios
- User workflows
- Business requirements

## User Journeys

### Authentication Journey
Tests for user authentication:
- Login with valid credentials
- Login with invalid credentials
- Password reset flow
- Session management

### Payment Journey
Tests for payment processing:
- Create payment
- Process payment
- Handle payment failures
- Refund processing

### Onboarding Journey
Tests for new user onboarding:
- Account creation
- Email verification
- Profile setup
- First login experience

## Test Execution Strategy

- Parallel execution with 3-5 agents
- Priority-based ordering
- Dependency handling
- Retry on failure (max 1 retry)
- Screenshot and video on failure

## Success Criteria

- All smoke tests pass
- 90%+ functional tests pass
- No critical regressions
- All UAT scenarios validated
''',
        'approved': True
    }


def cleanup_test_data(db: DatabaseManager):
    """Clean up test data from previous runs."""
    logger.info("Cleaning up test data...")

    try:
        with db.uat_session() as session:
            # Delete test plan if exists
            existing = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == 'test-001'
            ).first()

            if existing:
                session.delete(existing)
                logger.info("Deleted existing test plan for cycle_id='test-001'")

    except Exception as e:
        logger.warning(f"Cleanup warning: {e}")


def verify_feature_25():
    """Comprehensive verification of Feature #25."""

    print("\n" + "=" * 80)
    print("FEATURE #25 VERIFICATION - Orchestrator reads test plan from database")
    print("=" * 80)

    verification_results = []

    # ============================================================================
    # CHECK 1: Create approved test plan in database
    # ============================================================================
    print("\n[CHECK 1] Creating approved test plan in database with cycle_id='test-001'...")

    db = get_db_manager()
    cleanup_test_data(db)

    try:
        plan_data = create_test_plan_data()

        with db.uat_session() as session:
            new_plan = UATTestPlan(**plan_data)
            session.add(new_plan)
            session.flush()  # Get the ID

            plan_id = new_plan.id
            print(f"  ✓ Test plan created with ID: {plan_id}")
            print(f"    - cycle_id: {plan_data['cycle_id']}")
            print(f"    - approved: {plan_data['approved']}")
            print(f"    - journeys: {len(plan_data['journeys_identified'])}")
            print(f"    - phases: {len(plan_data['recommended_phases'])}")

        verification_results.append(("Create test plan", True, None))

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        verification_results.append(("Create test plan", False, str(e)))
        return False

    # ============================================================================
    # CHECK 2: Run orchestrator with cycle_id='test-001'
    # ============================================================================
    print("\n[CHECK 2] Creating orchestrator and reading test plan...")

    try:
        orchestrator = create_orchestrator()
        print(f"  ✓ Orchestrator created")
        print(f"    - Database: {orchestrator.db.uat_db_path}")

        # Read the test plan
        plan = orchestrator.read_test_plan('test-001')
        print(f"  ✓ Test plan read successfully")
        print(f"    - project_name: {plan['project_name']}")
        print(f"    - cycle_id: {plan['cycle_id']}")
        print(f"    - approved: {plan['approved']}")

        verification_results.append(("Run orchestrator", True, None))

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        verification_results.append(("Run orchestrator", False, str(e)))
        return False

    # ============================================================================
    # CHECK 3: Verify orchestrator connects to uat_tests.db
    # ============================================================================
    print("\n[CHECK 3] Verifying database connection...")

    try:
        # Check database file exists
        db_path = orchestrator.db.uat_db_path
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found: {db_path}")

        print(f"  ✓ Database file exists: {db_path}")

        # Verify we can query the database
        with db.uat_session() as session:
            result = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == 'test-001'
            ).first()

            if not result:
                raise ValueError("Could not query test plan from database")

            print(f"  ✓ Database query successful")
            print(f"    - Retrieved plan ID: {result.id}")

        verification_results.append(("Database connection", True, None))

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        verification_results.append(("Database connection", False, str(e)))
        return False

    # ============================================================================
    # CHECK 4: Verify orchestrator reads test plan record
    # ============================================================================
    print("\n[CHECK 4] Verifying test plan record read...")

    try:
        # Check all expected fields are present
        expected_fields = [
            'id', 'project_name', 'cycle_id', 'total_features_completed',
            'journeys_identified', 'recommended_phases', 'test_prd',
            'approved', 'created_at'
        ]

        missing_fields = []
        for field in expected_fields:
            if field not in plan:
                missing_fields.append(field)

        if missing_fields:
            raise ValueError(f"Missing fields: {missing_fields}")

        print(f"  ✓ All expected fields present ({len(expected_fields)} fields)")

        # Verify data integrity
        if plan['cycle_id'] != 'test-001':
            raise ValueError(f"Wrong cycle_id: {plan['cycle_id']}")

        if not plan['approved']:
            raise ValueError("Plan should be approved")

        print(f"  ✓ Data integrity verified")
        print(f"    - cycle_id matches: {plan['cycle_id'] == 'test-001'}")
        print(f"    - approved status: {plan['approved']}")

        verification_results.append(("Read test plan record", True, None))

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        verification_results.append(("Read test plan record", False, str(e)))
        return False

    # ============================================================================
    # CHECK 5: Verify orchestrator validates approved=true
    # ============================================================================
    print("\n[CHECK 5] Verifying approved=true validation...")

    try:
        # Test 1: Approved plan should work
        plan = orchestrator.read_test_plan('test-001')
        if not plan['approved']:
            raise ValueError("Expected approved=True")
        print(f"  ✓ Approved plan accepted")

        # Test 2: Unapproved plan should be rejected
        with db.uat_session() as session:
            unapproved_plan = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == 'test-001'
            ).first()
            unapproved_plan.approved = False

        try:
            # Create new orchestrator to clear cached plan
            orch2 = create_orchestrator()
            orch2.read_test_plan('test-001')
            raise ValueError("Should have rejected unapproved plan")
        except RuntimeError as e:
            if 'not approved' in str(e):
                print(f"  ✓ Unapproved plan rejected correctly")
            else:
                raise

        # Reset approved status
        with db.uat_session() as session:
            plan_obj = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == 'test-001'
            ).first()
            plan_obj.approved = True

        verification_results.append(("Validate approved=true", True, None))

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        verification_results.append(("Validate approved=true", False, str(e)))
        return False

    # ============================================================================
    # CHECK 6: Verify orchestrator retrieves test_prd document
    # ============================================================================
    print("\n[CHECK 6] Verifying test_prd document retrieval...")

    try:
        # Get test_prd via get_test_prd method
        test_prd = orchestrator.get_test_prd()
        print(f"  ✓ test_prd retrieved")
        print(f"    - Length: {len(test_prd)} characters")
        print(f"    - Preview: {test_prd[:100]}...")

        # Verify test_prd is not empty
        if not test_prd:
            raise ValueError("test_prd is empty")

        # Verify test_prd is a string
        if not isinstance(test_prd, str):
            raise ValueError(f"test_prd is not a string: {type(test_prd)}")

        print(f"  ✓ test_prd is valid non-empty string")

        # Verify test_prd contains expected content
        if 'Smoke Tests' not in test_prd:
            raise ValueError("test_prd missing expected content")

        print(f"  ✓ test_prd contains expected content")

        verification_results.append(("Retrieve test_prd document", True, None))

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        verification_results.append(("Retrieve test_prd document", False, str(e)))
        return False

    # ============================================================================
    # CHECK 7: Verify orchestrator parses test_prd successfully
    # ============================================================================
    print("\n[CHECK 7] Verifying test_prd parsing...")

    try:
        parsed = orchestrator.parse_test_prd()
        print(f"  ✓ test_prd parsed successfully")
        print(f"    - Lines: {parsed['line_count']}")
        print(f"    - Sections: {parsed['section_count']}")
        print(f"    - Has phases: {parsed['has_phases']}")
        print(f"    - Has journeys: {parsed['has_journeys']}")
        print(f"    - Validation status: {parsed['validation_status']}")

        # Verify parsing results
        if parsed['line_count'] == 0:
            raise ValueError("No lines in parsed test_prd")

        if parsed['section_count'] == 0:
            raise ValueError("No sections found in test_prd")

        if parsed['validation_status'] == 'invalid':
            raise ValueError("test_prd validation status is 'invalid'")

        print(f"  ✓ Parsing results valid")

        # Verify sections
        sections = parsed['sections']
        if len(sections) == 0:
            raise ValueError("No sections extracted")

        print(f"  ✓ Sections extracted: {list(sections.keys())[:3]}...")

        verification_results.append(("Parse test_prd successfully", True, None))

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        verification_results.append(("Parse test_prd successfully", False, str(e)))
        return False

    # ============================================================================
    # BONUS CHECK: Validate plan readiness
    # ============================================================================
    print("\n[BONUS CHECK] Validating overall plan readiness...")

    try:
        readiness = orchestrator.validate_plan_readiness()
        print(f"  ✓ Plan readiness validated")
        print(f"    - Is ready: {readiness['is_ready']}")
        print(f"    - Checks passed: {sum(1 for v in readiness['checks'].values() if v is True)}/{len(readiness['checks'])}")

        for check, result in readiness['checks'].items():
            status = "✓" if result else "✗"
            print(f"    {status} {check}: {result}")

        verification_results.append(("Plan readiness validation", True, None))

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        verification_results.append(("Plan readiness validation", False, str(e)))

    # ============================================================================
    # SUMMARY
    # ============================================================================
    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result, _ in verification_results if result)
    total = len(verification_results)

    print(f"\nTotal Checks: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")

    print("\nDetailed Results:")
    for check_name, result, error in verification_results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {check_name}")
        if error:
            print(f"    Error: {error}")

    if passed == total:
        print("\n" + "=" * 80)
        print("✓ ALL VERIFICATION CHECKS PASSED")
        print("=" * 80)
        print("\nFeature #25 is WORKING CORRECTLY.")
        print("The Test Orchestrator successfully:")
        print("  - Connects to uat_tests.db")
        print("  - Reads test plans by cycle_id")
        print("  - Validates approval status")
        print("  - Retrieves test_prd documents")
        print("  - Parses test_prd structure")
        return True
    else:
        print("\n" + "=" * 80)
        print("✗ SOME CHECKS FAILED")
        print("=" * 80)
        print(f"\n{total - passed} out of {total} checks failed.")
        print("Feature #25 is NOT working correctly.")
        return False


if __name__ == '__main__':
    try:
        success = verify_feature_25()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.exception("Unexpected error during verification")
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        sys.exit(1)
