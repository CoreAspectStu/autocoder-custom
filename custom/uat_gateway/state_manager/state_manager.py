"""
State Manager Module for UAT Gateway

Provides checkpoint/resume functionality for test execution.
Allows long-running test suites to be interrupted and resumed from the last checkpoint.
"""

import json
import hashlib
import gzip
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import threading
import uuid

import logging

# Add parent directory to path for imports

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import TestExecutionError, handle_errors
from uat_gateway.test_executor.test_executor import TestResult
from uat_gateway.utils.encryption import get_encryption_manager

logger = logging.getLogger(__name__)


class CheckpointStatus(Enum):
    """Status of a checkpoint"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TestArtifact:
    """
    Represents a test artifact (screenshot, video, trace)

    Feature #78: Artifact metadata for reliable storage and retrieval
    """
    artifact_type: str  # 'screenshot', 'video', 'trace'
    path: str
    test_name: str
    timestamp: str
    file_size: int = 0
    exists: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestArtifact':
        """Create artifact from dictionary"""
        return cls(**data)


@dataclass
class TestCheckpoint:
    """
    Represents a checkpoint in test execution

    A checkpoint saves the state at a specific point during test execution,
    allowing resume functionality.

    Feature #78: Now includes artifact tracking for reliable storage
    """
    checkpoint_id: str
    timestamp: str
    test_file: str
    completed_tests: List[str] = field(default_factory=list)
    pending_tests: List[str] = field(default_factory=list)
    test_results: List[Dict[str, Any]] = field(default_factory=list)
    execution_metadata: Dict[str, Any] = field(default_factory=dict)
    status: CheckpointStatus = CheckpointStatus.PENDING
    # Feature #78: Track artifacts at checkpoint level
    artifacts: List[TestArtifact] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert checkpoint to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        # Convert TestArtifact objects to dicts
        data['artifacts'] = [a.to_dict() if isinstance(a, TestArtifact) else a for a in data.get('artifacts', [])]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestCheckpoint':
        """Create checkpoint from dictionary"""
        data['status'] = CheckpointStatus(data['status'])
        # Convert artifact dicts back to TestArtifact objects
        if 'artifacts' in data and data['artifacts']:
            data['artifacts'] = [
                TestArtifact.from_dict(a) if isinstance(a, dict) else a
                for a in data['artifacts']
            ]
        return cls(**data)


@dataclass
class ExecutionState:
    """
    Represents the complete execution state

    Contains all checkpoints and metadata for a test execution session.
    """
    execution_id: str
    start_time: str
    base_url: str
    test_directory: str
    output_directory: str
    checkpoints: List[TestCheckpoint] = field(default_factory=list)
    current_checkpoint_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert execution state to dictionary"""
        return {
            'execution_id': self.execution_id,
            'start_time': self.start_time,
            'base_url': self.base_url,
            'test_directory': self.test_directory,
            'output_directory': self.output_directory,
            'checkpoints': [cp.to_dict() for cp in self.checkpoints],
            'current_checkpoint_index': self.current_checkpoint_index,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionState':
        """Create execution state from dictionary"""
        checkpoints = [
            TestCheckpoint.from_dict(cp_data)
            for cp_data in data.get('checkpoints', [])
        ]
        data['checkpoints'] = checkpoints
        return cls(**data)


@dataclass
class ExecutionRecord:
    """
    Represents a single test execution record in history

    Feature #75: Stores execution history with timestamps and results
    """
    timestamp: str  # ISO 8601 format
    run_id: str  # Unique identifier for this run
    total_tests: int
    passed_tests: int
    failed_tests: int
    pass_rate: float  # 0-100
    duration_ms: int
    results: List[Dict[str, Any]]  # Serialized TestResult objects
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionRecord':
        """Create ExecutionRecord from dictionary"""
        return cls(**data)


@dataclass
class HistoryQuery:
    """
    Query parameters for searching execution history

    Feature #75: Query execution history
    """
    limit: Optional[int] = None  # Max number of results to return
    start_date: Optional[str] = None  # ISO 8601 format
    end_date: Optional[str] = None  # ISO 8601 format
    min_pass_rate: Optional[float] = None  # Minimum pass rate (0-100)
    max_pass_rate: Optional[float] = None  # Maximum pass rate (0-100)


class StateManager:
    """
    Manages execution state and checkpoint/resume functionality

    Responsibilities:
    - Create checkpoints during test execution
    - Save execution state to disk
    - Load execution state from disk
    - Resume execution from last checkpoint
    - Track test progress across checkpoints
    """

    def __init__(self, state_directory: str = "state"):
        """
        Initialize state manager

        Args:
            state_directory: Directory to store state files
        """
        self.state_directory = Path(state_directory)
        self.checkpoints_dir = self.state_directory / "checkpoints"
        self.history_dir = self.state_directory / "history"

        # Create directories if they don't exist
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)

        self.current_state: Optional[ExecutionState] = None
        self.logger = logger

        # Feature #242: Add locks to prevent race conditions
        self._state_lock = threading.Lock()  # Lock for state operations
        self._checkpoint_lock = threading.Lock()  # Lock for checkpoint operations
        self._file_lock = threading.Lock()  # Lock for file I/O operations

    def generate_execution_id(self, test_directory: str) -> str:
        """
        Generate a unique execution ID using UUID to prevent race conditions

        Feature #242: Use UUID instead of timestamp to guarantee uniqueness
        even under high concurrency.

        Args:
            test_directory: Directory containing tests (for reference only)

        Returns:
            Unique execution ID (UUID-based)
        """
        # Use UUID4 for guaranteed uniqueness without requiring coordination
        # This prevents race conditions when multiple threads create states concurrently
        unique_id = uuid.uuid4()

        # Create hash from test directory path for human-readability
        dir_hash = hashlib.md5(test_directory.encode()).hexdigest()[:8]

        return f"exec_{dir_hash}_{unique_id}"

    def create_checkpoint(
        self,
        test_file: str,
        completed_tests: List[str],
        pending_tests: List[str],
        test_results: List[Dict[str, Any]],
        execution_metadata: Optional[Dict[str, Any]] = None
    ) -> TestCheckpoint:
        """
        Create a checkpoint during test execution

        Args:
            test_file: Path to test file
            completed_tests: List of completed test names
            pending_tests: List of pending test names
            test_results: List of test results so far
            execution_metadata: Optional metadata about execution

        Returns:
            Created TestCheckpoint object
        """
        # Feature #242: Use UUID to prevent race conditions in checkpoint creation
        checkpoint_unique_id = uuid.uuid4()
        checkpoint_index = len(self.current_state.checkpoints) if self.current_state else 0
        checkpoint_id = f"checkpoint_{checkpoint_index}_{checkpoint_unique_id}"

        checkpoint = TestCheckpoint(
            checkpoint_id=checkpoint_id,
            timestamp=datetime.now().isoformat(),
            test_file=test_file,
            completed_tests=completed_tests,
            pending_tests=pending_tests,
            test_results=test_results,
            execution_metadata=execution_metadata or {},
            status=CheckpointStatus.COMPLETED
        )

        self.logger.info(f"Created checkpoint {checkpoint_id} with {len(completed_tests)} completed tests")

        return checkpoint

    def save_checkpoint(self, checkpoint: TestCheckpoint) -> str:
        """
        Save checkpoint to disk with encryption for sensitive fields

        Feature #214: Encrypts sensitive test data at rest
        Feature #242: Thread-safe file writing with locks

        Args:
            checkpoint: Checkpoint to save

        Returns:
            Path to saved checkpoint file
        """
        # Feature #242: Use lock to prevent concurrent file writes
        with self._file_lock:
            checkpoint_file = self.checkpoints_dir / f"{checkpoint.checkpoint_id}.json"

            # Convert checkpoint to dictionary
            checkpoint_dict = checkpoint.to_dict()

            # Feature #214: Encrypt sensitive fields
            encryption_manager = get_encryption_manager()
            encrypted_dict = encryption_manager.encrypt_dict(checkpoint_dict, recursive=True)

            with open(checkpoint_file, 'w') as f:
                json.dump(encrypted_dict, f, indent=2)

            self.logger.info(f"Saved checkpoint to {checkpoint_file} (encrypted)")

        return str(checkpoint_file)

    def load_checkpoint(self, checkpoint_id: str) -> Optional[TestCheckpoint]:
        """
        Load checkpoint from disk with decryption for sensitive fields

        Feature #214: Decrypts sensitive test data for authorized users

        Args:
            checkpoint_id: ID of checkpoint to load

        Returns:
            Loaded TestCheckpoint or None if not found or corrupted
        """
        # Feature #82: Validate checkpoint file before attempting to load
        validation = self.validate_checkpoint_file(checkpoint_id)

        if not validation['can_load']:
            self.logger.error(f"Checkpoint {checkpoint_id} validation failed:")
            for error in validation['errors']:
                self.logger.error(f"  - {error}")
            return None

        checkpoint_file = self.checkpoints_dir / f"{checkpoint_id}.json"

        try:
            with open(checkpoint_file, 'r') as f:
                encrypted_data = json.load(f)

            # Feature #214: Decrypt sensitive fields
            encryption_manager = get_encryption_manager()
            decrypted_dict = encryption_manager.decrypt_dict(encrypted_data, recursive=True)

            checkpoint = TestCheckpoint.from_dict(decrypted_dict)
            self.logger.info(f"Loaded checkpoint {checkpoint_id} from disk (decrypted)")

            # Log warnings if any
            if validation.get('warnings'):
                for warning in validation['warnings']:
                    self.logger.warning(f"Checkpoint {checkpoint_id} warning: {warning}")

            return checkpoint

        except Exception as e:
            self.logger.error(f"Failed to load checkpoint {checkpoint_id} despite validation: {e}")
            return None

    def list_checkpoints(self) -> List[str]:
        """
        List all available checkpoint IDs

        Returns:
            List of checkpoint IDs
        """
        checkpoint_files = list(self.checkpoints_dir.glob("checkpoint_*.json"))
        checkpoint_ids = [f.stem for f in checkpoint_files]
        checkpoint_ids.sort()

        return checkpoint_ids

    def get_latest_checkpoint(self) -> Optional[TestCheckpoint]:
        """
        Get the most recent checkpoint

        Returns:
            Latest TestCheckpoint or None if no checkpoints exist
        """
        checkpoint_ids = self.list_checkpoints()

        if not checkpoint_ids:
            return None

        # Get the last checkpoint (most recent)
        latest_id = checkpoint_ids[-1]
        return self.load_checkpoint(latest_id)

    def initialize_execution(
        self,
        test_directory: str,
        base_url: str,
        output_directory: str = "output",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ExecutionState:
        """
        Initialize a new execution state

        Args:
            test_directory: Directory containing tests
            base_url: Base URL for testing
            output_directory: Output directory for artifacts
            metadata: Optional metadata

        Returns:
            Created ExecutionState
        """
        execution_id = self.generate_execution_id(test_directory)

        state = ExecutionState(
            execution_id=execution_id,
            start_time=datetime.now().isoformat(),
            base_url=base_url,
            test_directory=test_directory,
            output_directory=output_directory,
            checkpoints=[],
            current_checkpoint_index=0,
            metadata=metadata or {}
        )

        self.current_state = state
        self.logger.info(f"Initialized execution {execution_id}")

        return state

    def save_state(self, state: ExecutionState) -> str:
        """
        Save execution state to disk with encryption for sensitive fields

        Feature #214: Encrypts sensitive test data at rest
        Feature #242: Thread-safe file writing with locks

        Args:
            state: Execution state to save

        Returns:
            Path to saved state file
        """
        # Feature #242: Use lock to prevent concurrent file writes
        with self._file_lock:
            state_file = self.state_directory / f"{state.execution_id}.json"

            # Convert state to dictionary
            state_dict = state.to_dict()

            # Feature #214: Encrypt sensitive fields
            encryption_manager = get_encryption_manager()
            encrypted_dict = encryption_manager.encrypt_dict(state_dict, recursive=True)

            with open(state_file, 'w') as f:
                json.dump(encrypted_dict, f, indent=2)

            self.logger.info(f"Saved execution state to {state_file} (encrypted)")

            return str(state_file)

    def load_state(self, execution_id: str) -> Optional[ExecutionState]:
        """
        Load execution state from disk with decryption for sensitive fields

        Feature #214: Decrypts sensitive test data for authorized users

        Args:
            execution_id: Execution ID to load

        Returns:
            Loaded ExecutionState or None if not found or corrupted
        """
        # Feature #82: Validate state file before attempting to load
        validation = self.validate_state_file(execution_id)

        if not validation['can_load']:
            self.logger.error(f"State file {execution_id} validation failed:")
            for error in validation['errors']:
                self.logger.error(f"  - {error}")
            return None

        state_file = self.state_directory / f"{execution_id}.json"

        try:
            with open(state_file, 'r') as f:
                encrypted_data = json.load(f)

            # Feature #214: Decrypt sensitive fields
            encryption_manager = get_encryption_manager()
            decrypted_dict = encryption_manager.decrypt_dict(encrypted_data, recursive=True)

            state = ExecutionState.from_dict(decrypted_dict)
            self.current_state = state
            self.logger.info(f"Loaded execution state {execution_id} (decrypted)")

            # Log warnings if any
            if validation.get('warnings'):
                for warning in validation['warnings']:
                    self.logger.warning(f"State {execution_id} warning: {warning}")

            return state

        except Exception as e:
            self.logger.error(f"Failed to load state {execution_id} despite validation: {e}")
            return None

    def load_latest_state(self) -> Optional[ExecutionState]:
        """
        Load the most recent execution state

        Returns:
            Latest ExecutionState or None if no states exist
        """
        state_files = list(self.state_directory.glob("exec_*.json"))

        if not state_files:
            return None

        # Sort by modification time, get most recent
        latest_file = max(state_files, key=lambda f: f.stat().st_mtime)

        execution_id = latest_file.stem
        return self.load_state(execution_id)

    def can_resume(self) -> bool:
        """
        Check if execution can be resumed from a checkpoint

        Returns:
            True if a checkpoint exists for resume
        """
        latest_checkpoint = self.get_latest_checkpoint()
        return latest_checkpoint is not None and len(latest_checkpoint.pending_tests) > 0

    def get_resume_state(self) -> Optional[Dict[str, Any]]:
        """
        Get the state needed to resume execution

        Returns:
            Dictionary with resume information or None if cannot resume
        """
        if not self.can_resume():
            return None

        latest_checkpoint = self.get_latest_checkpoint()

        # Try to get execution_id from current state
        execution_id = None
        if self.current_state:
            execution_id = self.current_state.execution_id
        else:
            # Try to load the latest state file to get execution_id
            state_files = list(self.state_directory.glob("exec_*.json"))
            if state_files:
                # Load the most recent state file
                latest_state_file = max(state_files, key=lambda p: p.stat().st_mtime)
                try:
                    with open(latest_state_file, 'r') as f:
                        state_data = json.load(f)
                        execution_id = state_data.get('execution_id')
                except Exception:
                    pass

        return {
            'checkpoint_id': latest_checkpoint.checkpoint_id,
            'execution_id': execution_id,  # Feature #97: Include execution_id for resume
            'timestamp': latest_checkpoint.timestamp,
            'test_file': latest_checkpoint.test_file,
            'completed_tests': latest_checkpoint.completed_tests,
            'pending_tests': latest_checkpoint.pending_tests,
            'test_results': latest_checkpoint.test_results,
            'execution_metadata': latest_checkpoint.execution_metadata,
            'tests_completed': len(latest_checkpoint.completed_tests),
            'tests_pending': len(latest_checkpoint.pending_tests)
        }

    # ==========================================================================
    # Feature #82: State Validation Methods
    # ==========================================================================

    def validate_state_file(self, execution_id: str) -> Dict[str, Any]:
        """
        Validate state file integrity before loading

        Performs comprehensive validation of state file including:
        - File existence and readability
        - JSON syntax validation
        - Required field presence
        - Data type validation
        - Checkpoint integrity

        Args:
            execution_id: Execution ID to validate

        Returns:
            Dictionary with validation results:
            {
                'valid': bool,
                'errors': List[str],
                'warnings': List[str],
                'file_size': int,
                'can_load': bool
            }
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'file_size': 0,
            'can_load': True
        }

        state_file = self.state_directory / f"{execution_id}.json"

        # Check file existence
        if not state_file.exists():
            result['valid'] = False
            result['can_load'] = False
            result['errors'].append(f"State file not found: {state_file}")
            return result

        # Check file size
        try:
            result['file_size'] = state_file.stat().st_size
            if result['file_size'] == 0:
                result['valid'] = False
                result['can_load'] = False
                result['errors'].append("State file is empty (0 bytes)")
                return result
        except Exception as e:
            result['valid'] = False
            result['can_load'] = False
            result['errors'].append(f"Cannot read file: {e}")
            return result

        # Validate JSON syntax
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            result['valid'] = False
            result['can_load'] = False
            result['errors'].append(f"Invalid JSON syntax: {e.msg} at line {e.lineno}, column {e.colno}")
            return result
        except Exception as e:
            result['valid'] = False
            result['can_load'] = False
            result['errors'].append(f"Cannot read file: {e}")
            return result

        # Validate required fields for ExecutionState
        required_fields = ['execution_id', 'start_time', 'base_url', 'test_directory', 'output_directory']
        for field in required_fields:
            if field not in data:
                result['valid'] = False
                result['errors'].append(f"Missing required field: {field}")

        # Validate data types
        type_checks = {
            'execution_id': str,
            'start_time': str,
            'base_url': str,
            'test_directory': str,
            'output_directory': str,
            'checkpoints': list,
            'current_checkpoint_index': int,
            'metadata': dict
        }

        for field, expected_type in type_checks.items():
            if field in data and not isinstance(data[field], expected_type):
                result['valid'] = False
                result['errors'].append(
                    f"Field '{field}' has wrong type: expected {expected_type.__name__}, got {type(data[field]).__name__}"
                )

        # Validate checkpoints if present
        if 'checkpoints' in data:
            for i, checkpoint_data in enumerate(data['checkpoints']):
                checkpoint_errors = self._validate_checkpoint_data(checkpoint_data, index=i)
                if checkpoint_errors:
                    result['valid'] = False
                    result['errors'].extend([f"Checkpoint {i}: {err}" for err in checkpoint_errors])

        # Determine if file can be loaded despite warnings
        if result['errors']:
            result['can_load'] = False

        return result

    def _validate_checkpoint_data(self, checkpoint_data: Dict[str, Any], index: int = 0) -> List[str]:
        """
        Validate checkpoint data structure

        Args:
            checkpoint_data: Checkpoint dictionary to validate
            index: Checkpoint index for error reporting

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        required_fields = ['checkpoint_id', 'timestamp', 'test_file', 'status']
        for field in required_fields:
            if field not in checkpoint_data:
                errors.append(f"Missing required field: {field}")

        # Validate status enum
        if 'status' in checkpoint_data:
            valid_statuses = ['pending', 'in_progress', 'completed', 'failed']
            if checkpoint_data['status'] not in valid_statuses:
                errors.append(f"Invalid status: {checkpoint_data['status']}")

        # Validate list fields
        list_fields = ['completed_tests', 'pending_tests', 'test_results']
        for field in list_fields:
            if field in checkpoint_data and not isinstance(checkpoint_data[field], list):
                errors.append(f"Field '{field}' must be a list")

        return errors

    def validate_checkpoint_file(self, checkpoint_id: str) -> Dict[str, Any]:
        """
        Validate checkpoint file integrity before loading

        Args:
            checkpoint_id: Checkpoint ID to validate

        Returns:
            Dictionary with validation results:
            {
                'valid': bool,
                'errors': List[str],
                'warnings': List[str],
                'file_size': int,
                'can_load': bool
            }
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'file_size': 0,
            'can_load': True
        }

        checkpoint_file = self.checkpoints_dir / f"{checkpoint_id}.json"

        # Check file existence
        if not checkpoint_file.exists():
            result['valid'] = False
            result['can_load'] = False
            result['errors'].append(f"Checkpoint file not found: {checkpoint_file}")
            return result

        # Check file size
        try:
            result['file_size'] = checkpoint_file.stat().st_size
            if result['file_size'] == 0:
                result['valid'] = False
                result['can_load'] = False
                result['errors'].append("Checkpoint file is empty (0 bytes)")
                return result
        except Exception as e:
            result['valid'] = False
            result['can_load'] = False
            result['errors'].append(f"Cannot read file: {e}")
            return result

        # Validate JSON syntax
        try:
            with open(checkpoint_file, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            result['valid'] = False
            result['can_load'] = False
            result['errors'].append(f"Invalid JSON syntax: {e.msg} at line {e.lineno}, column {e.colno}")
            return result
        except Exception as e:
            result['valid'] = False
            result['can_load'] = False
            result['errors'].append(f"Cannot read file: {e}")
            return result

        # Validate checkpoint structure
        checkpoint_errors = self._validate_checkpoint_data(data)
        if checkpoint_errors:
            result['valid'] = False
            result['errors'].extend(checkpoint_errors)

        # Determine if file can be loaded despite warnings
        if result['errors']:
            result['can_load'] = False

        return result

    # ==========================================================================
    # Feature #78: Artifact Persistence Methods
    # ==========================================================================

    def add_artifacts_to_checkpoint(
        self,
        checkpoint_id: str,
        artifacts: List[TestArtifact]
    ) -> bool:
        """
        Add artifacts to an existing checkpoint

        Args:
            checkpoint_id: ID of checkpoint to update
            artifacts: List of artifacts to add

        Returns:
            True if artifacts were added successfully, False otherwise
        """
        checkpoint = self.load_checkpoint(checkpoint_id)
        if not checkpoint:
            self.logger.error(f"Cannot add artifacts: checkpoint {checkpoint_id} not found")
            return False

        # Add new artifacts
        checkpoint.artifacts.extend(artifacts)
        self.logger.info(f"Added {len(artifacts)} artifacts to checkpoint {checkpoint_id}")

        # Save updated checkpoint
        self.save_checkpoint(checkpoint)
        return True

    def get_artifacts_from_checkpoint(self, checkpoint_id: str) -> List[TestArtifact]:
        """
        Get all artifacts from a checkpoint

        Args:
            checkpoint_id: ID of checkpoint

        Returns:
            List of TestArtifact objects (empty list if checkpoint not found)
        """
        checkpoint = self.load_checkpoint(checkpoint_id)
        if not checkpoint:
            self.logger.warning(f"Cannot get artifacts: checkpoint {checkpoint_id} not found")
            return []

        return checkpoint.artifacts

    def verify_artifact_existence(self, artifact_path: str) -> bool:
        """
        Verify that an artifact file exists on disk

        Args:
            artifact_path: Path to artifact file

        Returns:
            True if file exists and has content, False otherwise
        """
        path = Path(artifact_path)
        if not path.exists():
            self.logger.warning(f"Artifact file does not exist: {artifact_path}")
            return False

        if path.stat().st_size == 0:
            self.logger.warning(f"Artifact file is empty: {artifact_path}")
            return False

        return True

    def verify_all_artifacts(self, checkpoint_id: str) -> Dict[str, Any]:
        """
        Verify all artifacts in a checkpoint exist on disk

        Args:
            checkpoint_id: ID of checkpoint to verify

        Returns:
            Dictionary with verification results:
            {
                'total': int,
                'verified': int,
                'missing': int,
                'artifacts': List[Dict]
            }
        """
        checkpoint = self.load_checkpoint(checkpoint_id)
        if not checkpoint:
            return {
                'total': 0,
                'verified': 0,
                'missing': 0,
                'artifacts': []
            }

        total = len(checkpoint.artifacts)
        verified = 0
        missing = 0
        artifact_details = []

        for artifact in checkpoint.artifacts:
            exists = self.verify_artifact_existence(artifact.path)
            artifact.exists = exists

            if exists:
                verified += 1
                status = "verified"
            else:
                missing += 1
                status = "missing"

            artifact_details.append({
                'type': artifact.artifact_type,
                'path': artifact.path,
                'test_name': artifact.test_name,
                'status': status,
                'file_size': artifact.file_size
            })

        self.logger.info(
            f"Artifact verification for {checkpoint_id}: "
            f"{verified}/{total} verified, {missing} missing"
        )

        return {
            'total': total,
            'verified': verified,
            'missing': missing,
            'artifacts': artifact_details
        }

    def persist_artifacts_from_results(
        self,
        checkpoint_id: str,
        test_results: List[Dict[str, Any]]
    ) -> int:
        """
        Extract and persist artifacts from test results

        Args:
            checkpoint_id: ID of checkpoint to add artifacts to
            test_results: List of test result dictionaries

        Returns:
            Number of artifacts persisted
        """
        artifacts = []

        for result in test_results:
            test_name = result.get('test_name', 'unknown')

            # Extract screenshot artifact
            screenshot_path = result.get('screenshot_path')
            if screenshot_path:
                artifacts.append(self._create_artifact_from_file(
                    artifact_type='screenshot',
                    path=screenshot_path,
                    test_name=test_name
                ))

            # Extract video artifact
            video_path = result.get('video_path')
            if video_path:
                artifacts.append(self._create_artifact_from_file(
                    artifact_type='video',
                    path=video_path,
                    test_name=test_name
                ))

            # Extract trace artifact
            trace_path = result.get('trace_path')
            if trace_path:
                artifacts.append(self._create_artifact_from_file(
                    artifact_type='trace',
                    path=trace_path,
                    test_name=test_name
                ))

            # Extract additional artifacts from 'artifacts' list
            for artifact_dict in result.get('artifacts', []):
                if isinstance(artifact_dict, dict):
                    artifacts.append(TestArtifact(
                        artifact_type=artifact_dict.get('artifact_type', 'unknown'),
                        path=artifact_dict.get('path', ''),
                        test_name=test_name,
                        timestamp=artifact_dict.get('timestamp', datetime.now().isoformat()),
                        file_size=artifact_dict.get('file_size', 0),
                        exists=True
                    ))

        if artifacts:
            self.add_artifacts_to_checkpoint(checkpoint_id, artifacts)

        self.logger.info(f"Persisted {len(artifacts)} artifacts from test results to checkpoint {checkpoint_id}")
        return len(artifacts)

    def _create_artifact_from_file(
        self,
        artifact_type: str,
        path: str,
        test_name: str
    ) -> TestArtifact:
        """
        Create a TestArtifact object from a file path

        Args:
            artifact_type: Type of artifact ('screenshot', 'video', 'trace')
            path: Path to artifact file
            test_name: Name of test that created this artifact

        Returns:
            TestArtifact object with file metadata
        """
        file_path = Path(path)
        file_size = 0
        exists = False
        timestamp = datetime.now().isoformat()

        if file_path.exists():
            file_size = file_path.stat().st_size
            exists = file_size > 0
            timestamp = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()

        return TestArtifact(
            artifact_type=artifact_type,
            path=str(file_path),
            test_name=test_name,
            timestamp=timestamp,
            file_size=file_size,
            exists=exists
        )

    def get_artifact_summary(self, checkpoint_id: str) -> Dict[str, int]:
        """
        Get a summary of artifacts by type for a checkpoint

        Args:
            checkpoint_id: ID of checkpoint

        Returns:
            Dictionary with counts by type:
            {
                'screenshots': int,
                'videos': int,
                'traces': int,
                'total': int
            }
        """
        checkpoint = self.load_checkpoint(checkpoint_id)
        if not checkpoint:
            return {
                'screenshots': 0,
                'videos': 0,
                'traces': 0,
                'total': 0
            }

        screenshots = sum(1 for a in checkpoint.artifacts if a.artifact_type == 'screenshot')
        videos = sum(1 for a in checkpoint.artifacts if a.artifact_type == 'video')
        traces = sum(1 for a in checkpoint.artifacts if a.artifact_type == 'trace')
        total = len(checkpoint.artifacts)

        return {
            'screenshots': screenshots,
            'videos': videos,
            'traces': traces,
            'total': total
        }

    # ==========================================================================
    # Cleanup Methods
    # ==========================================================================

    def cleanup_old_checkpoints(self, keep_count: int = 10):
        """
        Remove old checkpoints, keeping only the most recent ones

        Args:
            keep_count: Number of checkpoints to keep
        """
        checkpoint_files = list(self.checkpoints_dir.glob("checkpoint_*.json"))

        if len(checkpoint_files) <= keep_count:
            return

        # Sort by modification time
        checkpoint_files.sort(key=lambda f: f.stat().st_mtime)

        # Remove oldest checkpoints
        to_remove = checkpoint_files[:-keep_count]

        for file in to_remove:
            file.unlink()
            self.logger.info(f"Removed old checkpoint: {file.name}")

    def cleanup_old_states(self, keep_count: int = 5):
        """
        Remove old execution states, keeping only the most recent ones

        Args:
            keep_count: Number of states to keep
        """
        state_files = list(self.state_directory.glob("exec_*.json"))

        # Filter out checkpoint files
        state_files = [f for f in state_files if f.name.startswith("exec_")]

        if len(state_files) <= keep_count:
            return

        # Sort by modification time
        state_files.sort(key=lambda f: f.stat().st_mtime)

        # Remove oldest states
        to_remove = state_files[:-keep_count]

        for file in to_remove:
            file.unlink()
            self.logger.info(f"Removed old state: {file.name}")

    def compress_old_states(self, days_threshold: int = 7, keep_count: int = 3):
        """
        Compress execution states older than specified days to save space

        Args:
            days_threshold: Compress states older than this many days
            keep_count: Always keep this many of the most recent states uncompressed

        Returns:
            Number of states compressed
        """
        state_files = list(self.state_directory.glob("exec_*.json"))

        # Filter out already compressed files and checkpoint files
        state_files = [f for f in state_files if not f.name.endswith('.json.gz')]
        state_files = [f for f in state_files if f.name.startswith("exec_")]

        if len(state_files) <= keep_count:
            self.logger.info("Not enough states to compress (at or below keep_count)")
            return 0

        # Sort by modification time (newest first)
        state_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # Keep the most recent 'keep_count' files uncompressed
        files_to_check = state_files[keep_count:]
        compressed_count = 0
        cutoff_time = datetime.now() - timedelta(days=days_threshold)

        for state_file in files_to_check:
            # Check file age
            file_mtime = datetime.fromtimestamp(state_file.stat().st_mtime)

            if file_mtime < cutoff_time:
                try:
                    # Compress the file
                    compressed_file = self._compress_file(state_file)
                    compressed_count += 1
                    self.logger.info(f"Compressed old state: {state_file.name} -> {compressed_file.name}")
                except Exception as e:
                    self.logger.error(f"Failed to compress {state_file.name}: {e}")
            else:
                self.logger.debug(f"Skipping recent state: {state_file.name} (age: {(datetime.now() - file_mtime).days} days)")

        return compressed_count

    def _compress_file(self, file_path: Path) -> Path:
        """
        Compress a single file using gzip

        Args:
            file_path: Path to file to compress

        Returns:
            Path to compressed file
        """
        compressed_path = Path(str(file_path) + '.gz')

        with open(file_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Remove original file after successful compression
        file_path.unlink()

        return compressed_path

    def load_state_compressed(self, execution_id: str) -> Optional[ExecutionState]:
        """
        Load execution state from disk (handles both compressed and uncompressed)

        Args:
            execution_id: Execution ID to load

        Returns:
            Loaded ExecutionState or None if not found or corrupted
        """
        # Try compressed version first
        compressed_file = self.state_directory / f"{execution_id}.json.gz"

        if compressed_file.exists():
            try:
                with gzip.open(compressed_file, 'rt') as f:
                    data = json.load(f)

                state = ExecutionState.from_dict(data)
                self.current_state = state
                self.logger.info(f"Loaded compressed execution state {execution_id}")

                return state

            except json.JSONDecodeError as e:
                self.logger.error(f"Compressed state file {execution_id} is corrupted: {e}")
                return None
            except Exception as e:
                self.logger.error(f"Failed to load compressed state {execution_id}: {e}")
                return None

        # Fall back to uncompressed version
        return self.load_state(execution_id)

    def get_compression_stats(self) -> Dict[str, Any]:
        """
        Get statistics about compressed vs uncompressed states

        Returns:
            Dictionary with compression statistics
        """
        all_state_files = list(self.state_directory.glob("exec_*.json*"))

        uncompressed_count = 0
        compressed_count = 0
        uncompressed_size = 0
        compressed_size = 0

        for file_path in all_state_files:
            if file_path.name.endswith('.gz'):
                compressed_count += 1
                compressed_size += file_path.stat().st_size
            else:
                uncompressed_count += 1
                uncompressed_size += file_path.stat().st_size

        total_size = uncompressed_size + compressed_size
        compression_ratio = (1 - (compressed_size / (uncompressed_size + compressed_size + 1))) * 100 if total_size > 0 else 0

        return {
            'total_states': uncompressed_count + compressed_count,
            'uncompressed_count': uncompressed_count,
            'compressed_count': compressed_count,
            'uncompressed_size_bytes': uncompressed_size,
            'compressed_size_bytes': compressed_size,
            'total_size_bytes': total_size,
            'compression_ratio_percent': round(compression_ratio, 2),
            'space_saved_bytes': uncompressed_size - compressed_size if compressed_count > 0 else 0
        }

    # ==========================================================================
    # Feature #80: State Export for Debugging
    # ==========================================================================

    def export_state(
        self,
        state: Optional[ExecutionState] = None,
        output_path: Optional[str] = None
    ) -> str:
        """
        Export execution state to a human-readable JSON file for debugging

        Creates a comprehensive export of the current execution state including
        all checkpoints, test results, and metadata. Useful for manual inspection
        and debugging of test execution issues.

        Args:
            state: ExecutionState to export (uses current_state if None)
            output_path: Path for export file (auto-generated if None)

        Returns:
            Path to the exported JSON file
        """
        # Use current state if not provided
        if state is None:
            state = self.current_state

        if state is None:
            raise ValueError("No state to export. Initialize or load a state first.")

        # Generate output path if not provided
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(self.state_directory / f"export_{state.execution_id}_{timestamp}.json")

        output_file = Path(output_path)

        # Create parent directories if needed
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Prepare export data with enhanced debugging information
        export_data = {
            'export_metadata': {
                'exported_at': datetime.now().isoformat(),
                'exported_by': 'StateManager.export_state()',
                'execution_id': state.execution_id,
                'state_file': str(self.state_directory / f"{state.execution_id}.json")
            },
            'execution': {
                'execution_id': state.execution_id,
                'start_time': state.start_time,
                'base_url': state.base_url,
                'test_directory': state.test_directory,
                'output_directory': state.output_directory,
                'current_checkpoint_index': state.current_checkpoint_index,
                'metadata': state.metadata
            },
            'checkpoints': [],
            'summary': self._generate_export_summary(state)
        }

        # Add detailed checkpoint information
        for checkpoint in state.checkpoints:
            checkpoint_data = checkpoint.to_dict()

            # Add additional debugging information
            checkpoint_data['debug_info'] = {
                'completed_count': len(checkpoint.completed_tests),
                'pending_count': len(checkpoint.pending_tests),
                'total_tests': len(checkpoint.completed_tests) + len(checkpoint.pending_tests),
                'results_count': len(checkpoint.test_results),
                'checkpoint_file': str(self.checkpoints_dir / f"{checkpoint.checkpoint_id}.json")
            }

            # Add test results summary
            if checkpoint.test_results:
                passed = sum(1 for r in checkpoint.test_results if r.get('status') == 'passed')
                failed = sum(1 for r in checkpoint.test_results if r.get('status') == 'failed')
                skipped = sum(1 for r in checkpoint.test_results if r.get('status') == 'skipped')

                checkpoint_data['debug_info']['results_summary'] = {
                    'passed': passed,
                    'failed': failed,
                    'skipped': skipped,
                    'total': len(checkpoint.test_results)
                }

            export_data['checkpoints'].append(checkpoint_data)

        # Write export file with pretty formatting
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Exported state to {output_file}")

        return str(output_file)

    def _generate_export_summary(self, state: ExecutionState) -> Dict[str, Any]:
        """
        Generate a summary of the execution state for the export

        Args:
            state: ExecutionState to summarize

        Returns:
            Dictionary with summary information
        """
        total_checkpoints = len(state.checkpoints)

        # Aggregate test statistics across all checkpoints
        total_completed = 0
        total_pending = 0
        total_results = 0
        total_passed = 0
        total_failed = 0

        for checkpoint in state.checkpoints:
            total_completed += len(checkpoint.completed_tests)
            total_pending += len(checkpoint.pending_tests)
            total_results += len(checkpoint.test_results)

            for result in checkpoint.test_results:
                if result.get('status') == 'passed':
                    total_passed += 1
                elif result.get('status') == 'failed':
                    total_failed += 1

        # Calculate pass rate
        pass_rate = (total_passed / total_results * 100) if total_results > 0 else 0

        return {
            'total_checkpoints': total_checkpoints,
            'total_completed_tests': total_completed,
            'total_pending_tests': total_pending,
            'total_test_results': total_results,
            'total_passed': total_passed,
            'total_failed': total_failed,
            'pass_rate_percent': round(pass_rate, 2),
            'execution_duration_minutes': self._calculate_execution_duration(state)
        }

    def _calculate_execution_duration(self, state: ExecutionState) -> float:
        """
        Calculate execution duration in minutes

        Args:
            state: ExecutionState

        Returns:
            Duration in minutes
        """
        try:
            start = datetime.fromisoformat(state.start_time)
            end = datetime.now()

            duration = (end - start).total_seconds() / 60  # Convert to minutes
            return round(duration, 2)
        except Exception:
            return 0.0

    # ========================================================================
    # Execution History Methods (Feature #75)
    # ========================================================================

    @handle_errors(component="state_manager", reraise=True)
    def save_execution_record(
        self,
        results: List[TestResult],
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ExecutionRecord:
        """
        Save an execution record to history

        Feature #75: "Verify run is recorded"
        Feature #75: "Verify timestamp is saved"
        Feature #75: "Verify results are saved"

        Args:
            results: List of test results from this execution
            run_id: Optional unique identifier for this run (auto-generated if None)
            metadata: Optional metadata to attach to the record

        Returns:
            ExecutionRecord that was saved

        Raises:
            TestExecutionError: If save fails
        """
        # Generate run ID if not provided
        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Calculate metrics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.passed)
        failed_tests = total_tests - passed_tests
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0.0
        duration_ms = sum(r.duration_ms for r in results)

        # Create timestamp
        timestamp = datetime.now().isoformat()

        # Serialize test results
        results_data = [r.to_dict() for r in results]

        # Create execution record
        record = ExecutionRecord(
            timestamp=timestamp,
            run_id=run_id,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            pass_rate=pass_rate,
            duration_ms=duration_ms,
            results=results_data,
            metadata=metadata or {}
        )

        # Save to file
        file_path = self.history_dir / f"execution-{run_id}.json"
        try:
            with open(file_path, 'w') as f:
                json.dump(record.to_dict(), f, indent=2)

            self.logger.info(f"Saved execution record: {file_path}")
            self.logger.info(
                f"  Tests: {passed_tests}/{total_tests} passed ({pass_rate:.1f}%)"
            )

        except Exception as e:
            raise TestExecutionError(
                f"Failed to save execution record: {str(e)}",
                component="state_manager"
            )

        return record

    @handle_errors(component="state_manager", reraise=True)
    def load_execution_record(self, run_id: str) -> Optional[ExecutionRecord]:
        """
        Load an execution record from history

        Feature #75: "Verify history is queryable"

        Args:
            run_id: Unique identifier for the run

        Returns:
            ExecutionRecord if found, None otherwise
        """
        file_path = self.history_dir / f"execution-{run_id}.json"

        if not file_path.exists():
            self.logger.warning(f"Execution record not found: {run_id}")
            return None

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            record = ExecutionRecord.from_dict(data)
            self.logger.info(f"Loaded execution record: {run_id}")

            return record

        except json.JSONDecodeError as e:
            self.logger.error(f"Corrupted execution record: {run_id} - {str(e)}")
            # Handle corrupted state gracefully
            return None

        except Exception as e:
            self.logger.error(f"Failed to load execution record: {run_id} - {str(e)}")
            return None

    @handle_errors(component="state_manager", reraise=False)
    def query_history(self, query: HistoryQuery) -> List[ExecutionRecord]:
        """
        Query execution history with filters

        Feature #75: "Verify history is queryable"

        Args:
            query: HistoryQuery object with filter parameters

        Returns:
            List of ExecutionRecords matching the query
        """
        self.logger.info("Querying execution history...")

        records = []

        # Load all history files
        for file_path in self.history_dir.glob("execution-*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)

                record = ExecutionRecord.from_dict(data)

                # Apply filters
                if query.start_date:
                    if record.timestamp < query.start_date:
                        continue

                if query.end_date:
                    if record.timestamp > query.end_date:
                        continue

                if query.min_pass_rate is not None:
                    if record.pass_rate < query.min_pass_rate:
                        continue

                if query.max_pass_rate is not None:
                    if record.pass_rate > query.max_pass_rate:
                        continue

                records.append(record)

            except json.JSONDecodeError as e:
                self.logger.error(
                    f"Corrupted history file: {file_path.name} - {str(e)}"
                )
                # Skip corrupted files (graceful degradation)

            except Exception as e:
                self.logger.error(
                    f"Error reading history file: {file_path.name} - {str(e)}"
                )

        # Sort by timestamp (newest first)
        records.sort(key=lambda r: r.timestamp, reverse=True)

        # Apply limit
        if query.limit:
            records = records[:query.limit]

        self.logger.info(f"Found {len(records)} records matching query")

        return records

    @handle_errors(component="state_manager", reraise=False)
    def get_latest_execution(self) -> Optional[ExecutionRecord]:
        """
        Get the most recent execution record

        Returns:
            Most recent ExecutionRecord, or None if no history exists
        """
        query = HistoryQuery(limit=1)
        results = self.query_history(query)

        return results[0] if results else None

    @handle_errors(component="state_manager", reraise=False)
    def get_execution_stats(self) -> Dict[str, Any]:
        """
        Get statistics about execution history

        Returns:
            Dictionary with execution statistics
        """
        records = self.query_history(HistoryQuery())

        if not records:
            return {
                "total_executions": 0,
                "avg_pass_rate": 0.0,
                "best_pass_rate": 0.0,
                "worst_pass_rate": 0.0,
                "total_tests_run": 0
            }

        total_executions = len(records)
        avg_pass_rate = sum(r.pass_rate for r in records) / total_executions
        best_pass_rate = max(r.pass_rate for r in records)
        worst_pass_rate = min(r.pass_rate for r in records)
        total_tests_run = sum(r.total_tests for r in records)

        stats = {
            "total_executions": total_executions,
            "avg_pass_rate": round(avg_pass_rate, 1),
            "best_pass_rate": round(best_pass_rate, 1),
            "worst_pass_rate": round(worst_pass_rate, 1),
            "total_tests_run": total_tests_run
        }

        self.logger.info(f"Execution stats: {stats}")

        return stats

    @handle_errors(component="state_manager", reraise=False)
    def cleanup_old_history(self, keep_last_n: int = 50) -> int:
        """
        Clean up old history files, keeping only the most recent N

        Feature #75: "Cleans up old state files"

        Args:
            keep_last_n: Number of recent history files to keep

        Returns:
            Number of files deleted
        """
        self.logger.info(f"Cleaning up old history (keeping last {keep_last_n})...")

        # Get all history files sorted by modification time (newest first)
        history_files = sorted(
            self.history_dir.glob("execution-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        # Keep only the most recent N files
        files_to_delete = history_files[keep_last_n:]

        deleted_count = 0
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                deleted_count += 1
                self.logger.debug(f"Deleted old history file: {file_path.name}")

            except Exception as e:
                self.logger.error(f"Failed to delete {file_path.name}: {str(e)}")

        self.logger.info(f"Cleaned up {deleted_count} old history files")

        return deleted_count

    @handle_errors(component="state_manager", reraise=False)
    def clear_history(self) -> int:
        """
        Clear all execution history

        Returns:
            Number of files deleted
        """
        self.logger.warning("Clearing all execution history...")

        deleted_count = 0
        for file_path in self.history_dir.glob("execution-*.json"):
            try:
                file_path.unlink()
                deleted_count += 1

            except Exception as e:
                self.logger.error(f"Failed to delete {file_path.name}: {str(e)}")

        self.logger.warning(f"Cleared {deleted_count} history files")

        return deleted_count

    # ========================================================================
    # Feature #274: Journey Cleanup Methods
    # ========================================================================

    @handle_errors(component="state_manager", reraise=False, default_return=0)
    def remove_checkpoints_by_journey(self, journey_id: str) -> int:
        """
        Remove all checkpoints that reference a specific journey (Feature #274)

        This cleans up orphaned checkpoint data when a journey is deleted.

        Args:
            journey_id: Journey ID to search for in checkpoints

        Returns:
            Number of checkpoints removed
        """
        self.logger.info(f"Removing checkpoints for journey {journey_id}")

        removed_count = 0
        checkpoint_files = list(self.checkpoints_dir.glob("checkpoint_*.json"))

        for checkpoint_file in checkpoint_files:
            try:
                # Load checkpoint to check if it references the journey
                with open(checkpoint_file, 'r') as f:
                    checkpoint_data = json.load(f)

                # Check if journey_id is referenced in checkpoint
                checkpoint_json = json.dumps(checkpoint_data)
                if journey_id in checkpoint_json:
                    # Check if this is an archived card (acceptable) or active reference (not acceptable)
                    is_archived = checkpoint_data.get('status') == 'archived'

                    if not is_archived:
                        # Remove checkpoint file
                        checkpoint_file.unlink()
                        removed_count += 1
                        self.logger.debug(
                            f"Removed checkpoint {checkpoint_file.name} "
                            f"referencing journey {journey_id}"
                        )

            except Exception as e:
                self.logger.error(
                    f"Failed to process checkpoint {checkpoint_file.name}: {str(e)}"
                )

        self.logger.info(
            f"Removed {removed_count} checkpoints for journey {journey_id}"
        )

        return removed_count

    @handle_errors(component="state_manager", reraise=False, default_return=0)
    def remove_journey_references_from_execution(
        self,
        execution_id: str,
        journey_id: str
    ) -> int:
        """
        Remove journey references from an execution state (Feature #274)

        This cleans up orphaned journey references in execution checkpoints.

        Args:
            execution_id: Execution ID to clean up
            journey_id: Journey ID to remove references to

        Returns:
            Number of checkpoints cleaned up
        """
        self.logger.info(
            f"Removing journey {journey_id} references from execution {execution_id}"
        )

        # Load execution state
        state = self.load_state(execution_id)
        if not state:
            self.logger.warning(f"Execution {execution_id} not found")
            return 0

        # Filter out checkpoints that reference the journey
        original_count = len(state.checkpoints)
        filtered_checkpoints = []

        for checkpoint in state.checkpoints:
            # Check if checkpoint references the journey
            checkpoint_json = json.dumps(checkpoint.to_dict())
            if journey_id not in checkpoint_json:
                # Keep checkpoint that doesn't reference the journey
                filtered_checkpoints.append(checkpoint)
            else:
                self.logger.debug(
                    f"Removing checkpoint {checkpoint.checkpoint_id} "
                    f"referencing journey {journey_id}"
                )

        # Update state if checkpoints were removed
        if len(filtered_checkpoints) < original_count:
            state.checkpoints = filtered_checkpoints
            state.updated_at = datetime.now(timezone.utc)

            # Save updated state
            self.save_state(state)

            removed_count = original_count - len(filtered_checkpoints)
            self.logger.info(
                f"Removed {removed_count} journey references from execution {execution_id}"
            )

            return removed_count
        else:
            self.logger.debug(
                f"No journey {journey_id} references found in execution {execution_id}"
            )
            return 0
