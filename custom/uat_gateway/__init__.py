"""
UAT Gateway - Custom AutoCoder Module
======================================

Automated User Acceptance Testing system for AutoCoder projects.

This module provides comprehensive UAT capabilities including:
- Journey extraction from project specs
- Automated test generation (Playwright)
- Multi-tool testing (E2E, visual regression, accessibility, API)
- Kanban board integration
- Real-time progress tracking
- Auto-fix capabilities

Usage:
    from uat_gateway import UATGatewayOrchestrator

    orchestrator = UATGatewayOrchestrator(
        project_path="/path/to/project",
        project_id="my-project"
    )
    result = await orchestrator.run_full_uat_cycle()
"""

__version__ = "1.0.0"

# Core components - lazy import to avoid circular dependencies
from .orchestrator.orchestrator import OrchestratorConfig, Orchestrator

# Re-export with common names
UATGatewayOrchestrator = Orchestrator
UATOrchestrator = Orchestrator

__all__ = [
    "UATGatewayOrchestrator",
    "UATOrchestrator",
    "Orchestrator",
    "OrchestratorConfig",
    "__version__",
]
