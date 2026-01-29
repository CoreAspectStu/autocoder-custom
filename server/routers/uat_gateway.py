"""
UAT Gateway Integration Router

Provides API endpoints to trigger UAT testing cycles and integrate
with the DevLayer quality gate workflow.

Also provides endpoints to query UAT tests from uat_tests.db (separate from features.db)

Workflow:
1. PRD created in AutoCoder
2. AutoCoder generates features and builds code
3. Dev completes implementation (basic tests pass)
4. UAT Gateway runs user journey tests
5. Failures → DevLayer cards for triage
6. DevLayer approved → Dev cards created
7. Dev fixes → UAT retest triggered
8. Pass → Archive all cards
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from enum import Enum
import asyncio
import sys
from pathlib import Path
from contextlib import contextmanager
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from custom.uat_gateway.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
    from custom.uat_gateway.state_manager.state_manager import StateManager
    UAT_GATEWAY_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  UAT Gateway not available: {e}")
    UAT_GATEWAY_AVAILABLE = False

# Optional: Import DevLayer for automatic bug card creation
try:
    from custom.devlayer import DevLayerManager, DevLayerConfig
    DEVLAYER_AVAILABLE = True
except ImportError:
    print("⚠️  DevLayer not available - UAT failures won't auto-create cards")
    DEVLAYER_AVAILABLE = False

router = APIRouter(
    prefix="/api/uat",
    tags=["uat-gateway"]
)

# State directory for UAT Gateway
STATE_DIR = Path.home() / ".autocoder" / "uat_gateway"


class UATTriggerRequest(BaseModel):
    """Request to trigger UAT testing cycle"""
    project_name: str
    project_path: Optional[str] = None
    spec_path: Optional[str] = None
    force: bool = False  # Skip prerequisite checks
    # Test filtering options
    journey_types: Optional[list[str]] = None  # Filter by journey type: authentication, payment, onboarding, admin
    scenario_types: Optional[list[str]] = None  # Filter by scenario type: happy_path, error_path
    specific_scenarios: Optional[list[str]] = None  # Run only specific scenario IDs
    test_label: Optional[str] = None  # Label for this test run (e.g., "Smoke Test", "Regression")


class UATTriggerResponse(BaseModel):
    """Response from UAT trigger"""
    success: bool
    cycle_id: Optional[str] = None
    message: str
    status_url: Optional[str] = None


@router.get("/health")
async def health_check():
    """Check if UAT Gateway integration is available"""
    return {
        "available": UAT_GATEWAY_AVAILABLE,
        "devlayer_integration": DEVLAYER_AVAILABLE,
        "state_directory": str(STATE_DIR),
        "message": "UAT Gateway integration ready" if UAT_GATEWAY_AVAILABLE else "UAT Gateway not available"
    }


async def run_playwright_tests_direct(
    project_path: Path,
    test_filter: Optional[str] = None,
    base_url: str = "http://localhost:3000"
):
    """
    Run Playwright tests directly without journey extraction

    This bypasses the orchestrator's journey extraction phase and runs
    existing Playwright tests directly from the project's e2e directory.
    """
    import subprocess
    import json
    import os

    test_dir = project_path / "e2e"
    if not test_dir.exists():
        raise FileNotFoundError(f"No e2e directory found in {project_path}")

    # First, count the total tests using --list option
    print(f"🔍 Counting total tests...", flush=True)
    list_cmd = ["npx", "playwright", "test", "--list"]
    if test_filter:
        list_cmd.append(test_filter)
    else:
        list_cmd.append(str(test_dir))

    list_result = subprocess.run(
        list_cmd,
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=30
    )

    # Count test lines from list output
    test_count = 0
    if list_result.stdout:
        # Each test is on its own line
        test_count = len([line for line in list_result.stdout.split('\n')
                         if line.strip() and '›' in line])

    print(f"🔍 Found {test_count} tests", flush=True)

    # Build Playwright command using list reporter
    cmd = [
        "npx", "playwright", "test",
        f"--reporter=list",
        f"--base-url={base_url}"
    ]

    # Add test filter if specified
    if test_filter:
        cmd.append(test_filter)
    else:
        # Run all tests in e2e directory
        cmd.append(str(test_dir))

    print(f"🧪 Running Playwright tests: {' '.join(cmd)}", flush=True)

    # Run tests with longer timeout
    result = subprocess.run(
        cmd,
        cwd=project_path,
        capture_output=True,
        text=True,
        timeout=900  # 15 minute timeout
    )

    print(f"📝 Test completed with return code: {result.returncode}", flush=True)

    test_results = {
        'success': result.returncode == 0,
        'total_tests': test_count,
        'passed_tests': 0,
        'failed_tests': 0,
        'failures': [],  # List of detailed failure info
        'stdout': result.stdout[:10000] if result.stdout else '',
        'stderr': result.stderr[:5000] if result.stderr else ''
    }

    # Try to read the .last-run.json file that Playwright creates
    last_run_file = project_path / "test-results" / ".last-run.json"

    if last_run_file.exists():
        try:
            with open(last_run_file, 'r') as f:
                last_run_data = json.load(f)

            failed_test_ids = last_run_data.get('failedTests', [])

            # Collect detailed failure information from test output
            # Parse the list output to extract failed test names
            failed_test_names = []
            for line in result.stdout.split('\n'):
                if 'failed' in line.lower() and '›' in line:
                    # Extract test name from line like "[chromium] › e2e/auth.spec.ts:9:9 › Authentication › Registration › can register a new user"
                    parts = line.split('›')
                    if len(parts) >= 3:
                        # Reconstruct test name
                        test_parts = parts[2:]  # Everything after the file path
                        test_name = ' › '.join([p.strip() for p in test_parts]).strip()
                        if test_name and test_name not in failed_test_names:
                            failed_test_names.append(test_name)

            print(f"📝 Extracted {len(failed_test_names)} unique failed test names", flush=True)

            # Now collect artifacts for each unique failure
            test_results_dir = project_path / "test-results"

            for test_name in failed_test_names[:30]:  # Limit to 30 cards
                # Try to find a matching test directory
                # Test directories are named like: "auth-Authentication-Login-can-login-with-valid-credentials-chromium"
                # Convert test name to directory pattern
                test_dir_pattern = test_name.replace(' › ', '-').replace(' ', '-').lower()

                # Find matching directory
                matching_dirs = []
                for dir_path in test_results_dir.iterdir():
                    if dir_path.is_dir() and not dir_path.name.startswith('.'):
                        dir_name = dir_path.name.lower()
                        # Check if directory name contains key parts of the test name
                        if any(part.lower() in dir_name for part in test_name.split(' › ')[1:3] if part):
                            matching_dirs.append(dir_path)
                            break

                error_message = f"Test failed: {test_name}"
                screenshot_file = None
                test_dir_path = None

                if matching_dirs:
                    test_dir_path = matching_dirs[0]

                    # Check for error context file
                    error_context_file = test_dir_path / "error-context.md"
                    if error_context_file.exists():
                        try:
                            context_content = error_context_file.read_text()
                            # Extract error message
                            if "Error:" in context_content:
                                error_msg_section = context_content.split("Error:")[1].split("\n")[0]
                                if error_msg_section.strip():
                                    error_message = error_msg_section.strip()[:200]
                            elif "expected" in context_content.lower():
                                error_message = "Assertion failed - see error context for details"
                        except:
                            pass

                    # Find screenshot
                    screenshots = list(test_dir_path.glob("*failed*.png"))
                    if not screenshots:
                        screenshots = list(test_dir_path.glob("*.png"))
                    if screenshots:
                        screenshot_file = str(screenshots[0])

                test_results['failures'].append({
                    'test_id': f"failure_{len(test_results['failures'])}",
                    'test_name': test_name,
                    'error_message': error_message[:200],
                    'screenshot': screenshot_file,
                    'directory': str(test_dir_path) if test_dir_path else None
                })

            failed_tests = len(failed_test_ids)

            # With test count known, calculate passed
            if test_count > 0:
                # Each test runs on multiple browsers (chromium, firefox, webkit, Mobile Chrome, Mobile Safari = 5)
                # So total test runs = test_count * browsers
                browsers = 5
                total_test_runs = test_count * browsers
                passed_tests = total_test_runs - failed_tests

                test_results.update({
                    'total_tests': total_test_runs,
                    'passed_tests': max(0, passed_tests),
                    'failed_tests': failed_tests,
                    'duration_ms': 0  # Not tracking duration yet
                })

            print(f"📊 Test results: "
                  f"total={test_results['total_tests']}, "
                  f"passed={test_results['passed_tests']}, "
                  f"failed={test_results['failed_tests']}", flush=True)
            print(f"📝 Captured {len(test_results['failures'])} detailed failure reports", flush=True)

        except Exception as e:
            print(f"⚠️  Failed to parse .last-run.json: {e}", flush=True)
            import traceback
            traceback.print_exc()

    return test_results


@router.post("/trigger", response_model=UATTriggerResponse)
async def trigger_uat_cycle(
    request: UATTriggerRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger a UAT testing cycle for a project

    This is the main entry point for the quality gate workflow:
    1. User completes dev work in AutoCoder
    2. User clicks "Run UAT Tests" in UI
    3. This endpoint runs Playwright tests directly
    4. Test failures automatically create DevLayer cards
    5. Results returned to UI for display

    Args:
        request: UAT trigger request with project details

    Returns:
        UATTriggerResponse with cycle ID and status URL
    """
    # Check if we should use direct test execution (for projects without UAT journeys)
    use_direct_execution = request.force or True  # Default to direct for now

    if use_direct_execution:
        # Direct test execution mode
        if not request.project_path:
            try:
                import sys
                root = Path(__file__).parent.parent.parent
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                from registry import get_project_path

                registered_path = get_project_path(request.project_name)
                if registered_path:
                    request.project_path = registered_path
                else:
                    request.project_path = str(Path.home() / "projects" / "autocoder-projects" / request.project_name)
            except ImportError:
                request.project_path = str(Path.home() / "projects" / "autocoder-projects" / request.project_name)

        project_path = Path(request.project_path)
        if not project_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Project path not found: {request.project_path}"
            )

        # Check for e2e directory
        if not (project_path / "e2e").exists():
            raise HTTPException(
                status_code=400,
                detail=f"No e2e directory found in {project_path}. Please create Playwright tests first."
            )

        # Generate cycle ID
        cycle_id = f"uat_{request.project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Write cycle ID to lock file
        state_dir = STATE_DIR / request.project_name
        state_dir.mkdir(parents=True, exist_ok=True)
        lock_file = state_dir / "uat_cycle.lock"
        lock_file.write_text(cycle_id)

        # Run tests in background
        background_tasks.add_task(
            run_uat_tests_direct_background,
            str(project_path),
            request.project_name,
            cycle_id,
            request.specific_scenarios[0] if request.specific_scenarios else None
        )

        return UATTriggerResponse(
            success=True,
            cycle_id=cycle_id,
            message="UAT testing cycle started (direct mode)",
            status_url=f"/api/uat/status/{cycle_id}"
        )

    # Original orchestrator mode (disabled for now)
    if not UAT_GATEWAY_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="UAT Gateway integration not available. Install custom/uat_gateway module."
        )

    # Create state directory if needed
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Look up project path from registry if not provided
    if not request.project_path:
        try:
            import sys
            root = Path(__file__).parent.parent.parent
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from registry import get_project_path

            registered_path = get_project_path(request.project_name)
            if registered_path:
                request.project_path = registered_path
            else:
                # Fallback to default path
                request.project_path = str(Path.home() / "projects" / "autocoder-projects" / request.project_name)
        except ImportError:
            # Registry not available, use default path
            request.project_path = str(Path.home() / "projects" / "autocoder-projects" / request.project_name)

    project_path = Path(request.project_path)
    if not project_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Project path not found: {request.project_path}"
        )

    # Check for spec.yaml or app_spec.txt
    spec_path = request.spec_path or "spec.yaml"
    if not (project_path / spec_path).exists():
        # Fallback to app_spec.txt if spec.yaml doesn't exist
        if (project_path / "app_spec.txt").exists():
            spec_path = "app_spec.txt"
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Spec file not found: tried {spec_path} and app_spec.txt in {project_path}"
            )

    # Generate cycle ID
    cycle_id = f"uat_{request.project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        import os
        original_cwd = os.getcwd()

        # Change to project directory (orchestrator expects to run from project dir)
        os.chdir(project_path)

        # Configure orchestrator with correct parameters
        config = OrchestratorConfig(
            spec_path=spec_path,
            state_directory=str(STATE_DIR / request.project_name),
            base_url="http://localhost:3000",  # Default, can be made configurable
        )

        # Initialize orchestrator
        orchestrator = Orchestrator(config)

        # Restore original directory
        os.chdir(original_cwd)

        # Check if another cycle is already running
        if orchestrator.is_cycle_running():
            return UATTriggerResponse(
                success=False,
                message="Another UAT cycle is already running for this project",
                status_url=f"/api/uat/status/{orchestrator.get_current_cycle_id()}"
            )

        # Run cycle in background
        background_tasks.add_task(run_uat_cycle_background, orchestrator, cycle_id)

        # Write cycle ID to lock file for status tracking
        state_dir = STATE_DIR / request.project_name
        state_dir.mkdir(parents=True, exist_ok=True)
        lock_file = state_dir / "uat_cycle.lock"
        lock_file.write_text(cycle_id)

        return UATTriggerResponse(
            success=True,
            cycle_id=cycle_id,
            message="UAT testing cycle started",
            status_url=f"/api/uat/status/{cycle_id}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start UAT cycle: {str(e)}"
        )


