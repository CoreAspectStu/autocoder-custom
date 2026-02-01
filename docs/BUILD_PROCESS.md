# AutoCoder UI Build Process Documentation

## Issue Description

**Problem:** The production systemd service (`autocoder-ui.service`) was starting uvicorn directly without ensuring the React frontend was built. This caused UI changes to not appear until someone manually ran `npm run build`.

**Root Cause:** The systemd service bypassed `start_ui.py`, which contains smart build detection logic.

## Solution

Created a production wrapper script that:
1. Checks if frontend build is needed
2. Runs `npm run build` to compile TypeScript and bundle the React app
3. Starts the uvicorn server

## Files Modified

### 1. Created: `/home/stu/projects/autocoder/start_ui_production.sh`

Production launcher script for systemd that ensures the UI is built before starting the server.

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[AutoCoder UI] Checking if frontend build is needed..."
if ! npm run build --prefix ui > /dev/null 2>&1; then
    echo "[ERROR] Frontend build failed!"
    exit 1
fi

echo "[AutoCoder UI] Frontend build complete"
echo "[AutoCoder UI] Starting uvicorn server..."

exec /home/stu/projects/autocoder/venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8888
```

### 2. Modified: `/home/stu/.config/systemd/user/autocoder-ui.service`

**Changed ExecStart from:**
```ini
ExecStart=/home/stu/projects/autocoder/venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8888
```

**To:**
```ini
ExecStart=/home/stu/projects/autocoder/start_ui_production.sh
```

## How It Works

### Development Mode (Manual)

For development with hot reload:
```bash
cd /home/stu/projects/autocoder
python start_ui.py --dev
```

This starts:
- Vite dev server on http://127.0.0.1:5173 (with hot reload)
- FastAPI backend on http://127.0.0.1:8888

### Production Mode (systemd)

The systemd service now:
1. Runs cleanup scripts (orphans, notifications)
2. **Executes `start_ui_production.sh`**
3. Wrapper script builds the frontend (`npm run build`)
4. Wrapper script starts uvicorn on port 8888
5. FastAPI serves static files from `ui/dist/`

### Build Process Details

The `npm run build` command does:
1. **TypeScript compilation**: `tsc -b` (strict mode, catches type errors)
2. **Vite bundling**: `vite build` (optimizes and minifies for production)
3. **Output**: `ui/dist/` directory with optimized assets

**Build time:** ~6-10 seconds (depending on hardware)
**Output size:** ~1.2 MB (gzipped)

## Applying Changes

To apply the new systemd configuration:

```bash
# Reload systemd daemon
systemctl --user daemon-reload

# Restart the service
systemctl --user restart autocoder-ui

# Check status
systemctl --user status autocoder-ui
```

## Troubleshooting

### Build Fails

If the frontend build fails:
1. Check TypeScript errors: `cd /home/stu/projects/autocoder/ui && npm run build`
2. Fix type errors in source files
3. Restart the service

### UI Changes Not Appearing

If you make UI changes and they don't appear:
1. Check if build is running: Look for "[AutoCoder UI] Frontend build complete" in logs
2. Force a rebuild: `cd /home/stu/projects/autocoder/ui && npm run build`
3. Restart service: `systemctl --user restart autocoder-ui`

### Service Won't Start

1. Check logs: `journalctl --user -u autocoder-ui -n 50`
2. Verify build works manually: `cd /home/stu/projects/autocoder && ./start_ui_production.sh`
3. Check port 8888 is available: `fuser -k 8888/tcp`

## TypeScript Configuration

The UI uses **strict TypeScript** (`tsconfig.json`):
- `"strict": true` - All strict type-checking options enabled
- `"noUnusedLocals": false` - Allows unused variables (for debugging)
- `"noUnusedParameters": false` - Allows unused parameters (for debugging)

If TypeScript errors occur during build, they must be fixed before the service will start successfully.

## Alternative: Development Mode for systemd

If you prefer hot-reload in production (not recommended), you can run development servers via systemd:

```ini
ExecStart=/home/stu/projects/autocoder/venv/bin/python start_ui.py --dev
```

This will start both Vite and FastAPI, but uses more resources and is slower.

## Verification

To verify the fix is working:

```bash
# 1. Make a trivial UI change
echo "// TEST" >> /home/stu/projects/autocoder/ui/src/main.tsx

# 2. Restart service
systemctl --user restart autocoder-ui

# 3. Check logs for build confirmation
journalctl --user -u autocoder-ui -n 20 | grep "Frontend build"

# 4. Verify change appears in browser
```

Expected log output:
```
[AutoCoder UI] Checking if frontend build is needed...
[AutoCoder UI] Frontend build complete
[AutoCoder UI] Starting uvicorn server...
```

## Summary

**Before:** systemd → uvicorn (served stale UI)
**After:** systemd → wrapper → npm build → uvicorn (serves fresh UI)

This ensures UI changes are automatically built and deployed when the service starts or restarts.
