# Mission Control UI Module

**Purpose:** Unified tabbed interface for AutoCoder that consolidates all monitoring and interaction features into a single view.

**Created:** 2026-01-24
**Status:** Active
**Type:** UI Enhancement (React components)

---

## What This Adds

This module transforms the AutoCoder UI from a single Kanban view into a comprehensive tabbed interface:

**5 Tabs:**
1. **📋 Kanban** - Existing feature board (unchanged)
2. **💬 Chat** - Agent conversation history (persistent, searchable)
3. **🐛 Issues** - Bug/annotation tracking (quick-add, resolve)
4. **📊 Status** - Server health dashboard (embedded /status page)
5. **📺 Terminal** - Agent output logs (existing DebugLogViewer)

**Key Features:**
- ✅ Project-scoped isolation (no cross-contamination)
- ✅ Persistent chat history across sessions
- ✅ Quick bug logging during development
- ✅ Server health monitoring
- ✅ Keyboard shortcuts (1-5 to switch tabs)
- ✅ localStorage tab persistence

---

## Why This Is Custom

**Problem:** AutoCoder's UI was fragmented:
- Kanban view in main UI
- Status dashboard at `/status` (separate page)
- DevLayer toggle button (broken, never rendered)
- No conversation history
- No centralized bug tracking

**Solution:** Unified tabbed interface puts everything in one place.

**Update Safety:** This modifies UI files (`ui/src/`) that may conflict with upstream changes. The install script makes integration easy, and documentation ensures conflicts are resolvable.

---

## Installation

See `INSTALLATION.md` for detailed integration steps.

**Quick install:**
```bash
cd ~/projects/autocoder/custom/mission_control_ui
./install.sh
```

This will:
1. Copy React components to `ui/src/components/`
2. Patch `ui/src/App.tsx` to use TabLayout
3. Show diff of changes
4. Rebuild UI (`cd ui && npm run build`)

---

## Architecture

**Component Structure:**
```
TabLayout.tsx               # Main tab container
  ├── Tab 1: Kanban         # Existing KanbanBoard component
  ├── Tab 2: ChatTab        # NEW - Agent conversation UI
  ├── Tab 3: IssuesTab      # NEW - Annotation CRUD
  ├── Tab 4: StatusTab      # NEW - Embedded /status dashboard
  └── Tab 5: Terminal       # Existing DebugLogViewer
```

**Data Flow (Project-Scoped):**
```
User selects project: "callAspect"
        ↓
TabLayout receives: selectedProject="callAspect"
        ↓
Each tab fetches data scoped to "callAspect":
  - ChatTab: /api/devlayer/projects/callAspect/chat
  - IssuesTab: /api/devlayer/projects/callAspect/annotations
  - StatusTab: /api/status?project=callAspect
```

**No shared state between projects.** Switching projects triggers full data reload.

---

## Modified Files

### Core UI Files (tracked for upstream merges)

| File | Type | Changes |
|------|------|---------|
| `ui/src/App.tsx` | Modified | Import TabLayout, replace main content with `<TabLayout>` |
| `ui/src/components/TabLayout.tsx` | New | Main tab container with 5 tabs |
| `ui/src/components/ChatTab.tsx` | New | Chat history interface |
| `ui/src/components/IssuesTab.tsx` | New | Annotation management UI |
| `ui/src/components/StatusTab.tsx` | New | Server health dashboard |

### Backend API (optional - extends existing)

| File | Type | Changes |
|------|------|---------|
| `server/routers/devlayer.py` | Optional | Add pagination to chat endpoint |
| `server/routers/status.py` | Optional | Add JSON API endpoint |

---

## Update Strategy

**When pulling from upstream:**

1. **If `ui/src/App.tsx` conflicts:**
   - Accept upstream changes
   - Re-run `./install.sh` to re-apply TabLayout integration

2. **If new UI dependencies added:**
   - Run `cd ui && npm install`
   - Re-run `./install.sh`

3. **If custom components conflict:**
   - Custom components in `custom/mission_control_ui/components/` are source of truth
   - Copy to `ui/src/components/` manually if needed

**Source of Truth:** `custom/mission_control_ui/components/` (NOT `ui/src/components/`)

---

## Testing

**Manual Test Checklist:**
```bash
# Start UI
cd ~/projects/autocoder && autocoder ui

# Open browser: http://localhost:4001

# Test tab navigation
- Press '1' → Kanban tab appears
- Press '2' → Chat tab appears
- Press '3' → Issues tab appears
- Press '4' → Status tab appears
- Press '5' → Terminal tab appears

# Test project isolation
- Select "callAspect" project
- Go to Chat tab → see callAspect messages
- Switch to "QR" project
- Chat tab updates → see QR messages (NOT callAspect)

# Test persistence
- Switch to Issues tab
- Refresh browser (Ctrl+R)
- Issues tab still active (localStorage restored)
```

**E2E Tests (TODO):**
- See `custom/mission_control_ui/tests/` (future)

---

## Troubleshooting

**Issue:** Tabs don't appear after install
- **Fix:** Rebuild UI: `cd ui && npm run build`
- **Fix:** Clear browser cache (Ctrl+Shift+R)

**Issue:** Chat tab shows wrong project's messages
- **Fix:** Check `selectedProject` prop is passed correctly
- **Debug:** Console should show API calls to correct project name

**Issue:** Components import errors after upstream update
- **Fix:** Re-run `./install.sh` to copy components again

---

## Future Enhancements

- [ ] Search/filter chat history by date range
- [ ] Export chat history to markdown
- [ ] Voice annotations (speak instead of type)
- [ ] Pinned messages (bookmark important moments)
- [ ] Agent response time analytics
- [ ] Multi-project view (see all projects at once)

---

## Credits

**Built by:** BMAD Party Mode (Mary, John, Bob, Winston, Amelia, Murat, Sally)
**Date:** 2026-01-24
**Reason:** Consolidate fragmented UI into unified workspace
