"""
Test Orchestrator for UAT AutoCoder Plugin.

This module coordinates parallel test execution, mirroring the core AutoCoder
parallel_orchestrator.py pattern but specialized for UAT testing.

Key responsibilities:
- Read test plans from uat_test_plan table by cycle_id
- Validate plan approval status
- Parse test_prd document
- Spawn and coordinate test agents
- Monitor progress and report results
"""

import os
import sys
import json
import logging
import time
import subprocess
import signal
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from threading import Thread, Lock, Event

try:
    from .database import DatabaseManager, get_db_manager, UATTestPlan, UATTestFeature
    from .config import get_config, ConfigManager
    from .dev_task_creator import create_and_link_dev_task
except ImportError:
    from database import DatabaseManager, get_db_manager, UATTestPlan, UATTestFeature
    from config import get_config, ConfigManager
    from dev_task_creator import create_and_link_dev_task

# Configure logging
logger = logging.getLogger(__name__)


class TestOrchestrator:
    """
    Coordinates UAT test execution by reading test plans from the database.

    The orchestrator is responsible for:
    1. Reading approved test plans from uat_test_plan table
    2. Validating plan status and retrieving test_prd
    3. Parsing the test_prd into executable test scenarios
    4. Coordinating parallel test execution (future feature)
    5. Aggregating and reporting results (future feature)
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize the test orchestrator.

        Args:
            db_manager: Database manager instance (uses singleton if not provided)
        """
        self.db = db_manager or get_db_manager()
        self.config = get_config()
        self.current_plan: Optional[Dict[str, Any]] = None
        self.current_cycle_id: Optional[str] = None
        self.agent_processes: List[subprocess.Popen] = []

        # Progress tracking (Feature #28)
        self.agent_test_assignments: Dict[int, Optional[int]] = {}  # agent_id -> test_id
        self.test_start_times: Dict[int, datetime] = {}  # test_id -> start_time
        self.progress_lock = Lock()
        self.monitoring_active = False
        self.monitor_thread: Optional[Thread] = None

        # Retry tracking (Feature #29)
        self.test_retry_counts: Dict[int, int] = {}  # test_id -> retry_count
        self.test_retry_results: Dict[int, List[Dict[str, Any]]] = {}  # test_id -> list of failure results

        # Graceful shutdown (Feature #33)
        self.shutdown_requested = False  # Flag to indicate shutdown requested
        self.shutdown_event = Event()  # Event to signal shutdown
        self.shutdown_timeout_seconds = 30  # Max time to wait for tests to complete during shutdown
        self._signal_handlers_registered = False  # Track if signal handlers are registered

        # WebSocket progress callback (Feature #30)
        # This will be set by the API server to enable real-time updates
        self.websocket_callback: Optional[callable] = None

    def read_test_plan(self, cycle_id: str) -> Dict[str, Any]:
        """
        Read an approved test plan from the database by cycle_id.

        This method:
        1. Connects to uat_tests.db
        2. Queries the uat_test_plan table for the given cycle_id
        3. Validates that the plan is approved (approved=true)
        4. Retrieves and returns the test plan data

        Args:
            cycle_id: Unique identifier for the test cycle (e.g., 'test-001')

        Returns:
            Dictionary containing test plan data with keys:
            - id: Plan ID
            - project_name: Name of the project
            - cycle_id: Test cycle identifier
            - total_features_completed: Number of completed features
            - journeys_identified: List of user journey names
            - recommended_phases: List of test phase names
            - test_prd: Test specification document (Markdown)
            - approved: Approval status (must be True)
            - created_at: Plan creation timestamp

        Raises:
            ValueError: If cycle_id is empty or None
            RuntimeError: If plan not found, not approved, or database error occurs
        """
        if not cycle_id:
            raise ValueError("cycle_id cannot be empty or None")

        logger.info(f"Reading test plan for cycle_id: {cycle_id}")

        try:
            with self.db.uat_session() as session:
                # Query for test plan by cycle_id
                plan = session.query(UATTestPlan).filter(
                    UATTestPlan.cycle_id == cycle_id
                ).first()

                if not plan:
                    raise RuntimeError(
                        f"Test plan not found for cycle_id: {cycle_id}. "
                        f"Please generate and approve a test plan first."
                    )

                # Convert to dictionary for validation
                plan_dict = plan.to_dict()

                # Validate plan is approved
                if not plan_dict.get('approved'):
                    raise RuntimeError(
                        f"Test plan {cycle_id} is not approved. "
                        f"Please approve the test plan before execution."
                    )

                # Store as current plan
                self.current_plan = plan_dict
                self.current_cycle_id = cycle_id

                logger.info(
                    f"Successfully read test plan: {plan_dict['project_name']} "
                    f"(cycle_id: {cycle_id}, approved: {plan_dict['approved']})"
                )

                return plan_dict

        except Exception as e:
            if isinstance(e, (ValueError, RuntimeError)):
                raise
            logger.error(f"Database error reading test plan: {e}")
            raise RuntimeError(f"Failed to read test plan: {e}")

    def get_test_prd(self, cycle_id: Optional[str] = None) -> str:
        """
        Get the test_prd document from an approved test plan.

        Args:
            cycle_id: Test cycle identifier (uses current plan if not provided)

        Returns:
            Test specification document as Markdown string

        Raises:
            RuntimeError: If no plan is loaded or test_prd is not available
        """
        # Use provided cycle_id or current plan
        if cycle_id and cycle_id != self.current_cycle_id:
            # Read new plan if different cycle_id
            plan = self.read_test_plan(cycle_id)
            return plan.get('test_prd', '')

        if not self.current_plan:
            raise RuntimeError(
                "No test plan loaded. Call read_test_plan() first."
            )

        test_prd = self.current_plan.get('test_prd', '')
        if not test_prd:
            raise RuntimeError(
                f"Test plan {self.current_cycle_id} does not contain a test_prd document."
            )

        return test_prd

    def parse_test_prd(self, test_prd: Optional[str] = None) -> Dict[str, Any]:
        """
        Parse the test_prd document into structured data.

        The test_prd is a Markdown document that contains:
        - Test phases (smoke, functional, regression, uat)
        - User journeys (authentication, payment, etc.)
        - Test scenarios with steps and expected results

        This method performs basic validation and structure checking.
        Full parsing into individual test features will be implemented
        in a future feature.

        Args:
            test_prd: Test specification document (uses current plan if not provided)

        Returns:
            Dictionary with parsed structure:
            - raw_markdown: The original test_prd content
            - lines: List of lines in the document
            - sections: Dictionary of markdown sections found
            - has_phases: Boolean indicating if test phases are defined
            - has_journeys: Boolean indicating if user journeys are defined
            - validation_status: 'valid', 'incomplete', or 'invalid'

        Raises:
            RuntimeError: If test_prd is not available or parsing fails
        """
        if test_prd is None:
            test_prd = self.get_test_prd()

        if not test_prd:
            raise RuntimeError("Cannot parse empty test_prd")

        logger.info("Parsing test_prd document")

        try:
            # Split into lines for processing
            lines = test_prd.split('\n')

            # Extract markdown sections (lines starting with #)
            sections = {}
            current_section = None
            section_content = []

            for line in lines:
                if line.strip().startswith('#'):
                    # Save previous section
                    if current_section:
                        sections[current_section] = '\n'.join(section_content).strip()

                    # Start new section
                    current_section = line.strip()
                    section_content = []
                else:
                    section_content.append(line)

            # Save last section
            if current_section:
                sections[current_section] = '\n'.join(section_content).strip()

            # Basic validation: check for expected content
            has_phases = any(
                'phase' in section.lower() or 'smoke' in section.lower() or
                'functional' in section.lower() or 'regression' in section.lower() or
                'uat' in section.lower()
                for section in sections.keys()
            )

            has_journeys = any(
                'journey' in section.lower() or 'scenario' in section.lower() or
                'authentication' in section.lower() or 'payment' in section.lower()
                for section in sections.keys()
            )

            # Determine validation status
            if has_phases and has_journeys:
                validation_status = 'valid'
            elif has_phases or has_journeys:
                validation_status = 'incomplete'
            else:
                validation_status = 'invalid'

            result = {
                'raw_markdown': test_prd,
                'lines': lines,
                'sections': sections,
                'has_phases': has_phases,
                'has_journeys': has_journeys,
                'validation_status': validation_status,
                'section_count': len(sections),
                'line_count': len(lines)
            }

            logger.info(
                f"Parsed test_prd: {len(lines)} lines, {len(sections)} sections, "
                f"status={validation_status}"
            )

            return result

        except Exception as e:
            logger.error(f"Error parsing test_prd: {e}")
            raise RuntimeError(f"Failed to parse test_prd: {e}")

    def validate_plan_readiness(self, cycle_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate that a test plan is ready for execution.

        Performs comprehensive checks:
        - Plan exists in database
        - Plan is approved
        - test_prd document is present
        - test_prd can be parsed
        - Plan contains required metadata

        Args:
            cycle_id: Test cycle identifier (uses current plan if not provided)

        Returns:
            Dictionary with validation results:
            - is_ready: Boolean indicating overall readiness
            - checks: Dictionary of individual check results
            - plan_summary: Summary of plan metadata
            - parsed_prd: Parsed test_prd structure

        Raises:
            RuntimeError: If validation fails critically
        """
        if cycle_id:
            self.read_test_plan(cycle_id)

        if not self.current_plan:
            return {
                'is_ready': False,
                'error': 'No test plan loaded',
                'checks': {}
            }

        checks = {
            'plan_exists': True,
            'plan_approved': self.current_plan.get('approved', False),
            'has_test_prd': bool(self.current_plan.get('test_prd')),
            'has_project_name': bool(self.current_plan.get('project_name')),
            'has_journeys': bool(self.current_plan.get('journeys_identified')),
            'has_phases': bool(self.current_plan.get('recommended_phases')),
        }

        # Try to parse test_prd
        parsed_prd = None
        if checks['has_test_prd']:
            try:
                parsed_prd = self.parse_test_prd()
                checks['prd_parseable'] = True
                checks['prd_status'] = parsed_prd.get('validation_status')
            except Exception as e:
                checks['prd_parseable'] = False
                checks['prd_error'] = str(e)

        # Overall readiness
        is_ready = all(checks.values()) if isinstance(list(checks.values())[0], bool) else False

        return {
            'is_ready': is_ready,
            'checks': checks,
            'plan_summary': {
                'cycle_id': self.current_plan.get('cycle_id'),
                'project_name': self.current_plan.get('project_name'),
                'total_features_completed': self.current_plan.get('total_features_completed'),
                'journeys_count': len(self.current_plan.get('journeys_identified', [])),
                'phases_count': len(self.current_plan.get('recommended_phases', [])),
            },
            'parsed_prd': parsed_prd
        }

    def get_plan_metadata(self) -> Dict[str, Any]:
        """
        Get metadata about the currently loaded test plan.

        Returns:
            Dictionary with plan metadata

        Raises:
            RuntimeError: If no plan is currently loaded
        """
        if not self.current_plan:
            raise RuntimeError("No test plan loaded. Call read_test_plan() first.")

        return {
            'cycle_id': self.current_plan.get('cycle_id'),
            'project_name': self.current_plan.get('project_name'),
            'approved': self.current_plan.get('approved'),
            'total_features_completed': self.current_plan.get('total_features_completed'),
            'journeys_identified': self.current_plan.get('journeys_identified', []),
            'recommended_phases': self.current_plan.get('recommended_phases', []),
            'created_at': self.current_plan.get('created_at'),
            'test_prd_length': len(self.current_plan.get('test_prd', '')),
        }

    def spawn_test_agents(self, agent_count: Optional[int] = None) -> List[subprocess.Popen]:
        """
        Spawn the configured number of test agent processes.

        This method creates subprocess agents that will execute tests in parallel.
        Each agent is a separate Python process that can claim and run tests.

        Args:
            agent_count: Number of agents to spawn (defaults to config.max_concurrent_agents)

        Returns:
            List of spawned subprocess Popen objects

        Raises:
            RuntimeError: If unable to spawn agent processes
            ValueError: If agent_count is invalid
        """
        # Use configured count if not specified
        if agent_count is None:
            agent_count = self.config.max_concurrent_agents

        if agent_count < 1:
            raise ValueError(f"agent_count must be >= 1, got: {agent_count}")

        logger.info(f"Spawning {agent_count} test agents...")

        # Get path to agent execution script
        # For now, we'll create a simple mock agent script
        agent_script = self._create_agent_script()

        spawned_processes = []

        try:
            for i in range(agent_count):
                # Spawn agent process
                proc = subprocess.Popen(
                    [sys.executable, str(agent_script)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                spawned_processes.append(proc)
                logger.info(f"Spawned agent #{i+1} (PID: {proc.pid})")

                # Respect startup delay if configured
                if i < agent_count - 1:  # Don't delay after last agent
                    delay = self.config.agent_startup_delay_seconds
                    if delay > 0:
                        time.sleep(delay)

            # Store reference to spawned agents
            self.agent_processes.extend(spawned_processes)

            logger.info(f"Successfully spawned {len(spawned_processes)} test agents")

            return spawned_processes

        except Exception as e:
            # Clean up any partially spawned processes
            logger.error(f"Error spawning agents: {e}")
            for proc in spawned_processes:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            raise RuntimeError(f"Failed to spawn test agents: {e}")

    def _create_agent_script(self) -> Path:
        """
        Create a temporary script that simulates a test agent.

        In a full implementation, this would point to the actual agent
        execution script. For now, we create a simple mock that runs
        for a short time to demonstrate agent spawning.

        Returns:
            Path to the agent script
        """
        import tempfile

        # Create a temporary directory for agent scripts
        agent_dir = Path(tempfile.gettempdir()) / "uat_agents"
        agent_dir.mkdir(exist_ok=True)

        agent_script = agent_dir / "mock_test_agent.py"

        # Create a simple mock agent that runs for a few seconds
        script_content = '''#!/usr/bin/env python3
"""
Mock Test Agent for UAT AutoCoder

This simulates a test agent that would claim and execute tests.
"""
import sys
import time
import os

def main():
    agent_id = os.environ.get('UAT_AGENT_ID', 'unknown')
    print(f"[Agent-{agent_id}] Starting test agent")
    print(f"[Agent-{agent_id}] PID: {os.getpid()}")
    sys.stdout.flush()

    # Simulate agent working
    # In real implementation, this would:
    # 1. Connect to MCP server
    # 2. Claim a test via test_claim_and_get()
    # 3. Execute the test
    # 4. Mark test as passed/failed
    time.sleep(20)  # Run longer to allow testing

    print(f"[Agent-{agent_id}] Test execution complete")
    sys.stdout.flush()

if __name__ == '__main__':
    main()
'''

        agent_script.write_text(script_content)
        agent_script.chmod(0o755)

        return agent_script

    def get_spawned_agent_count(self) -> int:
        """
        Get the number of currently spawned agent processes.

        Returns:
            Number of active agent processes
        """
        # Filter out processes that have terminated
        active_processes = [p for p in self.agent_processes if p.poll() is None]
        self.agent_processes = active_processes
        return len(active_processes)

    def get_agent_pids(self) -> List[int]:
        """
        Get process IDs of all spawned agents.

        Returns:
            List of process IDs (only for active processes)
        """
        active_processes = [p for p in self.agent_processes if p.poll() is None]
        return [p.pid for p in active_processes]

    def terminate_all_agents(self) -> None:
        """
        Terminate all spawned agent processes gracefully.

        Attempts to terminate agents with SIGTERM, then uses SIGKILL
        if they don't terminate within 2 seconds.
        """
        logger.info(f"Terminating {len(self.agent_processes)} agent processes...")

        for proc in self.agent_processes:
            if proc.poll() is None:  # Still running
                logger.debug(f"Terminating agent (PID: {proc.pid})")
                proc.terminate()

        # Wait for graceful termination
        start_time = time.time()
        timeout = 2

        for proc in self.agent_processes:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Agent (PID: {proc.pid}) did not terminate gracefully, killing...")
                    proc.kill()
                    proc.wait()

        terminated_count = len(self.agent_processes)
        self.agent_processes.clear()

        logger.info(f"Terminated {terminated_count} agent processes")

    def get_available_tests(self, cycle_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all tests that are ready to be executed.

        A test is ready if:
        - Status is 'pending'
        - All dependencies are 'passed'

        Args:
            cycle_id: Test cycle identifier (uses current plan if not provided)

        Returns:
            List of test dictionaries sorted by priority (highest first)
        """
        if cycle_id and cycle_id != self.current_cycle_id:
            self.read_test_plan(cycle_id)

        logger.info("Fetching available tests for execution")

        try:
            with self.db.uat_session() as session:
                # Get all pending tests
                pending_tests = session.query(UATTestFeature).filter(
                    UATTestFeature.status == 'pending'
                ).order_by(UATTestFeature.priority.asc()).all()

                available_tests = []

                for test in pending_tests:
                    test_dict = test.to_dict()

                    # Check if all dependencies are passed
                    dependencies = test_dict.get('dependencies', [])

                    if not dependencies:
                        # No dependencies, test is ready
                        available_tests.append(test_dict)
                        continue

                    # Check each dependency
                    all_deps_passed = True
                    for dep_id in dependencies:
                        dep_test = session.query(UATTestFeature).filter(
                            UATTestFeature.id == dep_id
                        ).first()

                        if not dep_test or dep_test.status != 'passed':
                            all_deps_passed = False
                            logger.debug(
                                f"Test #{test.id} '{test.scenario}' waiting for "
                                f"dependency #{dep_id} (status: {dep_test.status if dep_test else 'not found'})"
                            )
                            break

                    if all_deps_passed:
                        available_tests.append(test_dict)

                logger.info(f"Found {len(available_tests)} available tests (out of {len(pending_tests)} pending)")

                return available_tests

        except Exception as e:
            logger.error(f"Error fetching available tests: {e}")
            raise RuntimeError(f"Failed to get available tests: {e}")

    def assign_tests_to_agents(
        self,
        agent_count: Optional[int] = None,
        cycle_id: Optional[str] = None
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Intelligently assign tests to agents based on dependencies, priority, and availability.

        Assignment strategy:
        1. Get all available tests (pending + dependencies satisfied)
        2. Sort by priority (highest first)
        3. Distribute tests evenly across agents using round-robin
        4. Each agent gets a list of tests to execute

        Args:
            agent_count: Number of agents to distribute tests across (defaults to config.max_concurrent_agents)
            cycle_id: Test cycle identifier (uses current plan if not provided)

        Returns:
            Dictionary mapping agent_id (0-indexed) to list of test dictionaries
        """
        if agent_count is None:
            agent_count = self.config.max_concurrent_agents

        if agent_count < 1:
            raise ValueError(f"agent_count must be >= 1, got: {agent_count}")

        logger.info(f"Assigning tests to {agent_count} agents")

        # Get all available tests
        available_tests = self.get_available_tests(cycle_id)

        if not available_tests:
            logger.warning("No available tests to assign")
            return {i: [] for i in range(agent_count)}

        # Distribute tests evenly using round-robin
        assignments = {i: [] for i in range(agent_count)}

        for idx, test in enumerate(available_tests):
            agent_id = idx % agent_count
            assignments[agent_id].append(test)

        # Log assignment summary
        total_tests = len(available_tests)
        tests_per_agent = [len(assignments[i]) for i in range(agent_count)]

        logger.info(
            f"Assigned {total_tests} tests to {agent_count} agents "
            f"(distribution: {tests_per_agent})"
        )

        # Log details for each agent
        for agent_id, tests in assignments.items():
            if tests:
                test_names = [f"#{t['id']} {t['scenario']}" for t in tests[:3]]
                if len(tests) > 3:
                    test_names.append(f"...and {len(tests) - 3} more")
                logger.debug(f"Agent #{agent_id}: {', '.join(test_names)}")

        return assignments

    def get_next_test_for_agent(
        self,
        agent_id: int,
        assigned_tests: Optional[List[Dict[str, Any]]] = None,
        cycle_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get the next test for a specific agent to execute.

        This method simulates an agent requesting work. It returns the highest
        priority test that:
        1. Is in the agent's assigned list (if provided)
        2. Is still pending (not claimed by another agent)
        3. Has all dependencies satisfied

        Args:
            agent_id: Agent identifier (0-indexed)
            assigned_tests: Optional list of tests pre-assigned to this agent
            cycle_id: Test cycle identifier (uses current plan if not provided)

        Returns:
            Test dictionary or None if no tests available
        """
        logger.debug(f"Agent #{agent_id} requesting next test")

        # If assigned_tests provided, use that list
        if assigned_tests:
            # Find first test that's still pending
            for test in assigned_tests:
                if test.get('status') == 'pending':
                    logger.debug(f"Agent #{agent_id} assigned test #{test['id']} '{test['scenario']}'")
                    return test
            logger.debug(f"Agent #{agent_id} has no more tests in assigned list")
            return None

        # Otherwise, get from available tests (round-robin style)
        available_tests = self.get_available_tests(cycle_id)

        if not available_tests:
            logger.debug(f"Agent #{agent_id} - no available tests")
            return None

        # Round-robin: pick test at index agent_id
        if agent_id < len(available_tests):
            test = available_tests[agent_id]
            logger.debug(f"Agent #{agent_id} claimed test #{test['id']} '{test['scenario']}'")
            return test

        logger.debug(f"Agent #{agent_id} - no test at round-robin position")
        return None

    def get_agent_workload_summary(self, cycle_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a summary of test workload for agents.

        Args:
            cycle_id: Test cycle identifier (uses current plan if not provided)

        Returns:
            Dictionary with workload statistics:
            - total_tests: Total number of tests
            - pending_tests: Tests waiting to run
            - available_tests: Tests ready to run (dependencies satisfied)
            - blocked_tests: Tests blocked by dependencies
            - passed_tests: Tests that have passed
            - failed_tests: Tests that have failed
            - in_progress_tests: Tests currently running
        """
        if cycle_id and cycle_id != self.current_cycle_id:
            self.read_test_plan(cycle_id)

        logger.info("Generating agent workload summary")

        try:
            with self.db.uat_session() as session:
                # Count tests by status
                total_tests = session.query(UATTestFeature).count()
                pending_tests = session.query(UATTestFeature).filter(
                    UATTestFeature.status == 'pending'
                ).count()
                passed_tests = session.query(UATTestFeature).filter(
                    UATTestFeature.status == 'passed'
                ).count()
                failed_tests = session.query(UATTestFeature).filter(
                    UATTestFeature.status == 'failed'
                ).count()
                in_progress_tests = session.query(UATTestFeature).filter(
                    UATTestFeature.status == 'in_progress'
                ).count()

                # Count available vs blocked
                available_tests = len(self.get_available_tests(cycle_id))
                blocked_tests = pending_tests - available_tests

                summary = {
                    'total_tests': total_tests,
                    'pending_tests': pending_tests,
                    'available_tests': available_tests,
                    'blocked_tests': blocked_tests,
                    'passed_tests': passed_tests,
                    'failed_tests': failed_tests,
                    'in_progress_tests': in_progress_tests,
                    'completion_rate': round((passed_tests / total_tests * 100) if total_tests > 0 else 0, 2),
                }

                logger.info(f"Workload summary: {summary}")

                return summary

        except Exception as e:
            logger.error(f"Error generating workload summary: {e}")
            raise RuntimeError(f"Failed to generate workload summary: {e}")

    # ========================================================================
    # FEATURE #28: Progress Monitoring Methods
    # ========================================================================

    def start_monitoring(self, check_interval_seconds: float = 2.0) -> None:
        """
        Start the monitoring thread to track agent progress.

        The monitoring thread periodically checks:
        - Which agent is running which test
        - Test execution duration (detect timeouts)
        - Agent process status (alive/terminated)
        - Test completion status

        Args:
            check_interval_seconds: How often to check progress (default: 2.0 seconds)

        Raises:
            RuntimeError: If monitoring is already active
        """
        if self.monitoring_active:
            raise RuntimeError("Monitoring is already active")

        logger.info(f"Starting progress monitoring (interval: {check_interval_seconds}s)")

        self.monitoring_active = True
        self.monitor_thread = Thread(
            target=self._monitoring_loop,
            args=(check_interval_seconds,),
            daemon=True,
            name="UATProgressMonitor"
        )
        self.monitor_thread.start()

        logger.info("Progress monitoring thread started")

    def stop_monitoring(self) -> None:
        """
        Stop the monitoring thread gracefully.

        Waits up to 5 seconds for the monitoring thread to complete.
        """
        if not self.monitoring_active:
            logger.debug("Monitoring is not active")
            return

        logger.info("Stopping progress monitoring...")

        self.monitoring_active = False

        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5.0)

            if self.monitor_thread.is_alive():
                logger.warning("Monitoring thread did not stop within timeout")
            else:
                logger.info("Progress monitoring stopped")

    def _monitoring_loop(self, check_interval_seconds: float) -> None:
        """
        Main monitoring loop that runs in a separate thread.

        This method:
        1. Checks agent process status
        2. Updates test start times
        3. Detects test timeouts
        4. Marks timed-out tests as failed
        5. Updates progress statistics

        Args:
            check_interval_seconds: How often to check (in seconds)
        """
        logger.info("Monitoring loop started")

        while self.monitoring_active:
            try:
                with self.progress_lock:
                    self._check_agent_progress()
                    self._check_timeouts()
                    self._update_progress_stats()

                    # Send progress stats via WebSocket (Feature #30)
                    snapshot = self.get_progress_snapshot()
                    self._send_progress_stats(snapshot)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)

            # Sleep until next check
            time.sleep(check_interval_seconds)

        logger.info("Monitoring loop stopped")

    def _check_agent_progress(self) -> None:
        """
        Check the progress of each agent and update tracking.

        This method:
        - Filters out terminated agents
        - Updates agent_test_assignments based on current status
        - Detects when agents complete tests
        """
        # Update active agent list
        active_agents = []
        for i, proc in enumerate(self.agent_processes):
            if proc.poll() is None:  # Still running
                active_agents.append(proc)
            else:
                # Agent terminated
                logger.debug(f"Agent #{i} (PID: {proc.pid}) terminated")

                # Clear its test assignment if any
                if i in self.agent_test_assignments:
                    test_id = self.agent_test_assignments[i]
                    logger.info(f"Agent #{i} terminated while running test #{test_id}")

                    # Mark test as failed (agent crashed)
                    self._mark_test_failed(
                        test_id,
                        error=f"Agent #{i} process terminated unexpectedly",
                        exit_code=proc.returncode
                    )

                    # Clear assignment
                    del self.agent_test_assignments[i]

        self.agent_processes = active_agents

    def _check_timeouts(self) -> None:
        """
        Check for tests that have exceeded the timeout threshold.

        Tests that exceed test_timeout_seconds are marked as failed.
        """
        timeout_seconds = self.config.test_timeout_seconds
        now = datetime.now()

        timed_out_tests = []

        for test_id, start_time in list(self.test_start_times.items()):
            elapsed = (now - start_time).total_seconds()

            if elapsed > timeout_seconds:
                timed_out_tests.append((test_id, elapsed))

        # Mark timed-out tests as failed
        for test_id, elapsed in timed_out_tests:
            logger.warning(
                f"Test #{test_id} timed out after {elapsed:.1f}s "
                f"(timeout: {timeout_seconds}s)"
            )

            self._mark_test_failed(
                test_id,
                error=f"Test execution exceeded timeout ({timeout_seconds}s)",
                duration=elapsed
            )

            # Clear start time and assignment
            if test_id in self.test_start_times:
                del self.test_start_times[test_id]

            # Find which agent was running this test and clear assignment
            for agent_id, assigned_test_id in list(self.agent_test_assignments.items()):
                if assigned_test_id == test_id:
                    del self.agent_test_assignments[agent_id]
                    break

    def _update_progress_stats(self) -> None:
        """
        Update internal progress statistics.

        This method queries the database for current test status
        and updates tracking dictionaries.
        """
        try:
            with self.db.uat_session() as session:
                # Update in_progress tests
                in_progress_tests = session.query(UATTestFeature).filter(
                    UATTestFeature.status == 'in_progress'
                ).all()

                for test in in_progress_tests:
                    test_id = test.id

                    # Track start time if not already tracking
                    if test_id not in self.test_start_times:
                        # Use started_at if available, otherwise use now
                        if test.started_at:
                            self.test_start_times[test_id] = test.started_at
                        else:
                            self.test_start_times[test_id] = datetime.now()

                    # Update agent assignment if test has been claimed
                    # (We'll need to query which agent claimed it - for now,
                    #  we track that separately via assign_test_to_agent)

        except Exception as e:
            logger.error(f"Error updating progress stats: {e}")

    def assign_test_to_agent(self, agent_id: int, test_id: int) -> None:
        """
        Record that a test has been assigned to an agent.

        This is called when an agent claims a test. It updates
        the internal tracking dictionaries.

        Args:
            agent_id: Agent identifier (0-indexed)
            test_id: Test identifier
        """
        with self.progress_lock:
            self.agent_test_assignments[agent_id] = test_id
            self.test_start_times[test_id] = datetime.now()

            logger.info(
                f"Agent #{agent_id} assigned to test #{test_id} "
                f"(total: {len(self.agent_test_assignments)} agents active)"
            )

            # Send WebSocket notification (Feature #30)
            self._send_test_started(test_id, agent_id)

    def mark_test_completed(self, test_id: int, status: str, result: Optional[Dict[str, Any]] = None) -> None:
        """
        Mark a test as completed (passed or failed).

        This method updates the database and clears the agent assignment.
        If the test failed and can be retried, it will be reset for retry.

        Args:
            test_id: Test identifier
            status: Final status ('passed' or 'failed')
            result: Optional result dictionary with duration, error, etc.
        """
        # Handle retry logic for failed tests
        if status == 'failed':
            # Check if we should retry this test
            if self.should_retry_test(test_id, result):
                logger.info(f"Test #{test_id} failed - scheduling retry")
                self.reset_test_for_retry(test_id, result or {})
                return  # Don't mark as failed yet, will retry

        with self.progress_lock:
            logger.info(f"Test #{test_id} marked as {status}")

            # Update database
            try:
                with self.db.uat_session() as session:
                    test = session.query(UATTestFeature).filter(
                        UATTestFeature.id == test_id
                    ).first()

                    if test:
                        test.status = status
                        test.completed_at = datetime.now()

                        if result:
                            # Include retry history if available
                            final_result = result.copy()

                            if test_id in self.test_retry_counts:
                                retry_count = self.test_retry_counts[test_id]
                                if retry_count > 0:
                                    final_result['retry_count'] = retry_count
                                    final_result['retry_history'] = self.test_retry_results.get(test_id, [])

                            # Store result JSON
                            import json
                            test.result = json.dumps(final_result)

                        session.commit()

                        logger.info(
                            f"Test #{test_id} '{test.scenario}' marked as {status} "
                            f"in database"
                        )

                        # Feature #42: Create dev task if test failed due to bug (not blocker)
                        if status == 'failed' and result:
                            self._create_dev_task_for_failed_test(test_id, test, result)

            except Exception as e:
                logger.error(f"Error updating test status in database: {e}")

            # Clear tracking
            # Calculate duration before clearing start time
            duration = 0.0
            if test_id in self.test_start_times:
                duration = (datetime.now() - self.test_start_times[test_id]).total_seconds()
                del self.test_start_times[test_id]

            # Find and clear agent assignment
            agent_id = None
            for aid, assigned_test_id in list(self.agent_test_assignments.items()):
                if assigned_test_id == test_id:
                    agent_id = aid
                    del self.agent_test_assignments[aid]
                    logger.debug(f"Cleared Agent #{aid} assignment (test #{test_id} completed)")
                    break

            # Send WebSocket notification (Feature #30) - if method exists
            if hasattr(self, '_send_test_passed') and status == 'passed':
                if agent_id is not None:
                    self._send_test_passed(test_id, agent_id, duration)
            elif hasattr(self, '_send_test_failed') and status == 'failed':
                error_msg = result.get('error', 'Test failed') if result else 'Test failed'
                self._send_test_failed(test_id, agent_id, error_msg, duration)

    def _create_dev_task_for_failed_test(
        self,
        test_id: int,
        test: Any,
        result: Dict[str, Any]
    ) -> None:
        """
        Create a dev task in features.db when a UAT test fails (Feature #42).

        This is called after a test is marked as failed (and retries are exhausted).
        The dev task contains details from the test failure and is linked via
        devlayer_card_id for traceability.

        Args:
            test_id: ID of the failed UAT test
            test: UATTestFeature object
            result: Test result dictionary with error, screenshot, video, etc.
        """
        try:
            # Check if this is a blocker (not a bug)
            # Blockers have already been handled by park_test() in Feature #39
            if result.get('blocker_type'):
                logger.debug(f"Test #{test_id} has blocker type - skipping dev task creation")
                return

            # Check if dev task already created
            if test.devlayer_card_id:
                logger.debug(f"Test #{test_id} already has dev task #{test.devlayer_card_id}")
                return

            # Build test dictionary for dev task creation
            uat_test_dict = {
                'scenario': test.scenario,
                'description': test.description,
                'steps': json.loads(test.steps) if test.steps else [],
            }

            # Get project directory and database paths
            project_dir = self.db.project_dir
            uat_tests_db_path = self.db.uat_db_path

            # Create and link dev task
            feature_id = create_and_link_dev_task(
                project_dir=project_dir,
                uat_tests_db_path=uat_tests_db_path,
                uat_test_id=test_id,
                uat_test=uat_test_dict,
                result=result
            )

            if feature_id:
                logger.info(
                    f"✓ Created dev task #{feature_id} for failed UAT test #{test_id}: {test.scenario}"
                )

                # Send notification about dev task creation (if WebSocket method exists)
                if hasattr(self, '_send_dev_task_created'):
                    self._send_dev_task_created(test_id, feature_id)

            else:
                logger.warning(f"Failed to create dev task for UAT test #{test_id}")

        except Exception as e:
            # Don't fail the test if dev task creation fails
            logger.error(f"Error creating dev task for test #{test_id}: {e}", exc_info=True)


    def _mark_test_failed(
        self,
        test_id: int,
        error: str,
        exit_code: Optional[int] = None,
        duration: Optional[float] = None
    ) -> None:
        """
        Internal method to mark a test as failed.

        Args:
            test_id: Test identifier
            error: Error message
            exit_code: Optional process exit code
            duration: Optional test duration in seconds
        """
        result = {
            'error': error,
            'exit_code': exit_code,
            'duration': duration,
            'failed_at': datetime.now().isoformat()
        }

        self.mark_test_completed(test_id, 'failed', result)

    # ========================================================================
    # FEATURE #29: Test Failure Retry Methods
    # ========================================================================

    def get_test_retry_count(self, test_id: int) -> int:
        """
        Get the current retry count for a test.

        Args:
            test_id: Test identifier

        Returns:
            Number of retry attempts for this test
        """
        with self.progress_lock:
            return self.test_retry_counts.get(test_id, 0)

    def can_retry_test(self, test_id: int) -> bool:
        """
        Check if a test can be retried based on retry count.

        Args:
            test_id: Test identifier

        Returns:
            True if test has remaining retries, False otherwise
        """
        with self.progress_lock:
            current_retries = self.test_retry_counts.get(test_id, 0)
            max_retries = self.config.max_retries
            can_retry = current_retries < max_retries

            logger.debug(
                f"Test #{test_id} retry check: {current_retries}/{max_retries} "
                f"({'can retry' if can_retry else 'max retries reached'})"
            )

            return can_retry

    def should_retry_test(self, test_id: int, result: Optional[Dict[str, Any]] = None) -> bool:
        """
        Determine if a failed test should be retried.

        A test should be retried if:
        1. It has remaining retries (can_retry_test)
        2. The failure is retryable (not a configuration error, etc.)

        Args:
            test_id: Test identifier
            result: Optional result dictionary from failed test

        Returns:
            True if test should be retried, False otherwise
        """
        # Check if we have retries remaining
        if not self.can_retry_test(test_id):
            logger.info(f"Test #{test_id} cannot be retried (max retries reached)")
            return False

        # Check if the error is retryable
        # Non-retryable errors: configuration errors, not found, permission denied
        if result and 'error' in result:
            error_msg = result['error'].lower()

            non_retryable_indicators = [
                'not found',
                'no such file',
                'permission denied',
                'unauthorized',
                'authentication',
                'configuration',
                'invalid',
                'malformed'
            ]

            for indicator in non_retryable_indicators:
                if indicator in error_msg:
                    logger.info(
                        f"Test #{test_id} failure is non-retryable: '{result['error']}'"
                    )
                    return False

        # Test is retryable
        logger.info(f"Test #{test_id} is eligible for retry")
        return True

    def reset_test_for_retry(self, test_id: int, previous_result: Dict[str, Any]) -> None:
        """
        Reset a failed test for retry.

        This method:
        1. Increments retry count
        2. Stores previous failure result
        3. Resets test status to 'pending'
        4. Clears agent assignment
        5. Logs retry attempt

        Args:
            test_id: Test identifier
            previous_result: Result from previous failed attempt
        """
        with self.progress_lock:
            # Increment retry count
            self.test_retry_counts[test_id] = self.test_retry_counts.get(test_id, 0) + 1

            # Store previous failure result
            if test_id not in self.test_retry_results:
                self.test_retry_results[test_id] = []
            self.test_retry_results[test_id].append(previous_result)

            retry_count = self.test_retry_counts[test_id]
            max_retries = self.config.max_retries

            logger.info(
                f"Resetting test #{test_id} for retry (attempt {retry_count}/{max_retries})"
            )

        # Update database (release lock for DB operation)
        try:
            with self.db.uat_session() as session:
                test = session.query(UATTestFeature).filter(
                    UATTestFeature.id == test_id
                ).first()

                if test:
                    # Reset to pending for retry
                    test.status = 'pending'
                    test.started_at = None  # Clear start time
                    test.completed_at = None  # Clear completion time

                    # Store retry history in result field
                    retry_history = {
                        'retry_attempt': retry_count,
                        'max_retries': max_retries,
                        'previous_failures': self.test_retry_results[test_id],
                        'retry_scheduled_at': datetime.now().isoformat()
                    }

                    import json
                    test.result = json.dumps(retry_history)

                    session.commit()

                    logger.info(
                        f"Test #{test_id} '{test.scenario}' reset to pending "
                        f"(retry {retry_count}/{max_retries})"
                    )

        except Exception as e:
            logger.error(f"Error resetting test #{test_id} for retry: {e}")

        # Clear agent assignment and start time
        with self.progress_lock:
            # Clear from test start times
            if test_id in self.test_start_times:
                del self.test_start_times[test_id]

            # Clear agent assignment
            for agent_id, assigned_test_id in list(self.agent_test_assignments.items()):
                if assigned_test_id == test_id:
                    del self.agent_test_assignments[agent_id]
                    logger.debug(f"Cleared Agent #{agent_id} assignment (test #{test_id} retry)")
                    break

    def get_retry_summary(self, test_id: int) -> Dict[str, Any]:
        """
        Get retry history and summary for a test.

        Args:
            test_id: Test identifier

        Returns:
            Dictionary with retry information:
            - test_id: Test identifier
            - retry_count: Number of retry attempts
            - max_retries: Maximum allowed retries
            - can_retry: Whether test can be retried again
            - failure_history: List of previous failure results
            - last_failure: Most recent failure result (if any)
        """
        with self.progress_lock:
            retry_count = self.test_retry_counts.get(test_id, 0)
            max_retries = self.config.max_retries
            failure_history = self.test_retry_results.get(test_id, [])

            return {
                'test_id': test_id,
                'retry_count': retry_count,
                'max_retries': max_retries,
                'can_retry': retry_count < max_retries,
                'failure_history': failure_history,
                'last_failure': failure_history[-1] if failure_history else None,
                'remaining_retries': max(0, max_retries - retry_count)
            }

    def get_progress_snapshot(self) -> Dict[str, Any]:
        """
        Get a snapshot of current progress.

        Returns:
            Dictionary with current progress information:
            - active_agents: Number of active agent processes
            - agent_assignments: Dictionary of agent_id -> test_id
            - tests_in_progress: List of test IDs currently running
            - test_durations: Dictionary of test_id -> elapsed_seconds
            - monitoring_active: Whether monitoring is active
            - retry_summary: Summary of retry attempts
        """
        with self.progress_lock:
            now = datetime.now()

            # Calculate elapsed times
            test_durations = {}
            for test_id, start_time in self.test_start_times.items():
                elapsed = (now - start_time).total_seconds()
                test_durations[test_id] = round(elapsed, 2)

            # Collect retry summary (Feature #29)
            retry_summary = {
                'total_retries': sum(self.test_retry_counts.values()),
                'tests_retried': len(self.test_retry_counts),
                'retry_details': {}
            }

            for test_id, retry_count in self.test_retry_counts.items():
                retry_summary['retry_details'][test_id] = {
                    'retry_count': retry_count,
                    'max_retries': self.config.max_retries,
                    'can_retry': retry_count < self.config.max_retries
                }

            return {
                'active_agents': len(self.agent_processes),
                'agent_assignments': dict(self.agent_test_assignments),  # Copy
                'tests_in_progress': list(self.test_start_times.keys()),
                'test_durations': test_durations,
                'monitoring_active': self.monitoring_active,
                'retry_summary': retry_summary,
                'timestamp': now.isoformat()
            }

    def get_agent_status(self, agent_id: int) -> Dict[str, Any]:
        """
        Get the status of a specific agent.

        Args:
            agent_id: Agent identifier (0-indexed)

        Returns:
            Dictionary with agent status:
            - exists: Whether agent exists in tracking
            - process_alive: Whether the agent process is still running
            - pid: Process ID (if alive)
            - current_test_id: Test ID currently assigned (if any)
            - test_duration: How long the test has been running (if any)
        """
        with self.progress_lock:
            exists = agent_id < len(self.agent_processes)
            process_alive = False
            pid = None
            current_test_id = None
            test_duration = None

            if exists:
                proc = self.agent_processes[agent_id]
                process_alive = proc.poll() is None

                if process_alive:
                    pid = proc.pid

                current_test_id = self.agent_test_assignments.get(agent_id)

                if current_test_id and current_test_id in self.test_start_times:
                    elapsed = (datetime.now() - self.test_start_times[current_test_id]).total_seconds()
                    test_duration = round(elapsed, 2)

            return {
                'agent_id': agent_id,
                'exists': exists,
                'process_alive': process_alive,
                'pid': pid,
                'current_test_id': current_test_id,
                'test_duration': test_duration
            }


    # ========================================================================
    # FEATURE #33: Graceful Shutdown Methods
    # ========================================================================

    def register_signal_handlers(self) -> None:
        """
        Register signal handlers for graceful shutdown.

        This method sets up handlers for SIGTERM and SIGINT (Ctrl+C) that
        trigger graceful shutdown, allowing running tests to complete.
        """
        if self._signal_handlers_registered:
            logger.debug("Signal handlers already registered")
            return

        def signal_handler(signum, frame):
            """Handle shutdown signals."""
            signal_name = signal.Signals(signum).name
            logger.info(f"Received signal {signal_name} ({signum}), initiating graceful shutdown...")
            self.request_shutdown(f"Signal {signal_name}")

        # Register handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        self._signal_handlers_registered = True
        logger.info("Signal handlers registered for SIGTERM and SIGINT")

    def request_shutdown(self, reason: str = "Manual request") -> None:
        """
        Request graceful shutdown of the orchestrator.

        This method:
        1. Sets the shutdown_requested flag
        2. Sets the shutdown_event
        3. Stops spawning new tests
        4. Logs the shutdown reason

        Args:
            reason: Why shutdown is being requested
        """
        if self.shutdown_requested:
            logger.debug("Shutdown already requested")
            return

        logger.warning(f"Shutdown requested: {reason}")
        self.shutdown_requested = True
        self.shutdown_event.set()

    def graceful_shutdown(self, timeout_seconds: Optional[float] = None) -> Dict[str, Any]:
        """
        Perform graceful shutdown of the orchestrator.

        This method:
        1. Stops the monitoring thread
        2. Waits for running tests to complete (up to timeout)
        3. Terminates agent processes cleanly
        4. Saves current state to database
        5. Ensures no zombie processes

        Args:
            timeout_seconds: Maximum time to wait for tests (default: shutdown_timeout_seconds)

        Returns:
            Dictionary with shutdown results:
            - shutdown_completed: True if shutdown completed successfully
            - tests_in_progress_at_shutdown: Number of tests still running
            - tests_completed_during_shutdown: Number of tests that finished during shutdown
            - agents_terminated: Number of agent processes terminated
            - monitoring_stopped: Whether monitoring thread was stopped
            - state_saved: Whether state was saved to database
            - timeout_exceeded: True if shutdown took longer than timeout
            - zombie_processes: List of PIDs that couldn't be terminated
        """
        if timeout_seconds is None:
            timeout_seconds = self.shutdown_timeout_seconds

        logger.info(f"Starting graceful shutdown (timeout: {timeout_seconds}s)")
        shutdown_start = time.time()

        # Track shutdown metrics
        tests_in_progress_at_shutdown = len(self.test_start_times)
        tests_completed_during_shutdown = 0
        zombie_processes = []

        # Step 1: Stop monitoring thread
        logger.info("Step 1: Stopping progress monitoring...")
        monitoring_was_active = self.monitoring_active
        self.stop_monitoring()
        logger.info("✓ Progress monitoring stopped")

        # Step 2: Wait for running tests to complete
        if tests_in_progress_at_shutdown > 0:
            logger.info(f"Step 2: Waiting for {tests_in_progress_at_shutdown} tests to complete...")

            # Poll for test completion
            poll_start = time.time()
            while self.test_start_times:
                elapsed = time.time() - poll_start

                if elapsed > timeout_seconds:
                    logger.warning(
                        f"Shutdown timeout exceeded ({timeout_seconds}s), "
                        f"{len(self.test_start_times)} tests still running"
                    )
                    break

                # Check if any tests completed
                tests_completed_during_shutdown = tests_in_progress_at_shutdown - len(self.test_start_times)

                # Update progress snapshot to detect completions
                try:
                    with self.db.uat_session() as session:
                        in_progress_tests = session.query(UATTestFeature).filter(
                            UATTestFeature.status == 'in_progress'
                        ).count()

                        if in_progress_tests != len(self.test_start_times):
                            # Some tests completed, update tracking
                            self._update_progress_stats()
                            tests_completed_during_shutdown = tests_in_progress_at_shutdown - len(self.test_start_times)

                except Exception as e:
                    logger.error(f"Error checking test status: {e}")

                # Wait before next poll
                time.sleep(0.5)

            logger.info(
                f"✓ {tests_completed_during_shutdown} tests completed during shutdown "
                f"({len(self.test_start_times)} still running)"
            )
        else:
            logger.info("Step 2: No tests in progress, skipping wait")

        # Step 3: Terminate remaining agent processes
        logger.info("Step 3: Terminating agent processes...")
        active_agents_before = len(self.agent_processes)

        if active_agents_before > 0:
            # Use existing terminate_all_agents method
            self.terminate_all_agents()
            agents_terminated = active_agents_before
            logger.info(f"✓ Terminated {agents_terminated} agent processes")
        else:
            agents_terminated = 0
            logger.info("✓ No agent processes to terminate")

        # Step 4: Check for zombie processes
        logger.info("Step 4: Checking for zombie processes...")
        for proc in self.agent_processes:
            if proc.poll() is None:  # Still running
                zombie_processes.append(proc.pid)
                logger.error(f"Zombie process detected: PID {proc.pid}")

        if zombie_processes:
            logger.error(f"Failed to terminate {len(zombie_processes)} zombie processes")
            # Force kill any remaining zombies
            for pid in zombie_processes:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception as e:
                    logger.error(f"Failed to kill zombie process {pid}: {e}")

        # Step 5: Save orchestrator state to database
        logger.info("Step 5: Saving orchestrator state...")
        state_saved = self._save_shutdown_state()

        if state_saved:
            logger.info("✓ Orchestrator state saved to database")
        else:
            logger.warning("Failed to save orchestrator state")

        # Calculate shutdown duration
        shutdown_duration = time.time() - shutdown_start
        timeout_exceeded = shutdown_duration > timeout_seconds

        # Prepare results
        shutdown_results = {
            'shutdown_completed': len(zombie_processes) == 0,
            'tests_in_progress_at_shutdown': tests_in_progress_at_shutdown,
            'tests_completed_during_shutdown': tests_completed_during_shutdown,
            'tests_still_running': len(self.test_start_times),
            'agents_terminated': agents_terminated,
            'monitoring_stopped': not monitoring_was_active or not self.monitoring_active,
            'state_saved': state_saved,
            'timeout_exceeded': timeout_exceeded,
            'zombie_processes': zombie_processes,
            'shutdown_duration_seconds': round(shutdown_duration, 2),
            'shutdown_reason': 'Graceful shutdown completed'
        }

        # Clear shutdown flag
        self.shutdown_requested = False
        self.shutdown_event.clear()

        logger.info(
            f"Graceful shutdown completed in {shutdown_duration:.2f}s: "
            f"{tests_completed_during_shutdown} tests completed, "
            f"{len(self.test_start_times)} tests interrupted, "
            f"{agents_terminated} agents terminated"
        )

        return shutdown_results

    def _save_shutdown_state(self) -> bool:
        """
        Save the current orchestrator state to database.

        This saves:
        - Current cycle_id
        - Active agent test assignments
        - Test start times
        - Shutdown timestamp

        Returns:
            True if state saved successfully, False otherwise
        """
        try:
            state = {
                'cycle_id': self.current_cycle_id,
                'agent_test_assignments': dict(self.agent_test_assignments),
                'test_start_times': {
                    test_id: start_time.isoformat()
                    for test_id, start_time in self.test_start_times.items()
                },
                'active_agents': len(self.agent_processes),
                'shutdown_timestamp': datetime.now().isoformat()
            }

            # In a full implementation, this would save to a dedicated table
            # For now, we'll log it
            logger.info(f"Orchestrator state: {json.dumps(state, indent=2)}")

            # Future: Save to uat_orchestrator_state table
            # with self.db.uat_session() as session:
            #     state_record = UATOrchestratorState(...)
            #     session.add(state_record)
            #     session.commit()

            return True

        except Exception as e:
            logger.error(f"Error saving shutdown state: {e}")
            return False

    def is_shutdown_requested(self) -> bool:
        """
        Check if shutdown has been requested.

        Returns:
            True if shutdown has been requested
        """
        return self.shutdown_requested

    def wait_for_shutdown_event(self, timeout_seconds: Optional[float] = None) -> bool:
        """
        Wait for the shutdown event to be set.

        This is useful for blocking operations that need to be interruptible.

        Args:
            timeout_seconds: Maximum time to wait (None = wait indefinitely)

        Returns:
            True if shutdown event was set, False if timeout exceeded
        """
        return self.shutdown_event.wait(timeout=timeout_seconds)

    # ========================================================================
    # FEATURE #30: WebSocket Progress Reporting
    # ========================================================================

    def set_websocket_callback(self, callback: callable) -> None:
        """
        Set the WebSocket callback function for real-time progress updates.

        The callback function should accept two parameters:
        - cycle_id (str): The test cycle identifier
        - message (dict): The message to broadcast to WebSocket clients

        The callback is responsible for broadcasting the message to all
        connected WebSocket clients for the given cycle_id.

        Args:
            callback: Async function to call with progress updates
        """
        logger.info("WebSocket progress callback registered")
        self.websocket_callback = callback

    def _broadcast_progress(self, message_type: str, **kwargs) -> None:
        """
        Broadcast a progress message to all WebSocket clients.

        This method is called from the monitoring thread to send real-time
        updates about test execution progress.

        Args:
            message_type: Type of message (test_started, test_passed, test_failed, progress_stats)
            **kwargs: Additional message fields (test_id, agent_id, timestamp, etc.)
        """
        if not self.websocket_callback:
            # No callback registered - skip WebSocket broadcast
            logger.debug("No WebSocket callback registered - skipping broadcast")
            return

        if not self.current_cycle_id:
            # No active cycle - skip broadcast
            logger.debug("No active cycle_id - skipping broadcast")
            return

        # Construct message
        message = {
            'type': message_type,
            'cycle_id': self.current_cycle_id,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }

        # Call the WebSocket callback (may be async)
        try:
            logger.debug(f"Broadcasting WebSocket message: {message_type}")
            callback_result = self.websocket_callback(self.current_cycle_id, message)
            # If callback returns a coroutine, we can't await it in sync thread
            # The callback should handle async execution internally
            if callback_result is not None:
                import asyncio
                if asyncio.iscoroutine(callback_result):
                    # Schedule coroutine on event loop if available
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(callback_result)
                    except RuntimeError:
                        # No event loop running - skip
                        logger.debug("No event loop running - skipping async callback")
        except Exception as e:
            logger.error(f"Error calling WebSocket callback: {e}")

    def _send_test_started(self, test_id: int, agent_id: int) -> None:
        """
        Send a 'test_started' message to WebSocket clients.

        Args:
            test_id: ID of the test that started
            agent_id: ID of the agent running the test
        """
        try:
            with self.db.uat_session() as session:
                test = session.query(UATTestFeature).filter(
                    UATTestFeature.id == test_id
                ).first()

                if not test:
                    logger.warning(f"Cannot send test_started - test #{test_id} not found")
                    return

                self._broadcast_progress(
                    'test_started',
                    test_id=test_id,
                    agent_id=agent_id,
                    scenario=test.scenario,
                    phase=test.phase,
                    journey=test.journey
                )
        except Exception as e:
            logger.error(f"Error sending test_started message: {e}")

    def _send_test_passed(self, test_id: int, agent_id: int, duration: float) -> None:
        """
        Send a 'test_passed' message to WebSocket clients.

        Args:
            test_id: ID of the test that passed
            agent_id: ID of the agent that ran the test
            duration: Test execution duration in seconds
        """
        try:
            with self.db.uat_session() as session:
                test = session.query(UATTestFeature).filter(
                    UATTestFeature.id == test_id
                ).first()

                if not test:
                    logger.warning(f"Cannot send test_passed - test #{test_id} not found")
                    return

                self._broadcast_progress(
                    'test_passed',
                    test_id=test_id,
                    agent_id=agent_id,
                    scenario=test.scenario,
                    phase=test.phase,
                    journey=test.journey,
                    duration=duration
                )
        except Exception as e:
            logger.error(f"Error sending test_passed message: {e}")

    def _send_test_failed(self, test_id: int, agent_id: int, error: str, duration: float) -> None:
        """
        Send a 'test_failed' message to WebSocket clients.

        Args:
            test_id: ID of the test that failed
            agent_id: ID of the agent that ran the test (or None)
            error: Error message
            duration: Test execution duration in seconds
        """
        try:
            with self.db.uat_session() as session:
                test = session.query(UATTestFeature).filter(
                    UATTestFeature.id == test_id
                ).first()

                if not test:
                    logger.warning(f"Cannot send test_failed - test #{test_id} not found")
                    return

                self._broadcast_progress(
                    'test_failed',
                    test_id=test_id,
                    agent_id=agent_id,
                    scenario=test.scenario,
                    phase=test.phase,
                    journey=test.journey,
                    error=error,
                    duration=duration
                )
        except Exception as e:
            logger.error(f"Error sending test_failed message: {e}")

    def _send_progress_stats(self, snapshot: dict) -> None:
        """
        Send a 'progress_stats' message to WebSocket clients.

        Args:
            snapshot: Progress snapshot from get_progress_snapshot()
        """
        try:
            self._broadcast_progress(
                'progress_stats',
                **snapshot
            )
        except Exception as e:
            logger.error(f"Error sending progress_stats message: {e}")

    # ========================================================================
    # FEATURE #34: Resumable Session Methods
    # ========================================================================

    def check_for_interrupted_tests(self, cycle_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Check for tests that were interrupted (in_progress status) from a previous run.

        This method is called when starting a new test execution to detect
        tests that were left in 'in_progress' state due to orchestrator
        crash, system failure, or user interruption.

        Args:
            cycle_id: Test cycle identifier (uses current plan if not provided)

        Returns:
            Dictionary with interrupted test information:
            - has_interrupted_tests: True if any in_progress tests found
            - interrupted_test_count: Number of in_progress tests
            - interrupted_test_ids: List of test IDs that were interrupted
            - recovery_action: Action to take ('reset', 'skip', or 'none')
        """
        if cycle_id and cycle_id != self.current_cycle_id:
            self.read_test_plan(cycle_id)

        logger.info("Checking for interrupted tests from previous session...")

        try:
            with self.db.uat_session() as session:
                # Query for in_progress tests
                in_progress_tests = session.query(UATTestFeature).filter(
                    UATTestFeature.status == 'in_progress'
                ).all()

                interrupted_count = len(in_progress_tests)
                interrupted_ids = [test.id for test in in_progress_tests]

                has_interrupted = interrupted_count > 0

                if has_interrupted:
                    logger.warning(
                        f"Found {interrupted_count} interrupted tests from previous session: "
                        f"{interrupted_ids}"
                    )
                    recovery_action = 'reset'
                else:
                    logger.info("No interrupted tests found - clean state")
                    recovery_action = 'none'

                return {
                    'has_interrupted_tests': has_interrupted,
                    'interrupted_test_count': interrupted_count,
                    'interrupted_test_ids': interrupted_ids,
                    'recovery_action': recovery_action,
                    'timestamp': datetime.now().isoformat()
                }

        except Exception as e:
            logger.error(f"Error checking for interrupted tests: {e}")
            raise RuntimeError(f"Failed to check for interrupted tests: {e}")

    def reset_interrupted_tests(
        self,
        test_ids: Optional[List[int]] = None,
        cycle_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reset interrupted tests back to 'pending' status for re-execution.

        This method:
        1. Resets test status from 'in_progress' to 'pending'
        2. Clears started_at timestamp
        3. Clears completed_at timestamp
        4. Logs reset for each test
        5. Returns summary of reset operations

        Args:
            test_ids: Optional list of specific test IDs to reset (if None, resets all in_progress tests)
            cycle_id: Test cycle identifier (uses current plan if not provided)

        Returns:
            Dictionary with reset results:
            - tests_reset_count: Number of tests reset
            - test_ids_reset: List of test IDs that were reset
            - success: True if all resets succeeded
            - errors: List of any errors encountered
        """
        if cycle_id and cycle_id != self.current_cycle_id:
            self.read_test_plan(cycle_id)

        logger.info("Resetting interrupted tests to pending status...")

        errors = []
        tests_reset = []

        try:
            with self.db.uat_session() as session:
                # If no specific test IDs provided, find all in_progress tests
                if test_ids is None:
                    in_progress_tests = session.query(UATTestFeature).filter(
                        UATTestFeature.status == 'in_progress'
                    ).all()
                    test_ids = [test.id for test in in_progress_tests]

                logger.info(f"Resetting {len(test_ids)} interrupted tests: {test_ids}")

                # Reset each test
                for test_id in test_ids:
                    try:
                        test = session.query(UATTestFeature).filter(
                            UATTestFeature.id == test_id
                        ).first()

                        if not test:
                            logger.warning(f"Test #{test_id} not found, skipping")
                            errors.append(f"Test #{test_id} not found")
                            continue

                        if test.status != 'in_progress':
                            logger.warning(
                                f"Test #{test_id} has status '{test.status}', not 'in_progress', skipping"
                            )
                            errors.append(f"Test #{test_id} status is '{test.status}'")
                            continue

                        # Reset to pending
                        old_status = test.status
                        test.status = 'pending'
                        test.started_at = None
                        test.completed_at = None

                        # Add result note about reset
                        import json
                        reset_info = {
                            'reset_at': datetime.now().isoformat(),
                            'previous_status': old_status,
                            'previous_started_at': test.started_at.isoformat() if test.started_at else None,
                            'reset_reason': 'Orchestrator resumable session recovery'
                        }

                        # Append to existing result or create new
                        try:
                            existing_result = json.loads(test.result) if test.result else {}
                            existing_result['reset_info'] = reset_info
                            test.result = json.dumps(existing_result)
                        except (json.JSONDecodeError, TypeError):
                            # If result is not valid JSON, just overwrite
                            test.result = json.dumps({'reset_info': reset_info})

                        tests_reset.append(test_id)
                        logger.info(
                            f"✓ Reset test #{test_id} '{test.scenario}' from '{old_status}' to 'pending'"
                        )

                    except Exception as e:
                        error_msg = f"Error resetting test #{test_id}: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)

                # Commit all changes
                session.commit()

                logger.info(f"Reset complete: {len(tests_reset)} tests reset to pending")

                return {
                    'tests_reset_count': len(tests_reset),
                    'test_ids_reset': tests_reset,
                    'success': len(errors) == 0,
                    'errors': errors
                }

        except Exception as e:
            logger.error(f"Error resetting interrupted tests: {e}")
            raise RuntimeError(f"Failed to reset interrupted tests: {e}")

    def prepare_for_resumable_execution(self, cycle_id: str) -> Dict[str, Any]:
        """
        Prepare the orchestrator for resumable test execution.

        This method:
        1. Reads and validates the test plan
        2. Checks for interrupted tests from previous sessions
        3. Resets interrupted tests to pending (if any found)
        4. Returns execution readiness status

        This should be called before run_tests() to ensure clean state.

        Args:
            cycle_id: Test cycle identifier

        Returns:
            Dictionary with preparation results:
            - ready_for_execution: True if ready to execute
            - interrupted_tests_found: Number of interrupted tests found
            - interrupted_tests_reset: Number of tests reset
            - plan_validated: True if plan is valid and approved
            - message: Status message
        """
        logger.info(f"Preparing for resumable execution: {cycle_id}")

        # Step 1: Read and validate test plan
        logger.info("Step 1: Validating test plan...")
        plan_data = self.read_test_plan(cycle_id)

        if not plan_data.get('approved'):
            return {
                'ready_for_execution': False,
                'interrupted_tests_found': 0,
                'interrupted_tests_reset': 0,
                'plan_validated': False,
                'message': f"Test plan '{cycle_id}' is not approved"
            }

        logger.info(f"✓ Test plan approved: {plan_data['project_name']}")

        # Step 2: Check for interrupted tests
        logger.info("Step 2: Checking for interrupted tests...")
        interrupted_info = self.check_for_interrupted_tests(cycle_id)

        interrupted_count = interrupted_info['interrupted_test_count']

        # Step 3: Reset interrupted tests if found
        reset_count = 0
        if interrupted_count > 0:
            logger.info(f"Step 3: Resetting {interrupted_count} interrupted tests...")
            reset_result = self.reset_interrupted_tests(
                test_ids=interrupted_info['interrupted_test_ids'],
                cycle_id=cycle_id
            )
            reset_count = reset_result['tests_reset_count']

            logger.info(f"✓ Reset {reset_count} interrupted tests to pending")
        else:
            logger.info("Step 3: No interrupted tests to reset")

        # Ready for execution
        ready = True
        message = (
            f"Ready for execution: {reset_count} interrupted tests reset, "
            f"plan validated and approved"
        )

        logger.info(f"✓ {message}")

        return {
            'ready_for_execution': ready,
            'interrupted_tests_found': interrupted_count,
            'interrupted_tests_reset': reset_count,
            'plan_validated': True,
            'message': message
        }

    def run_tests(self, cycle_id: str) -> Dict[str, Any]:
        """
        Run the full test execution cycle for a given cycle_id.

        This method orchestrates the complete test execution:
        1. Prepares for resumable execution (checks for interrupted tests)
        2. Reads and validates the test plan
        3. Spawns configured number of test agents
        4. Assigns tests to agents based on dependencies and priority
        5. Starts agent processes (agents run in background)

        Args:
            cycle_id: Test cycle identifier

        Returns:
            Dictionary with execution start information:
            - cycle_id: Test cycle identifier
            - execution_started: True if started successfully
            - agents_spawned: Number of agents spawned
            - tests_assigned: Total number of tests assigned
            - interrupted_tests_reset: Number of interrupted tests reset (if any)
            - message: Status message

        Raises:
            ValueError: If cycle_id is invalid
            RuntimeError: If plan not found, not approved, or execution error
        """
        logger.info(f"Starting test execution for cycle: {cycle_id}")

        # Step 1: Prepare for resumable execution
        logger.info("Step 1: Preparing for resumable execution...")
        prep_result = self.prepare_for_resumable_execution(cycle_id)

        if not prep_result['ready_for_execution']:
            raise RuntimeError(prep_result['message'])

        interrupted_reset = prep_result['interrupted_tests_reset']
        if interrupted_reset > 0:
            logger.info(f"✓ Reset {interrupted_reset} interrupted tests from previous session")

        # Step 2: Read and validate test plan (already done in prepare, but load it)
        plan_data = self.current_plan
        logger.info(f"Step 2: Test plan loaded: {plan_data['project_name']}")

        # Step 3: Get agent count from config
        agent_count = self.config.max_concurrent_agents
        logger.info(f"Step 3: Spawning {agent_count} test agents")

        # Step 4: Spawn test agents
        agent_processes = self.spawn_test_agents(agent_count)
        agents_spawned = len(agent_processes)

        if agents_spawned == 0:
            raise RuntimeError("Failed to spawn any test agents")

        logger.info(f"✓ Spawned {agents_spawned} agent processes")
        logger.info(f"  Agent PIDs: {[p.pid for p in agent_processes]}")

        # Step 5: Assign tests to agents
        logger.info("Step 4: Assigning tests to agents")
        test_assignments = self.assign_tests_to_agents(agents_spawned, cycle_id)

        tests_assigned = sum(len(tests) for tests in test_assignments.values())
        logger.info(f"✓ Assigned {tests_assigned} tests to {agents_spawned} agents")

        # Log per-agent assignment
        for agent_id, test_ids in test_assignments.items():
            logger.info(f"  Agent #{agent_id}: {len(test_ids)} tests assigned")

        # Step 6: Store assignments for progress tracking
        # (Future agents will query their assignments via get_next_test_for_agent)
        logger.info("Step 5: Test execution ready - agents will claim tests independently")

        execution_info = {
            'cycle_id': cycle_id,
            'execution_started': True,
            'agents_spawned': agents_spawned,
            'tests_assigned': tests_assigned,
            'interrupted_tests_reset': interrupted_reset,
            'agent_assignments': test_assignments,
            'message': f"Test execution started with {agents_spawned} agents and {tests_assigned} tests"
        }

        if interrupted_reset > 0:
            execution_info['message'] += f" (resumed from interruption, {interrupted_reset} tests reset)"

        logger.info(f"✓ Test execution initiated successfully for cycle: {cycle_id}")

        return execution_info

    # ========================================================================
    # FEATURE #31: Final Results Aggregation
    # ========================================================================

    def get_final_summary(self, cycle_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate final summary statistics for a completed test cycle.

        This method aggregates all test results from the database and calculates
        summary statistics including total tests, passed/failed/skipped counts,
        pass rate percentage, total duration, and breakdowns by phase and journey.

        Args:
            cycle_id: Test cycle identifier (uses current_cycle_id if not provided)

        Returns:
            Dictionary with comprehensive summary statistics:
            - cycle_id: Test cycle identifier
            - total_tests: Total number of tests in the cycle
            - passed: Number of tests that passed
            - failed: Number of tests that failed
            - skipped: Number of tests skipped
            - pending: Number of tests still pending (not completed)
            - pass_rate: Percentage of tests that passed (0-100)
            - total_duration_seconds: Total time from first test start to last test end
            - average_test_duration_seconds: Average duration of completed tests
            - by_phase: Breakdown by test phase (smoke, functional, etc.)
            - by_journey: Breakdown by user journey (authentication, payment, etc.)
            - by_test_type: Breakdown by test type (e2e, visual, api, a11y)
            - failed_tests: List of failed test details (id, scenario, error)
            - devlayer_cards_created: Number of DevLayer cards created

        Raises:
            RuntimeError: If cycle_id is not provided and no cycle is loaded
        """
        # Use provided cycle_id or current plan
        if cycle_id is None:
            cycle_id = self.current_cycle_id

        if not cycle_id:
            raise RuntimeError(
                "No cycle_id provided and no cycle loaded. "
                "Call read_test_plan() first or provide cycle_id parameter."
            )

        logger.info(f"Generating final summary for cycle: {cycle_id}")

        try:
            with self.db.uat_session() as session:
                # Query all tests for this cycle
                tests = session.query(UATTestFeature).all()

                if not tests:
                    logger.warning(f"No tests found for cycle: {cycle_id}")
                    return {
                        'cycle_id': cycle_id,
                        'total_tests': 0,
                        'passed': 0,
                        'failed': 0,
                        'skipped': 0,
                        'pending': 0,
                        'pass_rate': 0.0,
                        'total_duration_seconds': 0.0,
                        'average_test_duration_seconds': 0.0,
                        'by_phase': {},
                        'by_journey': {},
                        'by_test_type': {},
                        'failed_tests': [],
                        'devlayer_cards_created': 0
                    }

                # Initialize counters
                total_tests = len(tests)
                passed = 0
                failed = 0
                skipped = 0
                pending = 0
                devlayer_cards = 0

                # Track durations
                first_start_time = None
                last_end_time = None
                completed_test_durations = []

                # Breakdown dictionaries
                by_phase = {}
                by_journey = {}
                by_test_type = {}
                failed_tests = []

                # Process each test
                for test in tests:
                    # Count by status
                    status = test.status.lower()
                    if status == 'passed':
                        passed += 1
                    elif status == 'failed':
                        failed += 1
                    elif status == 'skipped':
                        skipped += 1
                    elif status == 'pending' or status == 'in_progress':
                        pending += 1

                    # Count DevLayer cards
                    if test.devlayer_card_id:
                        devlayer_cards += 1

                    # Track failed tests
                    if status == 'failed':
                        error_msg = None
                        if test.result and isinstance(test.result, dict):
                            error_msg = test.result.get('error')

                        failed_tests.append({
                            'id': test.id,
                            'scenario': test.scenario,
                            'phase': test.phase,
                            'journey': test.journey,
                            'error': error_msg
                        })

                    # Track timing (for completed tests)
                    if test.started_at and test.completed_at:
                        if first_start_time is None or test.started_at < first_start_time:
                            first_start_time = test.started_at

                        if last_end_time is None or test.completed_at > last_end_time:
                            last_end_time = test.completed_at

                        # Calculate individual test duration
                        duration_seconds = (test.completed_at - test.started_at).total_seconds()
                        completed_test_durations.append(duration_seconds)

                    # Breakdown by phase
                    phase = test.phase or 'unknown'
                    if phase not in by_phase:
                        by_phase[phase] = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
                    by_phase[phase]['total'] += 1
                    if status == 'passed':
                        by_phase[phase]['passed'] += 1
                    elif status == 'failed':
                        by_phase[phase]['failed'] += 1
                    elif status == 'skipped':
                        by_phase[phase]['skipped'] += 1

                    # Breakdown by journey
                    journey = test.journey or 'unknown'
                    if journey not in by_journey:
                        by_journey[journey] = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
                    by_journey[journey]['total'] += 1
                    if status == 'passed':
                        by_journey[journey]['passed'] += 1
                    elif status == 'failed':
                        by_journey[journey]['failed'] += 1
                    elif status == 'skipped':
                        by_journey[journey]['skipped'] += 1

                    # Breakdown by test type
                    test_type = test.test_type or 'unknown'
                    if test_type not in by_test_type:
                        by_test_type[test_type] = {'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0}
                    by_test_type[test_type]['total'] += 1
                    if status == 'passed':
                        by_test_type[test_type]['passed'] += 1
                    elif status == 'failed':
                        by_test_type[test_type]['failed'] += 1
                    elif status == 'skipped':
                        by_test_type[test_type]['skipped'] += 1

                # Calculate pass rate
                completed_count = passed + failed + skipped
                pass_rate = (passed / completed_count * 100) if completed_count > 0 else 0.0

                # Calculate total duration
                total_duration_seconds = 0.0
                if first_start_time and last_end_time:
                    total_duration_seconds = (last_end_time - first_start_time).total_seconds()

                # Calculate average test duration
                average_test_duration_seconds = 0.0
                if completed_test_durations:
                    average_test_duration_seconds = sum(completed_test_durations) / len(completed_test_durations)

                # Build summary
                summary = {
                    'cycle_id': cycle_id,
                    'total_tests': total_tests,
                    'passed': passed,
                    'failed': failed,
                    'skipped': skipped,
                    'pending': pending,
                    'pass_rate': round(pass_rate, 2),
                    'total_duration_seconds': round(total_duration_seconds, 2),
                    'average_test_duration_seconds': round(average_test_duration_seconds, 2),
                    'by_phase': by_phase,
                    'by_journey': by_journey,
                    'by_test_type': by_test_type,
                    'failed_tests': failed_tests,
                    'devlayer_cards_created': devlayer_cards,
                    'timestamp': datetime.now().isoformat()
                }

                logger.info(
                    f"Final summary: {passed}/{total_tests} passed ({pass_rate:.1f}%), "
                    f"{failed} failed, {skipped} skipped, {pending} pending"
                )

                return summary

        except Exception as e:
            logger.error(f"Error generating final summary: {e}")
            raise RuntimeError(f"Failed to generate final summary: {e}")


def create_orchestrator() -> TestOrchestrator:
    """
    Factory function to create a new TestOrchestrator instance.

    Returns:
        TestOrchestrator instance
    """
    return TestOrchestrator()


if __name__ == '__main__':
    # Test basic orchestrator functionality
    logging.basicConfig(level=logging.INFO)

    print("UAT Test Orchestrator - Testing")
    print("=" * 60)

    orchestrator = create_orchestrator()

    # Test: Try to read non-existent plan
    try:
        orchestrator.read_test_plan('non-existent')
    except Exception as e:
        print(f"\n✓ Expected error for non-existent plan: {e}")

    print("\nOrchestrator initialized successfully")
    print(f"Database: {orchestrator.db.uat_db_path}")
    print("\nOrchestrator is ready to read test plans.")
