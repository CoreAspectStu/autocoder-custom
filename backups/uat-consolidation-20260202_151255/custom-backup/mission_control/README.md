# Mission Control

**Unified monitoring + human-in-the-loop interface for AutoCoder**

---

## What is Mission Control?

Mission Control combines two powerful features into one interface:

1. **Status Dashboard** (already exists)
   - Active agents with mascots
   - API quota tracking (5-hour window)
   - Feature progress (passing/total)
   - System health metrics
   - Escaped process detection

2. **DevLayer** (newly integrated)
   - Agents can ask you questions
   - Request credentials/decisions
   - Report blockers
   - Send chat messages
   - Create annotations (bugs/ideas/workarounds)

## Quick Start

### Installation

```bash
# Install Mission Control
cd ~/projects/autocoder
python custom/mission-control/install.py

# Enable it
echo "MISSION_CONTROL_ENABLED=true" >> .env

# Start AutoCoder
autocoder-ui
```

### Using DevLayer

**In the UI:**
- Press `L` to toggle DevLayer mode
- See attention queue (critical requests first)
- Respond to agent requests
- Chat with agents
- View/create annotations

**From agents (after enabling):**

Agents automatically have access to DevLayer tools:
- `devlayer_ask_question` - Ask human a question
- `devlayer_report_blocker` - Report blocker, get guidance
- `devlayer_request_decision` - Request human decision
- `devlayer_request_auth` - Request credentials
- `devlayer_send_chat` - Send status updates
- `devlayer_create_annotation` - Document bugs/ideas

---

## Architecture

### Directory Structure

```
custom/mission-control/
├── README.md                    # This file
├── install.py                   # Installation script
├── integration.py               # Client.py integration helper
├── client/
│   ├── __init__.py
│   └── devlayer_client.py       # Python API for agents
├── mcp_server/
│   ├── __init__.py
│   └── mission_control_mcp.py   # MCP tools for Claude SDK
├── server/                      # (existing - in autocoder/server/routers/)
│   ├── devlayer.py              # DevLayer API
│   └── status.py                # Status dashboard
└── docs/
    ├── examples.md              # Usage examples
    ├── api.md                   # API reference
    └── troubleshooting.md       # Common issues
```

### How It Works

**1. Backend API** (`server/routers/devlayer.py`)
- SQLite database: `~/.autocoder/devlayer.db`
- REST endpoints for requests, chat, annotations
- n8n webhook integration (optional)

**2. Python Client** (`client/devlayer_client.py`)
- Standalone library agents can import
- Async/await API
- Automatic polling for responses
- Timeout handling

**3. MCP Server** (`mcp_server/mission_control_mcp.py`)
- Exposes DevLayer as MCP tools
- Claude SDK agents call tools
- Handles request/response cycle

**4. React UI** (`ui/src/components/DevLayer.tsx`)
- Real-time updates (polling every 3s for requests, 2s for chat)
- Multi-project dashboard
- Per-project detail view
- Mute/unmute notifications

---

## Usage Examples

### Agent Asks Question

```python
# Agent code (automatic via MCP tools)
# Claude decides to use devlayer_ask_question tool

Agent: "Should I use REST or GraphQL for the API?"
[DevLayer creates 'question' request, agent waits]
Human responds via UI: "Use REST for now, we can add GraphQL later"
Agent: "Got it! Implementing REST API endpoints..."
```

### Agent Reports Blocker

```python
Agent: "Database migration failed - production DB is read-only"
[DevLayer creates 'blocker' request with priority='critical']
Human responds: "Use staging DB at staging.example.com"
Agent: "Thanks! Switching to staging database..."
```

### Agent Requests Credentials

```python
Agent: "I need STRIPE_API_KEY to implement checkout"
[DevLayer creates 'auth_needed' request]
Human responds: "sk-test-4eC39HqLyjWDarjtT1zdp7dc"
Agent: "Credential received. Proceeding with Stripe integration"
```

### Agent Sends Status Update

```python
# Fire-and-forget chat message
await devlayer.send_chat("Starting database migration (est. 5 min)")
await devlayer.send_chat("Migration complete! 127 records migrated")
```

### Agent Creates Annotation

```python
# Document workaround for later
await devlayer.create_annotation(
    type="workaround",
    content="Auth API is flaky - implemented 3x retry with exponential backoff"
)

# Report bug
await devlayer.create_annotation(
    type="bug",
    content="Payment form validation fails on Safari - needs testing"
)
```

---

## Python API Reference

### DevLayerClient

