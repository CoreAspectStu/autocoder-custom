# AutoCoder Remote Quick Reference

## TL;DR

```bash
# 1. SSH to server (tunnels auto-forward ports)
# 2. Run (with resource guardrails):
autocoder-ui

# 3. Open http://localhost:8889
# 4. Close terminal - it keeps running
```

**Why `autocoder-ui`?** Wraps startup with systemd resource limits (2 cores, 8GB RAM, 250 processes) to prevent browser automation from consuming all system resources.

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
| Start UI (no limits) | `cd ~/projects/autocoder && ./remote-start.sh ui` |
| Start agent | `cd ~/projects/autocoder && ./remote-start.sh agent myproject` |
| Check status | `cd ~/projects/autocoder && ./remote-start.sh status` |
| View logs | `cd ~/projects/autocoder && ./remote-start.sh logs ui` |
| Stop all | `cd ~/projects/autocoder && ./remote-start.sh stop` |
| Reattach | `cd ~/projects/autocoder && ./remote-start.sh attach ui` |

## Detach from tmux

Press `Ctrl+B` then `D`

## Full docs

See [remote-setup.md](./remote-setup.md)
