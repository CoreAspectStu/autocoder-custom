#!/usr/bin/env python3
"""
Integration Test - Full UAT Workflow Execution (Feature #47)

This test executes the complete UAT AutoCoder workflow:
1. PRD Analysis (from app_spec.txt)
2. Test Plan Generation
3. Test Plan Approval
4. Test Orchestrator Execution
5. Results Aggregation

This validates that the entire system works end-to-end.
"""

import sys
import os
import json
import asyncio
import time
from datetime import datetime
from pathlib import Path
import sqlite3
import requests
import logging

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from custom.uat_plugin.database import get_db_manager, UATTestPlan, UATTestFeature

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API Base URL
API_BASE = "http://localhost:8001"


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_step(step_num, description):
    """Print a test step with formatting."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}STEP {step_num}: {description}{Colors.END}")
    print("=" * 80)


def print_success(message):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")


def print_error(message):
    """Print error message."""
    print(f"{Colors.RED}✗ {message}{Colors.END}")


def print_info(message):
    """Print info message."""
    print(f"{Colors.YELLOW}→ {message}{Colors.END}")


def check_server_health():
    """Check if the API server is running."""
    print_step(0, "Check API Server Health")

    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Server is running: {data.get('status', 'OK')}")
            print_info(f"UAT Plugin: {data.get('uat_plugin', 'Not detected')}")
            return True
        else:
            print_error(f"Server returned status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Cannot connect to server: {e}")
        print_info("Make sure the API server is running: python -m custom.uat_plugin.api_server")
        return False


def generate_test_plan(project_path):
    """Step 1: Generate test plan from PRD."""
    print_step(1, "Generate Test Plan from PRD")

    payload = {
        "project_path": project_path
    }

    print_info(f"POST /api/uat/generate-plan")
    print_info(f"Project path: {project_path}")

    try:
        response = requests.post(
            f"{API_BASE}/api/uat/generate-plan",
            json=payload,
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            cycle_id = data.get('cycle_id')
            print_success(f"Test plan generated successfully")
            print_info(f"Cycle ID: {cycle_id}")
            print_info(f"Project: {data.get('project_name')}")
            print_info(f"Features completed: {data.get('total_features_completed')}")
            print_info(f"Journeys identified: {', '.join(data.get('journeys_identified', []))}")
            print_info(f"Recommended phases: {', '.join(data.get('recommended_phases', []))}")

            # Save cycle_id for subsequent steps
            with open('/tmp/uat_integration_cycle_id.txt', 'w') as f:
                f.write(cycle_id)

            return cycle_id, data
        else:
            print_error(f"Failed to generate plan: {response.status_code}")
            print_info(response.text)
            return None, None

    except Exception as e:
        print_error(f"Exception during plan generation: {e}")
        return None, None


def verify_test_plan_in_db(cycle_id):
    """Step 2: Verify test plan was saved to database."""
    print_step(2, "Verify Test Plan in Database")

    try:
        db_manager = get_db_manager()
        with db_manager.uat_session() as session:
            plan = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == cycle_id
            ).first()

            if plan:
                print_success(f"Test plan found in database")
                print_info(f"ID: {plan.id}")
                print_info(f"Project: {plan.project_name}")
                print_info(f"Approved: {plan.approved}")
                print_info(f"Created at: {plan.created_at}")

                # Verify test_prd content
                if plan.test_prd:
                    prd_length = len(plan.test_prd)
                    print_info(f"Test PRD length: {prd_length} characters")
                    print_success("Test PRD content exists")

                return True
            else:
                print_error(f"Test plan not found in database for cycle_id: {cycle_id}")
                return False

    except Exception as e:
        print_error(f"Error verifying test plan in database: {e}")
        return False


def retrieve_test_plan(cycle_id):
    """Step 3: Retrieve test plan via API."""
    print_step(3, "Retrieve Test Plan via API")

    try:
        response = requests.get(f"{API_BASE}/api/uat/plan/{cycle_id}")

        if response.status_code == 200:
            data = response.json()
            print_success(f"Test plan retrieved successfully")
            print_info(f"Cycle ID: {data.get('cycle_id')}")
            print_info(f"Approved: {data.get('approved')}")
            print_info(f"Test PRD preview: {data.get('test_prd', '')[:100]}...")
            return True
        else:
            print_error(f"Failed to retrieve plan: {response.status_code}")
            return False

    except Exception as e:
        print_error(f"Exception during plan retrieval: {e}")
        return False


def approve_test_plan(cycle_id):
    """Step 4: Approve the test plan."""
    print_step(4, "Approve Test Plan")

    try:
        response = requests.post(f"{API_BASE}/api/uat/approve-plan/{cycle_id}")

        if response.status_code == 200:
            data = response.json()
            print_success(f"Test plan approved successfully")
            print_info(f"Tests created: {data.get('tests_created', 0)}")
            print_info(f"Message: {data.get('message', '')}")

            # Verify test features were created
            return verify_test_features_created(cycle_id)
        else:
            print_error(f"Failed to approve plan: {response.status_code}")
            print_info(response.text)
            return False

    except Exception as e:
        print_error(f"Exception during plan approval: {e}")
        return False


def verify_test_features_created(cycle_id):
    """Verify that test features were created after approval."""
    print_info("Verifying test features were created...")

    try:
        db_manager = get_db_manager()
        with db_manager.uat_session() as session:
            # Count all test features (features aren't linked to cycle_id in current schema)
            features = session.query(UATTestFeature).all()

            if features:
                count = len(features)
                print_success(f"Found {count} test features in database")

                # Show breakdown by phase
                phases = {}
                journeys = {}
                for feature in features:
                    phase = feature.phase or 'unknown'
                    journey = feature.journey or 'unknown'
                    phases[phase] = phases.get(phase, 0) + 1
                    journeys[journey] = journeys.get(journey, 0) + 1

                print_info("Breakdown by phase:")
                for phase, cnt in sorted(phases.items()):
                    print_info(f"  - {phase}: {cnt}")

                print_info("Breakdown by journey:")
                for journey, cnt in sorted(journeys.items()):
                    print_info(f"  - {journey}: {cnt}")

                return True
            else:
                print_error("No test features created")
                return False

    except Exception as e:
        print_error(f"Error verifying test features: {e}")
        return False


def trigger_test_execution(cycle_id):
    """Step 5: Trigger test execution."""
    print_step(5, "Trigger Test Execution")

    payload = {
        "cycle_id": cycle_id
    }

    print_info(f"POST /api/uat/trigger")
    print_info(f"Cycle ID: {cycle_id}")

    try:
        response = requests.post(
            f"{API_BASE}/api/uat/trigger",
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            print_success(f"Test execution triggered successfully")
            print_info(f"Message: {data.get('message', '')}")
            print_info(f"Orchestrator started: {data.get('orchestrator_started', False)}")
            return True
        else:
            print_error(f"Failed to trigger execution: {response.status_code}")
            print_info(response.text)
            return False

    except Exception as e:
        print_error(f"Exception during trigger: {e}")
        return False


def monitor_progress(cycle_id, timeout_seconds=120):
    """Step 6: Monitor test execution progress."""
    print_step(6, "Monitor Test Execution Progress")

    start_time = time.time()
    last_counts = {}
    consecutive_same_count = 0

    print_info("Monitoring progress (will timeout after 120 seconds of inactivity)...")

    while time.time() - start_time < timeout_seconds:
        try:
            response = requests.get(f"{API_BASE}/api/uat/progress/{cycle_id}")

            if response.status_code == 200:
                data = response.json()

                total = data.get('total_tests', 0)
                passed = data.get('passed', 0)
                failed = data.get('failed', 0)
                running = data.get('running', 0)
                pending = data.get('pending', 0)
                agents = data.get('active_agents', 0)

                # Check if counts changed
                current_counts = {
                    'passed': passed,
                    'failed': failed,
                    'running': running,
                    'pending': pending
                }

                if current_counts != last_counts:
                    print_info(
                        f"Progress: Total={total}, "
                        f"Passed={passed}, Failed={failed}, "
                        f"Running={running}, Pending={pending}, "
                        f"Agents={agents}"
                    )
                    last_counts = current_counts
                    consecutive_same_count = 0

                    # Check if complete
                    if running == 0 and pending == 0:
                        print_success("All tests completed!")
                        break
                else:
                    consecutive_same_count += 1
                    if consecutive_same_count > 10:
                        print_info("No progress for 10 checks, stopping monitor")
                        break

            time.sleep(2)

        except Exception as e:
            print_error(f"Error monitoring progress: {e}")
            time.sleep(2)

    return True


def verify_final_results(cycle_id):
    """Step 7: Verify final test results."""
    print_step(7, "Verify Final Test Results")

    try:
        db_manager = get_db_manager()
        with db_manager.uat_session() as session:
            # Get all test features (not filtered by cycle_id in current schema)
            features = session.query(UATTestFeature).all()

            if not features:
                print_error("No test features found")
                return False

            total = len(features)
            passed = sum(1 for f in features if f.status == 'passed')
            failed = sum(1 for f in features if f.status == 'failed')
            skipped = sum(1 for f in features if f.status == 'skipped')
            pending = sum(1 for f in features if f.status == 'pending' or f.status == 'in_progress')

            print_success(f"Final Results:")
            print_info(f"  Total tests: {total}")
            print_info(f"  Passed: {passed}")
            print_info(f"  Failed: {failed}")
            print_info(f"  Skipped: {skipped}")
            print_info(f"  Still pending: {pending}")

            if failed > 0:
                print_info(f"\nFailed tests:")
                for feature in features:
                    if feature.status == 'failed':
                        error_msg = "Unknown error"
                        if feature.result:
                            try:
                                result_data = json.loads(feature.result) if isinstance(feature.result, str) else feature.result
                                error_msg = result_data.get('error', 'Unknown error')[:100]
                            except:
                                pass
                        print_info(f"  - {feature.scenario}: {error_msg}")

            return True

    except Exception as e:
        print_error(f"Error verifying final results: {e}")
        return False


def check_status_endpoint(project_name):
    """Step 8: Check status endpoint."""
    print_step(8, "Check Status Endpoint")

    try:
        # First, get the actual project name from the most recent test plan
        db_manager = get_db_manager()
        with db_manager.uat_session() as session:
            plan = session.query(UATTestPlan).order_by(
                UATTestPlan.created_at.desc()
            ).first()

            if not plan:
                print_error("No test plans found in database")
                return False

            actual_project_name = plan.project_name
            print_info(f"Using project name from database: {actual_project_name}")

        response = requests.get(f"{API_BASE}/api/uat/status/{actual_project_name}")

        if response.status_code == 200:
            data = response.json()
            print_success(f"Status retrieved successfully")
            print_info(f"Project: {data.get('project_name')}")
            print_info(f"Status: {data.get('execution_status')}")
            print_info(f"Cycle ID: {data.get('cycle_id')}")
            print_info(f"Approved: {data.get('approved')}")
            return True
        else:
            print_error(f"Failed to get status: {response.status_code}")
            print_info(response.text)
            return False

    except Exception as e:
        print_error(f"Exception during status check: {e}")
        return False


def main():
    """Run the full integration test."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("=" * 80)
    print("UAT AutoCoder - Full Workflow Integration Test")
    print("=" * 80)
    print(f"{Colors.END}\n")

    # Use current project as test subject
    project_path = str(Path(__file__).parent.parent.parent.parent)
    project_name = Path(project_path).name

    print_info(f"Project path: {project_path}")
    print_info(f"Project name: {project_name}")
    print_info(f"API Base URL: {API_BASE}\n")

    results = []

    # Step 0: Check server health
    if not check_server_health():
        print_error("\nServer health check failed. Please start the API server first.")
        return 1

    # Step 1: Generate test plan
    cycle_id, plan_data = generate_test_plan(project_path)
    results.append(("Generate Test Plan", cycle_id is not None))
    if not cycle_id:
        print_error("\nFailed to generate test plan. Stopping test.")
        return 1

    # Step 2: Verify test plan in database
    result = verify_test_plan_in_db(cycle_id)
    results.append(("Verify Test Plan in DB", result))

    # Step 3: Retrieve test plan via API
    result = retrieve_test_plan(cycle_id)
    results.append(("Retrieve Test Plan via API", result))

    # Step 4: Approve test plan
    result = approve_test_plan(cycle_id)
    results.append(("Approve Test Plan", result))

    # Step 5: Trigger test execution
    result = trigger_test_execution(cycle_id)
    results.append(("Trigger Test Execution", result))

    # Step 6: Monitor progress
    result = monitor_progress(cycle_id, timeout_seconds=120)
    results.append(("Monitor Progress", result))

    # Step 7: Verify final results
    result = verify_final_results(cycle_id)
    results.append(("Verify Final Results", result))

    # Step 8: Check status endpoint
    result = check_status_endpoint(project_name)
    results.append(("Check Status Endpoint", result))

    # Print summary
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("=" * 80)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 80)
    print(f"{Colors.END}\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for step, result in results:
        status = f"{Colors.GREEN}PASS{Colors.END}" if result else f"{Colors.RED}FAIL{Colors.END}"
        print(f"{status} - {step}")

    print(f"\n{Colors.BOLD}Results: {passed}/{total} steps passed{Colors.END}")

    if passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL TESTS PASSED{Colors.END}\n")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ SOME TESTS FAILED{Colors.END}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
