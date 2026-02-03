"""
Real-time Event System for UAT Gateway

This module provides WebSocket-based real-time notifications for test execution,
including error events, progress updates, and status changes.

Feature #175: Error notifications are sent immediately via WebSocket events.
"""

import asyncio
import json
from typing import Dict, Any, Optional, Set, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import logging

try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    WebSocketServerProtocol = None


# ============================================================================
# Event Types
# ============================================================================

class EventType(Enum):
    """Types of events that can be broadcast"""
    ERROR = "error"                    # Test failure/error
    PROGRESS = "progress"              # Execution progress update
    STATUS = "status"                  # Overall status change
    JOURNEY_COMPLETE = "journey_complete"  # Journey finished
    SCENARIO_COMPLETE = "scenario_complete"  # Scenario finished
    ORCHESTRATOR_START = "orchestrator_start"  # Cycle started
    ORCHESTRATOR_COMPLETE = "orchestrator_complete"  # Cycle finished
    SUCCESS = "success"                # Feature #231: Successful action completed


class ErrorSeverity(Enum):
    """Severity levels for error events"""
    CRITICAL = "critical"  # Test failure, blocking
    HIGH = "high"          # Significant error
    MEDIUM = "medium"      # Warning-level issue
    LOW = "low"            # Minor issue


# ============================================================================
# Event Data Models
# ============================================================================

@dataclass
class ErrorEvent:
    """Event data for test errors/failures"""
    event_type: str = EventType.ERROR.value
    test_name: str = ""
    error_message: str = ""
    error_stack: Optional[str] = None
    severity: str = ErrorSeverity.HIGH.value
    timestamp: str = ""
    journey_id: Optional[str] = None
    scenario_type: Optional[str] = None
    artifact_paths: Dict[str, str] = None  # screenshot, video, trace

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if self.artifact_paths is None:
            self.artifact_paths = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


@dataclass
class ProgressEvent:
    """Event data for execution progress"""
    event_type: str = EventType.PROGRESS.value
    stage: str = ""  # e.g., "journey_extraction", "test_execution"
    progress: float = 0.0  # 0.0 to 1.0
    message: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


@dataclass
class StatusEvent:
    """Event data for overall status changes"""
    event_type: str = EventType.STATUS.value
    status: str = ""  # "running", "completed", "failed"
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


@dataclass
class SuccessEvent:
    """Event data for successful actions - Feature #231"""
    event_type: str = EventType.SUCCESS.value
    action: str = ""  # e.g., "Test completed", "Card created", "Settings saved"
    message: str = ""  # Clear success message
    entity_type: Optional[str] = None  # e.g., "journey", "scenario", "bug"
    entity_id: Optional[str] = None  # ID of affected entity
    metadata: Dict[str, Any] = None  # Additional context
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


# Union type for all event types
Event = ErrorEvent | ProgressEvent | StatusEvent | SuccessEvent


# ============================================================================
# WebSocket Event Manager
# ============================================================================

