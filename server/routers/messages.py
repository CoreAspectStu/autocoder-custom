"""
Messages Router
===============

API endpoints for bidirectional human-agent communication.
Enables the Chrome extension to send guidance and receive requests from the agent.
"""

import asyncio
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Add root to path for registry import
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from registry import get_project_path as registry_get_project_path


router = APIRouter(prefix="/api/projects/{project_name}", tags=["messages"])


# ============================================================================
# Data Models
# ============================================================================


class MessageContext(BaseModel):
    """Context about where the message was sent from."""
    url: Optional[str] = None
    title: Optional[str] = None
    screenshot_id: Optional[str] = None
    element_selector: Optional[str] = None


class HumanMessage(BaseModel):
    """Message from human to agent."""
    type: Literal["guidance", "answer", "auth", "stop"] = "guidance"
    content: str
    context: Optional[MessageContext] = None


class AgentRequest(BaseModel):
    """Request from agent to human."""
    id: str
    type: Literal["auth_needed", "direction_needed", "confirmation", "info"]
    message: str
    created_at: str
    responded: bool = False
    response: Optional[str] = None


class MessageResponse(BaseModel):
    """Response after sending a message."""
    id: str
    created_at: str
    type: str
    content: str
    direction: Literal["sent", "received"] = "sent"


class ScreenshotUpload(BaseModel):
    """Screenshot upload from extension."""
    image: str  # Base64 data URL
    url: Optional[str] = None
    title: Optional[str] = None
    timestamp: str


# ============================================================================
# In-Memory Storage (could be replaced with SQLite for persistence)
# ============================================================================


class MessageStore:
    """Thread-safe in-memory storage for messages and requests."""

    def __init__(self):
        self._messages: dict[str, list[dict]] = {}  # project_name -> messages
        self._requests: dict[str, list[dict]] = {}  # project_name -> requests
        self._screenshots: dict[str, list[dict]] = {}  # project_name -> screenshots
        self._callbacks: dict[str, list] = {}  # project_name -> callbacks
        self._lock = asyncio.Lock()

    async def add_message(self, project: str, message: dict) -> dict:
        """Add a message to the store."""
        async with self._lock:
            if project not in self._messages:
                self._messages[project] = []

            msg = {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now().isoformat(),
                **message,
            }
            self._messages[project].append(msg)

            # Keep only last 100 messages
            if len(self._messages[project]) > 100:
                self._messages[project] = self._messages[project][-100:]

            # Notify callbacks
            await self._notify_callbacks(project, "message", msg)

            return msg

    async def get_messages(self, project: str, limit: int = 50) -> list[dict]:
        """Get recent messages for a project."""
        async with self._lock:
            messages = self._messages.get(project, [])
            return messages[-limit:]

    async def add_request(self, project: str, request: dict) -> dict:
        """Add an agent request."""
        async with self._lock:
            if project not in self._requests:
                self._requests[project] = []

            req = {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now().isoformat(),
                "responded": False,
                "response": None,
                **request,
            }
            self._requests[project].append(req)

            # Notify callbacks
            await self._notify_callbacks(project, "request", req)

            return req

    async def get_requests(self, project: str, pending_only: bool = False) -> list[dict]:
        """Get requests for a project."""
        async with self._lock:
            requests = self._requests.get(project, [])
            if pending_only:
                return [r for r in requests if not r["responded"]]
            return requests

    async def respond_to_request(self, project: str, request_id: str, response: str) -> Optional[dict]:
        """Respond to an agent request."""
        async with self._lock:
            requests = self._requests.get(project, [])
            for req in requests:
                if req["id"] == request_id:
                    req["responded"] = True
                    req["response"] = response
                    req["responded_at"] = datetime.now().isoformat()

                    # Notify callbacks
                    await self._notify_callbacks(project, "response", req)

                    return req
            return None

    async def add_screenshot(self, project: str, screenshot: dict) -> dict:
        """Add a screenshot."""
        async with self._lock:
            if project not in self._screenshots:
                self._screenshots[project] = []

            ss = {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now().isoformat(),
                **screenshot,
            }
            self._screenshots[project].append(ss)

            # Keep only last 20 screenshots
            if len(self._screenshots[project]) > 20:
                self._screenshots[project] = self._screenshots[project][-20:]

            return ss

    async def get_screenshots(self, project: str) -> list[dict]:
        """Get screenshots for a project."""
        async with self._lock:
            return self._screenshots.get(project, [])

    def add_callback(self, project: str, callback):
        """Add a callback for message events."""
        if project not in self._callbacks:
            self._callbacks[project] = []
        self._callbacks[project].append(callback)

    def remove_callback(self, project: str, callback):
        """Remove a callback."""
        if project in self._callbacks:
            self._callbacks[project] = [c for c in self._callbacks[project] if c != callback]

    async def _notify_callbacks(self, project: str, event_type: str, data: dict):
        """Notify all callbacks for a project."""
        callbacks = self._callbacks.get(project, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_type, data)
                else:
                    callback(event_type, data)
            except Exception as e:
                print(f"Callback error: {e}")


