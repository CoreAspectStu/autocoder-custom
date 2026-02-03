"""
Change-Based Test Selector - Select tests based on code changes

This module analyzes git changes to determine which test journeys should be executed.
It maps code changes to features and selects only the affected journeys, reducing
test execution time by skipping unrelated tests.

Feature #207 implementation
"""

import subprocess
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

import sys

# Add parent directory to path for imports

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import TestExecutionError, handle_errors


# ============================================================================
# Data Models
# ============================================================================

class ChangeType(Enum):
    """Types of code changes"""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass
class CodeChange:
    """Represents a single file change"""
    file_path: str
    change_type: ChangeType
    diff_stats: Optional[str] = None  # e.g., "+10 -5"
    affected_functions: Set[str] = field(default_factory=set)
    affected_classes: Set[str] = field(default_factory=set)

    def __str__(self) -> str:
        return f"{self.change_type.value}: {self.file_path}"


@dataclass
class FeatureMapping:
    """Maps a file or pattern to a feature/journey"""
    pattern: str  # File path pattern or regex
    journey_ids: Set[str]  # Journey IDs affected by changes to this pattern
    description: str = ""  # Description of what this pattern represents

    def matches(self, file_path: str) -> bool:
        """Check if a file path matches this pattern"""
        # Simple pattern matching (supports wildcards)
        pattern = self.pattern.replace("*", ".*").replace("?", ".")
        return bool(re.search(pattern, file_path))


# ============================================================================
# Change-Based Selector
# ============================================================================

