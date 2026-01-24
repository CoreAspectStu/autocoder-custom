# Custom Work - Must Be Preserved During Updates

**Last Updated:** 2026-01-25
**AutoCoder Custom Instance:** CoreAspectStu/autocoder-custom
**Upstream:** leonvanzyl/autocoder

This document lists ALL custom modifications to this AutoCoder instance that must be preserved when pulling updates from upstream.

---

## Critical Custom Work (DO NOT OVERWRITE)

### 1. Mission Control Integration (`custom/mission_control/`)

**Purpose:** Human-in-the-loop DevLayer integration for agents to request human input.

**Files:**
- `custom/mission_control/client.py` - Python client library for DevLayer API
- `custom/mission_control/mcp_server/mission_control_mcp.py` - MCP server with 9 tools (6 DevLayer + 3 quota management)
- `custom/mission_control/mcp_server/__init__.py`

**Features:**
- Agents can ask questions, report blockers, request decisions, request auth
- Press `L` in UI to toggle DevLayer mode
- Enable via `MISSION_CONTROL_ENABLED=true` in `.env`
- **NEW:** Quota management tools (added 2026-01-25):
  - `quota_get_usage` - Show current quota usage and remaining
  - `quota_set_limit` - Dynamically adjust quota limits for Anthropic vs GLM
  - `quota_get_history` - View quota usage history and daily summaries

**Preservation Strategy:**
- Entire `custom/mission_control/` directory is custom (not in upstream)
- Safe to merge upstream changes - no conflicts expected
- After merge: Verify Mission Control still works (test with agent)

---

### 2. Enhanced Status Dashboard (`server/routers/status.py`)

**Purpose:** Extended status router with DevLayer controls and port management.

**Modifications:**
- Added DevLayer toggle endpoint (`/api/status/devlayer`)
- Added port change endpoint (`/api/status/change-port`)
- Added XML spec viewer endpoint (`/api/status/xml-spec`)
- Extended from ~400 lines to 1597 lines
- Dev server controls: Start/Stop buttons for projects on ports 4000-4099
- Port management with conflict detection
- Health metrics and progress tracking
- Auto-refresh every 5 seconds

**Preservation Strategy:**
- ⚠️ **HIGH RISK** - Upstream may modify `server/routers/status.py`
- Before update: Check `git diff upstream/master server/routers/status.py`
- If upstream changed: Manual merge required
- After merge: Test all status endpoints and UI functionality

**Test Commands:**
```bash
# Test status endpoints
curl http://localhost:8888/api/status/projects
curl http://localhost:8888/api/status/ports
curl http://localhost:8888/api/status/xml-spec
curl -X POST http://localhost:8888/api/status/change-port -d '{"port": 4001}'
```

---

### 3. Quota Budget Tracker with GLM Support (`api/quota_budget.py`)

**Purpose:** Track API quota usage with 5-hour rolling window. GLM has much higher limits than Anthropic.

**Modifications:**
- Added GLM detection via `ANTHROPIC_BASE_URL` environment variable
- Increased quota limit from 400 (Anthropic) to 10,000 (GLM) when using Zhipu AI
- Lines 29-32: Auto-detect GLM and adjust limit accordingly

```python
# Allow override via environment variable
import os
if os.getenv("ANTHROPIC_BASE_URL", "").startswith("https://api.z.ai"):
    # GLM via Zhipu AI has much higher quotas
    DEFAULT_QUOTA_LIMIT = 10000  # Much higher limit for GLM
```

**Preservation Strategy:**
- ⚠️ **MEDIUM RISK** - Upstream may modify `api/quota_budget.py`
- Check for upstream changes before merging
- After merge: Verify GLM detection still works and quota limits are correct

**Test Commands:**
```bash
# Test with GLM configuration
export ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic
venv/bin/python -c "from api.quota_budget import get_quota_budget; print(get_quota_budget().quota_limit)"
# Should output: 10000

# Test with Anthropic (default)
unset ANTHROPIC_BASE_URL
venv/bin/python -c "from api.quota_budget import get_quota_budget; print(get_quota_budget().quota_limit)"
# Should output: 400
```

---

### 4. Manual Execution Prevention (`autonomous_agent_demo.py`)

