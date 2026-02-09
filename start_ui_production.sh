#!/bin/bash
# AutoCoder UI Production Launcher for systemd
# This script ensures the frontend is built before starting the server

set -e

cd "$(dirname "$0")"

echo "[AutoCoder UI] Checking if frontend build is needed..."

# Build frontend using the same logic as start_ui.py
# This ensures UI changes are reflected before starting the server
# Build frontend - use vite build directly (skip tsc for custom UAT components)
if ! (cd ui && npx vite build) > /dev/null 2>&1; then
    echo "[ERROR] Frontend build failed!"
    echo "Please run 'cd ui && npx vite build' to see errors"
    exit 1
fi

echo "[AutoCoder UI] Frontend build complete"
echo "[AutoCoder UI] Starting uvicorn server..."

# Start uvicorn directly (systemd handles restart logic)
exec /home/stu/projects/autocoder/venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8888
