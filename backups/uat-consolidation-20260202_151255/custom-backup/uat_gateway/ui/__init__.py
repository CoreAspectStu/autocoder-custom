"""
UAT Gateway UI Components

This package provides frontend components for the UAT Gateway system:
- Kanban UI: Card components and result modals
- Progress Tracker: Dashboard components for tracking UAT progress
- Realtime: WebSocket-based live updates (Feature #175)
- Success Notifications: Toast notifications for successful actions (Feature #231)
"""

from uat_gateway.ui.events import (
    EventManager,
    ErrorEvent,
    ProgressEvent,
    StatusEvent,
    SuccessEvent,  # Feature #231
    EventType,
    ErrorSeverity,
    get_event_manager,
    reset_event_manager,
)

__all__ = [
    "EventManager",
    "ErrorEvent",
    "ProgressEvent",
    "StatusEvent",
    "SuccessEvent",  # Feature #231
    "EventType",
    "ErrorSeverity",
    "get_event_manager",
    "reset_event_manager",
]
