"""
Smart Test Selector - Prioritize and optimize test execution order

This module is responsible for:
- Calculating test priority scores based on multiple factors
- Selecting critical tests to run first
- Optimizing test execution order for faster feedback
- Grouping tests by priority tiers (critical, high, medium, low)
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import re
from collections import defaultdict
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import TestSelectionError, handle_errors
from custom.uat_gateway.test_executor.test_executor import TestResult


# ============================================================================
# Data Models
# ============================================================================

class PriorityTier(Enum):
    """Priority tiers for test categorization"""
    CRITICAL = "critical"  # Tests that MUST pass (core functionality)
    HIGH = "high"  # Important tests (frequently used features)
    MEDIUM = "medium"  # Standard tests (normal features)
    LOW = "low"  # Optional tests (edge cases, nice-to-haves)


class DependencyType(Enum):
    """Types of test dependencies for parallelization optimization"""
    ISOLATED = "isolated"  # Test doesn't share state, can run in parallel with any other isolated test
    SHARED_STATE = "shared_state"  # Test modifies shared state, must run sequentially with other shared state tests
    SEQUENTIAL = "sequential"  # Test must run after specific other tests (explicit dependency)
    RESOURCE_LOCK = "resource_lock"  # Test requires exclusive access to a resource


@dataclass
class TestDependency:
    """Represents a dependency relationship for a test"""
    test_name: str
    dependency_type: DependencyType
    depends_on: List[str] = field(default_factory=list)  # Names of tests this depends on
    resources: List[str] = field(default_factory=list)  # Resources this test locks (e.g., "database", "api")
    estimated_duration_ms: int = 5000  # Default 5 seconds


@dataclass
class ExecutionGroup:
    """A group of tests that can be executed in parallel"""
    tests: List[str]  # Test names in this group
    can_run_in_parallel: bool
    estimated_duration_ms: int  # Duration of this group (longest test in group)
    required_resources: Set[str] = field(default_factory=set)  # Resources needed by this group

    def __len__(self) -> int:
        return len(self.tests)


@dataclass
class SelectionResult:
    """Result of smart test selection with parallelization optimization"""
    selected_tests: List[str]  # Ordered list of test names
    execution_groups: List[ExecutionGroup]  # Groups that can run in parallel
    dependencies: List[TestDependency]  # Dependency information
    total_estimated_duration_ms: int  # Total estimated duration with parallelization
    parallelization_efficiency: float  # 0-1, higher = better parallelization
    max_workers_used: int  # Maximum workers that can be utilized


@dataclass
class TestMetadata:
    """Metadata about a test for prioritization"""
    test_name: str
    file_path: Optional[str] = None
    journey_id: Optional[str] = None
    scenario_type: Optional[str] = None  # 'happy_path' or 'error_path'
    tags: List[str] = field(default_factory=list)
    duration_ms: Optional[int] = None  # Average execution time
    last_run: Optional[datetime] = None
    pass_rate: Optional[float] = None  # Historical pass rate (0-100)
    failure_count: int = 0  # Number of recent failures
    flakiness_score: float = 0.0  # 0-100, higher = more flaky

    # Priority factors (0-10 scale, higher = more important)
    business_criticality: int = 5  # How critical is this feature?
    user_impact: int = 5  # How many users does this affect?
    change_frequency: int = 5  # How often does this code change?

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "file_path": self.file_path,
            "journey_id": self.journey_id,
            "scenario_type": self.scenario_type,
            "tags": self.tags,
            "duration_ms": self.duration_ms,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "pass_rate": self.pass_rate,
            "failure_count": self.failure_count,
            "flakiness_score": round(self.flakiness_score, 2),
            "business_criticality": self.business_criticality,
            "user_impact": self.user_impact,
            "change_frequency": self.change_frequency
        }


@dataclass
class TestPriority:
    """Calculated priority for a test"""
    test_name: str
    priority_score: float  # 0-100, higher = should run first
    priority_tier: PriorityTier
    factors: Dict[str, float] = field(default_factory=dict)  # Individual factor scores
    estimated_duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "priority_score": round(self.priority_score, 2),
            "priority_tier": self.priority_tier.value,
            "factors": self.factors,
            "estimated_duration_ms": self.estimated_duration_ms
        }


@dataclass
class TestSelection:
    """Result of test selection operation"""
    selected_tests: List[str]  # Ordered list of test names
    total_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    estimated_duration_ms: int
    selection_reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "selected_tests": self.selected_tests,
            "total_count": self.total_count,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "estimated_duration_ms": self.estimated_duration_ms,
            "estimated_duration_seconds": round(self.estimated_duration_ms / 1000, 2),
            "selection_reason": self.selection_reason
        }


# ============================================================================
# Smart Test Selector
# ============================================================================

class SmartTestSelector:
    """
    Smart test selector for prioritized test execution

    Feature #208 implementation:
    - Calculates test priority scores based on multiple factors
    - Selects critical tests to run first
    - Optimizes execution order for faster feedback
    - Groups tests by priority tiers

    Priority Factors:
    1. Business Criticality (0-10): Core functionality vs optional features
    2. User Impact (0-10): Number of users affected
    3. Change Frequency (0-10): How often code changes
    4. Recent Failures (0-10): Tests that failed recently
    5. Flakiness Score (0-10 neg): Penalize flaky tests
    6. Duration (0-10 neg): Prefer faster tests for quick feedback
    """

    # Priority tier thresholds
    CRITICAL_THRESHOLD = 80.0
    HIGH_THRESHOLD = 60.0
    MEDIUM_THRESHOLD = 40.0

    def __init__(self):
        self.logger = get_logger("smart_test_selector")
        self._test_metadata: Dict[str, TestMetadata] = {}
        self._historical_results: List[TestResult] = []

    @handle_errors(component="smart_test_selector", reraise=True)
    def load_test_metadata(self, metadata: List[TestMetadata]) -> None:
        """
        Load test metadata for prioritization

        Args:
            metadata: List of TestMetadata objects

        Raises:
            TestSelectionError: If metadata cannot be loaded
        """
        if not metadata:
            raise TestSelectionError(
                "No test metadata provided",
                component="smart_test_selector",
                context={"metadata_count": len(metadata)}
            )

        self._test_metadata = {m.test_name: m for m in metadata}
        self.logger.info(f"Loaded metadata for {len(metadata)} tests")

    @handle_errors(component="smart_test_selector", reraise=False)
    def load_historical_results(self, results: List[TestResult]) -> None:
        """
        Load historical test results for calculating priority factors

        Args:
            results: List of TestResult objects from previous runs
        """
        self._historical_results = results
        self.logger.info(f"Loaded {len(results)} historical results")

        # Update metadata with historical data
        self._update_metadata_from_history()

    def _update_metadata_from_history(self) -> None:
        """Update test metadata with statistics from historical results"""
        # Group results by test name
        results_by_test: Dict[str, List[TestResult]] = defaultdict(list)
        for result in self._historical_results:
            results_by_test[result.test_name].append(result)

        # Update metadata for each test
        for test_name, results in results_by_test.items():
            if test_name not in self._test_metadata:
                # Create metadata if it doesn't exist
                self._test_metadata[test_name] = TestMetadata(test_name=test_name)

            metadata = self._test_metadata[test_name]

            # Calculate pass rate
            total_runs = len(results)
            passed_runs = sum(1 for r in results if r.passed)
            metadata.pass_rate = (passed_runs / total_runs * 100) if total_runs > 0 else 0

            # Count recent failures (last 10 runs)
            recent_results = results[-10:]
            metadata.failure_count = sum(1 for r in recent_results if not r.passed)

            # Calculate average duration
            durations = [r.duration_ms for r in results if r.duration_ms > 0]
            if durations:
                metadata.duration_ms = int(sum(durations) / len(durations))

            # Last run time
            if results:
                metadata.last_run = max(
                    r.duration_ms for r in results  # Use duration_ms as proxy for timestamp
                    if hasattr(r, 'timestamp')
                ) or datetime.now()

            # Calculate flakiness score
            # Flaky = mix of passes and failures in recent runs
            if total_runs >= 3:
                passed_ratio = passed_runs / total_runs
                # Most flaky when pass rate is around 50%
                metadata.flakiness_score = 100 * (1 - abs(passed_ratio - 0.5) * 2)

    @handle_errors(component="smart_test_selector", reraise=True)
    def calculate_priority(self, test_name: str) -> TestPriority:
        """
        Calculate priority score for a single test

        Priority Score Calculation (0-100):
        - Business Criticality (0-10) * 1.5 weight
        - User Impact (0-10) * 1.2 weight
        - Change Frequency (0-10) * 1.0 weight
        - Recent Failures (0-10) * 1.3 weight
        - Flakiness Penalty (0-10) * -0.5 weight (penalty)
        - Duration Penalty (0-10) * -0.3 weight (penalty for slow tests)

        Args:
            test_name: Name of the test

        Returns:
            TestPriority object with score and tier

        Raises:
            TestSelectionError: If test metadata not found
        """
        if test_name not in self._test_metadata:
            # Create default metadata if not found
            self.logger.warning(f"No metadata found for {test_name}, using defaults")
            self._test_metadata[test_name] = TestMetadata(test_name=test_name)

        metadata = self._test_metadata[test_name]

        # Calculate individual factor scores
        factors = {}

        # 1. Business Criticality (weight: 1.5)
        criticality_score = metadata.business_criticality * 1.5
        factors["business_criticality"] = criticality_score

        # 2. User Impact (weight: 1.2)
        user_impact_score = metadata.user_impact * 1.2
        factors["user_impact"] = user_impact_score

        # 3. Change Frequency (weight: 1.0)
        change_frequency_score = metadata.change_frequency * 1.0
        factors["change_frequency"] = change_frequency_score

        # 4. Recent Failures (weight: 1.3)
        failure_score = min(metadata.failure_count, 10) * 1.3
        factors["recent_failures"] = failure_score

        # 5. Flakiness Penalty (weight: -0.5)
        flakiness_penalty = (metadata.flakiness_score / 10) * -0.5
        factors["flakiness_penalty"] = flakiness_penalty

        # 6. Duration Penalty (weight: -0.3)
        # Prefer faster tests for quick feedback
        if metadata.duration_ms:
            # Map duration to 0-10 scale (0ms = 0, 10000ms+ = 10)
            duration_factor = min(metadata.duration_ms / 1000, 10)
            duration_penalty = duration_factor * -0.3
            factors["duration_penalty"] = duration_penalty
        else:
            factors["duration_penalty"] = 0.0

        # Calculate total priority score
        priority_score = sum(factors.values())

        # Normalize to 0-100 range
        # Max possible: (10*1.5) + (10*1.2) + (10*1.0) + (10*1.3) = 50
        # Min possible: 0 + 0 + 0 + 0 + (-5) + (-3) = -8
        # We'll scale and clamp to 0-100
        normalized_score = max(0, min(100, (priority_score + 8) * 2))

        # Determine priority tier
        if normalized_score >= self.CRITICAL_THRESHOLD:
            tier = PriorityTier.CRITICAL
        elif normalized_score >= self.HIGH_THRESHOLD:
            tier = PriorityTier.HIGH
        elif normalized_score >= self.MEDIUM_THRESHOLD:
            tier = PriorityTier.MEDIUM
        else:
            tier = PriorityTier.LOW

        return TestPriority(
            test_name=test_name,
            priority_score=normalized_score,
            priority_tier=tier,
            factors=factors,
            estimated_duration_ms=metadata.duration_ms or 0
        )

    @handle_errors(component="smart_test_selector", reraise=True)
    def select_critical_tests(
        self,
        max_tests: Optional[int] = None,
        max_duration_ms: Optional[int] = None
    ) -> TestSelection:
        """
        Select critical tests to run first

        Feature #208: Smart selector prioritizes critical tests

        Args:
            max_tests: Maximum number of tests to select (optional)
            max_duration_ms: Maximum total duration in milliseconds (optional)

        Returns:
            TestSelection with ordered test names

        Raises:
            TestSelectionError: If no tests are available
        """
        if not self._test_metadata:
            raise TestSelectionError(
                "No test metadata loaded. Call load_test_metadata() first.",
                component="smart_test_selector"
            )

        self.logger.info("Selecting critical tests...")

        # Calculate priorities for all tests
        priorities = []
        for test_name in self._test_metadata.keys():
            priority = self.calculate_priority(test_name)
            priorities.append(priority)

        # Filter critical tier tests
        critical_tests = [p for p in priorities if p.priority_tier == PriorityTier.CRITICAL]

        # If no critical tests, include high priority tests
        if not critical_tests:
            self.logger.warning("No critical tests found, including high priority tests")
            critical_tests = [p for p in priorities if p.priority_tier == PriorityTier.HIGH]

        # Sort by priority score (descending)
        critical_tests.sort(key=lambda p: p.priority_score, reverse=True)

        # Apply constraints
        selected = self._apply_constraints(
            critical_tests,
            max_tests=max_tests,
            max_duration_ms=max_duration_ms
        )

        # Count tests by tier
        tier_counts = self._count_tiers(selected)

        total_duration = sum(p.estimated_duration_ms for p in selected)

        selection = TestSelection(
            selected_tests=[p.test_name for p in selected],
            total_count=len(selected),
            critical_count=tier_counts[PriorityTier.CRITICAL],
            high_count=tier_counts[PriorityTier.HIGH],
            medium_count=tier_counts[PriorityTier.MEDIUM],
            low_count=tier_counts[PriorityTier.LOW],
            estimated_duration_ms=total_duration,
            selection_reason="Critical tests for fastest feedback"
        )

        self.logger.info(
            f"Selected {len(selected)} critical tests "
            f"({tier_counts[PriorityTier.CRITICAL]} critical, "
            f"{tier_counts[PriorityTier.HIGH]} high)"
        )

        return selection

    def select_all_tests(
        self,
        optimize_order: bool = True,
        max_tests: Optional[int] = None,
        max_duration_ms: Optional[int] = None
    ) -> TestSelection:
        """
        Select all tests with optional optimization

        Args:
            optimize_order: If True, sort by priority score
            max_tests: Maximum number of tests to select (optional)
            max_duration_ms: Maximum total duration in milliseconds (optional)

        Returns:
            TestSelection with ordered test names
        """
        if not self._test_metadata:
            raise TestSelectionError(
                "No test metadata loaded. Call load_test_metadata() first.",
                component="smart_test_selector"
            )

        self.logger.info("Selecting all tests...")

        # Calculate priorities for all tests
        priorities = []
        for test_name in self._test_metadata.keys():
            priority = self.calculate_priority(test_name)
            priorities.append(priority)

        # Sort by priority if optimization requested
        if optimize_order:
            priorities.sort(key=lambda p: p.priority_score, reverse=True)
            selection_reason = "All tests optimized by priority"
        else:
            selection_reason = "All tests in original order"

        # Apply constraints
        selected = self._apply_constraints(
            priorities,
            max_tests=max_tests,
            max_duration_ms=max_duration_ms
        )

        # Count tests by tier
        tier_counts = self._count_tiers(selected)

        total_duration = sum(p.estimated_duration_ms for p in selected)

        selection = TestSelection(
            selected_tests=[p.test_name for p in selected],
            total_count=len(selected),
            critical_count=tier_counts[PriorityTier.CRITICAL],
            high_count=tier_counts[PriorityTier.HIGH],
            medium_count=tier_counts[PriorityTier.MEDIUM],
            low_count=tier_counts[PriorityTier.LOW],
            estimated_duration_ms=total_duration,
            selection_reason=selection_reason
        )

        self.logger.info(f"Selected {len(selected)} tests (optimized: {optimize_order})")

        return selection

    def select_tests_by_tag(
        self,
        tag: str,
        max_tests: Optional[int] = None,
        max_duration_ms: Optional[int] = None
    ) -> TestSelection:
        """
        Select tests with a specific tag

        Args:
            tag: Tag to filter by (e.g., 'smoke', 'regression', 'api')
            max_tests: Maximum number of tests to select (optional)
            max_duration_ms: Maximum total duration in milliseconds (optional)

        Returns:
            TestSelection with ordered test names
        """
        if not self._test_metadata:
            raise TestSelectionError(
                "No test metadata loaded. Call load_test_metadata() first.",
                component="smart_test_selector"
            )

        self.logger.info(f"Selecting tests with tag: {tag}")

        # Find tests with the tag
        matching_tests = [
            (test_name, metadata)
            for test_name, metadata in self._test_metadata.items()
            if tag in metadata.tags
        ]

        if not matching_tests:
            raise TestSelectionError(
                f"No tests found with tag: {tag}",
                component="smart_test_selector",
                context={"tag": tag, "available_tags": self._get_all_tags()}
            )

        # Calculate priorities for matching tests
        priorities = []
        for test_name, _ in matching_tests:
            priority = self.calculate_priority(test_name)
            priorities.append(priority)

        # Sort by priority score (descending)
        priorities.sort(key=lambda p: p.priority_score, reverse=True)

        # Apply constraints
        selected = self._apply_constraints(
            priorities,
            max_tests=max_tests,
            max_duration_ms=max_duration_ms
        )

        # Count tests by tier
        tier_counts = self._count_tiers(selected)

        total_duration = sum(p.estimated_duration_ms for p in selected)

        selection = TestSelection(
            selected_tests=[p.test_name for p in selected],
            total_count=len(selected),
            critical_count=tier_counts[PriorityTier.CRITICAL],
            high_count=tier_counts[PriorityTier.HIGH],
            medium_count=tier_counts[PriorityTier.MEDIUM],
            low_count=tier_counts[PriorityTier.LOW],
            estimated_duration_ms=total_duration,
            selection_reason=f"Tests tagged with '{tag}'"
        )

        self.logger.info(f"Selected {len(selected)} tests with tag '{tag}'")

        return selection

    def get_priority_summary(self) -> Dict[str, Any]:
        """
        Get summary of test priorities

        Returns:
            Dictionary with priority statistics
        """
        if not self._test_metadata:
            return {
                "total_tests": 0,
                "tiers": {},
                "message": "No test metadata loaded"
            }

        # Calculate priorities for all tests
        priorities = []
        for test_name in self._test_metadata.keys():
            priority = self.calculate_priority(test_name)
            priorities.append(priority)

        # Count by tier
        tier_counts = self._count_tiers(priorities)

        # Calculate statistics
        scores = [p.priority_score for p in priorities]
        avg_score = sum(scores) / len(scores) if scores else 0

        return {
            "total_tests": len(priorities),
            "average_priority_score": round(avg_score, 2),
            "tiers": {
                "critical": tier_counts[PriorityTier.CRITICAL],
                "high": tier_counts[PriorityTier.HIGH],
                "medium": tier_counts[PriorityTier.MEDIUM],
                "low": tier_counts[PriorityTier.LOW]
            },
            "highest_priority_test": max(priorities, key=lambda p: p.priority_score).test_name if priorities else None,
            "lowest_priority_test": min(priorities, key=lambda p: p.priority_score).test_name if priorities else None
        }

    @handle_errors(component="smart_test_selector", reraise=True)
    def select_tests(
        self,
        test_names: List[str],
        max_workers: int = 3,
        optimize_priority: bool = True
    ) -> SelectionResult:
        """
        Select and optimize tests for parallel execution

        Feature #209: Smart selector optimizes parallelization

        This method:
        1. Analyzes test dependencies based on naming patterns
        2. Groups tests that can run in parallel (isolated tests)
        3. Sequences tests that have dependencies
        4. Optimizes execution order for speed

        Args:
            test_names: List of test names to select
            max_workers: Maximum parallel workers available
            optimize_priority: If True, sort by priority within groups

        Returns:
            SelectionResult with optimized execution plan

        Raises:
            TestSelectionError: If no tests provided or analysis fails
        """
        if not test_names:
            raise TestSelectionError(
                "No test names provided for selection",
                component="smart_test_selector"
            )

        self.logger.info(f"Selecting {len(test_names)} tests for parallel execution (max_workers={max_workers})")

        # Step 1: Analyze dependencies for each test
        dependencies = self._analyze_test_dependencies(test_names)

        # Step 2: Sort tests considering dependencies and priority
        sorted_tests = self._sort_tests_with_dependencies(
            test_names,
            dependencies,
            optimize_priority=optimize_priority
        )

        # Step 3: Create execution groups for parallelization
        execution_groups = self._create_execution_groups(
            sorted_tests,
            dependencies,
            max_workers
        )

        # Step 4: Calculate metrics
        total_duration = self._calculate_total_duration(execution_groups, dependencies)
        efficiency = self._calculate_parallelization_efficiency(
            sorted_tests,
            execution_groups,
            max_workers
        )

        result = SelectionResult(
            selected_tests=sorted_tests,
            execution_groups=execution_groups,
            dependencies=dependencies,
            total_estimated_duration_ms=total_duration,
            parallelization_efficiency=efficiency,
            max_workers_used=min(max_workers, max(len(g) for g in execution_groups) if execution_groups else 1)
        )

        self.logger.info(
            f"Selected {len(sorted_tests)} tests in {len(execution_groups)} groups "
            f"(efficiency: {efficiency:.1%}, duration: {total_duration / 1000:.1f}s)"
        )

        return result

    def _analyze_test_dependencies(self, test_names: List[str]) -> List[TestDependency]:
        """
        Analyze test names to determine dependencies

        Uses heuristics based on common test naming patterns:
        - create_*: Often dependencies for other tests
        - delete_*: Should run late, may depend on create
        - view_*: Usually isolated, can run in parallel
        - login/logout: Have implicit dependencies
        """
        dependencies = []

        # Identify test types
        create_tests = set()
        delete_tests = set()
        view_tests = set()
        update_tests = set()
        login_tests = set()
        logout_tests = set()
        resource_modifying_tests = set()

        for test_name in test_names:
            lower_name = test_name.lower()

            if 'create' in lower_name:
                create_tests.add(test_name)
                resource_modifying_tests.add(test_name)
            elif 'delete' in lower_name:
                delete_tests.add(test_name)
                resource_modifying_tests.add(test_name)
            elif 'update' in lower_name or 'edit' in lower_name or 'modify' in lower_name:
                update_tests.add(test_name)
                resource_modifying_tests.add(test_name)
            elif 'view' in lower_name or 'get' in lower_name or 'list' in lower_name or 'show' in lower_name:
                view_tests.add(test_name)
            elif 'login' in lower_name or 'auth' in lower_name:
                login_tests.add(test_name)
            elif 'logout' in lower_name:
                logout_tests.add(test_name)

        # Determine dependency type for each test
        for test_name in test_names:
            lower_name = test_name.lower()

            # Determine dependency type
            if test_name in view_tests:
                # View tests are usually isolated
                dep_type = DependencyType.ISOLATED
            elif test_name in login_tests or test_name in logout_tests:
                # Auth tests have sequential dependencies
                dep_type = DependencyType.SEQUENTIAL
            elif test_name in resource_modifying_tests:
                # Tests that modify state have shared state dependencies
                dep_type = DependencyType.SHARED_STATE
            else:
                # Default to isolated for unknown patterns
                dep_type = DependencyType.ISOLATED

            # Determine explicit dependencies
            depends_on = []

            if test_name in delete_tests:
                # Delete tests should run after corresponding create/update
                for create_test in create_tests:
                    if self._tests_are_related(test_name, create_test):
                        depends_on.append(create_test)
                for update_test in update_tests:
                    if self._tests_are_related(test_name, update_test):
                        depends_on.append(update_test)

            elif test_name in update_tests:
                # Update tests should run after create
                for create_test in create_tests:
                    if self._tests_are_related(test_name, create_test):
                        depends_on.append(create_test)

            elif test_name in logout_tests:
                # Logout should run after login
                depends_on.extend(list(login_tests))

            elif test_name in login_tests:
                # Login tests should run early (no explicit dependencies)
                # But they might depend on create_user tests
                for create_test in create_tests:
                    if 'user' in create_test.lower():
                        depends_on.append(create_test)

            # Determine resources
            resources = []
            if 'database' in lower_name or 'db' in lower_name:
                resources.append('database')
            if 'api' in lower_name:
                resources.append('api')

            # Get estimated duration from metadata
            metadata = self._test_metadata.get(test_name)
            duration_ms = metadata.duration_ms if metadata and metadata.duration_ms else 5000

            dep = TestDependency(
                test_name=test_name,
                dependency_type=dep_type,
                depends_on=depends_on,
                resources=resources,
                estimated_duration_ms=duration_ms
            )
            dependencies.append(dep)

        return dependencies

    def _tests_are_related(self, test1: str, test2: str) -> bool:
        """
        Check if two tests are related (operate on same entity)

        Examples:
        - test_create_user and test_delete_user are related
        - test_create_product and test_view_product are related
        """
        # Extract entity from test names
        def extract_entity(test_name: str) -> str:
            """Extract the entity being tested (e.g., 'user', 'product')"""
            lower = test_name.lower()

            # Look for common patterns after action verbs
            for action in ['create_', 'delete_', 'update_', 'view_', 'get_', 'list_', 'edit_', 'modify_']:
                if action in lower:
                    parts = lower.split(action)
                    if len(parts) > 1:
                        # Get the entity name (first word after action)
                        entity = parts[1].split('_')[0]
                        return entity

            # Fallback: look for common entity keywords
            entities = ['user', 'product', 'order', 'admin', 'customer', 'item', 'account']
            for entity in entities:
                if entity in lower:
                    return entity

            return ''

        entity1 = extract_entity(test1)
        entity2 = extract_entity(test2)

        return entity1 != '' and entity1 == entity2

    def _sort_tests_with_dependencies(
        self,
        test_names: List[str],
        dependencies: List[TestDependency],
        optimize_priority: bool = True
    ) -> List[str]:
        """
        Sort tests respecting dependencies and optionally optimizing by priority

        Uses topological sort for dependencies, then priority optimization
        """
        # Create dependency map
        dep_map = {dep.test_name: dep for dep in dependencies}
        remaining = set(test_names)
        sorted_tests = []
        iteration_count = 0
        max_iterations = len(test_names) * 2  # Prevent infinite loops

        while remaining and iteration_count < max_iterations:
            iteration_count += 1

            # Find tests with no unsatisfied dependencies
            ready = []
            for test_name in list(remaining):
                # Tests with no dependencies are always ready
                if test_name not in dep_map:
                    ready.append(test_name)
                    continue

                dep = dep_map[test_name]

                # Check if all dependencies are satisfied
                deps_satisfied = all(
                    dep_test in sorted_tests
                    for dep_test in dep.depends_on
                )

                if deps_satisfied:
                    ready.append(test_name)

            if not ready:
                # Circular dependency or all remaining tests depend on each other
                # Add the highest priority remaining test to break the cycle
                if optimize_priority:
                    ready_ready = [
                        t for t in remaining
                        if all(d in sorted_tests for d in dep_map[t].depends_on)
                    ]
                    if not ready_ready:
                        # Break cycle by adding highest priority remaining test
                        priority_scores = {
                            t: self.calculate_priority(t).priority_score
                            for t in remaining
                        }
                        ready = [max(priority_scores, key=priority_scores.get)]
                    else:
                        ready = ready_ready
                else:
                    # Add first remaining test to break cycle
                    ready = [list(remaining)[0]]

            # Sort ready tests by priority if optimization is enabled
            if optimize_priority:
                priority_scores = {
                    test: self.calculate_priority(test).priority_score
                    for test in ready
                }
                ready.sort(key=lambda t: priority_scores[t], reverse=True)

            # Add ready tests to sorted list
            for test in ready:
                sorted_tests.append(test)
                remaining.remove(test)

        # Add any remaining tests (shouldn't happen, but safety net)
        sorted_tests.extend(list(remaining))

        return sorted_tests

    def _create_execution_groups(
        self,
        sorted_tests: List[str],
        dependencies: List[TestDependency],
        max_workers: int
    ) -> List[ExecutionGroup]:
        """
        Create execution groups for parallel processing

        Groups tests that can run in parallel (isolated tests)
        while respecting sequential dependencies
        """
        dep_map = {dep.test_name: dep for dep in dependencies}
        groups = []
        current_group = []
        current_group_resources = set()

        for test_name in sorted_tests:
            dep = dep_map[test_name]

            # Check if test can run in parallel with current group
            can_join_group = False

            if dep.dependency_type == DependencyType.ISOLATED:
                # Isolated tests can run in parallel
                # Check resource conflicts
                if not dep.resources or not current_group_resources.intersection(dep.resources):
                    # No resource conflicts, can add to current group
                    can_join_group = len(current_group) < max_workers
                else:
                    # Resource conflict, start new group
                    can_join_group = False

            elif dep.dependency_type == DependencyType.RESOURCE_LOCK:
                # Resource lock tests need exclusive access
                can_join_group = False

            else:
                # Sequential or shared state tests must be in their own group
                can_join_group = False

            if can_join_group and current_group:
                # Add to current group
                current_group.append(test_name)
                current_group_resources.update(dep.resources)
            else:
                # Start new group
                if current_group:
                    # Finalize current group
                    duration = max(
                        dep_map[t].estimated_duration_ms
                        for t in current_group
                    )
                    groups.append(ExecutionGroup(
                        tests=current_group,
                        can_run_in_parallel=True,
                        estimated_duration_ms=duration,
                        required_resources=current_group_resources.copy()
                    ))

                # Start new group with this test
                current_group = [test_name]
                current_group_resources = set(dep.resources)

        # Add final group
        if current_group:
            duration = max(
                dep_map[t].estimated_duration_ms
                for t in current_group
            )
            # Mark as parallel only if multiple tests
            can_parallel = len(current_group) > 1
            groups.append(ExecutionGroup(
                tests=current_group,
                can_run_in_parallel=can_parallel,
                estimated_duration_ms=duration,
                required_resources=current_group_resources.copy()
            ))

        return groups

    def _calculate_total_duration(
        self,
        execution_groups: List[ExecutionGroup],
        dependencies: List[TestDependency]
    ) -> int:
        """Calculate total estimated duration with parallelization"""
        # Sum of group durations (groups run sequentially, tests in group run in parallel)
        return sum(group.estimated_duration_ms for group in execution_groups)

    def _calculate_parallelization_efficiency(
        self,
        sorted_tests: List[str],
        execution_groups: List[ExecutionGroup],
        max_workers: int
    ) -> float:
        """
        Calculate parallelization efficiency

        Efficiency = (sequential_time / parallel_time) / max_workers

        Returns:
            Float from 0-1, higher = better parallelization
        """
        if not execution_groups:
            return 0.0

        # Sequential time = sum of all test durations
        dep_map = {dep.test_name: dep for dep in self._analyze_test_dependencies(sorted_tests)}
        sequential_time = sum(
            dep_map[test].estimated_duration_ms
            for test in sorted_tests
        )

        # Parallel time = sum of group durations
        parallel_time = sum(group.estimated_duration_ms for group in execution_groups)

        if parallel_time == 0:
            return 0.0

        # Calculate efficiency
        theoretical_best_time = sequential_time / max_workers
        efficiency = min(1.0, theoretical_best_time / parallel_time)

        return efficiency

    def get_execution_plan(self, result: SelectionResult) -> str:
        """
        Generate a human-readable execution plan

        Args:
            result: SelectionResult from select_tests()

        Returns:
            Formatted string describing the execution plan
        """
        lines = []
        lines.append("=" * 60)
        lines.append("SMART TEST SELECTION EXECUTION PLAN")
        lines.append("=" * 60)

        lines.append(f"\nTotal Tests: {len(result.selected_tests)}")
        lines.append(f"Execution Groups: {len(result.execution_groups)}")
        lines.append(f"Max Workers: {result.max_workers_used}")
        lines.append(f"Parallelization Efficiency: {result.parallelization_efficiency:.1%}")
        lines.append(f"Estimated Duration: {result.total_estimated_duration_ms / 1000:.1f}s")

        lines.append("\n" + "-" * 60)
        lines.append("DEPENDENCY ANALYSIS")
        lines.append("-" * 60)

        # Count dependency types
        dep_counts = {}
        for dep in result.dependencies:
            dep_counts[dep.dependency_type] = dep_counts.get(dep.dependency_type, 0) + 1

        for dep_type, count in dep_counts.items():
            lines.append(f"  {dep_type.value}: {count}")

        lines.append("\n" + "-" * 60)
        lines.append("EXECUTION GROUPS")
        lines.append("-" * 60)

        for i, group in enumerate(result.execution_groups, 1):
            parallel_flag = "✓ PARALLEL" if group.can_run_in_parallel else "→ SEQUENTIAL"
            lines.append(f"\nGroup {i}: {parallel_flag}")
            lines.append(f"  Tests ({len(group.tests)}): {', '.join(group.tests)}")
            lines.append(f"  Duration: {group.estimated_duration_ms / 1000:.1f}s")
            if group.required_resources:
                lines.append(f"  Resources: {', '.join(group.required_resources)}")

        lines.append("\n" + "-" * 60)
        lines.append("EXECUTION ORDER")
        lines.append("-" * 60)

        for i, test in enumerate(result.selected_tests, 1):
            dep = next((d for d in result.dependencies if d.test_name == test), None)
            if dep and dep.depends_on:
                lines.append(f"{i}. {test} (after: {', '.join(dep.depends_on)})")
            else:
                lines.append(f"{i}. {test}")

        lines.append("\n" + "=" * 60)

        return "\n".join(lines)

    def _apply_constraints(
        self,
        priorities: List[TestPriority],
        max_tests: Optional[int] = None,
        max_duration_ms: Optional[int] = None
    ) -> List[TestPriority]:
        """
        Apply constraints to selected tests

        Args:
            priorities: List of TestPriority objects
            max_tests: Maximum number of tests
            max_duration_ms: Maximum total duration

        Returns:
            Filtered list of TestPriority objects
        """
        selected = priorities

        # Apply max_tests constraint
        if max_tests and len(selected) > max_tests:
            selected = selected[:max_tests]
            self.logger.info(f"Limited to {max_tests} tests")

        # Apply max_duration_ms constraint
        if max_duration_ms:
            cumulative_duration = 0
            duration_limited = []
            for priority in selected:
                if cumulative_duration + priority.estimated_duration_ms <= max_duration_ms:
                    duration_limited.append(priority)
                    cumulative_duration += priority.estimated_duration_ms
                else:
                    break

            if len(duration_limited) < len(selected):
                self.logger.info(
                    f"Limited to {len(duration_limited)} tests due to duration constraint "
                    f"({max_duration_ms}ms)"
                )
                selected = duration_limited

        return selected

    def _count_tiers(self, priorities: List[TestPriority]) -> Dict[PriorityTier, int]:
        """Count tests by priority tier"""
        counts = {
            PriorityTier.CRITICAL: 0,
            PriorityTier.HIGH: 0,
            PriorityTier.MEDIUM: 0,
            PriorityTier.LOW: 0
        }

        for priority in priorities:
            counts[priority.priority_tier] += 1

        return counts

    def _get_all_tags(self) -> List[str]:
        """Get all unique tags from loaded metadata"""
        all_tags = set()
        for metadata in self._test_metadata.values():
            all_tags.update(metadata.tags)
        return sorted(list(all_tags))
