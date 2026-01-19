# AutoCoder Remote Setup Guide

Run AutoCoder on a headless server via SSH with persistent sessions.

## Prerequisites

### Server Requirements

1. **Xvfb** - Virtual framebuffer for headless browser support
   ```bash
   sudo apt-get update && sudo apt-get install -y xvfb
   ```

2. **tmux** - Terminal multiplexer for persistent sessions
   ```bash
   sudo apt-get install -y tmux
   ```

3. **Python 3.11+** with venv support
   ```bash
   sudo apt-get install -y python3 python3-venv
   ```

4. **Node.js 18+** for Playwright and the React UI
   ```bash
   # Check version
   node --version
   ```

### What Was Installed

On the core-control server (138.201.197.54), the following was set up:

| Component | Purpose |
|-----------|---------|
| `xvfb` | Virtual X11 display for Playwright browsers |
| `tmux` | Keeps sessions alive after SSH disconnect |
| `remote-start.sh` | Launcher script in the autocoder directory |

## SSH Tunnel Configuration

AutoCoder runs on the server but you access it through your local browser via SSH tunnels.

### Port Mapping

| Local Port | Server Port | Service |
|------------|-------------|---------|
| 8889 | 8888 | AutoCoder Web UI |
| 5174 | 5173 | Vite dev server (optional) |
| 3001 | 3000 | App preview - React/Next.js |
| 5001 | 5000 | App preview - Flask/other |
| 4321 | 4321 | App preview - Astro |

**Note:** Local ports are offset to avoid conflicts with services running on your local machine.

### MobaXterm Setup (MobaSSHTunnel)

1. Open MobaXterm → Tools → MobaSSHTunnel
2. Click "New SSH tunnel"
3. Configure each tunnel:

**Tunnel 1 - AutoCoder UI (Required)**
```
Local port:     8889
SSH server:     138.201.197.54:22
Remote server:  127.0.0.1
Remote port:    8888
```

**Tunnel 2 - App Preview (Recommended)**
```
Local port:     3001
SSH server:     138.201.197.54:22
Remote server:  127.0.0.1
Remote port:    3000
```

**Tunnel 3 - Vite Dev (Optional)**
```
Local port:     5174
SSH server:     138.201.197.54:22
Remote server:  127.0.0.1
Remote port:    5173
```

4. Save and start the tunnels

### Command Line SSH (Alternative)

```bash
ssh -L 8889:localhost:8888 \
    -L 3001:localhost:3000 \
    -L 5174:localhost:5173 \
    stu@138.201.197.54
```

## Usage

### Starting AutoCoder

1. **Connect to server** (with tunnels active)

2. **Start the Web UI**
   ```bash
   cd ~/projects/autocoder
   ./remote-start.sh ui
   ```

3. **Open in your local browser**
   ```
   http://localhost:8889
   ```

4. **You can now disconnect SSH** - the UI keeps running

### Script Commands

```bash
# Start Web UI in background
./remote-start.sh ui

# Start agent for a project
./remote-start.sh agent myproject

# Check what's running
./remote-start.sh status

# View live logs
./remote-start.sh logs ui
./remote-start.sh logs myproject

# Attach to session (interactive)
./remote-start.sh attach ui

# Stop everything
./remote-start.sh stop
```

### Reconnecting Later

1. Start your SSH tunnels in MobaXterm
2. SSH into the server
3. Check status:
   ```bash
   cd ~/projects/autocoder
   ./remote-start.sh status
   ```
4. If running, just open `http://localhost:8889`
5. If stopped, run `./remote-start.sh ui`

## How It Works

### Architecture

