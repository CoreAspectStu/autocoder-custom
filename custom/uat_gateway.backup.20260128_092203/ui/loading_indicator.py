"""
Loading Indicator Component for UAT Gateway

This module provides loading indicators, progress bars, and spinners
for long-running operations in the UAT Gateway interface.

Feature #232: UAT gateway shows loading indicators
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
import threading
import time


class LoadingState(Enum):
    """States for loading indicators"""
    IDLE = "idle"
    LOADING = "loading"
    SUCCESS = "success"
    ERROR = "error"


class IndicatorType(Enum):
    """Types of loading indicators"""
    SPINNER = "spinner"
    PROGRESS_BAR = "progress_bar"
    DOTS = "dots"
    PULSE = "pulse"


@dataclass
class LoadingIndicator:
    """
    Represents a loading indicator for a long-running operation.

    This component displays visual feedback during operations like:
    - Test execution
    - Data processing
    - File uploads
    - API calls
    """
    operation_id: str
    operation_name: str
    indicator_type: IndicatorType = IndicatorType.SPINNER
    state: LoadingState = LoadingState.IDLE
    progress: float = 0.0  # 0-100
    message: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize timestamps when state changes"""
        if self.state == LoadingState.LOADING and not self.start_time:
            self.start_time = datetime.now()

    def start(self, message: str = ""):
        """Start the loading indicator"""
        self.state = LoadingState.LOADING
        self.start_time = datetime.now()
        self.end_time = None
        self.message = message or "Loading..."
        self.progress = 0.0

    def update_progress(self, progress: float, message: str = ""):
        """
        Update progress percentage

        Args:
            progress: Progress value from 0-100
            message: Optional status message
        """
        self.progress = max(0.0, min(100.0, progress))
        if message:
            self.message = message

    def increment_progress(self, amount: float = 1.0, message: str = ""):
        """
        Increment progress by a specific amount

        Args:
            amount: Amount to increment (default 1.0)
            message: Optional status message
        """
        self.update_progress(self.progress + amount, message)

    def complete(self, message: str = "Complete!"):
        """Mark the operation as complete"""
        self.state = LoadingState.SUCCESS
        self.progress = 100.0
        self.message = message
        self.end_time = datetime.now()

    def fail(self, message: str = "Operation failed"):
        """Mark the operation as failed"""
        self.state = LoadingState.ERROR
        self.message = message
        self.end_time = datetime.now()

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get operation duration in seconds"""
        if self.start_time:
            end = self.end_time or datetime.now()
            return (end - self.start_time).total_seconds()
        return None

    @property
    def is_complete(self) -> bool:
        """Check if operation is complete (success or error)"""
        return self.state in (LoadingState.SUCCESS, LoadingState.ERROR)

    @property
    def is_loading(self) -> bool:
        """Check if operation is currently loading"""
        return self.state == LoadingState.LOADING

    def to_html(self) -> str:
        """
        Generate HTML for the loading indicator

        Returns:
            HTML string representing the loading indicator
        """
        state_class = f"loading-{self.state.value}"
        type_class = f"indicator-{self.indicator_type.value}"

        # Progress bar style
        progress_style = f"width: {self.progress}%" if self.indicator_type == IndicatorType.PROGRESS_BAR else ""

        # Determine icon based on state
        if self.state == LoadingState.SUCCESS:
            icon = "✅"
        elif self.state == LoadingState.ERROR:
            icon = "❌"
        else:
            icon = self._get_spinner_icon()

        html = f'''
        <div class="loading-indicator {state_class} {type_class}" data-operation-id="{self.operation_id}">
            <div class="indicator-icon">{icon}</div>
            <div class="indicator-content">
                <div class="indicator-message">{self.operation_name}</div>
                {f'<div class="indicator-status">{self.message}</div>' if self.message else ''}
                {f'<div class="indicator-progress-bar"><div class="indicator-progress-fill" style="{progress_style}"></div></div>' if self.indicator_type == IndicatorType.PROGRESS_BAR else ''}
                {f'<div class="indicator-percentage">{self.progress:.0f}%</div>' if self.progress > 0 else ''}
                {f'<div class="indicator-duration">{self.duration_seconds:.1f}s</div>' if self.duration_seconds else ''}
            </div>
        </div>
        '''
        return html

    def _get_spinner_icon(self) -> str:
        """Get spinner icon based on indicator type"""
        if self.indicator_type == IndicatorType.SPINNER:
            return "⏳"
        elif self.indicator_type == IndicatorType.DOTS:
            return "..."
        elif self.indicator_type == IndicatorType.PULSE:
            return "●"
        else:
            return "⏳"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "operation_id": self.operation_id,
            "operation_name": self.operation_name,
            "indicator_type": self.indicator_type.value,
            "state": self.state.value,
            "progress": self.progress,
            "message": self.message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "is_complete": self.is_complete,
            "is_loading": self.is_loading,
            "metadata": self.metadata
        }


class LoadingIndicatorManager:
    """
    Manages multiple loading indicators for the UAT Gateway.

    This class tracks loading states for concurrent operations,
    generates collective HTML, and provides progress tracking.
    """

    def __init__(self):
        """Initialize loading indicator manager"""
        self.indicators: Dict[str, LoadingIndicator] = {}
        self.history: List[Dict[str, Any]] = []

    def create_indicator(
        self,
        operation_id: str,
        operation_name: str,
        indicator_type: IndicatorType = IndicatorType.SPINNER
    ) -> LoadingIndicator:
        """
        Create a new loading indicator

        Args:
            operation_id: Unique identifier for the operation
            operation_name: Human-readable operation name
            indicator_type: Type of indicator to display

        Returns:
            LoadingIndicator instance
        """
        indicator = LoadingIndicator(
            operation_id=operation_id,
            operation_name=operation_name,
            indicator_type=indicator_type
        )
        self.indicators[operation_id] = indicator
        return indicator

    def get_indicator(self, operation_id: str) -> Optional[LoadingIndicator]:
        """Get an existing indicator by ID"""
        return self.indicators.get(operation_id)

    def start_operation(self, operation_id: str, message: str = ""):
        """Start an operation"""
        indicator = self.get_indicator(operation_id)
        if indicator:
            indicator.start(message)

    def update_progress(self, operation_id: str, progress: float, message: str = ""):
        """Update progress for an operation"""
        indicator = self.get_indicator(operation_id)
        if indicator:
            indicator.update_progress(progress, message)

    def complete_operation(self, operation_id: str, message: str = "Complete!"):
        """Mark an operation as complete"""
        indicator = self.get_indicator(operation_id)
        if indicator:
            indicator.complete(message)
            self._archive_indicator(indicator)

    def fail_operation(self, operation_id: str, message: str = "Operation failed"):
        """Mark an operation as failed"""
        indicator = self.get_indicator(operation_id)
        if indicator:
            indicator.fail(message)
            self._archive_indicator(indicator)

    def remove_indicator(self, operation_id: str):
        """Remove an indicator from active tracking"""
        if operation_id in self.indicators:
            del self.indicators[operation_id]

    def _archive_indicator(self, indicator: LoadingIndicator):
        """
        Archive completed indicator to history

        Args:
            indicator: Indicator to archive
        """
        self.history.append({
            "operation_id": indicator.operation_id,
            "operation_name": indicator.operation_name,
            "state": indicator.state.value,
            "duration_seconds": indicator.duration_seconds,
            "completed_at": datetime.now().isoformat()
        })

        # Remove from active indicators
        self.remove_indicator(indicator.operation_id)

    def get_active_indicators(self) -> List[LoadingIndicator]:
        """Get all currently active (loading) indicators"""
        return [ind for ind in self.indicators.values() if ind.is_loading]

    def get_all_indicators(self) -> List[LoadingIndicator]:
        """Get all indicators (active and complete)"""
        return list(self.indicators.values())

    def has_active_operations(self) -> bool:
        """Check if there are any active operations"""
        return any(ind.is_loading for ind in self.indicators.values())

    def to_html(self) -> str:
        """
        Generate HTML for all active indicators

        Returns:
            HTML string with all loading indicators
        """
        if not self.indicators:
            return ""

        indicators_html = []
        for indicator in self.indicators.values():
            indicators_html.append(indicator.to_html())

        return f'''
        <div class="loading-indicators-container">
            {''.join(indicators_html)}
        </div>
        '''

    def get_css_styles(self) -> str:
        """
        Get CSS styles for loading indicators

        Returns:
            CSS string
        """
        return """
