# AutoCoder Future Improvements

**Date:** 2026-01-20
**Source:** Party-mode brainstorming session

---

## Quick Wins Implemented ✅

1. **TL;DR section** - Added to `custom/README.md` (reduces decision fatigue)
2. **Doctor command** - `./remote-start.sh doctor` (7-step health check)
3. **Better port detection** - Uses `lsof` with socket fallback in `status.py`
4. **Help command** - Enhanced with doctor reference

---

## Strategic Improvements (Not Yet Implemented)

### 1. Multi-User Architecture

**Problem:** Single UI server, shared Xvfb, manual SSH tunnels - can't serve multiple developers simultaneously

**Options:**
- **A) Containerization** (Docker + Traefik)
  - Complete isolation, resource limits
  - Overhead, complexity

- **B) Namespace isolation** (Dynamic port allocation)
  - Lighter weight: 8888 + user_id per user
  - Port management complexity

### 2. State Management Scalability

**Problem:** SQLite per project - no concurrent access, no transaction isolation for parallel agents

**Solution:** PostgreSQL migration
- Already running locally
- Connection pooling via pgbouncer
- ACID guarantees, row-level locking
- Better observability

### 3. SSH Tunnel Pain Point

**Problem:** Manual tunnel setup is barrier to adoption for non-technical users

**Options:**
- **A) Web proxy** (Cloudflare Tunnel/ngrok) - Zero SSH config
- **B) Wireguard VPN** - Direct network access
- **C) Code-server integration** - VS Code + AutoCoder in browser

---

## High Impact / Low Effort Features

### 1. One-Line Install Script
```bash
curl -fsSL https://autocoder.sh/install | bash
```
- Auto-detects OS, installs deps, configures everything
- Eliminates 80% of setup pain

### 2. Health Monitoring Endpoint
- `/api/health` returns JSON status
- Hook into uptime monitors
- Slack notifications on failures

### 3. Project Templates
- Pre-configured specs for common stacks
- `./remote-start.sh new --template=nextjs-saas`
- Faster time-to-value

### 4. Web-Based Terminal
- View agent output in browser (no SSH needed)
- xterm.js + WebSockets
- Medium-high effort

### 5. Agent Resource Limits
- Memory/CPU caps per agent
- Prevents runaway processes
- systemd cgroups integration

### 6. Backup/Restore
- `./remote-start.sh backup project-name`
- Saves features.db + generated code
- S3/B2 backend

---

## Still Pending from Dev Review

- Integration tests (none exist)
- Centralized JSON logging
- Modularize remote-start.sh (currently 430 lines)
- Environment variables for paths
- Session naming collision prevention (partially implemented)

---

## Strategic Questions to Answer

**Target User:**
- Solo developers? (current setup works)
- Small teams (2-5)? (need multi-user + collaboration)
- Enterprise? (need SSO, audit logs, quotas)

**Usage Data Needed:**
- How many concurrent projects?
- Average session duration?
- Most common failure modes?

**Competitive Context:**
- GitHub Copilot Workspace - cloud-native
- Cursor - local-first, seamless
- Replit Agent - fully hosted

**AutoCoder's Unique Value:**
- Self-hosted (data sovereignty)
- Multi-session persistence
- Feature tracking + regression testing

---

## Architectural Constraints

1. **Multi-tenant support** - Current design is single-user
2. **Concurrent access** - SQLite limits parallel agents
3. **Network accessibility** - SSH tunnels are setup friction

---

## Next Steps (When Returning to This)

1. Define target user persona
2. Gather usage metrics (if available)
3. Pick ONE constraint to solve first
4. Start with highest impact/lowest effort items
5. Consider: Is this a fork or upstream contribution?

---

## References

- Party-mode discussion: 2026-01-20
- Participants: Winston (Architect), Mary (Analyst), Amelia (Dev), Barry (Quick Flow)
- Implementation commit: e0fbce8
