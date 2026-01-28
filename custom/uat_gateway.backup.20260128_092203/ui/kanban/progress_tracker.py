"""
Progress Tracker - Overall UAT Statistics Dashboard

This module provides a dashboard component that displays aggregate statistics
about UAT testing progress across all journeys and scenarios.

Feature: #167 - Progress tracker shows overall stats
Feature: #171 - Progress tracker has quick navigation
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum


class ExecutionStage(Enum):
    """Execution stages for progress tracking"""
    NOT_STARTED = "not_started"
    PARSING = "parsing"
    EXTRACTION = "extraction"
    GENERATION = "generation"
    EXECUTION = "execution"
    PROCESSING = "processing"
    UPDATING = "updating"
    COMPLETE = "complete"
    FAILED = "failed"


# ============================================================================
# Navigation Support (Feature #171)
# ============================================================================

class NavigationLinkType(str, Enum):
    """Types of navigation links"""
    JOURNEY = "journey"  # Link to journey details page
    RESULT = "result"    # Link to results page
    MODAL = "modal"      # Link to open modal overlay


@dataclass
class NavigationLink:
    """
    Represents a clickable navigation link in the UI.

    This simulates what would be rendered as an <a> tag or onClick handler
    in the actual HTML/React interface.

    Feature #171: Quick navigation from progress tracker
    """
    url: str
    label: str
    link_type: Union[NavigationLinkType, str]

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for JSON serialization"""
        return {
            "url": self.url,
            "label": self.label,
            "type": str(self.link_type)
        }

    def __repr__(self) -> str:
        return f"NavigationLink(url={self.url}, label={self.label}, type={self.link_type})"


class ClickableJourneyCard:
    """
    Represents a journey card with clickable navigation elements.

    This extends the basic journey card display to include interactive
    elements for navigation to journey details and result views.

    Feature #171: Quick navigation from progress tracker
    """

    def __init__(self, journey_stats: 'JourneyStats'):
        """
        Initialize clickable journey card

        Args:
            journey_stats: Journey statistics to display
        """
        self.journey_stats = journey_stats
        self.navigation_links: List[NavigationLink] = []

    def add_navigation_link(self, url: str, label: str, link_type: Union[NavigationLinkType, str]):
        """
        Add a navigation link to this card

        Args:
            url: Target URL or route
            label: Display text
            link_type: Type of link ('journey', 'result', 'modal')
        """
        link = NavigationLink(url=url, label=label, link_type=link_type)
        self.navigation_links.append(link)
        return link

    def has_journey_link(self) -> bool:
        """Check if card has a journey navigation link"""
        return any(str(link.link_type) == 'journey' for link in self.navigation_links)

    def has_result_links(self) -> bool:
        """Check if card has result navigation links"""
        return any(str(link.link_type) in ['result', 'modal'] for link in self.navigation_links)

    def get_journey_link(self) -> Optional[NavigationLink]:
        """Get the journey navigation link"""
        for link in self.navigation_links:
            if str(link.link_type) == 'journey':
                return link
        return None

    def get_result_links(self) -> List[NavigationLink]:
        """Get all result navigation links"""
        return [link for link in self.navigation_links if str(link.link_type) in ['result', 'modal']]

    def to_html(self) -> str:
        """
        Generate HTML for clickable journey card

        Returns:
            HTML string with navigation links
        """
        js = self.journey_stats
        status_class = f"status-{js.status}"

        # Generate navigation links HTML
        links_html = []
        for link in self.navigation_links:
            if str(link.link_type) == 'journey':
                links_html.append(f'''
                <a href="{link.url}" class="nav-link nav-journey" data-link-type="journey">
                    {link.label} →
                </a>
                ''')
            elif str(link.link_type) == 'result':
                links_html.append(f'''
                <a href="{link.url}" class="nav-link nav-result" data-link-type="result">
                    {link.label}
                </a>
                ''')
            elif str(link.link_type) == 'modal':
                links_html.append(f'''
                <button class="nav-link nav-modal" data-modal="{link.url}" data-link-type="modal">
                    {link.label}
                </button>
                ''')

        links_section = ''.join(links_html) if links_html else ''

        html = f'''
        <div class="journey-card {status_class} clickable" data-journey-id="{js.journey_id}">
            <div class="journey-header">
                <span class="journey-name">{js.journey_name}</span>
                <span class="journey-status">{js.status.upper()}</span>
            </div>
            <div class="journey-progress">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {js.completion_percentage:.1f}%"></div>
                </div>
                <div class="progress-stats">
                    <span>{js.completed_scenarios}/{js.total_scenarios} scenarios</span>
                    <span>{js.pass_rate:.1f}% pass rate</span>
                </div>
            </div>
            {f'<div class="journey-navigation">{links_section}</div>' if links_section else ''}
        </div>
        '''
        return html


