"""
Smart Test Selector - Optimize test parallelization and execution order

This module analyzes tests to determine dependencies and optimizes
execution order for maximum parallelization while respecting dependencies.

Feature #209 implementation
"""

import sys
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import re
from collections import defaultdict

# Add parent directory to path for imports

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import TestSelectionError, handle_errors


# ============================================================================
# Data Models
# ============================================================================

class DependencyType(Enum):
    """Types of test dependencies"""
    SHARED_STATE = "shared_state"  # Tests that modify shared application state
    SEQUENTIAL = "sequential"  # Tests that must run in specific order
    RESOURCE = "resource"  # Tests that use exclusive resources
    ISOLATED = "isolated"  # Tests with no dependencies (can run in parallel)


@dataclass
class TestDependency:
    """Represents a dependency between tests"""
    test_name: str
    dependency_type: DependencyType
    depends_on: Set[str] = field(default_factory=set)  # Tests this depends on
    blocks: Set[str] = field(default_factory=set)  # Tests blocked by this
    priority: int = 0  # Higher priority tests run first


@dataclass
class ExecutionGroup:
    """A group of tests that can run in parallel"""
    group_id: int
    tests: List[str]  # Test names in this group
    can_run_in_parallel: bool = True
    estimated_duration_ms: int = 0


@dataclass
class SelectionResult:
    """Result of test selection and optimization"""
    selected_tests: List[str]  # All tests to run
    execution_groups: List[ExecutionGroup]  # Tests grouped by parallelization
    dependencies: List[TestDependency]  # All discovered dependencies
    total_estimated_duration_ms: int = 0
    parallelization_efficiency: float = 0.0  # 0.0 to 1.0 (higher is better)

    def get_optimization_summary(self) -> str:
        """Get a summary of the optimization"""
        total_tests = len(self.selected_tests)
        parallel_groups = len([g for g in self.execution_groups if g.can_run_in_parallel])

        return (
            f"Selected {total_tests} tests\n"
            f"  - Organized into {len(self.execution_groups)} execution groups\n"
            f"  - {parallel_groups} groups can run in parallel\n"
            f"  - Parallelization efficiency: {self.parallelization_efficiency:.1%}\n"
            f"  - Estimated duration: {self.total_estimated_duration_ms}ms"
        )


# ============================================================================
# Smart Test Selector
# ============================================================================