async def run_uat_tests_direct_background(
    project_path: str,
    project_name: str,
    cycle_id: str,
    test_filter: Optional[str] = None
):
    """
    Run UAT tests directly in background (bypasses orchestrator)

    This function:
    1. Runs Playwright tests directly from e2e directory
    2. Processes test results
    3. Creates DevLayer cards for failures
    4. Removes lock file when complete
    """
    try:
        print(f"🧪 Starting direct UAT test execution for {project_name}")
        print(f"   Project path: {project_path}")
        print(f"   Cycle ID: {cycle_id}")

        # Run Playwright tests directly
        result = await run_playwright_tests_direct(
            Path(project_path),
            test_filter=test_filter
        )

        print(f"📊 Test Results:")
        if 'total_tests' in result:
            print(f"   Total: {result['total_tests']}")
            print(f"   Passed: {result['passed_tests']}")
            print(f"   Failed: {result['failed_tests']}")
            print(f"   Duration: {result['duration_ms']}ms")

        # Create DevLayer cards for failures
        if DEVLAYER_AVAILABLE and result.get('failed_tests', 0) > 0:
            print(f"📝 Creating DevLayer cards for {result['failed_tests']} failures...")
            await process_test_results_to_devlayer(
                project_name,
                cycle_id,
                result
            )

        print(f"✅ UAT cycle {cycle_id} completed successfully")

    except Exception as e:
        print(f"❌ Error running UAT cycle {cycle_id}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Remove lock file when cycle completes
        try:
            state_dir = STATE_DIR / project_name
            lock_file = state_dir / "uat_cycle.lock"
            if lock_file.exists():
                lock_file.unlink()
                print(f"✅ Removed lock file for completed cycle {cycle_id}")
        except Exception as e:
            print(f"⚠️  Failed to remove lock file: {e}")


async def process_test_results_to_devlayer(
    project_name: str,
    cycle_id: str,
    test_results: dict
):
    """
    Process Playwright test results and create DevLayer cards for failures

    This integrates direct test execution with DevLayer quality gate:
    - Failed tests → DevLayer bug cards
    - Test evidence attached to cards
    """
    try:
        if not DEVLAYER_AVAILABLE:
            return

        from custom.devlayer import DevLayerManager, DevLayerConfig, TestEvidence

        devlayer_config = DevLayerConfig(
            db_path=str(Path.home() / ".autocoder" / "quality_gate.db")
        )
        devlayer_manager = DevLayerManager(devlayer_config, project_name)

        failed_tests = test_results.get('failed_tests', 0)
        failures_list = test_results.get('failures', [])

        print(f"📝 Processing {failed_tests} failures for DevLayer cards", flush=True)

        # Create individual cards for each failure
        cards_created = 0
        for failure in failures_list[:30]:  # Limit to 30 cards max
            try:
                # Create TestEvidence object for each failure
                evidence = TestEvidence(
                    scenario_id=failure.get('test_id', cycle_id),
                    error_message=failure.get('error_message', 'Test failed')[:200],
                    steps_to_reproduce=[
                        f"1. Test: {failure.get('test_name', 'Unknown test')}",
                        f"2. Browser: Multiple browsers tested",
                        f"3. Status: Failed",
                    ],
                    screenshot_path=failure.get('screenshot'),
                    log_path=failure.get('directory')
                )

                # Create a descriptive title
                test_name = failure.get('test_name', 'Unknown Test')
                # Clean up test name for title
                if len(test_name) > 80:
                    test_name = test_name[:77] + "..."
                title = f"UAT Failure: {test_name}"

                await devlayer_manager.create_uat_bug_card(
                    evidence=evidence,
                    title=title,
                    uat_card_id=failure.get('test_id', cycle_id)
                )
                cards_created += 1

            except Exception as e:
                print(f"⚠️  Failed to create card for {failure.get('test_name', 'unknown')}: {e}", flush=True)
                continue

        # Also create a summary card if there were many failures
        if failed_tests > 5:
            summary_evidence = TestEvidence(
                scenario_id=cycle_id,
                error_message=f"{failed_tests} tests failed in total",
                steps_to_reproduce=[
                    f"1. UAT test cycle: {cycle_id}",
                    f"2. Total tests run: {test_results.get('total_tests', 0)}",
                    f"3. Passed: {test_results.get('passed_tests', 0)}",
                    f"4. Failed: {failed_tests}",
                    f"5. See individual cards for details",
                ],
                log_path=str(Path.home() / ".autocoder" / "uat_gateway" / project_name / f"{cycle_id}.log")
            )

            await devlayer_manager.create_uat_bug_card(
                evidence=summary_evidence,
                title=f"UAT Summary: {failed_tests} failures - {cycle_id}",
                uat_card_id=cycle_id
            )
            cards_created += 1

        print(f"✅ Created {cards_created} DevLayer cards for UAT failures", flush=True)

    except Exception as e:
        print(f"⚠️  Failed to process test results to DevLayer: {e}")
        import traceback
        traceback.print_exc()


async def run_uat_cycle_background(orchestrator: 'Orchestrator', cycle_id: str):
    """
    Run UAT cycle in background and process results

    This function:
    1. Runs the complete UAT testing cycle
    2. Processes test results
    3. Creates DevLayer cards for failures
    4. Updates pipeline events
    5. Removes lock file when complete
    """
    try:
        # Run the UAT cycle
        result = orchestrator.run_cycle()

        if result.success:
            # Process results and create DevLayer cards for failures
            if DEVLAYER_AVAILABLE:
                await process_uat_results_to_devlayer(orchestrator, result)
        else:
            print(f"❌ UAT cycle {cycle_id} failed: {result.errors}")

    except Exception as e:
        print(f"❌ Error running UAT cycle {cycle_id}: {e}")
    finally:
        # Remove lock file when cycle completes
        try:
            # Get state directory from orchestrator config
            if hasattr(orchestrator, 'config'):
                state_dir = Path(orchestrator.config.state_directory)
                lock_file = state_dir / "uat_cycle.lock"
                if lock_file.exists():
                    lock_file.unlink()
                    print(f"✅ Removed lock file for completed cycle {cycle_id}")
        except Exception as e:
            print(f"⚠️  Failed to remove lock file: {e}")


async def process_uat_results_to_devlayer(orchestrator: 'Orchestrator', result: Any):
    """
    Process UAT test results and create DevLayer cards for failures

    This integrates UAT Gateway with DevLayer quality gate:
    - Failed tests → DevLayer bug cards
    - Test evidence attached to cards
    - Cards linked back to UAT scenarios
    """
    try:
        # Initialize DevLayer manager
        # Extract project name from the orchestrator's context or use a default
        project_id = getattr(orchestrator, 'project_id', 'default')

        devlayer_config = DevLayerConfig(
            db_path=str(Path.home() / ".autocoder" / "quality_gate.db")
        )
        devlayer_manager = DevLayerManager(devlayer_config, project_id)

        # Get test results from orchestrator
        if hasattr(orchestrator, '_raw_test_results'):
            for test_result in orchestrator._raw_test_results:
                if test_result.status == "failed":
                    # Create DevLayer card for each failure
                    await devlayer_manager.create_uat_bug_card({
                        "uat_card_id": test_result.scenario_id,
                        "title": f"UAT Failure: {test_result.scenario_id}",
                        "description": test_result.error_message or "Test failed",
                        "evidence": {
                            "scenario_id": test_result.scenario_id,
                            "error_message": test_result.error_message,
                            "steps_to_reproduce": test_result.steps or [],
                            "screenshot": test_result.screenshot_path,
                            "video": test_result.video_path,
                            "logs": test_result.console_logs
                        }
                    })

        print(f"✅ Processed UAT results to DevLayer cards")

    except Exception as e:
        print(f"⚠️  Failed to process UAT results to DevLayer: {e}")


@router.get("/status/{project_name}")
async def get_project_uat_status(project_name: str):
    """Get UAT status for a project - check if cycle is running"""
    if not UAT_GATEWAY_AVAILABLE:
        return {"is_running": False, "message": "UAT Gateway not available"}

    try:
        # Look up project path from registry
        try:
            import sys
            root = Path(__file__).parent.parent.parent
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from registry import get_project_path

            project_path = get_project_path(project_name)
            if not project_path:
                project_path = str(Path.home() / "projects" / "autocoder-projects" / project_name)
        except ImportError:
            project_path = str(Path.home() / "projects" / "autocoder-projects" / project_name)

        # Check for lock file
        state_dir = STATE_DIR / project_name
        lock_file = state_dir / "uat_cycle.lock"

        if lock_file.exists():
            # Read lock file to get cycle info
            try:
                lock_content = lock_file.read_text().strip()
                return {
                    "is_running": True,
                    "cycle_id": lock_content,
                    "progress": "Running tests...",
                    "message": "UAT cycle in progress"
                }
            except:
                return {
                    "is_running": True,
                    "message": "UAT cycle in progress"
                }

        return {
            "is_running": False,
            "message": "No UAT cycle running"
        }

    except Exception as e:
        return {
            "is_running": False,
            "message": f"Error checking status: {str(e)}"
        }


@router.get("/status/{cycle_id}")
async def get_cycle_status(cycle_id: str):
    """Get status of a UAT testing cycle"""
    # TODO: Implement status tracking
    return {
        "cycle_id": cycle_id,
        "status": "running",
        "progress": "0%",
        "message": "Cycle in progress"
    }


@router.get("/projects")
async def list_uat_projects():
    """List projects that can run UAT tests"""
    projects_dir = Path.home() / "projects" / "autocoder-projects"
    if not projects_dir.exists():
        return {"projects": []}

    projects = []
    for project_path in projects_dir.iterdir():
        if project_path.is_dir():
            # Check if project has spec.yaml
            spec_file = project_path / "spec.yaml"
            if spec_file.exists():
                projects.append({
                    "name": project_path.name,
                    "path": str(project_path),
                    "has_spec": True
                })

    return {"projects": projects}


@router.get("/test-options")
async def get_test_options():
    """
    Get available test filtering options.

    Returns:
    - Journey types (authentication, payment, onboarding, admin)
    - Scenario types (happy_path, error_path)
    - Preset test configurations
    """
    return {
        "journey_types": [
            {
                "value": "authentication",
                "label": "Authentication",
                "description": "Login, logout, password reset, account management"
            },
            {
                "value": "payment",
                "label": "Payment",
                "description": "Checkout, payment processing, refunds"
            },
            {
                "value": "onboarding",
                "label": "Onboarding",
                "description": "Registration, welcome flow, first-time user experience"
            },
            {
                "value": "admin",
                "label": "Admin",
                "description": "Admin panel, user management, settings"
            }
        ],
        "scenario_types": [
            {
                "value": "happy_path",
                "label": "Happy Path",
                "description": "Everything works correctly - normal user flow"
            },
            {
                "value": "error_path",
                "label": "Error Path",
                "description": "Error conditions, validation, edge cases"
            }
        ],
        "preset_tests": [
            {
                "id": "smoke",
                "label": "Smoke Test",
                "description": "Quick validation of core functionality",
                "journey_types": ["authentication"],
                "scenario_types": ["happy_path"]
            },
            {
                "id": "regression",
                "label": "Regression Test",
                "description": "Full test suite to catch regressions",
                "journey_types": None,  # All
                "scenario_types": None  # All
            },
            {
                "id": "critical_path",
                "label": "Critical Path",
                "description": "Core user journeys only",
                "journey_types": ["authentication", "payment"],
                "scenario_types": ["happy_path"]
            },
            {
                "id": "edge_case",
                "label": "Edge Cases",
                "description": "Error handling and edge cases",
                "journey_types": None,
                "scenario_types": ["error_path"]
            }
        ]
    }


@router.post("/manual-bug")
async def create_manual_bug_card(bug_data: Dict[str, Any]):
    """
    Manually create a DevLayer bug card (for testing or manual reporting)

    This allows creating bug cards without running full UAT cycle.
    Useful for:
    - Testing DevLayer integration
    - Manual bug reports from QA
    - Customer-reported issues
    """
    if not DEVLAYER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="DevLayer integration not available"
        )

    try:
        from custom.devlayer import DevLayerManager, DevLayerConfig

        config = DevLayerConfig(
            database_path=str(Path.home() / ".autocoder" / "quality_gate.db")
        )
        manager = DevLayerManager(config, bug_data.get("project_id", "manual"))

        card_id = await manager.create_uat_bug_card(bug_data)

        return {
            "success": True,
            "card_id": card_id,
            "message": "Bug card created successfully"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create bug card: {str(e)}"
        )


