# AutoCoder Remote Quick Reference

## TL;DR

```bash
# 1. SSH to server (tunnels auto-forward ports)
# 2. Run (with resource guardrails):
autocoder-ui

# 3. Open http://localhost:8889
# 4. Close terminal - it keeps running
```

**Why `autocoder-ui`?** Starts the UI inside a systemd user scope so runaway sub-agents/Playwright/Claude can't melt the box.

## Port Convention

| Range | Purpose |
|-------|---------|
| **3000-3999** | Reserved for LOCAL only (never forwarded) |
| **4000-4099** | AutoCoder dev servers (via SSH tunnel) |

## Tunnel Cheat Sheet

| Your Browser | Tunnel | Server |
|--------------|--------|--------|
| `localhost:8889` | → | `:8888` AutoCoder UI |
| `localhost:4000` | → | `:4000` Project 1 |
| `localhost:4001` | → | `:4001` Project 2 |

See `docs/ports-4000-4099.txt` for full SSH config port list.

## Commands

| Do This | Command |
|---------|---------|
| Start UI (safe) | `autocoder-ui` |
| Start UI (no limits) | `autocoder ui` |
| Start agent | `autocoder agent myproject` |
| Check status | `autocoder status` |
| Health check | `autocoder-health` |
| View logs | `autocoder logs ui` |
| Stop all | `autocoder stop` |
| Reattach | `autocoder attach ui` |

**Note:** `autocoder` is a convenience wrapper for `./remote-start.sh` that works from any directory.

## Detach from tmux

Press `Ctrl+B` then `D`

## Full docs

See [remote-setup.md](./remote-setup.md)
