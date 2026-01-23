# AutoCoder Custom Additions

This directory tracks all custom modifications made to the vanilla AutoCoder project for remote server deployment.

## 🚀 TL;DR - Quick Start

**What is this?** Remote server infrastructure for running AutoCoder on headless servers via SSH.

**Quick commands:**
```bash
./remote-start.sh ui              # Start Web UI (port 8888)
./remote-start.sh status          # Check what's running
./remote-start.sh doctor          # Check system health
./remote-start.sh --help          # Show all commands
```

**Access:** http://localhost:8888 (via SSH tunnel: `ssh -L 8888:localhost:8888 stu@server`)

**Documentation:**
- **Quick reference:** `custom/docs/remote-quickstart.md`
- **User guide:** `custom/docs/remote-setup.md`
- **Full inventory:** Keep reading this file

**Slash commands:** `/autocoder` to start UI, `/autocoder-help` for reference

---

## ⚡ **UPDATING AUTOCODER FROM UPSTREAM?**

**🚨 READ THIS FIRST:** [`docs/UPDATE-GUIDE.md`](docs/UPDATE-GUIDE.md)

This guide documents the exact process for safely updating while preserving all custom work. **IMPORTANT:** Tell Claude to read this file before starting any update process.

**Quick summary:**
1. Create backup branch: `git branch backup-$(date +%Y-%m-%d)`
2. Pull upstream: `git pull origin master`
3. Resolve conflicts (guide shows patterns)
4. Install new deps: `pip install -r requirements.txt`
5. Test everything works

**Last successful update:** 2026-01-22 (merged 28 commits, zero issues)

---

## 📁 Directory Structure

```
autocoder/
├── custom/                            # This directory - tracks all customizations
│   ├── README.md                      # This file - master index
│   ├── docs/                          # Remote server documentation
│   │   ├── UPDATE-GUIDE.md           # ⚡ Upstream update process (READ FIRST!)
│   │   ├── UPDATE-CHECKLIST.md       # Quick update reference card
│   │   ├── remote-quickstart.md      # Quick reference card
│   │   ├── remote-setup.md           # User guide
│   │   ├── remote-server-setup.md    # Complete setup instructions
│   │   ├── auth-settings-customization.md  # Auth system (deprecated)
│   │   ├── future-improvements.md    # Feature wishlist
│   │   └── ports-4000-4099.txt       # SSH config port mappings
│   ├── patches/                       # Patch system for upstream updates
│   │   ├── apply-remote-access.sh    # Auto-apply script (all patches)
│   │   ├── port-assignment.patch     # Port assignment system (4000-4099)
│   │   └── README.md                  # Patch documentation
│   └── auth_config.py                 # [DEPRECATED] Auth utilities (unused)
│
├── remote-start.sh                    # [CUSTOM] Main launcher script
├── server/routers/
│   └── status.py                      # [CUSTOM] Enhanced dashboard (1132 lines)
└── docs/
    └── README.md                      # [CUSTOM] Documentation index
```

**Global Additions (outside this repo):**
```
~/.claude/commands/
├── autocoder.md                       # /autocoder slash command
└── autocoder-help.md                  # /autocoder-help slash command
```

---

## 📋 Complete File Inventory

### Scripts

| File | Location | Purpose | Lines |
|------|----------|---------|-------|
| `remote-start.sh` | `/` | tmux/Xvfb session manager with doctor command | 430 |
| `apply-remote-access.sh` | `custom/patches/` | Auto-applies patches after git pull | 77 |

### Server Routes & Services

| File | Location | Purpose | Lines |
|------|----------|---------|-------|
| `status.py` | `server/routers/` | [CUSTOM] Enhanced dashboard with health metrics, agent status, spec modal with XML formatting | 1132 |

**Note:** After 2026-01-22 update, auth customizations were removed in favor of upstream's simplified approach. Port assignment system was also deprecated by upstream.

### Documentation

