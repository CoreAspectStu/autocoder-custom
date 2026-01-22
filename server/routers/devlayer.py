"""
DevLayer API Router

Handles agent requests, chat messages, and annotations with SQLite persistence.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
import sqlite3
import os
import uuid
import json

router = APIRouter(prefix="/api/devlayer", tags=["devlayer"])

# Database path - use home directory for cross-project persistence
DB_PATH = os.path.expanduser("~/.autocoder/devlayer.db")


def get_db():
    """Get database connection and ensure tables exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Create tables if they don't exist
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_requests (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            type TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal',
            message TEXT NOT NULL,
            context TEXT,
            created_at TEXT NOT NULL,
            responded INTEGER DEFAULT 0,
            response TEXT,
            responded_at TEXT
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS annotations (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            feature_id TEXT,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resolved INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_requests_project ON agent_requests(project);
        CREATE INDEX IF NOT EXISTS idx_chat_project ON chat_messages(project);
        CREATE INDEX IF NOT EXISTS idx_annotations_project ON annotations(project);
    """)

    return conn


# Request models
class AgentRequestCreate(BaseModel):
    project: str
    type: Literal['question', 'auth_needed', 'blocker', 'decision']
    priority: Literal['critical', 'normal', 'low'] = 'normal'
    message: str
    context: Optional[str] = None


class AgentRequestResponse(BaseModel):
    response: str


class ChatMessageCreate(BaseModel):
    content: str


class AnnotationCreate(BaseModel):
    type: Literal['bug', 'comment', 'workaround', 'idea']
    content: str
    feature_id: Optional[str] = None


class WebhookPayload(BaseModel):
    type: str
    priority: str
    project: str
    message: str
    request_id: str
    timestamp: str


# Webhook configuration (loaded from env or config)
WEBHOOK_URL = os.environ.get('DEVLAYER_WEBHOOK_URL', '')


async def send_webhook(payload: WebhookPayload):
    """Send webhook notification to n8n."""
    if not WEBHOOK_URL:
        return

    import httpx
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                WEBHOOK_URL,
                json=payload.model_dump(),
                timeout=5.0
            )
    except Exception as e:
        print(f"Webhook failed: {e}")


# Routes

@router.get("/requests")
async def get_all_requests():
    """Get all agent requests across all projects."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM agent_requests
            ORDER BY
                CASE priority
                    WHEN 'critical' THEN 1
                    WHEN 'normal' THEN 2
                    ELSE 3
                END,
                created_at DESC
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.post("/requests")
async def create_request(req: AgentRequestCreate):
    """Create a new agent request (called by agent)."""
    conn = get_db()
    try:
        request_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + 'Z'

        conn.execute("""
            INSERT INTO agent_requests (id, project, type, priority, message, context, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (request_id, req.project, req.type, req.priority, req.message, req.context, now))
        conn.commit()

        # Send webhook notification
        await send_webhook(WebhookPayload(
            type='agent_request',
            priority=req.priority,
            project=req.project,
            message=req.message,
            request_id=request_id,
            timestamp=now
        ))

        return {"id": request_id, "created_at": now}
    finally:
        conn.close()


@router.post("/requests/{request_id}/respond")
async def respond_to_request(request_id: str, resp: AgentRequestResponse):
    """Respond to an agent request."""
    conn = get_db()
    try:
        now = datetime.utcnow().isoformat() + 'Z'

        result = conn.execute("""
            UPDATE agent_requests
            SET responded = 1, response = ?, responded_at = ?
            WHERE id = ?
        """, (resp.response, now, request_id))
        conn.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Request not found")

        return {"success": True, "responded_at": now}
    finally:
        conn.close()


@router.get("/projects/{project_name}/requests")
async def get_project_requests(project_name: str):
    """Get agent requests for a specific project."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM agent_requests
            WHERE project = ?
            ORDER BY created_at DESC
        """, (project_name,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.get("/projects/{project_name}/chat")
async def get_chat_messages(project_name: str, limit: int = 100):
    """Get chat messages for a project."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM chat_messages
            WHERE project = ?
            ORDER BY created_at ASC
            LIMIT ?
        """, (project_name, limit)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.post("/projects/{project_name}/chat")
async def send_chat_message(project_name: str, msg: ChatMessageCreate):
    """Send a chat message (human to agent)."""
    conn = get_db()
    try:
        msg_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + 'Z'

        conn.execute("""
            INSERT INTO chat_messages (id, project, role, content, created_at)
            VALUES (?, ?, 'human', ?, ?)
        """, (msg_id, project_name, msg.content, now))
        conn.commit()

        return {"id": msg_id, "created_at": now}
    finally:
        conn.close()


@router.get("/projects/{project_name}/annotations")
async def get_annotations(project_name: str):
    """Get annotations for a project."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM annotations
            WHERE project = ?
            ORDER BY created_at DESC
        """, (project_name,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.post("/projects/{project_name}/annotations")
async def create_annotation(project_name: str, ann: AnnotationCreate):
    """Create an annotation."""
    conn = get_db()
    try:
        ann_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + 'Z'

        conn.execute("""
            INSERT INTO annotations (id, project, feature_id, type, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ann_id, project_name, ann.feature_id, ann.type, ann.content, now))
        conn.commit()

        return {"id": ann_id, "created_at": now}
    finally:
        conn.close()


@router.patch("/projects/{project_name}/annotations/{annotation_id}")
async def update_annotation(project_name: str, annotation_id: str, resolved: bool = False):
    """Update an annotation (mark as resolved)."""
    conn = get_db()
    try:
        result = conn.execute("""
            UPDATE annotations
            SET resolved = ?
            WHERE id = ? AND project = ?
        """, (1 if resolved else 0, annotation_id, project_name))
        conn.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Annotation not found")

        return {"success": True}
    finally:
        conn.close()


@router.delete("/projects/{project_name}/annotations/{annotation_id}")
async def delete_annotation(project_name: str, annotation_id: str):
    """Delete an annotation."""
    conn = get_db()
    try:
        result = conn.execute("""
            DELETE FROM annotations
            WHERE id = ? AND project = ?
        """, (annotation_id, project_name))
        conn.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Annotation not found")

        return {"success": True}
    finally:
        conn.close()


# n8n webhook endpoint for external notifications
@router.post("/webhook/notify")
async def webhook_notify(
    type: str,
    project: str,
    message: str,
    priority: str = 'normal'
):
    """
    Endpoint to trigger notifications via n8n webhook.
    Call this to send alerts for custom events.
    """
    await send_webhook(WebhookPayload(
        type=type,
        priority=priority,
        project=project,
        message=message,
        request_id=str(uuid.uuid4()),
        timestamp=datetime.utcnow().isoformat() + 'Z'
    ))
    return {"success": True}
