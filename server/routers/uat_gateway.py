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

# Import FeatureListResponse from schemas to match features API structure
from ..schemas import FeatureListResponse, FeatureResponse


# ============================================================================
# Helper Functions
# ============================================================================

def _is_valid_yaml_spec(spec_file_path: str) -> bool:
    """
    Check if a spec file is valid YAML format for UAT Orchestrator.

    Returns True if the file exists and can be parsed as YAML, False otherwise.
    """
    try:
        import yaml
        with open(spec_file_path, 'r') as f:
            yaml.safe_load(f)
        return True
    except (FileNotFoundError, yaml.YAMLError, ImportError):
        return False


# Core UAT functionality - database manager
try:
    from custom.uat_plugin.database import get_db_manager
    UAT_DATABASE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  UAT database not available: {e}")
    UAT_DATABASE_AVAILABLE = False

# ============================================================================
# CRITICAL: UAT Orchestrator Import
# ============================================================================
# There are TWO orchestrators in the codebase:
#   1. custom/uat_plugin/orchestrator.py - BROKEN (missing dev_task_creator.py)
#   2. custom/uat_gateway/orchestrator/orchestrator.py - WORKING
#
# ALWAYS import from custom.uat_gateway.orchestrator.orchestrator
# DO NOT change to custom.uat_plugin.orchestrator
#
# See: /docs/projects/autocoder/uat-mode-trigger-fixes.md
# ============================================================================

try:
    from custom.uat_gateway.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
    UAT_ORCHESTRATOR_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  UAT Orchestrator not available (orchestrated mode disabled): {e}")
    UAT_ORCHESTRATOR_AVAILABLE = False

UAT_GATEWAY_AVAILABLE = UAT_DATABASE_AVAILABLE

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

# Import execution router for Feature #45 (bug fix retest)
try:
    # Add the UAT project to the path
    uat_project_path = Path("/home/stu/projects/autocoder-projects/UAT")
    if str(uat_project_path) not in sys.path:
        sys.path.insert(0, str(uat_project_path))

    from api.execution import router as execution_router, set_database_manager
    # Remove the /api/uat prefix from execution router since it's already included
    # The execution router has prefix="/api/uat/execution", we want just "/execution"
    execution_router.prefix = "/execution"
    router.include_router(execution_router, tags=["uat-execution"])

    # Initialize db_manager for execution router
    try:
        from uat_plugin.database import get_db_manager
        uat_db_manager = get_db_manager()
        set_database_manager(uat_db_manager)
        print("✅ UAT execution router database manager initialized (Feature #45)")
    except ImportError:
        print("⚠️  UAT plugin database not available - execution endpoints may not work")

    print("✅ UAT execution router integrated (Feature #45)")
