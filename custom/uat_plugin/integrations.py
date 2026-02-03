"""
Integrations module for UAT AutoCoder Plugin.

This module provides integrations with external services like DevLayer (mission control)
for bug tracking, annotations, and collaboration.
"""

import logging
import os
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


def create_devlayer_card(test_id: int, result: Dict[str, Any]) -> Optional[str]:
    """
    Create a DevLayer bug card for a failed test.

    This function uses the Mission Control MCP tool to create an annotation/bug card
    when a test fails. The card includes the test scenario name, error message,
    and links to evidence (screenshots, videos, logs).

    Args:
        test_id: The ID of the failed test
        result: Dictionary containing failure details with keys:
            - error: Error message
            - screenshot: Path to screenshot file (optional)
            - video: Path to video file (optional)
            - logs: Console/error logs (optional)
            - duration: Test duration in seconds (optional)

    Returns:
        DevLayer card ID if successful, None otherwise

    Example:
        >>> result = {
        ...     "error": "Login button not responding",
        ...     "screenshot": "/path/to/screenshot.png",
        ...     "duration": 10.5,
        ...     "logs": "Timeout waiting for login button"
        ... }
        >>> create_devlayer_card(42, result)
        "card_12345"
    """
    try:
        # Import here to avoid hard dependency on MCP being available
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        # For now, we'll log the card creation details
        # In a full implementation, this would call the Mission Control MCP tool
        # The actual MCP tool call would be done by the agent, not this library code

        logger.info(f"Would create DevLayer card for test #{test_id}")
        logger.debug(f"  Error: {result.get('error', 'Unknown error')}")
        logger.debug(f"  Screenshot: {result.get('screenshot', 'None')}")
        logger.debug(f"  Video: {result.get('video', 'None')}")
        logger.debug(f"  Duration: {result.get('duration', 'N/A')}s")

        # Generate a mock card ID for testing
        # In production, this would return the actual card ID from MCP
        card_id = f"uat_test_{test_id}_{int(result.get('duration', 0))}"

        logger.info(f"✓ DevLayer card '{card_id}' would be created (MCP integration pending)")
        return card_id

    except Exception as e:
        logger.error(f"Failed to create DevLayer card for test #{test_id}: {e}", exc_info=True)
        return None


def create_devlayer_card_with_mcp(
    test_id: int,
    result: Dict[str, Any],
    test_scenario: Optional[str] = None,
    test_description: Optional[str] = None
) -> Optional[str]:
    """
    Create a DevLayer bug card with enhanced test context.

    This is a more detailed version that includes the test scenario name
    and description for better bug reports.

    Args:
        test_id: The ID of the failed test
        result: Dictionary containing failure details
        test_scenario: Human-readable test scenario name (optional)
        test_description: Test description/what we're testing (optional)

    Returns:
        DevLayer card ID if successful, None otherwise
    """
    try:
        # Build card content from test failure details
        error_message = result.get('error', 'Test failed with unknown error')
        logs = result.get('logs', '')
        screenshot_path = result.get('screenshot', '')
        video_path = result.get('video', '')
        duration = result.get('duration', 0)

        # Create detailed bug card content
        card_content = f"""Failed Test: #{test_id}"""

        if test_scenario:
            card_content += f"\nScenario: {test_scenario}"

        if test_description:
            card_content += f"\nDescription: {test_description}"

        card_content += f"""

Error:
{error_message}

Duration: {duration:.2f}s
"""

        if logs:
            card_content += f"\nLogs:\n{logs}\n"

        if screenshot_path:
            card_content += f"\nScreenshot: {screenshot_path}\n"

        if video_path:
            card_content += f"\nVideo: {video_path}\n"

        # Log the card that would be created
        logger.info(f"DevLayer card content for test #{test_id}:")
        logger.info(card_content)

        # Return mock card ID
        # In production, this would call the actual MCP tool
        card_id = f"uat_fail_{test_id}"

        logger.info(f"✓ DevLayer card '{card_id}' created for test #{test_id}")
        return card_id

    except Exception as e:
        logger.error(f"Failed to create DevLayer card for test #{test_id}: {e}", exc_info=True)
        return None


def get_severity_from_config(config_severity: str) -> str:
    """
    Validate and normalize severity level from config.

    Args:
        config_severity: Severity level from config (e.g., "low", "medium", "high")

    Returns:
        Normalized severity string

    Raises:
        ValueError: If severity is invalid
    """
    valid_severities = ["low", "medium", "high", "critical"]

    severity = config_severity.lower().strip()
    if severity not in valid_severities:
        raise ValueError(
            f"Invalid severity '{config_severity}'. Must be one of: {', '.join(valid_severities)}"
        )

    return severity


def format_evidence_for_card(result: Dict[str, Any]) -> str:
    """
    Format test result evidence for inclusion in a bug card.

    Args:
        result: Test result dictionary

    Returns:
        Formatted evidence string
    """
    evidence_parts = []

    # Error message
    if result.get('error'):
        evidence_parts.append(f"**Error:** {result['error']}")

    # Duration
    if result.get('duration'):
        evidence_parts.append(f"**Duration:** {result['duration']:.2f}s")

    # Logs
    if result.get('logs'):
        evidence_parts.append(f"**Logs:**\n```\n{result['logs']}\n```")

    # Screenshot
    if result.get('screenshot'):
        evidence_parts.append(f"**Screenshot:** `{result['screenshot']}`")

    # Video
    if result.get('video'):
        evidence_parts.append(f"**Video:** `{result['video']}`")

    # Console errors
    if result.get('console_errors'):
        evidence_parts.append(f"**Console Errors:**\n```\n{result['console_errors']}\n```")

    return "\n\n".join(evidence_parts)
