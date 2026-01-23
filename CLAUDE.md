# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ IMPORTANT: Custom Modified Instance

**This is NOT vanilla AutoCoder.** This instance has significant custom modifications:

- **Enhanced Status Dashboard** - `server/routers/status.py` (1132 lines with XML formatting, modal UI, health metrics)
- **Remote Server Management** - `remote-start.sh` (tmux-based server control)
- **Port Assignment System** - 4000-4099 range for SSH tunnel compatibility
- **Custom Documentation** - `custom/` directory with guides and patches

### 🔄 Updating from Upstream

**⚠️ TRIGGER PHRASES - WHEN YOU SEE THESE, FOLLOW THE UPDATE GUIDE:**
- "update autocoder"
- "pull from upstream"
- "get latest changes"
- "merge upstream"
- "update from the base repo"

**MANDATORY FIRST STEP:** Read this file BEFORE doing anything:
```
/home/stu/projects/autocoder/custom/docs/UPDATE-GUIDE.md
```

**DO NOT:**
- ❌ Run `git pull` without reading the guide first
- ❌ Make any assumptions about what's safe to overwrite
- ❌ Skip the backup branch creation
- ❌ Forget to test after merging

**DO:**
- ✅ Read UPDATE-GUIDE.md completely
- ✅ Create backup branch with date: `git branch backup-$(date +%Y-%m-%d)`
- ✅ Follow the documented conflict resolution patterns
- ✅ Test thoroughly after merge
- ✅ Install any new dependencies from requirements.txt

**Last successful update:** 2026-01-22 (merged 28 commits successfully)

---

## 🔄 Git Workflow & Backup

**IMPORTANT:** This is a CUSTOM FORK with custom work that must be preserved.

### Remote Setup

- `origin` → https://github.com/CoreAspectStu/autocoder-custom (YOUR fork - push custom changes here)
- `upstream` → https://github.com/leonvanzyl/autocoder (upstream - pull updates from here)

### Daily Workflow: Saving Your Changes

**After making ANY changes to the codebase:**

```bash
cd ~/projects/autocoder

# 1. Check what changed
git status

# 2. Stage your changes
git add <files>

# 3. Commit with descriptive message
git commit -m "Description of changes"

# 4. Push to YOUR fork (backup to GitHub)
git push origin master
```

**IMPORTANT:** Push to `origin` (your fork) regularly to back up custom work!

### Getting Upstream Updates

**When you need the latest features from upstream:**

```bash
# 1. READ THE UPDATE GUIDE FIRST!
cat custom/docs/UPDATE-GUIDE.md

# 2. Create backup branch
git branch backup-$(date +%Y-%m-%d)

# 3. Pull from upstream (not origin!)
git pull upstream master --no-rebase

# 4. Resolve any conflicts (see UPDATE-GUIDE.md)

# 5. Push merged changes to your fork
git push origin master
```

**Never run `git pull origin master`** - origin is YOUR fork, not upstream!

---

## Project Overview

This is an autonomous coding agent system with a React-based UI. It uses the Claude Agent SDK to build complete applications over multiple sessions using a two-agent pattern:

1. **Initializer Agent** - First session reads an app spec and creates features in a SQLite database
2. **Coding Agent** - Subsequent sessions implement features one by one, marking them as passing

## Commands

### Quick Start (Recommended)

```bash
# Remote server (with resource guardrails) - RECOMMENDED
autocoder-ui      # Limits: 2 cores, 8GB RAM, 250 processes

# Remote server (convenience wrapper - no guardrails)
autocoder ui      # Works from any directory
autocoder status  # Check running sessions
autocoder stop    # Stop all sessions
autocoder logs ui # View logs

# Local development
./start.sh        # CLI menu (Linux/macOS)
./start_ui.sh     # Web UI (Linux/macOS)
start.bat         # CLI menu (Windows)
start_ui.bat      # Web UI (Windows)

# Direct (requires cd to project directory)
./remote-start.sh ui
```

