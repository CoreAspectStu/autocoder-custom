"""
Orchestrator - Coordinate the complete UAT testing cycle

This module orchestrates the entire UAT testing process:
1. Parse spec.yaml
2. Extract journeys
3. Generate tests
4. Execute tests
5. Process results
6. Update Kanban
"""

import sys
import os  # Feature #267: For getpid() in lock file
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import time
import threading
import fcntl  # Feature #267: File locking for double-start prevention


from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import OrchestratorError, handle_errors
from uat_gateway.state_manager.state_manager import StateManager, ExecutionState
from uat_gateway.journey_extractor.journey_extractor import JourneyExtractor, Journey
from uat_gateway.test_generator.test_generator import TestGenerator, GeneratedTest
from uat_gateway.test_executor.test_executor import TestExecutor, TestResult
from uat_gateway.test_executor.performance_detector import PerformanceDetector  # Feature #186
from uat_gateway.result_processor.result_processor import ResultProcessor, ProcessedResult
from uat_gateway.kanban_integrator.kanban_integrator import KanbanIntegrator, JourneyCard, ScenarioCard, BugKanbanCard
from uat_gateway.orchestrator.prerequisite_validator import PrerequisiteValidator, ValidationResult
from uat_gateway.ui.events import get_event_manager  # Feature #231: Success notifications


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator"""
    spec_path: str = "spec.yaml"
    test_directory: str = "tests/e2e"
    output_directory: str = "output"
    state_directory: str = "state"
    base_url: str = "http://localhost:3000"
    kanban_api_url: Optional[str] = None
    kanban_api_token: Optional[str] = None

    # Execution options
    parallel_execution: bool = True
    max_parallel_tests: int = 3
    retry_flaky_tests: bool = True
    max_retries: int = 2

    # State management
    enable_checkpoints: bool = True
    checkpoint_interval_seconds: int = 60


@dataclass
class OrchestratorResult:
    """Result of a complete UAT cycle"""
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float

    # Stage results
    spec_parsed: bool = False
    journeys_extracted: bool = False
    tests_generated: bool = False
    tests_executed: bool = False
    results_processed: bool = False
    kanban_updated: bool = False

    # Metrics
    total_journeys: int = 0
    total_scenarios: int = 0
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    pass_rate: float = 0.0

    # Artifacts
    journey_cards_created: List[JourneyCard] = field(default_factory=list)
    scenario_cards_created: List[ScenarioCard] = field(default_factory=list)
    bug_cards_created: List[BugKanbanCard] = field(default_factory=list)

    # Errors
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "success": self.success,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": self.duration_seconds,
            "spec_parsed": self.spec_parsed,
            "journeys_extracted": self.journeys_extracted,
            "tests_generated": self.tests_generated,
            "tests_executed": self.tests_executed,
            "results_processed": self.results_processed,
            "kanban_updated": self.kanban_updated,
            "total_journeys": self.total_journeys,
            "total_scenarios": self.total_scenarios,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "pass_rate": self.pass_rate,
            "journey_cards_created": [c.card_id for c in self.journey_cards_created],
            "scenario_cards_created": [c.card_id for c in self.scenario_cards_created],
            "bug_cards_created": [c.card_id for c in self.bug_cards_created],
            "errors": self.errors
        }


@dataclass
class ExecutionSummary:
    """Summary of test execution results"""
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int = 0
    pass_rate: float = 0.0
    duration_ms: int = 0

    def __post_init__(self):
        """Calculate pass rate if not provided"""
        if self.pass_rate == 0.0 and self.total_tests > 0:
            self.pass_rate = (self.passed_tests / self.total_tests) * 100


# ============================================================================
# Orchestrator
# ============================================================================

class Orchestrator:
    """
    Main orchestrator for UAT testing cycle

    Coordinates all components:
    - JourneyExtractor: Parse spec and extract journeys
    - TestGenerator: Generate test code
    - TestExecutor: Run tests and capture artifacts
    - PerformanceDetector: Track and analyze execution times (Feature #186)
    - ResultProcessor: Process results and determine actions
    - KanbanIntegrator: Create/update Kanban cards
    - StateManager: Maintain execution state
    """

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.logger = get_logger(__name__)
        self.state_manager = StateManager(state_directory=config.state_directory)

        # Initialize components (set to None first)
        self.journey_extractor: Optional[JourneyExtractor] = None
        self.test_generator: Optional[TestGenerator] = None
        self.test_executor: Optional[TestExecutor] = None
        self.performance_detector: Optional[PerformanceDetector] = None  # Feature #186
        self.result_processor: Optional[ResultProcessor] = None
        self.kanban_integrator: Optional[KanbanIntegrator] = None
        self.prerequisite_validator: Optional[PrerequisiteValidator] = None
        self.event_manager = None  # Feature #231: Success notifications

        # Execution state
        self.state: Optional[ExecutionState] = None
        self.result: Optional[OrchestratorResult] = None

        # Store raw test results for processing
        self._raw_test_results: List[TestResult] = []

        # Feature #269: Double-click protection (in-memory)
        # Prevents duplicate test execution when user double-clicks submit button
        self._is_cycle_running: bool = False
        self._current_cycle_id: Optional[str] = None

        # Feature #267: File-based lock for cross-process protection
        # Prevents multiple UAT cycles from running simultaneously across different processes
        self._lock_file_path: Path = Path(config.state_directory) / "uat_cycle.lock"
        self._lock_file: Optional[object] = None  # Will hold file object for fcntl

        # Initialize all components
        self.initialize_components()

    def initialize_components(self):
        """Initialize all component modules"""
        self.logger.info("Initializing orchestrator components...")

        # Journey Extractor
        self.journey_extractor = JourneyExtractor()
        self.logger.info("✓ JourneyExtractor initialized")

        # Test Generator
        from uat_gateway.test_generator.test_generator import TestConfig
        test_config = TestConfig(
            output_directory=self.config.test_directory,
            base_url=self.config.base_url
        )
        self.test_generator = TestGenerator(config=test_config)
        self.logger.info("✓ TestGenerator initialized")

        # Test Executor
        from uat_gateway.test_executor.test_executor import ExecutionConfig
        execution_config = ExecutionConfig(
            test_directory=self.config.test_directory,
            output_directory=self.config.output_directory,
            base_url=self.config.base_url
        )
        self.test_executor = TestExecutor(config=execution_config)
        self.logger.info("✓ TestExecutor initialized")

        # Performance Detector (Feature #186)
        self.performance_detector = PerformanceDetector(state_manager=self.state_manager)
        self.logger.info("✓ PerformanceDetector initialized")

        # Result Processor
        self.result_processor = ResultProcessor()
        self.logger.info("✓ ResultProcessor initialized")

        # Kanban Integrator (optional)
        if self.config.kanban_api_url and self.config.kanban_api_token:
            self.kanban_integrator = KanbanIntegrator(
                api_url=self.config.kanban_api_url,
                api_token=self.config.kanban_api_token
            )
            self.logger.info("✓ KanbanIntegrator initialized")
        else:
            self.logger.warning("Kanban integration disabled (no API credentials)")

        # Prerequisite Validator
        self.prerequisite_validator = PrerequisiteValidator(
            base_url=self.config.base_url
        )
        self.logger.info("✓ PrerequisiteValidator initialized")

        # Event Manager (Feature #231: Success notifications)
        self.event_manager = get_event_manager()
        self.logger.info("✓ EventManager initialized for success notifications")

    def _acquire_cycle_lock(self) -> bool:
        """
        Feature #267: Acquire file-based lock to prevent concurrent UAT cycles

        Uses fcntl.flock() for cross-process locking. This prevents multiple
        UAT cycles from running simultaneously, even from different processes.

        Returns:
            True if lock was acquired successfully
            False if lock is held by another process

        Raises:
            OrchestratorError: If lock file cannot be created
        """
        try:
            # Ensure state directory exists
            self._lock_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Open lock file (create if doesn't exist)
            self._lock_file = open(self._lock_file_path, 'w')

            # Try to acquire exclusive, non-blocking lock
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Lock acquired successfully
                self._lock_file.write(f"{datetime.now().isoformat()}\n")
                self._lock_file.write(f"PID: {os.getpid()}\n")
                self._lock_file.flush()
                self.logger.info(f"✓ Cycle lock acquired: {self._lock_file_path}")
                return True
            except BlockingIOError:
                # Lock is held by another process
                self._lock_file.close()
                self._lock_file = None
                self.logger.warning(f"⚠️  Cycle lock is held by another process")
                return False

        except Exception as e:
            # Clean up on error
            if self._lock_file:
                try:
                    self._lock_file.close()
                except:
                    pass
                self._lock_file = None
            raise OrchestratorError(f"Failed to acquire cycle lock: {e}")

    def _release_cycle_lock(self):
        """
        Feature #267: Release file-based lock after cycle completion

        Releases the lock and optionally cleans up the lock file.
        """
        if self._lock_file:
            try:
                # Release lock
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                self._lock_file = None
                self.logger.info("✓ Cycle lock released")

                # Clean up lock file
                if self._lock_file_path.exists():
                    try:
                        self._lock_file_path.unlink()
                        self.logger.debug("✓ Lock file cleaned up")
                    except Exception as e:
                        self.logger.warning(f"⚠️  Could not clean up lock file: {e}")
            except Exception as e:
                self.logger.warning(f"⚠️  Error releasing lock: {e}")

    def run_cycle(self) -> OrchestratorResult:
        """
        Run the complete UAT testing cycle

        Feature #267: Implements file-based locking for double-start prevention
        Feature #269: Implements in-memory double-click protection

        Locking Strategy:
        1. File-based lock (fcntl): Prevents concurrent cycles across processes
        2. In-memory flag: Prevents double-clicks within same process

        Returns:
            OrchestratorResult with complete cycle results

        Raises:
            OrchestratorError: If another cycle is already running
        """
        # Feature #267: Try to acquire file-based lock FIRST
        # This prevents concurrent cycles across different processes
        lock_acquired = self._acquire_cycle_lock()
        if not lock_acquired:
            # Lock is held by another process
            error_msg = (
                "Another UAT cycle is already running. "
                "Cannot start multiple cycles simultaneously. "
                "Please wait for the current cycle to complete."
            )
            self.logger.error(f"❌ {error_msg}")
            raise OrchestratorError(error_msg)

        # Feature #269: Check in-memory flag (double-click protection)
        # This catches double-clicks within the same process
        if self._is_cycle_running:
            self.logger.warning(
                f"⚠️ Cycle already running (ID: {self._current_cycle_id}). "
                "Ignoring duplicate submission. This prevents double-execution when "
                "user double-clicks the submit button."
            )

            # Release the lock since we're not actually running
            self._release_cycle_lock()

            # Return error result indicating duplicate submission
            return OrchestratorResult(
                success=False,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=0.0,
                errors=["Cycle already in progress - duplicate submission ignored"]
            )

        # Set running flag
        self._is_cycle_running = True
        self._current_cycle_id = f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        self.logger.info("=" * 70)
        self.logger.info("STARTING UAT TESTING CYCLE")
        self.logger.info(f"Cycle ID: {self._current_cycle_id}")
        self.logger.info("=" * 70)

        start_time = datetime.now()
        self.result = OrchestratorResult(
            success=False,
            start_time=start_time,
            end_time=start_time,
            duration_seconds=0.0
        )

        try:
            # Stage 0: Validate prerequisites (Feature #101)
            self.logger.info("\n[0/8] Validating prerequisites...")
            validation_result = self._validate_prerequisites()
            self.logger.info(f"✓ Prerequisites validated: {validation_result.passed_checks}/{validation_result.total_checks} checks passed")

            # Initialize state
            self.logger.info("\n[1/8] Initializing execution state...")
            self._initialize_state()

            # Stage 1: Parse spec
            self.logger.info("\n[2/7] Parsing spec file...")
            spec = self._parse_spec()
            if spec:
                self.result.spec_parsed = True
                self.logger.info(f"✓ Spec parsed: {self.config.spec_path}")
            else:
                raise OrchestratorError("Failed to parse spec file")

            # Stage 2: Extract journeys
            self.logger.info("\n[2/7] Extracting journeys from spec...")
            journeys = self._extract_journeys(spec)
            if journeys:
                self.result.journeys_extracted = True
                self.result.total_journeys = len(journeys)
                self.result.total_scenarios = sum(len(j.scenarios) for j in journeys)
                self.logger.info(f"✓ Extracted {len(journeys)} journeys with {self.result.total_scenarios} scenarios")
            else:
                raise OrchestratorError("No journeys extracted from spec")

            # Stage 2.5: Create Kanban cards early (Feature #98)
            self.logger.info("\n[3.5/7] Creating Kanban cards early...")
            self._create_kanban_cards_early(journeys)

            # Stage 3: Generate tests
            self.logger.info("\n[3/8] Generating tests from journeys...")
            generated_tests = self._generate_tests(journeys)
            if generated_tests:
                self.result.tests_generated = True
                self.result.total_tests = len(generated_tests)
                self.logger.info(f"✓ Generated {len(generated_tests)} tests")
            else:
                raise OrchestratorError("No tests generated")

            # Stage 4: Execute tests
            self.logger.info("\n[4/8] Executing tests...")
            test_results = self._execute_tests()
            if test_results:
                self.result.tests_executed = True
                # Use summary data directly
                self.result.passed_tests = test_results.passed_tests
                self.result.failed_tests = test_results.failed_tests
                self.result.pass_rate = test_results.pass_rate
                self.logger.info(f"✓ Tests executed: {test_results.passed_tests}/{test_results.total_tests} passed ({test_results.pass_rate:.1f}%)")

                # Feature #231: Success notification for test execution
                if test_results.failed_tests == 0:
                    self.event_manager.broadcast_success(
                        action="Tests Executed",
                        message=f"All {test_results.total_tests} tests passed successfully",
                        entity_type="test_cycle",
                        metadata={
                            "total_tests": test_results.total_tests,
                            "passed_tests": test_results.passed_tests,
                            "duration_ms": test_results.duration_ms
                        }
                    )
                elif test_results.passed_tests > 0:
                    self.event_manager.broadcast_success(
                        action="Tests Executed",
                        message=f"{test_results.passed_tests}/{test_results.total_tests} tests passed",
                        entity_type="test_cycle",
                        metadata={
                            "total_tests": test_results.total_tests,
                            "passed_tests": test_results.passed_tests,
                            "failed_tests": test_results.failed_tests,
                            "pass_rate": f"{test_results.pass_rate:.1f}%"
                        }
                    )
            else:
                raise OrchestratorError("Test execution failed")

            # Stage 5: Process results
            self.logger.info("\n[5/8] Processing test results...")
            processed_results = self._process_results(self._raw_test_results)
            if processed_results:
                self.result.results_processed = True
                self.logger.info(f"✓ Results processed: action={processed_results.action}")
            else:
                raise OrchestratorError("Result processing failed")

            # Stage 6: Update Kanban
            self.logger.info("\n[6/8] Updating Kanban board...")
            kanban_updated = self._update_kanban(journeys, processed_results)
            if kanban_updated:
                self.result.kanban_updated = True
                self.logger.info(f"✓ Kanban updated: {len(self.result.journey_cards_created)} journeys, {len(self.result.scenario_cards_created)} scenarios, {len(self.result.bug_cards_created)} bugs")

                # Feature #231: Success notification for Kanban update
                total_cards = (
                    len(self.result.journey_cards_created) +
                    len(self.result.scenario_cards_created) +
                    len(self.result.bug_cards_created)
                )
                self.event_manager.broadcast_success(
                    action="Kanban Updated",
                    message=f"{total_cards} cards created/updated successfully",
                    entity_type="kanban",
                    metadata={
                        "journey_cards": len(self.result.journey_cards_created),
                        "scenario_cards": len(self.result.scenario_cards_created),
                        "bug_cards": len(self.result.bug_cards_created)
                    }
                )
            else:
                self.logger.warning("Kanban update skipped or failed")

            # Mark cycle as successful
            self.result.success = all([
                self.result.spec_parsed,
                self.result.journeys_extracted,
                self.result.tests_generated,
                self.result.tests_executed,
                self.result.results_processed,
                # kanban_updated is optional (can be skipped if no API credentials)
            ])

            # Save final state
            self._save_final_state()

        except Exception as e:
            self.logger.error(f"UAT cycle failed: {e}", exc_info=True)
            self.result.errors.append(str(e))
            self.result.success = False

        finally:
            # Feature #269: Always clear running flag, even if exception occurs
            # This ensures button is re-enabled after cycle completes or fails
            if self._is_cycle_running:
                self.logger.info(f"Clearing running flag for cycle: {self._current_cycle_id}")
                self._is_cycle_running = False
                self._current_cycle_id = None

        # Finalize
        end_time = datetime.now()
        self.result.end_time = end_time
        self.result.duration_seconds = (end_time - start_time).total_seconds()

        self.logger.info("\n" + "=" * 70)
        self.logger.info("UAT TESTING CYCLE COMPLETE")
        self.logger.info("=" * 70)
        self.logger.info(f"Duration: {self.result.duration_seconds:.2f} seconds")
        self.logger.info(f"Success: {self.result.success}")
        self.logger.info(f"Tests: {self.result.passed_tests}/{self.result.total_tests} passed ({self.result.pass_rate:.1f}%)")
        self.logger.info(f"Journey Cards: {len(self.result.journey_cards_created)}")
        self.logger.info(f"Scenario Cards: {len(self.result.scenario_cards_created)}")
        self.logger.info(f"Bug Cards: {len(self.result.bug_cards_created)}")

        if self.result.errors:
            self.logger.error(f"Errors: {len(self.result.errors)}")
            for error in self.result.errors:
                self.logger.error(f"  - {error}")

        # Notify Mission Control of completion
        # Feature #99: Orchestrator notifies Mission Control on completion
        self.logger.info("\n[NOTIFY] Sending Mission Control notification...")
        notification_sent = self._notify_mission_control()
        if notification_sent:
            self.logger.info("✓ Mission Control notified")
        else:
            self.logger.info("  Mission Control notification skipped (MCP not available or failed)")

        # Feature #231: Success notification for cycle completion
        if self.result.success:
            self.event_manager.broadcast_success(
                action="UAT Cycle Completed",
                message=f"Cycle completed successfully: {self.result.passed_tests}/{self.result.total_tests} tests passed",
                entity_type="uat_cycle",
                metadata={
                    "duration_seconds": self.result.duration_seconds,
                    "total_tests": self.result.total_tests,
                    "passed_tests": self.result.passed_tests,
                    "pass_rate": f"{self.result.pass_rate:.1f}%",
                    "journey_cards": len(self.result.journey_cards_created),
                    "scenario_cards": len(self.result.scenario_cards_created)
                }
            )

        return self.result

    # ========================================================================
    # Feature #269: Double-Click Protection Helper Methods
    # ========================================================================

    def is_cycle_running(self) -> bool:
        """
        Check if a UAT cycle is currently running

        Feature #269: This method should be used by UI components to determine
        if the submit button should be disabled.

        Returns:
            True if a cycle is running, False otherwise
        """
        return self._is_cycle_running

    def get_current_cycle_id(self) -> Optional[str]:
        """
        Get the ID of the currently running cycle

        Feature #269: Returns the cycle ID if running, None otherwise

        Returns:
            Current cycle ID or None
        """
        return self._current_cycle_id

    def _validate_prerequisites(self) -> ValidationResult:
        """
        Validate all prerequisites before starting UAT cycle

        Returns:
            ValidationResult with all check results

        Raises:
            OrchestratorError: If any critical checks fail
        """
        # Gather components
        components = {
            "journey_extractor": self.journey_extractor,
            "test_generator": self.test_generator,
            "test_executor": self.test_executor,
            "result_processor": self.result_processor,
        }

        # Kanban config (optional)
        kanban_config = None
        if self.config.kanban_api_url and self.config.kanban_api_token:
            kanban_config = {
                "api_url": self.config.kanban_api_url,
                "api_token": self.config.kanban_api_token
            }

        # Run validation
        result = self.prerequisite_validator.validate_all(
            components=components,
            kanban_config=kanban_config
        )

        return result

    def _initialize_state(self):
        """Initialize execution state"""
        self.state = self.state_manager.initialize_execution(
            test_directory=self.config.test_directory,
            base_url=self.config.base_url,
            output_directory=self.config.output_directory
        )
        self.logger.info(f"✓ Execution ID: {self.state.execution_id}")

    def _parse_spec(self) -> Optional[Any]:
        """Parse spec.yaml file"""
        try:
            spec_path = Path(self.config.spec_path)
            if not spec_path.exists():
                raise OrchestratorError(f"Spec file not found: {self.config.spec_path}")

            spec = self.journey_extractor.load_spec(str(spec_path))
            return spec
        except Exception as e:
            self.logger.error(f"Failed to parse spec: {e}")
            self.result.errors.append(f"Spec parsing failed: {e}")
            return None

    def _extract_journeys(self, spec: Dict[str, Any]) -> List[Journey]:
        """Extract journeys from parsed spec"""
        try:
            journeys = self.journey_extractor.detect_patterns(spec)
            return journeys
        except Exception as e:
            self.logger.error(f"Failed to extract journeys: {e}")
            self.result.errors.append(f"Journey extraction failed: {e}")
            return []

    def _create_kanban_cards_early(self, journeys: List[Journey]):
        """
        Create Kanban cards early after journey extraction (Feature #98)

        This creates journey and scenario cards immediately after extraction,
        before test execution begins. This allows real-time tracking.
        """
        if not self.kanban_integrator:
            self.logger.info("Kanban integrator not configured, skipping early card creation")
            return

        try:
            # Create journey cards
            journey_cards = self.kanban_integrator.create_journey_cards(journeys)
            for card in journey_cards:
                self.result.journey_cards_created.append(card)
            self.logger.info(f"✓ Created {len(journey_cards)} journey cards early")

            # Create scenario cards
            scenario_cards = self.kanban_integrator.create_scenario_cards(journeys)
            for card in scenario_cards:
                self.result.scenario_cards_created.append(card)
            self.logger.info(f"✓ Created {len(scenario_cards)} scenario cards early")

        except Exception as e:
            self.logger.warning(f"Failed to create Kanban cards early: {e}")
            # Don't fail the cycle, just log the warning

    def _generate_tests(self, journeys: List[Journey]) -> List[GeneratedTest]:
        """Generate tests from journeys"""
        try:
            # Load journeys into test generator
            self.test_generator.load_journeys(journeys)

            # Generate tests for all journeys
            all_tests = self.test_generator.generate_tests()

            return all_tests
        except Exception as e:
            self.logger.error(f"Failed to generate tests: {e}")
            self.result.errors.append(f"Test generation failed: {e}")
            return []

    def _execute_tests(self) -> Optional[ExecutionSummary]:
        """Execute generated tests"""
        try:
            test_results: List[TestResult] = self.test_executor.run_tests(
                test_pattern=self.config.test_directory
            )

            # Store raw test results for later processing
            self._raw_test_results = test_results

            # Feature #186: Track execution times with PerformanceDetector
            if self.performance_detector and test_results:
                self.logger.info("Tracking test execution times...")
                metrics = self.performance_detector.track_execution_times(
                    results=test_results,
                    run_id=self.state.execution_id
                )

                # Log performance metrics
                for metric in metrics:
                    self.logger.debug(
                        f"  {metric.test_name}: {metric.avg_duration_ms:.2f}ms "
                        f"(min: {metric.min_duration_ms:.2f}ms, "
                        f"max: {metric.max_duration_ms:.2f}ms)"
                    )

                # Generate and log summary
                summary = self.performance_detector.generate_summary(test_results)
                self.logger.info(
                    f"Performance Summary: "
                    f"{summary.total_tests} tests, "
                    f"avg {summary.avg_duration_ms:.2f}ms, "
                    f"{summary.fast_tests_count} fast, "
                    f"{summary.medium_tests_count} medium, "
                    f"{summary.slow_tests_count} slow"
                )

                # Check for regressions
                regressions = self.performance_detector.detect_regressions()
                if regressions:
                    self.logger.warning(
                        f"Detected {len(regressions)} performance regression(s)"
                    )
                    for reg in regressions[:5]:  # Log top 5
                        self.logger.warning(
                            f"  REGRESSION: {reg.test_name} "
                            f"({reg.recent_avg_ms:.2f}ms vs {reg.baseline_avg_ms:.2f}ms baseline)"
                        )

            # Convert List[TestResult] to ExecutionSummary
            total_tests = len(test_results)
            passed_tests = sum(1 for r in test_results if r.passed)
            failed_tests = sum(1 for r in test_results if not r.passed)
            skipped_tests = 0  # TestResult doesn't have a skipped field
            pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0

            summary = ExecutionSummary(
                total_tests=total_tests,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
                pass_rate=pass_rate
            )
            return summary
        except Exception as e:
            self.logger.error(f"Failed to execute tests: {e}")
            self.result.errors.append(f"Test execution failed: {e}")
            return None

    def _process_results(self, test_results: List[TestResult]) -> Optional[ProcessedResult]:
        """Process test results"""
        try:
            # Process results using the provided test_results
            processed = self.result_processor.process_results(test_results)

            return processed
        except Exception as e:
            self.logger.error(f"Failed to process results: {e}")
            self.result.errors.append(f"Result processing failed: {e}")
            return None

    def _update_kanban(
        self,
        journeys: List[Journey],
        processed_results: Optional[ProcessedResult]
    ) -> bool:
        """
        Update Kanban board with final statuses (Feature #98)

        Cards were already created early in _create_kanban_cards_early().
        This method updates their statuses based on test results.
        """
        if not self.kanban_integrator:
            self.logger.info("Kanban integrator not configured, skipping...")
            return False

        try:
            # Update card statuses based on test results
            from uat_gateway.kanban_integrator.kanban_integrator import CardStatus

            # Determine overall status based on test results
            all_passed = (self.result.failed_tests == 0)
            some_passed = (self.result.passed_tests > 0)

            # Update journey card statuses
            for card in self.result.journey_cards_created:
                if all_passed:
                    # All tests passed -> journey is done
                    self.kanban_integrator.update_card_status(card.card_id, CardStatus.DONE)
                    self.logger.debug(f"Updated {card.card_id} to DONE")
                elif some_passed:
                    # Some tests passed -> needs review
                    self.kanban_integrator.update_card_status(card.card_id, CardStatus.IN_REVIEW)
                    self.logger.debug(f"Updated {card.card_id} to IN_REVIEW")
                else:
                    # All tests failed -> blocked
                    self.kanban_integrator.update_card_status(card.card_id, CardStatus.BLOCKED)
                    self.logger.debug(f"Updated {card.card_id} to BLOCKED")

            # Update scenario card statuses
            for card in self.result.scenario_cards_created:
                # For now, mark all scenarios as done
                # In a real implementation, this would be based on individual test results
                self.kanban_integrator.update_card_status(card.card_id, CardStatus.DONE)
                self.logger.debug(f"Updated {card.card_id} to DONE")

            # Create bug cards for failures (Feature #88)
            if processed_results and hasattr(processed_results, 'bugs') and processed_results.bugs:
                for bug in processed_results.bugs:
                    try:
                        bug_card = self.kanban_integrator.create_bug_cards([bug])[0]
                        if bug_card:
                            self.result.bug_cards_created.append(bug_card)
                    except Exception as e:
                        self.logger.warning(f"Failed to create bug card: {e}")

            self.logger.info(
                f"✓ Updated Kanban card statuses: "
                f"{len(self.result.journey_cards_created)} journeys, "
                f"{len(self.result.scenario_cards_created)} scenarios, "
                f"{len(self.result.bug_cards_created)} bugs"
            )

            return True
        except Exception as e:
            self.logger.error(f"Failed to update Kanban: {e}")
            self.result.errors.append(f"Kanban update failed: {e}")
            return False

    def _save_final_state(self):
        """Save final execution state"""
        try:
            # Save execution state
            self.state_manager.save_state(self.state)

            # Save execution record with test results (Feature #186)
            if self.result:
                # Serialize test results for persistence
                results_data = [r.to_dict() for r in self._raw_test_results]

                self.state_manager.save_execution_record(
                    results=self._raw_test_results,  # Feature #186: Pass actual test results
                    run_id=self.state.execution_id,
                    metadata=self.result.to_dict()
                )

                self.logger.info(
                    f"✓ Execution record saved with {len(results_data)} test results"
                )

            self.logger.info("✓ Final state saved")
        except Exception as e:
            self.logger.warning(f"Failed to save final state: {e}")

    def _notify_mission_control(self):
        """
        Notify Mission Control on UAT cycle completion

        Sends a notification with:
        - Cycle completion status
        - Test summary (total, passed, failed)
        - Pass rate percentage
        - Journey and scenario card counts
        - Duration

        Feature #99: Orchestrator notifies Mission Control on completion
        """
        try:
            # Import here to avoid hard dependency
            # This allows the orchestrator to work even if MCP is not available
            try:
                from mcp__mission_control__devlayer_send_chat import send_chat
            except ImportError:
                self.logger.warning("Mission Control MCP not available, skipping notification...")
                return False

            # Build notification message
            status_emoji = "✅" if self.result.success else "❌"
            status_text = "PASSED" if self.result.success else "FAILED"

            message = f"""
{status_emoji} **UAT Cycle {status_text}**

**Summary:**
• Tests: {self.result.passed_tests}/{self.result.total_tests} passed
• Pass Rate: {self.result.pass_rate:.1f}%
• Duration: {self.result.duration_seconds:.1f} seconds

**Artifacts Created:**
• Journey Cards: {len(self.result.journey_cards_created)}
• Scenario Cards: {len(self.result.scenario_cards_created)}
• Bug Cards: {len(self.result.bug_cards_created)}

**Details:**
• Total Journeys: {self.result.total_journeys}
• Total Scenarios: {self.result.total_scenarios}
"""

            # Add error details if any
            if self.result.errors:
                message += f"\n⚠️ **Errors ({len(self.result.errors)}):**\n"
                for error in self.result.errors[:3]:  # Show first 3 errors
                    message += f"  • {error}\n"
                if len(self.result.errors) > 3:
                    message += f"  • ... and {len(self.result.errors) - 3} more\n"

            # Send notification via MCP
            send_chat(message=message)

            self.logger.info("✓ Mission Control notification sent")
            return True

        except Exception as e:
            self.logger.warning(f"Failed to notify Mission Control: {e}")
            self.result.errors.append(f"Mission Control notification failed: {e}")
            return False

    @staticmethod
    def generate_unified_report(
        e2e_results: List[TestResult],
        visual_results: List['ComparisonResult'],
        a11y_results: List['ScanResult'],
        api_results: List['APITestResult']
    ) -> str:
        """
        Generate unified report from all tool results

        Feature #145: Tool orchestrator generates unified reports

        Args:
            e2e_results: List of E2E test results
            visual_results: List of visual comparison results
            a11y_results: List of accessibility scan results
            api_results: List of API test results

        Returns:
            Unified report string with all sections
        """
        from uat_gateway.adapters.visual.visual_adapter import ComparisonResult
        from uat_gateway.adapters.a11y.a11y_adapter import ScanResult
        from uat_gateway.adapters.api.api_adapter import APITestResult

        lines = []
        lines.append("=" * 70)
        lines.append("UNIFIED TEST REPORT")
        lines.append("=" * 70)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Executive Summary
        lines.append("EXECUTIVE SUMMARY")
        lines.append("-" * 70)
        lines.append("")

        # Calculate overall metrics
        total_e2e = len(e2e_results)
        passed_e2e = sum(1 for r in e2e_results if r.passed)
        failed_e2e = total_e2e - passed_e2e
        e2e_pass_rate = (passed_e2e / total_e2e * 100) if total_e2e > 0 else 0

        total_visual = len(visual_results)
        passed_visual = sum(1 for r in visual_results if r.passed)
        failed_visual = total_visual - passed_visual
        avg_diff = sum(r.difference_percentage for r in visual_results) / total_visual if total_visual > 0 else 0

        total_a11y = len(a11y_results)
        passed_a11y = sum(1 for r in a11y_results if r.passed)
        failed_a11y = total_a11y - passed_a11y
        avg_a11y_score = sum(r.score for r in a11y_results) / total_a11y if total_a11y > 0 else 0
        total_violations = sum(len(r.violations) for r in a11y_results)

        total_api = len(api_results)
        passed_api = sum(1 for r in api_results if r.success)
        failed_api = total_api - passed_api
        avg_response_time = sum(r.response_time_ms for r in api_results if r.response_time_ms) / total_api if total_api > 0 else 0

        lines.append(f"Total Tests Across All Tools: {total_e2e + total_visual + total_a11y + total_api}")
        lines.append(f"E2E Tests:        {passed_e2e}/{total_e2e} passed ({e2e_pass_rate:.1f}%)")
        lines.append(f"Visual Tests:     {passed_visual}/{total_visual} passed")
        lines.append(f"A11y Scans:       {passed_a11y}/{total_a11y} passed")
        lines.append(f"API Tests:        {passed_api}/{total_api} passed")
        lines.append("")
        lines.append(f"Overall Status: {'✅ PASSING' if (failed_e2e + failed_visual + failed_a11y + failed_api) == 0 else '❌ FAILURES DETECTED'}")
        lines.append("")

        # E2E Section
        lines.append("=" * 70)
        lines.append("E2E TEST RESULTS")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Total E2E Tests:  {total_e2e}")
        lines.append(f"E2E Passed:       {passed_e2e}")
        lines.append(f"E2E Failed:       {failed_e2e}")
        lines.append(f"E2E Pass Rate:    {e2e_pass_rate:.1f}%")
        lines.append("")

        if e2e_results:
            lines.append("Test Details:")
            for result in e2e_results:
                status = "✅ PASS" if result.passed else "❌ FAIL"
                lines.append(f"  {status} {result.test_name} ({result.duration_ms}ms)")
                if not result.passed and result.error_message:
                    lines.append(f"      Error: {result.error_message}")

        lines.append("")

        # Visual Section
        lines.append("=" * 70)
        lines.append("VISUAL COMPARISON RESULTS")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Total Visual Comparisons: {total_visual}")
        lines.append(f"Visual Passed:              {passed_visual}")
        lines.append(f"Visual Failed:              {failed_visual}")
        lines.append(f"Avg Difference:             {avg_diff:.2f}%")
        lines.append("")

        if visual_results:
            lines.append("Comparison Details:")
            for result in visual_results:
                status = "✅ PASS" if result.passed else "❌ FAIL"
                lines.append(f"  {status} {result.test_name} ({result.viewport})")
                lines.append(f"      Difference: {result.difference_percentage:.2f}% ({result.diff_pixels}/{result.total_pixels} pixels)")
                if result.diff_path:
                    lines.append(f"      Diff: {result.diff_path}")

        lines.append("")

        # A11y Section
        lines.append("=" * 70)
        lines.append("ACCESSIBILITY TEST RESULTS")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Total A11y Scans:    {total_a11y}")
        lines.append(f"A11y Passed:         {passed_a11y}")
        lines.append(f"A11y Failed:         {failed_a11y}")
        lines.append(f"Avg A11y Score:      {avg_a11y_score:.1f}/100")
        lines.append(f"Total Violations:    {total_violations}")
        lines.append("")

        if a11y_results:
            lines.append("Scan Details:")
            for result in a11y_results:
                status = "✅ PASS" if result.passed else "❌ FAIL"
                lines.append(f"  {status} {result.test_name} (Score: {result.score:.1f}/100)")
                lines.append(f"      URL: {result.url}")
                if result.violations:
                    lines.append(f"      Violations: {len(result.violations)}")
                    for violation in result.violations:
                        lines.append(f"        - [{violation.impact}] {violation.description}")

        lines.append("")

        # API Section
        lines.append("=" * 70)
        lines.append("API TEST RESULTS")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Total API Tests:     {total_api}")
        lines.append(f"API Passed:          {passed_api}")
        lines.append(f"API Failed:          {failed_api}")
        lines.append(f"Avg Response Time:   {avg_response_time:.1f}ms")
        lines.append("")

        if api_results:
            lines.append("Endpoint Details:")
            for result in api_results:
                status = "✅ PASS" if result.success else "❌ FAIL"
                lines.append(f"  {status} {result.endpoint.method} {result.endpoint.path}")
                if result.status_code:
                    lines.append(f"      Status: {result.status_code}")
                if result.response_time_ms:
                    lines.append(f"      Response Time: {result.response_time_ms:.1f}ms")
                if result.error:
                    lines.append(f"      Error: {result.error}")

        lines.append("")

        # Footer
        lines.append("=" * 70)
        lines.append("END OF UNIFIED REPORT")
        lines.append("=" * 70)

        return "\n".join(lines)
