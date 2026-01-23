# Resource Guardrails for AutoCoder

## Problem

AutoCoder uses browser automation (Playwright/Puppeteer) which can spawn multiple browser processes. Without limits, these can:
- Consume all available CPU (causing system slowdown)
- Use excessive RAM (triggering OOM killer)
- Fork bomb (thousands of processes crashing the system)

## Solution: systemd Resource Limits

The `autocoder-ui` wrapper script applies systemd resource limits before starting the UI.

### Wrapper Script

Located at: `~/bin/autocoder-ui`

```bash
#!/usr/bin/env bash
set -euo pipefail

# Safety rails: adjust if you want
CPU="200%"     # ~2 cores
MEM="8G"
TASKS="250"

exec systemd-run --user --scope \
  -p CPUQuota="$CPU" \
  -p MemoryMax="$MEM" \
  -p TasksMax="$TASKS" \
  bash -lc 'cd ~/projects/autocoder && ./remote-start.sh ui'
```

### Limits Explained

| Limit | Value | Meaning |
|-------|-------|---------|
| `CPUQuota` | 200% | Maximum 2 CPU cores worth of time |
| `MemoryMax` | 8G | Hard limit of 8GB RAM (kills process if exceeded) |
| `TasksMax` | 250 | Maximum 250 processes/threads in scope |

### Usage

```bash
# Start with guardrails (recommended)
autocoder-ui

# Check status
cd ~/projects/autocoder
./remote-start.sh status

# Stop
./remote-start.sh stop

# View logs
./remote-start.sh logs ui
```

### When to Bypass Guardrails

Only bypass if you're actively debugging resource issues or need more resources for large projects:

```bash
cd ~/projects/autocoder
./remote-start.sh ui
```

### Adjusting Limits

Edit the wrapper script if you need different limits:

```bash
nano ~/bin/autocoder-ui

# Increase to 4 cores and 16GB:
CPU="400%"     # ~4 cores
MEM="16G"
TASKS="500"
```

### Monitoring Resource Usage

```bash
# Check current resource usage
systemctl --user status run-*.scope

# View all user scopes
systemctl --user list-units --type=scope
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
