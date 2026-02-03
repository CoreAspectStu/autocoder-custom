# Fork Maintenance Guide

This fork (autocoder-custom) contains significant custom work that differs from the upstream `leonvanzyl/autocoder` repository.

## Remote Configuration

```bash
origin    git@github.com:CoreAspectStu/autocoder-custom.git  (your fork)
upstream  https://github.com/leonvanzyl/autocoder            (original)
```

## Custom Work (Must Preserve During Merge)

### Custom Directories (NEVER remove)
- `custom/` - All local extensions and plugins
  - `custom/uat_gateway/` - UAT Gateway integration
  - `custom/uat_plugin/` - UAT testing framework
- `docs/projects/autocoder/` - Custom documentation

### Custom Server Files
- `server/routers/status.py` - Enhanced status dashboard (1132 lines)
- `server/routers/uat_gateway.py` - UAT Gateway API endpoints
- `server/routers/a11y_testing.py` - Accessibility testing
- `server/routers/api_testing.py` - API testing integration
- `server/routers/blocker.py` - Blocker detection API
- `server/routers/msw_integration.py` - MSW integration
- `server/routers/visual_testing.py` - Visual testing
- `server/routers/uat_reports.py` - UAT reporting
- `server/routers/uat_websocket.py` - UAT WebSocket
- `server/services/blocker_detector.py` - Blocker detection service
- `server/services/blocker_storage.py` - Blocker storage

### Custom UI Components
- `ui/src/components/blocker/` - Blocker detection UI
- `ui/src/components/JourneyVisualizer.tsx` - UAT journey visualization
- `ui/src/components/ProgressTracker.tsx` - Progress tracking
- `ui/src/components/ResultsModal.tsx` - Test results display
- `ui/src/components/UAT*.tsx` - All UAT-related components
- `ui/src/hooks/useBlockerDetection.ts` - Blocker detection hook
- `ui/src/hooks/useUATWebSocket.tsx` - UAT WebSocket hook

### Local Patches to Upstream Files
These files have local modifications that must be reapplied after merge:

#### `server/websocket.py`
**Change**: Accept-first pattern for WebSocket connections
```python
# Accept the WebSocket connection FIRST
await websocket.accept()

# Then validate and close with error codes if needed
if not validate_project_name(project_name):
    await websocket.close(code=4000, reason="Invalid project name")
    return

# Register the connection
await manager.register(websocket, project_name)
```
**Why**: Starlette WebSocket requires accept() before any close() calls

#### `server/schemas.py`
**Change**: Pydantic validators with `mode='before'`
```python
@field_validator('steps', mode='before')
@classmethod
def validate_steps(cls, v: list[str] | None) -> list[str]:
    if v is None:
        return []
    # ... rest of validation
```
**Why**: Database returns NULL for empty JSON arrays - validator must handle this

#### `server/routers/assistant_chat.py`, `spec_creation.py`, `expand_project.py`, `terminal.py`
**Change**: Apply same accept-first pattern as `server/websocket.py`

#### `api/database.py`
**Change**: Add NOT NULL constraints
```python
dependencies = Column(JSON, nullable=False, default=list)
```
**Why**: Prevents future NULL value issues

### CLI Tools
- `bin/autocoder-*` - Custom wrapper scripts

## Update Strategy

### Option 1: Stay Diverged (RECOMMENDED)
- Treat this as a separate product with custom features
- Only cherry-pick specific critical fixes from upstream
- Your custom work is now a differentiating feature

### Option 2: Selective Merge
Only merge upstream changes that don't conflict with custom work:

```bash
# 1. Create backup branch
git checkout -b backup-before-merge-$(date +%Y%m%d)

# 2. Review upstream commits
git fetch upstream
git log HEAD..upstream/master --oneline

# 3. Cherry-pick specific commits
git cherry-pick <commit-sha>

# 4. Re-apply local patches (see sections above)
# 5. Test thoroughly
```

### Option 3: Full Merge (NOT RECOMMENDED)
High conflict risk due to extensive custom work.

```bash
# Only attempt if absolutely necessary
git checkout -b merge-upstream-$(date +%Y%m%d)
git merge upstream/master
# Resolve conflicts preserving custom/ directory and local patches
```

## Merge Conflict Resolution

### Protect custom directory
Add to `.gitattributes`:
```
custom/ merge=ours
docs/projects/autocoder/ merge=ours
```

Then run:
```bash
git config --global merge.ours.driver true
```

### Re-applying local patches after merge
1. `server/websocket.py` - Ensure accept() comes before validation
2. `server/schemas.py` - Ensure mode='before' on validators
3. `api/database.py` - Ensure NOT NULL DEFAULT list on dependencies
4. Test WebSocket connections
5. Test Features API for all projects

## Testing Checklist After Any Update

- [ ] WebSocket connects without HTTP 403 error
- [ ] Features API loads for all projects
- [ ] Status dashboard works
- [ ] UAT Gateway functional
- [ ] All custom routers respond
- [ ] No database errors in logs

## Contributing Upstream

Consider contributing these fixes upstream:
- WebSocket accept-first pattern (universal fix)
- Pydantic NULL handling (affects all users)
- NOT NULL constraints (prevents data issues)

Your custom features (status dashboard, UAT Gateway) may be valuable additions to upstream if modularized properly.
