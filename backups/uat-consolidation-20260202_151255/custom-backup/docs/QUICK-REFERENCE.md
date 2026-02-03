# AutoCoder UI Quick Reference

## Commands (Resource-Constrained Mode - Recommended)

All commands work from any directory.

### Start
```bash
autocoder-ui-start
```
Starts UI at http://127.0.0.1:8888 inside systemd scope with limits:
- CPU: 200% (2 cores max)
- Memory: 8GB max
- Tasks: 250 max

### Status
```bash
autocoder-ui-status
```
Shows:
- Running/stopped status
- Resource usage (CPU/RAM/tasks)
- Port status
- Escaped processes (if any)
- API health

### Monitor
```bash
autocoder-ui-monitor
```
Real-time dashboard showing resource usage and warnings. Press Ctrl+C to exit.

### Stop
```bash
autocoder-ui-stop
```
Cleanly stops UI and all child processes (agents, claude, playwright, etc.)

## Access

### From Local Machine (Windows)
Tunnel already configured in `~/.ssh/config`:
```
ssh -N core-control
```

Then open: http://localhost:8889

## What Gets Contained

When you start with `autocoder-ui-start`, everything runs inside a systemd scope:
- uvicorn server (UI)
- Agent orchestrator
- Coding agents (3 concurrent)
- Testing agents
- Claude CLI processes
- Playwright MCP servers (browser automation)
- Feature MCP servers (SQLite access)

**Result:** All processes killed cleanly when you stop. No stragglers.

## Known Leakage

Xvfb (virtual display) sometimes starts outside the scope. This is harmless - it's a lightweight X server for headless browser automation.

## Troubleshooting

### Port 8888 Already in Use
```bash
autocoder-ui-stop
ss -ltnp | grep ':8888'  # Should be empty
autocoder-ui-start
```

### Tasks Approaching Limit
Monitor shows "⚠️ Tasks near limit: 230/250"

**Solution:** Reduce concurrent agents in UI settings, or increase limit in `~/bin/autocoder-ui-start`:
```bash
-p TasksMax=500 \
```

### High Memory Usage
Monitor shows "⚠️ Memory high: 7GB/8GB"

**Solution:** Increase limit:
```bash
-p MemoryMax=16G \
```

### Check if Process is Contained
```bash
PID=<process_id>
CG=$(systemctl --user show autocoder-ui.scope -p ControlGroup --value)
grep -x "$PID" /sys/fs/cgroup"$CG"/cgroup.procs && echo "✅ Inside" || echo "❌ Escaped"
```

## Related Docs

- [resource-guardrails.md](./resource-guardrails.md) - Full technical details
- [remote-quickstart.md](./remote-quickstart.md) - SSH tunnel setup
- [UPDATE-GUIDE.md](./UPDATE-GUIDE.md) - Updating from upstream
