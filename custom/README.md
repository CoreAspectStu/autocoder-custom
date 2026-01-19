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

## 📁 Directory Structure

```
autocoder/
├── custom/                            # This directory - tracks all customizations
│   ├── README.md                      # This file - master index
│   ├── docs/                          # Remote server documentation
│   │   ├── remote-quickstart.md      # Quick reference card
│   │   ├── remote-setup.md           # User guide
│   │   ├── remote-server-setup.md    # Complete setup instructions
│   │   └── ports-4000-4099.txt       # SSH config port mappings
│   └── patches/                       # Patch system for upstream updates
│       ├── apply-remote-access.sh    # Auto-apply script
│       ├── remote-access.patch       # Git patch file
│       └── README.md                  # Patch documentation
│
├── remote-start.sh                    # [CUSTOM] Main launcher script
├── server/routers/
│   └── status.py                      # [CUSTOM] Status page router
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
| `remote-start.sh` | `/` | tmux/Xvfb session manager | 317 |
| `apply-remote-access.sh` | `custom/patches/` | Auto-applies patches after git pull | 77 |

### Server Routes

| File | Location | Purpose | Lines |
|------|----------|---------|-------|
| `status.py` | `server/routers/` | Status page with port detection | 287 |

### Documentation

| File | Location | Purpose | Words |
|------|----------|---------|-------|
| `custom/README.md` | `custom/` | This file - master index | - |
| `remote-quickstart.md` | `custom/docs/` | Quick reference cheat sheet | ~300 |
| `remote-setup.md` | `custom/docs/` | Complete user guide | ~2000 |
| `remote-server-setup.md` | `custom/docs/` | Full setup instructions | ~3500 |
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

### 2. Status Page
**Problem Solved:** See all projects and their running dev servers at a glance

**Access:** `http://localhost:8888/status` (after starting UI)

**Features:**
- Lists all registered projects
- Detects which ports are listening
- Shows dev server URLs
- Real-time port detection

### 3. Patch System
**Problem Solved:** Survive upstream updates without losing custom code

**How It Works:**
- After `git pull`, run `custom/patches/apply-remote-access.sh`
- Auto-patches core files to integrate status router
- Documented in `custom/patches/README.md`

### 4. Comprehensive Documentation
**Problem Solved:** Multiple learning paths for different needs

**Levels:**
- Quick reference card (`custom/docs/remote-quickstart.md`)
- User guide (`custom/docs/remote-setup.md`)
- Full setup guide (`custom/docs/remote-server-setup.md`)

### 5. Claude Code Integration
**Problem Solved:** Quick access from anywhere

**Commands:**
- `/autocoder` - Start the UI remotely
- `/autocoder-help` - Show complete command reference

---

## 📝 Changelog

### 2026-01-20
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

- **Total Custom Files:** 12
- **Lines of Code (Scripts):** ~600
- **Lines of Code (Router):** 287
- **Documentation Words:** ~6000
- **Last Updated:** 2026-01-20

---

**Note:** This is a living document. Update it whenever you add, modify, or remove customizations.
