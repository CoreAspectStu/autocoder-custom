# UAT Mode Trigger Fixes

**Date:** 2026-02-03
**Issue:** UAT Mode Play button not working - "nothing happens"
**Root Cause:** Two bugs in `/server/routers/uat_gateway.py`

## Bug #1: Execution Mode Logic Error (Line 394)

### The Problem
```python
use_direct_execution = request.force or True  # Default to direct for now
```

**This ALWAYS evaluates to `True`** because of Python's `or` operator:
- `False or True` → `True`
- `True or True` → `True`
- `None or True` → `True`

**Impact:** Always ran "direct mode" (Playwright tests from `e2e/` directory) instead of "orchestrator mode" (UAT tests from `~/.autocoder/uat_tests.db`).

### The Fix
```python
# Choose execution mode:
# - If UAT Orchestrator is available, use it by default (runs tests from uat_tests.db)
# - Otherwise fall back to direct Playwright execution
# - request.force=True forces direct mode, request.force=False forces orchestrator mode
if request.force is not None:
    # Explicit force setting
    use_direct_execution = request.force
else:
    # Default: use orchestrator if available, otherwise direct mode
    use_direct_execution = not UAT_ORCHESTRATOR_AVAILABLE
```

**Now correctly defaults to orchestrator mode when available.**

---

## Bug #2: Wrong Orchestrator Import (Line 47)

### The Problem
```python
try:
    from custom.uat_plugin.orchestrator import Orchestrator
    UAT_ORCHESTRATOR_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  UAT Orchestrator not available (orchestrated mode disabled): {e}")
    UAT_ORCHESTRATOR_AVAILABLE = False
```

**Issue:** Importing from `custom.uat_plugin.orchestrator` which is **broken** (missing `dev_task_creator.py`).

**Impact:** `UAT_ORCHESTRATOR_AVAILABLE = False`, so the code falls back to direct mode even after fixing Bug #1.

### The Fix
```python
try:
    from custom.uat_gateway.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
    UAT_ORCHESTRATOR_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  UAT Orchestrator not available (orchestrated mode disabled): {e}")
    UAT_ORCHESTRATOR_AVAILABLE = False
```

**Now imports from the working `custom.uat_gateway.orchestrator.orchestrator` module.**

---

## How UAT Mode Trigger Works

### Flow Diagram
```
User clicks "Play" button in UAT Mode
        ↓
Frontend: triggerUATExecution(projectName)
        ↓
API: POST /api/uat/trigger
        ↓
Server: trigger_uat_cycle() in uat_gateway.py
        ↓
┌─────────────────────────────────────────────┐
│ Check execution mode:                        │
│   - If request.force is set: use that       │
│   - If UAT_ORCHESTRATOR_AVAILABLE: use it   │
│   - Otherwise: use direct mode              │
└─────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────┐
│ ORCHESTRATOR MODE (runs tests from DB)      │
│   1. Parse spec.yaml                         │
│   2. Extract journeys                        │
│   3. Read pending tests from uat_tests.db    │
│   4. Execute tests via Playwright            │
│   5. Update test status in DB                │
│   6. Return results to UI                    │
└─────────────────────────────────────────────┘
        ↓
        OR
        ↓
┌─────────────────────────────────────────────┐
│ DIRECT MODE (runs e2e/ tests)               │
│   1. Check for e2e/ directory                │
│   2. Run Playwright tests directly           │
│   3. Parse results                           │
│   4. Return to UI                            │
└─────────────────────────────────────────────┘
```

### Database Locations

| Purpose | Location | Notes |
|---------|----------|-------|
| UAT Tests | `~/.autocoder/uat_tests.db` | Global database with 300+ pending tests |
| Features | `{project}/features.db` | Per-project features |
| Registry | `~/.autocoder/registry.db` | Project name → path mapping |

---

## Two Orchestrators - Why Two Exist?

### Location #1: `custom/uat_plugin/orchestrator.py`
**Status:** BROKEN
- Missing `dev_task_creator.py` dependency
- Do NOT use
- Legacy/abandoned implementation

### Location #2: `custom/uat_gateway/orchestrator/orchestrator.py`
**Status:** WORKING
- Complete implementation with all dependencies
- Handles spec parsing, journey extraction, test generation
- This is what the UAT Gateway uses

**Always import from:** `custom.uat_gateway.orchestrator.orchestrator`

---

## Testing the Fix

### 1. Verify Orchestrator is Importable
```bash
python3 -c "
from custom.uat_gateway.orchestrator.orchestrator import Orchestrator, OrchestratorConfig
print('✓ Orchestrator available')
"
```

### 2. Check Pending Tests
```bash
sqlite3 ~/.autocoder/uat_tests.db "SELECT status, COUNT(*) FROM uat_test_features GROUP BY status"
```

Expected output:
```
pending|300
passed|1727
in_progress|14
failed|4
parked|5
```

### 3. Test the Trigger Endpoint
```bash
curl -X POST http://localhost:8888/api/uat/trigger \
  -H "Content-Type: application/json" \
  -d '{"project_name": "callAspect"}'
```

Expected response:
```json
{
  "success": true,
  "cycle_id": "uat_callAspect_20260203_191700",
  "message": "UAT testing cycle started",
  "status_url": "/api/uat/status/uat_callAspect_20260203_191700"
}
```

### 4. Monitor Progress
```bash
# Check status
curl http://localhost:8888/api/uat/status/uat_callAspect_20260203_191700

# Check logs
journalctl --user -u autocoder-ui -f
```

---

## Common Issues & Solutions

### Issue: "UAT Orchestrator not available"
**Cause:** Import failing
**Fix:** Check that `custom/uat_gateway/` exists and has all files:
```bash
ls -la custom/uat_gateway/orchestrator/
```

### Issue: Tests not running
**Cause:** Execution mode stuck on "direct"
**Fix:** Verify the fix on line 394 was applied:
```bash
grep "use_direct_execution" server/routers/uat_gateway.py
```

Should NOT contain `= request.force or True`

### Issue: Pending tests showing but not executing
**Cause:** Tests in project DB, not global DB
**Fix:** UAT tests should be in `~/.autocoder/uat_tests.db`, not project directory

---

## Files Modified

1. **`/server/routers/uat_gateway.py`**
   - Line 47: Fixed orchestrator import
   - Line 394: Fixed execution mode logic

## Related Documentation

- `/docs/projects/autocoder/uat-gateway-integration.md` - UAT Gateway overview
- `/custom/uat_gateway/README.md` - UAT Gateway module docs
- `/docs/projects/autocoder/websocket-patterns.md` - WebSocket error handling

---

## Future Maintenance

**When modifying the trigger endpoint:**
1. Test the `use_direct_execution` logic with all combinations
2. Verify orchestrator import still works
3. Check that pending tests from `~/.autocoder/uat_tests.db` are executed
4. Never change back to `custom.uat_plugin.orchestrator` import

**When adding new orchestrator features:**
1. Update `custom/uat_gateway/orchestrator/orchestrator.py`
2. Keep the working import path
3. Do NOT create imports from `uat_plugin` unless specifically fixing that module