```
┌─────────────────────┐     SSH Tunnels      ┌─────────────────────────────┐
│   Your Machine      │◄───────────────────► │   Server (138.201.197.54)   │
│                     │                       │                             │
│  Browser            │                       │  ┌─────────────────────┐   │
│  localhost:8889 ────┼───► port 8888 ───────►│  │ AutoCoder Web UI    │   │
│                     │                       │  │ (FastAPI + React)   │   │
│  Browser            │                       │  └─────────────────────┘   │
│  localhost:3001 ────┼───► port 3000 ───────►│                             │
│                     │                       │  ┌─────────────────────┐   │
│                     │                       │  │ Your App Dev Server │   │
│                     │                       │  │ (built by agent)    │   │
│                     │                       │  └─────────────────────┘   │
│                     │                       │                             │
│                     │                       │  ┌─────────────────────┐   │
│                     │                       │  │ Xvfb :99            │   │
│                     │                       │  │ (virtual display)   │   │
│                     │                       │  │                     │   │
│                     │                       │  │  ┌───────────────┐  │   │
│                     │                       │  │  │ Playwright    │  │   │
│                     │                       │  │  │ Browser       │  │   │
│                     │                       │  │  └───────────────┘  │   │
│                     │                       │  └─────────────────────┘   │
│                     │                       │                             │
│                     │                       │  tmux sessions keep        │
│                     │                       │  everything running        │
└─────────────────────┘                       └─────────────────────────────┘
```

### Components

1. **Xvfb (X Virtual Framebuffer)**
   - Creates a fake display `:99` on the server
   - Playwright browsers render into this virtual display
   - No physical monitor needed

2. **tmux (Terminal Multiplexer)**
   - Sessions persist after SSH disconnect
   - Each service runs in its own tmux session
   - Prefixed with `autocoder-` for easy identification

3. **remote-start.sh**
   - Manages Xvfb lifecycle
   - Creates/destroys tmux sessions
   - Handles logging

## Troubleshooting

### "Session already running"

```bash
./remote-start.sh status  # See what's running
./remote-start.sh stop    # Stop everything
./remote-start.sh ui      # Start fresh
```

### Can't connect to localhost:8889

1. Check tunnels are running in MobaXterm
2. Check UI is running: `./remote-start.sh status`
3. Check logs: `./remote-start.sh logs ui`

### Playwright browser errors

```bash
# Ensure Xvfb is running
./remote-start.sh status

# If Xvfb not running, restart everything
./remote-start.sh stop
./remote-start.sh ui
```

### Port already in use on server

Check what's using the port:
```bash
sudo lsof -i :8888
```

The script automatically finds available ports starting from 8888.

### App preview not loading

1. Check which port your app is using (visible in agent logs)
2. Ensure you have a tunnel for that port
3. Common ports: 3000, 5173, 4321, 5000

## Running Multiple Projects

When running multiple AutoCoder projects simultaneously, each project's dev server needs a unique port.

### Port Assignment Strategy

**Recommended:** Let Vite auto-assign ports (don't hardcode in package.json)

```json
// package.json - let Vite find available port
{
  "scripts": {
    "dev": "vite"  // NOT "vite --port 3000"
  }
}
```

Vite will use 5173, then 5174, 5175, etc. if ports are occupied.

### Tunnel Setup for Multiple Projects

Set up a range of tunnels in MobaXterm:

| Local Port | Remote Port | Purpose |
|------------|-------------|---------|
| 5173 | 5173 | Project 1 dev server |
| 5174 | 5174 | Project 2 dev server |
| 5175 | 5175 | Project 3 dev server |
| 3001 | 3000 | Alternative (if project uses port 3000) |

### Checking Which Port a Project Uses

The AutoCoder UI shows the detected URL in the dev server panel. You can also check:

```bash
# See all listening ports
ss -tlnp | grep -E "(vite|node)"

# Or check a specific project's dev server
ps aux | grep vite
```

### If Port Conflicts Occur

1. Stop the conflicting dev server in the UI
2. Edit the project's `package.json` to use a different port
3. Restart the dev server

## YOLO Mode (Headless Testing)

If you don't need visual browser testing:

```bash
# Set in .env
echo "PLAYWRIGHT_HEADLESS=true" >> ~/projects/autocoder/.env

# Or run agent with --yolo flag (skips browser entirely)
./remote-start.sh agent myproject --yolo
```

This runs faster but skips visual verification.

## Files Created

| File | Purpose |
|------|---------|
| `remote-start.sh` | Main launcher script |
| `docs/remote-setup.md` | This documentation |
| `/tmp/autocoder-xvfb.pid` | Xvfb process ID (runtime) |
| `autocoder-ui.log` | UI session logs |
| `agent-*.log` | Agent session logs |