**Purpose:** Prevent agents from running outside systemd resource limits.

**Modifications:**
- Added systemd cgroup detection at lines 47-73
- Checks `/proc/self/cgroup` for "autocoder-ui.service"
- Fallback: Checks `AUTOCODER_SYSTEMD_SERVICE` environment variable
- Bypass for development: Set `AUTOCODER_ALLOW_MANUAL=1`

```python
def _check_systemd_cgroup():
    """Check if we're running in the autocoder-ui.service cgroup."""
    # Allow bypass for testing (set AUTOCODER_ALLOW_MANUAL=1)
    if os.environ.get("AUTOCODER_ALLOW_MANUAL") == "1":
        return True

    # Check cgroup v2 (modern systems)
    try:
        cgroup_path = Path("/proc/self/cgroup")
        if cgroup_path.exists():
            cgroup_content = cgroup_path.read_text()
            if "autocoder-ui.service" in cgroup_content:
                return True
    except Exception:
        pass

    # Fallback: Check for environment variable set by systemd
    if os.environ.get("AUTOCODER_SYSTEMD_SERVICE") == "1":
        return True

    return False
```

**Preservation Strategy:**
- ⚠️ **HIGH RISK** - `autonomous_agent_demo.py` is frequently modified by upstream
- Before update: Check `git diff upstream/master autonomous_agent_demo.py`
- After merge: Verify cgroup check still prevents manual execution
- Test: Try running agent manually (should fail) and via systemd (should work)

**Test Commands:**
```bash
# Test manual execution (should fail)
python autonomous_agent_demo.py --project-dir qr
# Expected: ERROR: AutoCoder must run inside systemd service!

# Test systemd execution (should work)
systemctl --user restart autocoder-ui.service
```

---

### 5. Systemd Service Configuration (`~/.config/systemd/user/autocoder-ui.service`)

**Purpose:** Systemd user service with resource limits and GLM configuration.

**Modifications:**
- Added port cleanup: `ExecStartPre=/bin/bash -c 'fuser -k 8888/tcp 2>/dev/null || true'`
- Increased RAM from 8GB to 32GB: `MemoryMax=32G`
- Added GLM API environment variables:
  - `ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic`
  - `ANTHROPIC_AUTH_TOKEN=4eacd9c8435d4365a9ce58705d25b368.TXK2cwuODm5w4y0g`
  - `ANTHROPIC_DEFAULT_SONNET_MODEL=glm-4.7`
  - `ANTHROPIC_DEFAULT_OPUS_MODEL=glm-4.7`
  - `ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.5-air`
  - `API_TIMEOUT_MS=3000000`
- Added systemd service detection: `AUTOCODER_SYSTEMD_SERVICE=1`
- Fixed restart configuration: `Restart=on-failure`, `StartLimitBurst=5`, `StartLimitIntervalSec=300`

**Preservation Strategy:**
- ⚠️ **CRITICAL** - This file is NOT tracked in git (systemd config, not in repo)
- **MANUAL** - Must manually re-apply after any OS-level systemd changes
- Before update: Copy service file to backup location
- After update: Manually restore service file and reload: `systemctl --user daemon-reload`

**Backup Location:**
```bash
cp ~/.config/systemd/user/autocoder-ui.service ~/backup/autocoder-ui.service.backup
```

---

### 6. Remote Server Management (`remote-start.sh`)

**Purpose:** Tmux-based server control wrapper for AutoCoder UI.

**Features:**
- Starts UI in background tmux session
- Can run from any directory via `autocoder` alias (see `~/bin/autocoder`)
- Port management: 4000-4099 range for SSH tunnel compatibility
- Not recommended for production (use systemd service instead)

**Preservation Strategy:**
- Low risk (wrapper script, not core functionality)
- Check for upstream changes: `git diff upstream/master remote-start.sh`
- After merge: Verify script can start UI successfully

---

### 7. Convenience Wrapper (`~/bin/autocoder`)

**Purpose:** Shortcut to `remote-start.sh` that works from any directory.

**Content:**
```bash
#!/bin/bash
cd ~/projects/autocoder && exec ./remote-start.sh "$@"
```

