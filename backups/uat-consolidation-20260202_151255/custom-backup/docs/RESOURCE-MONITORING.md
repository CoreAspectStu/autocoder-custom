# Resource Monitoring in Mission Control

**Last Updated:** 2026-01-25

AutoCoder custom instance includes real-time resource monitoring via Mission Control MCP tools.

---

## Available Tools

### 1. `resource_get_stats`

Get system and AutoCoder resource usage statistics.

**Usage:**
```python
# Via Mission Control MCP server
tool_result = await call_tool("resource_get_stats", {
    "include_processes": True  # Show per-process breakdown (default: true)
})
print(tool_result[0].text)
```

**Output:**
```
🖥️  System-Wide Resources
CPU: 4.2% (load: 0.88, 2.02, 2.73)
Memory: 8.06GB / 251.59GB (3.2%)
Processes: 408 total

🔒 AutoCoder Cgroup (systemd limits enforced)
Status: ✅ Running inside autocoder-ui.service
Processes: 6 (limit: 250)
CPU: 2.1% (limit: 200% = 2 cores)
Memory: 0.08GB (limit: 32GB)

📋 Per-Process Breakdown
  🌐 Web UI (PID 1354120): 0.5% CPU, 72.5MB RAM
  🤖 Agent (PID 1354300): 1.2% CPU, 145.3MB RAM
  🎭 Playwright (PID 1354320): 0.4% CPU, 89.2MB RAM

📊 API Quota (5-hour window)
Used: 500 / 10000 prompts (5.0%)
Remaining: 9500 prompts
```

---

## What It Shows

### System-Wide Resources
- **CPU %** - Total CPU usage across all cores
- **Load averages** - 1, 5, 15 minute load averages
- **Memory** - Used/total RAM and percentage
- **Processes** - Total process count on system

### AutoCoder Cgroup (if running inside systemd)
- **Status** - Whether limits are enforced (✅) or not (❌)
- **Processes** - Current process count / 250 limit
- **CPU** - Current usage / 200% limit (2 cores)
- **Memory** - Current usage / 32GB limit

**If NOT running inside cgroup:**
```
⚠️  AutoCoder Cgroup
Status: ❌ NOT running inside autocoder-ui.service
Warning: Resource limits NOT enforced!
```

### Per-Process Breakdown
Shows each AutoCoder process with:
- **Process type** - Web UI, Agent, Orchestrator, Coding Agent, Testing Agent, Playwright
- **PID** - Process ID
- **CPU %** - Current CPU usage
- **RAM** - Memory usage in MB

Process type icons:
- 🌐 Web UI - uvicorn server
- 🤖 Agent - autonomous_agent_demo.py
- 🎯 Orchestrator - parallel_orchestrator.py
- 💻 Coding Agent - Feature implementation
- 🧪 Testing Agent - Regression testing
- 🎭 Playwright - Browser automation
- 📦 Python - Other Python processes

### API Quota Summary
- **Used** - Prompts used in 5-hour window
- **Remaining** - Prompts remaining before quota limit
- **Percentage** - Usage percentage

---

## How Agents Use It

Agents can call the `resource_get_stats` tool through Mission Control to:

1. **Check if limits are enforced** - Verify they're running inside systemd cgroup
2. **Monitor resource usage** - See CPU/memory consumption before starting new agents
3. **Detect resource pressure** - Decide whether to spawn additional sub-agents
4. **Identify runaway processes** - Spot agents consuming excessive resources
5. **Correlate with API quota** - See both system resources and API usage together

**Example agent usage:**
```python
# Agent checks resources before spawning sub-agents
resource_stats = await call_tool("resource_get_stats", {})
quota_stats = await call_tool("quota_get_usage", {})

# Decide safe concurrency
quota_remaining = parse_remaining_prompts(quota_stats)
safe_agents = quota_remaining // 20  # 20 prompts per agent

# Check if system has capacity
if "limit: 250" in resource_stats and "Processes: 6" in resource_stats:
    current_processes = 6
    max_processes = 250
    capacity = max_processes - current_processes

    # Use the lower of API quota or system capacity
    actual_concurrency = min(safe_agents, capacity // 10)  # 10 processes per agent
```

---

## Human Monitoring

Operators can monitor resources in several ways:

