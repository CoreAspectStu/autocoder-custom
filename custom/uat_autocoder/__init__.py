"""
UAT AutoCoder Plugin

A mini-AutoCoder system for UAT testing that mirrors the core AutoCoder workflow:
PRD Analysis → Test Planning → Test Features → Agent Execution → Results

This plugin follows AutoCoder patterns:
- Separate database (uat_tests.db)
- Parallel test orchestrator
- MCP server for test management
- Agent-based test execution
- WebSocket progress updates
"""

__version__ = "1.0.0"

from .database import UATDatabase
from .orchestrator import UATOrchestrator
from .mcp_server import UATTestMCP

__all__ = [
    "UATDatabase",
    "UATOrchestrator",
    "UATTestMCP",
]