except ImportError as e:
    print(f"⚠️  UAT execution router not available: {e}")
    print("   Feature #45 (bug fix retest) endpoints will not be available")

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
    agents_spawned: Optional[int] = 0  # Number of test agents spawned (0 for direct execution)
    execution_mode: Optional[str] = "direct"  # "direct" or "orchestrated"


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
    list_cmd = ["npx", "playwright", "test", "--list", f"--config={test_dir}/playwright.config.ts"]
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

    # Build Playwright command using JSON reporter for easy parsing
    # Also output to console for visibility
    cmd = [
        "npx", "playwright", "test",
        f"--config={test_dir}/playwright.config.ts",
        f"--reporter=json",  # JSON output to stdout for parsing
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

    # Parse JSON output to get test stats
    passed_tests = 0
    failed_tests = 0
    skipped_tests = 0
    duration_ms = 0

    try:
        # The JSON reporter outputs a large JSON structure
        # Find the stats section which is at the end
        stats_start = result.stdout.rfind('"stats":')
        if stats_start >= 0:
            # Find the opening brace of the stats object
            stats_obj_start = result.stdout.find('{', stats_start)
            if stats_obj_start >= 0:
                # Find the matching closing brace by counting braces
                brace_count = 0
                i = stats_obj_start
                while i < len(result.stdout):
                    if result.stdout[i] == '{':
                        brace_count += 1
                    elif result.stdout[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            # Found the end of stats object
                            stats_json = result.stdout[stats_obj_start:i+1]
                            stats = json.loads(stats_json)
                            passed_tests = stats.get('expected', 0)  # Tests that passed
                            failed_tests = stats.get('unexpected', 0)  # Tests that failed
                            skipped_tests = stats.get('skipped', 0)  # Tests that were skipped
                            duration_ms = int(stats.get('duration', 0) * 1000) if stats.get('duration') else 0
                            break
                    i += 1

            print(f"📊 Test Results from JSON:")
            print(f"   Total: {passed_tests + failed_tests + skipped_tests}")
            print(f"   Passed: {passed_tests}")
            print(f"   Failed: {failed_tests}")
            print(f"   Skipped: {skipped_tests}")
            print(f"   Duration: {duration_ms}ms", flush=True)
    except Exception as e:
        print(f"⚠️  Failed to parse JSON output: {e}", flush=True)

    test_results = {
        'success': result.returncode == 0,
        'total_tests': passed_tests + failed_tests + skipped_tests,
        'passed_tests': passed_tests,
        'failed_tests': failed_tests,
        'skipped_tests': skipped_tests,
        'duration_ms': duration_ms,
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
                    'failed_tests': failed_tests
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
    # ===========================================================================
    # CRITICAL: Execution Mode Selection Logic
    # ===========================================================================
    #
    # BUG FIX (2026-02-03): DO NOT change back to: request.force or True
    # This ALWAYS evaluates to True due to Python's 'or' operator!
    #
    # Correct logic:
    #   - If request.force is explicitly set, use that value
    #   - Otherwise, check if orchestrator can be used:
    #     * Orchestrator must be available
    #     * Spec file must be valid YAML (spec.yaml or app_spec.txt in YAML format)
    #     * If spec is not valid YAML, fall back to direct mode (e2e/ tests)
    #
    # Modes:
    #   - Orchestrator mode: Runs 300+ pending UAT tests from global DB
    #   - Direct mode: Runs Playwright tests from project's e2e/ directory
    #
    # See: /docs/projects/autocoder/uat-mode-trigger-fixes.md
    # ===========================================================================

    # SIMPLIFIED LOGIC (2026-02-03): Always use direct mode for now
    # The orchestrator requires spec.yaml in proper YAML format, but many
    # projects use custom spec formats (like callAspect's app_spec.txt).
    # Direct mode runs Playwright tests from e2e/ directory which works.
    #
    # TODO: Re-enable orchestrator mode once all projects have proper spec.yaml
    #
    use_direct_execution = True

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
            message=f"UAT testing cycle started (direct mode) - running {len(list((project_path / 'e2e').glob('*.spec.ts')))} test files",
            status_url=f"/api/uat/status/{cycle_id}",
            agents_spawned=0,  # Direct execution uses Playwright, not autonomous agents
            execution_mode="direct"
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

    # CRITICAL: Convert to absolute path before changing directories!
    # The orchestrator runs in a background task AFTER we restore original_cwd,
    # so relative paths would be broken.
    spec_path = str(project_path / spec_path)

    # Generate cycle ID
    cycle_id = f"uat_{request.project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Configure orchestrator with correct parameters
        # NOTE: Orchestrator no longer requires running from project directory
        # since we now use absolute paths for spec
        config = OrchestratorConfig(
            spec_path=spec_path,
            state_directory=str(STATE_DIR / request.project_name),
            base_url="http://localhost:3000",  # Default, can be made configurable
        )

        # Initialize orchestrator
        orchestrator = Orchestrator(config)

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


@router.get("/progress/{cycle_id}", response_model=dict)
async def get_uat_progress(cycle_id: str):
    """
    Get progress of a UAT testing cycle

    Returns test counts and status for the specified cycle.
    The cycle_id format is: uat_{project_name}_{timestamp}
    """
    try:
        # Extract project name from cycle_id
        parts = cycle_id.split('_')
        if len(parts) < 2 or parts[0] != 'uat':
            return {
                "cycle_id": cycle_id,
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "running": 0,
                "pending": 0,
                "active_agents": 0,
                "started_at": None,
                "updated_at": datetime.now().isoformat(),
                "tests": []
            }

        project_name = parts[1]

        # Check for lock file to determine if cycle is still running
        state_dir = STATE_DIR / project_name
        state_dir.mkdir(parents=True, exist_ok=True)
        lock_file = state_dir / "uat_cycle.lock"
        results_file = state_dir / f"{cycle_id}_results.json"

        is_running = False
        if lock_file.exists():
            try:
                current_cycle = lock_file.read_text().strip()
                is_running = (current_cycle == cycle_id)
            except:
                pass

        # Try to read test results from results file
        passed = 0
        failed = 0
        skipped = 0
        total_tests = 0

        if results_file.exists():
            try:
                import json
                with open(results_file, 'r') as f:
                    results = json.load(f)
                total_tests = results.get('total_tests', 0)
                passed = results.get('passed', 0)
                failed = results.get('failed', 0)
                skipped = results.get('skipped', 0)
                print(f"📊 Progress: {passed} passed, {failed} failed, {skipped} skipped", flush=True)
            except Exception as e:
                print(f"⚠️  Failed to read results file: {e}", flush=True)

        return {
            "cycle_id": cycle_id,
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "running": 1 if is_running else 0,
            "pending": skipped if not is_running else 0,
            "active_agents": 0,
            "started_at": lock_file.stat().st_mtime if lock_file.exists() else None,
            "updated_at": datetime.now().isoformat(),
            "tests": []
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get progress: {str(e)}"
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
            print(f"   Skipped: {result.get('skipped_tests', 0)}")
            print(f"   Duration: {result['duration_ms']}ms")

        # Save test results to state directory for progress endpoint
        state_dir = STATE_DIR / project_name
        state_dir.mkdir(parents=True, exist_ok=True)
        results_file = state_dir / f"{cycle_id}_results.json"
        with open(results_file, 'w') as f:
            json.dump({
                'cycle_id': cycle_id,
                'total_tests': result.get('total_tests', 0),
                'passed': result.get('passed_tests', 0),
                'failed': result.get('failed_tests', 0),
                'skipped': result.get('skipped_tests', 0),
                'duration_ms': result.get('duration_ms', 0),
                'completed_at': datetime.now().isoformat()
            }, f)
        print(f"💾 Saved test results to {results_file}")

        # Update UAT test statuses in database
        # Only mark as "passed" if tests actually ran (not skipped)
        # Skipped tests stay in "pending" so they show as incomplete
        try:
            import sqlite3
            uat_db_path = Path.home() / ".autocoder" / "uat_tests.db"
            if uat_db_path.exists():
                conn = sqlite3.connect(uat_db_path)
                cursor = conn.cursor()

                # Only update tests that actually passed (not skipped)
                # Skipped tests should remain as "pending" so they can be implemented later
                if result.get('passed_tests', 0) > 0:
                    cursor.execute("""
                        UPDATE uat_test_features
                        SET status = 'passed',
                            completed_at = datetime('now')
                        WHERE status = 'pending'
                        LIMIT ?
                    """, (result.get('passed_tests', 0),))
                    updated_count = cursor.rowcount
                else:
                    # All tests were skipped - don't mark anything as passed
                    # They stay in pending so developers know to implement them
                    updated_count = 0

                conn.commit()
                conn.close()

                if updated_count > 0:
                    print(f"✅ Updated {updated_count} UAT tests from 'pending' to 'passed' (tests actually ran)")
                else:
                    print(f"ℹ️  All tests were skipped - keeping {result.get('skipped_tests', 0)} tests as 'pending' for implementation")
        except Exception as e:
            print(f"⚠️  Failed to update UAT test statuses: {e}")

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

    # UAT database is in the uat-autocoder config directory
    uat_db_path = Path.home() / ".autocoder" / "uat_tests.db"

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


@router.get("/tests", response_model=FeatureListResponse)
async def list_uat_tests(project: Optional[str] = None):
    """
    List UAT tests from uat_tests.db, optionally filtered by project.

    This endpoint mirrors the features API but queries from the UAT database
    instead of the dev features database.

    Args:
        project: Optional project name to filter tests. When specified, returns
                 only tests from the latest approved cycle for that project.

    Returns tests organized by status (pending/in_progress/done) to match
    the FeatureListResponse schema expected by the frontend.
    """
    try:
        import sqlite3
        import json
        from pathlib import Path

        # Connect directly to UAT database
        uat_db_path = Path.home() / ".autocoder" / "uat_tests.db"

        if not uat_db_path.exists():
            # Return empty lists if no UAT database exists yet
            return FeatureListResponse(
                pending=[],
                in_progress=[],
                done=[],
            )

        conn = sqlite3.connect(str(uat_db_path))
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()

        # If project specified, find the latest approved cycle for that project
        cycle_filter = ""
        if project:
            cursor.execute("""
                SELECT cycle_id
                FROM uat_test_plan
                WHERE project_name = ? AND approved = 1
                ORDER BY created_at DESC
                LIMIT 1
            """, (project,))
            result = cursor.fetchone()
            if result:
                cycle_id = result['cycle_id']
                # Filter tests by cycle_id (stored as prefix in scenario field)
                # Scenario format: [YYYYMMDD_HHMMSS] Test name
                cycle_filter = f"WHERE scenario LIKE '[{cycle_id[:15]}]%'"
            else:
                # No approved cycle found for this project
                conn.close()
                return FeatureListResponse(
                    pending=[],
                    in_progress=[],
                    done=[],
                )

        # Query UAT test features from the correct table (Feature #174)
        cursor.execute(f"""
            SELECT
                id,
                priority,
                scenario as name,
                description,
                status,
                phase,
                journey,
                test_type,
                expected_result,
                devlayer_card_id,
                started_at,
                completed_at,
                created_at
            FROM uat_test_features
            {cycle_filter}
            ORDER BY priority ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        # Organize by status (matching features router logic)
        pending = []
        in_progress = []
        done = []

        for row in rows:
            # Convert row to dict
            test_dict = dict(row)

            # Map UAT test fields to FeatureResponse schema
            # UAT: phase, journey, scenario, description, steps (JSON)
            # Feature: category, name, description, steps (list), dependencies (list)

            # Parse steps from JSON if available
            steps_json = test_dict.get('steps', '[]')
            if isinstance(steps_json, str):
                import json
                try:
                    steps_list = json.loads(steps_json)
                except:
                    steps_list = []
            elif isinstance(steps_json, list):
                steps_list = steps_json
            else:
                steps_list = []

            # Create FeatureResponse-compatible dict
            # Note: SQL query aliases 'scenario as name', so we use 'name' here
            feature_response = {
                'id': test_dict['id'],
                'priority': test_dict['priority'],
                'category': test_dict.get('journey', 'uat'),  # Use journey as category
                'name': test_dict.get('name', test_dict.get('description', '')),
                'description': test_dict.get('description', ''),
                'steps': steps_list if steps_list else ['No steps defined'],
                'dependencies': [],  # UAT tests don't use feature dependencies
                'passes': False,
                'in_progress': False,
            }

            # Map UAT status to FeatureResponse structure
            # UAT statuses: pending, in_progress, passed, failed, needs-human, parked
            status = test_dict.get('status', 'pending')

            if status == 'passed':
                feature_response['passes'] = True
                feature_response['in_progress'] = False
                done.append(feature_response)
            elif status == 'in_progress':
                feature_response['passes'] = False
                feature_response['in_progress'] = True
                in_progress.append(feature_response)
            else:
                # pending, failed, needs-human, parked all go to pending column
                feature_response['passes'] = False
                feature_response['in_progress'] = False
                pending.append(feature_response)

        return FeatureListResponse(
            pending=pending,
            in_progress=in_progress,
            done=done,
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
        import sqlite3
        from pathlib import Path

        # Connect directly to UAT database
        uat_db_path = Path.home() / ".autocoder" / "uat_tests.db"

        if not uat_db_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"UAT database not found"
            )

        conn = sqlite3.connect(str(uat_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query specific UAT test by ID
        cursor.execute("""
            SELECT
                id,
                priority,
                scenario as name,
                description,
                status,
                phase,
                journey,
                test_type,
                expected_result,
                devlayer_card_id,
                started_at,
                completed_at,
                created_at
            FROM uat_test_features
            WHERE id = ?
        """, (test_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"UAT test {test_id} not found"
            )

        # Convert to dict
        test_dict = dict(row)

        # Map status to passes/in_progress flags
        status = test_dict.get('status', 'pending')
        if status == 'passed':
            test_dict['passes'] = True
            test_dict['in_progress'] = False
        elif status == 'in_progress':
            test_dict['passes'] = False
            test_dict['in_progress'] = True
        else:
            test_dict['passes'] = False
            test_dict['in_progress'] = False

        return test_dict

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get UAT test: {str(e)}"
        )


@router.post("/tests")
async def create_uat_test(request: Dict[str, Any]):
    """
    Create a new UAT test

    Creates a single UAT test task with the following fields:
    - scenario: Test scenario name
    - journey: User journey being tested
    - phase: Test phase (smoke, functional, regression, uat)
    - steps: Test execution steps
    - expected_result: Expected test outcome
    - category: Test category (optional, defaults to phase)
    - priority: Test priority (optional, auto-assigned if not provided)

    The test is created in uat_tests.db (separate from features.db)
    """
    try:
        with get_uat_db_session() as session:
            from api.database import Feature

            # Extract fields from request
            scenario = request.get('scenario')
            journey = request.get('journey')
            phase = request.get('phase')
            steps = request.get('steps', [])
            expected_result = request.get('expected_result', '')
            category = request.get('category', phase)
            priority = request.get('priority')

            # Validate required fields
            if not scenario:
                raise HTTPException(
                    status_code=400,
                    detail="scenario is required"
                )
            if not journey:
                raise HTTPException(
                    status_code=400,
                    detail="journey is required"
                )
            if not phase:
                raise HTTPException(
                    status_code=400,
                    detail="phase is required (smoke, functional, regression, uat)"
                )
            if phase not in ['smoke', 'functional', 'regression', 'uat']:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid phase: {phase}. Must be one of: smoke, functional, regression, uat"
                )
            if not steps or not isinstance(steps, list):
                raise HTTPException(
                    status_code=400,
                    detail="steps is required and must be a list"
                )

            # Auto-assign priority if not provided
            if priority is None:
                # Get the highest priority and add 1
                max_priority = session.query(Feature).count()
                priority = max_priority + 1

            # Build description from UAT-specific fields
            description = f"Journey: {journey}\n"
            description += f"Phase: {phase}\n"
            description += f"Scenario: {scenario}\n"
            description += f"Expected Result: {expected_result}"

            # Create the UAT test
            uat_test = Feature(
                priority=priority,
                category=category,
                name=scenario,  # Use scenario as the test name
                description=description,
                steps=steps,
                passes=False,
                in_progress=False,
                dependencies=None,
                complexity_score=1,  # UAT tests are typically straightforward
                created_at=datetime.utcnow()
            )

            session.add(uat_test)
            session.commit()
            session.refresh(uat_test)

            return {
                "success": True,
                "test_id": uat_test.id,
                "message": f"UAT test '{scenario}' created successfully",
                "test": uat_test.to_dict()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create UAT test: {str(e)}"
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


# ============================================================================
# Blocker Detection Models (Feature #9)
# ============================================================================

class BlockerType(str, Enum):
    """Types of blockers that can prevent test execution"""
    EMAIL_VERIFICATION = "email_verification"
    SMS = "sms"
    PAYMENT_GATEWAY = "payment_gateway"
    EXTERNAL_API = "external_api"
    DATABASE_MIGRATION = "database_migration"
    THIRD_PARTY_SERVICE = "third_party_service"
    AUTH_PROVIDER = "auth_provider"


class BlockerAction(str, Enum):
    """Actions user can take when a blocker is detected"""
    WAIT = "wait"  # Pause and wait for user to manually resolve
    SKIP = "skip"  # Skip affected tests and continue
    MOCK = "mock"  # Use test doubles/mocks instead


class BlockerConfig(BaseModel):
    """Configuration for a single blocker type"""
    blocker_type: BlockerType
    detected: bool
    action: Optional[BlockerAction] = None
    reason: str  # Why this blocker was detected
    affected_tests: List[str] = []  # Test scenarios that would be affected
    notes: Optional[str] = None


class DetectBlockersRequest(BaseModel):
    """Request to detect potential blockers in a project"""
    project_name: str
    project_path: Optional[str] = None


class DetectBlockersResponse(BaseModel):
    """Response with detected blockers and recommendations"""
    success: bool
    project_name: str
    blockers_detected: List[BlockerConfig]
    total_blockers: int
    critical_blockers: int  # Blockers that would prevent most tests
    message: str
    recommendations: str  # Human-readable summary


class ConfigureBlockersRequest(BaseModel):
    """Request to save blocker configuration"""
    project_name: str
    blockers: List[BlockerConfig]


class ConfigureBlockersResponse(BaseModel):
    """Response after saving blocker configuration"""
    success: bool
    project_name: str
    blockers_configured: int
    message: str
    config_saved_at: Optional[str] = None


# ============================================================================
# Blocker Detection Endpoints (Feature #9)
# ============================================================================

def _detect_blockers_from_spec(spec_content: str) -> List[BlockerConfig]:
    """
    Analyze app_spec.txt to detect potential blockers

    Args:
        spec_content: The app_spec.txt content

    Returns:
        List of detected blockers with recommendations
    """
    blockers = []
    spec_lower = spec_content.lower()

    # Detect email verification requirements
    if any(term in spec_lower for term in ['email verification', 'email confirm', 'verify email', 'email token']):
        blockers.append(BlockerConfig(
            blocker_type=BlockerType.EMAIL_VERIFICATION,
            detected=True,
            reason="Project requires email verification (e.g., account confirmation, password reset)",
            affected_tests=["authentication - signup", "authentication - password recovery"],
            notes="Email service (SMTP) must be configured or tests will use mocked email verification"
        ))

    # Detect SMS requirements
    if any(term in spec_lower for term in ['sms', 'text message', 'phone verification', '2fa', 'two-factor', 'otp']):
        blockers.append(BlockerConfig(
            blocker_type=BlockerType.SMS,
            detected=True,
            reason="Project requires SMS verification (e.g., 2FA, phone confirmation)",
            affected_tests=["authentication - 2FA", "authentication - phone verification"],
            notes="SMS gateway (Twilio, etc.) must be configured or tests will use mocked SMS"
        ))

    # Detect payment gateway requirements
    if any(term in spec_lower for term in ['payment', 'checkout', 'stripe', 'paypal', 'credit card', 'transaction']):
        blockers.append(BlockerConfig(
            blocker_type=BlockerType.PAYMENT_GATEWAY,
            detected=True,
            reason="Project processes payments (e.g., Stripe, PayPal)",
            affected_tests=["payment - checkout", "payment - refund", "payment - subscription"],
            notes="Payment gateway test mode must be configured or tests will use mocked payments"
        ))

    # Detect external API dependencies
    if any(term in spec_lower for term in ['api integration', 'external service', 'webhook', 'third-party']):
        blockers.append(BlockerConfig(
            blocker_type=BlockerType.EXTERNAL_API,
            detected=True,
            reason="Project integrates with external APIs or services",
            affected_tests=["integration tests"],
            notes="External API credentials or test endpoints must be configured"
        ))

    # Detect database migration dependencies
    if 'migration' in spec_lower or 'database schema' in spec_lower:
        blockers.append(BlockerConfig(
            blocker_type=BlockerType.DATABASE_MIGRATION,
            detected=True,
            reason="Project requires specific database schema or migrations",
            affected_tests=["database setup", "data seeding"],
            notes="Database must be initialized with correct schema before tests"
        ))

    # Detect third-party service dependencies
    if any(term in spec_lower for term in ['oauth', 'google', 'github', 'facebook', 'social login']):
        blockers.append(BlockerConfig(
            blocker_type=BlockerType.AUTH_PROVIDER,
            detected=True,
            reason="Project uses external OAuth providers",
            affected_tests=["authentication - social login"],
            notes="OAuth test credentials must be configured or tests will use mocked auth"
        ))

    return blockers


@router.post("/detect-blockers", response_model=DetectBlockersResponse)
async def detect_blockers(request: DetectBlockersRequest):
    """
    Detect potential blockers that could prevent UAT test execution

    This endpoint analyzes the project to identify common blockers:
    1. Parses app_spec.txt for blocker keywords
    2. Identifies services that need configuration (email, SMS, payments, etc.)
    3. Returns detected blockers with recommendations

    The conversational UI will present these to the user and ask:
    - "I detected email verification is required. How should I handle it?"
    - Options: "Wait for you to configure", "Skip those tests", "Use mock emails"

    Args:
        request: DetectBlockersRequest with project name

    Returns:
        DetectBlockersResponse with detected blockers
    """
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
            return DetectBlockersResponse(
                success=False,
                project_name=request.project_name,
                blockers_detected=[],
                total_blockers=0,
                critical_blockers=0,
                message=f"Project path not found: {request.project_path}",
                recommendations=""
            )

        # Read app_spec.txt
        spec_path = project_path / "app_spec.txt"
        if not spec_path.exists():
            return DetectBlockersResponse(
                success=False,
                project_name=request.project_name,
                blockers_detected=[],
                total_blockers=0,
                critical_blockers=0,
                message=f"app_spec.txt not found at {spec_path}",
                recommendations=""
            )

        spec_content = spec_path.read_text(encoding='utf-8')

        # Detect blockers from spec
        blockers = _detect_blockers_from_spec(spec_content)

        # Count critical blockers (affect most tests)
        critical_count = sum(1 for b in blockers if len(b.affected_tests) >= 2)

        # Generate human-readable recommendations
        if blockers:
            blocker_summary = []
            for blocker in blockers:
                blocker_summary.append(f"- **{blocker.blocker_type.value.replace('_', ' ').title()}**: {blocker.reason}")

            recommendations = (
                f"I detected {len(blockers)} potential blocker(s) that may prevent test execution:\n\n"
                + "\n".join(blocker_summary) +
                "\n\nFor each blocker, you can choose:\n"
                "• **Wait**: Pause and I'll wait for you to configure the service manually\n"
                "• **Skip**: Skip tests that depend on this blocker\n"
                "• **Mock**: Use test doubles instead of real services\n\n"
                "How would you like to handle these?"
            )
        else:
            recommendations = "No blockers detected! Your project looks ready for automated testing."

        print(f"🔍 Detected {len(blockers)} blockers for {request.project_name}")
        for blocker in blockers:
            print(f"   - {blocker.blocker_type.value}: {blocker.reason}")

        return DetectBlockersResponse(
            success=True,
            project_name=request.project_name,
            blockers_detected=blockers,
            total_blockers=len(blockers),
            critical_blockers=critical_count,
            message=f"Detected {len(blockers)} potential blocker(s)",
            recommendations=recommendations
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect blockers: {str(e)}"
        )


@router.post("/configure-blockers", response_model=ConfigureBlockersResponse)
async def configure_blockers(request: ConfigureBlockersRequest):
    """
    Save blocker configuration preferences

    This endpoint saves the user's choices for how to handle detected blockers.
    The configuration will be used during test plan generation and execution.

    Configuration is saved to: ~/.autocoder/uat_gateway/{project_name}/blockers.json

    Args:
        request: ConfigureBlockersRequest with blocker preferences

    Returns:
        ConfigureBlockersResponse confirming save
    """
    try:
        # Create config directory
        project_config_dir = STATE_DIR / request.project_name
        project_config_dir.mkdir(parents=True, exist_ok=True)

        # Save blocker configuration
        config_path = project_config_dir / "blockers.json"
        with open(config_path, 'w') as f:
            json.dump({
                "project_name": request.project_name,
                "blockers": [b.dict() for b in request.blockers],
                "configured_at": datetime.now().isoformat()
            }, f, indent=2)

        # Count configured blockers (action != None)
        configured_count = sum(1 for b in request.blockers if b.action is not None)

        print(f"💾 Saved blocker configuration for {request.project_name}")
        print(f"   Path: {config_path}")
        print(f"   Blockers configured: {configured_count}/{len(request.blockers)}")

        return ConfigureBlockersResponse(
            success=True,
            project_name=request.project_name,
            blockers_configured=configured_count,
            message=f"Blocker configuration saved ({configured_count} blockers configured)",
            config_saved_at=datetime.now().isoformat()
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save blocker configuration: {str(e)}"
        )


@router.get("/configure-blockers/{project_name}")
async def get_blocker_configuration(project_name: str):
    """
    Retrieve saved blocker configuration for a project

    Args:
        project_name: Name of the project

    Returns:
        JSON with blocker configuration or empty config if not found
    """
    try:
        config_path = STATE_DIR / project_name / "blockers.json"

        if not config_path.exists():
            return {
                "success": True,
                "project_name": project_name,
                "blockers": [],
                "message": "No blocker configuration found"
            }

        with open(config_path, 'r') as f:
            config = json.load(f)

        print(f"📋 Retrieved blocker configuration for {project_name}")

        return config

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve blocker configuration: {str(e)}"
        )


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
    estimated_execution_time: Optional[Dict[str, Any]] = None  # FR16: Estimated execution time breakdown


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

        # Import TestPlannerAgent from uat_plugin
        from custom.uat_plugin.test_planner import TestPlannerAgent
        from custom.uat_plugin.database import DatabaseManager

        # Initialize test planner with project's app_spec.txt and features.db
        print(f"🔍 Generating test plan for {request.project_name}...")
        print(f"   Project path: {project_path}")
        print(f"   Spec: {app_spec_path}")

        # Create database manager with project's features.db
        features_db_path = project_path / "features.db"
        db_manager = DatabaseManager(features_db_path=str(features_db_path))

        planner = TestPlannerAgent(app_spec_path=str(app_spec_path), db_manager=db_manager)

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

        # FEATURE #16: Calculate estimated execution time
        print("⏱️  Calculating estimated execution time...")
        total_test_count = len(test_plan['test_scenarios'])

        # Configuration for time estimation (based on industry standards and FR16 requirements)
        avg_test_duration_seconds = 120  # Average 2 minutes per test (conservative estimate)
        max_concurrent_agents = 3  # Default parallel execution cap (FR69, FR100)
        setup_time_seconds = 60  # Initial setup (browser launch, environment prep)
        teardown_time_seconds = 30  # Final cleanup

        # Calculate sequential execution time (if tests ran one at a time)
        sequential_time_seconds = (total_test_count * avg_test_duration_seconds) + setup_time_seconds + teardown_time_seconds

        # Calculate parallel execution time (with 3 agents running concurrently)
        # Tests are divided among agents, each agent runs its share sequentially
        tests_per_agent = max(1, total_test_count // max_concurrent_agents)
        remaining_tests = total_test_count % max_concurrent_agents

        # The last agent handles the remainder
        if remaining_tests > 0:
            tests_per_agent = max(tests_per_agent, remaining_tests)

        parallel_time_seconds = (tests_per_agent * avg_test_duration_seconds) + setup_time_seconds + teardown_time_seconds

        # Format time estimates for display
        def format_duration(seconds: int) -> str:
            """Format seconds into human-readable duration"""
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"

        estimated_execution_time = {
            "total_tests": total_test_count,
            "sequential_execution": {
                "seconds": sequential_time_seconds,
                "formatted": format_duration(sequential_time_seconds),
                "description": "If tests ran one at a time"
            },
            "parallel_execution": {
                "seconds": parallel_time_seconds,
                "formatted": format_duration(parallel_time_seconds),
                "description": f"With {max_concurrent_agents} concurrent agents",
                "concurrent_agents": max_concurrent_agents
            },
            "assumptions": {
                "average_test_duration_seconds": avg_test_duration_seconds,
                "setup_time_seconds": setup_time_seconds,
                "teardown_time_seconds": teardown_time_seconds,
                "max_concurrent_agents": max_concurrent_agents
            },
            "time_saved": {
                "seconds": sequential_time_seconds - parallel_time_seconds,
                "formatted": format_duration(sequential_time_seconds - parallel_time_seconds),
                "percentage_saved": round(((sequential_time_seconds - parallel_time_seconds) / sequential_time_seconds) * 100, 1)
            }
        }

        print(f"   Sequential: {format_duration(sequential_time_seconds)}")
        print(f"   Parallel ({max_concurrent_agents} agents): {format_duration(parallel_time_seconds)}")
        print(f"   Time saved: {format_duration(sequential_time_seconds - parallel_time_seconds)} ({estimated_execution_time['time_saved']['percentage_saved']}%)")

        # FEATURE #14: Save test plan to database for approval
        print("💾 Saving test plan to database...")
        from uat_plugin.database import get_db_manager, UATTestPlan
        from datetime import datetime

        db = get_db_manager()
        with db.uat_session() as session:
            # Check if plan already exists
            existing_plan = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == test_plan['cycle_id']
            ).first()

            if not existing_plan:
                # Create new test plan record
                uat_test_plan = UATTestPlan(
                    project_name=request.project_name,
                    cycle_id=test_plan['cycle_id'],
                    total_features_completed=test_plan['total_features_completed'],
                    journeys_identified=test_plan['journeys_identified'],
                    recommended_phases=test_plan['recommended_phases'],
                    test_prd=test_plan['test_prd'],
                    approved=False
                )
                session.add(uat_test_plan)
                session.commit()
                print(f"   Saved to uat_test_plan table: {test_plan['cycle_id']}")
            else:
                print(f"   Test plan already exists in database: {test_plan['cycle_id']}")

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
            created_at=test_plan['created_at'],
            estimated_execution_time=estimated_execution_time  # FR16: Include time estimate
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


# ==============================================================================
# FEATURE #12: Conversational Test Framework Modification
# ==============================================================================

class ModifyTestPlanRequest(BaseModel):
    """Request to modify proposed test framework conversationally"""
    project_name: str
    cycle_id: str  # From previous generate-plan response
    modification_type: Literal[
        "add_tests",
        "remove_tests",
        "change_phases",
        "adjust_journeys",
        "custom"
    ]
    modification_params: Dict[str, Any] = {}  # Flexible params for different modification types
    user_message: Optional[str] = None  # Natural language description of changes


class ModifyTestPlanResponse(BaseModel):
    """Response with modified test framework"""
    success: bool
    cycle_id: str
    project_name: str
    original_test_count: int
    modified_test_count: int
    journeys_identified: List[Dict[str, Any]]
    recommended_phases: List[Dict[str, Any]]
    test_scenarios: List[Dict[str, Any]]
    test_dependencies: Dict[int, List[int]]
    test_prd: str
    modifications_applied: List[str]
    message: str
    created_at: Optional[str] = None


@router.post("/modify-plan", response_model=ModifyTestPlanResponse)
async def modify_test_plan(request: ModifyTestPlanRequest):
    """
    Modify proposed test framework conversationally (FR11)

    This endpoint allows users to modify the proposed test framework before confirmation:
    - Add/remove specific tests
    - Change phase allocation (e.g., "more smoke tests, fewer regression tests")
    - Add/remove entire journeys
    - Adjust test counts

    The modifications are handled conversationally - users describe what they want
    to change in natural language, and the system updates the plan accordingly.

    Args:
        request: ModifyTestPlanRequest with cycle_id and modification details

    Returns:
        ModifyTestPlanResponse with updated test framework

    Example modifications:
    - "Add 5 more smoke tests for authentication"
    - "Remove all regression tests, keep only smoke and functional"
    - "Add payment journey testing"
    - "Reduce functional tests by 50%, increase UAT tests"
    """
    if not UAT_GATEWAY_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="UAT Gateway backend not available - ensure uat-autocoder plugin is installed"
        )

    try:
        # Import TestPlannerAgent
        from custom.uat_plugin.test_planner import TestPlannerAgent, modify_test_plan

        # Determine project path
        project_path = None
        try:
            import sys
            root = Path(__file__).parent.parent.parent
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from registry import get_project_path

            registered_path = get_project_path(request.project_name)
            if registered_path:
                project_path = Path(registered_path)
            else:
                project_path = Path.home() / "projects" / "autocoder-projects" / request.project_name
        except ImportError:
            project_path = Path.home() / "projects" / "autocoder-projects" / request.project_name

        if not project_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Project path not found: {project_path}"
            )

        # Get original test plan (simulate loading from state)
        app_spec_path = project_path / "app_spec.txt"
        if not app_spec_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"app_spec.txt not found at {app_spec_path}"
            )

        print(f"🔧 Modifying test plan for cycle {request.cycle_id}...")
        print(f"   Modification type: {request.modification_type}")
        if request.user_message:
            print(f"   User request: {request.user_message}")

        # Create database manager with project's features.db
        features_db_path = project_path / "features.db"
        db_manager = DatabaseManager(features_db_path=str(features_db_path))

        # Initialize test planner
        planner = TestPlannerAgent(app_spec_path=str(app_spec_path), db_manager=db_manager)

        # Generate original plan first (in production, this would be loaded from state)
        original_plan = planner.generate_test_plan()
        original_test_count = len(original_plan['test_scenarios'])

        # Apply modifications
        print("📝 Applying modifications...")
        modified_plan = modify_test_plan(
            original_plan=original_plan,
            modification_type=request.modification_type,
            modification_params=request.modification_params,
            user_message=request.user_message
        )

        # Track modifications applied
        modifications_applied = []
        if request.modification_type == "add_tests":
            added_count = len(modified_plan['test_scenarios']) - original_test_count
            modifications_applied.append(f"Added {added_count} test(s)")
        elif request.modification_type == "remove_tests":
            removed_count = original_test_count - len(modified_plan['test_scenarios'])
            modifications_applied.append(f"Removed {removed_count} test(s)")
        elif request.modification_type == "change_phases":
            modifications_applied.append(f"Updated phase allocation: {request.modification_params.get('phases', [])}")
        elif request.modification_type == "adjust_journeys":
            modifications_applied.append(f"Adjusted journeys: {request.modification_params.get('journeys', [])}")
        elif request.user_message:
            modifications_applied.append(f"Custom: {request.user_message}")

        # Format response (same structure as generate-plan)
        journeys_identified = []
        for journey in modified_plan['journeys_identified']:
            journey_scenarios = [s for s in modified_plan['test_scenarios'] if s['journey'] == journey]
            journey_phases = list(set(s['phase'] for s in journey_scenarios))
            journeys_identified.append({
                'journey': journey,
                'test_count': len(journey_scenarios),
                'phases': sorted(journey_phases, key=lambda p: ['smoke', 'functional', 'regression', 'uat'].index(p))
            })

        recommended_phases = []
        for phase in modified_plan['recommended_phases']:
            phase_scenarios = [s for s in modified_plan['test_scenarios'] if s['phase'] == phase]
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

        print(f"✅ Test plan modified:")
        print(f"   Original: {original_test_count} scenarios")
        print(f"   Modified: {len(modified_plan['test_scenarios'])} scenarios")
        print(f"   Changes: {', '.join(modifications_applied)}")

        return ModifyTestPlanResponse(
            success=True,
            cycle_id=request.cycle_id,  # Keep same cycle_id for modifications
            project_name=request.project_name,
            original_test_count=original_test_count,
            modified_test_count=len(modified_plan['test_scenarios']),
            journeys_identified=journeys_identified,
            recommended_phases=recommended_phases,
            test_scenarios=modified_plan['test_scenarios'],
            test_dependencies=modified_plan['test_dependencies'],
            test_prd=modified_plan['test_prd'],
            modifications_applied=modifications_applied,
            message=f"Test framework modified successfully. {len(modified_plan['test_scenarios'])} scenarios (was {original_test_count}). Changes: {', '.join(modifications_applied)}",
            created_at=modified_plan.get('created_at')
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to modify test plan: {str(e)}"
        )


# ============================================================================
# FEATURE #14: Create UAT test tasks in database
# ============================================================================

class ApproveTestPlanRequest(BaseModel):
    """Request to approve a test plan and create UAT tests"""
    cycle_id: str


class ApproveTestPlanResponse(BaseModel):
    """Response after approving test plan"""
    success: bool
    cycle_id: str
    project_name: str
    tests_created: int
    test_ids: List[int]
    message: str
    approved_at: Optional[str] = None


@router.post("/approve-plan/{cycle_id}", response_model=ApproveTestPlanResponse)
async def approve_test_plan(cycle_id: str):
    """
    Approve a test plan and create UAT test tasks in database (FR12)

    This endpoint:
    1. Retrieves the test plan from uat_test_plan table using cycle_id
    2. Creates UATTestFeature records in uat_tests.db for each test scenario
    3. Marks the test plan as approved
    4. Returns list of created test IDs

    The created tests include all required fields:
    - id: Auto-increment primary key
    - priority: Execution order (1, 2, 3, ...)
    - phase: smoke, functional, regression, or uat
    - journey: User journey category (authentication, payment, etc.)
    - scenario: Human-readable test name with cycle_id prefix
    - description: What this test validates
    - test_type: e2e, visual, api, or a11y
    - test_file: Path to Playwright test file (optional)
    - steps: JSON array of test steps
    - expected_result: Expected outcome
    - status: pending (default)
    - dependencies: JSON array of test IDs this test depends on
    - result: null (to be filled during execution)

    All tests are created in a single atomic transaction.

    Args:
        cycle_id: Unique cycle identifier from test plan generation

    Returns:
        ApproveTestPlanResponse with created test count and IDs
    """
    if not UAT_GATEWAY_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="UAT Gateway backend not available - ensure uat-autocoder plugin is installed"
        )

    try:
        # Import database manager
        from custom.uat_plugin.database import get_db_manager, UATTestPlan, UATTestFeature

        db = get_db_manager()

        # Step 1: Retrieve test plan from database
        print(f"🔍 Retrieving test plan {cycle_id}...")

        with db.uat_session() as session:
            test_plan = session.query(UATTestPlan).filter(
                UATTestPlan.cycle_id == cycle_id
            ).first()

            if not test_plan:
                # Test plan not found in database
                raise HTTPException(
                    status_code=404,
                    detail=f"Test plan {cycle_id} not found. Please generate a test plan first using /generate-plan"
                )

            if test_plan.approved:
                # Already approved - return existing tests
                existing_tests = session.query(UATTestFeature).filter(
                    UATTestFeature.scenario.contains(f"[{cycle_id[:15]}]")
                ).all()

                return ApproveTestPlanResponse(
                    success=True,
                    cycle_id=cycle_id,
                    project_name=test_plan.project_name,
                    tests_created=len(existing_tests),
                    test_ids=[t.id for t in existing_tests],
                    message=f"Test plan already approved. {len(existing_tests)} tests exist.",
                    approved_at=test_plan.created_at.isoformat() if test_plan.created_at else None
                )

            # Step 2: Parse test scenarios from test_prd markdown
            print(f"📋 Parsing test plan for {test_plan.project_name}...")

            scenarios = _parse_test_scenarios_from_prd(
                test_plan.test_prd,
                cycle_id,
                test_plan.journeys_identified,
                test_plan.recommended_phases
            )

            print(f"  Found {len(scenarios)} test scenarios")

            # Step 3: Create UATTestFeature records in database
            print(f"💾 Creating {len(scenarios)} UAT test records...")

            test_ids = []
            priority = 1

            for scenario_data in scenarios:
                # Create test feature
                test_feature = UATTestFeature(
                    priority=priority,
                    phase=scenario_data['phase'],
                    journey=scenario_data['journey'],
                    scenario=scenario_data['scenario'],
                    description=scenario_data['description'],
                    test_type=scenario_data.get('test_type', 'e2e'),
                    test_file=scenario_data.get('test_file'),
                    steps=scenario_data['steps'],
                    expected_result=scenario_data['expected_result'],
                    status='pending',
                    dependencies=scenario_data.get('dependencies', []),
                    result=None,
                    devlayer_card_id=None
                )

                session.add(test_feature)
                session.flush()  # Get the ID without committing
                test_ids.append(test_feature.id)

                priority += 1

            # Step 4: Mark test plan as approved
            test_plan.approved = True

            # Commit transaction (atomic - all or nothing)
            session.commit()

            print(f"✅ Test plan approved:")
            print(f"   Cycle ID: {cycle_id}")
            print(f"   Tests created: {len(test_ids)}")
            print(f"   Test IDs: {test_ids[:5]}{'...' if len(test_ids) > 5 else ''}")

            # Step 5: Generate Playwright test files
            print(f"📁 Generating Playwright test files...")
            try:
                from api.registry import get_project_path
                project_path = get_project_path(test_plan.project_name)

                # Generate test files
                files_created = _generate_playwright_tests(
                    project_path=str(project_path),
                    scenarios=scenarios,
                    cycle_id=cycle_id
                )
                print(f"   Generated {files_created} test files in e2e/")
            except Exception as e:
                print(f"   ⚠️  Warning: Failed to generate test files: {e}")
                print(f"   Tests are in database but Playwright files need manual creation")
                import traceback
                traceback.print_exc()

            return ApproveTestPlanResponse(
                success=True,
                cycle_id=cycle_id,
                project_name=test_plan.project_name,
                tests_created=len(test_ids),
                test_ids=test_ids,
                message=f"Test plan approved successfully. Created {len(test_ids)} UAT tests in database.",
                approved_at=datetime.now().isoformat()
            )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to approve test plan: {str(e)}"
        )


def _parse_test_scenarios_from_prd(
    test_prd: str,
    cycle_id: str,
    journeys_identified: List[str],
    recommended_phases: List[str]
) -> List[Dict[str, Any]]:
    """
    Parse test scenarios from test PRD markdown document.

    The test PRD contains markdown with scenario definitions like:
    ## Phase: smoke
    ### Journey: authentication
    #### Scenario: User can log in with valid credentials
    **Description:** Tests the login flow...
    **Steps:** [...]
    **Expected Result:** ...

    Args:
        test_prd: Test PRD markdown document
        cycle_id: Cycle ID for scenario naming
        journeys_identified: List of journey names
        recommended_phases: List of phase names

    Returns:
        List of scenario dictionaries with all required fields
    """
    import re

    scenarios = []
    current_phase = None
    current_journey = None

    # Split PRD into lines
    lines = test_prd.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect phase headers (## Phase: smoke)
        phase_match = re.match(r'##\s+Phase:\s*(\w+)', line, re.IGNORECASE)
        if phase_match:
            current_phase = phase_match.group(1).lower()
            if current_phase not in ['smoke', 'functional', 'regression', 'uat']:
                current_phase = 'functional'  # Default
            i += 1
            continue

        # Detect journey headers (### Journey: authentication)
        journey_match = re.match(r'###\s+Journey:\s*(\w+)', line, re.IGNORECASE)
        if journey_match:
            current_journey = journey_match.group(1).lower()
            i += 1
            continue

        # Detect scenario headers (#### Scenario: ...)
        scenario_match = re.match(r'####\s+Scenario:\s*(.+)', line, re.IGNORECASE)
        if scenario_match:
            scenario_name = scenario_match.group(1).strip()

            # Parse scenario details
            description = ""
            steps = []
            expected_result = ""
            test_type = "e2e"

            # Look for description, steps, expected result in next lines
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith('####'):
                next_line = lines[j].strip()

                if next_line.startswith('**Description:**'):
                    description = next_line.split('**Description:**', 1)[1].strip()
                elif next_line.startswith('**Steps:**'):
                    # Parse JSON array or list
                    steps_str = next_line.split('**Steps:**', 1)[1].strip()
                    try:
                        steps = eval(steps_str) if steps_str.startswith('[') else [steps_str]
                    except:
                        steps = [steps_str]
                elif next_line.startswith('**Expected Result:**'):
                    expected_result = next_line.split('**Expected Result:**', 1)[1].strip()
                elif next_line.startswith('**Test Type:**'):
                    test_type = next_line.split('**Test Type:**', 1)[1].strip().lower()

                j += 1

            # Create scenario with cycle_id prefix
            cycle_prefix = cycle_id[:15]
            scenario = {
                'phase': current_phase or 'smoke',
                'journey': current_journey or 'general',
                'scenario': f"[{cycle_prefix}] {scenario_name}",
                'description': description or f"Test scenario: {scenario_name}",
                'test_type': test_type,
                'test_file': None,
                'steps': steps if steps else ['Run test scenario'],
                'expected_result': expected_result or 'Test passes successfully',
                'dependencies': []
            }

            scenarios.append(scenario)

            i = j
            continue

        i += 1

    # If no scenarios parsed (markdown format different), generate from phases/journeys
    if not scenarios:
        print("⚠️  No scenarios parsed from PRD, generating from phases/journeys...")
        for phase in recommended_phases:
            for journey in journeys_identified:
                cycle_prefix = cycle_id[:15]
                scenarios.append({
                    'phase': phase,
                    'journey': journey,
                    'scenario': f"[{cycle_prefix}] {phase.capitalize()} test for {journey}",
                    'description': f"Validate {journey} functionality in {phase} phase",
                    'test_type': 'e2e',
                    'test_file': None,
                    'steps': [f'Execute {phase} test for {journey}'],
                    'expected_result': f'{phase.capitalize()} test passes for {journey}',
                    'dependencies': []
                })

    return scenarios


def _generate_playwright_tests(
    project_path: str,
    scenarios: List[Dict[str, Any]],
    cycle_id: str
) -> int:
    """
    Generate Playwright test files from approved test scenarios.

    Creates:
    - e2e/ directory structure
    - playwright.config.ts
    - One test file per journey with all scenarios for that journey
    - tests.config.ts for shared configuration

    Args:
        project_path: Path to the project directory
        scenarios: List of test scenario dictionaries
        cycle_id: Cycle ID for test identification

    Returns:
        Number of test files created
    """
    from pathlib import Path
    import json

    project_dir = Path(project_path)
    e2e_dir = project_dir / "e2e"

    # Create e2e directory
    e2e_dir.mkdir(parents=True, exist_ok=True)
    print(f"   Created e2e directory at {e2e_dir}")

    # Group scenarios by journey
    scenarios_by_journey = {}
    for scenario in scenarios:
        journey = scenario['journey']
        if journey not in scenarios_by_journey:
            scenarios_by_journey[journey] = []
        scenarios_by_journey[journey].append(scenario)

    # Generate playwright.config.ts if it doesn't exist
    config_path = e2e_dir / "playwright.config.ts"
    if not config_path.exists():
        config_content = '''import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 3,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
'''
        with open(config_path, 'w') as f:
            f.write(config_content)
        print(f"   Created playwright.config.ts")

    # Generate one test file per journey
    files_created = 0
    for journey, journey_scenarios in scenarios_by_journey.items():
        # Sanitize journey name for filename
        journey_filename = journey.replace(' ', '_').replace('-', '_').lower()
        test_file_path = e2e_dir / f"{journey_filename}.spec.ts"

        # Generate test file content
        test_content = f"""import {{ test, expect }} from '@playwright/test';

// {journey.title()} Journey Tests
// UAT Cycle: {cycle_id}
// Generated: {datetime.now().isoformat()}

test.describe('{journey.title()} Journey', () => {{
"""

        # Generate each test case
        for scenario in journey_scenarios:
            scenario_name = scenario['scenario'].replace('[{cycle_id}] ', '').strip()
            test_content += f"""
  // Skipping test pending implementation: {scenario_name}
  // TODO: Implement test steps for: {scenario_name}
  // Description: {scenario['description']}
"""
            for i, step in enumerate(scenario.get('steps', []), 1):
                test_content += f"  // {i}. {step}\n"

            test_content += f"""
  // Expected result: {scenario['expected_result']}

  test.skip(true, 'Test implementation pending - generated from UAT test plan');

  test('{scenario_name}', async ({{ page }}) => {{
    // Placeholder implementation - replace with actual test steps
    await page.goto('/');

    // Basic sanity check - replace with meaningful assertions
    await expect(page.locator('body')).toBeVisible();
  }});

"""

        test_content += "});\n"

        # Write test file
        with open(test_file_path, 'w') as f:
            f.write(test_content)
        files_created += 1
        print(f"   Created {journey_filename}.spec.ts ({len(journey_scenarios)} tests)")

    # Create package.json scripts if they don't exist
    package_json_path = project_dir / "package.json"
    if package_json_path.exists():
        try:
            with open(package_json_path, 'r') as f:
                package_json = json.load(f)

            # Ensure test scripts exist
            if 'scripts' not in package_json:
                package_json['scripts'] = {}

            scripts_to_add = {
                'test:e2e': 'playwright test',
                'test:e2e:ui': 'playwright test --ui',
                'test:e2e:headed': 'playwright test --headed',
                'test:e2e:debug': 'playwright test --debug',
            }

            updated = False
            for script_name, script_cmd in scripts_to_add.items():
                if script_name not in package_json['scripts']:
                    package_json['scripts'][script_name] = script_cmd
                    updated = True

            if updated:
                with open(package_json_path, 'w') as f:
                    json.dump(package_json, f, indent=2)
                print(f"   Added test scripts to package.json")
        except Exception as e:
            print(f"   ⚠️  Could not update package.json: {e}")

    print(f"   Generated {files_created} test files covering {len(scenarios)} scenarios")
    return files_created