**Preservation Strategy:**
- ⚠️ **NOT TRACKED IN REPO** - User's personal bin script
- **MANUAL** - Must manually preserve during system updates
- No conflicts with upstream (outside of repo)

---

## Custom Documentation (`custom/docs/`)

### UPDATE-GUIDE.md
**Purpose:** Step-by-step guide for safely pulling updates from upstream.

**Content:**
- Pre-update checklist (backup branch, stash changes)
- Update process with conflict resolution patterns
- Post-update testing checklist
- Rollback procedures if update fails

**Preservation Strategy:**
- Custom documentation (not in upstream)
- Safe to merge upstream changes
- Keep updated with any new custom work

### CUSTOM-WORK.md (this file)
**Purpose:** Comprehensive list of all custom modifications.

**Preservation Strategy:**
- Keep this file updated with ALL custom changes
- Review before each upstream update
- Update after adding new custom features

---

## Environment Configuration (`.env`)

**Purpose:** Application environment variables.

**Custom Settings:**
- GLM API configuration (commented out - using systemd environment instead)
- Mission Control enablement: `MISSION_CONTROL_ENABLED=true`

**Preservation Strategy:**
- ⚠️ **MEDIUM RISK** - Upstream may add new environment variables
- Before update: Stash changes: `git stash push .env`
- After merge: Restore custom settings and merge any new upstream variables

---

## Update Checklist

Before pulling updates from upstream:

1. ✅ **Create backup branch**
   ```bash
   git branch backup-$(date +%Y-%m-%d)
   ```

2. ✅ **Stash local changes**
   ```bash
   git stash push -u "Uncommitted changes before update"
   ```

3. ✅ **Review upstream changes**
   ```bash
   git fetch upstream master
   git diff HEAD upstream/master --stat
   ```

4. ✅ **Check for conflicts with custom work**
   ```bash
   # High-risk files
   git diff HEAD upstream/master -- server/routers/status.py
   git diff HEAD upstream/master -- api/quota_budget.py
   git diff HEAD upstream/master -- autonomous_agent_demo.py
   ```

5. ✅ **Backup systemd service file**
   ```bash
   cp ~/.config/systemd/user/autocoder-ui.service ~/backup/autocoder-ui.service.backup
   ```

6. ✅ **Pull from upstream**
   ```bash
   git pull upstream master --no-rebase
   ```

7. ✅ **Resolve conflicts** (if any)
   - Prioritize custom work over upstream changes
   - Test all functionality after resolving conflicts

8. ✅ **Post-update testing**
   ```bash
   # Restart service
   systemctl --user restart autocoder-ui.service

   # Test Mission Control
   curl -X POST http://localhost:8888/api/devlayer/ask -H "Content-Type: application/json" -d '{"message":"test"}'

   # Test quota tools
   venv/bin/python -c "from api.quota_budget import get_quota_budget; print(get_quota_budget().quota_limit)"

   # Test cgroup check
   python autonomous_agent_demo.py --project-dir qr
   # Should fail with: ERROR: AutoCoder must run inside systemd service!
   ```

9. ✅ **Commit merge and push to origin**
   ```bash
   git add .
   git commit -m "Merge upstream/master - preserved custom work"
   git push origin master
   ```

---

## Rollback Procedure

If update causes issues:

1. **Reset to backup branch**
   ```bash
   git reset --hard backup-YYYY-MM-DD
   ```

2. **Restore systemd service**
   ```bash
   cp ~/backup/autocoder-ui.service.backup ~/.config/systemd/user/autocoder-ui.service
   systemctl --user daemon-reload
   systemctl --user restart autocoder-ui.service
   ```

3. **Test functionality**
   - Verify UI loads at http://localhost:8888
   - Verify Mission Control works
   - Verify quota tracking works
   - Test agent execution

---

## Contact & Support

**Repository:** https://github.com/CoreAspectStu/autocoder-custom
**Upstream:** https://github.com/leonvanzyl/autocoder

For issues with custom work, check:
1. Mission Control logs: `/tmp/mission_control.log`
2. AutoCoder logs: `~/projects/autocoder/orchestrator_debug.log`
3. Systemd journal: `journalctl --user -u autocoder-ui.service -f`

---

*Last reviewed: 2026-01-25*
*Next review: Before next upstream update*