**Why use `autocoder-ui`?** Starts the UI inside a systemd user scope so runaway sub-agents/Playwright/Claude can't melt the box (limits: 2 cores, 8GB RAM, 250 processes).

**Convenience wrapper:** `autocoder` is a shortcut to `./remote-start.sh` that works from any directory (see `~/bin/autocoder`).

### Python Backend (Manual)

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run the main CLI launcher
python start.py

# Run agent directly for a project (use absolute path or registered name)
python autonomous_agent_demo.py --project-dir C:/Projects/my-app
python autonomous_agent_demo.py --project-dir my-app  # if registered

# YOLO mode: rapid prototyping without browser testing
python autonomous_agent_demo.py --project-dir my-app --yolo

# Parallel mode: run multiple agents concurrently (1-5 agents)
python autonomous_agent_demo.py --project-dir my-app --parallel --max-concurrency 3
```

### YOLO Mode (Rapid Prototyping)

YOLO mode skips all testing for faster feature iteration:

```bash
# CLI
python autonomous_agent_demo.py --project-dir my-app --yolo

# UI: Toggle the lightning bolt button before starting the agent
```

**What's different in YOLO mode:**
- No regression testing (skips `feature_get_for_regression`)
- No Playwright MCP server (browser automation disabled)
- Features marked passing after lint/type-check succeeds
- Faster iteration for prototyping

**What's the same:**
- Lint and type-check still run to verify code compiles
- Feature MCP server for tracking progress
- All other development tools available

**When to use:** Early prototyping when you want to quickly scaffold features without verification overhead. Switch back to standard mode for production-quality development.

### React UI (in ui/ directory)

```bash
cd ui
npm install
npm run dev      # Development server (hot reload)
npm run build    # Production build (required for start_ui.bat)
npm run lint     # Run ESLint
```

**Note:** The `start_ui.bat` script serves the pre-built UI from `ui/dist/`. After making UI changes, run `npm run build` in the `ui/` directory.

## Architecture

### Core Python Modules

- `start.py` - CLI launcher with project creation/selection menu
- `autonomous_agent_demo.py` - Entry point for running the agent
- `agent.py` - Agent session loop using Claude Agent SDK
- `client.py` - ClaudeSDKClient configuration with security hooks and MCP servers
- `security.py` - Bash command allowlist validation (ALLOWED_COMMANDS whitelist)
- `prompts.py` - Prompt template loading with project-specific fallback
- `progress.py` - Progress tracking, database queries, webhook notifications
- `registry.py` - Project registry for mapping names to paths (cross-platform)
- `parallel_orchestrator.py` - Concurrent agent execution with dependency-aware scheduling
- `api/dependency_resolver.py` - Cycle detection (Kahn's algorithm + DFS) and dependency validation

### Project Registry

Projects can be stored in any directory. The registry maps project names to paths using SQLite:
- **All platforms**: `~/.autocoder/registry.db`

The registry uses:
- SQLite database with SQLAlchemy ORM
- POSIX path format (forward slashes) for cross-platform compatibility
- SQLite's built-in transaction handling for concurrency safety

### Server API (server/)

The FastAPI server provides REST endpoints for the UI:

- `server/routers/projects.py` - Project CRUD with registry integration
- `server/routers/features.py` - Feature management
- `server/routers/agent.py` - Agent control (start/stop/pause/resume)
- `server/routers/filesystem.py` - Filesystem browser API with security controls
- `server/routers/spec_creation.py` - WebSocket for interactive spec creation

### Feature Management

Features are stored in SQLite (`features.db`) via SQLAlchemy. The agent interacts with features through an MCP server:

- `mcp_server/feature_mcp.py` - MCP server exposing feature management tools
- `api/database.py` - SQLAlchemy models (Feature table with priority, category, name, description, steps, passes, dependencies)

MCP tools available to the agent:
- `feature_get_stats` - Progress statistics
- `feature_get_next` - Get highest-priority pending feature (respects dependencies)
- `feature_claim_next` - Atomically claim next available feature (for parallel mode)
- `feature_get_for_regression` - Random passing features for regression testing
- `feature_mark_passing` - Mark feature complete
- `feature_skip` - Move feature to end of queue
- `feature_create_bulk` - Initialize all features (used by initializer)
- `feature_add_dependency` - Add dependency between features (with cycle detection)
- `feature_remove_dependency` - Remove a dependency

### React UI (ui/)

- Tech stack: React 18, TypeScript, TanStack Query, Tailwind CSS v4, Radix UI, dagre (graph layout)
- `src/App.tsx` - Main app with project selection, kanban board, agent controls
- `src/hooks/useWebSocket.ts` - Real-time updates via WebSocket (progress, agent status, logs, agent updates)
- `src/hooks/useProjects.ts` - React Query hooks for API calls
- `src/lib/api.ts` - REST API client
- `src/lib/types.ts` - TypeScript type definitions

Key components:
- `AgentMissionControl.tsx` - Dashboard showing active agents with mascots (Spark, Fizz, Octo, Hoot, Buzz)
- `DependencyGraph.tsx` - Interactive node graph visualization with dagre layout
- `CelebrationOverlay.tsx` - Confetti animation on feature completion
- `FolderBrowser.tsx` - Server-side filesystem browser for project folder selection

Keyboard shortcuts (press `?` for help):
- `D` - Toggle debug panel
- `G` - Toggle Kanban/Graph view
- `N` - Add new feature
- `A` - Toggle AI assistant
- `,` - Open settings

### Project Structure for Generated Apps

Projects can be stored in any directory (registered in `~/.autocoder/registry.db`). Each project contains:
- `prompts/app_spec.txt` - Application specification (XML format)
- `prompts/initializer_prompt.md` - First session prompt
- `prompts/coding_prompt.md` - Continuation session prompt
- `features.db` - SQLite database with feature test cases
- `.agent.lock` - Lock file to prevent multiple agent instances

### Security Model

Defense-in-depth approach configured in `client.py`:
1. OS-level sandbox for bash commands
2. Filesystem restricted to project directory only
3. Bash commands validated against `ALLOWED_COMMANDS` in `security.py`

## Claude Code Integration

- `.claude/commands/create-spec.md` - `/create-spec` slash command for interactive spec creation
- `.claude/skills/frontend-design/SKILL.md` - Skill for distinctive UI design
- `.claude/templates/` - Prompt templates copied to new projects

## Key Patterns

### Prompt Loading Fallback Chain

1. Project-specific: `{project_dir}/prompts/{name}.md`
2. Base template: `.claude/templates/{name}.template.md`

### Agent Session Flow

1. Check if `features.db` has features (determines initializer vs coding agent)
2. Create ClaudeSDKClient with security settings
3. Send prompt and stream response
4. Auto-continue with 3-second delay between sessions

### Real-time UI Updates

The UI receives updates via WebSocket (`/ws/projects/{project_name}`):
- `progress` - Test pass counts (passing, in_progress, total)
- `agent_status` - Running/paused/stopped/crashed
- `log` - Agent output lines with optional featureId/agentIndex for attribution
- `feature_update` - Feature status changes
- `agent_update` - Multi-agent state updates (thinking/working/testing/success/error) with mascot names

### Parallel Mode

When running with `--parallel`, the orchestrator:
1. Spawns multiple Claude agents as subprocesses (up to `--max-concurrency`)
2. Each agent claims features atomically via `feature_claim_next`
3. Features blocked by unmet dependencies are skipped
4. Browser contexts are isolated per agent using `--isolated` flag
5. AgentTracker parses output and emits `agent_update` messages for UI

### Design System

The UI uses a **neobrutalism** design with Tailwind CSS v4:
- CSS variables defined in `ui/src/styles/globals.css` via `@theme` directive
- Custom animations: `animate-slide-in`, `animate-pulse-neo`, `animate-shimmer`
- Color tokens: `--color-neo-pending` (yellow), `--color-neo-progress` (cyan), `--color-neo-done` (green)
