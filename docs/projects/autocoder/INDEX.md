# AutoCoder Project Documentation

## Quick Reference

| Document | Description | Last Updated |
|----------|-------------|--------------|
| [UAT Mode Trigger Fixes](./uat-mode-trigger-fixes.md) | Bug fixes for UAT Mode Play button - execution mode logic and orchestrator import | 2026-02-03 |
| [WebSocket Patterns](./websocket-patterns.md) | WebSocket error handling patterns and accept-then-validate approach | 2026-02-03 |

## Recent Changes

### 2026-02-03: UAT Mode Trigger Fixes
**Issue:** UAT Mode Play button not working - "nothing happens"

**Root Causes:**
1. Execution mode logic error (`request.force or True` always True)
2. Wrong orchestrator import (broken `uat_plugin` instead of working `uat_gateway`)

**Impact:** UAT tests were not executing from the global `~/.autocoder/uat_tests.db` database (300+ pending tests).

**See:** [uat-mode-trigger-fixes.md](./uat-mode-trigger-fixes.md) for full details, testing procedures, and maintenance guidelines.

### 2026-02-03: WebSocket Connection Fixes
**Issue:** WebSocket connections failing with HTTP 403 errors

**Root Causes:**
1. Missing `await websocket.accept()` before validation
2. Pydantic validators not handling NULL values from database

**Impact:** All WebSocket endpoints (project, assistant, spec, terminal, expand) were failing.

**See:** [websocket-patterns.md](./websocket-patterns.md) for the accept-then-validate pattern and error handling best practices.

## Maintenance Checklist

When modifying these systems:
- [ ] Review relevant documentation first
- [ ] Test changes against existing patterns
- [ ] Update documentation if patterns change
- [ ] Commit with clear reference to the issue addressed

## Related Documentation

- `/custom/docs/UPDATE-GUIDE.md` - Upstream merge procedures
- `/custom/docs/` - Custom module documentation
- `/.github/FORK-MAINTENANCE.md` - Fork maintenance and merge strategy
