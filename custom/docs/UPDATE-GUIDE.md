# AutoCoder Update Guide

**Last Updated:** 2026-02-01
**Purpose:** Safe upstream updates while preserving custom work

## 📋 Pre-Update Checklist

**⚠️ NEW: Run the automated readiness check first:**
```bash
cd ~/projects/autocoder
./bin/check-upgrade-readiness.sh
```

This checks for:
- Uncommitted changes (will block upgrade)
- Pending database migrations (will warn)
- Service health status
- Backup branch exists

Then proceed with manual steps:

1. **Verify clean working directory:**
   ```bash
   cd ~/projects/autocoder
   git status  # Should show "nothing to commit, working tree clean"
   ```

2. **Create backup branch:**
   ```bash
   git branch backup-$(date +%Y-%m-%d)
   git branch | grep backup  # Verify it was created
   ```

3. **Check what's coming:**
   ```bash
   git fetch upstream master
   git log --oneline HEAD..upstream/master | head -20  # See incoming commits
   git diff --stat HEAD..upstream/master  # See file changes
   ```

4. **Check for schema changes** (if merging custom work):
   ```bash
   # Search for database schema changes in incoming commits
   git diff HEAD..upstream/master -- "*.py" | grep -E "Column|ADD COLUMN|ALTER TABLE"
   ```

---

## 🛡️ Custom Work That Must Survive

### Files We Own (Not in Upstream)
These will never conflict and auto-survive:

- ✅ `custom/` - All documentation, patches, auth utilities
- ✅ `remote-start.sh` - Remote server management script
- ✅ `server/routers/status.py` - Enhanced dashboard (1132 lines)

### Files We Modified (Potential Conflicts)
Watch for conflicts in:

- ⚠️ `server/services/project_config.py` - Port assignment logic (4000-4099)
- ⚠️ `server/schemas.py` - May have schema field conflicts
- ⚠️ `server/routers/settings.py` - May have endpoint conflicts
- ⚠️ `agent.py` - Import statement conflicts

---

## 🔄 Update Process

### Step 1: Pull Upstream
```bash
cd ~/projects/autocoder
git pull origin master --no-rebase
```

**Expected:** Merge conflicts in modified files.

### Step 2: Resolve Conflicts

For each conflict file, use this strategy:

#### Pattern 1: Imports (agent.py, etc.)
```bash
# Conflict looks like:
<<<<<<< HEAD
from progress import has_features, is_project_complete, ...
=======
from progress import count_passing_tests, has_features, ...
>>>>>>> origin/master

# Resolution: KEEP BOTH (merge unique imports)
from progress import count_passing_tests, has_features, is_project_complete, ...
```

#### Pattern 2: Removed Custom Features (settings.py, schemas.py)
```bash
# If upstream removed our custom auth code:
<<<<<<< HEAD
auth_method: Literal["claude_login", "api_key"] = "claude_login"
api_key_configured: bool = False
=======
testing_agent_ratio: int = 1
count_testing_in_concurrency: bool = False
>>>>>>> origin/master

# Resolution: ACCEPT THEIRS (upstream simplified auth)
testing_agent_ratio: int = 1
count_testing_in_concurrency: bool = False
```

**Why?** Authentication still works via Claude CLI without the custom code.

#### Pattern 3: Deleted Files
If upstream deletes a file we use:
- `server/routers/status.py` - Don't worry, ours will remain (it's custom)
- `custom/` directory - Never touched by upstream

### Step 3: Stage and Commit
```bash
# After resolving all conflicts:
git add <resolved-files>
git status  # Verify all conflicts resolved

git commit -m "Merge upstream: <describe new features>

Conflicts resolved:
- <file1>: <what you did>
- <file2>: <what you did>

Preserved custom:
- remote-start.sh
- server/routers/status.py
- custom/ directory

Upstream features:
- <list key new features>
"
```

### Step 4: Install New Dependencies
```bash
cd ~/projects/autocoder
source venv/bin/activate

# Check if requirements.txt changed:
git diff HEAD~1 requirements.txt

# If changed, install:
pip install -r requirements.txt
```

**Common new dependencies:**
- `apscheduler` (for scheduling feature)
- Check `requirements.txt` diff for others

