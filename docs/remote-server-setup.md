# AutoCoder Remote Server Setup Guide

Complete guide to configure AutoCoder for remote access via SSH tunnels on a headless server.

## Overview

This guide documents all changes made to enable:
- Running AutoCoder on a headless server (no monitor)
- Accessing the UI through SSH tunnels from a local machine
- Persistent sessions that survive SSH disconnects
- A status page showing all running dev servers and their ports

## Prerequisites

### Server Requirements

- Linux server (tested on Debian 12)
- Python 3.11+
- Node.js 18+
- SSH access

### Install Required Packages

```bash
# Virtual display for Playwright browsers
sudo apt-get update
sudo apt-get install -y xvfb

# Terminal multiplexer for persistent sessions
sudo apt-get install -y tmux

# Python venv support (if not already installed)
sudo apt-get install -y python3-venv
```

### Install Playwright Browsers

After setting up AutoCoder, install Playwright browsers with system dependencies:

```bash
cd /path/to/autocoder

# Install Playwright npm package
npm install playwright

# Install Chromium browser with all required system dependencies (fonts, libs)
npx playwright install chromium --with-deps
```

The `--with-deps` flag installs required fonts and libraries for proper visual rendering.

## Files Created

### 1. Remote Launcher Script

**File:** `remote-start.sh` (in AutoCoder root directory)

This script manages tmux sessions and Xvfb for headless operation.