```python
from custom.mission_control.client import DevLayerClient

client = DevLayerClient(project_name="my-app")

# Ask question (blocks until response)
response = await client.ask_question(
    message="Should I use TypeScript or JavaScript?",
    context="Building a new React app",
    priority=RequestPriority.NORMAL
)

# Report blocker
guidance = await client.report_blocker(
    message="API endpoint returns 404",
    context="Testing payment integration",
    priority=RequestPriority.CRITICAL
)

# Request decision
decision = await client.request_decision(
    message="Monolith or microservices for MVP?",
    context="Expected 1000 users at launch"
)

# Request credentials
api_key = await client.request_auth(
    service_name="Stripe",
    key_name="STRIPE_API_KEY",
    context="Implementing checkout flow"
)

# Send chat (fire-and-forget)
await client.send_chat("Starting deployment...")

# Create annotation
await client.create_annotation(
    type="bug",  # or "comment", "workaround", "idea"
    content="Dark mode toggle needs styling fix",
    feature_id="42"  # optional
)
```

### Request Types & Priorities

```python
from custom.mission_control.client import RequestType, RequestPriority

# Types
RequestType.QUESTION      # General question
RequestType.AUTH_NEEDED   # Needs credentials
RequestType.BLOCKER       # Stuck, can't proceed
RequestType.DECISION      # Needs human decision

# Priorities
RequestPriority.CRITICAL  # Show first, red badge
RequestPriority.NORMAL    # Yellow badge
RequestPriority.LOW       # Gray badge
```

---

## Configuration

### Environment Variables

```bash
# Enable/disable Mission Control
MISSION_CONTROL_ENABLED=true

# Optional: n8n webhook for Slack/email notifications
DEVLAYER_WEBHOOK_URL=https://n8n.example.com/webhook/devlayer
```

### Timeout Settings

Edit `custom/mission-control/client/devlayer_client.py`:

```python
client = DevLayerClient(
    project_name="my-app",
    timeout=600,      # 10 minutes (default: 300s)
    poll_interval=10  # Check every 10s (default: 5s)
)
```

---

## Updating AutoCoder (Upstream Merge)

Mission Control is **update-safe** - it lives in `custom/` which upstream never touches.

**After updating from upstream:**

1. Mission Control files are untouched (safe)
2. Re-run install script if `client.py` was overwritten:
   ```bash
   python custom/mission-control/install.py
   ```
3. Re-enable in `.env`: `MISSION_CONTROL_ENABLED=true`
4. Done!

**Why it's safe:**
- All code in `custom/mission-control/` (never touched by upstream)
- Integration is a 3-line patch to `client.py`
- Easy to re-apply if needed

---

## Uninstallation

```bash
# Disable without uninstalling
echo "MISSION_CONTROL_ENABLED=false" >> .env

# Full uninstall (removes from client.py)
python custom/mission-control/install.py --uninstall
```

---

## Troubleshooting

### Agent doesn't have DevLayer tools

**Cause:** `MISSION_CONTROL_ENABLED` not set to `true`

**Fix:**
```bash
echo "MISSION_CONTROL_ENABLED=true" > .env
# Restart AutoCoder
```

### Requests not showing in UI

**Cause:** DevLayer mode not enabled

**Fix:** Press `L` in UI to toggle DevLayer mode

### Agent times out waiting for response

**Cause:** No human responded within timeout (default 5 min)

**Fix:**
1. Increase timeout in `devlayer_client.py`
2. Or respond faster :)

### Database locked errors

**Cause:** Multiple agents writing to `~/.autocoder/devlayer.db` simultaneously

**Fix:** SQLite handles this automatically with retries (should be rare)

---

## Roadmap

**Current (v1.0):**
- ✅ Full Python client API
- ✅ MCP server integration
- ✅ React UI with polling
- ✅ Multi-project dashboard
- ✅ Installation script

**Future (v2.0):**
- [ ] WebSocket for real-time updates (replace polling)
- [ ] Audio/visual notifications for critical requests
- [ ] Mobile-friendly UI
- [ ] n8n workflow templates (Slack notifications)
- [ ] Agent context from annotations (read before starting feature)
- [ ] Prompt templates teaching agents when to ask for help

---

## Contributing

Mission Control is part of the AutoCoder custom features.

**Found a bug?** Create issue in autocoder-custom repo.

**Want to add features?** All code in `custom/mission-control/` - modify freely!

---

## License

Same as AutoCoder (open source).

---

**Built with ❤️ for better human-AI collaboration**
