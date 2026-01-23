# Resource Guardrails for AutoCoder

## Problem

AutoCoder spawns multiple processes including:
- Claude CLI instances (MCP servers for context7, perplexity)
- Browser automation (Playwright/Puppeteer with Chromium)
- Virtual display (Xvfb)
- Agent SDK subprocesses

Without limits, runaway processes can:
- Consume all available CPU (58%+ per claude process observed)
- Use excessive RAM (triggering OOM killer)
- Fork bomb (thousands of processes crashing the system)
- Escape tmux containment and persist after stop commands

## Solution: systemd User Scope with Resource Limits

The AutoCoder UI now runs inside a **systemd user scope** that acts as a resource cage. All child processes (claude, chrome, playwright) stay contained and are killed cleanly when the scope stops.

### Start Script

Located at: `~/bin/autocoder-ui-start`

```bash
#!/usr/bin/env bash
set -euo pipefail
cd ~/projects/autocoder

systemctl --user stop autocoder-ui.scope 2>/dev/null || true
systemctl --user reset-failed 2>/dev/null || true

exec systemd-run --user --unit=autocoder-ui --scope \
  -p CPUQuota=200% \
  -p MemoryMax=8G \
  -p TasksMax=250 \
  bash -lc 'cd ~/projects/autocoder && exec ./venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8888'
```

**Key changes from previous approach:**
- Runs uvicorn directly using `./venv/bin/python -m uvicorn` (not via remote-start.sh)
- Uses systemd scope for containment (not tmux)
- All child processes inherit the scope and stay caged

### Limits Explained

| Limit | Value | Meaning |
|-------|-------|---------|
| `CPUQuota` | 200% | Maximum 2 CPU cores worth of time |
| `MemoryMax` | 8G | Hard limit of 8GB RAM (kills process if exceeded) |
| `TasksMax` | 250 | Maximum 250 processes/threads in scope |

### Usage

```bash
# Start UI with guardrails (recommended)
autocoder-ui-start

# Check status
autocoder-ui-status

# Stop cleanly
autocoder-ui-stop

# Monitor resource usage in real-time
watch -n 2 'systemctl --user status autocoder-ui.scope --no-pager | grep -E "Tasks:|Memory:|CPU:"'
```

**What gets contained:**
- uvicorn server (UI)
- Agent orchestrator
- Multiple coding/testing agents
- Claude CLI processes (one per agent)
- Playwright MCP servers (browser automation)
- Feature MCP servers (database)
- All their child processes

### Adjusting Limits

Edit the start script if you need different limits:

```bash
nano ~/bin/autocoder-ui-start

# Increase to 4 cores and 16GB:
-p CPUQuota=400% \
-p MemoryMax=16G \
-p TasksMax=500 \
```

### Monitoring Resource Usage

```bash
# Real-time monitoring (recommended)
autocoder-ui-monitor

# Check current status
systemctl --user status autocoder-ui.scope

# Check if a process is inside the scope
PID=<process_id>
CG=$(systemctl --user show autocoder-ui.scope -p ControlGroup --value)
grep -x "$PID" /sys/fs/cgroup"$CG"/cgroup.procs && echo "✅ Contained" || echo "❌ Escaped"
```

### How It Works

1. `systemd-run --user --scope` creates a transient systemd scope
2. Resource limits are applied via cgroup v2
3. If limits are exceeded:
   - CPU: Process is throttled (slowed down)
   - Memory: Process is killed (OOM)
   - Tasks: Fork/clone calls fail

### Related Issues

- **Issue:** Browser processes consuming all CPU
  - **Solution:** CPUQuota limits usage

- **Issue:** Memory leaks from long-running agents
  - **Solution:** MemoryMax kills process before system OOM

- **Issue:** Fork bombs from buggy code
  - **Solution:** TasksMax prevents excessive process creation

### Future Improvements

- [ ] Add resource monitoring dashboard to UI
- [ ] Auto-adjust limits based on project size
- [ ] Alert when approaching limits
- [ ] Graceful degradation instead of hard kill on OOM

## See Also

- [remote-start.sh](../../remote-start.sh) - tmux-based session management
- [remote-quickstart.md](./remote-quickstart.md) - Quick reference
- systemd.resource-control(5) - Full documentation of resource limits
