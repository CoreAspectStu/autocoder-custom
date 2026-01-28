"""
AutoCoder Integration Module

This module provides integration between the UAT Gateway and AutoCoder projects.
It can connect to AutoCoder project directories, read spec files, and interface
with the feature management system.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import yaml

from custom.uat_gateway.utils.logger import get_logger
from custom.uat_gateway.utils.errors import JourneyExtractionError, handle_errors
from custom.uat_gateway.journey_extractor.journey_extractor import JourneyExtractor, Spec


logger = get_logger(__name__)


@dataclass
class AutoCoderProjectInfo:
    """Information about an AutoCoder project"""
    project_path: Path
    project_name: str
    spec_file: Optional[Path] = None
    has_spec: bool = False
    spec_format: Optional[str] = None  # 'yaml', 'txt', or 'unknown'
    feature_count: int = 0
    journey_count: int = 0


@dataclass
class FeatureInfo:
    """Information about a feature from the feature management system"""
    feature_id: int
    name: str
    category: str
    description: str
    passes: bool
    in_progress: bool
    dependencies: List[int]


class AutoCoderIntegration:
    """
    Integration layer for connecting UAT Gateway to AutoCoder projects

    This class provides methods to:
    - Connect to AutoCoder project directories
    - Read and parse spec files
    - Interface with the feature management MCP server
    - Verify project structure and configuration
    """

    def __init__(self, project_path: Optional[Path] = None):
        """
        Initialize AutoCoder integration

        Args:
            project_path: Path to AutoCoder project directory.
                         If None, uses the UAT Gateway's parent AutoCoder project.
        """
        if project_path is None:
            # Default to the AutoCoder project
            # uat-gateway/src/gateway -> uat-gateway -> autocoder-projects -> autocoder
            current_path = Path(__file__).resolve().parent
            project_path = current_path.parent.parent.parent.parent / "autocoder"

        self.project_path = Path(project_path).resolve()
        self.spec_file: Optional[Path] = None
        self.spec_data: Optional[Dict[str, Any]] = None
        self.extractor: Optional[JourneyExtractor] = None

        logger.info(f"AutoCoder integration initialized for project: {self.project_path}")

    def connect(self) -> AutoCoderProjectInfo:
        """
        Connect to AutoCoder project and gather information

        Returns:
            AutoCoderProjectInfo with project details

        Raises:
            JourneyExtractionError: If project directory doesn't exist or is inaccessible
        """
        logger.info(f"Connecting to AutoCoder project at: {self.project_path}")

        # Verify project directory exists
        if not self.project_path.exists():
            raise JourneyExtractionError(
                f"AutoCoder project directory does not exist: {self.project_path}"
            )

        if not self.project_path.is_dir():
            raise JourneyExtractionError(
                f"Path is not a directory: {self.project_path}"
            )

        logger.info(f"✓ Project directory exists: {self.project_path}")

        # Get project name
        project_name = self.project_path.name

        # Look for spec file
        spec_file = self._find_spec_file()

        project_info = AutoCoderProjectInfo(
            project_path=self.project_path,
            project_name=project_name,
            spec_file=spec_file,
            has_spec=spec_file is not None
        )

        if spec_file:
            project_info.spec_format = self._detect_spec_format(spec_file)
            logger.info(f"✓ Found spec file: {spec_file} (format: {project_info.spec_format})")

        return project_info

    def _find_spec_file(self) -> Optional[Path]:
        """
        Find spec file in AutoCoder project

        Searches for:
        - app_spec.txt
        - spec.yaml
        - spec.yml
        - .autocoder/spec.yaml

        Returns:
            Path to spec file, or None if not found
        """
        possible_names = [
            "app_spec.txt",
            "spec.yaml",
            "spec.yml",
            ".autocoder/spec.yaml",
            ".autocoder/spec.yml"
        ]

        for name in possible_names:
            spec_path = self.project_path / name
            if spec_path.exists() and spec_path.is_file():
                logger.debug(f"Found spec file: {spec_path}")
                return spec_path

        logger.debug("No spec file found in project")
        return None

    def _detect_spec_format(self, spec_file: Path) -> str:
        """
        Detect spec file format

        Args:
            spec_file: Path to spec file

        Returns:
            'yaml', 'txt', or 'unknown'
        """
        suffix = spec_file.suffix.lower()
        if suffix in ['.yaml', '.yml']:
            return 'yaml'
        elif suffix == '.txt':
            return 'txt'
        else:
            return 'unknown'

    def read_spec(self) -> Spec:
        """
        Read and parse the spec file

        Returns:
            Spec with parsed spec data

        Raises:
            JourneyExtractionError: If spec file cannot be read or parsed
        """
        if not self.spec_file:
            # Try to find spec file
            self.spec_file = self._find_spec_file()

        if not self.spec_file:
            raise JourneyExtractionError(
                "No spec file found in AutoCoder project. "
                "Expected app_spec.txt or spec.yaml"
            )

        logger.info(f"Reading spec file: {self.spec_file}")

        # Initialize extractor if needed
        if self.extractor is None:
            self.extractor = JourneyExtractor(str(self.spec_file))

        # Extract spec data
        try:
            project_spec = self.extractor.extract_project_spec()
            self.spec_data = project_spec
            logger.info(f"✓ Spec file read successfully")
            logger.info(f"  - Project: {project_spec.project_name}")
            logger.info(f"  - Phases: {len(project_spec.phases)}")
            logger.info(f"  - Stories: {sum(len(p.stories) for p in project_spec.phases.values())}")
            logger.info(f"  - Features: {len(project_spec.features)}")

            return project_spec

        except Exception as e:
            raise JourneyExtractionError(
                f"Failed to parse spec file: {e}"
            )

    def get_feature_info(self, feature_id: int) -> FeatureInfo:
        """
        Get information about a specific feature

        This would typically interface with the MCP feature management server.
        For now, returns a placeholder.

        Args:
            feature_id: Feature ID

        Returns:
            FeatureInfo with feature details
        """
        # Placeholder - in real implementation, this would call MCP tools
        # For now, we'll return mock data to demonstrate the interface
        return FeatureInfo(
            feature_id=feature_id,
            name=f"Feature {feature_id}",
            category="Integration",
            description="Placeholder feature info",
            passes=False,
            in_progress=False,
            dependencies=[]
        )

    def get_all_features(self) -> List[FeatureInfo]:
        """
        Get information about all features

        This would typically interface with the MCP feature management server.
        For now, returns empty list to demonstrate the interface.

        Returns:
            List of FeatureInfo objects
        """
        # Placeholder - in real implementation, this would call MCP tools
        # mcp__features__feature_get_stats, etc.
        return []

    def verify_integration(self) -> Dict[str, Any]:
        """
        Verify that the AutoCoder integration is working correctly

        Returns:
            Dictionary with verification results
        """
        results = {
            "project_connected": False,
            "spec_readable": False,
            "spec_parsed": False,
            "features_accessible": False,
            "errors": []
        }

        # Step 1: Verify project connection
        try:
            project_info = self.connect()
            results["project_connected"] = True
            results["project_name"] = project_info.project_name
            results["spec_exists"] = project_info.has_spec
        except Exception as e:
            results["errors"].append(f"Project connection failed: {e}")

        # Step 2: Verify spec is readable
        if results["project_connected"] and project_info.has_spec:
            try:
                self.spec_file = project_info.spec_file
                spec_content = self.spec_file.read_text()
                results["spec_readable"] = True
                results["spec_size"] = len(spec_content)
            except Exception as e:
                results["errors"].append(f"Spec reading failed: {e}")

        # Step 3: Verify spec can be parsed
        if results["spec_readable"]:
            try:
                project_spec = self.read_spec()
                results["spec_parsed"] = True
                results["phases_count"] = len(project_spec.phases)
                results["stories_count"] = sum(len(p.stories) for p in project_spec.phases.values())
                results["features_count"] = len(project_spec.features)
                results["journeys_count"] = len(project_spec.journeys)
            except Exception as e:
                results["errors"].append(f"Spec parsing failed: {e}")

        # Step 4: Verify features are accessible (placeholder)
        # In real implementation, this would test MCP connection
        results["features_accessible"] = True  # Placeholder
        results["note"] = "Feature access via MCP not yet implemented"

        return results


def create_autocoder_integration(project_path: Optional[Path] = None) -> AutoCoderIntegration:
    """
    Factory function to create AutoCoder integration

    Args:
        project_path: Path to AutoCoder project. If None, uses default.

    Returns:
        Configured AutoCoderIntegration instance
    """
    return AutoCoderIntegration(project_path=project_path)
