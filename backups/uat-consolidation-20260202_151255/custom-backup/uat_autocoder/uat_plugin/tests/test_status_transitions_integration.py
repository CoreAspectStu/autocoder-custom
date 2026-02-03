"""
Integration tests for UAT Test Status Lifecycle with Database.

Tests end-to-end status transitions with history tracking for Feature #20.
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path to import custom modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from custom.uat_plugin.database import DatabaseManager, UATTestFeature, update_status_with_history
from custom.uat_plugin.status_machine import is_valid_transition
from datetime import datetime


@pytest.fixture
def db():
    """Create database manager for testing."""
    return DatabaseManager()


@pytest.fixture
def test_test(db):
    """Create a test UAT test feature for testing."""
    with db.uat_session() as session:
        test = UATTestFeature(
            priority=1,
            phase='smoke',
            journey='authentication',
            scenario='Test login with valid credentials',
            description='Verify user can login with username and password',
            test_type='e2e',
            steps=['Enter username', 'Enter password', 'Click login'],
            expected_result='User is logged in and redirected to dashboard',
            status='pending'
        )
        session.add(test)
        session.commit()
        test_id = test.id

    yield test_id

    # Cleanup
    with db.uat_session() as session:
        test = session.query(UATTestFeature).filter(
            UATTestFeature.id == test_id
        ).first()
        if test:
            session.delete(test)
            session.commit()


class TestFullLifecycle:
    """Test complete test lifecycle: pending → in_progress → passed."""

    def test_pending_to_in_progress_to_passed(self, db, test_test):
        """Test: pending → in_progress → passed with history tracking."""
        test_id = test_test

        # Verify initial status
        test = db.get_test_by_id(test_id)
        assert test['status'] == 'pending'
        assert test['status_history'] is None or len(test['status_history']) == 0

        # Transition to in_progress
        with db.uat_session() as session:
            update_status_with_history(
                session, test_id, 'in_progress',
                agent_id='test_agent_1',
                reason='Test claimed by agent'
            )
            session.commit()

        # Verify transition
        test = db.get_test_by_id(test_id)
        assert test['status'] == 'in_progress'
        assert len(test['status_history']) == 1
        assert test['status_history'][0]['from'] == 'pending'
        assert test['status_history'][0]['to'] == 'in_progress'
        assert test['status_history'][0]['agent'] == 'test_agent_1'
        assert test['started_at'] is not None  # Timestamp set

        # Transition to passed
        with db.uat_session() as session:
            update_status_with_history(
                session, test_id, 'passed',
                agent_id='test_agent_1',
                reason='Test completed successfully'
            )
            session.commit()

        # Verify final state
        test = db.get_test_by_id(test_id)
        assert test['status'] == 'passed'
        assert len(test['status_history']) == 2
        assert test['status_history'][1]['from'] == 'in_progress'
        assert test['status_history'][1]['to'] == 'passed'
        assert test['completed_at'] is not None  # Timestamp set


class TestInvalidTransitionBlocked:
    """Test that invalid transitions are rejected."""

    def test_cannot_mark_passed_test_as_failed(self, db, test_test):
        """Test: Cannot transition from passed to failed (terminal state)."""
        test_id = test_test

        # First, move test to passed state
        with db.uat_session() as session:
            update_status_with_history(session, test_id, 'in_progress', agent_id='agent1')
            session.commit()

            update_status_with_history(session, test_id, 'passed', agent_id='agent1')
            session.commit()

        # Try to mark as failed (should be rejected)
        with pytest.raises(ValueError, match="Invalid status transition"):
            with db.uat_session() as session:
                update_status_with_history(
                    session, test_id, 'failed',
                    agent_id='agent2',
                    reason='Trying to mark passed test as failed'
                )
                session.commit()

    def test_cannot_skip_in_progress(self, db, test_test):
        """Test: Cannot go from pending to passed directly."""
        test_id = test_test

        # Try to mark pending test as passed (should be rejected)
        with pytest.raises(ValueError, match="Invalid status transition"):
            with db.uat_session() as session:
                update_status_with_history(
                    session, test_id, 'passed',
                    agent_id='agent1',
                    reason='Trying to skip in_progress'
                )
                session.commit()


class TestFailedRetryFlow:
    """Test retry flow after failure."""

    def test_failed_to_in_progress_retry(self, db, test_test):
        """Test: failed → in_progress (retry after fix)."""
        test_id = test_test

        # Move to in_progress
        with db.uat_session() as session:
            update_status_with_history(session, test_id, 'in_progress', agent_id='agent1')
            session.commit()

        # Mark as failed
        with db.uat_session() as session:
            update_status_with_history(
                session, test_id, 'failed',
                agent_id='agent1',
                reason='Bug detected: Login button not working'
            )
            session.commit()

        # Verify failed state
        test = db.get_test_by_id(test_id)
        assert test['status'] == 'failed'
        assert len(test['status_history']) == 2

        # Retry after fix
        with db.uat_session() as session:
            update_status_with_history(
                session, test_id, 'in_progress',
                agent_id='agent2',
                reason='Retrying after bug fix'
            )
            session.commit()

        # Verify retry worked
        test = db.get_test_by_id(test_id)
        assert test['status'] == 'in_progress'
        assert len(test['status_history']) == 3
        assert test['status_history'][2]['from'] == 'failed'
        assert test['status_history'][2]['to'] == 'in_progress'


class TestNeedsHumanFlow:
    """Test needs-human status flow."""

    def test_in_progress_to_needs_human_to_in_progress(self, db, test_test):
        """Test: in_progress → needs-human → in_progress (blocker resolved)."""
        test_id = test_test

        # Move to in_progress
        with db.uat_session() as session:
            update_status_with_history(session, test_id, 'in_progress', agent_id='agent1')
            session.commit()

        # Detect blocker
        with db.uat_session() as session:
            update_status_with_history(
                session, test_id, 'needs-human',
                agent_id='agent1',
                reason='Blocker: Missing API credentials'
            )
            session.commit()

        # Verify needs-human state
        test = db.get_test_by_id(test_id)
        assert test['status'] == 'needs-human'

        # User resolves blocker
        with db.uat_session() as session:
            update_status_with_history(
                session, test_id, 'in_progress',
                agent_id='system',
                reason='User provided API credentials'
            )
            session.commit()

        # Verify resumed
        test = db.get_test_by_id(test_id)
        assert test['status'] == 'in_progress'
        assert len(test['status_history']) == 3


class TestParkedFlow:
    """Test parked status flow."""

    def test_pending_to_parked_to_in_progress(self, db, test_test):
        """Test: pending → parked → in_progress (skip then retry)."""
        test_id = test_test

        # Park test (skip)
        with db.uat_session() as session:
            update_status_with_history(
                session, test_id, 'parked',
                agent_id='user',
                reason='Test not applicable yet'
            )
            session.commit()

        # Verify parked
        test = db.get_test_by_id(test_id)
        assert test['status'] == 'parked'

        # Retry parked test
        with db.uat_session() as session:
            update_status_with_history(
                session, test_id, 'in_progress',
                agent_id='agent1',
                reason='Retrying parked test'
            )
            session.commit()

        # Verify retry worked
        test = db.get_test_by_id(test_id)
        assert test['status'] == 'in_progress'
        assert len(test['status_history']) == 2


class TestStatusHistoryEntryStructure:
    """Test that status history entries are properly structured."""

    def test_history_entry_structure(self, db, test_test):
        """Test: Each history entry has all required fields."""
        test_id = test_test

        # Make a transition
        with db.uat_session() as session:
            update_status_with_history(
                session, test_id, 'in_progress',
                agent_id='test_agent',
                reason='Test claimed'
            )
            session.commit()

        # Get test and check history
        test = db.get_test_by_id(test_id)
        history = test['status_history']

        assert len(history) == 1
        entry = history[0]

        # Check all required fields exist
        assert 'from' in entry
        assert 'to' in entry
        assert 'at' in entry
        assert 'agent' in entry
        assert 'reason' in entry

        # Check field types
        assert entry['from'] == 'pending'
        assert entry['to'] == 'in_progress'
        assert isinstance(entry['at'], str)  # ISO format timestamp
        assert entry['agent'] == 'test_agent'
        assert entry['reason'] == 'Test claimed'

        # Check timestamp is valid ISO format
        datetime.fromisoformat(entry['at'])  # Should not raise


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v'])
