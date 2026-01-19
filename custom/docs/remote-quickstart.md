# AutoCoder Remote Quick Reference

## TL;DR

```bash
# 1. SSH to server (tunnels auto-forward ports)
# 2. Run:
cd ~/projects/autocoder
./remote-start.sh ui

# 3. Open http://localhost:8889
# 4. Close terminal - it keeps running
```

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
| Start UI | `./remote-start.sh ui` |
| Start agent | `./remote-start.sh agent myproject` |
| Check status | `./remote-start.sh status` |
| View logs | `./remote-start.sh logs ui` |
| Stop all | `./remote-start.sh stop` |
| Reattach | `./remote-start.sh attach ui` |

## Detach from tmux

Press `Ctrl+B` then `D`

## Full docs

See [remote-setup.md](./remote-setup.md)
