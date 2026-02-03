"""
Results Importer Component for UAT Gateway

This module provides import functionality for test results, journeys, and scenarios.
Users can import previously exported test data to restore test results, journeys,
and scenarios from JSON files.

Feature: #301 - Import journey and test data
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from custom.uat_gateway.test_executor.test_executor import TestResult, ConsoleMessage
from custom.uat_gateway.journey_extractor.journey_extractor import Journey, Scenario, JourneyStep, ScenarioType


@dataclass
class ImportResult:
    """Result of an import operation"""
    success: bool
    imported_journeys: int = 0
    imported_scenarios: int = 0
    imported_test_results: int = 0
    imported_console_logs: int = 0
    duplicates_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class JourneyImportData:
    """Data structure for importing journeys"""
    journey_id: str
    journey_type: str
    name: str
    description: str
    steps: List[Dict[str, Any]]
    scenarios: List[Dict[str, Any]]
    priority: int = 5
    related_stories: List[str] = field(default_factory=list)


@dataclass
class ScenarioImportData:
    """Data structure for importing scenarios"""
    scenario_id: str
    scenario_type: str
    name: str
    description: str
    steps: List[Dict[str, Any]]
    error_type: Optional[str] = None
    acceptance_criteria: List[str] = field(default_factory=list)
    data_variations: List[Dict[str, Any]] = field(default_factory=list)
    setup_steps: List[Dict[str, Any]] = field(default_factory=list)
    cleanup_steps: List[Dict[str, Any]] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


class ResultsImporter:
    """
    Handles importing test results, journeys, and scenarios from JSON files

    Feature: #301 - Import journey and test data
    """

    def __init__(self):
        """Initialize the importer"""
        self.imported_journeys: Dict[str, Journey] = {}
        self.imported_scenarios: Dict[str, Scenario] = {}
        self.imported_results: List[TestResult] = []

    def import_from_file(self, file_path: str) -> ImportResult:
        """
        Import data from a JSON file

        Args:
            file_path: Path to the JSON file to import

        Returns:
            ImportResult with details of what was imported
        """
        result = ImportResult(success=False)

        try:
            # Read the file
            path = Path(file_path)
            if not path.exists():
                result.errors.append(f"File not found: {file_path}")
                return result

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate file structure
            if not self._validate_import_format(data, result):
                return result

            # Import journeys if present
            if 'journeys' in data:
                self._import_journeys(data['journeys'], result)

            # Import scenarios if present
            if 'scenarios' in data:
                self._import_scenarios(data['scenarios'], result)

            # Import test results if present
            if 'test_results' in data:
                self._import_test_results(data['test_results'], result)

            # Import console logs if present
            if 'console_logs' in data:
                self._import_console_logs(data['console_logs'], result)

            result.success = len(result.errors) == 0

        except json.JSONDecodeError as e:
            result.errors.append(f"Invalid JSON format: {e}")
        except Exception as e:
            result.errors.append(f"Import failed: {e}")

        return result

    def _validate_import_format(self, data: Dict[str, Any], result: ImportResult) -> bool:
        """
        Validate the imported data structure

        Args:
            data: Parsed JSON data
            result: ImportResult to record errors

        Returns:
            True if format is valid
        """
        # Must have at least one data section
        valid_sections = ['journeys', 'scenarios', 'test_results', 'console_logs']
        has_valid_section = any(section in data for section in valid_sections)

        if not has_valid_section:
            result.errors.append("No valid data sections found (journeys, scenarios, test_results, console_logs)")
            return False

        # If export_metadata exists, validate it
        if 'export_metadata' in data:
            metadata = data['export_metadata']
            required_fields = ['exported_at', 'export_version']
            for field in required_fields:
                if field not in metadata:
                    result.warnings.append(f"Missing metadata field: {field}")

        return True

    def _import_journeys(self, journeys_data: List[Dict[str, Any]], result: ImportResult) -> None:
        """
        Import journeys from data

        Args:
            journeys_data: List of journey dictionaries
            result: ImportResult to record statistics
        """
        for journey_dict in journeys_data:
            try:
                # Check for duplicate
                journey_id = journey_dict.get('journey_id')
                if not journey_id:
                    result.warnings.append("Journey missing journey_id, skipping")
                    continue

                # Only count as duplicate if already in our imported_journeys dict
                if journey_id in self.imported_journeys:
                    result.duplicates_skipped += 1
                    result.warnings.append(f"Duplicate journey skipped: {journey_id}")
                    continue

                # Convert steps
                steps = []
                for step_dict in journey_dict.get('steps', []):
                    step = JourneyStep(
                        step_id=step_dict.get('step_id', ''),
                        description=step_dict.get('description', ''),
                        action_type=step_dict.get('action_type', ''),
                        target=step_dict.get('target'),
                        expected_result=step_dict.get('expected_result')
                    )
                    steps.append(step)

                # Convert scenarios and track new ones
                scenarios = []
                new_scenario_count = 0
                for scenario_dict in journey_dict.get('scenarios', []):
                    scenario = self._create_scenario_from_dict(scenario_dict)
                    if scenario:
                        scenarios.append(scenario)
                        # Only add to imported_scenarios if not already there
                        if scenario.scenario_id not in self.imported_scenarios:
                            self.imported_scenarios[scenario.scenario_id] = scenario
                            new_scenario_count += 1

                # Create journey
                journey = Journey(
                    journey_id=journey_id,
                    journey_type=journey_dict.get('journey_type', 'user_journey'),
                    name=journey_dict.get('name', ''),
                    description=journey_dict.get('description', ''),
                    steps=steps,
                    scenarios=scenarios,
                    priority=journey_dict.get('priority', 5),
                    related_stories=journey_dict.get('related_stories', [])
                )

                self.imported_journeys[journey_id] = journey
                result.imported_journeys += 1
                result.imported_scenarios += new_scenario_count

            except Exception as e:
                result.errors.append(f"Error importing journey {journey_dict.get('journey_id', 'unknown')}: {e}")

    def _import_scenarios(self, scenarios_data: List[Dict[str, Any]], result: ImportResult) -> None:
        """
        Import standalone scenarios from data

        Args:
            scenarios_data: List of scenario dictionaries
            result: ImportResult to record statistics
        """
        for scenario_dict in scenarios_data:
            try:
                scenario_id = scenario_dict.get('scenario_id')
                if not scenario_id:
                    result.warnings.append("Scenario missing scenario_id, skipping")
                    continue

                if scenario_id in self.imported_scenarios:
                    result.duplicates_skipped += 1
                    result.warnings.append(f"Duplicate scenario skipped: {scenario_id}")
                    continue

                scenario = self._create_scenario_from_dict(scenario_dict)
                if scenario:
                    self.imported_scenarios[scenario_id] = scenario
                    result.imported_scenarios += 1

            except Exception as e:
                result.errors.append(f"Error importing scenario {scenario_dict.get('scenario_id', 'unknown')}: {e}")

    def _create_scenario_from_dict(self, scenario_dict: Dict[str, Any]) -> Optional[Scenario]:
        """
        Create a Scenario object from a dictionary

        Args:
            scenario_dict: Dictionary with scenario data

        Returns:
            Scenario object or None if invalid
        """
        try:
            # Convert scenario_type string to enum
            scenario_type_str = scenario_dict.get('scenario_type', 'happy_path')
            try:
                scenario_type = ScenarioType(scenario_type_str)
            except ValueError:
                scenario_type = ScenarioType.HAPPY_PATH

            # Convert steps
            def convert_steps(step_dicts):
                steps = []
                for step_dict in step_dicts:
                    step = JourneyStep(
                        step_id=step_dict.get('step_id', ''),
                        description=step_dict.get('description', ''),
                        action_type=step_dict.get('action_type', ''),
                        target=step_dict.get('target'),
                        expected_result=step_dict.get('expected_result')
                    )
                    steps.append(step)
                return steps

            steps = convert_steps(scenario_dict.get('steps', []))
            setup_steps = convert_steps(scenario_dict.get('setup_steps', []))
            cleanup_steps = convert_steps(scenario_dict.get('cleanup_steps', []))

            scenario = Scenario(
                scenario_id=scenario_dict.get('scenario_id', ''),
                scenario_type=scenario_type,
                name=scenario_dict.get('name', ''),
                description=scenario_dict.get('description', ''),
                steps=steps,
                error_type=scenario_dict.get('error_type'),
                acceptance_criteria=scenario_dict.get('acceptance_criteria', []),
                data_variations=scenario_dict.get('data_variations', []),
                setup_steps=setup_steps,
                cleanup_steps=cleanup_steps,
                dependencies=scenario_dict.get('dependencies', [])
            )

            return scenario

        except Exception as e:
            print(f"Error creating scenario from dict: {e}")
            return None

    def _import_test_results(self, results_data: List[Dict[str, Any]], result: ImportResult) -> None:
        """
        Import test results from data

        Args:
            results_data: List of test result dictionaries
            result: ImportResult to record statistics
        """
        from custom.uat_gateway.test_executor.test_executor import TestArtifact

        for result_dict in results_data:
            try:
                test_name = result_dict.get('test_name', '')

                # Convert artifacts
                artifacts = []
                for artifact_dict in result_dict.get('artifacts', []):
                    try:
                        # Parse timestamp
                        timestamp_str = artifact_dict.get('timestamp', '')
                        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()

                        # Create TestArtifact (ignore extra fields like size_bytes)
                        artifact = TestArtifact(
                            artifact_type=artifact_dict.get('artifact_type', 'unknown'),
                            path=artifact_dict.get('path', ''),
                            timestamp=timestamp,
                            test_name=test_name,
                            scenario_type=artifact_dict.get('scenario_type')
                        )
                        artifacts.append(artifact)
                    except Exception as e:
                        result.errors.append(f"Error importing artifact for {test_name}: {type(e).__name__}: {e}")
                        import traceback
                        traceback.print_exc()

                # Create TestResult
                test_result = TestResult(
                    test_name=test_name,
                    passed=result_dict.get('passed', True),
                    duration_ms=result_dict.get('duration_ms', 0),
                    error_message=result_dict.get('error_message'),
                    error_stack=result_dict.get('error_stack'),
                    screenshot_path=result_dict.get('screenshot_path'),
                    video_path=result_dict.get('video_path'),
                    trace_path=result_dict.get('trace_path'),
                    retry_count=result_dict.get('retry_count', 0),
                    journey_id=result_dict.get('journey_id'),
                    artifacts=artifacts
                )

                self.imported_results.append(test_result)
                result.imported_test_results += 1

            except Exception as e:
                result.errors.append(f"Error importing test result {result_dict.get('test_name', 'unknown')}: {e}")

    def _import_console_logs(self, logs_data: List[Dict[str, Any]], result: ImportResult) -> None:
        """
        Import console logs from data

        Args:
            logs_data: List of console log dictionaries
            result: ImportResult to record statistics
        """
        for log_dict in logs_data:
            try:
                log = ConsoleMessage(
                    level=log_dict.get('level', 'info'),
                    text=log_dict.get('text', ''),
                    timestamp=log_dict.get('timestamp', 0),
                    url=log_dict.get('url'),
                    line=log_dict.get('line'),
                    column=log_dict.get('column')
                )
                # Console logs are typically stored with test results
                # We're just counting them here
                result.imported_console_logs += 1

            except Exception as e:
                result.warnings.append(f"Error importing console log: {e}")

    def get_imported_journeys(self) -> List[Journey]:
        """
        Get all imported journeys

        Returns:
            List of imported Journey objects
        """
        return list(self.imported_journeys.values())

    def get_imported_scenarios(self) -> List[Scenario]:
        """
        Get all imported scenarios

        Returns:
            List of imported Scenario objects
        """
        return list(self.imported_scenarios.values())

    def get_imported_results(self) -> List[TestResult]:
        """
        Get all imported test results

        Returns:
            List of imported TestResult objects
        """
        return self.imported_results

    def get_journey_by_id(self, journey_id: str) -> Optional[Journey]:
        """
        Get an imported journey by ID

        Args:
            journey_id: Journey ID to look up

        Returns:
            Journey object or None if not found
        """
        return self.imported_journeys.get(journey_id)

    def get_scenario_by_id(self, scenario_id: str) -> Optional[Scenario]:
        """
        Get an imported scenario by ID

        Args:
            scenario_id: Scenario ID to look up

        Returns:
            Scenario object or None if not found
        """
        return self.imported_scenarios.get(scenario_id)


def create_results_importer() -> ResultsImporter:
    """
    Factory function to create a new ResultsImporter

    Returns:
        New ResultsImporter instance
    """
    return ResultsImporter()