@dataclass
class JourneyStats:
    """Statistics for a single journey"""
    journey_id: str
    journey_name: str
    total_scenarios: int
    completed_scenarios: int
    passed_scenarios: int
    failed_scenarios: int

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage"""
        if self.total_scenarios == 0:
            return 0.0
        return (self.completed_scenarios / self.total_scenarios) * 100

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate"""
        if self.completed_scenarios == 0:
            return 0.0
        return (self.passed_scenarios / self.completed_scenarios) * 100

    @property
    def status(self) -> str:
        """Get journey status"""
        if self.completed_scenarios == 0:
            return "pending"
        elif self.failed_scenarios > 0:
            return "failed"
        else:
            return "passed"


@dataclass
class OverallStats:
    """Overall statistics across all journeys"""
    total_journeys: int = 0
    total_scenarios: int = 0
    total_tests: int = 0
    completed_scenarios: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    execution_stage: ExecutionStage = ExecutionStage.NOT_STARTED
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @property
    def completion_percentage(self) -> float:
        """Calculate overall completion percentage"""
        if self.total_scenarios == 0:
            return 0.0
        return (self.completed_scenarios / self.total_scenarios) * 100

    @property
    def pass_rate(self) -> float:
        """Calculate overall pass rate"""
        if self.total_tests == 0:
            return 0.0
        return (self.passed_tests / self.total_tests) * 100

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate execution duration"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        elif self.start_time:
            return (datetime.now() - self.start_time).total_seconds()
        return None

    @property
    def estimated_remaining_seconds(self) -> Optional[float]:
        """Estimate remaining time based on progress"""
        if not self.start_time or self.completion_percentage == 0:
            return None

        elapsed = (datetime.now() - self.start_time).total_seconds()
        progress_ratio = self.completion_percentage / 100.0

        if progress_ratio > 0:
            total_estimated = elapsed / progress_ratio
            return total_estimated - elapsed
        return None


@dataclass
class FailureSummary:
    """Summary of test failures"""
    total_failures: int = 0
    critical_failures: int = 0
    journeys_with_failures: int = 0
    failure_details: List[Dict[str, Any]] = field(default_factory=list)

    def add_failure(self, journey_id: str, scenario_id: str, error: str):
        """Add a failure to the summary"""
        self.total_failures += 1
        self.failure_details.append({
            "journey_id": journey_id,
            "scenario_id": scenario_id,
            "error": error
        })