<style>
.loading-indicators-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    max-width: 400px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.loading-indicator {
    background: white;
    border-radius: 8px;
    padding: 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    display: flex;
    align-items: flex-start;
    gap: 12px;
    animation: slideIn 0.3s ease-out;
    min-width: 300px;
}

@keyframes slideIn {
    from {
        transform: translateX(100%);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}

.loading-indicator.loading-success {
    border-left: 4px solid #10b981;
}

.loading-indicator.loading-error {
    border-left: 4px solid #ef4444;
}

.loading-indicator.loading-loading {
    border-left: 4px solid #3b82f6;
}

.indicator-icon {
    font-size: 24px;
    line-height: 1;
    flex-shrink: 0;
}

.loading-loading .indicator-icon {
    animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
    0%, 100% {
        opacity: 1;
        transform: scale(1);
    }
    50% {
        opacity: 0.5;
        transform: scale(1.1);
    }
}

.indicator-content {
    flex: 1;
    min-width: 0;
}

.indicator-message {
    font-weight: 600;
    color: #1a1a1a;
    margin-bottom: 4px;
    font-size: 14px;
}

.indicator-status {
    color: #6b7280;
    font-size: 13px;
    margin-bottom: 8px;
}

.indicator-progress-bar {
    height: 6px;
    background: #f3f4f6;
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 6px;
}

.indicator-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #10b981);
    border-radius: 3px;
    transition: width 0.3s ease;
}

