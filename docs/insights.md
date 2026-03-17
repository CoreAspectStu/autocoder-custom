# Learnings & Gotchas

## Port Policy Enforcement (2026-02-13)

### Validation Script Requires Venv

**Issue:** `bin/validate-port-assignments` imports AutoCoder modules that require dependencies (psutil, etc.)

**Solution:** Created wrapper script `bin/validate-ports` that activates the venv first

**Lesson:** When creating utility scripts for AutoCoder, either:
1. Make them venv-aware (activate first)
2. Keep them dependency-free
3. Document the venv requirement clearly

### AutoCoder UI Must Restart for Config Changes

**Issue:** After changing port range constants, AutoCoder UI was still using old range (4000-4099)

**Solution:** `systemctl --user restart autocoder-ui`

**Lesson:** Python code changes require service restart. Port range is loaded at startup, not dynamically.

### Multiple Sessions for Same Path

**Observation:** Found 3 sessions registered for `/home/stu/projects/autocoder`:
- `autocoder-bugs` (old, from 2026-01-20)
- `autocoder-update` (old, from 2026-02-09)
- `autocoder-development` (new, active)

**Lesson:** Old sessions should be marked as `status: complete` or cleaned up. Session registry can accumulate stale entries.

---

## Template Section

When adding new insights, use this format:

## [Topic] (YYYY-MM-DD)

### [Specific Issue or Discovery]

**Issue/Context:** [What happened or was discovered]

**Solution/Explanation:** [How it was resolved or what it means]

**Lesson:** [Key takeaway for future work]
