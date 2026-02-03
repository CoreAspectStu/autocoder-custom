"""
Results Exporter Component for Kanban Results Modal

This module provides export functionality for test results from the results modal.
Users can click an "Export Results" button to download test results as a JSON file
with complete execution data including test results, artifacts, console logs, and metadata.

Feature: #159 - Results modal has export results button
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from custom.uat_gateway.test_executor.test_executor import TestResult, ConsoleMessage


@dataclass
class ExportMetadata:
    """Metadata for the export file"""
    exported_at: str
    export_version: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    total_duration_ms: int
    has_artifacts: bool
    has_console_logs: bool


@dataclass
class ResultsModal:
    """
    Simulates a results modal that displays test results with an export button.

    This represents a UI modal that would show test execution results with
    tabs for different result types and an export button to download results.

    Feature: #159 - Results modal has export results button
    """
    test_results: List[TestResult] = field(default_factory=list)
    execution_metadata: Dict[str, Any] = field(default_factory=dict)
    console_logs: List[ConsoleMessage] = field(default_factory=list)

    def add_test_result(self, result: TestResult):
        """
        Add a test result to the modal

        Args:
            result: TestResult to add to the modal
        """
        self.test_results.append(result)

    def get_export_data(self) -> Dict[str, Any]:
        """
        Get data ready for export

        Returns a dictionary containing all test results, metadata, and logs
        in a format suitable for JSON serialization.

        Returns:
            Dictionary with export_metadata, execution_metadata, test_results, console_logs
        """
        # Calculate summary statistics
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.passed)
        failed_tests = total_tests - passed_tests
        total_duration = sum(r.duration_ms for r in self.test_results)

        # Prepare export data
        export_data = {
            "export_metadata": {
                "exported_at": datetime.now().isoformat(),
                "export_version": "1.0",
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "total_duration_ms": total_duration,
                "has_artifacts": any(r.artifacts for r in self.test_results),
                "has_console_logs": len(self.console_logs) > 0
            },
            "execution_metadata": self.execution_metadata,
            "test_results": [],
            "console_logs": []
        }

        # Add test results
        for result in self.test_results:
            result_data = {
                "test_name": result.test_name,
                "passed": result.passed,
                "duration_ms": result.duration_ms,
                "error_message": result.error_message,
                "error_stack": result.error_stack,
                "screenshot_path": result.screenshot_path,
                "video_path": result.video_path,
                "trace_path": result.trace_path,
                "retry_count": result.retry_count,
                "journey_id": result.journey_id,
                "artifacts": [a.to_dict() for a in result.artifacts]
            }
            export_data["test_results"].append(result_data)

        # Add console logs
        for log in self.console_logs:
            log_data = {
                "level": log.level,
                "text": log.text,
                "timestamp": log.timestamp,
                "url": log.url,
                "line": log.line,
                "column": log.column
            }
            export_data["console_logs"].append(log_data)

        return export_data

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Get summary statistics for the modal

        Returns:
            Dictionary with total, passed, failed, duration stats
        """
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.passed)
        failed_tests = total_tests - passed_tests
        total_duration = sum(r.duration_ms for r in self.test_results)

        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "total_duration_ms": total_duration,
            "pass_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
        }


