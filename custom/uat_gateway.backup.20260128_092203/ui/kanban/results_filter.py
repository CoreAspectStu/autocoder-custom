"""
Results Filter Component for Kanban Results Modal

This module provides filtering functionality for test results in the results modal.
Users can filter results by pass/fail status to focus on specific test outcomes.

Used in Feature #160: Results modal filters results by status
Used in Feature #278: Search finds test results by name
Used in Feature #283: Multiple filters work together (status + journey)
Used in Feature #291: Relative time display (2 hours ago)
"""

from typing import List, Literal, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from custom.uat_gateway.test_executor.test_executor import TestResult
from custom.uat_gateway.utils.time_formatter import format_relative_time, format_absolute_time, format_iso8601
# Feature #403: Date range validation
from custom.uat_gateway.utils.date_validator import DateRangeValidator, DateRangeValidationResult


class ResultStatus(str, Enum):
    """Status filter options for test results"""
    ALL = "all"
    PASSED = "passed"
    FAILED = "failed"


@dataclass
class FilterStats:
    """Statistics for filtered results"""
    total_count: int
    passed_count: int
    failed_count: int
    pass_rate: float  # Percentage (0-100)
    fail_rate: float  # Percentage (0-100)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "total_count": self.total_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "pass_rate": round(self.pass_rate, 2),
            "fail_rate": round(self.fail_rate, 2),
            "pass_rate_formatted": f"{self.pass_rate:.1f}%",
            "fail_rate_formatted": f"{self.fail_rate:.1f}%"
        }


