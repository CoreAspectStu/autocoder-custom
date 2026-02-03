#!/usr/bin/env python3
"""
UAT AutoCoder Plugin - MCP Server

This module provides the Model Context Protocol (MCP) server for UAT test management.
It exposes tools for test agents to claim, execute, and report results for UAT tests.

The MCP server uses FastMCP framework and provides thread-safe access to the UAT database.

Author: AutoCoder Agent
Created: 2025-01-27
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import FastMCP
try:
    from fastmcp import FastMCP
    logger.info(f"✓ FastMCP imported successfully")
except ImportError as e:
    logger.error(f"✗ FastMCP not available: {e}")
    logger.error("Install with: pip3 install fastmcp")
    sys.exit(1)

# Import local modules
try:
    from .database import DatabaseManager, get_test_by_id, get_tests_by_status
    from .config import get_config
except ImportError as e:
    logger.error(f"✗ Failed to import local modules: {e}")
    logger.error("Ensure the custom/uat_plugin package is properly installed")
    sys.exit(1)


# Create FastMCP server instance
mcp = FastMCP("UAT AutoCoder Test Manager")


# =============================================================================
# MCP Tools - Test Claiming and Status Management
# =============================================================================

@mcp.tool()
def test_claim_and_get(test_id: int) -> Dict[str, Any]:
    """
    Atomically claim a test (mark in-progress) and return its full details.

    This is the primary way for test agents to claim work. It combines marking
    a test as in-progress with retrieving its details in a single atomic operation.

    Uses UPDATE with RETURNING clause for thread-safe atomic claim operation.

    Args:
        test_id: The ID of the test to claim and retrieve

    Returns:
        Dictionary with test details including claimed status, or error if not found

    Example:
        >>> test = test_claim_and_get(42)
        >>> print(test['scenario'])
        "User can login with valid credentials"
    """
    logger.info(f"Agent claiming test #{test_id}")

    try:
        db = DatabaseManager()

        # ATOMIC OPERATION: Update and return test details in one query
        # This prevents race conditions by using UPDATE's WHERE clause
        # to ensure only one agent can claim a test with status='pending'
        query = """
            UPDATE uat_test_features
            SET status = 'in_progress',
                started_at = ?
            WHERE id = ?
              AND status = 'pending'
            RETURNING *
        """

        result = db.update_and_fetch(query, (datetime.now().isoformat(), test_id))

        if result:
            # Test was successfully claimed (was pending, now in_progress)
            test = dict(result)
            logger.info(f"✓ Test #{test_id} claimed successfully")
            return {
                "success": True,
                "test": test,
                "already_claimed": False,
                "message": f"Test #{test_id} claimed successfully"
            }
        else:
            # Test was not in 'pending' state (either not found, or already claimed)
            test = get_test_by_id(test_id)
            if not test:
                logger.warning(f"Test #{test_id} not found")
                return {
                    "success": False,
                    "error": f"Test #{test_id} not found",
                    "test_id": test_id
                }

            # Test exists but wasn't pending (already in_progress, passed, or failed)
            logger.info(f"Test #{test_id} already claimed or completed (status: {test.get('status')})")
            return {
                "success": True,
                "test": test,
                "already_claimed": True,
                "message": f"Test #{test_id} was already claimed or completed"
            }

    except Exception as e:
        logger.error(f"Error claiming test #{test_id}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "test_id": test_id
        }


@mcp.tool()
def test_mark_passed(test_id: int, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mark a test as passing after successful execution.

    Call this after you have executed the test and verified it works correctly.
    This will update the test's status to 'passed' and store the result evidence.

    Validates that the status transition is valid (in_progress → passed).

    Args:
        test_id: The ID of the test to mark as passing
        result: Dictionary containing test results (screenshot, video, logs, error, duration)

    Returns:
        Confirmation dictionary with success status

    Example:
        >>> result = {
        ...     "screenshot": "/path/to/screenshot.png",
        ...     "duration": 5.2,
        ...     "logs": "Test passed successfully"
        ... }
        >>> test_mark_passed(42, result)
    """
    logger.info(f"Marking test #{test_id} as PASSED")

    try:
        db = DatabaseManager()

        # VALIDATE TRANSITION before updating
        from .status_machine import is_valid_transition

        # Get current status
        test = get_test_by_id(test_id)
        if not test:
            logger.warning(f"Test #{test_id} not found")
            return {
                "success": False,
                "error": f"Test #{test_id} not found",
                "test_id": test_id
            }

        current_status = test.get('status')
        if not is_valid_transition(current_status, 'passed'):
            logger.warning(
                f"Invalid status transition for test #{test_id}: {current_status} → passed"
            )
            return {
                "success": False,
                "error": f"Invalid status transition: {current_status} → passed",
                "test_id": test_id,
                "current_status": current_status
            }

        # Use update_status_with_history for proper tracking
        with db.uat_session() as session:
            from .database import update_status_with_history, UATTestFeature

            # Update status with history
            update_status_with_history(
                session,
                test_id,
                'passed',
                agent_id='test_agent',
                reason='Test completed successfully'
            )

            # Update result
            test_obj = session.query(UATTestFeature).filter(
                UATTestFeature.id == test_id
            ).first()
            test_obj.result = json.dumps(result)
            test_obj.completed_at = datetime.now()

            session.commit()

        logger.info(f"✓ Test #{test_id} marked as PASSED")
        return {
            "success": True,
            "test_id": test_id,
            "status": "passed",
            "message": f"Test #{test_id} marked as passing"
        }

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return {
            "success": False,
            "error": str(e),
            "test_id": test_id
        }
    except Exception as e:
        logger.error(f"Error marking test #{test_id} as passed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "test_id": test_id
        }