# ============================================================================
# UAT Tests API (queries uat_tests.db instead of features.db)
# ============================================================================

# UAT database directory
UAT_DB_DIR = Path.home() / ".autocoder" / "uat_autocoder"


def _get_uat_db_classes():
    """Lazy import of database classes for UAT tests."""
    global _create_uat_database, _UATTestFeature
    if '_create_uat_database' not in globals() or _create_uat_database is None:
        import sys
        from pathlib import Path
        root = Path(__file__).parent.parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        from api.database import create_database, Feature

        # Create UAT database adapter
        _create_uat_database = create_database
        _UATTestFeature = Feature
    return _create_uat_database, _UATTestFeature


@contextmanager
def get_uat_db_session():
    """
    Context manager for UAT database sessions.
    Uses uat_tests.db from the UAT autocoder project.
    """
    create_database, _ = _get_uat_db_classes()

    # UAT database is in the uat-autocoder project
    uat_db_path = Path.home() / "projects" / "autocoder-projects" / "uat-autocoder" / "uat_tests.db"

    if not uat_db_path.exists():
        # If UAT DB doesn't exist, create an empty one
        uat_db_path.parent.mkdir(parents=True, exist_ok=True)
        uat_db_path.touch()

    # Use the uat_db_path as the project directory
    _, SessionLocal = create_database(uat_db_path.parent)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


