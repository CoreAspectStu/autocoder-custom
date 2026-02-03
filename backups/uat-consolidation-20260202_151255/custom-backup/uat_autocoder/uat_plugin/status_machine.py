"""
UAT Test Status State Machine

Defines valid status transitions for UAT tests and provides validation logic.
Ensures tests follow proper lifecycle: pending → in_progress → passed/failed/needs-human/parked
"""

from typing import Set, Dict, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TestStatus(str, Enum):
    """Valid UAT test statuses."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    NEEDS_HUMAN = "needs-human"
    PARKED = "parked"


# Valid state transitions (what each status can transition TO)
VALID_TRANSITIONS: Dict[TestStatus, Set[TestStatus]] = {
    TestStatus.PENDING: {
        TestStatus.IN_PROGRESS,  # Normal flow: start testing
        TestStatus.PARKED,        # User decides to skip before starting
    },
    TestStatus.IN_PROGRESS: {
        TestStatus.PASSED,        # Test succeeded
        TestStatus.FAILED,        # Test failed (bug found)
        TestStatus.NEEDS_HUMAN,   # Blocker detected during execution
    },
    TestStatus.FAILED: {
        TestStatus.IN_PROGRESS,   # Retry after bug fix
        TestStatus.NEEDS_HUMAN,   # Blocker during retest
    },
    TestStatus.NEEDS_HUMAN: {
        TestStatus.IN_PROGRESS,   # User responded to blocker, resume testing
        TestStatus.PARKED,        # User gave up on this test
    },
    TestStatus.PASSED: {
        # Terminal state - no outgoing transitions
    },
    TestStatus.PARKED: {
        TestStatus.IN_PROGRESS,   # User decides to retry parked test
    },
}


# Terminal states (no outgoing transitions)
TERMINAL_STATES: Set[TestStatus] = {
    TestStatus.PASSED,
}


# Initial state for new tests
INITIAL_STATE = TestStatus.PENDING


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """
    Check if a status transition is valid.

    Args:
        from_status: Current status
        to_status: Desired new status

    Returns:
        True if transition is valid, False otherwise

    Examples:
        >>> is_valid_transition('pending', 'in_progress')
        True
        >>> is_valid_transition('passed', 'failed')
        False  # Can't go from passed back to failed (terminal state)
        >>> is_valid_transition('pending', 'passed')
        False  # Must go through in_progress first
    """
    try:
        from_enum = TestStatus(from_status)
        to_enum = TestStatus(to_status)
    except ValueError as e:
        # Invalid status string
        logger.warning(f"Invalid status string: {e}")
        return False

    # Check if transition is allowed
    allowed = VALID_TRANSITIONS.get(from_enum, set())
    is_valid = to_enum in allowed

    if not is_valid:
        logger.debug(f"Invalid transition: {from_status} → {to_status}")

    return is_valid


def get_valid_next_statuses(current_status: str) -> Set[str]:
    """
    Get all valid next statuses for a given current status.

    Args:
        current_status: Current test status

    Returns:
        Set of valid next status strings

    Example:
        >>> get_valid_next_statuses('pending')
        {'in_progress', 'parked'}
        >>> get_valid_next_statuses('passed')
        set()  # Terminal state
    """
    try:
        current_enum = TestStatus(current_status)
        allowed = VALID_TRANSITIONS.get(current_enum, set())
        return {status.value for status in allowed}
    except ValueError:
        logger.warning(f"Invalid current status: {current_status}")
        return set()


def get_terminal_statuses() -> Set[str]:
    """Get all terminal (final) statuses."""
    return {status.value for status in TERMINAL_STATES}


def is_terminal_status(status: str) -> bool:
    """
    Check if a status is terminal (final state).

    Args:
        status: Status string to check

    Returns:
        True if status is terminal, False otherwise

    Example:
        >>> is_terminal_status('passed')
        True
        >>> is_terminal_status('pending')
        False
    """
    return status in get_terminal_statuses()


def can_retry(status: str) -> bool:
    """
    Check if a test in this status can be retried.

    Args:
        status: Current test status

    Returns:
        True if test can be moved back to in_progress, False otherwise

    Example:
        >>> can_retry('failed')
        True
        >>> can_retry('passed')
        False
        >>> can_retry('needs-human')
        True
    """
    return is_valid_transition(status, 'in_progress')


def get_transition_description(from_status: str, to_status: str) -> str:
    """
    Get a human-readable description of a status transition.

    Args:
        from_status: Current status
        to_status: New status

    Returns:
        Human-readable description or None if transition is invalid
    """
    if not is_valid_transition(from_status, to_status):
        return None

    descriptions = {
        ('pending', 'in_progress'): 'Test claimed by agent',
        ('pending', 'parked'): 'Test skipped by user',
        ('in_progress', 'passed'): 'Test completed successfully',
        ('in_progress', 'failed'): 'Test failed - bug detected',
        ('in_progress', 'needs-human'): 'Blocker detected - awaiting user input',
        ('failed', 'in_progress'): 'Retrying test after fix',
        ('failed', 'needs-human'): 'Blocker during retest',
        ('needs-human', 'in_progress'): 'User resolved blocker - resuming',
        ('needs-human', 'parked'): 'Test abandoned after blocker',
        ('parked', 'in_progress'): 'Retrying previously parked test',
    }

    return descriptions.get((from_status, to_status), 'Status updated')