### Step 5: Test Everything
```bash
# 1. Stop any running instances
./remote-start.sh stop

# 2. Start UI server
./remote-start.sh ui

# 3. Wait and test API
sleep 5
curl -s http://localhost:8888/api/settings | jq

# 4. Test agent start/stop
curl -X POST "http://localhost:8888/api/projects/QR/agent/start" \
  -H "Content-Type: application/json" \
  -d '{"yolo_mode": true}' | jq

sleep 3
curl "http://localhost:8888/api/projects/QR/agent/status" | jq
curl -X POST "http://localhost:8888/api/projects/QR/agent/stop" | jq

# 5. Check status dashboard
curl http://localhost:8888/status | grep "AutoCoder Dashboard"

# 6. Check logs for errors
tmux capture-pane -t autocoder-ui -p | tail -50
```

---

## 🚨 If Something Breaks

### Rollback to Backup
```bash
git reset --hard backup-$(date +%Y-%m-%d)
```

### Check for Missing Dependencies
```bash
# Compare old vs new requirements:
git show origin/master:requirements.txt > /tmp/new-reqs.txt
git show HEAD~1:requirements.txt > /tmp/old-reqs.txt
diff /tmp/old-reqs.txt /tmp/new-reqs.txt

# Install any new packages
pip install <new-package>
```

### Check Import Errors
```bash
# If server won't start, check imports:
cd ~/projects/autocoder
source venv/bin/activate
python -c "from server.main import app; print('Imports OK')"
```

---

## 📝 Post-Update Documentation

After successful update:

1. **Update this guide** with any new patterns encountered
2. **Update `custom/README.md`** with:
   - New line counts for modified files
   - New upstream features received
   - Changelog entry with date
3. **Document any new conflicts** you resolved
4. **Test key features** again after a day

---

## 🎯 Quick Reference

### Conflict Resolution Rules:
1. **Imports:** Merge both (keep unique)
2. **Removed custom features:** Accept theirs (if feature non-critical)
3. **Custom files:** Always keep ours
4. **New dependencies:** Install from requirements.txt

### Files That Always Survive:
- `custom/` directory
- `remote-start.sh`
- `server/routers/status.py`

### Files to Watch:
- `server/services/project_config.py` (port assignment)
- `server/schemas.py` (schema fields)
- `server/routers/settings.py` (endpoints)
- `agent.py` (imports)

---

## 🔗 Related Documentation

- `custom/README.md` - Overview of all customizations
- `custom/docs/auth-settings-customization.md` - Auth system details (deprecated)
- `custom/patches/README.md` - Patch system (currently unused, consider removing)

---

## 📜 Past Incidents & Lessons Learned

### 2026-02-01: Database Schema Mismatch After Upgrade

**Problem:** After merging upstream fixes and custom UAT work, project assistants failed with "table conversations has no column named mode".

**Root Cause:**
- Custom UAT work added `mode` column to `conversations` table
- Migration script existed but was never executed
- Code expected new schema but databases had old schema

**Resolution:**
- Manually ran `assistant_db_add_mode_column.py` on all 7 project databases
- Created `check-upgrade-readiness.sh` to catch this in future

**Lessons:**
1. Schema changes require automated migrations
2. Run readiness check before any upgrade
3. Never merge custom work without checking for pending migrations

**Full Postmortem:** `docs/postmortem-2026-02-01-upgrade.md`

---

## 📞 For Claude Code in Future Sessions

### ⚠️ CRITICAL - YOU ARE READING THIS NOW, SO REMEMBER IT

**When the user says ANY of these phrases:**
- "update autocoder"
- "pull from upstream"
- "get latest changes"
- "merge upstream"
- "update from the base repo"

**YOU MUST:**

1. **STOP** - Do not run any git commands yet
2. **READ** this entire file: `/home/stu/projects/autocoder/custom/docs/UPDATE-GUIDE.md`
3. **UNDERSTAND** what custom work exists (see "Custom Work That Must Survive" section above)
4. **PLAN** using TodoWrite to track all steps
5. **BACKUP** first: `git branch backup-$(date +%Y-%m-%d)`
6. **EXECUTE** following the documented process exactly
7. **TEST** thoroughly using the documented testing procedures
8. **VERIFY** all custom files survived (status.py, remote-start.sh, custom/)

**Why this matters:**
- This is a custom-modified fork with 1000+ lines of custom code
- Upstream has deleted files we depend on (status.py)
- Upstream removed features we use (port assignment)
- Wrong merge strategy = data loss

**Context for AI:** This is a custom-modified fork of AutoCoder with:
- Enhanced status dashboard (server/routers/status.py - 1132 lines)
- Remote server management (remote-start.sh)
- Custom documentation (custom/ directory)
- Port assignment system (4000-4099 range)

All custom work MUST survive upstream updates.