class UATTestListResponse(BaseModel):
    """Response model for listing UAT tests"""
    total: int
    passing: int
    in_progress: int
    features: List[Dict[str, Any]]


@router.get("/tests", response_model=UATTestListResponse)
async def list_uat_tests():
    """
    List all UAT tests from uat_tests.db

    This endpoint mirrors the features API but queries from the UAT database
    instead of the dev features database.
    """
    try:
        with get_uat_db_session() as session:
            from api.database import Feature

            # Query all UAT tests
            uat_tests = session.query(Feature).order_by(Feature.priority).all()

            # Convert to dict format
            tests_list = [test.to_dict() for test in uat_tests]

            # Calculate statistics
            total = len(tests_list)
            passing = sum(1 for t in tests_list if t.get('passes', False))
            in_progress = sum(1 for t in tests_list if t.get('in_progress', False))

            return UATTestListResponse(
                total=total,
                passing=passing,
                in_progress=in_progress,
                features=tests_list
            )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list UAT tests: {str(e)}"
        )


@router.get("/tests/{test_id}")
async def get_uat_test(test_id: int):
    """Get a specific UAT test by ID"""
    try:
        with get_uat_db_session() as session:
            from api.database import Feature

            test = session.query(Feature).filter(Feature.id == test_id).first()

            if not test:
                raise HTTPException(
                    status_code=404,
                    detail=f"UAT test {test_id} not found"
                )

            return test.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get UAT test: {str(e)}"
        )


