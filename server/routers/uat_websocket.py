"""
UAT WebSocket Router

Provides real-time updates for UAT test execution via WebSocket.
Supports live progress tracking, test status updates, and agent monitoring.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Set, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/uat", tags=["uat-websocket"])


# ============================================================================
# Connection Manager
# ============================================================================

class UATConnectionManager:
    """Manages WebSocket connections for UAT test cycles."""

    def __init__(self):
        # cycle_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # WebSocket -> cycle_id mapping
        self.connection_cycles: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, cycle_id: str) -> None:
        """Accept and register a WebSocket connection for a cycle."""
        await websocket.accept()

        if cycle_id not in self.active_connections:
            self.active_connections[cycle_id] = set()

        self.active_connections[cycle_id].add(websocket)
        self.connection_cycles[websocket] = cycle_id

        # Send connection confirmation
        await self.send_personal({
            "type": "connected",
            "data": {
                "cycle_id": cycle_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        }, websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        cycle_id = self.connection_cycles.get(websocket)
        if cycle_id and cycle_id in self.active_connections:
            self.active_connections[cycle_id].discard(websocket)
            if not self.active_connections[cycle_id]:
                del self.active_connections[cycle_id]
        self.connection_cycles.pop(websocket, None)

    async def send_personal(self, message: dict, websocket: WebSocket) -> None:
        """Send a message to a specific WebSocket connection."""
        try:
            await websocket.send_json(message)
        except Exception:
            # Connection may be closed
            self.disconnect(websocket)

    async def broadcast_to_cycle(self, cycle_id: str, message: dict) -> None:
        """Broadcast a message to all connections for a cycle."""
        if cycle_id not in self.active_connections:
            return

        # Create a copy of the set to avoid modification during iteration
        connections = list(self.active_connections[cycle_id])
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

    async def broadcast_progress(self, cycle_id: str, stats: dict) -> None:
        """Broadcast progress statistics to all cycle connections."""
        await self.broadcast_to_cycle(cycle_id, {
            "type": "progress_stats",
            "data": {
                **stats,
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    async def broadcast_test_started(self, cycle_id: str, test_id: str, scenario: str, agent_id: str) -> None:
        """Broadcast that a test has started."""
        await self.broadcast_to_cycle(cycle_id, {
            "type": "test_started",
            "data": {
                "test_id": test_id,
                "scenario": scenario,
                "agent_id": agent_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    async def broadcast_test_passed(self, cycle_id: str, test_id: str, scenario: str, duration: float) -> None:
        """Broadcast that a test has passed."""
        await self.broadcast_to_cycle(cycle_id, {
            "type": "test_passed",
            "data": {
                "test_id": test_id,
                "scenario": scenario,
                "duration": duration,
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    async def broadcast_test_failed(self, cycle_id: str, test_id: str, scenario: str, error: str, duration: float) -> None:
        """Broadcast that a test has failed."""
        await self.broadcast_to_cycle(cycle_id, {
            "type": "test_failed",
            "data": {
                "test_id": test_id,
                "scenario": scenario,
                "error": error,
                "duration": duration,
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    async def broadcast_agent_started(self, cycle_id: str, agent_id: str, agent_name: str) -> None:
        """Broadcast that an agent has started."""
        await self.broadcast_to_cycle(cycle_id, {
            "type": "agent_started",
            "data": {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    async def broadcast_agent_stopped(self, cycle_id: str, agent_id: str) -> None:
        """Broadcast that an agent has stopped."""
        await self.broadcast_to_cycle(cycle_id, {
            "type": "agent_stopped",
            "data": {
                "agent_id": agent_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    async def broadcast_cycle_complete(self, cycle_id: str, summary: dict, total_duration: float) -> None:
        """Broadcast that the test cycle is complete."""
        await self.broadcast_to_cycle(cycle_id, {
            "type": "cycle_complete",
            "data": {
                "summary": summary,
                "total_duration": total_duration,
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    async def broadcast_error(self, cycle_id: str, message: str) -> None:
        """Broadcast an error message."""
        await self.broadcast_to_cycle(cycle_id, {
            "type": "error",
            "data": {
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
        })

    def get_active_connections_count(self, cycle_id: Optional[str] = None) -> int:
        """Get the count of active connections, optionally filtered by cycle."""
        if cycle_id:
            return len(self.active_connections.get(cycle_id, set()))
        return sum(len(conns) for conns in self.active_connections.values())


# Global connection manager instance
manager = UATConnectionManager()


# ============================================================================
# In-memory stats storage for progress tracking
# ============================================================================

class UATStatsStore:
    """Simple in-memory store for UAT test statistics."""

    def __init__(self):
        self.stats: Dict[str, dict] = {}

    def get_stats(self, cycle_id: str) -> Optional[dict]:
        """Get stats for a cycle."""
        return self.stats.get(cycle_id)

    def update_stats(self, cycle_id: str, updates: dict) -> None:
        """Update stats for a cycle."""
        if cycle_id not in self.stats:
            self.stats[cycle_id] = {
                "total_tests": 0,
                "passed": 0,
                "failed": 0,
                "running": 0,
                "pending": 0,
                "active_agents": 0
            }
        self.stats[cycle_id].update(updates)

    def reset_stats(self, cycle_id: str) -> None:
        """Reset stats for a cycle."""
        self.stats[cycle_id] = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "running": 0,
            "pending": 0,
            "active_agents": 0
        }


stats_store = UATStatsStore()


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@router.websocket("/ws/uat/{cycle_id}")
async def uat_websocket_endpoint(websocket: WebSocket, cycle_id: str):
    """
    WebSocket endpoint for real-time UAT test updates.

    Connect to: ws://localhost:8000/api/uat/ws/{cycle_id}

    Message Types:
    - connected: Initial connection confirmation
    - test_started: A test has begun execution
    - test_passed: A test has passed
    - test_failed: A test has failed
    - agent_started: An agent has started work
    - agent_stopped: An agent has finished work
    - progress_stats: Periodic progress update
    - cycle_complete: The entire test cycle is complete
    - error: Error notification

    Example message format:
    {
        "type": "test_started",
        "data": {
            "test_id": "123",
            "scenario": "User login journey",
            "agent_id": "agent-1",
            "timestamp": "2026-02-02T10:30:00Z"
        }
    }
    """
    await manager.connect(websocket, cycle_id)

    try:
        # Send initial progress stats if available
        initial_stats = stats_store.get_stats(cycle_id)
        if initial_stats:
            await manager.send_personal({
                "type": "progress_stats",
                "data": initial_stats
            }, websocket)

        # Keep connection alive and handle incoming messages
        while True:
            # Receive and acknowledge any client messages (ping/pong, etc.)
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                # Handle client messages if needed
                if message.get("type") == "ping":
                    await manager.send_personal({
                        "type": "pong",
                        "data": {"timestamp": datetime.utcnow().isoformat()}
                    }, websocket)
                elif message.get("type") == "request_stats":
                    # Client requested fresh stats
                    stats = stats_store.get_stats(cycle_id)
                    if stats:
                        await manager.send_personal({
                            "type": "progress_stats",
                            "data": stats
                        }, websocket)
            except json.JSONDecodeError:
                # Ignore invalid JSON
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        # Send error message before disconnecting
        try:
            await manager.send_personal({
                "type": "error",
                "data": {
                    "message": f"Connection error: {str(e)}",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }, websocket)
        except Exception:
            pass
        manager.disconnect(websocket)


# ============================================================================
# API Endpoints for Connection Management
# ============================================================================

class ConnectionStatsResponse(BaseModel):
    """Response model for connection statistics."""
    total_connections: int
    connections_by_cycle: Dict[str, int]
    active_cycles: list[str]


@router.get("/ws/uat/stats", response_model=ConnectionStatsResponse)
async def get_connection_stats():
    """
    Get statistics about active WebSocket connections.

    Returns:
        - total_connections: Total number of active connections
        - connections_by_cycle: Map of cycle_id to connection count
        - active_cycles: List of cycle IDs with active connections
    """
    connections_by_cycle = {
        cycle_id: len(conns)
        for cycle_id, conns in manager.active_connections.items()
    }

    return ConnectionStatsResponse(
        total_connections=manager.get_active_connections_count(),
        connections_by_cycle=connections_by_cycle,
        active_cycles=list(manager.active_connections.keys())
    )


@router.post("/ws/uat/broadcast/{cycle_id}")
async def broadcast_to_cycle(cycle_id: str, message: dict):
    """
    Manual broadcast endpoint for sending messages to all connections
    for a specific cycle. Useful for testing and external integrations.

    Message format:
    {
        "type": "message_type",
        "data": { ... }
    }
    """
    await manager.broadcast_to_cycle(cycle_id, message)
    return {"status": "broadcast", "cycle_id": cycle_id, "recipients": manager.get_active_connections_count(cycle_id)}


# ============================================================================
# Public API for Broadcasting Events
# ============================================================================

async def broadcast_test_event(cycle_id: str, event_type: str, data: dict) -> bool:
    """
    Public API for broadcasting test events to all connected clients.

    This function can be called from other parts of the application
    to send real-time updates to UAT test monitoring dashboards.

    Args:
        cycle_id: The test cycle identifier
        event_type: Type of event (test_started, test_passed, test_failed, etc.)
        data: Event data

    Returns:
        True if the message was broadcast, False otherwise
    """
    if event_type == "test_started":
        await manager.broadcast_test_started(
            cycle_id,
            data.get("test_id", ""),
            data.get("scenario", ""),
            data.get("agent_id", "")
        )
    elif event_type == "test_passed":
        await manager.broadcast_test_passed(
            cycle_id,
            data.get("test_id", ""),
            data.get("scenario", ""),
            data.get("duration", 0)
        )
    elif event_type == "test_failed":
        await manager.broadcast_test_failed(
            cycle_id,
            data.get("test_id", ""),
            data.get("scenario", ""),
            data.get("error", ""),
            data.get("duration", 0)
        )
    elif event_type == "agent_started":
        await manager.broadcast_agent_started(
            cycle_id,
            data.get("agent_id", ""),
            data.get("agent_name", "")
        )
    elif event_type == "agent_stopped":
        await manager.broadcast_agent_stopped(
            cycle_id,
            data.get("agent_id", "")
        )
    elif event_type == "progress":
        # Update stats store
        stats_store.update_stats(cycle_id, data)
        await manager.broadcast_progress(cycle_id, data)
    elif event_type == "complete":
        await manager.broadcast_cycle_complete(
            cycle_id,
            data.get("summary", {}),
            data.get("total_duration", 0)
        )
    elif event_type == "error":
        await manager.broadcast_error(cycle_id, data.get("message", ""))
    else:
        return False

    return True


# Export the broadcast function for use in other modules
__all__ = ["manager", "broadcast_test_event", "stats_store"]
