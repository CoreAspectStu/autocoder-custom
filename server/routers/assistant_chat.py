"""
Assistant Chat Router
=====================

WebSocket and REST endpoints for the read-only project assistant.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..services.assistant_chat_session import (
    AssistantChatSession,
    create_session,
    get_session,
    list_sessions,
    remove_session,
)
from ..services.assistant_database import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversations,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["assistant-chat"])

# Root directory
ROOT_DIR = Path(__file__).parent.parent.parent


def _get_project_path(project_name: str) -> Optional[Path]:
    """Get project path from registry."""
    import sys
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from registry import get_project_path
    return get_project_path(project_name)


def validate_project_name(name: str) -> bool:
    """Validate project name to prevent path traversal."""
    return bool(re.match(r'^[a-zA-Z0-9_-]{1,50}$', name))


# ============================================================================
# Pydantic Models
# ============================================================================

class ConversationSummary(BaseModel):
    """Summary of a conversation."""
    id: int
    project_name: str
    title: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    message_count: int


class ConversationMessageModel(BaseModel):
    """A message within a conversation."""
    id: int
    role: str
    content: str
    timestamp: Optional[str]


class ConversationDetail(BaseModel):
    """Full conversation with messages."""
    id: int
    project_name: str
    title: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    messages: list[ConversationMessageModel]


class SessionInfo(BaseModel):
    """Active session information."""
    project_name: str
    conversation_id: Optional[int]
    is_active: bool


# ============================================================================
# REST Endpoints - Conversation Management
# ============================================================================

@router.get("/conversations/{project_name}", response_model=list[ConversationSummary])
async def list_project_conversations(project_name: str, mode: str = 'dev'):
    """
    List all conversations for a project.

    Args:
        project_name: Name of the project
        mode: 'dev' or 'uat' - filter conversations by mode

    Returns an empty array [] when no conversations exist, not a 404 error.
    This ensures the frontend can distinguish between "no conversations" (200 with [])
    and "project not found" (404).
    """
    if not validate_project_name(project_name):
        raise HTTPException(status_code=400, detail="Invalid project name")

    if mode not in ['dev', 'uat']:
        raise HTTPException(status_code=400, detail="Invalid mode, must be 'dev' or 'uat'")

    project_dir = _get_project_path(project_name)
    if not project_dir or not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    conversations = get_conversations(project_dir, project_name, mode)

    # Explicitly return empty array when no conversations exist (Feature #150)
    # This prevents treating "no conversations" as an error condition
    if not conversations:
        return []

    return [ConversationSummary(**c) for c in conversations]


@router.get("/conversations/{project_name}/{conversation_id}", response_model=ConversationDetail)
async def get_project_conversation(project_name: str, conversation_id: int, mode: str = 'dev'):
    """Get a specific conversation with all messages."""
    if not validate_project_name(project_name):
        raise HTTPException(status_code=400, detail="Invalid project name")

    if mode not in ['dev', 'uat']:
        raise HTTPException(status_code=400, detail="Invalid mode, must be 'dev' or 'uat'")

    project_dir = _get_project_path(project_name)
    if not project_dir or not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    conversation = get_conversation(project_dir, conversation_id, mode)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationDetail(
        id=conversation["id"],
        project_name=conversation["project_name"],
        title=conversation["title"],
        created_at=conversation["created_at"],
        updated_at=conversation["updated_at"],
        messages=[ConversationMessageModel(**m) for m in conversation["messages"]],
    )


@router.post("/conversations/{project_name}", response_model=ConversationSummary)
async def create_project_conversation(project_name: str, mode: str = 'dev'):
    """Create a new conversation for a project."""
    if not validate_project_name(project_name):
        raise HTTPException(status_code=400, detail="Invalid project name")

    if mode not in ['dev', 'uat']:
        raise HTTPException(status_code=400, detail="Invalid mode, must be 'dev' or 'uat'")

    project_dir = _get_project_path(project_name)
    if not project_dir or not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    conversation = create_conversation(project_dir, project_name, mode)
    return ConversationSummary(
        id=conversation.id,
        project_name=conversation.project_name,
        title=conversation.title,
        created_at=conversation.created_at.isoformat() if conversation.created_at else None,
        updated_at=conversation.updated_at.isoformat() if conversation.updated_at else None,
        message_count=0,
    )


@router.delete("/conversations/{project_name}/{conversation_id}")
async def delete_project_conversation(project_name: str, conversation_id: int, mode: str = 'dev'):
    """Delete a conversation."""
    if not validate_project_name(project_name):
        raise HTTPException(status_code=400, detail="Invalid project name")

    if mode not in ['dev', 'uat']:
        raise HTTPException(status_code=400, detail="Invalid mode, must be 'dev' or 'uat'")

    project_dir = _get_project_path(project_name)
    if not project_dir or not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    success = delete_conversation(project_dir, conversation_id, mode)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"success": True, "message": "Conversation deleted"}


# ============================================================================
# REST Endpoints - Session Management
# ============================================================================

@router.get("/sessions", response_model=list[str])
async def list_active_sessions():
    """List all active assistant sessions."""
    return list_sessions()


@router.get("/sessions/{project_name}", response_model=SessionInfo)
async def get_session_info(project_name: str):
    """Get information about an active session."""
    if not validate_project_name(project_name):
        raise HTTPException(status_code=400, detail="Invalid project name")

    session = get_session(project_name)
    if not session:
        raise HTTPException(status_code=404, detail="No active session for this project")

    return SessionInfo(
        project_name=project_name,
        conversation_id=session.get_conversation_id(),
        is_active=True,
    )


@router.delete("/sessions/{project_name}")
async def close_session(project_name: str):
    """Close an active session."""
    if not validate_project_name(project_name):
        raise HTTPException(status_code=400, detail="Invalid project name")

    session = get_session(project_name)
    if not session:
        raise HTTPException(status_code=404, detail="No active session for this project")

    await remove_session(project_name)
    return {"success": True, "message": "Session closed"}


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@router.websocket("/ws/{project_name}")
async def assistant_chat_websocket(websocket: WebSocket, project_name: str):
    """
    WebSocket endpoint for assistant chat.

    Query Parameters:
    - mode: 'dev' or 'uat' - separate conversation contexts for Dev vs UAT mode

    Message protocol:

    Client -> Server:
    - {"type": "start", "conversation_id": int | null} - Start/resume session
    - {"type": "message", "content": "..."} - Send user message
    - {"type": "ping"} - Keep-alive ping

    Server -> Client:
    - {"type": "conversation_created", "conversation_id": int} - New conversation created
    - {"type": "text", "content": "..."} - Text chunk from Claude
    - {"type": "tool_call", "tool": "...", "input": {...}} - Tool being called
    - {"type": "response_done"} - Response complete
    - {"type": "error", "content": "..."} - Error message
    - {"type": "pong"} - Keep-alive pong
    """
    # Accept the WebSocket connection FIRST (required by Starlette)
    # This allows us to send proper error codes to the client
    await websocket.accept()

    # Security: Only allow connections from localhost
    client_host = websocket.client.host if websocket.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost", None):
        await websocket.close(code=4003, reason="Localhost access only")
        return

    # Validate project name
    if not validate_project_name(project_name):
        await websocket.close(code=4000, reason="Invalid project name")
        return

    # Extract mode from query parameters
    mode = 'dev'  # Default
    try:
        query_params = dict(websocket.query_params)
        mode = query_params.get('mode', 'dev')
        if mode not in ['dev', 'uat']:
            await websocket.close(code=4002, reason="Invalid mode, must be 'dev' or 'uat'")
            return
    except Exception as e:
        logger.warning(f"Failed to parse query params: {e}")

    # Get project directory
    project_dir = _get_project_path(project_name)
    if not project_dir:
        await websocket.close(code=4004, reason="Project not found in registry")
        return

    if not project_dir.exists():
        await websocket.close(code=4004, reason="Project directory not found")
        return

    logger.info(f"Assistant WebSocket connected for project: {project_name}, mode: {mode}")

    session: Optional[AssistantChatSession] = None

    try:
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                msg_type = message.get("type")
                logger.debug(f"Assistant received message type: {msg_type}")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                elif msg_type == "start":
                    # Get optional conversation_id to resume
                    conversation_id = message.get("conversation_id")
                    logger.debug(f"Processing start message with conversation_id={conversation_id}")

                    try:
                        # Create a new session with mode context
                        logger.debug(f"Creating session for {project_name}, mode: {mode}")
                        session = await create_session(
                            project_name,
                            project_dir,
                            conversation_id=conversation_id,
                            mode=mode,
                        )
                        logger.debug("Session created, starting...")

                        # Stream the initial greeting
                        async for chunk in session.start():
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(f"Sending chunk: {chunk.get('type')}")
                            await websocket.send_json(chunk)
                        logger.debug("Session start complete")
                    except Exception as e:
                        logger.exception(f"Error starting assistant session for {project_name}")
                        await websocket.send_json({
                            "type": "error",
                            "content": f"Failed to start session: {str(e)}"
                        })

                elif msg_type == "message":
                    if not session:
                        session = get_session(project_name)
                        if not session:
                            await websocket.send_json({
                                "type": "error",
                                "content": "No active session. Send 'start' first."
                            })
                            continue

                    user_content = message.get("content", "").strip()
                    if not user_content:
                        await websocket.send_json({
                            "type": "error",
                            "content": "Empty message"
                        })
                        continue

                    # Stream Claude's response
                    async for chunk in session.send_message(user_content):
                        await websocket.send_json(chunk)

                else:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Unknown message type: {msg_type}"
                    })

            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "content": "Invalid JSON"
                })

    except WebSocketDisconnect:
        logger.info(f"Assistant chat WebSocket disconnected for {project_name}")

    except Exception as e:
        logger.exception(f"Assistant chat WebSocket error for {project_name}")
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"Server error: {str(e)}"
            })
        except Exception:
            pass

    finally:
        # Don't remove session on disconnect - allow resume
        pass