class SmartTestSelector:
    """
    Smart test selector for optimizing parallel execution

    Analyzes tests to:
    1. Detect dependencies between tests
    2. Group independent tests for parallel execution
    3. Optimize execution order to minimize total time
    4. Respect test dependencies and ordering constraints
    """

    # Patterns that indicate shared state modifications
    SHARED_STATE_PATTERNS = [
        r'create.*user',
        r'register',
        r'login',
        r'delete.*',
        r'update.*profile',
        r'change.*password',
    ]

    # Patterns that indicate exclusive resource usage
    RESOURCE_PATTERNS = [
        r'admin',
        r'settings',
        r'config',
        r'websocket',
        r'upload',
    ]

    def __init__(self):
        self.logger = get_logger("smart_selector")
        self._dependencies: Dict[str, TestDependency] = {}
        self._test_history: Dict[str, List[float]] = defaultdict(list)  # test_name -> durations

    @handle_errors(component="smart_selector", reraise=True)
    def select_tests(
        self,
        test_names: List[str],
        test_files: Optional[Dict[str, str]] = None,
        max_workers: int = 3
    ) -> SelectionResult:
        """
        Select and optimize tests for parallel execution

        Args:
            test_names: List of test names to analyze
            test_files: Optional dict mapping test names to file content
            max_workers: Maximum number of parallel workers

        Returns:
            SelectionResult with optimized execution groups

        Raises:
            TestSelectionError: If selection fails
        """
        self.logger.info(f"Analyzing {len(test_names)} tests for optimal parallelization...")

        # Step 1: Analyze test dependencies
        dependencies = self._analyze_dependencies(test_names, test_files)

        # Step 2: Build dependency graph
        dependency_graph = self._build_dependency_graph(dependencies)

        # Step 3: Topological sort to get execution order
        execution_order = self._topological_sort(dependency_graph)

        # Step 4: Group tests for parallel execution
        execution_groups = self._group_for_parallel_execution(
            execution_order,
            dependencies,
            max_workers
        )

        # Step 5: Calculate metrics
        total_duration = self._estimate_total_duration(execution_groups, dependencies)
        efficiency = self._calculate_parallelization_efficiency(execution_groups, max_workers)

        result = SelectionResult(
            selected_tests=execution_order,
            execution_groups=execution_groups,
            dependencies=list(dependencies.values()),
            total_estimated_duration_ms=total_duration,
            parallelization_efficiency=efficiency
        )

        self.logger.info(f"Test selection complete:\n{result.get_optimization_summary()}")

        return result

    def _analyze_dependencies(
        self,
        test_names: List[str],
        test_files: Optional[Dict[str, str]] = None
    ) -> Dict[str, TestDependency]:
        """
        Analyze tests to detect dependencies

        Args:
            test_names: List of test names
            test_files: Optional test file contents for analysis

        Returns:
            Dict mapping test names to their dependencies
        """
        dependencies = {}

        for test_name in test_names:
            dep_type = self._determine_dependency_type(test_name, test_files)
            depends_on = self._find_dependencies(test_name, test_names, test_files)

            dependencies[test_name] = TestDependency(
                test_name=test_name,
                dependency_type=dep_type,
                depends_on=depends_on,
                priority=self._calculate_priority(test_name, dep_type)
            )

        # Build blocking relationships
        for test_name, dep in dependencies.items():
            for other_test in dep.depends_on:
                if other_test in dependencies:
                    dependencies[other_test].blocks.add(test_name)

        self.logger.debug(f"Found {len(dependencies)} test dependencies")
        return dependencies

    def _determine_dependency_type(
        self,
        test_name: str,
        test_files: Optional[Dict[str, str]] = None
    ) -> DependencyType:
        """Determine the dependency type for a test"""
        test_lower = test_name.lower()

        # Check for shared state modifiers
        for pattern in self.SHARED_STATE_PATTERNS:
            if re.search(pattern, test_lower):
                return DependencyType.SHARED_STATE

        # Check for exclusive resources
        for pattern in self.RESOURCE_PATTERNS:
            if re.search(pattern, test_lower):
                return DependencyType.RESOURCE

        # Check test file content if available
        if test_files and test_name in test_files:
            content = test_files[test_name].lower()
            if 'await' in content and 'login' in content:
                return DependencyType.SHARED_STATE
            if 'shared' in content or 'global' in content:
                return DependencyType.SHARED_STATE

        # Default to isolated (can run in parallel)
        return DependencyType.ISOLATED

    def _find_dependencies(
        self,
        test_name: str,
        all_tests: List[str],
        test_files: Optional[Dict[str, str]] = None
    ) -> Set[str]:
        """Find tests that this test depends on"""
        dependencies = set()
        test_lower = test_name.lower()

        # Heuristic: Tests with "login" in name depend on user creation tests
        if 'login' in test_lower:
            for other_test in all_tests:
                if 'create' in other_test.lower() and 'user' in other_test.lower():
                    dependencies.add(other_test)

        # Heuristic: "delete" tests depend on corresponding "create" tests
        if 'delete' in test_lower:
            resource = test_lower.replace('delete', '').strip()
            for other_test in all_tests:
                if f'create{resource}' in other_test.lower():
                    dependencies.add(other_test)

        # Heuristic: "update" tests depend on corresponding "create" tests
        if 'update' in test_lower:
            resource = test_lower.replace('update', '').strip()
            for other_test in all_tests:
                if f'create{resource}' in other_test.lower():
                    dependencies.add(other_test)

        return dependencies

    def _calculate_priority(self, test_name: str, dep_type: DependencyType) -> int:
        """
        Calculate test priority (higher = run earlier)

        Priority logic:
        - User creation: High priority (enables other tests)
        - Login tests: Medium-high priority
        - Core functionality: Medium priority
        - Cleanup/delete: Low priority (run last)
        - Isolated tests: Medium priority (good for parallelization)
        """
        test_lower = test_name.lower()

        if 'create' in test_lower and 'user' in test_lower:
            return 100  # Highest - creates foundation for other tests
        if 'register' in test_lower:
            return 95
        if 'create' in test_lower:
            return 85  # High priority for all create operations
        if 'login' in test_lower:
            return 80
        if 'delete' in test_lower or 'cleanup' in test_lower:
            return 5  # Lowest - cleanup operations (even lower than before)
        if dep_type == DependencyType.ISOLATED:
            return 60  # Medium-high - good candidates for parallelization
        if dep_type == DependencyType.RESOURCE:
            return 50  # Medium - exclusive resources
        return 40  # Default

    def _build_dependency_graph(
        self,
        dependencies: Dict[str, TestDependency]
    ) -> Dict[str, Set[str]]:
        """
        Build dependency graph for topological sorting

        Returns:
            Dict mapping test names to set of tests they depend on
        """
        graph = {}
        for test_name, dep in dependencies.items():
            graph[test_name] = dep.depends_on.copy()
        return graph

    def _topological_sort(
        self,
        graph: Dict[str, Set[str]]
    ) -> List[str]:
        """
        Perform topological sort on dependency graph

        Returns:
            List of tests in execution order (dependencies before dependents)
        """
        # Kahn's algorithm for topological sort
        in_degree = {node: len(deps) for node, deps in graph.items()}
        queue = [node for node, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # Sort queue by priority (extract from dependencies)
            queue.sort(key=lambda x: self._dependencies.get(x, TestDependency(x, DependencyType.ISOLATED)).priority, reverse=True)

            node = queue.pop(0)
            result.append(node)

            # Reduce in-degree for dependent nodes
            for dependent, deps in graph.items():
                if node in deps:
                    new_graph = {k: v.copy() for k, v in graph.items()}
                    new_graph[dependent].remove(node)
                    if len(new_graph[dependent]) == 0:
                        queue.append(dependent)
                    graph = new_graph

        # Check for cycles (if result doesn't contain all nodes)
        if len(result) != len(graph):
            self.logger.warning(
                "Detected circular dependencies or missing nodes. "
                "Some tests may not execute in optimal order."
            )
            # Add remaining nodes (they have cycles, just add them)
            for node in graph:
                if node not in result:
                    result.append(node)

        return result

    def _group_for_parallel_execution(
        self,
        execution_order: List[str],
        dependencies: Dict[str, TestDependency],
        max_workers: int
    ) -> List[ExecutionGroup]:
        """
        Group tests for parallel execution

        Groups tests that can run in parallel (no dependencies between them)
        while respecting the execution order.

        Args:
            execution_order: Tests in dependency order
            dependencies: Test dependency information
            max_workers: Maximum parallel workers

        Returns:
            List of ExecutionGroup objects
        """
        groups = []
        current_group: List[str] = []
        current_group_blocking: Set[str] = set()
        group_id = 0

        for test_name in execution_order:
            test_dep = dependencies[test_name]

            # Check if this test can run in current group
            can_add_to_current = (
                # Test must not be blocked by anything in current group
                not current_group_blocking.intersection(test_dep.depends_on) and
                # Current group tests must not be blocked by this test
                not any(test_name in dependencies[t].blocks for t in current_group) and
                # Respect max workers
                len(current_group) < max_workers
            )

            if can_add_to_current:
                # Add to current group
                current_group.append(test_name)
                current_group_blocking.update(test_dep.blocks)
            else:
                # Start new group
                if current_group:
                    groups.append(ExecutionGroup(
                        group_id=group_id,
                        tests=current_group,
                        can_run_in_parallel=len(current_group) > 1,
                        estimated_duration_ms=self._estimate_group_duration(current_group, dependencies)
                    ))
                    group_id += 1

                current_group = [test_name]
                current_group_blocking = test_dep.blocks.copy()

        # Add final group
        if current_group:
            groups.append(ExecutionGroup(
                group_id=group_id,
                tests=current_group,
                can_run_in_parallel=len(current_group) > 1,
                estimated_duration_ms=self._estimate_group_duration(current_group, dependencies)
            ))

        self.logger.debug(
            f"Created {len(groups)} execution groups "
            f"({len([g for g in groups if g.can_run_in_parallel])} parallel)"
        )

        return groups

    def _estimate_group_duration(
        self,
        group_tests: List[str],
        dependencies: Dict[str, TestDependency]
    ) -> int:
        """
        Estimate duration for a group of tests

        For parallel groups, uses the maximum duration among tests.
        For sequential groups, sums the durations.
        """
        if not group_tests:
            return 0

        # Use historical data if available
        durations = []
        for test_name in group_tests:
            if test_name in self._test_history:
                avg_duration = sum(self._test_history[test_name]) / len(self._test_history[test_name])
                durations.append(avg_duration)

        if durations:
            # For parallel execution, duration is max of all tests
            # For sequential, it's sum
            if len(group_tests) > 1:
                return int(max(durations))
            return int(sum(durations))

        # Default estimate if no historical data
        return len(group_tests) * 5000  # Assume 5 seconds per test

    def _estimate_total_duration(
        self,
        groups: List[ExecutionGroup],
        dependencies: Dict[str, TestDependency]
    ) -> int:
        """Estimate total execution time for all groups"""
        return sum(group.estimated_duration_ms for group in groups)

    def _calculate_parallelization_efficiency(
        self,
        groups: List[ExecutionGroup],
        max_workers: int
    ) -> float:
        """
        Calculate parallelization efficiency

        Returns:
            Float between 0.0 and 1.0, where:
            - 1.0 = perfect parallelization (all groups use max_workers)
            - 0.0 = no parallelization (all groups sequential)
        """
        if not groups:
            return 0.0

        total_tests = sum(len(g.tests) for g in groups)
        parallel_tests = sum(len(g.tests) for g in groups if g.can_run_in_parallel)

        if total_tests == 0:
            return 0.0

        # Calculate ratio of tests that can run in parallel
        base_efficiency = parallel_tests / total_tests

        # Adjust for worker utilization
        avg_group_size = total_tests / len(groups) if groups else 0
        worker_utilization = min(avg_group_size / max_workers, 1.0)

        # Combined efficiency metric
        return base_efficiency * worker_utilization

    def update_test_history(self, test_name: str, duration_ms: float) -> None:
        """
        Update historical duration data for a test

        This helps improve future duration estimates and grouping decisions.
        """
        self._test_history[test_name].append(duration_ms)

        # Keep only last 10 executions to avoid stale data
        if len(self._test_history[test_name]) > 10:
            self._test_history[test_name] = self._test_history[test_name][-10:]

    def get_execution_plan(self, result: SelectionResult) -> str:
        """
        Get a human-readable execution plan

        Args:
            result: Selection result from select_tests()

        Returns:
            Formatted string describing the execution plan
        """
        lines = [
            "=" * 60,
            "SMART TEST SELECTION EXECUTION PLAN",
            "=" * 60,
            "",
            f"Total Tests: {len(result.selected_tests)}",
            f"Execution Groups: {len(result.execution_groups)}",
            f"Estimated Duration: {result.total_estimated_duration_ms / 1000:.1f}s",
            f"Parallelization Efficiency: {result.parallelization_efficiency:.1%}",
            "",
            "EXECUTION ORDER:",
        ]

        for i, group in enumerate(result.execution_groups, 1):
            parallel_label = "PARALLEL" if group.can_run_in_parallel else "SEQUENTIAL"
            lines.append(f"\n  Group {i} ({parallel_label}):")
            for test in group.tests:
                dep = next((d for d in result.dependencies if d.test_name == test), None)
                if dep:
                    lines.append(f"    - {test} ({dep.dependency_type.value}, priority={dep.priority})")
                else:
                    lines.append(f"    - {test}")

        lines.append("\n" + "=" * 60)

        return "\n".join(lines)