@mcp.tool()
def test_mark_failed(test_id: int, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mark a test as failing after discovering a defect.

    Call this when a test agent discovers that a test scenario does not work
    correctly (bug detected). This will store the failure evidence and can
    optionally create a DevLayer bug card.

    Validates that the status transition is valid (in_progress → failed).

    Args:
        test_id: The ID of the test to mark as failing
        result: Dictionary containing failure evidence (screenshot, video, logs, error, duration)

    Returns:
        Confirmation dictionary with success status and DevLayer card ID (if created)

    Example:
        >>> result = {
        ...     "error": "Login button not responding",
        ...     "screenshot": "/path/to/screenshot.png",
        ...     "duration": 10.5,
        ...     "logs": "Timeout waiting for login button"
        ... }
        >>> test_mark_failed(42, result)
    """
    logger.info(f"Marking test #{test_id} as FAILED")

    try:
        db = DatabaseManager()
        config = get_config()

        # VALIDATE TRANSITION before updating
        from .status_machine import is_valid_transition

        # Get current status
        test = get_test_by_id(test_id)
        if not test:
            logger.warning(f"Test #{test_id} not found")
            return {
                "success": False,
                "error": f"Test #{test_id} not found",
                "test_id": test_id
            }

        current_status = test.get('status')
        if not is_valid_transition(current_status, 'failed'):
            logger.warning(
                f"Invalid status transition for test #{test_id}: {current_status} → failed"
            )
            return {
                "success": False,
                "error": f"Invalid status transition: {current_status} → failed",
                "test_id": test_id,
                "current_status": current_status
            }

        # Use update_status_with_history for proper tracking
        with db.uat_session() as session:
            from .database import update_status_with_history, UATTestFeature

            # Update status with history
            update_status_with_history(
                session,
                test_id,
                'failed',
                agent_id='test_agent',
                reason=f"Test failed: {result.get('error', 'Unknown error')}"
            )

            # Update result
            test_obj = session.query(UATTestFeature).filter(
                UATTestFeature.id == test_id
            ).first()
            test_obj.result = json.dumps(result)
            test_obj.completed_at = datetime.now()

            session.commit()

        # Create DevLayer card if configured
        card_id = None
        if config.integration.devlayer.auto_create_cards:
            try:
                # Fetch test details for better bug card context
                test_query = db.execute(
                    "SELECT scenario, description FROM uat_test_features WHERE id = ?",
                    (test_id,)
                ).fetchone()

                test_scenario = test_query[0] if test_query else None
                test_description = test_query[1] if test_query else None

                # Import DevLayer integration
                from .integrations import create_devlayer_card_with_mcp
                card_id = create_devlayer_card_with_mcp(
                    test_id, result, test_scenario, test_description
                )
                logger.info(f"✓ DevLayer card #{card_id} created for test #{test_id}")

                # Store card ID in test record
                db.execute(
                    "UPDATE uat_test_features SET devlayer_card_id = ? WHERE id = ?",
                    (card_id, test_id)
                )
                db.commit()
            except ImportError:
                logger.warning("DevLayer integration not available")
            except Exception as e:
                logger.warning(f"Failed to create DevLayer card: {e}")

        logger.info(f"✓ Test #{test_id} marked as FAILED")

        return {
            "success": True,
            "test_id": test_id,
            "status": "failed",
            "devlayer_card_id": card_id,
            "message": f"Test #{test_id} marked as failing"
        }

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return {
            "success": False,
            "error": str(e),
            "test_id": test_id
        }
    except Exception as e:
        logger.error(f"Error marking test #{test_id} as failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "test_id": test_id
        }


@mcp.tool()
def test_mark_in_progress(test_id: int) -> Dict[str, Any]:
    """
    Mark a test as in-progress.

    This prevents other agent sessions from working on the same test.
    Call this after getting your assigned test details with test_claim_and_get.

    Args:
        test_id: The ID of the test to mark as in-progress

    Returns:
        Dictionary with updated test details, or error if not found or already in progress

    Example:
        >>> test_mark_in_progress(42)
    """
    logger.info(f"Marking test #{test_id} as in-progress")

    try:
        db = DatabaseManager()

        # Check current status
        test = get_test_by_id(test_id)
        if not test:
            return {
                "success": False,
                "error": f"Test #{test_id} not found",
                "test_id": test_id
            }

        if test.get('status') == 'in_progress':
            return {
                "success": False,
                "error": f"Test #{test_id} is already in progress",
                "test_id": test_id,
                "test": test
            }

        # Mark as in_progress
        db.execute(
            "UPDATE uat_test_features SET status = ?, started_at = ? WHERE id = ?",
            ('in_progress', datetime.now().isoformat(), test_id)
        )
        db.commit()

        # Get updated test
        test = get_test_by_id(test_id)
        logger.info(f"✓ Test #{test_id} marked as in-progress")

        return {
            "success": True,
            "test": test,
            "message": f"Test #{test_id} marked as in progress"
        }

    except Exception as e:
        logger.error(f"Error marking test #{test_id} as in-progress: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "test_id": test_id
        }


@mcp.tool()
def test_get_next() -> Dict[str, Any]:
    """
    Get the next available test to work on and ATOMICALLY CLAIM IT.

    Returns a test that is ready to be executed (not passing, not in progress,
    and all dependencies satisfied). The test is immediately marked as in_progress
    to prevent race conditions where multiple agents get the same test.

    Uses UPDATE with RETURNING to atomically find and claim a test in one operation.
    Multiple agents calling this simultaneously will receive different tests.

    Returns:
        Dictionary with the next available test (already claimed), or a message if no tests available

    Example:
        >>> next_test = test_get_next()
        >>> if next_test['test']:
        ...     # Test is already claimed, proceed with execution
        ...     test_id = next_test['test']['id']
    """
    logger.info("Getting next available test (with atomic claim)")

    try:
        db = DatabaseManager()

        # ATOMIC OPERATION: Find and claim the next available test in one query
        # This prevents multiple agents from getting the same test
        query = """
            UPDATE uat_test_features
            SET status = 'in_progress',
                started_at = ?
            WHERE id = (
                SELECT id FROM uat_test_features
                WHERE status = 'pending'
                  AND (
                      dependencies IS NULL
                      OR dependencies = '[]'
                      OR json_array_length(dependencies) = 0
                      OR (
                          SELECT COUNT(*) FROM uat_test_features
                          WHERE id IN (
                              SELECT value FROM json_each(uat_test_features.dependencies)
                          )
                          AND status != 'passed'
                      ) = 0
                  )
                ORDER BY priority ASC
                LIMIT 1
            )
            RETURNING *
        """

        result = db.update_and_fetch(query, (datetime.now().isoformat(),))

        if result:
            test = dict(result)
            logger.info(f"✓ Found and claimed test #{test['id']}: {test['scenario']}")
            return {
                "success": True,
                "test": test,
                "message": f"Test #{test['id']} claimed and ready"
            }
        else:
            logger.info("No tests available")
            return {
                "success": True,
                "test": None,
                "message": "No tests available (all completed or blocked)"
            }

    except Exception as e:
        logger.error(f"Error getting next test: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
def test_get_stats() -> Dict[str, Any]:
    """
    Get statistics about test completion progress.

    Returns the number of passing tests, failing tests, in-progress tests,
    and total tests. Use this to track overall progress of the test cycle.

    Returns:
        Dictionary with test statistics (passing, failing, in_progress, total, percentage)

    Example:
        >>> stats = test_get_stats()
        >>> print(f"Progress: {stats['passing']}/{stats['total']} ({stats['percentage']}%)")
    """
    logger.info("Getting test statistics")

    try:
        db = DatabaseManager()

        # Get counts by status
        stats = db.fetch_one("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
            FROM uat_test_features
        """)

        if stats and stats['total'] > 0:
            percentage = (stats['passed'] / stats['total']) * 100
        else:
            percentage = 0.0

        logger.info(f"✓ Statistics: {stats['passed']}/{stats['total']} passing ({percentage:.1f}%)")

        return {
            "success": True,
            "stats": {
                "passing": stats['passed'] if stats else 0,
                "failing": stats['failed'] if stats else 0,
                "in_progress": stats['in_progress'] if stats else 0,
                "pending": stats['pending'] if stats else 0,
                "total": stats['total'] if stats else 0,
                "percentage": round(percentage, 1)
            }
        }

    except Exception as e:
        logger.error(f"Error getting statistics: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
def test_get_by_id(test_id: int) -> Dict[str, Any]:
    """
    Get a specific test by its ID.

    Returns the full details of a test including its scenario, steps,
    expected result, and current status.

    Args:
        test_id: The ID of the test to retrieve

    Returns:
        Dictionary with test details, or error if not found

    Example:
        >>> test = test_get_by_id(42)
        >>> print(test['scenario'])
        "User can login with valid credentials"
    """
    logger.info(f"Getting test #{test_id}")

    try:
        test = get_test_by_id(test_id)

        if test:
            logger.info(f"✓ Found test #{test_id}: {test['scenario']}")
            return {
                "success": True,
                "test": test
            }
        else:
            logger.warning(f"Test #{test_id} not found")
            return {
                "success": False,
                "error": f"Test #{test_id} not found",
                "test_id": test_id
            }

    except Exception as e:
        logger.error(f"Error getting test #{test_id}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "test_id": test_id
        }


# =============================================================================
# Server Startup
# =============================================================================

def main():
    """Main entry point for MCP server"""
    logger.info("=" * 60)
    logger.info("UAT AutoCoder MCP Server")
    logger.info("=" * 60)
    logger.info("")

    # Verify database connection
    try:
        db = DatabaseManager()
        test_result = db.fetch_one("SELECT COUNT(*) as count FROM uat_test_features")
        logger.info(f"✓ Database connected: {test_result['count'] if test_result else 0} tests in database")
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        logger.error("Please ensure the database is properly initialized")
        sys.exit(1)

    # Verify configuration
    try:
        config = get_config()
        logger.info(f"✓ Configuration loaded: {config.max_concurrent_agents} max agents")
    except Exception as e:
        logger.warning(f"⚠ Configuration loading failed: {e}")
        logger.warning("Using default configuration")

    # Log available tools
    logger.info("")
    logger.info("Available MCP Tools:")
    logger.info("  - test_claim_and_get(test_id): Atomically claim and get test details")
    logger.info("  - test_mark_passed(test_id, result): Mark test as passed")
    logger.info("  - test_mark_failed(test_id, result): Mark test as failed")
    logger.info("  - test_mark_in_progress(test_id): Mark test as in-progress")
    logger.info("  - test_get_next(): Get next available test")
    logger.info("  - test_get_stats(): Get test completion statistics")
    logger.info("  - test_get_by_id(test_id): Get specific test details")
    logger.info("")

    # Start server
    logger.info("UAT MCP Server ready - waiting for connections...")
    logger.info("=" * 60)

    # Run the MCP server
    mcp.run()


if __name__ == "__main__":
    main()