```bash
#!/bin/bash
#
# AutoCoder Remote Launcher
# =========================
# Run AutoCoder on a headless server via SSH with persistent sessions.
#
# Usage:
#   ./remote-start.sh ui          Start the Web UI (port 8888)
#   ./remote-start.sh agent <project>  Start agent for a project
#   ./remote-start.sh status      Show running sessions
#   ./remote-start.sh stop        Stop all AutoCoder sessions
#   ./remote-start.sh logs <name> Tail logs from a session
#   ./remote-start.sh attach <name> Attach to a session

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
TMUX_SESSION_PREFIX="autocoder"
UI_SESSION="${TMUX_SESSION_PREFIX}-ui"
AGENT_SESSION="${TMUX_SESSION_PREFIX}-agent"
DISPLAY_NUM=99
XVFB_PID_FILE="/tmp/autocoder-xvfb.pid"

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_deps() {
    local missing=()
    for cmd in tmux xvfb-run python3; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done
    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing dependencies: ${missing[*]}"
        exit 1
    fi
}

start_xvfb() {
    if [ -f "$XVFB_PID_FILE" ]; then
        local pid=$(cat "$XVFB_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Xvfb already running (PID: $pid)"
            export DISPLAY=":$DISPLAY_NUM"
            return 0
        fi
        rm -f "$XVFB_PID_FILE"
    fi
    log_info "Starting Xvfb on display :$DISPLAY_NUM"
    Xvfb ":$DISPLAY_NUM" -screen 0 1920x1080x24 &>/dev/null &
    echo $! > "$XVFB_PID_FILE"
    sleep 1
    if kill -0 "$(cat "$XVFB_PID_FILE")" 2>/dev/null; then
        log_info "Xvfb started (PID: $(cat "$XVFB_PID_FILE"))"
        export DISPLAY=":$DISPLAY_NUM"
    else
        log_error "Failed to start Xvfb"
        exit 1
    fi
}

stop_xvfb() {
    if [ -f "$XVFB_PID_FILE" ]; then
        local pid=$(cat "$XVFB_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping Xvfb (PID: $pid)"
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$XVFB_PID_FILE"
    fi
}

session_exists() { tmux has-session -t "$1" 2>/dev/null; }

cmd_ui() {
    check_deps
    if session_exists "$UI_SESSION"; then
        log_warn "UI session already running"
        return 1
    fi
    start_xvfb
    log_info "Starting AutoCoder Web UI in tmux session: $UI_SESSION"

    # IMPORTANT: Run uvicorn directly on fixed port 8888
    tmux new-session -d -s "$UI_SESSION" -c "$SCRIPT_DIR"
    tmux send-keys -t "$UI_SESSION" "export DISPLAY=:$DISPLAY_NUM" Enter
    tmux send-keys -t "$UI_SESSION" "export PLAYWRIGHT_HEADLESS=false" Enter
    tmux send-keys -t "$UI_SESSION" "source venv/bin/activate && python -m uvicorn server.main:app --host 127.0.0.1 --port 8888 2>&1 | tee autocoder-ui.log" Enter

    log_info "UI started on port 8888"
}

cmd_agent() {
    local project="$1"
    if [ -z "$project" ]; then
        log_error "Project name required"
        exit 1
    fi
    check_deps
    local session_name="${AGENT_SESSION}-${project//\//-}"
    if session_exists "$session_name"; then
        log_warn "Agent session already running"
        return 1
    fi
    start_xvfb
    tmux new-session -d -s "$session_name" -c "$SCRIPT_DIR"
    tmux send-keys -t "$session_name" "export DISPLAY=:$DISPLAY_NUM" Enter
    tmux send-keys -t "$session_name" "source venv/bin/activate && python autonomous_agent_demo.py --project-dir '$project' 2>&1 | tee 'agent-${project//\//-}.log'" Enter
    log_info "Agent started in session: $session_name"
}

cmd_status() {
    echo -e "\n${CYAN}AutoCoder Sessions:${NC}"
    for session in $(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep "^${TMUX_SESSION_PREFIX}"); do
        echo "  - $session (running)"
    done
    echo -e "\n${CYAN}Xvfb Status:${NC}"
    if [ -f "$XVFB_PID_FILE" ] && kill -0 "$(cat "$XVFB_PID_FILE")" 2>/dev/null; then
        echo "  Running (PID: $(cat "$XVFB_PID_FILE"))"
    else
        echo "  Not running"
    fi
}

cmd_stop() {
    log_info "Stopping all AutoCoder sessions..."
    for session in $(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep "^${TMUX_SESSION_PREFIX}"); do
        tmux kill-session -t "$session" 2>/dev/null || true
    done
    stop_xvfb
    log_info "All sessions stopped"
}

cmd_logs() {
    local name="$1"
    local session_name
    if [ "$name" = "ui" ]; then
        session_name="$UI_SESSION"
    else
        session_name="${AGENT_SESSION}-$name"
    fi
    if ! session_exists "$session_name"; then
        log_error "Session not found"
        exit 1
    fi
    tmux attach-session -t "$session_name"
}

case "${1:-help}" in
    ui) cmd_ui ;;
    agent) cmd_agent "$2" ;;
    status) cmd_status ;;
    stop) cmd_stop ;;
    logs|attach) cmd_logs "$2" ;;
    *) echo "Usage: $0 {ui|agent <project>|status|stop|logs <name>}" ;;
esac
```

Make executable:
```bash
chmod +x remote-start.sh
```

### 2. Status Page Router

**File:** `server/routers/status.py`

Provides `/status` endpoint showing all running dev servers.

