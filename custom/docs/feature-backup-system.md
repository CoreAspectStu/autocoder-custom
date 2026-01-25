# Feature Database Backup System

## Overview

AutoCoder now includes an **automatic backup system** for `features.db` databases. Every time a feature is created, modified, or has its status changed, an automatic backup is created.

This prevents data loss if the database becomes corrupted (like the QR project incident on 2026-01-25).

## How It Works

### Automatic Backups

The backup system is integrated into the Feature MCP server. Backups are triggered automatically when:

- ✅ **Features are created** - Before adding new features to the database
- ✅ **Features are marked passing** - Before updating a feature to "passing" status
- ✅ **Features are marked failing** - Before marking a feature as failing (regression)
- ✅ **Dependencies are added** - Before adding feature dependencies
- ✅ **Dependencies are removed** - Before removing dependencies
- ✅ **Bulk operations** - Before bulk feature creation

### Backup Files

**Location:** `{project_path}/.feature_backups/`

**Filename format:** `features_{count}_{timestamp}_{reason}.db`

Example: `features_598_20260125-144648_before_mark_passing.db`

**Metadata:** Each backup has a corresponding `.json` file with:
- Timestamp
- Reason for backup
- Feature count
- File sizes

### Rolling Retention

- **Keeps last 20 backups** by default
- Older backups automatically deleted
- ~0.3-0.4MB per backup (depending on feature count)
- Total storage: ~6-8MB for full backup history

## Using the Backup System

### Command-Line Tool

A `manage_backups.py` script is provided for manual backup management:

```bash
# List all backups for a project
python manage_backups.py list /path/to/project

# Show backup status
python manage_backups.py status /path/to/project

# Create a manual backup
python manage_backups.py backup /path/to/project --reason "before_experiments"

# Restore from backup
python manage_backups.py restore /path/to/project features_598_20260125-144648.db

# Clean up old backups (keep last 10)
python manage_backups.py cleanup /path/to/project --keep 10
```

### Using Environment Variable

```bash
export PROJECT_DIR=/path/to/project

python manage_backups.py list      # Uses PROJECT_DIR
python manage_backups.py status    # Uses PROJECT_DIR
```

## Backup Triggers

### MCP Server Tools

The following MCP tools automatically trigger backups:

| Tool | Backup Reason |
|------|---------------|
| `feature_create` | `before_feature_create` |
| `feature_create_bulk` | `before_bulk_create` |
| `feature_mark_passing` | `before_mark_passing` |
| `feature_mark_failing` | `before_mark_failing` |
| `feature_add_dependency` | `before_add_dependency` |
| `feature_remove_dependency` | `before_remove_dependency` |

### Python API

```python
from pathlib import Path
from api.database_backup import backup_features_db, list_backups, restore_from_backup

project_path = Path("/path/to/project")

# Manual backup
backup_path = backup_features_db(project_path, reason="manual")

# List backups
backups = list_backups(project_path)

# Restore from backup
success = restore_from_backup(project_path, "features_598_20260125-144648.db")
```

## Recovery Procedure

If `features.db` becomes corrupted:

### 1. Identify Corruption

Symptoms:
- API returns "database disk image is malformed"
- Kanban board won't load
- Features list is empty

### 2. List Available Backups

```bash
cd ~/projects/autocoder
python manage_backups.py list ~/projects/autocoder-projects/QR
```

### 3. Choose a Backup

Look for:
- Recent timestamp
- High feature count
- Good reason (e.g., "before_mark_passing")

### 4. Restore

```bash
python manage_backups.py restore ~/projects/autocoder-projects/QR \
    features_598_20260125-144648_before_mark_passing.db
```

The system will:
1. Create an emergency backup of the corrupted database
2. Restore from the chosen backup
3. Verify the database is readable
4. Report success/failure

## Configuration

### Change Retention Limit

Edit `api/database_backup.py`:

```python
MAX_BACKUPS = 30  # Keep last 30 backups instead of 20
```

### Change Backup Location

Backups are stored in `{project}/.feature_backups/` by default. This is intentional because:
- ✅ Project-specific (each project has its own backups)
- ✅ Git-friendly (can add `.feature_backups/` to `.gitignore` or track it)
- ✅ Portable (moves with the project)

### Disable Automatic Backups

To disable automatic backups, comment out the `backup_features_db()` calls in `mcp_server/feature_mcp.py`.

**Not recommended** - this defeats the safety mechanism.

## Monitoring

### Check Backup Status for All Projects

```python
from registry import list_registered_projects
from api.database_backup import backup_project_summary

projects = list_registered_projects()

for name, info in projects.items():
    project_path = Path(info["path"])
    summary = backup_project_summary(project_path)
    print(f"{name}: {summary['backup_count']} backups")
```

### Integration with Monitoring Tools

The backup system can be integrated with:
- **Netdata** - Alert if backup count is 0
- **Status page** - Show backup status in project cards
- **Scripts** - Periodic backup verification

## Best Practices

1. **Before risky operations:** Manually create a backup with `--reason "pre_experiment"`
2. **After major milestones:** Manually backup with `--reason "milestone_reached"`
3. **Regular cleanup:** Run `cleanup` to prevent disk usage growth
4. **Check status periodically:** Use `status` command to verify backups are being created
5. **Test restores:** Occasionally verify backups can be restored successfully

## Troubleshooting

### No backups being created

**Check:**
```bash
ls -la /path/to/project/.feature_backups/
```

**If empty:**
- Check MCP server logs for errors
- Verify `api/database_backup.py` exists
- Check file permissions on backup directory

### Backup restore fails

**Common causes:**
1. Backup file is also corrupted
2. Insufficient disk space
3. File permissions issue

**Solution:** Try an older backup, or use the emergency backup that was created during the restore attempt.

### Disk space growing

**Check:**
```bash
du -sh /path/to/project/.feature_backups/
```

**Solution:** Run cleanup to remove old backups
```bash
python manage_backups.py cleanup /path/to/project --keep 10
```

## Technical Details

### Database Format

- **Engine:** SQLite 3
- **File:** `features.db` in project root
- **Tables:** `features` (main), `alembic_version` (if migrations used)

### Backup Method

- **Type:** Full file copy using `shutil.copy2()`
- **Metadata:** Preserves timestamps and file attributes
- **Validation:** Verifies database is readable before backing up

### Concurrency Safety

- Backups are synchronous (block until complete)
- Multiple agents can backup simultaneously (file locking handled by OS)
- Each backup is atomic (copy or fail, no partial state)

## Future Improvements

Potential enhancements for the backup system:

- [ ] Compress backups older than 7 days
- [ ] Scheduled automatic backups (cron-like)
- [ ] Cloud storage integration (S3, Google Drive)
- [ ] Differential backups (only changes since last backup)
- [ ] Backup verification (integrity checks)
- [ ] Automatic restore testing
- [ ] Multi-project backup management
- [ ] Backup replication to secondary storage
- [ ] Email notifications on backup failures
