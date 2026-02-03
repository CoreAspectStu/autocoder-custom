"""
WebSocket Server with Authentication for UAT Gateway

This module provides a WebSocket server that requires authentication for connections.
It supports:
- Token-based authentication
- Connection rejection without valid auth
- Real-time progress updates
- Broadcast to authenticated clients
"""

import asyncio
import logging
import os
from typing import Dict, Optional, Set
import json
import secrets
from datetime import datetime, timedelta

import websockets
from websockets.server import WebSocketServerProtocol


logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails"""
    pass


class WebSocketClient:
    """Represents an authenticated WebSocket client"""

    def __init__(self, websocket: WebSocketServerProtocol, token: str, connected_at: datetime):
        self.websocket = websocket
        self.token = token
        self.connected_at = connected_at
        self.client_id = secrets.token_hex(8)

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging"""
        return {
            "client_id": self.client_id,
            "token": f"{self.token[:8]}..." if len(self.token) > 8 else self.token,
            "connected_at": self.connected_at.isoformat(),
        }


class WebSocketServer:
    """
    WebSocket server with authentication for UAT Gateway

    Authentication is token-based. Clients must provide a valid token
    when connecting, otherwise the connection is rejected.
    """

    # Default token for development (should be overridden by environment)
    DEFAULT_AUTH_TOKEN = "uat-gateway-dev-token"

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8001,
        auth_token: Optional[str] = None,
        message_queue_size: int = 100,
    ):
        """
        Initialize WebSocket server

        Args:
            host: Host to bind to
            port: Port to listen on
            auth_token: Token required for authentication (None = use env or default)
            message_queue_size: Maximum message queue size per client
        """
        self.host = host
        self.port = port
        self.auth_token = auth_token or os.getenv("WEBSOCKET_AUTH_TOKEN", self.DEFAULT_AUTH_TOKEN)
        self.message_queue_size = message_queue_size

        # Track connected clients
        self.clients: Dict[str, WebSocketClient] = {}
        self._server: Optional[websockets.WebSocketServer] = None
        self._shutdown_event = asyncio.Event()

        logger.info(f"WebSocket server initialized on {host}:{port}")
        logger.debug(f"Auth token: {self.auth_token[:8]}..." if len(self.auth_token) > 8 else "Auth token set")

    async def authenticate(self, token: Optional[str]) -> bool:
        """
        Verify authentication token

        Args:
            token: Token to validate

        Returns:
            True if token is valid, False otherwise
        """
        # Handle None or empty tokens
        if not token:
            logger.warning("Authentication failed: No token provided")
            return False

        is_valid = secrets.compare_digest(token, self.auth_token)

        if is_valid:
            logger.debug("Authentication successful")
        else:
            logger.warning(f"Authentication failed with token: {token[:8]}..." if len(token) > 8 else "Authentication failed")

        return is_valid

    async def handle_client(self, websocket: WebSocketServerProtocol):
        """
        Handle a client connection

        This is the main handler for incoming WebSocket connections.
        It authenticates the client and then processes messages.

        Args:
            websocket: WebSocket connection
        """
        client: Optional[WebSocketClient] = None

        try:
            # Step 1: Authenticate the client
            # Client must send auth token as first message
            try:
                # Wait for auth message (timeout after 5 seconds)
                auth_message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                auth_data = json.loads(auth_message)

                token = auth_data.get("token")
                if not token:
                    raise AuthenticationError("No token provided")

                # Verify token
                if not await self.authenticate(token):
                    raise AuthenticationError("Invalid token")

                # Authentication successful
                client = WebSocketClient(
                    websocket=websocket,
                    token=token,
                    connected_at=datetime.now()
                )
                self.clients[client.client_id] = client

                logger.info(f"Client authenticated: {client.client_id}")
                await websocket.send(json.dumps({
                    "type": "authenticated",
                    "client_id": client.client_id,
                    "message": "Authentication successful"
                }))

            except asyncio.TimeoutError:
                raise AuthenticationError("Authentication timeout - no token received")
            except json.JSONDecodeError:
                raise AuthenticationError("Invalid auth message format")

            # Step 2: Process client messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.handle_message(client, data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client {client.client_id}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON format"
                    }))
                except Exception as e:
                    logger.error(f"Error handling message from {client.client_id}: {e}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": str(e)
                    }))

        except AuthenticationError as e:
            # Authentication failed - close connection
            logger.warning(f"Authentication failed: {e}")
            try:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": str(e),
                    "code": "AUTH_FAILED"
                }))
                await websocket.close(code=1008, reason=str(e))
            except Exception:
                pass  # Connection may already be closed

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected normally")

        except Exception as e:
            logger.error(f"Unexpected error with client: {e}")
            try:
                await websocket.close(code=1011, reason="Internal server error")
            except Exception:
                pass

        finally:
            # Clean up client
            if client:
                self.clients.pop(client.client_id, None)
                logger.info(f"Client removed: {client.client_id}")

    async def handle_message(self, client: WebSocketClient, data: Dict):
        """
        Handle a message from a client

        Args:
            client: Client that sent the message
            data: Parsed message data
        """
        message_type = data.get("type")

        if message_type == "ping":
            # Respond to ping with pong
            await client.websocket.send(json.dumps({
                "type": "pong",
                "timestamp": datetime.now().isoformat()
            }))

        elif message_type == "subscribe":
            # Client wants to subscribe to updates
            # (For now, all clients receive all broadcasts)
            await client.websocket.send(json.dumps({
                "type": "subscribed",
                "message": "You will receive all updates"
            }))

        else:
            logger.warning(f"Unknown message type: {message_type}")

    async def broadcast(self, message_type: str, data: Dict):
        """
        Broadcast a message to all authenticated clients

        Args:
            message_type: Type of message (e.g., "progress", "error")
            data: Message data
        """
        if not self.clients:
            logger.debug("No clients connected, skipping broadcast")
            return

        message = json.dumps({
            "type": message_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        })

        # Send to all clients
        disconnected_clients = []
        for client_id, client in self.clients.items():
            try:
                await client.websocket.send(message)
            except Exception as e:
                logger.warning(f"Failed to send to client {client_id}: {e}")
                disconnected_clients.append(client_id)

        # Remove disconnected clients
        for client_id in disconnected_clients:
            self.clients.pop(client_id, None)

        logger.debug(f"Broadcast to {len(self.clients) - len(disconnected_clients)} clients")

    async def send_progress_update(self, journey_name: str, scenario_name: str, progress: float):
        """
        Send a progress update to all clients

        Args:
            journey_name: Name of the journey
            scenario_name: Name of the scenario
            progress: Progress percentage (0-100)
        """
        await self.broadcast("progress", {
            "journey": journey_name,
            "scenario": scenario_name,
            "progress": progress
        })

    async def send_scenario_complete(self, journey_name: str, scenario_name: str, passed: bool):
        """
        Send a scenario completion event to all clients

        Args:
            journey_name: Name of the journey
            scenario_name: Name of the scenario
            passed: Whether the scenario passed
        """
        await self.broadcast("scenario_complete", {
            "journey": journey_name,
            "scenario": scenario_name,
            "passed": passed
        })

    async def send_error(self, error_type: str, message: str, details: Optional[Dict] = None):
        """
        Send an error notification to all clients

        Args:
            error_type: Type of error
            message: Error message
            details: Additional error details
        """
        await self.broadcast("error", {
            "type": error_type,
            "message": message,
            "details": details or {}
        })

    async def start(self):
        """Start the WebSocket server"""
        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")

        self._server = await websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            max_size=self.message_queue_size,
            ping_interval=20,
            ping_timeout=20,
        )

        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")

    async def stop(self):
        """Stop the WebSocket server"""
        logger.info("Stopping WebSocket server...")

        # Close all client connections
        for client in list(self.clients.values()):
            try:
                await client.websocket.close(code=1001, reason="Server shutting down")
            except Exception:
                pass

        self.clients.clear()

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("WebSocket server stopped")

    async def run_until_shutdown(self):
        """Run server until shutdown is requested"""
        await self.start()
        await self._shutdown_event.wait()
        await self.stop()

    def request_shutdown(self):
        """Request server shutdown"""
        self._shutdown_event.set()

    def get_client_count(self) -> int:
        """Get number of connected clients"""
        return len(self.clients)

    def get_clients(self) -> list[Dict]:
        """Get list of connected clients"""
        return [client.to_dict() for client in self.clients.values()]
