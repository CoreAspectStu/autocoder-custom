"""
Mission Control Integration Patch

This module provides functions to integrate Mission Control MCP server
with AutoCoder's client.py without modifying the core file.

Usage in client.py:
    from custom.mission_control.integration import add_mission_control_mcp

    # After building mcp_servers dict:
    mcp_servers = add_mission_control_mcp(mcp_servers, project_dir)
"""

import os
import sys
from pathlib import Path


def add_mission_control_mcp(mcp_servers: dict, project_dir: Path) -> dict:
    """
    Add Mission Control MCP server to mcp_servers dict (if enabled).

    Args:
        mcp_servers: Existing MCP servers dict
        project_dir: Project directory path

    Returns:
        Updated mcp_servers dict (with mission_control added if enabled)

    Environment:
        MISSION_CONTROL_ENABLED: Set to "true" to enable Mission Control
    """
    # Check if Mission Control is enabled
    if not os.getenv("MISSION_CONTROL_ENABLED", "false").lower() in ("true", "1", "yes", "on"):
        return mcp_servers

    print("   - Mission Control enabled (DevLayer + human-in-the-loop)")

    # Get project name from directory
    project_name = project_dir.name

    # Add Mission Control MCP server
    mcp_servers["mission_control"] = {
        "command": sys.executable,
        "args": [
            str(Path(__file__).parent / "mcp_server" / "mission_control_mcp.py")
        ],
        "env": {
            "PROJECT_NAME": project_name,
            "PYTHONPATH": str(Path(__file__).parent.parent.parent.resolve()),
        },
    }

    return mcp_servers


def get_mission_control_tools() -> list[str]:
    """
    Get list of Mission Control MCP tool names.

    Returns:
        List of tool names to add to allowed_tools
    """
    return [
        "mcp__mission_control__devlayer_ask_question",
        "mcp__mission_control__devlayer_report_blocker",
        "mcp__mission_control__devlayer_request_decision",
        "mcp__mission_control__devlayer_request_auth",
        "mcp__mission_control__devlayer_send_chat",
        "mcp__mission_control__devlayer_create_annotation",
    ]