```python
"""
Status Router - Shows all running dev servers across projects.
"""

import re
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from registry import list_registered_projects
from ..services.dev_server_manager import get_devserver_manager

router = APIRouter(tags=["status"])


@router.get("/api/status/devservers")
async def list_all_devservers():
    """JSON API: List all dev servers."""
    projects = list_registered_projects()
    servers = []
    for name, info in projects.items():
        project_path = Path(info.get("path", ""))
        if not project_path.exists():
            continue
        manager = get_devserver_manager(name, project_path)
        await manager.healthcheck()
        if manager.status != "stopped":
            servers.append({
                "project": name,
                "status": manager.status,
                "url": manager.detected_url,
                "pid": manager.pid,
            })
    return {"servers": servers, "count": len(servers)}


@router.get("/status", response_class=HTMLResponse)
async def status_page():
    """HTML status page showing all dev servers."""
    projects = list_registered_projects()
    rows = []

    for name, info in projects.items():
        project_path = Path(info.get("path", ""))
        if not project_path.exists():
            continue
        manager = get_devserver_manager(name, project_path)
        await manager.healthcheck()

        status = manager.status
        url = manager.detected_url or "-"
        port = "-"
        if manager.detected_url:
            match = re.search(r':(\d+)', manager.detected_url)
            if match:
                port = match.group(1)

        if status == "running":
            badge = '<span style="color:#10b981;font-weight:bold;">● Running</span>'
        elif status == "crashed":
            badge = '<span style="color:#ef4444;font-weight:bold;">● Crashed</span>'
        else:
            badge = '<span style="color:#6b7280;">○ Stopped</span>'

        url_cell = f'<a href="{url}" target="_blank">{url}</a>' if url != "-" else "-"
        rows.append(f"<tr><td>{name}</td><td>{badge}</td><td>{port}</td><td>{url_cell}</td></tr>")

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AutoCoder - Dev Servers</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body {{ font-family: system-ui; background: #f9fafb; padding: 20px; }}
            table {{ width: 100%; max-width: 800px; margin: 0 auto; background: white;
                     border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
            th {{ background: #f9fafb; font-weight: 600; }}
            h1 {{ text-align: center; }}
        </style>
    </head>
    <body>
        <h1>🚀 Dev Servers</h1>
        <table>
            <tr><th>Project</th><th>Status</th><th>Port</th><th>URL</th></tr>
            {"".join(rows) or "<tr><td colspan='4'>No projects</td></tr>"}
        </table>
        <p style="text-align:center;color:#9ca3af;font-size:12px;">Auto-refreshes every 5 seconds</p>
    </body>
    </html>
    """)
```

## Files Modified

### 1. Register Status Router

**File:** `server/routers/__init__.py`

Add import and export:

```python
from .status import router as status_router

__all__ = [
    # ... existing routers ...
    "status_router",
]
```

### 2. Include Router in App

**File:** `server/main.py`

Add to imports:
```python
from .routers import (
    # ... existing imports ...
    status_router,
)
```

Add to router includes:
```python
app.include_router(status_router)
```

### 3. (Optional) Fix Port Hardcoding in Templates

**File:** `.claude/templates/app_spec.template.txt`

Change hardcoded ports to `auto` to prevent conflicts when running multiple projects:

```xml
<port>auto</port>
<note>Use Vite default port (5173+) - do NOT hardcode ports</note>
```

## Client Configuration (Windows/Mac/Linux)

### SSH Config

Add to `~/.ssh/config` on your **local machine**:

```
Host autocoder-server
  HostName YOUR_SERVER_IP
  User YOUR_USERNAME
  IdentityFile ~/.ssh/your-key
  IdentitiesOnly yes
  ServerAliveInterval 30
  ServerAliveCountMax 3
  TCPKeepAlive yes
  ExitOnForwardFailure yes

  # AutoCoder UI (required) - adjust local port as needed
  LocalForward 8889 127.0.0.1:8888

  # AutoCoder dev server ports (4000-4099)
  # See ports-4000-4099.txt for full list to copy
```

### Port Range Convention

**Reserved ranges:**
- **3000-3999**: Reserved for LOCAL development only (never forwarded)
- **4000-4099**: AutoCoder dev servers (forwarded via SSH tunnel)

AutoCoder projects should use ports in the 4000-4099 range. SSH doesn't support dynamic ranges, so all 100 ports must be listed explicitly in your SSH config.

### Port Mapping Reference

| Local Port | Server Port | Service |
|------------|-------------|---------|
| 8889 | 8888 | AutoCoder UI + Status Page |
| 4000-4099 | 4000-4099 | AutoCoder dev servers |

### Configuring Project Ports

Each project needs its port configured in `vite.config.js`:

```javascript
// vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 4001,  // Use a unique port in 4000-4099 range
  },
})
```

**Current project port assignments:**
| Project | Port |
|---------|------|
| test-minimal | 4000 |
| visual-test | 4001 |

