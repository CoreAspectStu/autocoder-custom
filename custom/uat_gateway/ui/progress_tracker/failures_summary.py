"""
Failures Summary Component for Progress Tracker Dashboard

This module provides comprehensive failure tracking and visualization for the
UAT Gateway progress tracker dashboard. It groups failures by category,
highlights critical failures, and provides multiple output formats.

Used in Feature #169: Progress tracker shows failures summary
"""

from typing import List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class FailureCategory(str, Enum):
    """
    Categories of test failures for grouping

    Categories help users understand patterns in failures and identify
    systemic issues (e.g., many selector failures might indicate
    selectors need updating).
    """
    SELECTOR = "selector"           # Element not found
    TIMEOUT = "timeout"             # Test exceeded time limit
    ASSERTION = "assertion"         # Assertion failed
    NETWORK = "network"             # Network/API error
    VISUAL = "visual"               # Visual regression detected
    ACCESSIBILITY = "accessibility" # A11y violation
    PERFORMANCE = "performance"     # Performance regression
    CRITICAL = "critical"           # Critical path failure
    OTHER = "other"                 # Other failures


class FailureSeverity(str, Enum):
    """
    Severity levels for failures

    Helps prioritize which failures to fix first.
    """
    CRITICAL = "critical"   # Blocks main user flow
    HIGH = "high"          # Important feature broken
    MEDIUM = "medium"      # Minor feature broken
    LOW = "low"            # Cosmetic issue


@dataclass
class FailureInfo:
    """
    Detailed information about a single test failure

    Captures all relevant information about a failure for debugging
    and analysis purposes.
    """
    test_id: str
    test_name: str
    journey_id: str
    scenario_id: str
    category: FailureCategory
    severity: FailureSeverity
    reason: str
    error_message: str
    timestamp: datetime
    stack_trace: str = ""

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization

        Returns:
            Dictionary representation of failure info
        """
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "journey_id": self.journey_id,
            "scenario_id": self.scenario_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "reason": self.reason,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
            "stack_trace": self.stack_trace
        }


@dataclass
class FailureGroup:
    """
    Group of failures by category

    Organizes failures of the same type together for better
    visualization and analysis.
    """
    category: FailureCategory
    count: int
    failures: List[FailureInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization

        Returns:
            Dictionary representation of failure group
        """
        return {
            "category": self.category.value,
            "category_label": self.category.value.replace("_", " ").title(),
            "count": self.count,
            "failures": [f.to_dict() for f in self.failures]
        }


