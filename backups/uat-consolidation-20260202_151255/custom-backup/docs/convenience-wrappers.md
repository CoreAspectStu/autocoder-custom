# AutoCoder Convenience Wrapper Scripts

Located in `~/bin/`, these wrapper scripts make AutoCoder commands easier to use.

## `autocoder-ui` (Resource-Limited Start)

**Purpose:** Starts the UI inside a systemd user scope so runaway sub-agents/Playwright/Claude can't melt the box.

**Location:** `~/bin/autocoder-ui`

**Source:**
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

**Usage:**
```bash
autocoder-ui
```

**When to use:** Always, unless you're debugging resource issues or need more than 2 cores / 8GB RAM.

**See:** [resource-guardrails.md](./resource-guardrails.md) for details on resource limits.

---

## `autocoder` (Convenience Wrapper)

**Purpose:** Run `remote-start.sh` commands from any directory without needing to `cd` to the project.

**Location:** `~/bin/autocoder`

**Source:**
```bash
#!/usr/bin/env bash
set -euo pipefail
cd ~/projects/autocoder
exec ./remote-start.sh "$@"
```

**Usage:**
```bash
autocoder ui              # Start Web UI (no resource limits)
autocoder status          # Show running sessions
autocoder stop            # Stop all sessions
autocoder logs ui         # View UI logs
autocoder attach ui       # Attach to UI tmux session
autocoder agent myproject # Start agent for project
```

**When to use:** Daily operations when you want a quick command without resource limits.

**Equivalent to:**
```bash
cd ~/projects/autocoder
./remote-start.sh <command>
```

---

## `autocoder-health` (Diagnostics)

**Purpose:** Quick health check showing system load and AutoCoder-related processes.

**Location:** `~/bin/autocoder-health`

**Source:**
```bash
#!/usr/bin/env bash
echo "=== $(date -Is) ==="
uptime
echo
echo "-- claude --"
pgrep -af "^claude$" || echo "none"
echo
echo "-- playwright/xvfb/chrome --"
pgrep -af "Xvfb :99|playwright|chromium|chrome.*playwright" || echo "none"
echo
echo "-- top CPU --"
ps -eo pid,ppid,%cpu,etime,cmd --sort=-%cpu | head -20
EOF
```

**Usage:**
```bash
autocoder-health
```

**Output shows:**
- Current time and system uptime
- Running Claude processes
- Playwright/browser automation processes
- Top 20 CPU-consuming processes

**When to use:**
- Debugging performance issues
- Checking if AutoCoder is still running
- Investigating resource usage before/after running with guardrails

---

## Comparison

| Command | Resource Limits | Working Directory | Use Case |
|---------|----------------|-------------------|----------|
| `autocoder-ui` | ✅ Yes (2 cores, 8GB, 250 tasks) | Any | **Production use** - prevents system instability |
| `autocoder ui` | ❌ No | Any | Quick starts, debugging, large projects |
| `./remote-start.sh ui` | ❌ No | Must be in `~/projects/autocoder` | Direct script invocation |

---

## Installation

Both scripts are tracked in the home directory git repo and automatically backed up:

```bash
# Check they exist
ls -lh ~/bin/autocoder*

# Make executable (should already be)
chmod +x ~/bin/autocoder*

# Verify they're in PATH
which autocoder autocoder-ui
```

If `~/bin` is not in your PATH, add to `~/.bashrc`:
```bash
export PATH="$HOME/bin:$PATH"
```

---

## Future Improvements

- [ ] `autocoder-dev <project>` - Start agent with resource limits for a project
- [ ] `autocoder-test <project>` - Run tests for a project
- [x] `autocoder-health` - ✅ Health check and diagnostics (DONE)
- [ ] Auto-adjust resource limits based on project size
- [ ] `autocoder-restart` - Stop and start with one command
- [ ] `autocoder-health --watch` - Continuous monitoring mode

---

## See Also

- [remote-start.sh](../../remote-start.sh) - The underlying script these wrappers call
- [resource-guardrails.md](./resource-guardrails.md) - Why we need resource limits
- [remote-quickstart.md](./remote-quickstart.md) - Quick reference for all commands
