# AutoScaler - Intelligent Resource Autoscaling

## Overview

The AutoScaler is an intelligent system that automatically adjusts AutoCoder's resource limits (CPU, memory, processes) based on real-time usage patterns. It ensures optimal performance while maintaining headroom for server operations.

## Quick Start

```bash
# Enable autoscaling
curl -X POST http://localhost:8888/api/autoscaler/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "enabled"}'

# Check status
curl http://localhost:8888/api/autoscaler/status

# View scaling history
curl http://localhost:8888/api/autoscaler/history?limit=10
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AutoScaler System                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────┐      ┌──────────────────┐            │
│  │  Metrics Collector│──────│  ThresholdScaler │            │
│  │  (cgroup v2)      │      │  (MVP logic)      │            │
│  └────────┬─────────┘      └────────┬─────────┘            │
│           │                          │                       │
│           ▼                          ▼                       │
│  ┌──────────────────┐      ┌──────────────────┐            │
│  │  SQLite Database │──────│  Action Executor │            │
│  │  (metrics/history)│     │  (systemd API)    │            │
│  └──────────────────┘      └──────────────────┘            │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## How It Works

### 1. Metrics Collection

Every 30 seconds, the autoscaler polls cgroup v2 for:
- **CPU usage**: From `/sys/fs/cgroup/.../cpu.stat`
- **Memory usage**: From `/sys/fs/cgroup/.../memory.current`
- **Process count**: From `/sys/fs/cgroup/.../cgroup.procs`

These are stored in `~/.autocoder/autoscaler.db` for trend analysis.

### 2. Threshold Evaluation

**Scale UP triggers** (any true, 3 consecutive checks):
- CPU > 85% of quota
- Memory > 80% of limit
- Processes > 85% of limit

**Scale DOWN triggers** (all true, 10 consecutive checks):
- CPU < 40% of quota
- Memory < 50% of limit
- Processes < 30% of limit
- No agents running OR all features complete

### 3. Resource Limits

**Current defaults** (from systemd service file):
- CPU: 200% (2 cores)
- Memory: 32GB
- Tasks: 250 processes

**Hard limits** (safety boundaries):
- Minimum: 1 core (100%), 8GB, 100 tasks
- Maximum: 8 cores (800%), 192GB, 1500 tasks

**System reserves** (never allocated):
- 1 CPU core
- 8GB RAM
- 50 processes

### 4. Scaling Action

When thresholds are breached:
1. Calculate new limits (scale up: ×1.5, scale down: ×0.6)
2. Backup current service file
3. Update `~/.config/systemd/user/autocoder-ui.service`
4. Run `systemctl --user daemon-reload`
5. Run `systemctl --user restart autocoder-ui.service`
6. On failure: restore backup immediately

## HTTP API Endpoints

### Status & Monitoring

#### `GET /api/autoscaler/status`

Get current autoscaler state.

**Response:**
```json
{
  "mode": "enabled",
  "policy": "balanced",
  "is_running": false,
  "current_limits": {
    "cpu_quota": 200,
    "memory_max": 32,
    "tasks_max": 250
  },
  "last_scale_time": "2026-01-25T10:30:00",
  "scale_up_count": 0,
  "scale_down_count": 0
}
```

#### `GET /api/autoscaler/metrics`

Get current resource usage from cgroup.

**Response:**
```json
{
  "timestamp": "2026-01-25T10:30:00",
  "cpu_percent": 45.2,
  "cpu_cores_used": 0.9,
  "memory_gb": 12.3,
  "process_count": 87,
  "agent_count": 2,
  "testing_agent_count": 0,
  "api_quota_remaining": 1000000,
  "features_pending": 15
}
```

#### `GET /api/autoscaler/history?limit=20`

View scaling action history.

**Response:**
```json
[
  {
    "id": 1,
    "timestamp": "2026-01-25T10:30:00",
    "action": "scale_up",
    "trigger_type": "threshold",
    "reason": "Thresholds breached: CPU=90.0%, Memory=28.5GB, Processes=230",
    "old_limits": {"cpu_quota": 200, "memory_max": 32, "tasks_max": 250},
    "new_limits": {"cpu_quota": 300, "memory_max": 40, "tasks_max": 350},
    "status": "success",
    "error_message": null
  }
]
```

### Control

#### `POST /api/autoscaler/mode`

Set operational mode.

**Request:**
```json
{
  "mode": "enabled"
}
```

Modes:
- `enabled`: Automatic scaling
- `disabled`: Autoscaler off
- `manual`: User controls limits via `/api/autoscaler/scale`

#### `POST /api/autoscaler/policy`

Set scaling policy profile.

**Request:**
```json
{
  "policy": "balanced"
}
```

Policies:
- `conservative`: 90% CPU threshold, 10min cooldown, ×1.3 scale-up
- `balanced`: 85% CPU threshold, 5min cooldown, ×1.5 scale-up (default)
- `aggressive`: 75% CPU threshold, 2min cooldown, ×2.0 scale-up

#### `POST /api/autoscaler/scale`

Manually set resource limits (switches to manual mode).

**Request:**
```json
{
  "cpu_quota": 600,
  "memory_max": 96,
  "tasks_max": 750,
  "reason": "Complex AI feature requiring heavy computation"
}
```

### Configuration

#### `GET /api/autoscaler/config`

Get current configuration.

#### `PUT /api/autoscaler/config`

Update configuration thresholds.

**Request:**
```json
{
  "scale_up_cpu_percent": 75,
  "consecutive_scale_up_checks": 2,
  "scale_cooldown_seconds": 120
}
```

## MCP Tools

Agents can control the autoscaler using these MCP tools:

### Control Tools

**`autoscaler_set_mode(mode)`**
- Enable/disable automatic scaling or switch to manual control
- Modes: `"enabled"`, `"disabled"`, `"manual"`

**`autoscaler_set_policy(policy)`**
- Set scaling policy profile
- Policies: `"conservative"`, `"balanced"`, `"aggressive"`

**`autoscaler_manual_scale(cpu_quota, memory_max, tasks_max, reason)`**
- Manually set resource limits
- Automatically switches to manual mode

### Query Tools

**`autoscaler_get_status()`**
- Get current autoscaler state and limits

**`autoscaler_get_metrics()`**
- Get current resource usage from cgroup

**`autoscaler_get_history(limit=20)`**
- View scaling action history

**`autoscaler_get_config()`**
- Get current configuration thresholds

**`autoscaler_set_config(...)`**
- Update specific configuration parameters

**`autoscaler_get_prediction()`**
- Get predicted future resource needs (Phase 2+ placeholder)

## Example Workflows

### Workflow 1: Automatic Scaling

```bash
# 1. Enable autoscaling
curl -X POST http://localhost:8888/api/autoscaler/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "enabled"}'

