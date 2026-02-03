"""
Journey State Machine Module for UAT Gateway

Feature #387: State transitions work correctly

Implements a state machine for journey execution with proper state transitions:
- PENDING: Journey created, not yet started
- RUNNING: Tests are currently executing
- COMPLETED: All tests finished successfully
- FAILED: Tests finished with failures
- CANCELLED: Journey was cancelled before completion

Valid transitions:
  PENDING → RUNNING
  PENDING → CANCELLED
  RUNNING → COMPLETED
  RUNNING → FAILED
  RUNNING → CANCELLED
  (any) → PENDING (reset/restart)

Invalid transitions are blocked with clear error messages.
"""

from enum import Enum
from typing import Dict, Set, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class JourneyStatus(Enum):
    """Status of a journey execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Define valid state transitions
VALID_TRANSITIONS: Dict[JourneyStatus, Set[JourneyStatus]] = {
    JourneyStatus.PENDING: {JourneyStatus.RUNNING, JourneyStatus.CANCELLED},
    JourneyStatus.RUNNING: {JourneyStatus.COMPLETED, JourneyStatus.FAILED, JourneyStatus.CANCELLED},
    JourneyStatus.COMPLETED: {JourneyStatus.PENDING},  # Can restart
    JourneyStatus.FAILED: {JourneyStatus.PENDING},  # Can retry
    JourneyStatus.CANCELLED: {JourneyStatus.PENDING},  # Can restart
}


@dataclass
class StateTransition:
    """Represents a state transition"""
    from_status: JourneyStatus
    to_status: JourneyStatus
    is_valid: bool
    reason: Optional[str] = None


class JourneyStateMachine:
    """
    State machine for journey execution status.

    Ensures that status transitions follow valid patterns and prevents
    invalid state changes that could corrupt the journey lifecycle.
    """

    def __init__(self):
        """Initialize the state machine"""
        self.logger = logger

    def validate_transition(
        self,
        current_status: str,
        new_status: str
    ) -> StateTransition:
        """
        Validate a state transition from current to new status.

        Args:
            current_status: Current status string (e.g., "pending", "running")
            new_status: Desired new status string

        Returns:
            StateTransition object with validation result
        """
        try:
            from_state = JourneyStatus(current_status.lower())
            to_state = JourneyStatus(new_status.lower())
        except ValueError as e:
            return StateTransition(
                from_status=JourneyStatus.PENDING,  # Default
                to_status=JourneyStatus.PENDING,
                is_valid=False,
                reason=f"Invalid status values: {e}"
            )

        # Check if transition is allowed
        allowed_next_states = VALID_TRANSITIONS.get(from_state, set())

        if to_state in allowed_next_states:
            self.logger.info(
                f"Valid transition: {from_state.value} → {to_state.value}"
            )
            return StateTransition(
                from_status=from_state,
                to_status=to_state,
                is_valid=True,
                reason=None
            )
        else:
            # Transition not allowed
            if from_state == to_state:
                reason = f"Already in {to_state.value} state"
            else:
                valid_list = ", ".join(s.value for s in allowed_next_states)
                reason = (
                    f"Cannot transition from {from_state.value} to {to_state.value}. "
                    f"Valid next states: {valid_list}"
                )

            self.logger.warning(
                f"Invalid transition attempted: {from_state.value} → {to_state.value}"
            )

            return StateTransition(
                from_status=from_state,
                to_status=to_state,
                is_valid=False,
                reason=reason
            )

    def get_valid_next_states(self, current_status: str) -> Set[str]:
        """
        Get all valid next states from the current status.

        Args:
            current_status: Current status string

        Returns:
            Set of valid next status strings
        """
        try:
            current = JourneyStatus(current_status.lower())
            valid_states = VALID_TRANSITIONS.get(current, set())
            return {s.value for s in valid_states}
        except ValueError:
            self.logger.error(f"Invalid current status: {current_status}")
            return set()

    def can_start(self, current_status: str) -> bool:
        """
        Check if journey can be started from current status.

        Args:
            current_status: Current status string

        Returns:
            True if PENDING → RUNNING transition is valid
        """
        transition = self.validate_transition(current_status, JourneyStatus.RUNNING.value)
        return transition.is_valid

    def can_complete(self, current_status: str) -> Tuple[bool, Optional[str]]:
        """
        Check if journey can be completed from current status.

        Args:
            current_status: Current status string

        Returns:
            Tuple of (can_complete, status_to_use)
        """
        success_transition = self.validate_transition(
            current_status,
            JourneyStatus.COMPLETED.value
        )

        fail_transition = self.validate_transition(
            current_status,
            JourneyStatus.FAILED.value
        )

        if success_transition.is_valid:
            return (True, JourneyStatus.COMPLETED.value)
        elif fail_transition.is_valid:
            return (True, JourneyStatus.FAILED.value)
        else:
            return (False, None)

    def can_cancel(self, current_status: str) -> bool:
        """
        Check if journey can be cancelled from current status.

        Args:
            current_status: Current status string

        Returns:
            True if cancellation is allowed
        """
        transition = self.validate_transition(current_status, JourneyStatus.CANCELLED.value)
        return transition.is_valid

    def can_restart(self, current_status: str) -> bool:
        """
        Check if journey can be restarted from current status.

        Args:
            current_status: Current status string

        Returns:
            True if PENDING state can be reached
        """
        transition = self.validate_transition(current_status, JourneyStatus.PENDING.value)
        return transition.is_valid


# Global instance
_state_machine: Optional[JourneyStateMachine] = None


def get_journey_state_machine() -> JourneyStateMachine:
    """
    Get the global journey state machine instance.

    Returns:
        JourneyStateMachine instance
    """
    global _state_machine
    if _state_machine is None:
        _state_machine = JourneyStateMachine()
    return _state_machine
