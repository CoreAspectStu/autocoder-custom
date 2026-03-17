# Port Allocation Policy

**IMPORTANT:** All AutoCoder/AutoForge projects MUST follow this port allocation strategy.

## Port Ranges

| Range | Purpose | Enforcement |
|-------|---------|-------------|
| **3000-3999** | Local/manual services | Reserved, do not use for AutoCoder projects |
| **4000-4999** | AutoCoder/AutoForge applications | **ENFORCED** - All dev servers auto-assigned from this range |
| **8000-8999** | System services | Coolify (8000), AutoCoder UI (8888), etc. |

## Why This Matters

1. **SSH Tunnel Compatibility** - Remote dev servers accessed via SSH tunnels need consistent port allocation
2. **Conflict Prevention** - Automatic assignment prevents port collisions between projects
3. **Monitoring** - Port ranges make it easy to identify what's running where
4. **Security** - Firewall rules can target specific ranges

## How It Works

AutoCoder **automatically** assigns ports from the 4000-4999 range when:
- A new project is created
- A project's dev server config is accessed
- The UI displays project controls

**Enforcement locations:**
1. `server/services/project_config.py` - Port assignment logic
2. `server/services/dev_server_manager.py` - Dev server controls validate commands
3. UI - Port selection dropdown limited to valid range

## Configuration Files

### Project Config (`.autoforge/config.json` or `.autocoder/config.json`)

```json
{
  "assigned_port": 4001,
  "dev_command": "PORT=4001 npm run dev"
}
```

### Server Config (`.autoforge/server.json` or `.autocoder/server.json`)

```json
{
  "dev_server": {
    "command": "PORT=4001 bun dev",
    "port": 4001,
    "url": "http://localhost:4001",
    "health_check": "/",
    "auto_start": false
  }
}
```

## Validation

Run the port validation script to check/fix all projects:

```bash
cd ~/projects/autocoder

# Check all projects
./bin/validate-port-assignments

# Fix out-of-range ports automatically
./bin/validate-port-assignments --fix
```

## Manual Port Assignment

If you need to manually set a specific port:

```bash
# Via AutoCoder UI (recommended)
# 1. Open project settings
# 2. Change port via dropdown (4000-4999 only)
# 3. Save

# Via Python API
from pathlib import Path
from server.services.project_config import set_assigned_port

project_dir = Path("/path/to/project")
set_assigned_port(project_dir, 4042)  # Must be 4000-4999
```

## SSH Tunnel Setup

For remote access to AutoCoder projects, forward the port range in your SSH config:

```ssh
Host core-control
  HostName 138.201.197.54
  User stu
  LocalForward 8889 127.0.0.1:8888  # AutoCoder UI
  # Forward AutoCoder project ports (add as needed):
  LocalForward 4001 127.0.0.1:4001
  LocalForward 4002 127.0.0.1:4002
  # ... etc
```

See `custom/docs/ports-4000-4999.txt` for a ready-to-paste SSH config template.

## What's Changed (2026-02-10)

**Previous:** Port range was 4000-4099 (100 ports)
**Current:** Port range is 4000-4999 (1000 ports)

**Migration:** Existing projects with ports 4000-4099 remain valid. The expanded range provides room for up to 1000 concurrent AutoCoder projects.

## Related Documentation

- System-wide policy: `~/CLAUDE.md` (Port Allocation Policy section)
- SSH tunnel config: `custom/docs/ports-4000-4999.txt`
- Custom work overview: `custom/README.md`
- Port assignment code: `server/services/project_config.py`
- Dev server manager: `server/services/dev_server_manager.py`