.indicator-percentage {
    font-size: 12px;
    color: #6b7280;
    font-weight: 600;
    display: inline-block;
    margin-right: 8px;
}

.indicator-duration {
    font-size: 11px;
    color: #9ca3af;
    display: inline-block;
}

/* Spinner-specific styles */
.indicator-spinner .indicator-icon {
    animation: spin 1s linear infinite;
}

@keyframes spin {
    from {
        transform: rotate(0deg);
    }
    to {
        transform: rotate(360deg);
    }
}

/* Dots animation */
.indicator-dots .indicator-icon::after {
    content: '...';
    animation: dots 1.5s steps(4, end) infinite;
}

@keyframes dots {
    0%, 20% {
        content: '.';
    }
    40% {
        content: '..';
    }
    60%, 100% {
        content: '...';
    }
}

/* Pulse animation */
.indicator-pulse .indicator-icon {
    animation: pulse-ring 1.5s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
}

@keyframes pulse-ring {
    0% {
        transform: scale(0.8);
        opacity: 0.8;
    }
    50% {
        transform: scale(1.2);
        opacity: 0.4;
    }
    100% {
        transform: scale(0.8);
        opacity: 0.8;
    }
}

/* Fade out animation for completed indicators */
.loading-indicator.loading-success,
.loading-indicator.loading-error {
    animation: slideIn 0.3s ease-out, fadeOut 0.5s ease-out 2.5s forwards;
}

@keyframes fadeOut {
    to {
        opacity: 0;
        transform: translateX(100%);
    }
}
</style>
"""


# Global instance for convenience
_global_manager = None


def get_loading_manager() -> LoadingIndicatorManager:
    """Get the global loading indicator manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = LoadingIndicatorManager()
    return _global_manager


def create_loading_indicator(
    operation_id: str,
    operation_name: str,
    indicator_type: IndicatorType = IndicatorType.SPINNER
) -> LoadingIndicator:
    """
    Convenience function to create a loading indicator

    Args:
        operation_id: Unique identifier for the operation
        operation_name: Human-readable operation name
        indicator_type: Type of indicator to display

    Returns:
        LoadingIndicator instance
    """
    manager = get_loading_manager()
    return manager.create_indicator(operation_id, operation_name, indicator_type)
