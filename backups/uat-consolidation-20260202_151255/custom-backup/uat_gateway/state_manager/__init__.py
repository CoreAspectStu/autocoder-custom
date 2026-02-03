"""
State Manager Module

Exports:
- StateManager: Main state management class
- ExecutionState: Complete execution state representation
- TestCheckpoint: Checkpoint representation
- CheckpointStatus: Checkpoint status enum
- TestArtifact: Test artifact representation (Feature #78)
"""

from .state_manager import (
    StateManager,
    ExecutionState,
    TestCheckpoint,
    CheckpointStatus,
    TestArtifact
)

__all__ = [
    'StateManager',
    'ExecutionState',
    'TestCheckpoint',
    'CheckpointStatus',
    'TestArtifact'
]