class ResultsExporter:
    """
    Handles exporting test results from the results modal

    Simulates the export functionality that would be triggered by clicking
    the "Export Results" button in the UI modal.

    Feature: #159 - Results modal has export results button
    """

    def __init__(self, output_directory: str = None):
        """
        Initialize exporter

        Args:
            output_directory: Directory for exported files (temp dir if None)
        """
        if output_directory is None:
            self.output_directory = tempfile.mkdtemp()
        else:
            self.output_directory = Path(output_directory)
            self.output_directory.mkdir(parents=True, exist_ok=True)

    def export_results(
        self,
        modal: ResultsModal,
        filename: str = None
    ) -> str:
        """
        Export results from modal to JSON file

        Args:
            modal: ResultsModal containing test results
            filename: Optional filename (auto-generated if None)

        Returns:
            Path to the exported file
        """
        # Generate filename if not provided
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_results_export_{timestamp}.json"

        output_path = Path(self.output_directory) / filename

        # Get export data from modal
        export_data = modal.get_export_data()

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        return str(output_path)

    def verify_export_format(self, file_path: str) -> bool:
        """
        Verify exported file has correct JSON format

        Args:
            file_path: Path to exported file

        Returns:
            True if format is correct
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Verify required sections exist
            required_sections = ['export_metadata', 'execution_metadata', 'test_results', 'console_logs']
            for section in required_sections:
                if section not in data:
                    return False

            # Verify export metadata has required fields
            metadata = data['export_metadata']
            required_metadata_fields = [
                'exported_at', 'export_version', 'total_tests',
                'passed_tests', 'failed_tests'
            ]
            for field in required_metadata_fields:
                if field not in metadata:
                    return False

            return True

        except Exception as e:
            print(f"Error verifying export format: {e}")
            return False

    def verify_data_completeness(
        self,
        file_path: str,
        expected_test_count: int,
        expected_log_count: int
    ) -> bool:
        """
        Verify exported file includes all expected data

        Args:
            file_path: Path to exported file
            expected_test_count: Expected number of test results
            expected_log_count: Expected number of console logs

        Returns:
            True if all data is present
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Verify test results count
            actual_test_count = len(data.get('test_results', []))
            if actual_test_count != expected_test_count:
                print(f"Test count mismatch: expected {expected_test_count}, got {actual_test_count}")
                return False

            # Verify console logs count
            actual_log_count = len(data.get('console_logs', []))
            if actual_log_count != expected_log_count:
                print(f"Log count mismatch: expected {expected_log_count}, got {actual_log_count}")
                return False

            # Verify each test result has required fields
            for result in data['test_results']:
                required_fields = ['test_name', 'passed', 'duration_ms']
                for field in required_fields:
                    if field not in result:
                        print(f"Missing field {field} in test result")
                        return False

            return True

        except Exception as e:
            print(f"Error verifying data completeness: {e}")
            return False

    def get_export_button_html(self, modal_id: str = "results-modal") -> str:
        """
        Generate HTML for export button

        Args:
            modal_id: ID of the modal this button belongs to

        Returns:
            HTML string for export button
        """
        return f'''
        <button
            class="export-results-btn"
            data-modal-id="{modal_id}"
            title="Download results as JSON"
        >
            <span class="export-icon">⬇️</span>
            Export Results
        </button>
        '''

    def get_css_styles(self) -> str:
        """
        Get CSS styles for export button

        Returns:
            CSS string for styling the export button
        """
        return """
        .export-results-btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 20px;
            background: #3b82f6;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
        }

        .export-results-btn:hover {
            background: #2563eb;
        }

        .export-results-btn:active {
            transform: scale(0.98);
        }

        .export-results-btn:disabled {
            background: #9ca3af;
            cursor: not-allowed;
        }

        .export-icon {
            font-size: 16px;
        }

        /* Export button in modal header */
        .modal-header .export-results-btn {
            padding: 8px 16px;
            font-size: 13px;
        }

        /* Export button with loading state */
        .export-results-btn.loading {
            position: relative;
            color: transparent;
        }

        .export-results-btn.loading::after {
            content: '';
            position: absolute;
            width: 16px;
            height: 16px;
            top: 50%;
            left: 50%;
            margin-left: -8px;
            margin-top: -8px;
            border: 2px solid #ffffff;
            border-radius: 50%;
            border-top-color: transparent;
            animation: export-spin 0.8s linear infinite;
        }

        @keyframes export-spin {
            to {
                transform: rotate(360deg);
            }
        }
        """


def create_results_modal() -> ResultsModal:
    """
    Factory function to create a new ResultsModal

    Returns:
        New ResultsModal instance
    """
    return ResultsModal()


def create_results_exporter(output_directory: str = None) -> ResultsExporter:
    """
    Factory function to create a new ResultsExporter

    Args:
        output_directory: Optional output directory for exports

    Returns:
        New ResultsExporter instance
    """
    return ResultsExporter(output_directory=output_directory)
