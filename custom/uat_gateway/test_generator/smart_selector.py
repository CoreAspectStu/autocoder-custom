"""
Smart Selector - Intelligently map code changes to affected features

This module analyzes git changes and determines which test features/journeys
are affected by code changes, enabling smart test selection.

Key capabilities:
1. Detect changed files since a git commit
2. Map changed files to features/journeys
3. Determine affected test scenarios
4. Provide intelligent test selection recommendations
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import TestGenerationError, handle_errors


# ============================================================================
# Data Models
# ============================================================================

class ChangeType(Enum):
    """Type of code change"""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


@dataclass
class FileChange:
    """Represents a single file change"""
    file_path: str
    change_type: ChangeType
    additions: int = 0
    deletions: int = 0
    diff_summary: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.change_type.value}: {self.file_path} (+{self.additions}, -{self.deletions})"

    def get_extension(self) -> str:
        """Get file extension"""
        return Path(self.file_path).suffix.lower()

    def get_directory(self) -> str:
        """Get parent directory"""
        return str(Path(self.file_path).parent)


@dataclass
class FeatureMapping:
    """Maps a code file pattern to features/journeys"""
    pattern: str  # Glob pattern or regex
    feature_ids: List[str]  # List of feature IDs affected
    journey_ids: List[str]  # List of journey IDs affected
    description: str
    priority: int = 5  # 1-10, for weighting matches

    def matches(self, file_path: str) -> bool:
        """
        Check if a file path matches this mapping pattern

        Args:
            file_path: Path to check

        Returns:
            True if file matches this pattern
        """
        # Normalize path separators
        normalized_path = file_path.replace('\\', '/')

        # Try exact pattern match first
        if normalized_path == self.pattern:
            return True

        # Try as glob pattern using fnmatch
        import fnmatch
        if fnmatch.fnmatch(normalized_path, self.pattern):
            return True

        # Try with ** wildcard expansion
        if '**' in self.pattern:
            # Split pattern and path
            pattern_parts = self.pattern.split('/')
            path_parts = normalized_path.split('/')

            # Match parts allowing ** to match multiple parts
            pi = 0
            for part in pattern_parts:
                if part == '**':
                    # ** matches zero or more parts
                    # Skip to next pattern part or end
                    if pi == len(pattern_parts) - 1:
                        return True  # ** at end matches everything
                    # Find the next fixed part
                    next_part = pattern_parts[pi + 1] if pi + 1 < len(pattern_parts) else None
                    if next_part:
                        while pi < len(path_parts) and path_parts[pi] != next_part:
                            pi += 1
                elif pi < len(path_parts) and fnmatch.fnmatch(path_parts[pi], part):
                    pi += 1
                else:
                    return False

            return pi >= len(path_parts) - 1

        # Try as regex
        try:
            if re.search(self.pattern, normalized_path):
                return True
        except re.error:
            pass

        return False


@dataclass
class SelectionResult:
    """Result of smart selection analysis"""
    changed_files: List[FileChange]
    affected_features: Set[str]
    affected_journeys: Set[str]
    confidence_score: float  # 0.0-1.0
    reasoning: List[str]  # Human-readable explanations

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "changed_files": [str(f) for f in self.changed_files],
            "affected_features": list(self.affected_features),
            "affected_journeys": list(self.affected_journeys),
            "confidence_score": self.confidence_score,
            "reasoning": self.reasoning
        }


# ============================================================================
# Smart Selector
# ============================================================================

class SmartSelector:
    """
    Intelligently selects tests based on code changes

    This class:
    1. Analyzes git diff to find changed files
    2. Maps changed files to features/journeys
    3. Provides recommendations for which tests to run
    """

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize SmartSelector

        Args:
            project_root: Root directory of the project (defaults to CWD)
        """
        self.logger = get_logger("smart_selector")
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.feature_mappings: List[FeatureMapping] = []
        self._initialize_default_mappings()

    @handle_errors(component="smart_selector", reraise=True)
    def detect_changed_files(
        self,
        since_commit: Optional[str] = None,
        branch: Optional[str] = None
    ) -> List[FileChange]:
        """
        Detect changed files using git

        Args:
            since_commit: Git commit SHA to compare against (default: HEAD~1)
            branch: Branch to compare against main/master

        Returns:
            List of FileChange objects

        Raises:
            TestGenerationError: If git operations fail
        """
        self.logger.info(f"Detecting changed files (since: {since_commit or 'HEAD~1'})")

        # Determine the git comparison target
        if branch:
            base_ref = f"origin/{branch}" if "origin/" not in branch else branch
            compare_ref = f"{base_ref}...HEAD"
        elif since_commit:
            compare_ref = since_commit
        else:
            compare_ref = "HEAD~1"

        try:
            # Get list of changed files
            result = subprocess.run(
                ['git', 'diff', '--name-status', compare_ref],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.project_root
            )

            if result.returncode != 0:
                raise TestGenerationError(
                    f"Git diff failed: {result.stderr}",
                    component="smart_selector",
                    context={"compare_ref": compare_ref, "error": result.stderr}
                )

            # Parse changed files
            changed_files = []
            lines = result.stdout.strip().split('\n')

            for line in lines:
                if not line:
                    continue

                parts = line.split('\t')
                if len(parts) < 2:
                    continue

                status_code = parts[0]
                file_path = parts[1]

                # Determine change type
                if status_code == 'A':
                    change_type = ChangeType.ADDED
                elif status_code == 'D':
                    change_type = ChangeType.DELETED
                elif status_code == 'R' or status_code.startswith('R'):
                    change_type = ChangeType.RENAMED
                else:
                    change_type = ChangeType.MODIFIED

                # Get diff stats for modified files
                additions = 0
                deletions = 0

                if change_type in [ChangeType.MODIFIED, ChangeType.ADDED]:
                    try:
                        numstat_result = subprocess.run(
                            ['git', 'diff', '--numstat', compare_ref, '--', file_path],
                            capture_output=True,
                            text=True,
                            timeout=30,
                            cwd=self.project_root
                        )

                        if numstat_result.returncode == 0:
                            stat_lines = numstat_result.stdout.strip().split('\n')
                            for stat_line in stat_lines:
                                stat_parts = stat_line.split()
                                if len(stat_parts) >= 2:
                                    try:
                                        additions = int(stat_parts[0])
                                        deletions = int(stat_parts[1])
                                    except ValueError:
                                        pass
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        pass

                file_change = FileChange(
                    file_path=file_path,
                    change_type=change_type,
                    additions=additions,
                    deletions=deletions
                )
                changed_files.append(file_change)

            self.logger.info(f"Detected {len(changed_files)} changed files")
            for fc in changed_files:
                self.logger.debug(f"  {fc}")

            return changed_files

        except subprocess.TimeoutExpired:
            raise TestGenerationError(
                "Git diff timed out",
                component="smart_selector"
            )
        except FileNotFoundError:
            raise TestGenerationError(
                "Git not found. Please ensure git is installed.",
                component="smart_selector"
            )
        except Exception as e:
            raise TestGenerationError(
                f"Failed to detect changed files: {str(e)}",
                component="smart_selector",
                context={"error": str(e)}
            )

    @handle_errors(component="smart_selector", reraise=True)
    def analyze_changes(self, changed_files: List[FileChange]) -> SelectionResult:
        """
        Analyze changed files and determine affected features

        Args:
            changed_files: List of FileChange objects

        Returns:
            SelectionResult with affected features and reasoning
        """
        self.logger.info(f"Analyzing {len(changed_files)} changed files")

        affected_features = set()
        affected_journeys = set()
        reasoning = []
        match_count = 0

        for file_change in changed_files:
            file_path = file_change.file_path
            self.logger.debug(f"Analyzing: {file_path}")

            # Find matching feature mappings
            matched = False
            for mapping in self.feature_mappings:
                if mapping.matches(file_path):
                    affected_features.update(mapping.feature_ids)
                    affected_journeys.update(mapping.journey_ids)

                    reason = f"File '{file_path}' matches '{mapping.pattern}' -> {mapping.description}"
                    reasoning.append(reason)
                    self.logger.debug(f"  ✓ {reason}")

                    match_count += 1
                    matched = True

            if not matched:
                # No explicit mapping - add generic reasoning
                ext = file_change.get_extension()
                if ext in ['.py', '.ts', '.tsx', '.js', '.jsx']:
                    reasoning.append(f"File '{file_path}' ({ext} changed) - may affect multiple features")
                    affected_features.add("all")  # Flag to run all tests
                elif ext in ['.css', '.scss', '.less']:
                    reasoning.append(f"Style file '{file_path}' changed - may affect visual tests")
                    affected_features.add("visual")
                elif ext in ['.yaml', '.yml', '.json']:
                    reasoning.append(f"Config file '{file_path}' changed - may affect test configuration")
                    affected_features.add("config")

        # Calculate confidence score
        total_files = len(changed_files)
        if total_files == 0:
            confidence_score = 0.0
        elif "all" in affected_features:
            confidence_score = 0.5  # Low confidence - need to run everything
        else:
            confidence_score = min(match_count / total_files, 1.0)

        self.logger.info(f"Analysis complete: {len(affected_features)} features affected")
        self.logger.info(f"Confidence score: {confidence_score:.2f}")

        return SelectionResult(
            changed_files=changed_files,
            affected_features=affected_features,
            affected_journeys=affected_journeys,
            confidence_score=confidence_score,
            reasoning=reasoning
        )

    @handle_errors(component="smart_selector", reraise=True)
    def select_tests_to_run(
        self,
        since_commit: Optional[str] = None,
        branch: Optional[str] = None
    ) -> SelectionResult:
        """
        Main entry point: Detect changes and select tests to run

        Args:
            since_commit: Git commit SHA to compare against
            branch: Branch to compare against

        Returns:
            SelectionResult with recommendations
        """
        self.logger.info("Starting smart test selection")

        # Step 1: Detect changed files
        changed_files = self.detect_changed_files(since_commit, branch)

        if not changed_files:
            self.logger.info("No changes detected - no tests to run")
            return SelectionResult(
                changed_files=[],
                affected_features=set(),
                affected_journeys=set(),
                confidence_score=1.0,
                reasoning=["No changes detected"]
            )

        # Step 2: Analyze changes and map to features
        result = self.analyze_changes(changed_files)

        self.logger.info("Smart selection complete")
        return result

    @handle_errors(component="smart_selector", reraise=True)
    def estimate_execution_time(
        self,
        selection_result: Optional[SelectionResult] = None,
        use_historical_data: bool = True
    ) -> float:
        """
        Estimate execution time for selected tests

        Feature #210: Calculate estimated execution time based on:
        - Number of affected features/journeys
        - Number of changed files
        - Historical performance data (if available)
        - Average test duration

        Args:
            selection_result: SelectionResult from select_tests_to_run or analyze_changes
            use_historical_data: Whether to use historical performance data

        Returns:
            Estimated execution time in seconds
        """
        self.logger.info("Estimating execution time for selected tests")

        # Import here to avoid circular dependency
        try:
            from uat_gateway.test_executor.performance_detector import PerformanceDetector
            from uat_gateway.state_manager.state_manager import StateManager
            perf_detector_available = True
        except ImportError:
            perf_detector_available = False
            self.logger.warning("PerformanceDetector not available - using default estimates")

        # If no selection result provided, do a fresh selection
        if selection_result is None:
            selection_result = self.select_tests_to_run()

        # No tests to run
        if not selection_result.affected_features:
            return 0.0

        # Try to get historical performance data
        historical_avg_seconds = None

        if use_historical_data and perf_detector_available:
            try:
                perf_detector = PerformanceDetector()
                summary = perf_detector.get_performance_summary()

                if summary and summary.total_executions > 0:
                    # Convert milliseconds to seconds
                    historical_avg_seconds = summary.avg_duration_ms / 1000.0
                    self.logger.info(f"Using historical avg: {historical_avg_seconds:.1f} seconds")
                else:
                    self.logger.info("No historical performance data - using defaults")
            except Exception as e:
                self.logger.warning(f"Could not load performance data: {e}")

        # Calculate base estimate from selection size
        num_features = len(selection_result.affected_features)
        num_journeys = len(selection_result.affected_journeys)
        num_files = len(selection_result.changed_files)

        # Default timing assumptions (can be customized per project)
        seconds_per_feature = 30.0  # Average 30 seconds per feature
        seconds_per_journey = 120.0  # Average 2 minutes per journey
        seconds_per_file = 10.0  # Overhead for each changed file

        # Base estimate from counts
        base_estimate = (
            (num_features * seconds_per_feature) +
            (num_journeys * seconds_per_journey) +
            (num_files * seconds_per_file)
        )

        # Adjust for "all" flag (means run everything - slower)
        if "all" in selection_result.affected_features:
            base_estimate *= 2.0  # Double the estimate for full test suite
            self.logger.debug("Adjusted estimate: 'all' flag detected")

        # Adjust for "visual" flag (visual tests are slower)
        if "visual" in selection_result.affected_features:
            base_estimate *= 1.5  # 50% more time for visual tests
            self.logger.debug("Adjusted estimate: visual tests included")

        # Use historical data if available to refine estimate
        if historical_avg_seconds is not None:
            # Blend base estimate with historical data
            # Weight: 70% historical, 30% base calculation
            final_estimate = (historical_avg_seconds * 0.7) + (base_estimate * 0.3)
            self.logger.info(f"Blended estimate: {final_estimate:.1f}s (historical: {historical_avg_seconds:.1f}s, base: {base_estimate:.1f}s)")
        else:
            final_estimate = base_estimate
            self.logger.info(f"Base estimate: {final_estimate:.1f}s")

        # Sanity checks
        # Minimum 10 seconds even for small selections
        final_estimate = max(final_estimate, 10.0)

        # Maximum 1 hour (very conservative)
        final_estimate = min(final_estimate, 3600.0)

        self.logger.info(f"Final execution time estimate: {final_estimate:.1f} seconds ({final_estimate/60:.1f} minutes)")

        return final_estimate

    def add_feature_mapping(
        self,
        pattern: str,
        feature_ids: List[str],
        journey_ids: List[str],
        description: str,
        priority: int = 5
    ) -> None:
        """
        Add a custom feature mapping

        Args:
            pattern: Glob pattern or regex to match files
            feature_ids: List of affected feature IDs
            journey_ids: List of affected journey IDs
            description: Human-readable description
            priority: Priority for weighting (1-10)
        """
        mapping = FeatureMapping(
            pattern=pattern,
            feature_ids=feature_ids,
            journey_ids=journey_ids,
            description=description,
            priority=priority
        )
        self.feature_mappings.append(mapping)
        self.logger.debug(f"Added mapping: {pattern} -> {description}")

    def _initialize_default_mappings(self) -> None:
        """
        Initialize default file-to-feature mappings

        This sets up common patterns for mapping code files to features.
        Projects should customize this for their specific structure.
        """
        # Authentication features
        self.feature_mappings.append(FeatureMapping(
            pattern="**/auth/**/*.py",
            feature_ids=["authentication", "login", "logout", "registration"],
            journey_ids=["auth-journey", "login-journey", "registration-journey"],
            description="Authentication module changes",
            priority=8
        ))

        self.feature_mappings.append(FeatureMapping(
            pattern="**/auth/**/*.ts",
            feature_ids=["authentication", "login", "logout"],
            journey_ids=["auth-journey"],
            description="Frontend auth components",
            priority=8
        ))

        # User management
        self.feature_mappings.append(FeatureMapping(
            pattern="**/user/**/*.py",
            feature_ids=["user-management", "profile", "settings"],
            journey_ids=["user-profile-journey", "settings-journey"],
            description="User management module",
            priority=7
        ))

        # API endpoints
        self.feature_mappings.append(FeatureMapping(
            pattern="**/api/**/*.py",
            feature_ids=["api", "backend"],
            journey_ids=["api-journey"],
            description="API backend changes",
            priority=9
        ))

        # Database
        self.feature_mappings.append(FeatureMapping(
            pattern="**/models/**/*.py",
            feature_ids=["database", "schema"],
            journey_ids=["all"],  # Schema changes affect everything
            description="Database model changes",
            priority=10
        ))

        self.feature_mappings.append(FeatureMapping(
            pattern="**/migrations/**/*.py",
            feature_ids=["database", "schema"],
            journey_ids=["all"],
            description="Database migrations",
            priority=10
        ))

        # UI components
        self.feature_mappings.append(FeatureMapping(
            pattern="**/components/**/*.tsx",
            feature_ids=["ui", "frontend"],
            journey_ids=["ui-journey"],
            description="React component changes",
            priority=6
        ))

        # Test infrastructure
        self.feature_mappings.append(FeatureMapping(
            pattern="**/test_*.py",
            feature_ids=["test-infrastructure"],
            journey_ids=[],
            description="Test code changes",
            priority=3
        ))

        # Configuration
        self.feature_mappings.append(FeatureMapping(
            pattern="spec.yaml",
            feature_ids=["specification"],
            journey_ids=["all"],
            description="Spec file changes - may affect all tests",
            priority=10
        ))

        self.logger.info(f"Initialized {len(self.feature_mappings)} default feature mappings")

    @handle_errors(component="smart_selector", reraise=True)
    def export_mappings(self, output_path: str) -> None:
        """
        Export feature mappings to a file for customization

        Args:
            output_path: Path to save mappings file
        """
        import json

        mappings_data = []
        for mapping in self.feature_mappings:
            mappings_data.append({
                "pattern": mapping.pattern,
                "feature_ids": mapping.feature_ids,
                "journey_ids": mapping.journey_ids,
                "description": mapping.description,
                "priority": mapping.priority
            })

        with open(output_path, 'w') as f:
            json.dump(mappings_data, f, indent=2)

        self.logger.info(f"Exported {len(mappings_data)} mappings to {output_path}")

    @handle_errors(component="smart_selector", reraise=True)
    def import_mappings(self, input_path: str) -> None:
        """
        Import feature mappings from a file

        Args:
            input_path: Path to mappings file
        """
        import json

        with open(input_path, 'r') as f:
            mappings_data = json.load(f)

        # Replace current mappings
        self.feature_mappings = []

        for mapping_data in mappings_data:
            mapping = FeatureMapping(
                pattern=mapping_data["pattern"],
                feature_ids=mapping_data["feature_ids"],
                journey_ids=mapping_data["journey_ids"],
                description=mapping_data["description"],
                priority=mapping_data.get("priority", 5)
            )
            self.feature_mappings.append(mapping)

        self.logger.info(f"Imported {len(self.feature_mappings)} mappings from {input_path}")


# ============================================================================
# Convenience Functions
# ============================================================================

def create_smart_selector(project_root: Optional[str] = None) -> SmartSelector:
    """
    Create a SmartSelector instance

    Args:
        project_root: Root directory of the project

    Returns:
        Configured SmartSelector
    """
    return SmartSelector(project_root)


__all__ = [
    "SmartSelector",
    "FileChange",
    "ChangeType",
    "FeatureMapping",
    "SelectionResult",
    "create_smart_selector",
]
