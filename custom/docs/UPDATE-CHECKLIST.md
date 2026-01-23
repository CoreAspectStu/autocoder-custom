# AutoCoder Update Checklist

Quick reference for updating from upstream. See `UPDATE-GUIDE.md` for full details.

## Pre-Flight

```bash
cd ~/projects/autocoder
git status                              # ✅ Clean?
git branch backup-$(date +%Y-%m-%d)    # ✅ Backup created?
git fetch origin master                 # ✅ See what's coming
git log --oneline HEAD..origin/master  # ✅ Review commits
```

## Execute

```bash
git pull origin master --no-rebase     # ⚠️ Expect conflicts
```

## Resolve Conflicts

**Common patterns:**

| File | Conflict Type | Resolution |
|------|---------------|------------|
| `agent.py` | Import statements | **MERGE BOTH** (keep unique imports) |
| `settings.py` | Removed custom auth | **ACCEPT THEIRS** (auth works without it) |
| `schemas.py` | Field changes | **ACCEPT THEIRS** (follow upstream schema) |

**After resolving:**
```bash
git add <files>
git commit -m "Merge upstream: <features>"
```

## Dependencies

```bash
source venv/bin/activate
pip install -r requirements.txt   # Install any new packages
```

## Test

```bash
./remote-start.sh stop
./remote-start.sh ui
sleep 5

# Quick tests:
curl http://localhost:8888/api/settings | jq
curl -X POST "http://localhost:8888/api/projects/QR/agent/start" -d '{"yolo_mode":true}' | jq
curl http://localhost:8888/status | grep "Dashboard"
```

## Verify Survival

```bash
ls -la remote-start.sh              # ✅ Exists?
ls -la server/routers/status.py     # ✅ Exists? (~1100 lines)
ls -la custom/                      # ✅ Directory intact?
```

## Rollback (if needed)

```bash
git reset --hard backup-$(date +%Y-%m-%d)
```

## Files That Must Survive

✅ **Always survive (not in upstream):**
- `custom/` directory
- `remote-start.sh`
- `server/routers/status.py`

⚠️ **Watch for conflicts:**
- `server/services/project_config.py`
- `server/schemas.py`
- `server/routers/settings.py`
- `agent.py`

---

**Full guide:** `UPDATE-GUIDE.md`
**Last update:** 2026-01-22 (28 commits merged successfully)