| File | Location | Purpose | Words |
|------|----------|---------|-------|
| `custom/README.md` | `custom/` | This file - master index | ~7000 |
| `UPDATE-GUIDE.md` | `custom/docs/` | **⚡ CRITICAL** Upstream update process | ~2500 |
| `UPDATE-CHECKLIST.md` | `custom/docs/` | Quick update reference card | ~400 |
| `remote-quickstart.md` | `custom/docs/` | Quick reference cheat sheet | ~300 |
| `remote-setup.md` | `custom/docs/` | Complete user guide | ~2000 |
| `remote-server-setup.md` | `custom/docs/` | Detailed server setup guide | ~3000 |
| `auth-settings-customization.md` | `custom/docs/` | [DEPRECATED] Auth settings (removed 2026-01-22) | ~3200 |
| `future-improvements.md` | `custom/docs/` | Feature wishlist from brainstorming | ~800 |
| `ports-4000-4099.txt` | `custom/docs/` | SSH tunnel port mappings | ~100 |
| `remote-server-setup.md` | `custom/docs/` | Full setup instructions | ~3500 |
| `future-improvements.md` | `custom/docs/` | Strategic improvements from party-mode | ~600 |
| `ports-4000-4099.txt` | `custom/docs/` | SSH tunnel config | - |
| `patches/README.md` | `custom/patches/` | Patch system docs | ~300 |
| `docs/README.md` | `docs/` | Documentation index | ~150 |

### Slash Commands (Global)

| File | Location | Purpose |
|------|----------|---------|
| `autocoder.md` | `~/.claude/commands/` | Start UI remotely |
| `autocoder-help.md` | `~/.claude/commands/` | Show full command reference |

---

## 🎯 What These Customizations Add

### 1. Remote Server Infrastructure
**Problem Solved:** Run AutoCoder on headless server via SSH

**Components:**
- `remote-start.sh` - Session management (start/stop/status/logs/attach)
- Xvfb integration for headless Playwright browsers
- tmux sessions that survive SSH disconnects
- Port 8888 for Web UI, 4000-4099 for dev servers

**Quick Start:**
```bash
./remote-start.sh ui              # Start Web UI
./remote-start.sh status          # Check what's running
```

### 2. Enhanced Status Dashboard
**Problem Solved:** See all projects, health metrics, and dev server status at a glance

**Access:** `http://localhost:8888/status` (after starting UI)

**Features:**
- **Summary Stats Dashboard:** Running servers, active agents, idle projects, total count
- **Project Cards:** Expandable cards with modern UI design
- **Health Indicators:** Color-coded status (green/yellow/red/gray) based on feature completion
- **Feature Progress:** Progress bars showing test completion percentage from features.db
- **Agent Status:** Detects running agents via tmux sessions
- **Quick Actions:**
  - View Spec (opens modal with formatted spec - XML tags converted to readable headings)
  - Open App (dev server URL if running)
  - View Logs (agent tmux session logs)