# Global store instance
message_store = MessageStore()


# ============================================================================
# Helper Functions
# ============================================================================


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name."""
    if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', name):
        raise HTTPException(status_code=400, detail="Invalid project name")
    return name


def get_project_dir(project_name: str) -> Path:
    """Get project directory path."""
    project_name = validate_project_name(project_name)
    project_dir = registry_get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")

    return project_dir


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/messages", response_model=MessageResponse)
async def send_message(project_name: str, message: HumanMessage) -> MessageResponse:
    """
    Send a message from human to agent.

    Message types:
    - guidance: General direction or guidance for the agent
    - answer: Response to an agent question
    - auth: Authentication key or credentials
    - stop: Request to stop the agent
    """
    get_project_dir(project_name)  # Validate project exists

    msg = await message_store.add_message(project_name, {
        "type": message.type,
        "content": message.content,
        "context": message.context.model_dump() if message.context else None,
        "direction": "sent",
    })

    return MessageResponse(
        id=msg["id"],
        created_at=msg["created_at"],
        type=msg["type"],
        content=msg["content"],
        direction="sent",
    )


@router.get("/messages")
async def get_messages(project_name: str, limit: int = 50) -> list[dict]:
    """Get recent messages for a project."""
    get_project_dir(project_name)
    return await message_store.get_messages(project_name, limit)


@router.get("/requests")
async def get_requests(project_name: str, pending_only: bool = False) -> list[dict]:
    """
    Get agent requests for a project.

    Set pending_only=true to only get unanswered requests.
    """
    get_project_dir(project_name)
    return await message_store.get_requests(project_name, pending_only)


@router.post("/requests/{request_id}/respond")
async def respond_to_request(project_name: str, request_id: str, response: dict) -> dict:
    """Respond to an agent request."""
    get_project_dir(project_name)

    content = response.get("response", "")
    if not content:
        raise HTTPException(status_code=400, detail="Response content required")

    result = await message_store.respond_to_request(project_name, request_id, content)
    if not result:
        raise HTTPException(status_code=404, detail="Request not found")

    return result


@router.post("/screenshots")
async def upload_screenshot(project_name: str, screenshot: ScreenshotUpload) -> dict:
    """Upload a screenshot from the extension."""
    get_project_dir(project_name)

    # Validate image data
    if not screenshot.image.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Invalid image data")

    ss = await message_store.add_screenshot(project_name, {
        "image": screenshot.image,
        "url": screenshot.url,
        "title": screenshot.title,
        "timestamp": screenshot.timestamp,
    })

    return {"id": ss["id"], "created_at": ss["created_at"]}


@router.get("/screenshots")
async def get_screenshots(project_name: str) -> list[dict]:
    """Get screenshots for a project (without image data)."""
    get_project_dir(project_name)
    screenshots = await message_store.get_screenshots(project_name)

    # Return without full image data (just metadata)
    return [
        {
            "id": ss["id"],
            "url": ss.get("url"),
            "title": ss.get("title"),
            "created_at": ss["created_at"],
            "has_image": bool(ss.get("image")),
        }
        for ss in screenshots
    ]


@router.get("/screenshots/{screenshot_id}")
async def get_screenshot(project_name: str, screenshot_id: str) -> dict:
    """Get a specific screenshot with image data."""
    get_project_dir(project_name)
    screenshots = await message_store.get_screenshots(project_name)

    for ss in screenshots:
        if ss["id"] == screenshot_id:
            return ss

    raise HTTPException(status_code=404, detail="Screenshot not found")


class AgentMessage(BaseModel):
    """Message from agent to human."""
    type: Literal["response", "question", "status", "error"] = "response"
    content: str


@router.post("/agent-messages")
async def send_agent_message(project_name: str, message: AgentMessage) -> dict:
    """
    Send a message from agent to human.

    This endpoint is called by the agent to communicate with the human.
    Messages will appear in the Chrome extension and trigger notifications.
    """
    get_project_dir(project_name)  # Validate project exists

    msg = await message_store.add_message(project_name, {
        "type": message.type,
        "content": message.content,
        "direction": "received",
    })

    return {"id": msg["id"], "created_at": msg["created_at"]}


# ============================================================================
# Agent Integration
# ============================================================================


async def create_agent_request(
    project_name: str,
    request_type: str,
    message: str,
) -> dict:
    """
    Create an agent request (called from agent code).

    Args:
        project_name: Name of the project
        request_type: Type of request (auth_needed, direction_needed, etc.)
        message: The message/question for the human

    Returns:
        The created request object
    """
    return await message_store.add_request(project_name, {
        "type": request_type,
        "message": message,
    })


async def get_pending_messages(project_name: str) -> list[dict]:
    """
    Get pending human messages (called from agent code).

    Returns messages that haven't been consumed yet.
    """
    return await message_store.get_messages(project_name)


def get_message_store() -> MessageStore:
    """Get the global message store for callback registration."""
    return message_store
