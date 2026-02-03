"""
Unit tests for UAT Test Status Lifecycle State Machine.

Tests the status transition validation and history tracking for Feature #20.
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path to import custom modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom.uat_plugin.status_machine import (
    is_valid_transition,
    get_valid_next_statuses,
    get_terminal_statuses,
    is_terminal_status,
    can_retry,
    get_transition_description,
    TestStatus
)


class TestValidTransitions:
    """Test all valid status transitions."""

    def test_pending_to_in_progress(self):
        """Test: pending → in_progress is VALID."""
        assert is_valid_transition('pending', 'in_progress') == True

    def test_pending_to_parked(self):
        """Test: pending → parked is VALID (user skips test)."""
        assert is_valid_transition('pending', 'parked') == True

    def test_in_progress_to_passed(self):
        """Test: in_progress → passed is VALID (test succeeded)."""
        assert is_valid_transition('in_progress', 'passed') == True

    def test_in_progress_to_failed(self):
        """Test: in_progress → failed is VALID (bug detected)."""
        assert is_valid_transition('in_progress', 'failed') == True

    def test_in_progress_to_needs_human(self):
        """Test: in_progress → needs-human is VALID (blocker detected)."""
        assert is_valid_transition('in_progress', 'needs-human') == True

    def test_failed_to_in_progress(self):
        """Test: failed → in_progress is VALID (retry after fix)."""
        assert is_valid_transition('failed', 'in_progress') == True

    def test_failed_to_needs_human(self):
        """Test: failed → needs-human is VALID (blocker during retest)."""
        assert is_valid_transition('failed', 'needs-human') == True

    def test_needs_human_to_in_progress(self):
        """Test: needs-human → in_progress is VALID (user resolved blocker)."""
        assert is_valid_transition('needs-human', 'in_progress') == True

    def test_needs_human_to_parked(self):
        """Test: needs-human → parked is VALID (user abandoned test)."""
        assert is_valid_transition('needs-human', 'parked') == True

    def test_parked_to_in_progress(self):
        """Test: parked → in_progress is VALID (user retrying parked test)."""
        assert is_valid_transition('parked', 'in_progress') == True


class TestInvalidTransitions:
    """Test that invalid transitions are rejected."""

    def test_passed_to_failed(self):
        """Test: passed → failed is INVALID (terminal state)."""
        assert is_valid_transition('passed', 'failed') == False

    def test_passed_to_in_progress(self):
        """Test: passed → in_progress is INVALID (terminal state)."""
        assert is_valid_transition('passed', 'in_progress') == False

    def test_pending_to_passed(self):
        """Test: pending → passed is INVALID (must go through in_progress first)."""
        assert is_valid_transition('pending', 'passed') == False

    def test_pending_to_failed(self):
        """Test: pending → failed is INVALID (must go through in_progress first)."""
        assert is_valid_transition('pending', 'failed') == False

    def test_failed_to_pending(self):
        """Test: failed → pending is INVALID (can't go back)."""
        assert is_valid_transition('failed', 'pending') == False

    def test_invalid_status_string(self):
        """Test: Invalid status strings return False."""
        assert is_valid_transition('invalid_status', 'in_progress') == False
        assert is_valid_transition('pending', 'invalid_status') == False


class TestGetValidNextStatuses:
    """Test getting valid next statuses for current status."""

    def test_pending_next_statuses(self):
        """Test: pending can go to in_progress or parked."""
        result = get_valid_next_statuses('pending')
        assert result == {'in_progress', 'parked'}

    def test_in_progress_next_statuses(self):
        """Test: in_progress can go to passed, failed, or needs-human."""
        result = get_valid_next_statuses('in_progress')
        assert result == {'passed', 'failed', 'needs-human'}

    def test_passed_next_statuses(self):
        """Test: passed is terminal (no outgoing transitions)."""
        result = get_valid_next_statuses('passed')
        assert result == set()

    def test_failed_next_statuses(self):
        """Test: failed can go to in_progress or needs-human."""
        result = get_valid_next_statuses('failed')
        assert result == {'in_progress', 'needs-human'}

    def test_needs_human_next_statuses(self):
        """Test: needs-human can go to in_progress or parked."""
        result = get_valid_next_statuses('needs-human')
        assert result == {'in_progress', 'parked'}

    def test_parked_next_statuses(self):
        """Test: parked can go to in_progress (retry)."""
        result = get_valid_next_statuses('parked')
        assert result == {'in_progress'}

    def test_invalid_current_status(self):
        """Test: Invalid current status returns empty set."""
        result = get_valid_next_statuses('invalid_status')
        assert result == set()


class TestTerminalStates:
    """Test terminal state identification."""

    def test_passed_is_terminal(self):
        """Test: passed is a terminal state."""
        assert is_terminal_status('passed') == True

    def test_pending_is_not_terminal(self):
        """Test: pending is not terminal."""
        assert is_terminal_status('pending') == False

    def test_in_progress_is_not_terminal(self):
        """Test: in_progress is not terminal."""
        assert is_terminal_status('in_progress') == False

    def test_failed_is_not_terminal(self):
        """Test: failed is not terminal (can retry)."""
        assert is_terminal_status('failed') == False

    def test_get_terminal_statuses_set(self):
        """Test: get_terminal_statuses returns correct set."""
        terminals = get_terminal_statuses()
        assert 'passed' in terminals
        assert 'pending' not in terminals
        assert 'in_progress' not in terminals
        assert 'failed' not in terminals


class TestCanRetry:
    """Test can_retry helper function."""

    def test_failed_can_retry(self):
        """Test: failed tests can be retried."""
        assert can_retry('failed') == True

    def test_needs_human_can_retry(self):
        """Test: needs-human tests can be retried after user responds."""
        assert can_retry('needs-human') == True

    def test_parked_can_retry(self):
        """Test: parked tests can be retried."""
        assert can_retry('parked') == True

    def test_passed_cannot_retry(self):
        """Test: passed tests cannot be retried (terminal)."""
        assert can_retry('passed') == False

    def test_pending_cannot_retry(self):
        """Test: pending tests don't need retry (not started yet)."""
        assert can_retry('pending') == False


class TestTransitionDescriptions:
    """Test human-readable transition descriptions."""

    def test_pending_to_in_progress_description(self):
        """Test: pending → in_progress has description."""
        desc = get_transition_description('pending', 'in_progress')
        assert desc == 'Test claimed by agent'

    def test_in_progress_to_passed_description(self):
        """Test: in_progress → passed has description."""
        desc = get_transition_description('in_progress', 'passed')
        assert desc == 'Test completed successfully'

    def test_in_progress_to_failed_description(self):
        """Test: in_progress → failed has description."""
        desc = get_transition_description('in_progress', 'failed')
        assert desc == 'Test failed - bug detected'

    def test_invalid_transition_returns_none(self):
        """Test: Invalid transitions return None."""
        desc = get_transition_description('passed', 'failed')
        assert desc is None


class TestStatusEnum:
    """Test TestStatus enum values."""

    def test_all_statuses_defined(self):
        """Test: All required statuses are defined."""
        assert TestStatus.PENDING == "pending"
        assert TestStatus.IN_PROGRESS == "in_progress"
        assert TestStatus.PASSED == "passed"
        assert TestStatus.FAILED == "failed"
        assert TestStatus.NEEDS_HUMAN == "needs-human"
        assert TestStatus.PARKED == "parked"

    def test_enum_values_match_strings(self):
        """Test: Enum values match expected string values."""
        assert TestStatus.PENDING.value == "pending"
        assert TestStatus.IN_PROGRESS.value == "in_progress"
        assert TestStatus.PASSED.value == "passed"
        assert TestStatus.FAILED.value == "failed"
        assert TestStatus.NEEDS_HUMAN.value == "needs-human"
        assert TestStatus.PARKED.value == "parked"


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v'])
