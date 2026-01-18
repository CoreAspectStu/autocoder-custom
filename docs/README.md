# AutoCoder Documentation

## Remote Server Setup

Guides for running AutoCoder on a headless server via SSH.

| Document | Description |
|----------|-------------|
| [remote-server-setup.md](./remote-server-setup.md) | **Complete setup guide** - All changes needed to replicate on a new server |
| [remote-setup.md](./remote-setup.md) | User guide - How to use remote access day-to-day |
| [remote-quickstart.md](./remote-quickstart.md) | Quick reference card |

## Quick Start

1. **New server setup?** → Read [remote-server-setup.md](./remote-server-setup.md)
2. **Already set up?** → Read [remote-quickstart.md](./remote-quickstart.md)

## Files Changed from Vanilla AutoCoder

| File | Change |
|------|--------|
| `remote-start.sh` | New - tmux/Xvfb launcher |
| `server/routers/status.py` | New - Status page |
| `server/routers/__init__.py` | Added status_router export |
| `server/main.py` | Added status_router include |