The app_spec template (`.claude/templates/app_spec.template.txt`) includes the port range note so new projects know to use 4000-4099.

## Usage

### 1. Connect via SSH

```bash
ssh autocoder-server
```

### 2. Start AutoCoder UI

```bash
cd /path/to/autocoder
./remote-start.sh ui
```

### 3. Access in Browser

| What | URL |
|------|-----|
| AutoCoder UI | `http://localhost:8889` |
| Status Page | `http://localhost:8889/status` |
| App Preview | Check status page for port |

### 4. Disconnect SSH (Optional)

You can close the terminal - the UI keeps running in tmux.

### 5. Reconnect Later

```bash
ssh autocoder-server
cd /path/to/autocoder
./remote-start.sh status    # Check what's running
./remote-start.sh attach ui # Reattach to UI session
```

### 6. Stop Everything

```bash
./remote-start.sh stop
```

## How It Works

### Architecture

```
┌──────────────────┐                    ┌─────────────────────────────┐
│  Local Machine   │    SSH Tunnels    │         Server              │
│                  │                    │                             │
│  Browser         │                    │  tmux: autocoder-ui         │
│  localhost:8889 ─┼───► :8888 ────────►│    └─ uvicorn (FastAPI)    │
│                  │                    │                             │
│  Browser         │                    │  Xvfb :99 (virtual display) │
│  localhost:4001 ─┼───► :4001 ────────►│    └─ Playwright browsers  │
│                  │                    │                             │
└──────────────────┘                    │  Dev servers (per project)  │
                                        │    └─ vite/next/etc         │
                                        └─────────────────────────────┘
```

### Components

1. **Xvfb** - Virtual framebuffer providing display :99 for Playwright
2. **tmux** - Terminal multiplexer keeping sessions alive after SSH disconnect
3. **uvicorn** - ASGI server running FastAPI on fixed port 8888
4. **SSH tunnels** - Secure port forwarding from local machine to server

## Troubleshooting

### Port Already in Use

```bash
# Find what's using a port
sudo lsof -i :8888

# Kill it
kill <PID>
```

### UI Won't Start

```bash
# Check logs
./remote-start.sh logs ui

# Or check the log file
tail -50 autocoder-ui.log
```

### Can't Connect from Browser

1. Verify SSH tunnel is active (check your SSH connection)
2. Verify server is running: `ss -tlnp | grep 8888`
3. Verify correct local port in browser URL

### Xvfb Issues

```bash
# Check if Xvfb is running
ps aux | grep Xvfb

# Restart everything
./remote-start.sh stop
./remote-start.sh ui
```

## Verifying Playwright Works

After setup, test that Playwright can run visual tests:

```bash
# Ensure Xvfb is running
./remote-start.sh status

# Run test script
export DISPLAY=:99
node -e "
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({
    headless: false,
    args: ['--disable-gpu', '--no-sandbox']
  });
  const page = await browser.newPage();
  await page.goto('https://example.com');
  await page.screenshot({ path: '/tmp/test.png' });
  await browser.close();
  console.log('SUCCESS: Playwright visual testing works!');
})();
"
```

If successful, you'll see "SUCCESS" and a screenshot at `/tmp/test.png`.

### Browser Launch Args

For headless servers, Playwright needs these browser args:
- `--disable-gpu` - Disable GPU acceleration (not available in Xvfb)
- `--no-sandbox` - Required for running as non-root in some environments

## Summary of Changes

| Item | Type | Purpose |
|------|------|---------|
| `xvfb` | Package | Virtual display for headless browsers |
| `tmux` | Package | Persistent terminal sessions |
| `playwright` | npm package | Browser automation |
| `chromium` | Playwright browser | Visual testing browser |
| `remote-start.sh` | New file | Manages tmux/Xvfb lifecycle |
| `server/routers/status.py` | New file | Status page showing dev servers |
| `server/routers/__init__.py` | Modified | Export status_router |
| `server/main.py` | Modified | Include status_router |
| SSH config | Client-side | Port forwarding configuration |