- **Port Information:** Banner showing 4000-4099 port convention
- **Real-time Updates:** Auto-refresh every 5 seconds
- **Project Metadata:** Project type, assigned port, spec status
- **Authentication Settings:** Toggle between Claude Login and API Key authentication (see #3 below)

### 3. Authentication Settings Panel
**Problem Solved:** Switching between Claude Login and API Key authentication requires manual .env editing

**Access:** `http://localhost:8888/status` (top panel)

**Features:**
- **Radio Toggle:** Switch between "Claude Login" and "API Key" methods
- **Secure Input:** Password-masked API key field
- **Auto-save to .env:** Updates `ANTHROPIC_AUTH_TOKEN` in .env file
- **Visual Feedback:** Success/error messages with status indicators
- **Key Privacy:** API keys never exposed in API responses, masked in UI
- **Instant Apply:** Changes saved immediately, take effect on next agent start

**How It Works:**
1. Select authentication method (Claude Login or API Key)
2. If API Key selected, enter your Anthropic API key
3. Click "Save Authentication Settings"
4. Settings written to `.env` file
5. Restart any running agents for changes to apply

**Documentation:** See `custom/docs/auth-settings-customization.md` for full reapply guide

### 4. Automatic Port Assignment
**Problem Solved:** Dev servers use framework defaults (3000, 5173) incompatible with SSH tunnels

**How It Works:**
- Projects automatically assigned ports in 4000-4099 range
- Port stored in `.autocoder/config.json` per project
- Conflict detection across all projects
- Templates use `{port}` placeholder (e.g., `npm run dev -- --port {port}`)

**Modified Files:**
- `server/services/project_config.py` - Port assignment logic
- `server/schemas.py` - Added `assigned_port` field
- `server/routers/devserver.py` - Returns assigned port in config
- `server/routers/status.py` - Displays assigned port (source of truth)

**Port Detection Priority:**
1. AutoCoder assigned port (`.autocoder/config.json`) - **SOURCE OF TRUTH**
2. Config files (package.json, vite.config.js) - fallback
3. Framework defaults (3000, 5173) - last resort

**Example:**
```bash
# QR project gets assigned port 4000 (instead of hardcoded 3006)
# Status page shows: QR → port 4000
# Command becomes: npm run dev -- --port 4000
# SSH tunnel: ssh -L 4000:localhost:4000 stu@server
```

### 5. Patch System
**Problem Solved:** Survive upstream updates without losing custom code

**How It Works:**
- After `git pull`, run `custom/patches/apply-remote-access.sh`
- Auto-patches core files to integrate status router
- Documented in `custom/patches/README.md`

### 6. Comprehensive Documentation
**Problem Solved:** Multiple learning paths for different needs

**Levels:**
- Quick reference card (`custom/docs/remote-quickstart.md`)
- User guide (`custom/docs/remote-setup.md`)
- Full setup guide (`custom/docs/remote-server-setup.md`)
- Auth settings reapply guide (`custom/docs/auth-settings-customization.md`)

### 7. Claude Code Integration
**Problem Solved:** Quick access from anywhere

**Commands:**
- `/autocoder` - Start the UI remotely
- `/autocoder-help` - Show complete command reference

---

## 📝 Changelog

### 2026-01-22 (Latest)
- ✅ **Authentication Settings Panel** - Web UI for switching between Claude Login and API Key authentication
  - Added auth settings panel to `/status` page with radio buttons and password input
  - Created `custom/auth_config.py` utility for managing .env file updates
  - Extended `server/schemas.py` with auth_method and api_key_configured fields
  - Modified `server/routers/settings.py` to handle auth method switching
  - API keys stored securely in `.env` file, never exposed in responses
  - Comprehensive documentation in `custom/docs/auth-settings-customization.md`
  - Full reapply guide for surviving upstream updates

### 2026-01-20
- ✅ **Enhanced Status Dashboard** - Complete redesign with card-based UI, health indicators, progress bars, agent status, and quick actions
  - Added `get_project_health()` to read features.db for test completion stats
  - Added `get_agent_status()` to detect running agents via tmux
  - Summary stats dashboard (running/agents/idle/total)
  - Color-coded health indicators based on feature completion
  - Expandable project cards with progressive disclosure
  - Quick action buttons with modal UI for viewing specs
  - **Spec Modal**: View Spec button opens modal with spec content and project details (project type, port, features, completion %)
  - **XML Formatting**: Spec content automatically parsed and formatted - XML tags (e.g., `<project_name>`) converted to readable headings ("Project Name:")
  - Hierarchical formatting with proper indentation for nested XML sections
  - Removed non-functional "Open Editor" button
  - Real-time updates every 5 seconds
- ✅ **Automatic port assignment (4000-4099 range)** - Dev servers now automatically assigned ports from SSH-friendly range
- ✅ Added TL;DR section to `custom/README.md`
- ✅ Implemented `doctor` command in `remote-start.sh` (7-step health check)
- ✅ Improved port detection in `status.py` (lsof-based with socket fallback)
- ✅ Enhanced help command with doctor reference
- ✅ Documented future improvements in `custom/docs/future-improvements.md`
- ✅ Created `custom/` directory structure
- ✅ Moved `docs/remote-*.md` to `custom/docs/`
- ✅ Moved `patches/` to `custom/patches/`
- ✅ Created this master README.md
- ✅ Added `/autocoder` and `/autocoder-help` slash commands

### 2026-01-19
- ✅ Created patch system in `patches/`
- ✅ Added comprehensive remote server documentation
- ✅ Implemented SSH tunnel port conventions (4000-4099)

### 2026-01-18
- ✅ Created `status.py` router with port detection
- ✅ Implemented `remote-start.sh` launcher
- ✅ Added Xvfb and tmux integration
- ✅ Created initial documentation suite

---

## 🔧 Maintenance Instructions

### After Pulling Upstream Updates

```bash
cd ~/projects/autocoder
git pull origin main

# If you see conflicts or missing functionality:
custom/patches/apply-remote-access.sh

# Restart services:
./remote-start.sh stop
./remote-start.sh ui
```

### Updating This Index

When you add new customizations:

1. **Add the file to the inventory table** above
2. **Document what it does** in "What These Customizations Add"
3. **Add entry to changelog** with date
4. **Update line counts** if files changed significantly
5. **Test that everything still works**
6. **Commit changes:** `git add custom/ && git commit -m "Update custom index"`

### Sharing These Customizations

To replicate on another AutoCoder installation:

```bash
# Copy the custom/ folder
rsync -av custom/ other-autocoder/custom/

# Copy the main script
cp remote-start.sh other-autocoder/

# Copy the status router
cp server/routers/status.py other-autocoder/server/routers/

# Apply patches
cd other-autocoder
custom/patches/apply-remote-access.sh

# Copy slash commands (optional)
cp ~/.claude/commands/autocoder*.md other-machine:~/.claude/commands/
```

---

## 🚀 Quick Reference

### Start/Stop Commands

```bash
./remote-start.sh ui              # Start Web UI (port 8888)
./remote-start.sh agent <project> # Start agent for project
./remote-start.sh status          # Show running sessions
./remote-start.sh logs ui         # View UI logs
./remote-start.sh attach ui       # Attach to session (Ctrl+B, D to detach)
./remote-start.sh stop            # Stop all sessions
```

### SSH Tunnel Setup (Local Machine)

```bash
ssh -L 8888:localhost:8888 \
    -L 4000:localhost:4000 \
    -L 4001:localhost:4001 \
    stu@138.201.197.54
```

### Access URLs

- **Web UI:** http://localhost:8888
- **Status Page:** http://localhost:8888/status
- **Project Dev Servers:** http://localhost:4000-4099

### Slash Commands (Global)

- `/autocoder` - Start UI on remote server
- `/autocoder-help` - Show complete reference

---

## 📚 Documentation Hierarchy

1. **Quick Start** → `custom/docs/remote-quickstart.md`
   - TL;DR for daily use
   - Command cheat sheet
   - 1-2 minutes

2. **User Guide** → `custom/docs/remote-setup.md`
   - Complete usage instructions
   - Architecture diagrams
   - Troubleshooting
   - 10-15 minutes

3. **Setup Guide** → `custom/docs/remote-server-setup.md`
   - From-scratch server setup
   - All dependencies
   - File-by-file explanation
   - 30-45 minutes

4. **Patch System** → `custom/patches/README.md`
   - How patches work
   - Manual conflict resolution
   - 5 minutes

5. **This File** → `custom/README.md`
   - Complete inventory
   - Maintenance procedures
   - Master index

---

## 🔗 Key Files Quick Links

| What You Need | File |
|---------------|------|
| Start the UI | `./remote-start.sh ui` |
| Check status | `./remote-start.sh status` |
| View all projects | http://localhost:8888/status |
| Quick commands | `custom/docs/remote-quickstart.md` |
| Full user guide | `custom/docs/remote-setup.md` |
| Fix after git pull | `custom/patches/apply-remote-access.sh` |
| Add new customizations | Update this file (`custom/README.md`) |

---

## 💡 Design Decisions

### Why This Structure?

1. **Single Source of Truth** - Everything tracked in one place
2. **Easy to Identify** - Clear separation of custom vs. upstream
3. **Portable** - Can copy entire `custom/` folder to share
4. **Git-Friendly** - Clean diffs, easy to review changes
5. **Maintainable** - Patch system ensures survival through updates

### Why Some Files Are Outside `custom/`?

- **`remote-start.sh`** - Needs project root to access `venv/`, `server/`, etc.
- **`server/routers/status.py`** - Python import paths require this location
- **`~/.claude/commands/`** - Global commands should be in home directory

These are documented in the inventory above with `[CUSTOM]` tags.

### Port Convention Rationale

- **3000-3999** - Reserved for LOCAL development (not forwarded)
- **4000-4099** - AutoCoder dev servers (forwarded via SSH)
- **8888** - AutoCoder Web UI (fixed, not configurable)

This prevents port conflicts between local and remote development.

---

## 🆘 Troubleshooting

### "Can't find custom/docs/"

You may be in the wrong directory:
```bash
cd ~/projects/autocoder
ls custom/docs/
```

### "Patches don't apply"

Upstream may have changed significantly:
```bash
# Check what changed
git diff origin/main server/routers/__init__.py
git diff origin/main server/main.py

# Manual fix instructions in:
custom/patches/README.md
```

### "Status page not found"

Patches may not be applied:
```bash
custom/patches/apply-remote-access.sh
./remote-start.sh stop && ./remote-start.sh ui
```

---

## 📊 Statistics

- **Total Custom/Modified Files:** 18
- **Lines of Code (Scripts):** ~507
- **Lines of Code (Routes/Services):** ~2611 (status.py ~1250, auth_config.py 145)
- **Documentation Words:** ~9800 (added ~3200 for auth settings)
- **Patch Size:** 334 lines
- **Last Updated:** 2026-01-22

---

**Note:** This is a living document. Update it whenever you add, modify, or remove customizations.
