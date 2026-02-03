# WebSocket Error Handling Patterns

This document describes the proper patterns for WebSocket endpoint implementation in AutoCoder to ensure robust error handling and proper error codes are sent to clients.

## The Core Pattern

**ALWAYS accept the WebSocket connection FIRST, then validate, then close with error codes if needed.**

```python
async def my_websocket(websocket: WebSocket, some_param: str):
    """WebSocket endpoint with proper error handling."""

    # 1. Accept FIRST (required by Starlette/FastAPI)
    await websocket.accept()

    # 2. Security check (optional but recommended)
    client_host = websocket.client.host if websocket.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost", None):
        await websocket.close(code=4003, reason="Localhost access only")
        return

    # 3. Validate input parameters
    if not validate_param(some_param):
        await websocket.close(code=4000, reason="Invalid parameter")
        return

    # 4. Look up resources
    resource = get_resource(some_param)
    if not resource:
        await websocket.close(code=4004, reason="Resource not found")
        return

    # 5. Register with connection manager (if applicable)
    await manager.register(websocket, some_param)  # NOT connect() - already accepted

    # 6. Main message loop
    try:
        while True:
            data = await websocket.receive_text()
            # ... handle messages
    except WebSocketDisconnect:
        pass  # Normal disconnect
    finally:
        await manager.disconnect(websocket, some_param)
```

## Why This Pattern?

### The Anti-Pattern (Don't Do This)

```python
# WRONG - This fails silently!
async def my_websocket(websocket: WebSocket, some_param: str):
    if not validate_param(some_param):
        await websocket.close(code=4000, reason="Invalid parameter")  # FAILS!
        return

    await websocket.accept()  # Never reached if validation fails
```

**What happens:**
- Calling `close()` before `accept()` violates the WebSocket state machine
- The client sees a generic connection error, not your custom error code
- The `reason` text is never sent to the client

### The Correct Pattern

```python
# CORRECT - Error codes reach the client
async def my_websocket(websocket: WebSocket, some_param: str):
    await websocket.accept()  # Accept first

    if not validate_param(some_param):
        await websocket.close(code=4000, reason="Invalid parameter")  # Works!
        return
```

**What happens:**
- WebSocket is accepted (connection established)
- Validation happens
- If validation fails, `close()` sends the error code and reason to the client
- Client can display meaningful error messages

## WebSocket Close Codes

| Code | Meaning | Usage |
|------|---------|-------|
| 4000 | Invalid parameter | Project name, ID, or other parameter is invalid |
| 4003 | Forbidden | Security check failed (e.g., not localhost) |
| 4004 | Not found | Resource doesn't exist (project, terminal, etc.) |
| 4002 | Invalid value | Parameter value is invalid (e.g., mode must be 'dev' or 'uat') |

## Connection Manager Usage

### When to use `connect()` vs `register()`

```python
# Use connect() when you don't need validation before accepting
async def simple_websocket(websocket: WebSocket, project_name: str):
    await manager.connect(websocket, project_name)  # Accepts + registers

# Use register() when you need to validate after accepting
async def validated_websocket(websocket: WebSocket, project_name: str):
    await websocket.accept()  # Accept first

    # Validate after accept
    if not validate_project(project_name):
        await websocket.close(code=4004, reason="Project not found")
        return

    await manager.register(websocket, project_name)  # Only registers (already accepted)
```

## Existing WebSocket Endpoints

| Endpoint | File | Pattern Used |
|----------|------|--------------|
| `/ws/projects/{project_name}` | `server/websocket.py` | Accept → Validate → Register |
| `/ws/projects/{project_name}/assistant` | `server/routers/assistant_chat.py` | Accept → Validate |
| `/ws/projects/{project_name}/spec` | `server/routers/spec_creation.py` | Accept → Validate |
| `/ws/projects/{project_name}/terminal/{id}` | `server/routers/terminal.py` | Accept → Validate |
| `/ws/projects/{project_name}/expand` | `server/routers/expand_project.py` | Accept → Validate |
| `/api/uat/ws/{cycle_id}` | `server/routers/uat_websocket.py` | Direct `connect()` call |

## Testing WebSocket Errors

### Client-Side Testing

```javascript
// Test connection with error handling
const ws = new WebSocket('ws://localhost:8888/ws/projects/invalid');

ws.onopen = () => {
  console.log('Connected');
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = (event) => {
  console.log('Closed:', event.code, event.reason);
  // 4004 - "Project not found in registry"
};
```

### Server-Side Testing

```bash
# Use websocat for WebSocket testing
echo '{"type":"ping"}' | websocat ws://localhost:8888/ws/projects/QR
```

## Common Pitfalls

### 1. Calling close() before accept()

```python
# WRONG
if invalid:
    await websocket.close(code=4000)  # Violates state machine
    return
await websocket.accept()
```

### 2. Using ConnectionManager.connect() after validation

```python
# WRONG - connect() calls accept() again
await websocket.accept()
# ... validation ...
await manager.connect(websocket, project_name)  # ERROR: Already accepted!

# CORRECT - Use register() instead
await websocket.accept()
# ... validation ...
await manager.register(websocket, project_name)
```

### 3. Forgetting localhost security check

```python
# Add this after accept() for security
client_host = websocket.client.host if websocket.client else None
if client_host not in ("127.0.0.1", "::1", "localhost", None):
    await websocket.close(code=4003, reason="Localhost access only")
    return
```

## Related Documentation

- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [Starlette WebSocket Documentation](https://www.starlette.io/websockets/)
- [RFC 6455 - WebSocket Protocol](https://datatracker.ietf.org/doc/html/rfc6455)
