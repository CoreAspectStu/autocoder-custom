# Architectural Decisions

## Port Allocation Policy (2026-02-13)

**Decision:** Expand AutoCoder port range from 4000-4099 to 4000-4999

**Rationale:**
- Original 100-port range too limiting for scale
- 1000 ports supports large number of concurrent projects
- Maintains SSH tunnel compatibility
- Prevents conflicts with local services (3000-3999) and system services (8000-8999)

**Implementation:**
- Updated `DEVSERVER_PORT_MIN/MAX` constants in `server/services/project_config.py`
- Created validation tools (`bin/validate-port-assignments`, `bin/validate-ports`)
- Documented in `PORT-POLICY.md` and system `~/CLAUDE.md`
- All existing projects (4000-4099) remain valid (subset of new range)

**Impact:**
- All new projects auto-assigned from 4000-4999
- Existing projects with ports 4000-4099 continue to work
- No migration needed
- AutoCoder UI restart required to pick up new range

---

## Template Section

When adding new decisions, use this format:

## [Decision Name] (YYYY-MM-DD)

**Decision:** [What was decided]

**Rationale:** [Why this decision was made]

**Alternatives Considered:** [Other options and why they were rejected]

**Implementation:** [How it was implemented]

**Impact:** [Effects on codebase, users, or operations]