@dataclass
class FailuresSummary:
    """
    Comprehensive failures summary for progress tracker dashboard

    Features:
    - Total failure count
    - Failures grouped by category
    - Critical failures highlighted separately
    - Recent failures list
    - Top failure reasons for quick insight

    Used in:
    - Progress tracker dashboard
    - Kanban card comments
    - Summary reports
    """

    total_failures: int
    critical_failures: List[FailureInfo] = field(default_factory=list)
    failure_groups: Dict[FailureCategory, FailureGroup] = field(default_factory=dict)
    recent_failures: List[FailureInfo] = field(default_factory=list)
    top_failure_reasons: List[tuple[str, int]] = field(default_factory=list)

    def get_critical_count(self) -> int:
        """
        Get count of critical failures

        Returns:
            Number of critical failures
        """
        return len(self.critical_failures)

    def get_grouped_failures(self) -> List[FailureGroup]:
        """
        Get failures grouped by category as list

        Returns:
            List of failure groups sorted by count (descending)
        """
        groups = list(self.failure_groups.values())
        groups.sort(key=lambda g: g.count, reverse=True)
        return groups

    def get_category_count(self, category: FailureCategory) -> int:
        """
        Get count of failures in a specific category

        Args:
            category: Failure category to query

        Returns:
            Number of failures in the category
        """
        group = self.failure_groups.get(category)
        return group.count if group else 0

    def to_dict(self) -> dict:
        """
        Convert to dictionary for JSON serialization

        Returns:
            Dictionary representation of failures summary
        """
        return {
            "total_failures": self.total_failures,
            "critical_count": self.get_critical_count(),
            "critical_failures": [f.to_dict() for f in self.critical_failures],
            "failure_groups": [g.to_dict() for g in self.get_grouped_failures()],
            "recent_failures": [f.to_dict() for f in self.recent_failures],
            "top_failure_reasons": self.top_failure_reasons
        }

    def to_html_summary(self) -> str:
        """
        Generate HTML for failures summary section of dashboard

        Returns:
            HTML string for rendering in web UI
        """
        html = ["<div class='failures-summary'>"]

        # Header with total count
        html.append(f"""
            <div class='failures-header'>
                <h3>❌ Failures Summary</h3>
                <span class='failure-count badge badge-danger'>{self.total_failures} Failed</span>
            </div>
        """)

        # Critical failures section
        if self.critical_failures:
            html.append("""
                <div class='critical-failures-section'>
                    <h4>🚨 Critical Failures</h4>
                    <div class='critical-failures-list'>
            """)
            for failure in self.critical_failures:
                html.append(f"""
                    <div class='critical-failure-item'>
                        <div class='failure-title'>{failure.test_name}</div>
                        <div class='failure-reason'>{failure.reason}</div>
                        <div class='failure-error'>{failure.error_message}</div>
                    </div>
                """)
            html.append("</div></div>")

        # Failure groups
        if self.failure_groups:
            html.append("<div class='failure-groups'><h4>Failures by Category</h4><div class='groups-grid'>")
            for group in self.get_grouped_failures():
                html.append(f"""
                    <div class='failure-group-card'>
                        <div class='group-header'>
                            <span class='group-icon'>{self._get_category_icon(group.category)}</span>
                            <span class='group-name'>{group.category.value.replace('_', ' ').title()}</span>
                        </div>
                        <div class='group-count'>{group.count} failures</div>
                    </div>
                """)
            html.append("</div></div>")

        # Top failure reasons
        if self.top_failure_reasons:
            html.append("<div class='top-reasons'><h4>Top Failure Reasons</h4><ul class='reasons-list'>")
            for reason, count in self.top_failure_reasons:
                html.append(f"<li><span class='reason'>{reason}</span> <span class='count'>({count})</span></li>")
            html.append("</ul></div>")

        html.append("</div>")
        return "\n".join(html)

    def to_markdown(self) -> str:
        """
        Generate markdown for failures summary

        Useful for:
        - Kanban card comments
        - Email notifications
        - Documentation

        Returns:
            Markdown string
        """
        lines = ["## ❌ Failures Summary", ""]
        lines.append(f"**Total Failures:** {self.total_failures}")
        lines.append("")

        # Critical failures
        if self.critical_failures:
            lines.append("### 🚨 Critical Failures")
            lines.append("")
            for failure in self.critical_failures:
                lines.append(f"- **{failure.test_name}**")
                lines.append(f"  - Reason: {failure.reason}")
                lines.append(f"  - Error: {failure.error_message}")
                lines.append("")

        # Failure groups
        if self.failure_groups:
            lines.append("### Failures by Category")
            lines.append("")
            for group in self.get_grouped_failures():
                icon = self._get_category_icon(group.category)
                lines.append(f"- {icon} **{group.category.value.replace('_', ' ').title()}**: {group.count}")
            lines.append("")

        # Top reasons
        if self.top_failure_reasons:
            lines.append("### Top Failure Reasons")
            lines.append("")
            for reason, count in self.top_failure_reasons[:10]:
                lines.append(f"{count+1}. {reason} ({count})")
            lines.append("")

        return "\n".join(lines)

    def get_css_styles(self) -> str:
        """
        Get CSS styles for failures summary display

        Returns:
            CSS string for styling the HTML output
        """
        return """
            .failures-summary {
                background: #fff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
            }

            .failures-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid #fee2e2;
            }

            .failures-header h3 {
                margin: 0;
                color: #991b1b;
                font-size: 1.5rem;
            }

            .badge-danger {
                background: #dc2626;
                color: white;
                padding: 4px 12px;
                border-radius: 20px;
                font-weight: 600;
                font-size: 0.875rem;
            }

            .critical-failures-section {
                background: #fef2f2;
                border: 1px solid #fecaca;
                border-radius: 6px;
                padding: 15px;
                margin-bottom: 20px;
            }

            .critical-failures-section h4 {
                margin: 0 0 15px 0;
                color: #991b1b;
                font-size: 1.125rem;
            }

            .critical-failure-item {
                background: white;
                border-left: 4px solid #dc2626;
                padding: 12px;
                margin-bottom: 10px;
                border-radius: 4px;
            }

            .failure-title {
                font-weight: 600;
                color: #1f2937;
                margin-bottom: 4px;
            }

            .failure-reason {
                color: #dc2626;
                font-size: 0.875rem;
                margin-bottom: 4px;
            }

            .failure-error {
                color: #6b7280;
                font-size: 0.8rem;
                font-family: monospace;
                background: #f3f4f6;
                padding: 4px 8px;
                border-radius: 4px;
            }

            .failure-groups {
                margin-bottom: 20px;
            }

            .failure-groups h4 {
                margin: 0 0 15px 0;
                color: #374151;
                font-size: 1.125rem;
            }

            .groups-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 12px;
            }

            .failure-group-card {
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                padding: 12px;
                transition: transform 0.2s, box-shadow 0.2s;
            }

            .failure-group-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }

            .group-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 8px;
            }

            .group-icon {
                font-size: 1.5rem;
            }

            .group-name {
                font-weight: 600;
                color: #374151;
            }

            .group-count {
                color: #6b7280;
                font-size: 0.875rem;
            }

            .top-reasons {
                margin-bottom: 0;
            }

            .top-reasons h4 {
                margin: 0 0 15px 0;
                color: #374151;
                font-size: 1.125rem;
            }

            .reasons-list {
                list-style: none;
                padding: 0;
                margin: 0;
            }

            .reasons-list li {
                display: flex;
                justify-content: space-between;
                padding: 8px 12px;
                background: #f9fafb;
                border-radius: 4px;
                margin-bottom: 6px;
            }

            .reasons-list .reason {
                color: #374151;
            }

            .reasons-list .count {
                color: #dc2626;
                font-weight: 600;
            }
        """

    def _get_category_icon(self, category: FailureCategory) -> str:
        """
        Get emoji icon for failure category

        Args:
            category: Failure category

        Returns:
            Emoji icon string
        """
        icons = {
            FailureCategory.SELECTOR: "🔍",
            FailureCategory.TIMEOUT: "⏱️",
            FailureCategory.ASSERTION: "❌",
            FailureCategory.NETWORK: "🌐",
            FailureCategory.VISUAL: "🎨",
            FailureCategory.ACCESSIBILITY: "♿",
            FailureCategory.PERFORMANCE: "📊",
            FailureCategory.CRITICAL: "🚨",
            FailureCategory.OTHER: "⚠️"
        }
        return icons.get(category, "⚠️")
