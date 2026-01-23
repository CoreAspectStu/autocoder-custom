# AutoCoder Netdata Monitoring

## Overview

Netdata now automatically monitors AutoCoder when `autocoder-ui.scope` is running. Alerts fire to Slack (#alerts channel) with specific remediation commands.

## What's Monitored

### 1. **Escaped Processes** (Auto-cleanup enabled ✅)
- **Metric:** `autocoder.escaped_processes`
- **Tracks:** Claude and Xvfb processes outside the systemd scope
- **Warning:** > 5 escaped processes
- **Critical:** > 10 escaped processes
- **Auto-remediation:** Runs `/usr/local/bin/autocoder-auto-cleanup` automatically
- **Manual:** `autocoder-cleanup-escaped`

### 2. **Task Count** (Manual remediation)
- **Metric:** `cgroup_autocoder-ui.scope.cpu_limit`
- **Warning:** > 400 tasks (80% of limit)
- **Critical:** > 450 tasks (90% of limit)
- **Remediation:**
  ```bash
  autocoder-ui-stop
  nano ~/bin/autocoder-ui-start  # Change TasksMax=500 to TasksMax=750
  autocoder-ui-start
  ```

### 3. **Memory Usage** (Manual remediation)
- **Metric:** `cgroup_autocoder-ui.scope.mem_usage`
- **Warning:** > 87.5% (14GB of 16GB)
- **Critical:** > 93.75% (15GB of 16GB)
- **Remediation:**
  ```bash
  autocoder-ui-stop
  nano ~/bin/autocoder-ui-start  # Change MemoryMax=16G to MemoryMax=32G
  autocoder-ui-start
  ```

### 4. **Active Agents**
- **Metric:** `autocoder.agents`
- **Tracks:** Number of coding agents currently running
- **Info only:** No alerts, just visibility

### 5. **Feature Progress**
- **Metric:** `autocoder.features`
- **Tracks:** `passing` and `total` features
- **Info only:** No alerts, just visibility

### 6. **Scope Crashed**
- **Warning:** Scope is in failed/dead state
- **Remediation:** `autocoder-ui-start` to restart

## Slack Notifications

All alerts go to **#alerts** channel with:
- Current metric value
- Threshold breached
- Specific command to run for remediation
- Auto-cleanup confirmation (when it runs)

Example alert:
```
⚠️ AutoCoder tasks high: 478/500 (95%)
Run: autocoder-ui-stop && edit ~/bin/autocoder-ui-start to increase TasksMax=750
```

## Auto-Cleanup

When > 5 escaped processes detected:
1. Netdata waits 2 minutes to confirm it's not transient
2. Executes `/usr/local/bin/autocoder-auto-cleanup`
3. Script kills escaped claude and Xvfb processes
4. Logs to `/var/log/autocoder-cleanup.log`
5. Sends Slack notification: "✅ AutoCoder auto-cleanup: Killed N escaped process(es)"

**Manual trigger:**
```bash
sudo /usr/local/bin/autocoder-auto-cleanup
```

## Viewing Metrics

### Netdata Dashboard
- URL: http://138.201.197.54:19999
- Navigate to: "AutoCoder" section
- Charts:
  - Escaped Processes (line chart)
  - Active Agents (line chart)
  - Feature Progress (line chart)

### API Access
```bash
# Current escaped process count
curl -s "http://localhost:19999/api/v1/data?chart=autocoder.escaped_processes&format=json&points=1"

# Active agents
curl -s "http://localhost:19999/api/v1/data?chart=autocoder.agents&format=json&points=1"

# Feature progress
curl -s "http://localhost:19999/api/v1/data?chart=autocoder.features&format=json&points=1"
```

## Configuration Files

| File | Purpose |
|------|---------|
| `/etc/netdata/health.d/autocoder.conf` | Alert definitions |
| `/etc/netdata/python.d/autocoder.conf` | Collector config |
| `/usr/libexec/netdata/python.d/autocoder.chart.py` | Custom Python collector |
| `/usr/local/bin/autocoder-auto-cleanup` | Auto-remediation script |
| `/var/log/autocoder-cleanup.log` | Cleanup event log |

## Tuning Alerts

Edit `/etc/netdata/health.d/autocoder.conf`:

```bash
sudo nano /etc/netdata/health.d/autocoder.conf
# Change thresholds, delays, etc.
sudo systemctl reload netdata
```

## Troubleshooting

### Collector not running
```bash
# Check Python collector status
sudo /usr/libexec/netdata/python.d/autocoder.chart.py debug trace

# Check Netdata logs
sudo journalctl -u netdata -f | grep autocoder
```

### Auto-cleanup not working
```bash
# Check cleanup log
sudo tail -f /var/log/autocoder-cleanup.log

# Test manually
sudo /usr/local/bin/autocoder-auto-cleanup
```

### Alerts not firing
```bash
# Check alert status
curl "http://localhost:19999/api/v1/alarms?all" | jq '.alarms.autocoder'

# Reload health config
sudo systemctl reload netdata
```

## Best Practices

1. **Monitor during development:** Keep Netdata dashboard open when running AutoCoder sessions
2. **Trust auto-cleanup:** Let it handle escaped processes automatically
3. **React to task warnings:** If you hit 400 tasks with concurrency=5, either:
   - Reduce to concurrency=4
   - Increase TasksMax to 750
4. **Review logs:** Check `/var/log/autocoder-cleanup.log` weekly to spot patterns

## Integration with AutoCoder Commands

The monitoring is **passive** - it doesn't interfere with:
- `autocoder-ui-start` / `autocoder-ui-stop`
- `autocoder-ui-status`
- Manual cleanup commands

It only **observes and alerts**. You remain in control.
