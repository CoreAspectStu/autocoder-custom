"""
Kanban UI Components

This package provides UI components for displaying UAT results
on Kanban cards and in modals.

Components:
- LogViewer: Display console logs with syntax highlighting
- ResultsFilter: Filter test results by pass/fail status
- ResultsExporter: Export test results to JSON file (Feature #159)
- ResultsModal: Modal containing test results with export button (Feature #159)
- ProgressTracker: Dashboard showing overall UAT statistics
- NavigationLink: Clickable navigation links (Feature #171)
- ClickableJourneyCard: Journey cards with navigation (Feature #171)
- VideoPlayer: HTML5 video player for test failure recordings (Feature #156)
"""

from custom.uat_gateway.ui.kanban.log_viewer import LogViewer, LogEntry
from custom.uat_gateway.ui.kanban.results_filter import ResultsFilter, ResultStatus, FilterStats
from custom.uat_gateway.ui.kanban.results_exporter import (
    ResultsExporter,
    ResultsModal,
    ExportMetadata,
    create_results_modal,
    create_results_exporter
)
from custom.uat_gateway.ui.kanban.progress_tracker import (
    ProgressTracker,
    OverallStats,
    JourneyStats,
    FailureSummary,
    ExecutionStage,
    NavigationLink,
    NavigationLinkType,
    ClickableJourneyCard,
    create_progress_tracker_from_orchestrator
)
from custom.uat_gateway.ui.kanban.video_player import (
    VideoPlayer,
    VideoPlayerError,
    VideoMetadata,
    create_video_player_modal,
    render_video_thumbnail
)

__all__ = [
    "LogViewer",
    "LogEntry",
    "ResultsFilter",
    "ResultStatus",
    "FilterStats",
    "ResultsExporter",
    "ResultsModal",
    "ExportMetadata",
    "create_results_modal",
    "create_results_exporter",
    "ProgressTracker",
    "OverallStats",
    "JourneyStats",
    "FailureSummary",
    "ExecutionStage",
    "NavigationLink",
    "NavigationLinkType",
    "ClickableJourneyCard",
    "create_progress_tracker_from_orchestrator",
    "VideoPlayer",
    "VideoPlayerError",
    "VideoMetadata",
    "create_video_player_modal",
    "render_video_thumbnail",
]