class ResultsFilter:
    """
    Filter test results by status (pass/fail), search by name, and filter by journey

    Features:
    - Filter results by passed/failed status
    - Search results by test name (case-insensitive)
    - Filter results by journey ID (Feature #283)
    - Combine status, search, and journey filters
    - Calculate statistics for filtered view
    - Support for "all", "passed", "failed" filters
    - Efficient filtering with list comprehensions
    - HTML representation for modal display
    """

    def __init__(self, results: List[TestResult]):
        """
        Initialize results filter with test results

        Args:
            results: List of test results to filter
        """
        self.results = results
        self._current_filter: ResultStatus = ResultStatus.ALL
        self._current_search: str = ""  # Feature #278: Search term
        self._current_journey: Optional[str] = None  # Feature #283: Journey filter
        self._current_date_filter: tuple[Optional[datetime], Optional[datetime]] = (None, None)  # Feature #294: Date range

    def filter(self, status: ResultStatus) -> List[TestResult]:
        """
        Filter results by status

        Args:
            status: Status filter to apply (all, passed, failed)

        Returns:
            Filtered list of test results
        """
        self._current_filter = status

        if status == ResultStatus.ALL:
            return self.results
        elif status == ResultStatus.PASSED:
            return [r for r in self.results if r.passed]
        elif status == ResultStatus.FAILED:
            return [r for r in self.results if not r.passed]
        else:
            # Unknown filter - return all
            return self.results

    def get_passed(self) -> List[TestResult]:
        """
        Get only passed tests

        Returns:
            List of passed test results
        """
        return self.filter(ResultStatus.PASSED)

    def get_failed(self) -> List[TestResult]:
        """
        Get only failed tests

        Returns:
            List of failed test results
        """
        return self.filter(ResultStatus.FAILED)

    def get_all(self) -> List[TestResult]:
        """
        Get all tests (no filter)

        Returns:
            All test results
        """
        return self.filter(ResultStatus.ALL)

    # Feature #278: Search functionality
    def search(self, search_term: str) -> List[TestResult]:
        """
        Search test results by name (case-insensitive)

        Args:
            search_term: Search term to filter test names

        Returns:
            Filtered list of test results matching the search term
        """
        self._current_search = search_term

        if not search_term or search_term.strip() == "":
            return self.results

        search_lower = search_term.lower().strip()
        return [r for r in self.results if search_lower in r.test_name.lower()]

    def get_current_search(self) -> str:
        """
        Get the current search term

        Returns:
            Current search term
        """
        return self._current_search

    def clear_search(self) -> List[TestResult]:
        """
        Clear search and return all results

        Returns:
            All test results (no search filter applied)
        """
        self._current_search = ""
        return self.results

    # Feature #283: Journey filtering
    def filter_by_journey(self, journey_id: Optional[str]) -> List[TestResult]:
        """
        Filter results by journey ID

        Args:
            journey_id: Journey ID to filter by, or None to show all

        Returns:
            Filtered list of test results for the specified journey
        """
        self._current_journey = journey_id

        if not journey_id or journey_id.strip() == "":
            return self.results

        return [r for r in self.results if r.journey_id == journey_id]

    def get_current_journey(self) -> Optional[str]:
        """
        Get the current journey filter

        Returns:
            Current journey ID filter, or None if not set
        """
        return self._current_journey

    def clear_journey(self) -> List[TestResult]:
        """
        Clear journey filter and return all results

        Returns:
            All test results (no journey filter applied)
        """
        self._current_journey = None
        return self.results

    # Feature #294: Date range filtering
    # Feature #403: Date range validation
    def filter_by_date_range(self, start_date: Optional[datetime], end_date: Optional[datetime]) -> List[TestResult]:
        """
        Filter results by date range (Feature #294)

        Args:
            start_date: Start of date range (inclusive), or None for no start limit
            end_date: End of date range (inclusive), or None for no end limit

        Returns:
            Filtered list of test results within the date range

        Raises:
            ValueError: If start_date > end_date (invalid date range)
        """
        # Feature #403: Validate date range before filtering
        if start_date is not None and end_date is not None:
            if start_date > end_date:
                raise ValueError(
                    f"Invalid date range: start date ({start_date.strftime('%Y-%m-%d')}) "
                    f"must be before or equal to end date ({end_date.strftime('%Y-%m-%d')})"
                )

        self._current_date_filter = (start_date, end_date)

        # If both dates are None, return all results
        if start_date is None and end_date is None:
            return self.results

        # Filter by date range
        filtered = []
        for result in self.results:
            # Check if result has timestamp
            if not hasattr(result, 'timestamp') or result.timestamp is None:
                continue

            # Check start date
            if start_date is not None and result.timestamp < start_date:
                continue

            # Check end date
            if end_date is not None and result.timestamp > end_date:
                continue

            filtered.append(result)

        return filtered

    def get_current_date_filter(self) -> Optional[tuple[datetime, datetime]]:
        """
        Get the current date filter

        Returns:
            Tuple of (start_date, end_date) or None if no filter active
        """
        return self._current_date_filter

    def clear_date_filter(self) -> List[TestResult]:
        """
        Clear date filter and return all results

        Returns:
            All test results (no date filter applied)
        """
        self._current_date_filter = (None, None)
        return self.results

    def filter_by_date_and_status(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        status: ResultStatus
    ) -> List[TestResult]:
        """
        Apply both date range filter and status filter together (Feature #294)

        Args:
            start_date: Start of date range (inclusive), or None
            end_date: End of date range (inclusive), or None
            status: Status filter to apply

        Returns:
            Filtered list of test results matching both criteria
        """
        # Apply status filter first
        status_filtered = self.filter(status)

        # Then apply date filter
        if start_date is None and end_date is None:
            return status_filtered

        # Handle invalid range
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        # Filter by date range
        filtered = []
        for result in status_filtered:
            if not hasattr(result, 'timestamp') or result.timestamp is None:
                continue

            if start_date is not None and result.timestamp < start_date:
                continue

            if end_date is not None and result.timestamp > end_date:
                continue

            filtered.append(result)

        return filtered

    def filter_all_four(
        self,
        status: ResultStatus,
        journey_id: Optional[str],
        search_term: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> List[TestResult]:
        """
        Apply status, journey, search, and date filters together (Feature #294)

        Args:
            status: Status filter to apply
            journey_id: Journey ID to filter by (or None for all journeys)
            search_term: Search term to apply
            start_date: Start of date range (inclusive), or None
            end_date: End of date range (inclusive), or None

        Returns:
            Filtered list of test results matching all four criteria
        """
        # Apply status filter first
        filtered = self.filter(status)

        # Apply journey filter if provided
        if journey_id and journey_id.strip() != "":
            filtered = [r for r in filtered if r.journey_id == journey_id]

        # Apply search filter if provided
        if search_term and search_term.strip() != "":
            search_lower = search_term.lower().strip()
            filtered = [r for r in filtered if search_lower in r.test_name.lower()]

        # Apply date filter if provided
        if start_date is not None or end_date is not None:
            # Handle invalid range
            if start_date and end_date and start_date > end_date:
                start_date, end_date = end_date, start_date

            filtered = [
                r for r in filtered
                if hasattr(r, 'timestamp') and r.timestamp is not None
                and (start_date is None or r.timestamp >= start_date)
                and (end_date is None or r.timestamp <= end_date)
            ]

        return filtered

    def filter_status_and_journey(self, status: ResultStatus, journey_id: Optional[str]) -> List[TestResult]:
        """
        Apply both status filter and journey filter together (Feature #283)

        Args:
            status: Status filter to apply
            journey_id: Journey ID to filter by (or None for all journeys)

        Returns:
            Filtered list of test results matching both criteria
        """
        # First apply status filter
        status_filtered = self.filter(status)

        # Then apply journey filter if journey_id provided
        if not journey_id or journey_id.strip() == "":
            return status_filtered

        return [r for r in status_filtered if r.journey_id == journey_id]

    def filter_all_three(self, status: ResultStatus, journey_id: Optional[str], search_term: str) -> List[TestResult]:
        """
        Apply status, journey, and search filters together (Feature #283)

        Args:
            status: Status filter to apply
            journey_id: Journey ID to filter by (or None for all journeys)
            search_term: Search term to apply

        Returns:
            Filtered list of test results matching all three criteria
        """
        # Apply status filter first
        filtered = self.filter(status)

        # Apply journey filter if provided
        if journey_id and journey_id.strip() != "":
            filtered = [r for r in filtered if r.journey_id == journey_id]

        # Apply search filter if provided
        if search_term and search_term.strip() != "":
            search_lower = search_term.lower().strip()
            filtered = [r for r in filtered if search_lower in r.test_name.lower()]

        return filtered

    # Feature #327: Sorting functionality
    def sort(self, sort_by: str = "test_name", sort_order: str = "asc") -> List[TestResult]:
        """
        Sort results by specified field (Feature #327)

        Args:
            sort_by: Field to sort by (test_name, duration, timestamp)
            sort_order: Sort order ('asc' or 'desc')

        Returns:
            Sorted list of test results
        """
        # Determine sort direction
        reverse = (sort_order.lower() == "desc")

        # Map field names to result attributes
        field_map = {
            "test_name": "test_name",
            "name": "test_name",
            "duration": "duration_ms",
            "duration_ms": "duration_ms",
            "timestamp": "timestamp",
            "date": "timestamp",
        }

        field = field_map.get(sort_by, "test_name")

        try:
            # Sort by the specified field
            # Handle None values for timestamp
            sorted_results = sorted(
                self.results,
                key=lambda r: getattr(r, field, "") if getattr(r, field, None) is not None else "",
                reverse=reverse
            )
            return sorted_results
        except Exception as e:
            # If sorting fails, return unsorted results
            return self.results

    def filter_and_search(self, status: ResultStatus, search_term: str) -> List[TestResult]:
        """
        Apply both status filter and search filter together

        Args:
            status: Status filter to apply
            search_term: Search term to apply

        Returns:
            Filtered list of test results matching both criteria
        """
        # First apply status filter
        status_filtered = self.filter(status)

        # Then apply search filter if search term provided
        if not search_term or search_term.strip() == "":
            return status_filtered

        search_lower = search_term.lower().strip()
        return [r for r in status_filtered if search_lower in r.test_name.lower()]

    def get_stats(self, status: Optional[ResultStatus] = None) -> FilterStats:
        """
        Get statistics for filtered results

        Args:
            status: Optional status filter. If not provided, uses current filter.

        Returns:
            FilterStats object with counts and percentages
        """
        filtered = self.filter(status) if status else self.filter(self._current_filter)

        total = len(filtered)
        passed = sum(1 for r in filtered if r.passed)
        failed = total - passed

        pass_rate = (passed / total * 100) if total > 0 else 0.0
        fail_rate = (failed / total * 100) if total > 0 else 0.0

        return FilterStats(
            total_count=total,
            passed_count=passed,
            failed_count=failed,
            pass_rate=pass_rate,
            fail_rate=fail_rate
        )

    def get_current_filter(self) -> ResultStatus:
        """
        Get the currently active filter

        Returns:
            Current ResultStatus filter
        """
        return self._current_filter

    def to_html_summary(self) -> str:
        """
        Generate HTML summary of available filters

        Returns:
            HTML string with filter buttons and counts
        """
        stats_all = self.get_stats(ResultStatus.ALL)
        stats_passed = self.get_stats(ResultStatus.PASSED)
        stats_failed = self.get_stats(ResultStatus.FAILED)

        return f"""
        <div class="results-filter">
            <div class="results-filter__header">
                <span class="results-filter__title">Filter Results:</span>
            </div>
            <div class="results-filter__buttons">
                <button class="filter-btn filter-btn--all" data-filter="all">
                    All ({stats_all.total_count})
                </button>
                <button class="filter-btn filter-btn--passed" data-filter="passed">
                    ✅ Passed ({stats_passed.passed_count})
                </button>
                <button class="filter-btn filter-btn--failed" data-filter="failed">
                    ❌ Failed ({stats_failed.failed_count})
                </button>
            </div>
        </div>
        """

    def to_html_results(self, status: ResultStatus) -> str:
        """
        Generate HTML representation of filtered results

        Args:
            status: Status filter to apply

        Returns:
            HTML string with filtered results
        """
        filtered = self.filter(status)
        stats = self.get_stats(status)

        if not filtered:
            return self._empty_state_html(status)

        html_parts = ['<div class="filtered-results">']

        # Header
        html_parts.append('<div class="filtered-results__header">')
        filter_name = status.value.title()
        html_parts.append(f'<h4 class="filtered-results__title">{filter_name} Tests</h4>')
        html_parts.append(f'<span class="filtered-results__count">{len(filtered)} tests</span>')
        html_parts.append('</div>')

        # Results list
        html_parts.append('<div class="filtered-results__list">')
        for result in filtered:
            html_parts.append(self._result_to_html(result))
        html_parts.append('</div>')

        html_parts.append('</div>')
        return '\n'.join(html_parts)

    def _result_to_html(self, result: TestResult) -> str:
        """
        Convert a single test result to HTML

        Feature #291: Adds relative timestamp with hover tooltip for absolute time
        """
        status_class = "result-passed" if result.passed else "result-failed"
        status_icon = "✅" if result.passed else "❌"
        status_text = "PASSED" if result.passed else "FAILED"

        error_html = ""
        if not result.passed and result.error_message:
            error_html = f'<div class="result__error">{result.error_message}</div>'

        # Feature #291: Add timestamp display
        timestamp_html = ""
        if result.timestamp:
            relative_time = format_relative_time(result.timestamp)
            absolute_time = format_absolute_time(result.timestamp)
            iso_time = format_iso8601(result.timestamp)

            timestamp_html = f'''
                <time class="result__timestamp"
                      datetime="{iso_time}"
                      data-timestamp="{iso_time}"
                      title="{absolute_time}">
                    {relative_time}
                </time>
            '''

        return f'''
        <div class="result-item {status_class}">
            <div class="result__header">
                <span class="result__icon">{status_icon}</span>
                <span class="result__status">{status_text}</span>
                <span class="result__name">{result.test_name}</span>
                <span class="result__duration">{result.duration_ms}ms</span>
                {timestamp_html}
            </div>
            {error_html}
        </div>
        '''

    def _empty_state_html(self, status: ResultStatus, search_term: str = None) -> str:
        """
        Generate HTML for empty filter state

        Args:
            status: The filter status being applied
            search_term: Optional search term that caused empty results (Feature #280)

        Returns:
            HTML string for empty state display
        """
        # Feature #280: Check if this is a search-empty state
        if search_term and search_term.strip():
            return self._search_empty_html(search_term)

        # Default empty state for filter
        filter_name = status.value.title()
        icon = "📭" if status == ResultStatus.ALL else ("✅" if status == ResultStatus.PASSED else "❌")

        return f'''
        <div class="filtered-results filtered-results--empty">
            <div class="filtered-results__empty">
                <span class="filtered-results__empty-emoji">{icon}</span>
                <p class="filtered-results__empty-text">No {filter_name.lower()} tests found</p>
            </div>
        </div>
        '''

    def _search_empty_html(self, search_term: str) -> str:
        """
        Generate HTML for empty search results (Feature #280)

        When a search returns no results, show a helpful message with:
        - Clear indication no results were found
        - The search term used
        - Suggestion to try different search terms
        - Option to clear search

        Args:
            search_term: The search term that returned no results

        Returns:
            HTML string for empty search state
        """
        return f'''
        <div class="filtered-results filtered-results--empty">
            <div class="filtered-results__empty">
                <span class="filtered-results__empty-emoji">🔍</span>
                <p class="filtered-results__empty-text">No tests found matching "{search_term}"</p>
                <p class="filtered-results__empty-hint">Try different keywords or clear the search to see all tests</p>
                <button class="filtered-results__clear-btn" onclick="clearSearch()">
                    Clear Search
                </button>
            </div>
        </div>
        '''

    def to_html_results_with_search(self, status: ResultStatus, search_term: str = None) -> str:
        """
        Generate HTML representation of filtered results with search (Feature #280)

        Args:
            status: Status filter to apply
            search_term: Optional search term to apply

        Returns:
            HTML string with filtered results or empty state
        """
        # Apply both filter and search
        if search_term and search_term.strip():
            filtered = self.filter_and_search(status, search_term)
        else:
            filtered = self.filter(status)

        stats = self.get_stats(status)

        if not filtered:
            return self._empty_state_html(status, search_term)

        html_parts = ['<div class="filtered-results">']

        # Header with search info
        html_parts.append('<div class="filtered-results__header">')
        filter_name = status.value.title()
        html_parts.append(f'<h4 class="filtered-results__title">{filter_name} Tests</h4>')

        # Show search term if active
        if search_term and search_term.strip():
            html_parts.append(f'<span class="filtered-results__search">Search: "{search_term}"</span>')

        html_parts.append(f'<span class="filtered-results__count">{len(filtered)} tests</span>')
        html_parts.append('</div>')

        # Results list
        html_parts.append('<div class="filtered-results__list">')
        for result in filtered:
            html_parts.append(self._result_to_html(result))
        html_parts.append('</div>')

        html_parts.append('</div>')
        return '\n'.join(html_parts)


    def get_css_styles(self) -> str:
        """
        Get CSS styles for results filter

        Returns:
            CSS string for styling the results filter HTML
        """
        return """
        .results-filter {
            padding: 16px;
            background: #f5f5f5;
            border-radius: 8px;
            margin-bottom: 16px;
        }

        .results-filter__header {
            margin-bottom: 12px;
        }

        .results-filter__title {
            font-size: 14px;
            font-weight: 600;
            color: #333;
            margin: 0;
        }

        .results-filter__buttons {
            display: flex;
            gap: 8px;
        }

        .filter-btn {
            flex: 1;
            padding: 8px 16px;
            border: 1px solid #ddd;
            border-radius: 6px;
            background: white;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            transition: all 0.2s;
        }

        .filter-btn:hover {
            background: #e8e8e8;
        }

        .filter-btn--active {
            border-color: #3b82f6;
            background: #eff6ff;
            color: #3b82f6;
        }

        .filter-btn--passed:hover,
        .filter-btn--passed.filter-btn--active {
            border-color: #10b981;
            background: #ecfdf5;
            color: #10b981;
        }

        .filter-btn--failed:hover,
        .filter-btn--failed.filter-btn--active {
            border-color: #ef4444;
            background: #fef2f2;
            color: #ef4444;
        }

        .filtered-results {
            background: white;
            border-radius: 8px;
            overflow: hidden;
        }

        .filtered-results__header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            background: #f9fafb;
            border-bottom: 1px solid #e5e7eb;
        }

        .filtered-results__title {
            margin: 0;
            font-size: 14px;
            font-weight: 600;
            color: #374151;
        }

        .filtered-results__count {
            font-size: 12px;
            color: #6b7280;
        }

        .filtered-results__list {
            max-height: 400px;
            overflow-y: auto;
        }

        .result-item {
            padding: 12px 16px;
            border-bottom: 1px solid #e5e7eb;
        }

        .result-item:last-child {
            border-bottom: none;
        }

        .result-item:hover {
            background: #f9fafb;
        }

        .result__header {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .result__icon {
            font-size: 16px;
        }

        .result__status {
            font-size: 10px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 3px;
            text-transform: uppercase;
        }

        .result-passed .result__status {
            background: #d1fae5;
            color: #065f46;
        }

        .result-failed .result__status {
            background: #fee2e2;
            color: #991b1b;
        }

        .result__name {
            flex: 1;
            font-size: 13px;
            font-weight: 500;
            color: #374151;
        }

        .result__duration {
            font-size: 11px;
            color: #9ca3af;
        }

        .result__error {
            margin-top: 8px;
            padding: 8px;
            background: #fef2f2;
            border-left: 3px solid #ef4444;
            border-radius: 4px;
            font-size: 12px;
            color: #991b1b;
            font-family: 'Monaco', 'Menlo', monospace;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .filtered-results--empty {
            padding: 40px;
            text-align: center;
        }

        .filtered-results__empty-emoji {
            font-size: 48px;
            display: block;
            margin-bottom: 12px;
        }

        .filtered-results__empty-text {
            color: #9ca3af;
            margin: 0;
            font-size: 14px;
        }

        /* Scrollbar styling */
        .filtered-results__list::-webkit-scrollbar {
            width: 8px;
        }

        .filtered-results__list::-webkit-scrollbar-track {
            background: #f1f1f1;
        }

        .filtered-results__list::-webkit-scrollbar-thumb {
            background: #c1c1c1;
            border-radius: 4px;
        }

        .filtered-results__list::-webkit-scrollbar-thumb:hover {
            background: #a8a8a8;
        }
        """

    def to_markdown(self, status: ResultStatus) -> str:
        """
        Generate markdown representation of filtered results

        Useful for embedding in Kanban card comments

        Args:
            status: Status filter to apply

        Returns:
            Markdown string with filtered results
        """
        filtered = self.filter(status)

        if not filtered:
            return f"## {status.title()} Tests\n\nNo tests found."

        lines = [f"## {status.title()} Tests\n"]
        lines.append(f"**Total:** {len(filtered)} tests\n")

        for result in filtered:
            status_icon = "✅" if result.passed else "❌"
            lines.append(f"### {status_icon} {result.test_name}")
            lines.append(f"- **Status:** {'PASSED' if result.passed else 'FAILED'}")
            lines.append(f"- **Duration:** {result.duration_ms}ms")

            if not result.passed and result.error_message:
                lines.append(f"- **Error:** `{result.error_message}`")

            lines.append("")

        return '\n'.join(lines)

    def get_javascript(self) -> str:
        """
        Get JavaScript code for dynamic relative time updates (Feature #291)

        Returns:
            JavaScript code string that updates relative timestamps
        """
        return """
        // Feature #291: Relative Time Display
        (function() {
            'use strict';

            /**
             * Format a timestamp as relative time
             * Mirrors the Python logic in time_formatter.py
             */
            function formatRelativeTime(timestamp, now) {
                const delta = now - timestamp;
                const seconds = Math.floor(delta / 1000);

                // Less than a minute
                if (seconds < 60) {
                    if (seconds < 10) return 'just now';
                    return seconds + ' seconds ago';
                }

                // Less than an hour
                const minutes = Math.floor(seconds / 60);
                if (minutes < 60) {
                    if (minutes === 1) return '1 minute ago';
                    return minutes + ' minutes ago';
                }

                // Less than a day
                const hours = Math.floor(minutes / 60);
                if (hours < 24) {
                    if (hours === 1) return '1 hour ago';
                    return hours + ' hours ago';
                }

                // Less than a week
                const days = Math.floor(hours / 24);
                if (days < 7) {
                    if (days === 1) {
                        // Return "yesterday at HH:MM AM/PM"
                        const timeStr = timestamp.toLocaleTimeString('en-US', {
                            hour: 'numeric',
                            minute: '2-digit',
                            hour12: true
                        });
                        return 'yesterday at ' + timeStr;
                    }
                    return days + ' days ago';
                }

                // Less than a month
                const weeks = Math.floor(days / 7);
                if (weeks < 4) {
                    if (weeks === 1) return '1 week ago';
                    return weeks + ' weeks ago';
                }

                // Less than a year
                const months = Math.floor(days / 30);
                if (months < 12) {
                    if (months === 1) return '1 month ago';
                    return months + ' months ago';
                }

                // More than a year
                const years = Math.floor(days / 365);
                if (years === 1) return '1 year ago';
                return years + ' years ago';
            }

            /**
             * Update all relative time elements on the page
             */
            function updateRelativeTimes() {
                const timeElements = document.querySelectorAll('[data-timestamp]');
                const now = new Date();

                timeElements.forEach(function(element) {
                    const timestampStr = element.getAttribute('data-timestamp');
                    if (!timestampStr) return;

                    const timestamp = new Date(timestampStr);

                    // Check if date is valid
                    if (isNaN(timestamp.getTime())) return;

                    const relativeTime = formatRelativeTime(timestamp, now);
                    element.textContent = relativeTime;
                });
            }

            /**
             * Initialize relative time updates
             */
            function init() {
                // Initial update
                updateRelativeTimes();

                // Update every minute (60000 ms)
                setInterval(updateRelativeTimes, 60000);

                console.log('Relative time display initialized (Feature #291)');
            }

            // Initialize when DOM is ready
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', init);
            } else {
                init();
            }

            // Also re-initialize when modal is opened (in case content is dynamically loaded)
            window.addEventListener('modalOpened', updateRelativeTimes);

            // Expose function globally for manual updates if needed
            window.updateRelativeTimes = updateRelativeTimes;
        })();
        """