@router.get("/stats/summary")
async def get_uat_stats_summary():
    """
    Get UAT testing statistics summary

    Returns:
    - Total tests
    - Passing tests
    - In-progress tests
    - Completion percentage
    """
    try:
        with get_uat_db_session() as session:
            from api.database import Feature

            total = session.query(Feature).count()
            passing = session.query(Feature).filter(Feature.passes == True).count()
            in_progress = session.query(Feature).filter(Feature.in_progress == True).count()

            percentage = (passing / total * 100) if total > 0 else 0

            return {
                "total": total,
                "passing": passing,
                "in_progress": in_progress,
                "percentage": round(percentage, 1)
            }

    except Exception as e:
        # If UAT DB doesn't exist or has errors, return empty stats
        return {
            "total": 0,
            "passing": 0,
            "in_progress": 0,
            "percentage": 0
        }


class ProjectContextResponse(BaseModel):
    """Response model for project context gathering"""
    success: bool
    project_name: str
    has_spec: bool
    spec_content: Optional[str] = None
    completed_features_count: int
    completed_features: List[Dict[str, Any]] = []
    uat_cycles_count: int
    uat_cycles: List[Dict[str, Any]] = []
    message: str


@router.get("/context/{project_name}", response_model=ProjectContextResponse)
async def get_project_context(project_name: str):
    """
    Gather project context for UAT planning

    This endpoint collects all necessary context for generating a UAT test plan:
    1. Reads app_spec.txt from the project directory
    2. Queries completed features from features.db
    3. Fetches previous UAT cycle history from uat_tests.db

    Args:
        project_name: Name of the project to gather context for

    Returns:
        ProjectContextResponse with all gathered context
    """
    try:
        # Look up project path from registry if available
        project_path = None
        try:
            import sys
            root = Path(__file__).parent.parent.parent
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from registry import get_project_path

            registered_path = get_project_path(project_name)
            if registered_path:
                project_path = Path(registered_path)
            else:
                project_path = Path.home() / "projects" / "autocoder-projects" / project_name
        except ImportError:
            project_path = Path.home() / "projects" / "autocoder-projects" / project_name

        # Verify project exists
        if not project_path.exists():
            return ProjectContextResponse(
                success=False,
                project_name=project_name,
                has_spec=False,
                completed_features_count=0,
                uat_cycles_count=0,
                message=f"Project directory not found: {project_path}"
            )

        # 1. Read app_spec.txt
        spec_path = project_path / "app_spec.txt"
        spec_content = None
        has_spec = False

        if spec_path.exists():
            try:
                spec_content = spec_path.read_text(encoding='utf-8')
                has_spec = True
            except Exception as e:
                print(f"⚠️  Failed to read app_spec.txt: {e}")
                spec_content = None
        else:
            print(f"⚠️  app_spec.txt not found at {spec_path}")

        # 2. Query completed features from features.db
        completed_features = []
        completed_features_count = 0

        features_db_path = project_path / "features.db"
        if features_db_path.exists():
            try:
                import sqlite3

                conn = sqlite3.connect(str(features_db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Query only completed features (passes = True)
                cursor.execute("""
                    SELECT id, priority, category, name, description, passes, completed_at
                    FROM features
                    WHERE passes = 1
                    ORDER BY priority ASC
                """)

                rows = cursor.fetchall()
                completed_features = [
                    {
                        "id": row["id"],
                        "priority": row["priority"],
                        "category": row["category"],
                        "name": row["name"],
                        "description": row["description"],
                        "completed_at": row["completed_at"]
                    }
                    for row in rows
                ]
                completed_features_count = len(completed_features)

                conn.close()
            except Exception as e:
                print(f"⚠️  Failed to query features.db: {e}")
        else:
            print(f"⚠️  features.db not found at {features_db_path}")

        # 3. Fetch previous UAT cycles from uat_tests.db
        uat_cycles = []
        uat_cycles_count = 0

        try:
            with get_uat_db_session() as session:
                from api.database import Feature

                # Query UAT tests with results (completed cycles)
                uat_tests = session.query(Feature).filter(
                    Feature.status.in_(['passed', 'failed', 'needs-human'])
                ).all()

                # Group by cycle (assuming test names or descriptions contain cycle info)
                # For now, just return all completed UAT tests
                uat_cycles = [
                    {
                        "id": test.id,
                        "name": test.name,
                        "phase": test.phase,
                        "journey": test.journey,
                        "status": test.status,
                        "result": test.result
                    }
                    for test in uat_tests
                ]
                uat_cycles_count = len(uat_cycles)

        except Exception as e:
            print(f"⚠️  Failed to query UAT cycles from uat_tests.db: {e}")
            # Don't fail the whole request if UAT history is missing

        # Check context completeness
        context_complete = has_spec and completed_features_count > 0
        message = "Project context gathered successfully"

        if not context_complete:
            missing = []
            if not has_spec:
                missing.append("app_spec.txt")
            if completed_features_count == 0:
                missing.append("completed features")
            if missing:
                message = f"Warning: Incomplete context - missing {', '.join(missing)}"

        return ProjectContextResponse(
            success=True,
            project_name=project_name,
            has_spec=has_spec,
            spec_content=spec_content,
            completed_features_count=completed_features_count,
            completed_features=completed_features,
            uat_cycles_count=uat_cycles_count,
            uat_cycles=uat_cycles,
            message=message
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to gather project context: {str(e)}"
        )


# Request/Response models for test plan generation
class GenerateTestPlanRequest(BaseModel):
    """Request to generate UAT test plan"""
    project_name: str
    project_path: Optional[str] = None  # Auto-discovered if not provided


class TestFrameworkProposal(BaseModel):
    """Proposed test framework with phases and journeys"""
    phase: str
    description: str
    test_count: int


class JourneyProposal(BaseModel):
    """User journey identified for testing"""
    journey: str
    test_count: int
    phases: List[str]


class GenerateTestPlanResponse(BaseModel):
    """Response from test plan generation"""
    success: bool
    cycle_id: Optional[str] = None
    project_name: str
    total_features_completed: int
    journeys_identified: List[Dict[str, Any]]
    recommended_phases: List[Dict[str, Any]]
    test_scenarios: List[Dict[str, Any]]
    test_dependencies: Dict[int, List[int]]
    test_prd: str
    message: str
    created_at: Optional[str] = None


@router.post("/generate-plan", response_model=GenerateTestPlanResponse)
async def generate_test_plan(request: GenerateTestPlanRequest):
    """
    Generate UAT test plan with proposed framework

    This endpoint analyzes the project and proposes a comprehensive test framework:
    1. Parses app_spec.txt to understand project requirements
    2. Queries completed features from features.db
    3. Identifies user journeys that need testing
    4. Determines appropriate test phases (smoke, functional, regression, UAT)
    5. Generates test scenarios for each journey/phase combination
    6. Calculates dependencies between tests
    7. Returns complete test plan for user review

    The proposed framework includes:
    - Smoke tests: Critical path verification
    - Functional tests: Feature-by-feature validation
    - Regression tests: Cross-feature workflow testing
    - UAT tests: End-to-end user scenarios

    Args:
        request: GenerateTestPlanRequest with project details

    Returns:
        GenerateTestPlanResponse with complete test framework proposal
    """
    if not UAT_GATEWAY_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="UAT Gateway backend not available - ensure uat-autocoder plugin is installed"
        )

    try:
        # Determine project path
        if not request.project_path:
            try:
                import sys
                root = Path(__file__).parent.parent.parent
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                from registry import get_project_path

                registered_path = get_project_path(request.project_name)
                if registered_path:
                    request.project_path = registered_path
                else:
                    request.project_path = str(Path.home() / "projects" / "autocoder-projects" / request.project_name)
            except ImportError:
                request.project_path = str(Path.home() / "projects" / "autocoder-projects" / request.project_name)

        project_path = Path(request.project_path)
        if not project_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Project path not found: {request.project_path}"
            )

        # Check for app_spec.txt
        app_spec_path = project_path / "app_spec.txt"
        if not app_spec_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"app_spec.txt not found at {app_spec_path} - cannot generate test plan without project specification"
            )

        # Import TestPlannerAgent from uat-autocoder backend
        import sys
        uat_backend_path = Path.home() / "projects" / "autocoder-projects" / "uat-autocoder"
        if str(uat_backend_path) not in sys.path:
            sys.path.insert(0, str(uat_backend_path))

        from custom.uat_plugin.test_planner import TestPlannerAgent

        # Initialize test planner with project's app_spec.txt
        print(f"🔍 Generating test plan for {request.project_name}...")
        print(f"   Project path: {project_path}")
        print(f"   Spec: {app_spec_path}")

        planner = TestPlannerAgent(app_spec_path=str(app_spec_path))

        # Generate the test plan
        print("📋 Analyzing project and generating test framework...")
        test_plan = planner.generate_test_plan()

        # Format response with structured phases and journeys
        journeys_identified = []
        for journey in test_plan['journeys_identified']:
            journey_scenarios = [s for s in test_plan['test_scenarios'] if s['journey'] == journey]
            journey_phases = list(set(s['phase'] for s in journey_scenarios))
            journeys_identified.append({
                'journey': journey,
                'test_count': len(journey_scenarios),
                'phases': sorted(journey_phases, key=lambda p: ['smoke', 'functional', 'regression', 'uat'].index(p))
            })

        recommended_phases = []
        for phase in test_plan['recommended_phases']:
            phase_scenarios = [s for s in test_plan['test_scenarios'] if s['phase'] == phase]
            phase_descriptions = {
                'smoke': 'Basic functionality checks to ensure critical paths work',
                'functional': 'Detailed testing of individual features',
                'regression': 'Cross-feature workflow testing',
                'uat': 'User-facing scenario validation'
            }
            recommended_phases.append({
                'phase': phase,
                'description': phase_descriptions.get(phase, ''),
                'test_count': len(phase_scenarios)
            })

        print(f"✅ Test plan generated: {test_plan['cycle_id']}")
        print(f"   Features: {test_plan['total_features_completed']}")
        print(f"   Journeys: {len(test_plan['journeys_identified'])}")
        print(f"   Phases: {', '.join(test_plan['recommended_phases'])}")
        print(f"   Scenarios: {len(test_plan['test_scenarios'])}")

        return GenerateTestPlanResponse(
            success=True,
            cycle_id=test_plan['cycle_id'],
            project_name=request.project_name,
            total_features_completed=test_plan['total_features_completed'],
            journeys_identified=journeys_identified,
            recommended_phases=recommended_phases,
            test_scenarios=test_plan['test_scenarios'],
            test_dependencies=test_plan['test_dependencies'],
            test_prd=test_plan['test_prd'],
            message=f"Test framework proposal generated successfully with {len(test_plan['test_scenarios'])} scenarios across {len(test_plan['recommended_phases'])} phases",
            created_at=test_plan['created_at']
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate test plan: {str(e)}"
        )