# 2. Start 5 parallel agents (via UI or API)
# The autoscaler detects high CPU usage and scales up to 300% CPU, 48GB RAM

# 3. Start 5 more agents
# Autoscaler detects queue depth and scales to 500% CPU, 64GB RAM

# 4. Features complete
# Autoscaler detects idle and scales back to 200% CPU, 32GB RAM
```

### Workflow 2: Manual Override

```bash
# 1. User knows a feature needs lots of resources
curl -X POST http://localhost:8888/api/autoscaler/scale \
  -H "Content-Type: application/json" \
  -d '{
    "cpu_quota": 600,
    "memory_max": 96,
    "tasks_max": 750,
    "reason": "Complex ML model training"
  }'

# 2. Feature completes

# 3. Re-enable autoscaling
curl -X POST http://localhost:8888/api/autoscaler/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "enabled"}'

# Autoscaler scales down after detecting idle
```

### Workflow 3: Conservative Policy for Production

```bash
# Set conservative policy for stability
curl -X POST http://localhost:8888/api/autoscaler/policy \
  -H "Content-Type: application/json" \
  -d '{"policy": "conservative"}'

# Result:
# - Scale-up only at 90% CPU (vs 85%)
# - 5 consecutive checks required (vs 3)
# - 10 minute cooldown (vs 5 minutes)
# - Less aggressive scaling (×1.3 vs ×1.5)
```

## Database Schema

The autoscaler uses SQLite at `~/.autocoder/autoscaler.db`:

### `autoscaler_metrics` (Rolling Window)

Stores resource usage snapshots (retention: 24 hours).

```sql
CREATE TABLE autoscaler_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    cpu_percent REAL NOT NULL,
    memory_gb REAL NOT NULL,
    process_count INTEGER NOT NULL,
    agent_count INTEGER NOT NULL,
    testing_agent_count INTEGER NOT NULL,
    api_quota_remaining INTEGER NOT NULL,
    features_pending INTEGER NOT NULL
);
```

### `autoscaler_history` (Audit Log)

Permanent log of all scaling actions.

```sql
CREATE TABLE autoscaler_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    old_cpu_quota INTEGER NOT NULL,
    old_memory_max INTEGER NOT NULL,
    old_tasks_max INTEGER NOT NULL,
    new_cpu_quota INTEGER NOT NULL,
    new_memory_max INTEGER NOT NULL,
    new_tasks_max INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT
);
```

### `autoscaler_config` (Single Row)

Configuration storage (id=1 only).

```sql
CREATE TABLE autoscaler_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT DEFAULT 'enabled',
    policy TEXT DEFAULT 'balanced',
    scale_up_cpu_percent INTEGER DEFAULT 85,
    scale_up_memory_percent INTEGER DEFAULT 80,
    scale_up_tasks_percent INTEGER DEFAULT 85,
    scale_down_cpu_percent INTEGER DEFAULT 40,
    scale_down_memory_percent INTEGER DEFAULT 50,
    scale_down_tasks_percent INTEGER DEFAULT 30,
    check_interval_seconds INTEGER DEFAULT 30,
    scale_cooldown_seconds INTEGER DEFAULT 300,
    consecutive_scale_up_checks INTEGER DEFAULT 3,
    consecutive_scale_down_checks INTEGER DEFAULT 10,
    scale_up_factor REAL DEFAULT 1.5,
    scale_down_factor REAL DEFAULT 0.6,
    min_cpu_quota INTEGER DEFAULT 100,
    max_cpu_quota INTEGER DEFAULT 800,
    min_memory_max INTEGER DEFAULT 8,
    max_memory_max INTEGER DEFAULT 192,
    min_tasks_max INTEGER DEFAULT 100,
    max_tasks_max INTEGER DEFAULT 1500,
    system_cpu_cores INTEGER DEFAULT 1,
    system_memory_gb INTEGER DEFAULT 8,
    system_processes INTEGER DEFAULT 50
);
```

## Safety Features

### Hard Limits

The autoscaler will **never** exceed:
- CPU: 8 cores (800%) → 66% of 12 total cores
- Memory: 192GB → 76% of 251GB total
- Processes: 1500 → safe limit

The autoscaler will **never** go below:
- CPU: 1 core (100%)
- Memory: 8GB
- Processes: 100

### Graceful Degradation

If service restart fails:
1. Restore backup service file immediately
2. Disable autoscaler (mark as failed)
3. Log error with details
4. Require manual re-enable

### Hysteresis (Anti-Thrash)

Prevents rapid up/down cycles:
- Minimum 5 minutes between scale actions
- Minimum scale amounts: 50% CPU, 8GB RAM, 50 tasks
- Scale up more aggressively (×1.5) than down (×0.6)

### Rollback on Failure

Every scaling action:
1. Creates backup of service file
2. Updates service file
3. Reloads systemd and restarts service
4. On failure: restores backup immediately

## Implementation Status

### ✅ Phase 1: MVP (Threshold-Based) - COMPLETE

Current implementation (this release):
- Reactive scaling based on current usage
- Threshold-based triggers (CPU >85%, etc.)
- Hysteresis (cooldown, minimum scale amounts)
- HTTP API endpoints
- MCP tools for agents
- SQLite persistence

### 🔄 Phase 2: Trend-Based - FUTURE

Planned features:
- Moving averages (MA5, MA15)
- Trend analysis (increasing/decreasing)
- Queue monitoring (feature queue depth)
- API quota awareness
- Prediction endpoint

### 🚀 Phase 3: ML-Powered - FUTURE

Planned features:
- Linear regression prediction
- Confidence intervals
- Feature complexity analysis
- Workload profiling
- Multi-project support

## Configuration Examples

### Conservative Policy (Stability-Focused)

```json
{
  "policy": "conservative",
  "scale_up_cpu_percent": 90,
  "scale_up_memory_percent": 85,
  "consecutive_scale_up_checks": 5,
  "scale_cooldown_seconds": 600,
  "scale_up_factor": 1.3
}
```

**Use case:** Production environments where stability is critical.

### Balanced Policy (Default)

```json
{
  "policy": "balanced",
  "scale_up_cpu_percent": 85,
  "scale_up_memory_percent": 80,
  "consecutive_scale_up_checks": 3,
  "scale_cooldown_seconds": 300,
  "scale_up_factor": 1.5
}
```

**Use case:** General development work.

### Aggressive Policy (Performance-Focused)

```json
{
  "policy": "aggressive",
  "scale_up_cpu_percent": 75,
  "scale_up_memory_percent": 70,
  "consecutive_scale_up_checks": 2,
  "scale_cooldown_seconds": 120,
  "scale_up_factor": 2.0
}
```

**Use case:** Rapid prototyping and development.

## Troubleshooting

### Autoscaler not scaling

1. Check mode is `enabled`:
   ```bash
   curl http://localhost:8888/api/autoscaler/status | jq '.mode'
   ```

2. Check metrics are being collected:
   ```bash
   curl http://localhost:8888/api/autoscaler/metrics | jq '.cpu_percent'
   ```

3. Verify thresholds are being breached:
   ```bash
   curl http://localhost:8888/api/autoscaler/config | jq '.scale_up_cpu_percent'
   ```

### Service restart failed

1. Check history for error:
   ```bash
   curl http://localhost:8888/api/autoscaler/history?limit=5 | jq '.[0].error_message'
   ```

2. Verify service file syntax:
   ```bash
   systemctl --user show autocoder-ui.service | grep FragmentPath
   cat ~/.config/systemd/user/autocoder-ui.service
   ```

3. Manual restart:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart autocoder-ui.service
   systemctl --user status autocoder-ui.service
   ```

### cgroup not found

The autoscaler requires the service to be running to find its cgroup:

```bash
# Start service first
systemctl --user start autocoder-ui.service

# Then check autoscaler metrics
curl http://localhost:8888/api/autoscaler/metrics
```

## Files

- `server/utils/resource_monitor.py` - cgroup metrics collector
- `server/services/autoscaler.py` - Main autoscaling engine
- `server/routers/autoscaler.py` - HTTP API endpoints
- `mcp_server/autoscaler_mcp.py` - MCP tools for agents
- `custom/docs/AUTOSCALER.md` - This documentation

## References

- Plan: `/home/stu/.claude/plans/stateless-roaming-brooks.md`
- Database: `~/.autocoder/autoscaler.db`
- Service file: `~/.config/systemd/user/autocoder-ui.service`
