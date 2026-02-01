# UAT Gateway Plugin - Deployment Guide

**Complete guide to installing and configuring the UAT (User Acceptance Testing) Mode Plugin for AutoCoder**

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Database Setup](#database-setup)
7. [Verification](#verification)
8. [API Reference](#api-reference)
9. [Troubleshooting](#troubleshooting)
10. [Uninstallation](#uninstallation)

---

## Overview

The **UAT Gateway Plugin** transforms AutoCoder from a pure development tool into a complete development + testing platform. Like a spell checker for a book editor, UAT Mode validates completed features through automated test journeys.

### What It Does

- **Mode Toggle**: Switch between Dev Mode (coding) and UAT Mode (testing) with one click
- **Separate Contexts**: Dev conversations → features.db, UAT conversations → uat_tests.db
- **Test Planning**: Conversational AI helps plan test frameworks based on your spec
- **Test Execution**: Run automated Playwright tests across multiple browsers
- **Blocker Handling**: Ask about external dependencies (email, SMS, payment) upfront

### Key Features

✅ **Zero-Downtime Integration**: Works alongside existing Dev Mode
✅ **Complete Separation**: Dev and UAT contexts never mix
✅ **AI-Powered**: Conversational test planning with Claude
✅ **Multi-Browser**: Chromium, Firefox, WebKit, Mobile emulation
✅ **Real-Time Updates**: WebSocket progress tracking
✅ **Persistent History**: Separate conversation histories per mode

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         AutoCoder UI                           │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  UATModeProvider (Context)                                │ │
│  │  ├─ mode: 'dev' | 'uat'                                   │ │
│  │  ├─ setMode(), toggleMode(), isUATMode                    │ │
│  │  └─ Persists to localStorage                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────┐              ┌──────────────────┐        │
│  │  Dev Mode View   │              │  UAT Mode View   │        │
│  │  ┌────────────┐  │              │  ┌────────────┐  │        │
│  │  │ Features    │  │              │  │ UAT Tests   │  │        │
│  │  │ (features. │  │              │  │ (uat_tests. │  │        │
│  │  │  db)        │  │              │  │  db)        │  │        │
│  │  └────────────┘  │              │  └────────────┘  │        │
│  │                  │              │                  │        │
│  │  Project         │              │  UAT Test        │        │
│  │  Assistant       │              │  Planner         │        │
│  │  (Bot Icon)      │              │  (Flask Icon)    │        │
│  └──────────────────┘              └──────────────────┘        │
│                                                                 │
│  Mode Toggle Button (Header)                                   │
│  └─ Flask Icon → Switches contexts instantly                   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AutoCoder Backend                         │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Main Router (/api/)                                      │  │
│  │  ├─ /projects/* (Dev features)                           │  │
│  │  ├─ /assistant/* (Mode-aware conversations)              │  │
│  │  └─ WebSocket /ws/projects/* (Real-time updates)         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  UAT Gateway Router (/api/uat/)                           │  │
│  │  ├─ GET  /stats/summary (UAT test stats)                │  │
│  │  ├─ GET  /tests (List UAT tests)                        │  │
│  │  ├─ POST /tests (Create UAT test)                       │  │
│  │  ├─ GET  /generate-plan (AI test planning)              │  │
│  │  ├─ POST /modify-plan (Modify test plan)                │  │
│  │  ├─ POST /approve-plan (Approve test plan)              │  │
│  │  └─ POST /trigger (Execute UAT tests)                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────┐              ┌──────────────────┐        │
│  │  features.db     │              │  uat_tests.db    │        │
│  │  (SQLite)        │              │  (SQLite)        │        │
│  │                  │              │                  │        │
│  │  ┌────────────┐ │              │  ┌────────────┐ │        │
│  │  │ features    │ │              │  │ uat_test_   │ │        │
│  │  │ table       │ │              │  │ features    │ │        │
│  │  └────────────┘ │              │  │ table       │ │        │
│  │                  │              │  └────────────┘ │        │
│  └──────────────────┘              └──────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required

- **AutoCoder** installed and working (at `/home/stu/projects/autocoder` or custom path)
- **Python 3.11+** (hard requirement - uses asyncio.TaskGroup)
- **Node.js 20+** (for frontend build)
- **uv** package manager (Python dependency management)

### External Services (Optional but Recommended)

- **Playwright browsers**: `playwright install chromium firefox webkit`
- **DevLayer API**: For bug card creation during UAT
- **n8n webhooks**: For async blocker notifications
- **Slack webhook**: For status updates

---

## Installation

### Step 1: Frontend Plugin Files

Copy these files to your AutoCoder UI:

```bash
# Navigate to AutoCoder UI
cd /path/to/autocoder/ui/src

# Create UAT contexts
mkdir -p contexts
# Copy UATModeContext.tsx (if not exists)

# Copy UAT components
cp /path/to/uat-plugin/components/UATModeToggle.tsx components/
cp /path/to/uat-plugin/components/AddUATTestForm.tsx components/
cp /path/to/uat-plugin/components/StartUATButton.tsx components/
cp /path/to/uat-plugin/components/UATTestPlanning.tsx components/
cp /path/to/uat-plugin/components/UATPlanningHelper.tsx components/
cp /path/to/uat-plugin/components/BlockerQuestions.tsx components/
cp /path/to/uat-plugin/components/UATTestModal.tsx components/

# Copy UAT hooks
mkdir -p hooks
cp /path/to/uat-plugin/hooks/useUATTests.ts hooks/
cp /path/to/uat-plugin/hooks/useGenerateTestPlan.ts hooks/
cp /path/to/uat-plugin/hooks/useModifyTestPlan.ts hooks/
cp /path/to/uat-plugin/hooks/useApproveTestPlan.ts hooks/
cp /path/to/uat-plugin/hooks/useUATProjectContext.ts hooks/
```

**Key Frontend Files:**

| File | Purpose |
|------|---------|
| `contexts/UATModeContext.tsx` | Global mode state management |
| `components/UATModeToggle.tsx` | Flask icon button to toggle modes |
| `components/AddUATTestForm.tsx` | Form to add UAT tests |
| `hooks/useUATTests.ts` | Fetch UAT tests from API |
| `lib/api.ts` | Add UAT API endpoint functions |

### Step 2: Backend Integration

Add the UAT Gateway router to your AutoCoder server:

```python
# In /path/to/autocoder/server/main.py

from .routers import uat_gateway

# Include UAT router
app.include_router(uat_gateway.router, tags=["uat"])

# Verify UAT_MODE_ENABLED setting
UAT_MODE_ENABLED = os.getenv("UAT_MODE_ENABLED", "true").lower() == "true"
```

**Copy UAT Gateway Router:**

```bash
# Copy the router file
cp /path/to/uat-plugin/routers/uat_gateway.py \
   /path/to/autocoder/server/routers/

# Copy database models if separate
cp /path/to/uat-plugin/models/uat_models.py \
   /path/to/autocoder/server/models/
```

### Step 3: Update Main App.tsx

Integrate UAT mode into your main App component:

```tsx
// In /path/to/autocoder/ui/src/App.tsx

import { UATModeProvider } from './contexts/UATModeContext'
import { UATModeToggle } from './components/UATModeToggle'
import { useUATMode } from './contexts/UATModeContext'

function App() {
  // Add mode state
  const { isUATMode } = useUATMode()

  // Fetch data based on mode
  const { data: devFeatures } = useFeatures(selectedProject)
  const { data: uatTests } = useUATTests()

  const features = isUATMode
    ? (uatTests ?? { pending: [], in_progress: [], done: [] })
    : devFeatures

  return (
    <UATModeProvider>
      {/* Add UAT Mode Toggle to header */}
      <UATModeToggle
        projectName={selectedProject}
        hasFeatures={features && features.total > 0}
      />

      {/* Pass mode to Assistant Panel */}
      <AssistantPanel
        projectName={selectedProject}
        mode={isUATMode ? 'uat' : 'dev'}
        isOpen={assistantOpen}
        onClose={() => setAssistantOpen(false)}
      />
    </UATModeProvider>
  )
}
```

### Step 4: Database Migration

Run the mode-aware conversation migration:

```bash
cd /path/to/autocoder/server/services

# Run migration for each project
python assistant_db_add_mode_column.py /path/to/project/directory
```

This adds the `mode` column to `assistant.db` for conversation separation.

### Step 5: Install Dependencies

```bash
# Python dependencies
cd /path/to/autocoder
uv pip install playwright pytest-asyncio sqlalchemy alembic

# Node.js dependencies
cd /path/to/autocoder/ui
npm install

# Install Playwright browsers
npx playwright install chromium firefox webkit
```

---

## Configuration

### Environment Variables

Add to your `.env` or environment:

```bash
# UAT Mode (default: true)
UAT_MODE_ENABLED=true

# UAT Database (relative to project directory)
UAT_DB_NAME=uat_tests.db

# Playwright Configuration
PLAYWRIGHT_BROWSERS=chromium,firefox,webkit
PLAYWRIGHT_HEADLESS=true

# DevLayer Integration (optional)
DEVLAYER_API_URL=https://api.devlayer.io
DEVLAYER_API_KEY=your_api_key

# n8n Webhooks (optional)
N8N_WEBHOOK_URL=https://your-n8n.com/webhook/uat-blocker
N8N_WEBHOOK_SECRET=your_secret_here

# Slack Notifications (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### AutoCoder Settings

```python
# In AutoCoder settings or config

UAT_CONFIG = {
    "enabled": True,
    "database": {
        "name": "uat_tests.db",
        "pool_size": 5,
        "max_overflow": 10
    },
    "test_execution": {
        "timeout_seconds": 300,
        "screenshot_on_failure": True,
        "video": True,
        "trace": "retain-on-failure"
    },
    "blocking_questions": {
        "email_verification": {"options": ["wait", "skip", "mock"]},
        "sms": {"options": ["wait", "skip", "mock"]},
        "payment_gateway": {"options": ["wait", "skip", "mock", "sandbox"]}
    }
}
```

---

## Database Setup

### UAT Tests Database Schema

The `uat_tests.db` uses a separate but compatible schema:

```sql
-- Main UAT test table (compatible with features schema)
CREATE TABLE uat_test_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    priority INTEGER NOT NULL DEFAULT 0,
    scenario TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',

    -- UAT-specific fields
    test_phase TEXT,  -- 'smoke', 'functional', 'regression', 'uat'
    journey_name TEXT,
    browser TEXT DEFAULT 'chromium',
    test_data TEXT,

    -- Standard fields
    passes BOOLEAN DEFAULT FALSE,
    in_progress BOOLEAN DEFAULT FALSE,
    dependencies TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Assistant conversations with mode separation
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'dev',  -- 'dev' or 'uat'
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_conversations_mode ON conversations (mode);
```

### Initialization

```python
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def init_uat_database(project_dir: Path) -> None:
    """Initialize UAT tests database for a project."""
    db_path = project_dir / "uat_tests.db"

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    print(f"✅ UAT database initialized at {db_path}")
```

---

## Verification

### 1. Check Frontend Mode Toggle

```bash
# Start AutoCoder UI
cd /path/to/autocoder/ui
npm run dev

# Open browser to http://localhost:5173
# Look for Flask icon in header (UAT Mode Toggle button)
```

**Expected:**
- ✅ Flask icon visible in header when project selected
- ✅ Clicking toggles between Dev/UAT modes
- ✅ Button label changes: "Add Feature" → "Add UAT Test"

### 2. Check API Endpoints

```bash
# Check UAT stats endpoint
curl http://localhost:8888/api/uat/stats/summary

# Expected response:
{
  "passing": 0,
  "in_progress": 0,
  "total": 0,
  "percentage": 0.0
}
```

### 3. Check Mode Separation

```bash
# Create Dev conversation
curl -X POST http://localhost:8888/api/assistant/conversations/my-project?mode=dev

# Create UAT conversation
curl -X POST http://localhost:8888/api/assistant/conversations/my-project?mode=uat

# List Dev conversations
curl http://localhost:8888/api/assistant/conversations/my-project?mode=dev

# List UAT conversations (should be separate list)
curl http://localhost:8888/api/assistant/conversations/my-project?mode=uat
```

**Expected:**
- ✅ Dev and UAT conversations return different lists
- ✅ Each has separate conversation IDs

### 4. Test Assistant Mode Awareness

```javascript
// Open browser console
// 1. Switch to Dev Mode
// 2. Open Assistant Panel
// 3. Check header shows "Project Assistant" with Bot icon
// 4. Send message: "What mode are you in?"
// 5. Assistant should reply about Dev Mode

// 6. Switch to UAT Mode
// 7. Open Assistant Panel
// 8. Check header shows "UAT Test Planner" with Flask icon
// 9. Send message: "What mode are you in?"
// 10. Assistant should reply about UAT Mode
```

---

## API Reference

### UAT Endpoints

#### Stats Summary
```http
GET /api/uat/stats/summary

Response:
{
  "passing": 10,
  "in_progress": 2,
  "total": 15,
  "percentage": 66.7
}
```

#### List UAT Tests
```http
GET /api/uat/tests

Response:
{
  "pending": [...],
  "in_progress": [...],
  "done": [...]
}
```

#### Create UAT Test
```http
POST /api/uat/tests
Content-Type: application/json

{
  "scenario": "User login flow",
  "journey_name": "Authentication",
  "test_phase": "functional",
  "browser": "chromium",
  "test_data": {"email": "test@example.com"}
}

Response:
{
  "message": "UAT test created",
  "test": {
    "id": 1,
    "scenario": "User login flow",
    "status": "pending",
    ...
  }
}
```

#### Generate Test Plan (AI)
```http
POST /api/uat/generate-plan
Content-Type: application/json

{
  "project_context": {
    "spec": "...",
    "completed_features": [...]
  },
  "blocker_responses": {
    "email_verification": "mock"
  }
}

Response:
{
  "proposed_framework": {
    "smoke_tests": [...],
    "functional_tests": [...],
    "regression_tests": [...],
    "uat_tests": [...]
  }
}
```

#### Execute UAT Tests
```http
POST /api/uat/trigger
Content-Type: application/json

{
  "cycle_id": "uat-20240131-001",
  "test_ids": [1, 2, 3],
  "browsers": ["chromium", "firefox"]
}

Response:
{
  "message": "UAT test execution started",
  "cycle_id": "uat-20240131-001",
  "tests_assigned": 3
}
```

### Mode-Aware Assistant Endpoints

All assistant endpoints now accept `?mode=dev|uat`:

```http
# List conversations (mode-separated)
GET /api/assistant/conversations/{project_name}?mode=dev
GET /api/assistant/conversations/{project_name}?mode=uat

# Get conversation
GET /api/assistant/conversations/{project_name}/{id}?mode=dev

# Create conversation
POST /api/assistant/conversations/{project_name}?mode=uat

# WebSocket (mode in query params)
WS /api/assistant/ws/{project_name}?mode=uat
```

---

## Troubleshooting

### Issue: Mode toggle not visible

**Symptoms:** Flask icon button doesn't appear in header

**Solutions:**
1. Check project is selected
2. Verify `UATModeProvider` wraps App
3. Check `UAT_MODE_ENABLED=true` in environment
4. Inspect browser console for React errors

```bash
# Check environment
echo $UAT_MODE_ENABLED

# Check UI components
grep -r "UATModeToggle" /path/to/autocoder/ui/src/App.tsx
```

### Issue: Conversations not separating

**Symptoms:** Dev conversations show in UAT mode

**Solutions:**
1. Run database migration
2. Check mode parameter in API calls
3. Verify localStorage keys include mode

```bash
# Run migration
cd /path/to/autocoder/server/services
python assistant_db_add_mode_column.py /path/to/project

# Check API calls
grep "mode=" /path/to/autocoder/ui/src/hooks/useConversations.ts
```

### Issue: UAT tests not appearing

**Symptoms:** UAT Mode shows empty kanban

**Solutions:**
1. Check `uat_tests.db` exists
2. Verify UAT router is mounted
3. Check API endpoint responds

```bash
# Check database
ls -la /path/to/project/uat_tests.db

# Check API
curl http://localhost:8888/api/uat/tests

# Check router
grep "uat_gateway" /path/to/autocoder/server/main.py
```

### Issue: Assistant not mode-aware

**Symptoms:** Assistant doesn't know it's in UAT mode

**Solutions:**
1. Check mode parameter passed to WebSocket
2. Verify backend session uses composite keys
3. Check system prompt includes mode context

```bash
# Check WebSocket URL
grep "wsUrl.*mode" /path/to/autocoder/ui/src/hooks/useAssistantChat.ts

# Check backend session
grep "_make_session_key" /path/to/autocoder/server/services/assistant_chat_session.py
```

### Issue: Playwright tests failing

**Symptoms:** UAT tests fail with browser errors

**Solutions:**
1. Install Playwright browsers
2. Check browser permissions
3. Verify test URLs are accessible

```bash
# Install browsers
npx playwright install chromium firefox webkit

# Test browser launch
npx playwright codegen http://localhost:3000
```

---

## Uninstallation

To remove the UAT plugin:

```bash
# 1. Remove frontend files
rm /path/to/autocoder/ui/src/contexts/UATModeContext.tsx
rm /path/to/autocoder/ui/src/components/UAT*.tsx
rm /path/to/autocoder/ui/src/hooks/useUAT*.ts

# 2. Remove backend router
rm /path/to/autocoder/server/routers/uat_gateway.py

# 3. Update App.tsx
# Remove UATModeProvider, UATModeToggle, isUATMode usage

# 4. Optional: Remove UAT databases
find /path/to/autocoder/projects -name "uat_tests.db" -delete

# 5. Remove environment variables
# Remove UAT_MODE_ENABLED, UAT_DB_NAME from .env
```

---

## Examples

### Complete UAT Workflow

```bash
# 1. Start AutoCoder
cd /path/to/autocoder
python -m uvicorn server.main:app --reload

# 2. Open UI (http://localhost:8888)
# 3. Select your project
# 4. Click Flask icon → Switch to UAT Mode

# 5. Click "Generate UAT Plan" button
# 6. AI assistant asks about blockers
#    - Email verification: "mock"
#    - SMS: "skip"
#    - Payment: "sandbox"

# 7. Review proposed test framework
#    - Smoke tests: 5 tests
#    - Functional tests: 15 tests
#    - Regression tests: 8 tests
#    - UAT tests: 12 tests

# 8. Click "Approve Plan"
# 9. Tests created in uat_tests.db

# 10. Click "Start UAT" button
# 11. Watch real-time progress in Mission Control
# 12. View results (pass/fail) in kanban board

# 13. Switch back to Dev Mode
# 14. Fix any failing tests
# 15. Switch to UAT Mode → Re-run tests
```

### API Usage Examples

```python
import requests

BASE_URL = "http://localhost:8888/api/uat"

# Generate test plan
response = requests.post(f"{BASE_URL}/generate-plan", json={
    "project_context": {
        "spec": "E-commerce app with checkout flow",
        "completed_features": ["user-auth", "product-catalog"]
    },
    "blocker_responses": {
        "email_verification": "mock",
        "payment_gateway": "sandbox"
    }
})

framework = response.json()["proposed_framework"]
print(f"Generated {len(framework['smoke_tests'])} smoke tests")

# Execute tests
response = requests.post(f"{BASE_URL}/trigger", json={
    "cycle_id": "uat-cycle-001",
    "test_ids": [1, 2, 3],
    "browsers": ["chromium"]
})

print(response.json()["message"])
# Output: "UAT test execution started"
```

---

## Support

**Documentation Updates:** This guide is maintained in:
```
/home/stu/projects/autocoder/docs/UAT-PLUGIN-DEPLOYMENT.md
```

**Issues & Questions:**
- Check main AutoCoder documentation
- Review feature specs in UAT project CLAUDE.md
- Check API logs: `/path/to/autocoder/logs/`

**Related Documentation:**
- Main AutoCoder README
- UAT Project Specification
- API Endpoint Documentation
- Database Schema Documentation

---

**Version:** 1.0.0
**Last Updated:** 2025-02-01
**Maintained By:** AutoCoder UAT Plugin Team