class ChangeBasedSelector:
    """
    Selects test journeys based on code changes

    The change-based selector:
    1. Detects code changes using git diff
    2. Maps changes to features using predefined patterns
    3. Selects affected journeys for execution
    4. Skips unrelated journeys to save time
    """

    def __init__(self, base_branch: str = "main"):
        """
        Initialize the change-based selector

        Args:
            base_branch: The git branch to compare against (default: main)
        """
        self.base_branch = base_branch
        self.logger = get_logger("change_based_selector")
        self.feature_mappings: List[FeatureMapping] = []
        self._initialize_default_mappings()

    def _initialize_default_mappings(self) -> None:
        """
        Initialize default feature-to-journey mappings

        These mappings define which code areas affect which test journeys.
        In a real system, these would be loaded from config or discovered.
        """
        # Core framework mappings
        self.feature_mappings.extend([
            # Orchestrator affects all integration tests
            FeatureMapping(
                pattern=r"src/orchestrator/.*",
                journey_ids={"*"},  # Wildcard = all journeys
                description="Core orchestration logic affects all tests"
            ),

            # Test executor affects all test execution
            FeatureMapping(
                pattern=r"src/test_executor/.*",
                journey_ids={"*"},
                description="Test execution framework affects all tests"
            ),

            # Journey extractor affects journey-based tests
            FeatureMapping(
                pattern=r"src/journey_extractor/.*",
                journey_ids={"*"},
                description="Journey extraction affects all journey-based tests"
            ),

            # API adapter affects API tests
            FeatureMapping(
                pattern=r"src/adapters/api/.*",
                journey_ids={"api-testing", "integration-tests"},
                description="API adapter affects API testing journeys"
            ),

            # Visual adapter affects visual/UI tests
            FeatureMapping(
                pattern=r"src/adapters/visual/.*",
                journey_ids={"visual-testing", "ui-tests"},
                description="Visual adapter affects visual/UI tests"
            ),

            # Accessibility adapter affects a11y tests
            FeatureMapping(
                pattern=r"src/adapters/a11y/.*",
                journey_ids={"a11y-testing", "accessibility-tests"},
                description="Accessibility adapter affects a11y tests"
            ),

            # Result processor affects result-related tests
            FeatureMapping(
                pattern=r"src/result_processor/.*",
                journey_ids={"result-processing", "autofix"},
                description="Result processor affects result handling"
            ),

            # Performance detector affects performance tests
            FeatureMapping(
                pattern=r"src/performance/.*",
                journey_ids={"performance-testing"},
                description="Performance detector affects performance tests"
            ),

            # Real-time updates affect websocket tests
            FeatureMapping(
                pattern=r"src/realtime/.*",
                journey_ids={"websocket-tests", "realtime-updates"},
                description="Real-time updates affect websocket tests"
            ),

            # State manager affects state-related tests
            FeatureMapping(
                pattern=r"src/state_manager/.*",
                journey_ids={"state-management", "persistence"},
                description="State manager affects state management tests"
            ),

            # Kanban integrator affects kanban tests
            FeatureMapping(
                pattern=r"src/kanban_integrator/.*",
                journey_ids={"kanban-integration", "card-creation"},
                description="Kanban integrator affects kanban tests"
            ),

            # AutoFix affects autofix-related tests
            FeatureMapping(
                pattern=r"src/autofix/.*",
                journey_ids={"autofix", "auto-fix"},
                description="AutoFix affects auto-fix tests"
            ),
        ])

    @handle_errors(component="change_based_selector", reraise=True)
    def detect_changes(self, target_branch: Optional[str] = None) -> List[CodeChange]:
        """
        Detect code changes using git diff

        Args:
            target_branch: Branch to compare against (defaults to self.base_branch)

        Returns:
            List of detected code changes

        Raises:
            TestExecutionError: If git operations fail
        """
        branch = target_branch or self.base_branch

        try:
            self.logger.info(f"Detecting changes against branch: {branch}")

            # Get list of changed files
            result = subprocess.run(
                ['git', 'diff', '--name-status', branch],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                raise TestExecutionError(
                    f"Git diff failed: {result.stderr}",
                    component="change_based_selector"
                )

            # Parse changed files
            changes = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                parts = line.split('\t')
                if len(parts) < 2:
                    continue

                status_code = parts[0]
                file_path = parts[1]

                # Determine change type
                change_type = self._parse_change_type(status_code)

                # Get diff stats for modified files
                diff_stats = None
                if change_type in [ChangeType.MODIFIED, ChangeType.ADDED]:
                    diff_stats = self._get_diff_stats(file_path, branch)

                # Extract affected functions/classes (simplified)
                affected_functions, affected_classes = self._extract_code_elements(
                    file_path, branch
                )

                change = CodeChange(
                    file_path=file_path,
                    change_type=change_type,
                    diff_stats=diff_stats,
                    affected_functions=affected_functions,
                    affected_classes=affected_classes
                )

                changes.append(change)
                self.logger.debug(f"Detected change: {change}")

            self.logger.info(f"Detected {len(changes)} code changes")
            return changes

        except subprocess.TimeoutExpired:
            raise TestExecutionError(
                "Git diff timed out",
                component="change_based_selector"
            )
        except FileNotFoundError:
            raise TestExecutionError(
                "Git not found. Please ensure git is installed.",
                component="change_based_selector"
            )
        except Exception as e:
            raise TestExecutionError(
                f"Failed to detect changes: {str(e)}",
                component="change_based_selector",
                context={"error": str(e)}
            )

    def _parse_change_type(self, status_code: str) -> ChangeType:
        """Parse git status code to ChangeType enum"""
        status_map = {
            'A': ChangeType.ADDED,
            'M': ChangeType.MODIFIED,
            'D': ChangeType.DELETED,
            'R': ChangeType.RENAMED,
            'C': ChangeType.ADDED,  # Copied
            'T': ChangeType.MODIFIED,  # Type changed
        }
        return status_map.get(status_code[0], ChangeType.MODIFIED)

    def _get_diff_stats(self, file_path: str, branch: str) -> Optional[str]:
        """Get diff stats for a file (e.g., '+10 -5')"""
        try:
            result = subprocess.run(
                ['git', 'diff', branch, '--numstat', '--', file_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    added = parts[0]
                    deleted = parts[1]
                    return f"+{added} -{deleted}"

            return None

        except Exception:
            return None

    def _extract_code_elements(
        self,
        file_path: str,
        branch: str
    ) -> Tuple[Set[str], Set[str]]:
        """
        Extract affected functions and classes from a changed file

        This is a simplified implementation. In production, you'd parse
        the actual diff to identify changed functions/classes.

        Args:
            file_path: Path to the changed file
            branch: Branch to compare against

        Returns:
            Tuple of (affected_functions, affected_classes)
        """
        # For Python files, we could parse the diff for function/class definitions
        # For now, return empty sets as a conservative default
        return set(), set()

    @handle_errors(component="change_based_selector", reraise=True)
    def map_changes_to_features(self, changes: List[CodeChange]) -> Set[str]:
        """
        Map code changes to affected journey IDs

        Args:
            changes: List of detected code changes

        Returns:
            Set of journey IDs that are affected by the changes
        """
        affected_journeys = set()

        for change in changes:
            for mapping in self.feature_mappings:
                if mapping.matches(change.file_path):
                    # Add all journey IDs from this mapping
                    affected_journeys.update(mapping.journey_ids)

                    # If wildcard, we'll mark all journeys as affected
                    if "*" in mapping.journey_ids:
                        self.logger.info(
                            f"Change to {change.file_path} affects ALL journeys "
                            f"(matched pattern: {mapping.pattern})"
                        )
                        # Return early - all journeys are affected
                        return {"*"}

                    self.logger.debug(
                        f"Change to {change.file_path} affects journeys: "
                        f"{mapping.journey_ids} (reason: {mapping.description})"
                    )

        self.logger.info(f"Mapped {len(changes)} changes to {len(affected_journeys)} journeys")
        return affected_journeys

    @handle_errors(component="change_based_selector", reraise=True)
    def select_affected_journeys(
        self,
        all_journey_ids: Set[str],
        target_branch: Optional[str] = None
    ) -> Tuple[Set[str], Set[str]]:
        """
        Select affected journeys based on code changes

        Args:
            all_journey_ids: All available journey IDs in the system
            target_branch: Branch to compare against (defaults to self.base_branch)

        Returns:
            Tuple of (selected_journey_ids, skipped_journey_ids)
        """
        # Detect changes
        changes = self.detect_changes(target_branch)

        if not changes:
            self.logger.warning("No changes detected - selecting all journeys")
            return all_journey_ids, set()

        # Map changes to features
        affected_journey_ids = self.map_changes_to_features(changes)

        # If wildcard, all journeys are affected
        if "*" in affected_journey_ids:
            self.logger.info("All journeys affected by changes")
            return all_journey_ids, set()

        # Determine which journeys to select and which to skip
        selected = set()
        skipped = set()

        for journey_id in all_journey_ids:
            if journey_id in affected_journey_ids:
                selected.add(journey_id)
            else:
                skipped.add(journey_id)

        self.logger.info(
            f"Smart selection: {len(selected)} journeys to run, "
            f"{len(skipped)} journeys to skip"
        )

        return selected, skipped

    @handle_errors(component="change_based_selector", reraise=True)
    def estimate_time_savings(
        self,
        skipped_journey_ids: Set[str],
        avg_journey_time_ms: int = 5000
    ) -> Dict[str, any]:
        """
        Estimate time saved by smart selection

        Args:
            skipped_journey_ids: Journey IDs that were skipped
            avg_journey_time_ms: Average execution time per journey in milliseconds

        Returns:
            Dictionary with time savings statistics
        """
        skipped_count = len(skipped_journey_ids)
        total_time_saved_ms = skipped_count * avg_journey_time_ms
        total_time_saved_sec = total_time_saved_ms / 1000

        return {
            "skipped_journeys": skipped_count,
            "avg_journey_time_ms": avg_journey_time_ms,
            "total_time_saved_ms": total_time_saved_ms,
            "total_time_saved_sec": total_time_saved_sec,
            "total_time_saved_min": total_time_saved_sec / 60,
        }


# ============================================================================
# Convenience Functions
# ============================================================================

def get_change_based_selector(base_branch: str = "main") -> ChangeBasedSelector:
    """Factory function to get a ChangeBasedSelector instance"""
    return ChangeBasedSelector(base_branch)


def select_affected_journeys(
    all_journey_ids: Set[str],
    base_branch: str = "main"
) -> Tuple[Set[str], Set[str]]:
    """
    Convenience function to select affected journeys

    Args:
        all_journey_ids: All available journey IDs
        base_branch: Git branch to compare against

    Returns:
        Tuple of (selected_journey_ids, skipped_journey_ids)
    """
    selector = get_change_based_selector(base_branch)
    return selector.select_affected_journeys(all_journey_ids)
