"""
API Routers
===========

FastAPI routers for different API endpoints.
"""

from .agent import router as agent_router
from .analytics import router as analytics_router
from .assistant_chat import router as assistant_chat_router
from .autoscaler import router as autoscaler_router
from .blocker import router as blocker_router
from .devserver import router as devserver_router
from .emergency import router as emergency_router
from .expand_project import router as expand_project_router
from .features import router as features_router
from .filesystem import router as filesystem_router
from .messages import router as messages_router
from .devlayer import router as devlayer_router
from .devlayer_quality import router as quality_gate_router
from .projects import router as projects_router
from .schedules import router as schedules_router
from .settings import router as settings_router
from .spec_creation import router as spec_creation_router
from .status import router as status_router
from .systemd import router as systemd_router
from .terminal import router as terminal_router
from .reports import router as reports_router
from .uat_gateway import router as uat_gateway_router
from .visual_testing import router as visual_testing_router
from .a11y_testing import router as a11y_testing_router
from .api_testing import router as api_testing_router
from .msw_integration import router as msw_integration_router
from .tool_orchestrator import router as tool_orchestrator_router
from .uat_websocket import router as uat_websocket_router
from .uat_reports import router as uat_reports_router

__all__ = [
    "projects_router",
    "features_router",
    "agent_router",
    "analytics_router",
    "schedules_router",
    "devserver_router",
    "emergency_router",
    "spec_creation_router",
    "expand_project_router",
    "filesystem_router",
    "assistant_chat_router",
    "settings_router",
    "status_router",
    "systemd_router",
    "terminal_router",
    "messages_router",
    "devlayer_router",
    "quality_gate_router",
    "autoscaler_router",
    "blocker_router",
    "reports_router",
    "uat_gateway_router",
    "visual_testing_router",
    "a11y_testing_router",
    "api_testing_router",
    "msw_integration_router",
    "tool_orchestrator_router",
    "uat_websocket_router",
    "uat_reports_router",
]