### 1. Via Mission Control (DevLayer)
Agents can send resource updates to humans:
```python
await call_tool("devlayer_send_chat", {
    "message": f"Resource check: {resource_stats[0].text}"
})
```

### 2. Via Systemd
```bash
# Check service status (shows cgroup limits)
systemctl --user status autocoder-ui.service

# View resource usage
systemd-run --user --user --scope systemctl show autocoder-ui.service | grep -E "CPU|Memory"
```

### 3. Via Netdata
- **URL:** http://138.201.197.54:8088
- **Alerts:** CPU > 85%, Memory > 85%, process count
- **Custom alerts:** AutoCoder-specific metrics

### 4. Direct Tool Call
```bash
# From within AutoCoder project
cd ~/projects/autocoder
venv/bin/python -c "
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from custom.mission_control.mcp_server.mission_control_mcp import call_tool

async def test():
    result = await call_tool('resource_get_stats', {'include_processes': True})
    print(result[0].text)

asyncio.run(test())
"
```

---

## Resource Limits Reference

### AutoCoder UI Service Limits
```ini
CPUQuota=200%         # 2 cores (out of 12 available)
MemoryMax=32G         # 32GB (out of 251GB available)
TasksMax=250          # 250 processes max
```

### Expected Resource Usage

**Idle (no agents running):**
- Processes: 1-6 (uvicorn + worker processes)
- CPU: < 1%
- Memory: 70-100MB

**Active (1 agent running):**
- Processes: 10-20 (agent + MCP servers + Playwright)
- CPU: 2-5%
- Memory: 200-500MB

**Parallel mode (5 agents):**
- Processes: 50-80 (orchestrator + 5 coding agents + 5 testing agents + browsers)
- CPU: 10-20%
- Memory: 2-4GB

**Warning signs:**
- Processes > 100: Check for runaway sub-agents
- CPU > 50%: Possible infinite loop or stuck agent
- Memory > 8GB: Memory leak or browser not closing

---

## Troubleshooting

### "NOT running inside autocoder-ui.service"
**Problem:** Agent started manually outside systemd
**Solution:**
```bash
# Kill manual process
pkill -f "autonomous_agent_demo"

# Restart via systemd
systemctl --user restart autocoder-ui.service
```

### "Processes: 250 (limit: 250)"
**Problem:** Hit process limit, agents can't spawn
**Solution:**
```bash
# Check for stuck processes
ps aux | grep python | grep autocoder

# Kill stuck agents
pkill -9 -f "autonomous_agent_demo"

# Restart service
systemctl --user restart autocoder-ui.service
```

### High memory usage (> 8GB)
**Problem:** Playwright browsers not closing
**Solution:**
```bash
# Kill Playwright processes
pkill -f playwright
pkill -f chromium

# Restart service
systemctl --user restart autocoder-ui.service
```

### Cgroup not detected
**Problem:** Running outside systemd or cgroup v2 not enabled
**Check:**
```bash
# Verify cgroup v2
mount | grep cgroup

# Check if in cgroup
cat /proc/self/cgroup | grep autocoder-ui
```

---

## Integration with Quota Management

Resource monitoring works alongside quota management tools:

| Tool | Purpose |
|------|---------|
| `resource_get_stats` | System resources (CPU, RAM, processes) |
| `quota_get_usage` | API quota (prompts used/remaining) |
| `quota_set_limit` | Adjust quota limits for Anthropic/GLM |
| `quota_get_history` | Usage trends over time |

**Combined monitoring example:**
```python
# Agent checks both resources and quota before spawning
resources = await call_tool("resource_get_stats", {})
quota = await call_tool("quota_get_usage", {})

# Parse output
if "limit: 250" in resources and "Processes: 20" in resources:
    # System has capacity (230 processes available)
    pass

if "Remaining: 1000" in quota:
    # API quota allows 50 more agents (1000 / 20)
    pass
```

---

## Future Enhancements

Potential improvements to resource monitoring:

1. **Historical trends** - Track resource usage over time
2. **Alerting** - Automatic warnings when approaching limits
3. **Auto-scaling** - Adjust concurrency based on available resources
4. **Per-project stats** - Resource usage by project
5. **Cost estimation** - Calculate API costs based on quota usage

---

*Last updated: 2026-01-25*
