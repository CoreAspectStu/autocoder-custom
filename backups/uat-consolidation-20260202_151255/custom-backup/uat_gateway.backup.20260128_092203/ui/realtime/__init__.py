"""
Real-time updates package for UAT Gateway

This package provides WebSocket-based real-time updates for test execution.
"""

from .websocket_server import WebSocketServer, WebSocketClient, AuthenticationError

__all__ = [
    "WebSocketServer",
    "WebSocketClient",
    "AuthenticationError",
]