# Request/Response models for untested journeys identification
class UntestedJourneysRequest(BaseModel):
    """Request to identify untested user journeys"""
    project_name: str
    project_path: Optional[str] = None  # Auto-discovered if not provided


class UntestedJourneysResponse(BaseModel):
    """Response with untested journey analysis"""
    success: bool
    project_name: str
    all_journeys: List[str]
    tested_journeys: List[str]
    untested_journeys: List[str]
    journey_coverage: Dict[str, int]
    total_journeys: int
    tested_count: int
    untested_count: int
    coverage_percentage: float
    message: str


@router.post("/untested-journeys", response_model=UntestedJourneysResponse)
async def identify_untested_journeys(request: UntestedJourneysRequest):
    """
    Identify user journeys that haven't been tested yet.

    This endpoint analyzes the project and cross-references with previous UAT cycles
    to determine which journeys still need testing:

    1. Parses app_spec.txt to understand project requirements
    2. Queries completed features from features.db
    3. Identifies ALL potential user journeys from spec and features
    4. Fetches previous UAT cycles from uat_tests.db
    5. Filters out journeys that have already been tested
    6. Returns detailed analysis of test coverage

    Use this to:
    - Avoid duplicating tests for already-tested journeys
    - Focus testing efforts on unexplored user flows
    - Track overall journey coverage percentage

    Args:
        request: UntestedJourneysRequest with project details

    Returns:
        UntestedJourneysResponse with journey coverage analysis
    """
    if not UAT_GATEWAY_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="UAT Gateway backend not available - ensure uat-autocoder plugin is installed"
        )

    try:
        # Determine project path
        if not request.project_path:
            try:
                import sys
                root = Path(__file__).parent.parent.parent
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                from registry import get_project_path

                registered_path = get_project_path(request.project_name)
                if registered_path:
                    request.project_path = registered_path
                else:
                    request.project_path = str(Path.home() / "projects" / "autocoder-projects" / request.project_name)
            except ImportError:
                request.project_path = str(Path.home() / "projects" / "autocoder-projects" / request.project_name)

        project_path = Path(request.project_path)
        if not project_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Project path not found: {request.project_path}"
            )

        # Check for app_spec.txt
        app_spec_path = project_path / "app_spec.txt"
        if not app_spec_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"app_spec.txt not found at {app_spec_path}"
            )

        # Import test planner functions
        import sys
        uat_backend_path = Path.home() / "projects" / "autocoder-projects" / "uat-autocoder"
        if str(uat_backend_path) not in sys.path:
            sys.path.insert(0, str(uat_backend_path))

        from custom.uat_plugin.test_planner import parse_app_spec, identify_untested_journeys
        from custom.uat_plugin.database import get_db_manager

        # Parse PRD
        print(f"🔍 Analyzing journeys for {request.project_name}...")
        prd_info = parse_app_spec(str(app_spec_path))

        # Query completed features
        db = get_db_manager()
        completed_features = db.query_passing_features()
        print(f"  Found {len(completed_features)} completed features")

        # Fetch previous UAT cycles
        previous_uat_cycles = []
        try:
            with get_uat_db_session() as session:
                from api.database import Feature

                # Query UAT tests with results (completed cycles)
                uat_tests = session.query(Feature).filter(
                    Feature.status.in_(['passed', 'failed', 'needs-human'])
                ).all()

                # Extract journey info from previous tests
                previous_uat_cycles = [
                    {
                        "id": test.id,
                        "name": test.name,
                        "phase": test.phase,
                        "journey": test.journey,
                        "status": test.status,
                    }
                    for test in uat_tests
                ]
                print(f"  Found {len(previous_uat_cycles)} previous UAT tests")

        except Exception as e:
            print(f"⚠️  Failed to query UAT cycles: {e}")
            # Continue without previous cycle data

        # Identify untested journeys
        print("📊 Analyzing journey coverage...")
        journey_analysis = identify_untested_journeys(
            prd_info=prd_info,
            completed_features=completed_features,
            previous_uat_cycles=previous_uat_cycles
        )

        # Calculate coverage percentage
        coverage_pct = 0.0
        if journey_analysis['total_journeys'] > 0:
            coverage_pct = (journey_analysis['tested_count'] / journey_analysis['total_journeys']) * 100

        # Format response message
        if journey_analysis['untested_count'] == 0:
            message = f"All {journey_analysis['total_journeys']} journeys have been tested! Coverage: {coverage_pct:.1f}%"
        elif journey_analysis['tested_count'] == 0:
            message = f"No journeys tested yet. {journey_analysis['untested_count']} journeys identified for first-time testing."
        else:
            message = f"Found {journey_analysis['untested_count']} untested journeys out of {journey_analysis['total_journeys']} total. Coverage: {coverage_pct:.1f}%"

        print(f"✅ Journey analysis complete:")
        print(f"   Total: {journey_analysis['total_journeys']}")
        print(f"   Tested: {journey_analysis['tested_count']}")
        print(f"   Untested: {journey_analysis['untested_count']}")
        print(f"   Coverage: {coverage_pct:.1f}%")

        return UntestedJourneysResponse(
            success=True,
            project_name=request.project_name,
            all_journeys=journey_analysis['all_journeys'],
            tested_journeys=journey_analysis['tested_journeys'],
            untested_journeys=journey_analysis['untested_journeys'],
            journey_coverage=journey_analysis['journey_coverage'],
            total_journeys=journey_analysis['total_journeys'],
            tested_count=journey_analysis['tested_count'],
            untested_count=journey_analysis['untested_count'],
            coverage_percentage=round(coverage_pct, 1),
            message=message
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to identify untested journeys: {str(e)}"
        )
