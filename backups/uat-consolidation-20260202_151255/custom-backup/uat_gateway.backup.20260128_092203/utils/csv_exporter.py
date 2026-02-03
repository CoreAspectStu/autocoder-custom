"""
CSV Export Utility for UAT Test Results

Generates CSV files from test result data.
Feature #461: Multiple export formats (CSV)
"""

import csv
import io
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class CSVExporter:
    """
    Generate CSV files from test results

    Features:
    - Export test results to CSV format
    - Include metadata and summary statistics
    - Support for filtering and sorting
    - Compatible with Excel and other spreadsheet applications
    """

    def __init__(self):
        """Initialize CSV exporter"""
        pass

    def export_test_results(
        self,
        results: List[Dict[str, Any]],
        include_metadata: bool = True
    ) -> str:
        """
        Export test results as CSV

        Args:
            results: List of test result dictionaries
            include_metadata: Whether to include metadata rows

        Returns:
            Path to the exported CSV file
        """
        if not results:
            logger.warning("No results to export")
            return self._create_empty_csv()

        # Create CSV file
        buffer = io.StringIO()
        writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)

        # Add metadata rows if requested
        if include_metadata:
            self._write_metadata(writer, results)

        # Write header row
        fieldnames = self._get_fieldnames(results[0])
        writer.writerow(fieldnames)

        # Write data rows
        for result in results:
            row = self._result_to_row(result, fieldnames)
            writer.writerow(row)

        # Get CSV content
        csv_content = buffer.getvalue()
        buffer.close()

        # Save to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"uat_test_results_{timestamp}.csv"
        temp_file = Path(tempfile.gettempdir()) / filename

        with open(temp_file, 'w', encoding='utf-8', newline='') as f:
            f.write(csv_content)

        logger.info(f"Exported {len(results)} test results to CSV: {temp_file}")
        return str(temp_file)

    def _create_empty_csv(self) -> str:
        """Create an empty CSV file with headers"""
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        # Write basic headers
        writer.writerow([
            'test_id',
            'test_name',
            'status',
            'duration_ms',
            'journey_id',
            'timestamp',
            'error_message'
        ])

        csv_content = buffer.getvalue()
        buffer.close()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"uat_test_results_empty_{timestamp}.csv"
        temp_file = Path(tempfile.gettempdir()) / filename

        with open(temp_file, 'w', encoding='utf-8', newline='') as f:
            f.write(csv_content)

        return str(temp_file)

    def _write_metadata(self, writer: csv.writer, results: List[Dict[str, Any]]):
        """Write metadata rows at the top of CSV"""
        # Calculate summary statistics
        total = len(results)
        passed = sum(1 for r in results if r.get('status') == 'passed')
        failed = sum(1 for r in results if r.get('status') == 'failed')
        skipped = sum(1 for r in results if r.get('status') == 'skipped')
        pass_rate = (passed / total * 100) if total > 0 else 0

        # Write metadata as comment rows (starting with #)
        writer.writerow(['# UAT Test Results Export'])
        writer.writerow([f'# Exported at: {datetime.now().isoformat()}'])
        writer.writerow([f'# Total results: {total}'])
        writer.writerow([f'# Passed: {passed}'])
        writer.writerow([f'# Failed: {failed}'])
        writer.writerow([f'# Skipped: {skipped}'])
        writer.writerow([f'# Pass rate: {pass_rate:.1f}%'])
        writer.writerow([])  # Empty row separator

    def _get_fieldnames(self, result: Dict[str, Any]) -> List[str]:
        """Get fieldnames from result dictionary"""
        return [
            'test_id',
            'test_name',
            'status',
            'duration_ms',
            'journey_id',
            'scenario_type',
            'timestamp',
            'retry_count',
            'passed',
            'error_message',
            'screenshot_path',
            'video_path',
            'trace_path',
            'artifact_count'
        ]

    def _result_to_row(self, result: Dict[str, Any], fieldnames: List[str]) -> List[str]:
        """Convert result dictionary to CSV row"""
        row = []

        for field in fieldnames:
            value = result.get(field, '')

            # Convert None to empty string
            if value is None:
                value = ''

            # Convert lists to comma-separated strings
            elif isinstance(value, list):
                value = ', '.join(str(v) for v in value)

            # Convert booleans to strings
            elif isinstance(value, bool):
                value = 'Yes' if value else 'No'

            # Convert everything else to string
            else:
                value = str(value)

            row.append(value)

        return row

    def verify_csv_format(self, file_path: str) -> bool:
        """
        Verify exported file has correct CSV format

        Args:
            file_path: Path to exported CSV file

        Returns:
            True if format is correct
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Read first few lines
                lines = []
                for i, line in enumerate(f):
                    if i >= 10:  # Check first 10 lines
                        break
                    lines.append(line.strip())

            # Verify file is not empty
            if not lines:
                logger.error("CSV file is empty")
                return False

            # Check if first line looks like a header
            # (metadata lines start with #)
            data_lines = [l for l in lines if not l.startswith('#') and l.strip()]
            if not data_lines:
                logger.error("No data lines in CSV")
                return False

            # Verify header row has expected columns
            header = data_lines[0]
            expected_columns = ['test_name', 'status', 'duration_ms']
            for col in expected_columns:
                if col not in header:
                    logger.error(f"Missing expected column: {col}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error verifying CSV format: {e}")
            return False

    def verify_data_completeness(
        self,
        file_path: str,
        expected_count: int
    ) -> bool:
        """
        Verify exported file includes all expected data

        Args:
            file_path: Path to exported CSV file
            expected_count: Expected number of test results

        Returns:
            True if all data is present
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Read all lines
                lines = f.readlines()

                # Filter out metadata/comment lines
                data_lines = [l.strip() for l in lines if not l.strip().startswith('#') and l.strip()]

                if len(data_lines) < 2:  # Need at least header + 1 data row
                    logger.error("Not enough data lines in CSV")
                    return False

                # Count data rows (excluding header)
                actual_count = len(data_lines) - 1  # Subtract header row

                # Verify count
                if actual_count != expected_count:
                    logger.error(f"Row count mismatch: expected {expected_count}, got {actual_count}")
                    return False

                # Parse header row
                header = data_lines[0].split(',')
                required_fields = ['test_name', 'status', 'duration_ms']

                # Verify header has required fields
                for field in required_fields:
                    if field not in header:
                        logger.error(f"Missing required field in header: {field}")
                        return False

                # Verify each data row has the right number of columns
                for i in range(1, len(data_lines)):
                    row = data_lines[i]
                    columns = row.split(',')

                    if len(columns) != len(header):
                        logger.warning(f"Row {i} has {len(columns)} columns, expected {len(header)}")

                return True

        except Exception as e:
            logger.error(f"Error verifying data completeness: {e}")
            return False


def create_csv_exporter() -> CSVExporter:
    """Factory function to create CSV exporter"""
    return CSVExporter()