class EventManager:
    """
    Manages WebSocket connections and broadcasts events

    This is the main class for real-time notifications. It maintains
    a set of connected WebSocket clients and broadcasts events to all
    connected clients.

    Usage:
        manager = EventManager()

        # Start server (in async context)
        await manager.start(host="localhost", port=8765)

        # Broadcast error event
        manager.broadcast_error(
            test_name="login_test",
            error_message="Assertion failed",
            severity=ErrorSeverity.HIGH
        )

        # Stop server
        await manager.stop()
    """

    def __init__(self, host: str = "localhost", port: int = 8765):
        """
        Initialize event manager

        Args:
            host: Host to bind WebSocket server to
            port: Port to bind WebSocket server to
        """
        self.host = host
        self.port = port
        self.logger = logging.getLogger("event_manager")
        self._clients: Set[WebSocketServerProtocol] = set()
        self._server = None
        self._is_running = False

        # Event handlers (for testing/monitoring)
        self._event_handlers: Dict[EventType, list] = {
            event_type: [] for event_type in EventType
        }

    def is_running(self) -> bool:
        """Check if event manager is running"""
        return self._is_running

    def get_client_count(self) -> int:
        """Get number of connected clients"""
        return len(self._clients)

    # ========================================================================
    # Event Broadcasting Methods
    # ========================================================================

    def broadcast_error(
        self,
        test_name: str,
        error_message: str,
        error_stack: Optional[str] = None,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        journey_id: Optional[str] = None,
        scenario_type: Optional[str] = None,
        artifact_paths: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Broadcast an error event to all connected clients

        Feature #175: This is the main method for sending immediate error notifications

        Note: This method always triggers registered event handlers, even if the
        WebSocket server is not running. This allows for testing and monitoring
        without requiring an active WebSocket connection.

        Args:
            test_name: Name of the test that failed
            error_message: Error message
            error_stack: Optional error stack trace
            severity: Error severity level
            journey_id: Optional journey ID
            scenario_type: Optional scenario type
            artifact_paths: Optional dict of artifact paths (screenshot, video, trace)
        """
        # Create event
        event = ErrorEvent(
            test_name=test_name,
            error_message=error_message,
            error_stack=error_stack,
            severity=severity.value,
            journey_id=journey_id,
            scenario_type=scenario_type,
            artifact_paths=artifact_paths or {}
        )

        # Always broadcast to handlers (even if WebSocket server not running)
        self._broadcast(event)

        if self._is_running:
            self.logger.info(f"✓ Error event broadcast: {test_name} - {error_message}")
        else:
            self.logger.debug(f"Error event sent to handlers: {test_name} - {error_message}")

    def broadcast_progress(
        self,
        stage: str,
        progress: float,
        message: str = ""
    ) -> None:
        """
        Broadcast a progress event to all connected clients

        Note: This method always triggers registered event handlers, even if the
        WebSocket server is not running.

        Args:
            stage: Current execution stage
            progress: Progress percentage (0.0 to 1.0)
            message: Optional progress message
        """
        event = ProgressEvent(
            stage=stage,
            progress=progress,
            message=message
        )

        self._broadcast(event)

        if self._is_running:
            self.logger.debug(f"Progress event broadcast: {stage} - {progress*100:.0f}%")

    def broadcast_status(
        self,
        status: str,
        total_tests: int = 0,
        passed_tests: int = 0,
        failed_tests: int = 0
    ) -> None:
        """
        Broadcast a status event to all connected clients

        Note: This method always triggers registered event handlers, even if the
        WebSocket server is not running.

        Args:
            status: Overall status (running, completed, failed)
            total_tests: Total number of tests
            passed_tests: Number of passed tests
            failed_tests: Number of failed tests
        """
        event = StatusEvent(
            status=status,
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests
        )

        self._broadcast(event)

        if self._is_running:
            self.logger.debug(f"Status event broadcast: {status}")

    def broadcast_success(
        self,
        action: str,
        message: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Broadcast a success event to all connected clients

        Feature #231: Send success notifications for completed actions

        Note: This method always triggers registered event handlers, even if the
        WebSocket server is not running.

        Args:
            action: Action that completed (e.g., "Test completed", "Card created")
            message: Clear success message (e.g., "Login test passed successfully")
            entity_type: Optional entity type (e.g., "journey", "scenario", "bug")
            entity_id: Optional ID of affected entity
            metadata: Optional additional context (e.g., {"duration": 120})
        """
        event = SuccessEvent(
            action=action,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata or {}
        )

        self._broadcast(event)

        if self._is_running:
            self.logger.info(f"✓ Success event broadcast: {action} - {message}")
        else:
            self.logger.debug(f"Success event sent to handlers: {action} - {message}")

    def _broadcast(self, event: Event) -> None:
        """
        Broadcast an event to all connected clients

        Always triggers event handlers, even if no WebSocket clients are connected.
        This allows event handlers to work for testing and monitoring without
        requiring an active WebSocket server.

        Args:
            event: Event to broadcast
        """
        # Convert event to JSON
        event_json = json.dumps(event.to_dict())

        # Broadcast to all WebSocket clients (if any)
        if self._clients:
            disconnected = set()
            for client in self._clients:
                try:
                    # Use asyncio to send asynchronously
                    asyncio.create_task(client.send(event_json))
                except Exception as e:
                    self.logger.warning(f"Failed to send event to client: {e}")
                    disconnected.add(client)

            # Remove disconnected clients
            for client in disconnected:
                self._clients.remove(client)
                self.logger.info(f"Removed disconnected client (remaining: {len(self._clients)})")
        else:
            self.logger.debug("No connected WebSocket clients, only triggering handlers")

        # ALWAYS trigger event handlers (even without WebSocket clients)
        # This allows testing and monitoring without requiring WebSocket server
        event_type = EventType(event.event_type)
        for handler in self._event_handlers[event_type]:
            try:
                handler(event)
            except Exception as e:
                self.logger.error(f"Event handler failed: {e}")

    # ========================================================================
    # Event Handlers (for testing/monitoring)
    # ========================================================================

    def on_error(self, handler: Callable[[ErrorEvent], None]) -> None:
        """Register a handler for error events"""
        self._event_handlers[EventType.ERROR].append(handler)

    def on_progress(self, handler: Callable[[ProgressEvent], None]) -> None:
        """Register a handler for progress events"""
        self._event_handlers[EventType.PROGRESS].append(handler)

    def on_status(self, handler: Callable[[StatusEvent], None]) -> None:
        """Register a handler for status events"""
        self._event_handlers[EventType.STATUS].append(handler)

    def on_success(self, handler: Callable[[SuccessEvent], None]) -> None:
        """Register a handler for success events - Feature #231"""
        self._event_handlers[EventType.SUCCESS].append(handler)

    # ========================================================================
    # WebSocket Server Management
    # ========================================================================

    async def start(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        """
        Start the WebSocket server

        Args:
            host: Optional host override
            port: Optional port override

        Raises:
            RuntimeError: If websockets library is not available
        """
        if not WEBSOCKETS_AVAILABLE:
            raise RuntimeError(
                "websockets library not available. Install with: pip install websockets"
            )

        host = host or self.host
        port = port or self.port

        if self._is_running:
            self.logger.warning("Event manager already running")
            return

        self.logger.info(f"Starting WebSocket server on {host}:{port}")

        async def handler(websocket, path):
            """Handle new WebSocket connections"""
            self._clients.add(websocket)
            self.logger.info(f"Client connected (total: {len(self._clients)})")

            try:
                # Keep connection alive and handle incoming messages
                async for message in websocket:
                    # Could handle client requests here if needed
                    pass
            except websockets.exceptions.ConnectionClosed:
                self.logger.info("Client connection closed")
            finally:
                self._clients.discard(websocket)
                self.logger.info(f"Client removed (remaining: {len(self._clients)})")

        self._server = await websockets.serve(handler, host, port)
        self._is_running = True

        self.logger.info(f"✓ WebSocket server started on ws://{host}:{port}")

    async def stop(self) -> None:
        """Stop the WebSocket server"""
        if not self._is_running:
            return

        self.logger.info("Stopping WebSocket server...")

        # Close all client connections
        for client in self._clients:
            try:
                await client.close()
            except Exception:
                pass

        self._clients.clear()

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        self._is_running = False
        self.logger.info("✓ WebSocket server stopped")


# ============================================================================
# Singleton Instance
# ============================================================================

# Global event manager instance
_event_manager: Optional[EventManager] = None


def get_event_manager() -> EventManager:
    """
    Get the global event manager instance

    Returns:
        EventManager instance
    """
    global _event_manager
    if _event_manager is None:
        _event_manager = EventManager()
    return _event_manager


def reset_event_manager() -> None:
    """Reset the global event manager (for testing)"""
    global _event_manager
    _event_manager = None
