# Postmortem: AutoCoder Upgrade 2026-02-01

## Executive Summary

On 2026-02-01, an upgrade from upstream (leonvanzyl/autocoder) was performed to apply critical fixes for runaway testing agent spawning. The upgrade succeeded but caused a runtime error: "table conversations has no column named mode" when opening project assistants.

**Root Cause:** Custom UAT work included a database schema change (added `mode` column) but lacked an automated migration path for existing databases.

## Timeline

| Time | Event | Status |
|------|-------|--------|
| 14:20 | Identified need for upstream update (runaway agent fix) | - |
| 14:25 | Created backup branches per UPDATE-GUIDE.md | ✅ |
| 14:27 | Cherry-picked critical upstream commits (2) | ✅ |
| 14:28 | Merged UAT custom work branch back to master | ✅ |
| 14:30 | Rebuilt UI and restarted service | ✅ |
| 14:31 | Service running, API responding | ✅ |
| 14:37 | User opened callAspect project assistant | ❌ Error |

## Root Cause Analysis

### What Went Wrong

The UAT custom work (`uat-custom-work-backup` branch) included:

1. **Code changes** - `server/services/assistant_database.py` added `mode` parameter to:
   - `Conversation` model (new column: `mode = Column(String(10), nullable=False, default='dev')`)
   - `create_conversation()` function signature
   - `get_conversations()` function signature

2. **Migration script** - `server/services/assistant_db_add_mode_column.py` was added to fix existing databases
3. **BUT** - The migration script was **never executed** as part of the merge

### Why It Happened

```
┌─────────────────────────────────────────────────────────────────┐
│ Before Upgrade                                                  │
├─────────────────────────────────────────────────────────────────┤
│ Working directory had UNCOMMITTED changes including:            │
│ - assistant_database.py with mode column                       │
│ - assistant_chat_session.py with session fixes                 │
│ - UI components with UAT improvements                          │
│ - Migration script (assistant_db_add_mode_column.py)           │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ Upgrade Process (What We Did)                                  │
├─────────────────────────────────────────────────────────────────┤
│ 1. Created branch uat-custom-work-backup                       │
│ 2. Committed all uncommitted work to that branch               │
│ 3. Cherry-picked upstream fixes to master                      │
│ 4. Merged uat-custom-work-backup into master                   │
│ 5. Rebuilt UI, restarted service                               │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ The Gap                                                         │
├─────────────────────────────────────────────────────────────────┤
│ ❌ Database migration script exists but was never run          │
│ ❌ No automated migration hook in the merge process            │
│ ❌ Existing assistant.db files (7 projects) had old schema      │
│ ❌ Code expected new schema → runtime error                    │
└─────────────────────────────────────────────────────────────────┘
```

### Contributing Factors

1. **Custom work was in progress** - UAT mode development was active but incomplete
2. **Migration manual process** - Script required manual execution per project
3. **No schema version tracking** - No way to know which DBs needed migration
4. **No pre-flight checks** - Service started successfully despite schema mismatch

## Resolution

**Applied at 14:40 AEDT** - Manual migration of all 7 project databases:

```bash
for db in /home/stu/projects/autocoder-projects/*/assistant.db; do
  python server/services/assistant_db_add_mode_column.py "$(dirname "$db")"
done
```

**Result:** All databases updated, project assistants working.

## Lessons Learned

### 1. Schema Changes Require Automated Migrations

**Problem:** Database schema changed but no automated migration.

**Solution:** For future schema changes:
- Add a migration system with version tracking
- Run migrations automatically on service startup
- Or use Alembic for proper SQLAlchemy migrations

### 2. Uncommitted Work is a Risk

**Problem:** Custom UAT work was uncommitted when upgrade was needed.

**Solution:**
- Commit WIP work to feature branches regularly
- Use `git stash` if you need to preserve uncommitted work during upgrade
- Never merge uncommitted work without reviewing

### 3. Migration Scripts Should Be Executable, Not Just Present

**Problem:** Migration script existed but wasn't run.

**Solution:** Add post-merge checklist:
```bash
# After any merge that touches database schemas:
grep -r "ALTER TABLE\|ADD COLUMN" server/ && echo "⚠️ Schema changes detected - run migrations!"
```

### 4. The UPDATE-GUIDE.md Process Works (Mostly)

**What worked:**
- ✅ Created backup branches before changes
- ✅ Cherry-picked specific commits (safer than full merge)
- ✅ Preserved custom work on separate branch
- ✅ Service stayed healthy through upgrade

**What didn't:**
- ❌ No check for pending migrations
- ❌ No validation that databases match code expectations

## Recommendations

### Immediate Actions

1. **Add migration runner to service startup:**
   ```python
   # In server/main.py
   on_startup():
       ensure_database_schema_current()
   ```

2. **Add pre-merge validation:**
   ```bash
   # Before git merge
   ./bin/check-pending-migrations.sh
   ```

3. **Document schema changes in CLAUDE.md:**
   ```markdown
   ## Schema Changes
   - 2026-01-XX: Added `mode` column to conversations table
   ```

### Long-term Improvements

1. **Adopt Alembic** for database migrations (industry standard)
2. **Add integration tests** that verify schema compatibility
3. **Create upgrade checklist** in UPDATE-GUIDE.md:
   - [ ] Check for pending migrations
   - [ ] Backup databases
   - [ ] Run migrations
   - [ ] Smoke test all features

4. **Consider schema version field** in each database:
   ```sql
   CREATE TABLE schema_version (version INTEGER, applied_at TIMESTAMP);
   ```

## Appendix: Files Changed in This Upgrade

### Upstream Fixes Applied
- `parallel_orchestrator.py` - Runaway agent cap + tracking cleanup

### Custom UAT Work Merged
- `server/services/assistant_database.py` - Added mode column
- `server/services/assistant_chat_session.py` - Session management
- `server/routers/assistant_chat.py` - Error handling
- `ui/src/components/*` - UAT mode improvements
- `server/services/assistant_db_add_mode_column.py` - Migration script (NEW)
- `server/tests/test_conversation_security.py` - Security tests (NEW)

### Backup Branches Created
- `backup-2026-02-01` - Pre-upgrade state
- `uat-custom-work-backup` - UAT WIP commit

---

**Prepared:** 2026-02-01
**Status:** Resolved
**Next Review:** After next upstream update
