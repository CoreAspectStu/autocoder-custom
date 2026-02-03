# Mission Control UI - Installation Guide

This guide explains how to integrate the Mission Control UI tabbed interface into AutoCoder.

---

## Quick Install

```bash
cd ~/projects/autocoder/custom/mission_control_ui
./install.sh
```

The script will:
1. Copy React components to `ui/src/components/`
2. Show you the required changes to `App.tsx`
3. Ask for confirmation before patching
4. Rebuild the UI (`cd ui && npm run build`)

---

## Manual Installation

If you prefer to install manually or the script fails:

### Step 1: Copy Components

```bash
cp components/TabLayout.tsx ../../ui/src/components/
cp components/ChatTab.tsx ../../ui/src/components/
cp components/IssuesTab.tsx ../../ui/src/components/
cp components/StatusTab.tsx ../../ui/src/components/
```

### Step 2: Modify App.tsx

**File:** `ui/src/App.tsx`

**Add import at top (around line 27):**
```typescript
import { TabLayout } from './components/TabLayout'
```

**Replace the main content section** (look for the section that renders KanbanBoard or DependencyGraph):

**BEFORE:**
```typescript
<div className="flex-1 overflow-hidden bg-white dark:bg-gray-950">
  {viewMode === 'kanban' ? (
    <KanbanBoard
      features={features}
      onFeatureClick={handleFeatureClick}
      onAddFeature={() => setShowAddFeature(true)}
      onExpandProject={() => setShowExpandProject(true)}
      hasSpec={hasSpec}
      onCreateSpec={() => setShowSpecChat(true)}
    />
  ) : (
    <DependencyGraph
      graph={graphData}
      onNodeClick={handleGraphNodeClick}
    />
  )}
</div>
```

**AFTER:**
```typescript
<div className="flex-1 overflow-hidden bg-white dark:bg-gray-950">
  {devLayerMode ? (
    <TabLayout
      selectedProject={selectedProject}
      features={features}
      onFeatureClick={handleFeatureClick}
      onAddFeature={() => setShowAddFeature(true)}
      onExpandProject={() => setShowExpandProject(true)}
      hasSpec={hasSpec}
      onCreateSpec={() => setShowSpecChat(true)}
      debugOpen={debugOpen}
      debugPanelHeight={debugPanelHeight}
      debugActiveTab={debugActiveTab}
      onDebugHeightChange={setDebugPanelHeight}
      onDebugTabChange={setDebugActiveTab}
    />
  ) : viewMode === 'kanban' ? (
    <KanbanBoard
      features={features}
      onFeatureClick={handleFeatureClick}
      onAddFeature={() => setShowAddFeature(true)}
      onExpandProject={() => setShowExpandProject(true)}
      hasSpec={hasSpec}
      onCreateSpec={() => setShowSpecChat(true)}
    />
  ) : (
    <DependencyGraph
      graph={graphData}
      onNodeClick={handleGraphNodeClick}
    />
  )}
</div>
```

**Note:** This makes DevLayer mode (purple button / L key) switch to the tabbed interface.

### Step 3: Rebuild UI

```bash
cd ~/projects/autocoder/ui
npm run build
```

### Step 4: Restart AutoCoder UI

```bash
cd ~/projects/autocoder
autocoder ui
```

---

## Verification

1. Open AutoCoder UI: http://localhost:4001
2. Select a project (e.g., "callAspect")
3. Press `L` key (or click purple button)
4. You should see 5 tabs: Kanban | Chat | Issues | Status | Terminal
5. Press `1-5` to switch between tabs
6. Chat tab should show conversation history
7. Issues tab should show annotations

---

## Troubleshooting

### Tabs don't appear

**Check 1:** DevLayer mode enabled?
- Look for purple button in top-right toolbar
- Press `L` to toggle DevLayer mode
- Button should be highlighted purple when active

**Check 2:** Components copied correctly?
```bash
ls -la ~/projects/autocoder/ui/src/components/ | grep -E "TabLayout|ChatTab|IssuesTab|StatusTab"
```
You should see all 4 files.

**Check 3:** Import errors in console?
- Open browser DevTools (F12)
- Check Console tab for import errors
- If errors, verify component file names match imports

### Chat tab is empty

**Check:** Project has chat messages?
```bash
sqlite3 ~/.autocoder/devlayer.db "SELECT COUNT(*) FROM chat_messages WHERE project='callAspect';"
```

If zero, send a test message:
```bash
curl -X POST http://localhost:8888/api/devlayer/projects/callAspect/chat \
  -H "Content-Type: application/json" \
  -d '{"content": "Test message"}'
```

### Issues tab shows "No active issues"

**Check:** Project has annotations?
```bash
sqlite3 ~/.autocoder/devlayer.db "SELECT COUNT(*) FROM annotations WHERE project='callAspect' AND resolved=0;"
```

If zero, create a test annotation:
```bash
cd ~/projects/autocoder
./venv/bin/python -c "
import asyncio
from custom.mission_control.client import DevLayerClient

async def test():
    client = DevLayerClient(project_name='callAspect')
    await client.create_annotation('bug', 'Test bug annotation')

asyncio.run(test())
"
```

### Status tab shows "API Not Implemented"

The `/api/status/json` endpoint needs to be created. This is optional - you can still use the Status tab with dummy data or skip it.

To create the endpoint, add to `server/routers/status.py`:
```python
@router.get("/api/status/json")
async def get_status_json():
    """Return status dashboard data as JSON."""
    projects = list_registered_projects()
    result = []
    for name, path in projects.items():
        project_path = Path(path)
        port = get_project_port(project_path)
        is_running = is_port_listening(port) if port else False
        health = get_project_health(project_path)

        result.append({
            "name": name,
            "path": str(project_path),
            "port": port,
            "is_running": is_running,
            "health": health["health"],
            "progress": health["progress"],
            "agent_status": get_agent_status(name),
        })
    return result
```

---

## Uninstallation

To remove Mission Control UI and revert to vanilla AutoCoder:

### Step 1: Remove Components

```bash
cd ~/projects/autocoder/ui/src/components
rm -f TabLayout.tsx ChatTab.tsx IssuesTab.tsx StatusTab.tsx
```

### Step 2: Revert App.tsx

Remove the TabLayout import and restore the original main content section (see git history or upstream version).

### Step 3: Rebuild UI

```bash
cd ~/projects/autocoder/ui
npm run build
```

---

## Integration with Upstream Updates

When pulling from upstream AutoCoder:

**If `ui/src/App.tsx` has conflicts:**
1. Accept upstream changes (take their version)
2. Re-run `./install.sh` to re-apply TabLayout integration
3. Review the diff carefully before confirming

**If UI dependencies change:**
1. Run `cd ui && npm install` after pull
2. Re-run `./install.sh`
3. Test thoroughly

**Source of truth:** `custom/mission_control_ui/components/` (NOT `ui/src/components/`)

Always keep custom components in `custom/mission_control_ui/components/` and copy to `ui/src/components/` via install script. This makes it easy to re-apply after upstream updates.