class ProgressTracker:
    """
    Progress tracker dashboard for UAT testing

    Displays overall statistics including:
    - Total journeys and scenarios
    - Pass rate across all tests
    - Execution progress and stage
    - Per-journey progress cards
    - Failure summary
    - Estimated time remaining
    """

    def __init__(self):
        """Initialize progress tracker"""
        self.overall_stats = OverallStats()
        self.journey_stats: Dict[str, JourneyStats] = {}
        self.failure_summary = FailureSummary()
        self.execution_history: List[Dict[str, Any]] = []

    def initialize_from_orchestrator_result(self, result: Dict[str, Any]):
        """
        Initialize tracker from orchestrator result

        Args:
            result: Orchestrator result dictionary
        """
        # Update overall stats
        self.overall_stats.total_journeys = result.get("total_journeys", 0)
        self.overall_stats.total_scenarios = result.get("total_scenarios", 0)
        self.overall_stats.total_tests = result.get("total_tests", 0)
        self.overall_stats.passed_tests = result.get("passed_tests", 0)
        self.overall_stats.failed_tests = result.get("failed_tests", 0)
        self.overall_stats.completed_scenarios = result.get("completed_scenarios", 0)

        # Set execution stage
        if result.get("success"):
            self.overall_stats.execution_stage = ExecutionStage.COMPLETE
        elif result.get("errors"):
            self.overall_stats.execution_stage = ExecutionStage.FAILED
        else:
            self.overall_stats.execution_stage = ExecutionStage.EXECUTION

        # Set timestamps
        if "start_time" in result:
            self.overall_stats.start_time = datetime.fromisoformat(result["start_time"])
        if "end_time" in result:
            self.overall_stats.end_time = datetime.fromisoformat(result["end_time"])

    def add_journey_stats(self, journey_stats: JourneyStats):
        """
        Add or update journey statistics

        Args:
            journey_stats: Journey statistics to add
        """
        self.journey_stats[journey_stats.journey_id] = journey_stats

        # Update overall stats
        self.overall_stats.total_journeys = len(self.journey_stats)
        self.overall_stats.total_scenarios = sum(
            js.total_scenarios for js in self.journey_stats.values()
        )
        self.overall_stats.completed_scenarios = sum(
            js.completed_scenarios for js in self.journey_stats.values()
        )

    def update_execution_stage(self, stage: ExecutionStage):
        """
        Update execution stage

        Args:
            stage: New execution stage
        """
        self.overall_stats.execution_stage = stage

        # Record in history
        self.execution_history.append({
            "timestamp": datetime.now().isoformat(),
            "stage": stage.value,
            "completion": self.overall_stats.completion_percentage
        })

    def get_overall_stats(self) -> OverallStats:
        """
        Get overall statistics

        Returns:
            OverallStats object with current statistics
        """
        return self.overall_stats

    def get_journey_stats(self, journey_id: str) -> Optional[JourneyStats]:
        """
        Get statistics for a specific journey

        Args:
            journey_id: Journey identifier

        Returns:
            JourneyStats if found, None otherwise
        """
        return self.journey_stats.get(journey_id)

    def get_all_journey_stats(self) -> List[JourneyStats]:
        """
        Get statistics for all journeys

        Returns:
            List of JourneyStats objects
        """
        return list(self.journey_stats.values())

    def get_failed_journeys(self) -> List[JourneyStats]:
        """
        Get journeys that have failures

        Returns:
            List of JourneyStats with failed scenarios
        """
        return [js for js in self.journey_stats.values() if js.failed_scenarios > 0]

    def to_html_dashboard(self, clickable: bool = False) -> str:
        """
        Generate HTML dashboard

        Args:
            clickable: If True, include navigation links in journey cards (Feature #171)

        Returns:
            HTML string for dashboard display
        """
        stats = self.overall_stats
        failure_count = len(self.get_failed_journeys())

        html = f"""
<div class="progress-tracker-dashboard">
    <h2>📊 UAT Progress Tracker</h2>

    <!-- Overall Stats -->
    <div class="overall-stats">
        <div class="stat-card">
            <div class="stat-icon">🎭</div>
            <div class="stat-value">{stats.total_journeys}</div>
            <div class="stat-label">Total Journeys</div>
        </div>

        <div class="stat-card">
            <div class="stat-icon">🧪</div>
            <div class="stat-value">{stats.total_scenarios}</div>
            <div class="stat-label">Total Scenarios</div>
        </div>

        <div class="stat-card">
            <div class="stat-icon">✅</div>
            <div class="stat-value">{stats.pass_rate:.1f}%</div>
            <div class="stat-label">Pass Rate</div>
        </div>

        <div class="stat-card">
            <div class="stat-icon">⏱️</div>
            <div class="stat-value">{stats.completion_percentage:.1f}%</div>
            <div class="stat-label">Execution Progress</div>
        </div>

        <div class="stat-card">
            <div class="stat-icon">❌</div>
            <div class="stat-value">{stats.failed_tests}</div>
            <div class="stat-label">Failed Tests</div>
        </div>
    </div>

    <!-- Execution Stage -->
    <div class="execution-stage">
        <span class="stage-label">Stage:</span>
        <span class="stage-value stage-{stats.execution_stage.value}">
            {stats.execution_stage.value.replace('_', ' ').title()}
        </span>
    </div>

    <!-- Failures Summary -->
    {self._generate_failures_html() if failure_count > 0 else ''}

    <!-- Journey Progress Cards -->
    <div class="journey-progress-cards">
        <h3>Journey Progress</h3>
        {self._generate_journey_cards_html(clickable=clickable)}
    </div>
</div>
"""
        return html

    def _generate_failures_html(self) -> str:
        """Generate failures summary HTML"""
        failed_journeys = self.get_failed_journeys()
        if not failed_journeys:
            return ""

        failure_items = []
        for js in failed_journeys[:5]:  # Show top 5 failures
            failure_items.append(f"""
            <div class="failure-item">
                <div class="failure-journey">{js.journey_name}</div>
                <div class="failure-count">{js.failed_scenarios} failures</div>
            </div>
            """)

        return f"""
    <div class="failures-summary">
        <h3>⚠️ Failures Summary</h3>
        <div class="failure-items">
            {''.join(failure_items)}
        </div>
    </div>
    """

    def _generate_journey_cards_html(self, clickable: bool = False) -> str:
        """
        Generate journey progress cards HTML

        Args:
            clickable: If True, generate clickable cards with navigation links (Feature #171)

        Returns:
            HTML string with journey cards
        """
        if not self.journey_stats:
            return '<p class="no-data">No journeys tracked yet</p>'

        cards = []
        for js in self.journey_stats.values():
            if clickable:
                # Use ClickableJourneyCard for navigation (Feature #171)
                card = ClickableJourneyCard(js)

                # Add journey details link
                card.add_navigation_link(
                    url=f"/journeys/{js.journey_id}",
                    label="View Details",
                    link_type=NavigationLinkType.JOURNEY
                )

                # Add result link based on status
                if js.failed_scenarios > 0:
                    # Link to failure modal for failed journeys
                    card.add_navigation_link(
                        url=f"/modals/{js.journey_id}/failures",
                        label=f"View {js.failed_scenarios} Failures",
                        link_type=NavigationLinkType.MODAL
                    )
                elif js.completed_scenarios > 0:
                    # Link to results page for completed journeys
                    card.add_navigation_link(
                        url=f"/results/{js.journey_id}",
                        label="View Results",
                        link_type=NavigationLinkType.RESULT
                    )

                cards.append(card.to_html())
            else:
                # Original static card HTML
                status_class = f"status-{js.status}"
                cards.append(f"""
                <div class="journey-card {status_class}">
                    <div class="journey-header">
                        <span class="journey-name">{js.journey_name}</span>
                        <span class="journey-status">{js.status.upper()}</span>
                    </div>
                    <div class="journey-progress">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {js.completion_percentage:.1f}%"></div>
                        </div>
                        <div class="progress-stats">
                            <span>{js.completed_scenarios}/{js.total_scenarios} scenarios</span>
                            <span>{js.pass_rate:.1f}% pass rate</span>
                        </div>
                    </div>
                </div>
                """)

        return ''.join(cards)

    def to_markdown_summary(self) -> str:
        """
        Generate markdown summary for Kanban comments

        Returns:
            Markdown string with summary
        """
        stats = self.overall_stats
        failed_journeys = self.get_failed_journeys()

        md = f"""## 📊 UAT Progress Summary

**Overall Statistics:**
- **Total Journeys:** {stats.total_journeys}
- **Total Scenarios:** {stats.total_scenarios}
- **Pass Rate:** {stats.pass_rate:.1f}%
- **Execution Progress:** {stats.completion_percentage:.1f}%
- **Stage:** {stats.execution_stage.value.replace('_', ' ').title()}

**Test Results:**
- ✅ Passed: {stats.passed_tests}
- ❌ Failed: {stats.failed_tests}
"""

        if failed_journeys:
            md += f"\n**Failures:** {len(failed_journeys)} journeys with failures\n"
            for js in failed_journeys[:3]:
                md += f"- {js.journey_name}: {js.failed_scenarios} failed scenarios\n"

        if stats.estimated_remaining_seconds:
            minutes = int(stats.estimated_remaining_seconds / 60)
            md += f"\n**Estimated Time Remaining:** ~{minutes} minutes\n"

        return md

    def get_css_styles(self) -> str:
        """
        Get CSS styles for dashboard

        Returns:
            CSS string
        """
        return """
<style>
.progress-tracker-dashboard {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    padding: 20px;
    background: #f8f9fa;
    border-radius: 8px;
}

.progress-tracker-dashboard h2 {
    margin: 0 0 20px 0;
    font-size: 24px;
    font-weight: 600;
    color: #1a1a1a;
}

.overall-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
}

.stat-card {
    background: white;
    padding: 16px;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
    text-align: center;
}

.stat-icon {
    font-size: 24px;
    margin-bottom: 8px;
}

.stat-value {
    font-size: 28px;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 4px;
}

.stat-label {
    font-size: 12px;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.execution-stage {
    background: white;
    padding: 12px 16px;
    border-radius: 6px;
    border: 1px solid #e5e7eb;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.stage-label {
    font-weight: 500;
    color: #6b7280;
}

.stage-value {
    font-weight: 600;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    text-transform: uppercase;
}

.stage-not_started { background: #e5e7eb; color: #6b7280; }
.stage-parsing, .stage-extraction, .stage-generation, .stage-execution, .stage-processing, .stage-updating {
    background: #dbeafe; color: #1e40af;
}
.stage-complete { background: #d1fae5; color: #065f46; }
.stage-failed { background: #fee2e2; color: #991b1b; }

.failures-summary {
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
}

.failures-summary h3 {
    margin: 0 0 12px 0;
    font-size: 16px;
    color: #991b1b;
}

.failure-items {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.failure-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background: white;
    border-radius: 4px;
}

.failure-journey {
    font-weight: 500;
    color: #1a1a1a;
}

.failure-count {
    color: #dc2626;
    font-weight: 600;
    font-size: 14px;
}

.journey-progress-cards h3 {
    margin: 0 0 16px 0;
    font-size: 18px;
    font-weight: 600;
    color: #1a1a1a;
}

.journey-card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
}

.journey-card.status-passed {
    border-left: 4px solid #10b981;
}

.journey-card.status-failed {
    border-left: 4px solid #ef4444;
}

.journey-card.status-pending {
    border-left: 4px solid #e5e7eb;
}

.journey-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.journey-name {
    font-weight: 600;
    color: #1a1a1a;
}

.journey-status {
    font-size: 11px;
    font-weight: 700;
    padding: 4px 8px;
    border-radius: 4px;
    text-transform: uppercase;
}

.status-passed .journey-status {
    background: #d1fae5;
    color: #065f46;
}

.status-failed .journey-status {
    background: #fee2e2;
    color: #991b1b;
}

.status-pending .journey-status {
    background: #f3f4f6;
    color: #6b7280;
}

.progress-bar {
    height: 8px;
    background: #f3f4f6;
    border-radius: 4px;
    overflow: hidden;
    margin-bottom: 8px;
}

.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #10b981);
    border-radius: 4px;
    transition: width 0.3s ease;
}

.progress-stats {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: #6b7280;
}

.no-data {
    color: #9ca3af;
    font-style: italic;
    text-align: center;
    padding: 20px;
}

/* Feature #171: Clickable navigation styles */
.journey-card.clickable {
    cursor: pointer;
    transition: transform 0.2s, box-shadow 0.2s;
}

.journey-card.clickable:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.journey-navigation {
    display: flex;
    gap: 8px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid #e5e7eb;
}

.nav-link {
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    text-decoration: none;
    transition: background 0.2s;
    cursor: pointer;
    border: none;
}

.nav-journey {
    background: #3b82f6;
    color: white;
}

.nav-journey:hover {
    background: #2563eb;
}

.nav-result {
    background: #10b981;
    color: white;
}

.nav-result:hover {
    background: #059669;
}

.nav-modal {
    background: #f59e0b;
    color: white;
}

.nav-modal:hover {
    background: #d97706;
}
</style>
"""


def create_progress_tracker_from_orchestrator(result: Dict[str, Any]) -> ProgressTracker:
    """
    Factory function to create progress tracker from orchestrator result

    Args:
        result: Orchestrator result dictionary

    Returns:
        ProgressTracker instance initialized with result data
    """
    tracker = ProgressTracker()
    tracker.initialize_from_orchestrator_result(result)
    return tracker
