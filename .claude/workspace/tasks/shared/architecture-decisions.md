# Architecture Decisions - UAT Gateway

**Workspace:** uat-gateway-oversight
**Purpose:** Shared record of architectural decisions
**Last Updated:** 2026-01-26

## Decision Template

Each decision should include:
- **Status:** Proposed | Approved | Rejected | Deprecated
- **Date:** Decision date
- **Context:** Background and problem
- **Decision:** What was decided
- **Rationale:** Why this decision
- **Consequences:** Impact and trade-offs
- **Alternatives Considered:** Other options explored

---

## Decision Log

### ADR-001: Adapter Pattern for Tool Integration

**Status:** Approved
**Date:** 2026-01-26
**Context:** Need to integrate multiple testing tools (Playwright, reg-cli, axe-core, Supertest, MSW) with different APIs.

**Decision:** Use adapter pattern to abstract tool differences behind unified interface.

**Rationale:**
- Each tool has unique API and conventions
- Allows adding/removing tools without breaking core
- Simplifies testing and maintenance
- Enables parallel tool development

**Consequences:**
- + Easy to add new tools
- + Isolated tool failures
- + Consistent interface for orchestrator
- - Additional abstraction layer
- - Slight performance overhead

**Alternatives Considered:**
- Direct tool integration: Rejected due to tight coupling
- Wrapper library: Rejected due to maintenance burden

---

### ADR-002: State Persistence via Checkpoints

**Status:** Approved
**Date:** 2026-01-26
**Context:** Long-running test execution needs to survive interruptions.

**Decision:** Implement checkpoint-based state persistence with JSON files and optional database backend.

**Rationale:**
- Supports resume after failures
- Enables debugging intermediate states
- Simple file-based approach (no database required initially)
- Can migrate to database if needed

**Consequences:**
- + Recovery from failures
- + Debugging capability
- + Simple initial implementation
- - File I/O overhead
- - Potential for stale state

**Alternatives Considered:**
- In-memory only: Rejected (no recovery)
- Database only: Rejected (over-engineering for v1)

---

### ADR-003: Kanban Card Hierarchy

**Status:** Approved
**Date:** 2026-01-26
**Context:** UAT produces multiple test artifacts (journeys, scenarios, bugs) that need Kanban tracking.

**Decision:** Implement hierarchical card system:
- Journey cards (🎭) - Parent cards for user journeys
- Scenario cards (🧪) - Child cards for individual tests
- Bug cards (🐛) - Linked to failing scenarios

**Rationale:**
- Maintains visibility at multiple levels
- Allows drilling down from journey to scenario
- Preserves existing Kanban UX patterns
- Enables dependency tracking

**Consequences:**
- + Clear hierarchy and relationships
- + Familiar card-based UX
- - More complex card management
- - Requires parent-child linking

**Alternatives Considered:**
- Flat card structure: Rejected (loses hierarchy)
- Separate board for UAT: Rejected (fragmented visibility)

---

### ADR-004: Real-time Updates via WebSocket

**Status:** Approved
**Date:** 2026-01-26
**Context:** Test execution can take minutes; users want live progress.

**Decision:** Implement WebSocket connection for real-time test execution updates.

**Rationale:**
- Better UX than polling
- Reduces server load
- Enables live progress bars
- Standard for real-time web apps

**Consequences:**
- + Excellent UX
- + Efficient server resource use
- - More complex frontend code
- - Requires reconnection handling

**Alternatives Considered:**
- HTTP polling: Rejected (poor UX, higher load)
- Server-Sent Events: Rejected (less flexible)

---

### ADR-005: Journey Discovery via Pattern Matching

**Status:** Approved
**Date:** 2026-01-26
**Context:** Need to automatically identify user journeys from feature specs.

**Decision:** Use keyword-based pattern matching with configurable journey templates.

**Rationale:**
- Works with existing spec format
- Configurable (add new patterns easily)
- Doesn't require ML/heuristics
- Transparent and debuggable

**Consequences:**
- + Simple implementation
- + Explainable results
- + Easy to extend
- - May miss complex journeys
- - Requires pattern maintenance

**Alternatives Considered:**
- ML-based clustering: Rejected (over-engineering, opaque)
- Manual journey definition: Rejected (defeats automation goal)

---

### ADR-006: Auto-Fix with Confidence Threshold

**Status:** Approved
**Date:** 2026-01-26
**Context:** Some test failures can be automatically fixed; others need human review.

**Decision:** Implement auto-fix with confidence scoring:
- Confidence ≥0.9: Apply automatically
- Confidence 0.7-0.9: Apply with human review
- Confidence <0.7: Create ticket for human

**Rationale:**
- Balances automation with safety
- Prevents bad automatic fixes
- Humans review edge cases
- Progressive enhancement as system learns

**Consequences:**
- + Safe automation
- + Humans stay in control
- + System can learn from corrections
- - Requires confidence calibration
- - Some manual work remains

**Alternatives Considered:**
- Full auto-fix: Rejected (too risky)
- No auto-fix: Rejected (misses automation opportunity)

---

### ADR-007: Visual Regression with Multi-Viewport Testing

**Status:** Approved
**Date:** 2026-01-26
**Context:** Apps must work across devices; visual bugs are user-visible.

**Decision:** Test 4 standard viewports with configurable diff tolerance.

**Rationale:**
- Covers majority of user devices
- Detects responsive design issues
- Configurable tolerance reduces false positives
- Industry standard practice

**Consequences:**
- + Comprehensive visual coverage
- + Catches responsive bugs
- - More test execution time
- - More screenshots to store

**Alternatives Considered:**
- Desktop only: Rejected (misses mobile bugs)
- All possible viewports: Rejected (impractical)

---

## Pending Decisions

### PDR-001: Database Backend for State

**Context:** File-based state may not scale for high-volume testing.

**Options:**
1. Keep file-based (simple)
2. Add SQLite (local DB)
3. Add PostgreSQL (shared DB)

**Status:** Monitoring - decide if file-based proves insufficient

---

### PDR-002: Test Artifact Retention Policy

**Context:** Screenshots, videos, and logs consume disk space.

**Options:**
1. Keep all artifacts forever
2. Keep N days then delete
3. Keep only on failure
4. Compress old artifacts

**Status:** Proposed - awaiting Phase 1 completion

---

## Stakeholder Input

### @architect
- Review all ADRs for architectural soundness
- Propose alternatives if concerns

### @dev
- Validate implementation feasibility
- Identify technical constraints

### @tea
- Ensure decisions support quality goals
- Validate testing implications

### @pm
- Assess timeline impact
- Identify scope implications
