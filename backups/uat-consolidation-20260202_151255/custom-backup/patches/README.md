# Remote Access Patches

This directory contains patches for remote access functionality that may be overwritten when pulling upstream updates.

## When to Use

After running `git pull` from upstream, if you see merge conflicts or lost functionality:

```bash
custom/patches/apply-remote-access.sh
./remote-start.sh stop && ./remote-start.sh ui
```

## What Gets Patched

### Patch 1: Status Router Integration
| File | Change |
|------|--------|
| `server/routers/__init__.py` | Adds `status_router` import and export |
| `server/main.py` | Adds `status_router` import and include |

### Patch 2: Port Assignment System (`port-assignment.patch`)
| File | Change |
|------|--------|
| `server/services/project_config.py` | Adds automatic port assignment (4000-4099 range) |
| `server/schemas.py` | Adds `assigned_port` field to `DevServerConfigResponse` |
| `server/routers/devserver.py` | Returns `assigned_port` in config endpoints |
| `server/routers/status.py` | Uses assigned port as source of truth (priority over package.json) |

## Files That Won't Conflict

These are new files that upstream doesn't have:

| File | Purpose |
|------|---------|
| `server/routers/status.py` | Status page with port detection |
| `remote-start.sh` | tmux/Xvfb session management |
| `custom/docs/remote-*.md` | Documentation |
| `custom/docs/ports-4000-4099.txt` | SSH config port forwards |
| `custom/patches/` | This directory |
| `custom/README.md` | Master index of all customizations |

## Manual Fix (if script fails)

### Status Router Integration

Add to `server/routers/__init__.py`:
```python
from .status import router as status_router
# In __all__:
    "status_router",
```

Add to `server/main.py`:
```python
from .routers import (
    ...
    status_router,
)
...
app.include_router(status_router)
```

### Port Assignment System

If `git apply custom/patches/port-assignment.patch` fails, manually apply:

1. **In `server/services/project_config.py`** - Add port assignment functions (see patch file)
2. **In `server/schemas.py`** - Add to `DevServerConfigResponse`:
   ```python
   assigned_port: int | None = None
   ```
3. **In `server/routers/devserver.py`** - Add to both config responses:
   ```python
   assigned_port=config["assigned_port"],
   ```
4. **In `server/routers/status.py`** - Update `get_project_port()` to check assigned port first:
   ```python
   from server.services.project_config import get_project_config

   # At start of get_project_port():
   try:
       config = get_project_config(project_path)
       assigned_port = config.get("assigned_port")
       if assigned_port is not None:
           return assigned_port
   except Exception:
       pass
   ```

## Port Range Convention

- **3000-3999**: Reserved for LOCAL development (not forwarded)
- **4000-4099**: AutoCoder dev servers (forwarded via SSH tunnel)
