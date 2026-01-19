# Remote Access Patches

This directory contains patches for remote access functionality that may be overwritten when pulling upstream updates.

## When to Use

After running `git pull` from upstream, if you see merge conflicts or lost functionality:

```bash
./patches/apply-remote-access.sh
./remote-start.sh stop && ./remote-start.sh ui
```

## What Gets Patched

| File | Change |
|------|--------|
| `server/routers/__init__.py` | Adds `status_router` import and export |
| `server/main.py` | Adds `status_router` import and include |

## Files That Won't Conflict

These are new files that upstream doesn't have:

| File | Purpose |
|------|---------|
| `server/routers/status.py` | Status page with port detection |
| `remote-start.sh` | tmux/Xvfb session management |
| `docs/remote-*.md` | Documentation |
| `docs/ports-4000-4099.txt` | SSH config port forwards |
| `patches/` | This directory |

## Manual Fix (if script fails)

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

## Port Range Convention

- **3000-3999**: Reserved for LOCAL development (not forwarded)
- **4000-4099**: AutoCoder dev servers (forwarded via SSH tunnel)
