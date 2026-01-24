"""
Status Router
=============

Shows all registered projects and detects if their dev servers are running
by checking if the configured port is actually listening.

Port Detection Priority:
1. AutoCoder assigned port (.autocoder/config.json) - SOURCE OF TRUTH
2. Config files (vite.config.js, package.json, etc.) - fallback
3. Framework defaults - last resort
"""

import json
import re
import socket
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

# Add root to path for registry and services import
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from registry import list_registered_projects
from server.services.project_config import get_project_config

router = APIRouter(tags=["status"])


def get_project_port(project_path: Path) -> int | None:
    """
    Get the configured dev server port for a project.

    Priority:
    1. AutoCoder assigned port (4000-4099 range) - this is what AutoCoder will use
    2. Config files (vite.config.js, package.json, etc.) - fallback for detection
    3. Framework defaults (3000 for Next.js, 5173 for Vite) - last resort

    Args:
        project_path: Path to the project directory

    Returns:
        Port number or None if no port can be determined
    """
    # PRIORITY 1: Check AutoCoder's assigned port (source of truth)
    try:
        config = get_project_config(project_path)
        assigned_port = config.get("assigned_port")
        if assigned_port is not None:
            return assigned_port
    except Exception:
        # If project_config fails, continue to fallback methods
        pass

    # PRIORITY 2: Check config files (fallback for non-AutoCoder managed servers)
    # Check vite.config.js
    vite_config = project_path / "vite.config.js"
    if vite_config.exists():
        try:
            content = vite_config.read_text()
            match = re.search(r'port:\s*(\d+)', content)
            if match:
                return int(match.group(1))
        except Exception:
            pass

    # Check vite.config.ts
    vite_config_ts = project_path / "vite.config.ts"
    if vite_config_ts.exists():
        try:
            content = vite_config_ts.read_text()
            match = re.search(r'port:\s*(\d+)', content)
            if match:
                return int(match.group(1))
        except Exception:
            pass

    # Check package.json for port in dev script
    package_json = project_path / "package.json"
    if package_json.exists():
        try:
            content = package_json.read_text()
            data = json.loads(content)
            dev_script = data.get("scripts", {}).get("dev", "")
            # Match patterns like: -p 4000, --port 4000, --port=4000
            match = re.search(r'(?:-p\s+|--port[=\s])(\d+)', dev_script)
            if match:
                return int(match.group(1))
        except Exception:
            pass

    # Default ports by framework
    if (project_path / "next.config.js").exists() or (project_path / "next.config.mjs").exists():
        return 3000  # Next.js default
    if vite_config.exists() or vite_config_ts.exists():
        return 5173  # Vite default

    return None


def is_port_listening(port: int) -> bool:
    """
    Check if something is listening on the given port.
    Uses lsof for more reliable detection, falls back to socket check.
    """
    # Method 1: Use lsof (more reliable, shows actual process)
    try:
        result = subprocess.run(
            ['lsof', '-i', f':{port}', '-sTCP:LISTEN', '-t'],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # lsof not available or timed out, fall back to socket method
        pass

    # Method 2: Socket connection check (fallback)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            result = s.connect_ex(('127.0.0.1', port))
            return result == 0
    except Exception:
        return False


def get_port_process_info(port: int) -> dict | None:
    """
    Get detailed information about the process listening on a port.
    Returns dict with pid, command, or None if no process found.
    """
    try:
        result = subprocess.run(
            ['lsof', '-i', f':{port}', '-sTCP:LISTEN', '-Fn', '-Fc'],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            info = {}
            for line in lines:
                if line.startswith('p'):
                    info['pid'] = line[1:]
                elif line.startswith('c'):
                    info['command'] = line[1:]
            return info if info else None
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return None


def get_project_health(project_path: Path) -> dict:
    """
    Get project health metrics including feature completion and test status.

    Returns:
        dict with keys: has_spec, spec_path, passing, total, percentage,
        has_features_db, last_modified, project_type
    """
    health = {
        "has_spec": False,
        "spec_path": None,
        "passing": 0,
        "total": 0,
        "percentage": 0.0,
        "has_features_db": False,
        "last_modified": None,
        "project_type": None,
    }

    # Check for app spec
    spec_path = project_path / "prompts" / "app_spec.txt"
    if spec_path.exists():
        health["has_spec"] = True
        health["spec_path"] = str(spec_path)
        try:
            health["last_modified"] = spec_path.stat().st_mtime
        except Exception:
            pass

    # Get project type from config
    try:
        config = get_project_config(project_path)
        health["project_type"] = config.get("detected_type")
    except Exception:
        pass

    # Check features database
    features_db = project_path / "features.db"
    if features_db.exists():
        health["has_features_db"] = True

        # Try to get feature stats from database
        try:
            import sqlite3
            conn = sqlite3.connect(str(features_db))
            cursor = conn.cursor()

            # Get total features
            cursor.execute("SELECT COUNT(*) FROM features")
            total = cursor.fetchone()[0]

            # Get passing features
            cursor.execute("SELECT COUNT(*) FROM features WHERE passes = 1")
            passing = cursor.fetchone()[0]

            conn.close()

            health["total"] = total
            health["passing"] = passing
            health["percentage"] = (passing / total * 100) if total > 0 else 0.0

        except Exception:
            pass

    return health


def get_agent_status(project_name: str) -> dict:
    """
    Check if agent is running for this project by looking for tmux session.

    Returns:
        dict with keys: running, session_name
    """
    try:
        session_name = f"autocoder-agent-{project_name.replace('/', '-')}"
        result = subprocess.run(
            ['tmux', 'has-session', '-t', session_name],
            capture_output=True,
            timeout=1
        )
        return {
            "running": result.returncode == 0,
            "session_name": session_name if result.returncode == 0 else None
        }
    except Exception:
        return {"running": False, "session_name": None}


@router.get("/api/status/devservers")
async def list_all_devservers():
    """
    List all registered projects with their actual running status.
    Detects servers by checking if configured port is listening.

    Enhanced with project health metrics, agent status, and quick links.
    """
    projects = list_registered_projects()
    servers = []

    for name, info in projects.items():
        project_path = Path(info.get("path", ""))
        if not project_path.exists():
            continue

        # Get dev server status
        port = get_project_port(project_path)
        is_running = port is not None and is_port_listening(port)

        # Get project health metrics
        health = get_project_health(project_path)

        # Get agent status
        agent = get_agent_status(name)

        servers.append({
            "project": name,
            "path": str(project_path),
            "status": "running" if is_running else "stopped",
            "port": port,
            "url": f"http://localhost:{port}/" if is_running and port else None,

            # Health metrics
            "has_spec": health["has_spec"],
            "spec_path": health["spec_path"],
            "project_type": health["project_type"],
            "features_total": health["total"],
            "features_passing": health["passing"],
            "completion_percentage": health["percentage"],
            "has_features_db": health["has_features_db"],

            # Agent status
            "agent_running": agent["running"],
            "agent_session": agent["session_name"],
        })

    # Calculate summary stats
    running_count = sum(1 for s in servers if s["status"] == "running")
    agent_count = sum(1 for s in servers if s["agent_running"])
    idle_count = len(servers) - running_count - agent_count

    return {
        "servers": servers,
        "count": len(servers),
        "summary": {
            "running": running_count,
            "agents": agent_count,
            "idle": idle_count,
        }
    }


@router.get("/api/status/spec/{project_name}")
async def get_project_spec(project_name: str):
    """
    Get the spec content and project details for a project.
    """
    projects = list_registered_projects()
    if project_name not in projects:
        return {"error": "Project not found"}, 404

    project_path = Path(projects[project_name].get("path", ""))
    if not project_path.exists():
        return {"error": "Project path does not exist"}, 404

    # Get project health and config
    health = get_project_health(project_path)
    config = get_project_config(project_path)

    # Read spec content if exists
    spec_content = None
    if health["has_spec"]:
        try:
            spec_content = Path(health["spec_path"]).read_text()
        except Exception:
            spec_content = "Error reading spec file"

    return {
        "project": project_name,
        "path": str(project_path),
        "has_spec": health["has_spec"],
        "spec_content": spec_content,
        "project_type": health["project_type"],
        "assigned_port": config.get("assigned_port"),
        "features_total": health["total"],
        "features_passing": health["passing"],
        "completion_percentage": health["percentage"],
    }


@router.get("/status", response_class=HTMLResponse)
async def status_page():
    """
    Status page showing all registered projects and their dev server status.
    """
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoCoder - Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f7fa;
            color: #2d3748;
            line-height: 1.6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px;
        }

        /* Header */
        header {
            margin-bottom: 32px;
        }

        h1 {
            font-size: 28px;
            font-weight: 700;
            color: #1a202c;
            margin-bottom: 8px;
        }

        .subtitle {
            color: #718096;
            font-size: 14px;
        }

        /* Summary Cards */
        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }

        .summary-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        .summary-card .label {
            font-size: 13px;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }

        .summary-card .value {
            font-size: 32px;
            font-weight: 700;
            color: #2d3748;
        }

        .summary-card.running .value { color: #10b981; }
        .summary-card.agents .value { color: #3b82f6; }
        .summary-card.idle .value { color: #9ca3af; }

        /* Port Range Info */
        .port-info {
            background: #eff6ff;
            border-left: 4px solid #3b82f6;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 24px;
            font-size: 14px;
        }

        .port-info strong {
            color: #1e40af;
        }

        /* Project Cards */
        .projects {
            display: grid;
            gap: 20px;
        }

        .project-card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow: hidden;
            transition: all 0.2s;
        }

        .project-card:hover {
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .project-header {
            padding: 20px;
            border-bottom: 1px solid #e2e8f0;
            cursor: pointer;
            user-select: none;
        }

        .project-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }

        .project-name {
            font-size: 18px;
            font-weight: 600;
            color: #1a202c;
        }

        .status-badges {
            display: flex;
            gap: 8px;
        }

        .badge {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }

        .badge.running { background: #d1fae5; color: #065f46; }
        .badge.stopped { background: #f3f4f6; color: #6b7280; }
        .badge.agent-active { background: #dbeafe; color: #1e40af; }

        .project-meta {
            display: flex;
            gap: 16px;
            font-size: 13px;
            color: #718096;
            flex-wrap: wrap;
        }

        .project-meta-item {
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .project-type {
            font-family: 'Monaco', 'Menlo', monospace;
            background: #f1f5f9;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
        }

        /* Project Details (Expandable) */
        .project-details {
            display: none;
            padding: 20px;
            background: #f9fafb;
            border-top: 1px solid #e2e8f0;
        }

        .project-details.expanded {
            display: block;
        }

        .details-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .detail-section h3 {
            font-size: 14px;
            font-weight: 600;
            color: #1a202c;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .detail-item {
            margin-bottom: 8px;
            font-size: 14px;
        }

        .detail-item strong {
            color: #4b5563;
            min-width: 120px;
            display: inline-block;
        }

        .progress-bar-container {
            background: #e2e8f0;
            height: 8px;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }

        .progress-bar {
            background: #10b981;
            height: 100%;
            transition: width 0.3s;
        }

        .progress-text {
            font-size: 12px;
            color: #718096;
            margin-top: 4px;
        }

        /* Quick Actions */
        .quick-actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .btn-primary {
            background: #3b82f6;
            color: white;
        }

        .btn-primary:hover {
            background: #2563eb;
        }

        .btn-secondary {
            background: #e5e7eb;
            color: #374151;
        }

        .btn-secondary:hover {
            background: #d1d5db;
        }

        .btn-success {
            background: #10b981;
            color: white;
        }

        .btn-success:hover {
            background: #059669;
        }

        /* Health Indicator */
        .health-indicator {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            font-weight: 500;
        }

        .health-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }

        .health-dot.green { background: #10b981; }
        .health-dot.yellow { background: #f59e0b; }
        .health-dot.red { background: #ef4444; }
        .health-dot.gray { background: #9ca3af; }

        /* Footer */
        footer {
            margin-top: 40px;
            padding: 20px 0;
            text-align: center;
            color: #9ca3af;
            font-size: 12px;
        }

        /* Expand Icon */
        .expand-icon {
            transition: transform 0.2s;
        }

        .project-card.expanded .expand-icon {
            transform: rotate(180deg);
        }

        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #9ca3af;
        }

        .empty-state-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 1000;
            overflow-y: auto;
        }

        .modal.active {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .modal-content {
            background: white;
            border-radius: 12px;
            max-width: 900px;
            width: 100%;
            max-height: 90vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04);
        }

        .modal-header {
            padding: 24px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .modal-header h2 {
            font-size: 20px;
            font-weight: 600;
            color: #1a202c;
            margin: 0;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 24px;
            color: #9ca3af;
            cursor: pointer;
            padding: 0;
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 6px;
            transition: all 0.2s;
        }

        .modal-close:hover {
            background: #f3f4f6;
            color: #1a202c;
        }

        .modal-body {
            padding: 24px;
            overflow-y: auto;
        }

        .spec-content {
            background: #f9fafb;
            padding: 16px;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
            max-height: 60vh;
            overflow-y: auto;
        }

        .project-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }

        .info-item {
            background: #f9fafb;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid #e2e8f0;
        }

        .info-item strong {
            display: block;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #718096;
            margin-bottom: 4px;
        }

        .info-item span {
            font-size: 14px;
            color: #2d3748;
        }

        .loading {
            text-align: center;
            padding: 40px;
            color: #9ca3af;
        }

        .error {
            background: #fef2f2;
            border: 1px solid #fca5a5;
            color: #991b1b;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 16px;
        }

        /* CUSTOM: Auth Settings Panel */
        .auth-settings {
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 32px;
        }

        .auth-settings h2 {
            font-size: 18px;
            font-weight: 600;
            color: #1a202c;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .auth-form {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .form-group label {
            font-size: 14px;
            font-weight: 500;
            color: #374151;
        }

        .radio-group {
            display: flex;
            gap: 24px;
        }

        .radio-option {
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
        }

        .radio-option input[type="radio"] {
            width: 18px;
            height: 18px;
            cursor: pointer;
        }

        .radio-option label {
            cursor: pointer;
            margin: 0;
        }

        .form-group input[type="password"],
        .form-group input[type="text"] {
            padding: 10px 12px;
            border: 1px solid #d1d5db;
            border-radius: 6px;
            font-size: 14px;
            font-family: 'Monaco', 'Menlo', monospace;
            transition: border-color 0.2s;
        }

        .form-group input:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }

        .form-group input:disabled {
            background: #f3f4f6;
            cursor: not-allowed;
        }

        .auth-actions {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .btn {
            padding: 10px 20px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
        }

        .btn-primary {
            background: #3b82f6;
            color: white;
        }

        .btn-primary:hover:not(:disabled) {
            background: #2563eb;
        }

        .btn-primary:disabled {
            background: #9ca3af;
            cursor: not-allowed;
        }

        .auth-status {
            font-size: 13px;
            padding: 8px 12px;
            border-radius: 6px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .auth-status.success {
            background: #d1fae5;
            color: #065f46;
        }

        .auth-status.info {
            background: #dbeafe;
            color: #1e40af;
        }

        .auth-status.error {
            background: #fee2e2;
            color: #991b1b;
        }

        .hint {
            font-size: 12px;
            color: #6b7280;
            margin-top: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎯 AutoCoder Dashboard</h1>
            <p class="subtitle">Manage all your AutoCoder projects and dev servers</p>
        </header>

        <!-- CUSTOM: Authentication Settings -->
        <div class="auth-settings">
            <h2>🔐 Authentication Settings</h2>
            <div class="auth-form">
                <div class="form-group">
                    <label>Authentication Method <span id="current-auth-badge" class="auth-status info" style="display: none; margin-left: 12px; font-size: 11px; padding: 4px 8px;"></span></label>
                    <div class="radio-group">
                        <div class="radio-option">
                            <input type="radio" id="auth-claude" name="auth-method" value="claude_login">
                            <label for="auth-claude">Claude Login (claude login)</label>
                        </div>
                        <div class="radio-option">
                            <input type="radio" id="auth-api" name="auth-method" value="api_key">
                            <label for="auth-api">API Key (Anthropic API)</label>
                        </div>
                    </div>
                </div>

                <div class="form-group" id="api-key-group" style="display: none;">
                    <label for="api-key">Anthropic API Key</label>
                    <input type="password" id="api-key" placeholder="sk-ant-api03-...">
                    <div class="hint">Your API key will be saved to .env file. Get one from https://console.anthropic.com/</div>
                </div>

                <div class="auth-actions">
                    <button class="btn btn-primary" id="save-auth">Save Authentication Settings</button>
                    <span class="auth-status" id="auth-status" style="display: none;"></span>
                </div>
            </div>
        </div>

        <!-- Summary Stats -->
        <div class="summary" id="summary">
            <div class="summary-card running">
                <div class="label">Dev Servers Running</div>
                <div class="value" id="running-count">0</div>
            </div>
            <div class="summary-card agents">
                <div class="label">Active Agents</div>
                <div class="value" id="agents-count">0</div>
            </div>
            <div class="summary-card idle">
                <div class="label">Idle Projects</div>
                <div class="value" id="idle-count">0</div>
            </div>
            <div class="summary-card">
                <div class="label">Total Projects</div>
                <div class="value" id="total-count">0</div>
            </div>
        </div>

        <!-- Port Range Info -->
        <div class="port-info">
            <strong>📡 Port Convention:</strong> Dev servers auto-assigned to <strong>4000-4099</strong> range (SSH tunnel friendly).
            Local development uses 3000-3999.
        </div>

        <!-- Projects -->
        <div class="projects" id="projects"></div>

        <footer>
            Auto-refreshes every 5 seconds • Last updated: <span id="last-update">Never</span>
        </footer>
    </div>

    <!-- Spec Modal -->
    <div class="modal" id="specModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modalTitle">Project Details</h2>
                <button class="modal-close" onclick="closeSpecModal()">&times;</button>
            </div>
            <div class="modal-body" id="modalBody">
                <div class="loading">Loading...</div>
            </div>
        </div>
    </div>

    <script>
        let lastDataStr = null;

        // CUSTOM: Authentication Settings
        // Load current auth settings on page load
        async function loadAuthSettings() {
            try {
                console.log('[AUTH] Loading settings from API...');
                const response = await fetch('/api/settings');
                const data = await response.json();
                console.log('[AUTH] Received settings:', data);

                // Set radio button based on current method
                const badge = document.getElementById('current-auth-badge');
                const apiRadio = document.getElementById('auth-api');
                const claudeRadio = document.getElementById('auth-claude');
                const apiKeyGroup = document.getElementById('api-key-group');

                console.log('[AUTH] Elements found:', {
                    badge: !!badge,
                    apiRadio: !!apiRadio,
                    claudeRadio: !!claudeRadio,
                    apiKeyGroup: !!apiKeyGroup
                });
                console.log('[AUTH] Auth method:', data.auth_method);

                if (!apiRadio || !claudeRadio || !apiKeyGroup) {
                    console.error('[AUTH] Missing required DOM elements!');
                    return;
                }

                if (data.auth_method === 'api_key') {
                    console.log('[AUTH] Setting API Key mode');
                    apiRadio.checked = true;
                    claudeRadio.checked = false;
                    apiKeyGroup.style.display = 'block';
                    if (data.api_key_configured) {
                        document.getElementById('api-key').placeholder = '***************** (configured)';
                        badge.textContent = 'Using API Key';
                        badge.className = 'auth-status success';
                        badge.style.display = 'inline-flex';
                    }
                } else {
                    console.log('[AUTH] Setting Claude Login mode');
                    claudeRadio.checked = true;
                    apiRadio.checked = false;
                    apiKeyGroup.style.display = 'none';
                    badge.textContent = 'Using Claude Login';
                    badge.className = 'auth-status info';
                    badge.style.display = 'inline-flex';
                }
                console.log('[AUTH] Settings loaded successfully');
            } catch (error) {
                console.error('[AUTH] Failed to load auth settings:', error);
            }
        }

        // Handle auth method radio change
        document.addEventListener('DOMContentLoaded', () => {
            // Wait a bit for DOM to be fully ready
            setTimeout(() => {
                loadAuthSettings();
            }, 100);

            // Toggle API key field based on selection
            document.querySelectorAll('input[name="auth-method"]').forEach(radio => {
                radio.addEventListener('change', (e) => {
                    const apiKeyGroup = document.getElementById('api-key-group');
                    if (e.target.value === 'api_key') {
                        apiKeyGroup.style.display = 'block';
                    } else {
                        apiKeyGroup.style.display = 'none';
                    }
                });
            });

            // Save auth settings
            document.getElementById('save-auth').addEventListener('click', async () => {
                const authMethod = document.querySelector('input[name="auth-method"]:checked').value;
                const apiKey = document.getElementById('api-key').value;
                const statusEl = document.getElementById('auth-status');
                const saveBtn = document.getElementById('save-auth');

                // Validate API key if using API key method
                if (authMethod === 'api_key' && !apiKey) {
                    statusEl.className = 'auth-status error';
                    statusEl.textContent = 'ERROR: API key is required';
                    statusEl.style.display = 'inline-flex';
                    setTimeout(() => statusEl.style.display = 'none', 3000);
                    return;
                }

                // Disable button during save
                saveBtn.disabled = true;
                statusEl.className = 'auth-status info';
                statusEl.textContent = 'Saving...';
                statusEl.style.display = 'inline-flex';

                try {
                    const payload = { auth_method: authMethod };
                    if (authMethod === 'api_key' && apiKey) {
                        payload.api_key = apiKey;
                    }

                    const response = await fetch('/api/settings', {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });

                    if (!response.ok) {
                        const error = await response.json();
                        throw new Error(error.detail || 'Failed to save settings');
                    }

                    const data = await response.json();

                    // Show success message
                    statusEl.className = 'auth-status success';
                    statusEl.textContent = 'SUCCESS: Settings saved! Restart agents for changes to take effect.';

                    // Update current auth badge
                    const badge = document.getElementById('current-auth-badge');
                    if (authMethod === 'api_key') {
                        badge.textContent = 'Using API Key';
                        badge.className = 'auth-status success';
                        badge.style.display = 'inline-flex';
                        // Clear API key field if it was set
                        document.getElementById('api-key').value = '';
                        document.getElementById('api-key').placeholder = '***************** (configured)';
                    } else {
                        badge.textContent = 'Using Claude Login';
                        badge.className = 'auth-status info';
                        badge.style.display = 'inline-flex';
                    }

                    setTimeout(() => statusEl.style.display = 'none', 5000);
                } catch (error) {
                    statusEl.className = 'auth-status error';
                    statusEl.textContent = `ERROR: ${error.message}`;
                    setTimeout(() => statusEl.style.display = 'none', 5000);
                } finally {
                    saveBtn.disabled = false;
                }
            });
        });

        // Format timestamp
        function formatTime(timestamp) {
            const date = new Date(timestamp);
            return date.toLocaleTimeString();
        }

        // Get health status
        function getHealthStatus(server) {
            if (!server.has_features_db) return { color: 'gray', text: 'No features' };
            if (server.features_total === 0) return { color: 'gray', text: 'Empty' };
            if (server.completion_percentage === 100) return { color: 'green', text: 'Complete' };
            if (server.completion_percentage >= 50) return { color: 'yellow', text: 'In Progress' };
            return { color: 'red', text: 'Started' };
        }

        // Render project card
        function renderProject(server) {
            const health = getHealthStatus(server);
            const hasUrl = server.status === 'running' && server.url;

            return `
                <div class="project-card" data-project="${server.project}" onclick="toggleExpand(this)">
                    <div class="project-header">
                        <div class="project-title-row">
                            <div class="project-name">${server.project}</div>
                            <div class="status-badges">
                                ${server.status === 'running'
                                    ? '<span class="badge running">🟢 Running</span>'
                                    : '<span class="badge stopped">⚪ Stopped</span>'}
                                ${server.agent_running
                                    ? '<span class="badge agent-active">🤖 Agent</span>'
                                    : ''}
                                <span class="expand-icon">v</span>
                            </div>
                        </div>
                        <div class="project-meta">
                            ${server.project_type ? `<span class="project-type">${server.project_type}</span>` : ''}
                            ${server.port ? `<span class="project-meta-item">Port: ${server.port}</span>` : ''}
                            ${server.has_spec ? `<span class="project-meta-item">Has Spec</span>` : ''}
                            <span class="project-meta-item">
                                <span class="health-dot ${health.color}"></span> ${health.text}
                            </span>
                        </div>
                    </div>

                    <div class="project-details">
                        <div class="details-grid">
                            <div class="detail-section">
                                <h3>Features Progress</h3>
                                ${server.has_features_db ? `
                                    <div class="detail-item">
                                        <strong>Passing:</strong> ${server.features_passing} / ${server.features_total}
                                    </div>
                                    <div class="progress-bar-container">
                                        <div class="progress-bar" style="width: ${server.completion_percentage}%"></div>
                                    </div>
                                    <div class="progress-text">${server.completion_percentage.toFixed(1)}% Complete</div>
                                ` : `
                                    <div class="detail-item" style="color: #9ca3af;">No features database found</div>
                                `}
                            </div>

                            <div class="detail-section">
                                <h3>Configuration</h3>
                                <div class="detail-item"><strong>Project Type:</strong> ${server.project_type || 'Unknown'}</div>
                                <div class="detail-item">
                                    <strong>Port:</strong>
                                    <input type="number"
                                           id="port-${server.project}"
                                           value="${server.port || 4000}"
                                           min="4000"
                                           max="4099"
                                           style="width: 70px; padding: 4px 8px; margin: 0 8px; border: 1px solid #d1d5db; border-radius: 4px;"
                                           onclick="event.stopPropagation()">
                                    <button class="btn btn-secondary"
                                            onclick="event.stopPropagation(); changePort('${server.project}')"
                                            style="padding: 4px 12px; font-size: 12px;">Change</button>
                                </div>
                                <div class="detail-item"><strong>Path:</strong> <code style="font-size: 11px; word-break: break-all;">${server.path}</code></div>
                            </div>

                            <div class="detail-section">
                                <h3>🎮 Dev Server Controls</h3>
                                <div class="quick-actions">
                                    ${server.status === 'stopped'
                                        ? `<button class="btn btn-success" onclick="event.stopPropagation(); startDevServer('${server.project}')">▶ Start Server</button>`
                                        : `<button class="btn" style="background: #ef4444; color: white;" onclick="event.stopPropagation(); stopDevServer('${server.project}')">⏹ Stop Server</button>`}
                                    ${hasUrl
                                        ? `<a href="${server.url}" target="_blank" class="btn btn-primary" onclick="event.stopPropagation()">🌐 Open App</a>`
                                        : ''}
                                </div>
                            </div>

                            <div class="detail-section">
                                <h3>🔗 Other Actions</h3>
                                <div class="quick-actions">
                                    ${server.has_spec
                                        ? `<button class="btn btn-primary" onclick="event.stopPropagation(); viewSpec('${server.project}')">📄 View Spec</button>`
                                        : ''}
                                    ${server.agent_running
                                        ? `<button class="btn btn-secondary" onclick="event.stopPropagation(); viewLogs('${server.project}')">🪵 View Logs</button>`
                                        : ''}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }

        // Toggle card expansion
        function toggleExpand(card) {
            card.classList.toggle('expanded');
            const details = card.querySelector('.project-details');
            details.classList.toggle('expanded');
        }

        // Actions
        async function viewSpec(project) {
            const modal = document.getElementById('specModal');
            const modalBody = document.getElementById('modalBody');
            const modalTitle = document.getElementById('modalTitle');

            // Show modal with loading state
            modal.classList.add('active');
            modalBody.innerHTML = '<div class="loading">Loading...</div>';
            modalTitle.textContent = `${project} - Details`;

            try {
                const resp = await fetch(`/api/status/spec/${encodeURIComponent(project)}`);
                const data = await resp.json();

                if (data.error) {
                    modalBody.innerHTML = `<div class="error">Error: ${data.error}</div>`;
                    return;
                }

                // Build project info section
                let html = '<div class="project-info">';
                html += `<div class="info-item"><strong>Project Type</strong><span>${data.project_type || 'Unknown'}</span></div>`;
                html += `<div class="info-item"><strong>Assigned Port</strong><span>${data.assigned_port || 'Not assigned'}</span></div>`;
                html += `<div class="info-item"><strong>Features</strong><span>${data.features_passing} / ${data.features_total} passing</span></div>`;
                html += `<div class="info-item"><strong>Completion</strong><span>${data.completion_percentage.toFixed(1)}%</span></div>`;
                html += '</div>';

                // Add spec content if exists
                if (data.has_spec && data.spec_content) {
                    html += '<h3 style="margin-bottom: 12px; font-size: 14px; color: #718096; text-transform: uppercase; letter-spacing: 0.5px;">App Specification</h3>';
                    html += `<div class="spec-content">${formatSpecContent(data.spec_content)}</div>`;
                } else {
                    html += '<div class="error">No spec file found (prompts/app_spec.txt)</div>';
                }

                modalBody.innerHTML = html;
            } catch (e) {
                modalBody.innerHTML = `<div class="error">Failed to load spec: ${e.message}</div>`;
            }
        }

        function formatSpecContent(xmlContent) {
            // Parse XML-like spec content into readable format with headings
            const parser = new DOMParser();
            const doc = parser.parseFromString(`<root>${xmlContent}</root>`, 'text/xml');

            // Check for parsing errors
            const parseError = doc.querySelector('parsererror');
            if (parseError) {
                // Fallback to plain text if XML parsing fails
                return `<pre style="white-space: pre-wrap; margin: 0;">${escapeHtml(xmlContent)}</pre>`;
            }

            function getDirectTextContent(node) {
                // Get only the direct text content, not from child elements
                let text = '';
                for (const child of node.childNodes) {
                    if (child.nodeType === Node.TEXT_NODE) {
                        text += child.textContent;
                    }
                }
                return text.trim();
            }

            function processNode(node, level = 0) {
                let html = '';
                const indent = level * 24; // 24px per level

                Array.from(node.children).forEach(child => {
                    const tagName = child.tagName;
                    const hasChildren = child.children.length > 0;
                    const directText = getDirectTextContent(child);

                    // Get attributes if any
                    const attrs = Array.from(child.attributes);

                    // Convert tag name to readable heading (e.g., "project_name" -> "Project Name")
                    let heading = tagName
                        .split('_')
                        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                        .join(' ');

                    // Add attributes to heading if present
                    if (attrs.length > 0) {
                        const attrText = attrs.map(attr => `${attr.name}: ${attr.value}`).join(', ');
                        heading += ` <span style="color: #6b7280; font-weight: 400; font-size: 0.9em;">(${escapeHtml(attrText)})</span>`;
                    }

                    if (hasChildren) {
                        // Tag with children - render as section heading
                        const headingSize = level === 0 ? 18 : (level === 1 ? 16 : 14);
                        const headingWeight = level === 0 ? 700 : 600;
                        const headingColor = level === 0 ? '#1a202c' : '#2d3748';
                        const marginTop = level === 0 ? 20 : 16;
                        const marginBottom = level === 0 ? 12 : 8;

                        html += `<div style="margin-left: ${indent}px; margin-top: ${marginTop}px; margin-bottom: ${marginBottom}px;">`;
                        html += `<div style="font-size: ${headingSize}px; font-weight: ${headingWeight}; color: ${headingColor}; margin-bottom: 8px;">${heading}</div>`;

                        // Add direct text content if any (before children)
                        if (directText) {
                            const lines = directText.split('\\n').map(l => l.trim()).filter(l => l);
                            if (lines.length > 0) {
                                html += `<div style="margin-left: ${indent + 16}px; margin-bottom: 12px; font-size: 13px; color: #4b5563; line-height: 1.8;">`;
                                lines.forEach(line => {
                                    html += `<div style="margin-bottom: 2px;">${escapeHtml(line)}</div>`;
                                });
                                html += '</div>';
                            }
                        }

                        html += processNode(child, level + 1);
                        html += '</div>';
                    } else if (directText) {
                        // Tag with only text content
                        const lines = directText.split('\\n').map(l => l.trim()).filter(l => l);

                        if (lines.length > 1 || (lines[0] && lines[0].startsWith('-'))) {
                            // Multi-line or bullet list - render as block
                            html += `<div style="margin-left: ${indent}px; margin-bottom: 12px;">`;
                            html += `<div style="font-size: 14px; font-weight: 600; color: #2d3748; margin-bottom: 6px;">${heading}</div>`;
                            html += `<div style="margin-left: 16px; font-size: 13px; color: #4b5563; line-height: 1.8;">`;
                            lines.forEach(line => {
                                html += `<div style="margin-bottom: 2px;">${escapeHtml(line)}</div>`;
                            });
                            html += '</div></div>';
                        } else if (lines.length === 1) {
                            // Single line - render inline
                            html += `<div style="margin-left: ${indent}px; margin-bottom: 8px;">`;
                            html += `<span style="font-size: 13px; font-weight: 600; color: #4b5563;">${heading}:</span> `;
                            html += `<span style="font-size: 13px; color: #6b7280;">${escapeHtml(lines[0])}</span>`;
                            html += '</div>';
                        }
                    }
                });

                return html;
            }

            return processNode(doc.documentElement);
        }

        function closeSpecModal() {
            document.getElementById('specModal').classList.remove('active');
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Close modal on background click
        document.getElementById('specModal').addEventListener('click', function(e) {
            if (e.target === this) {
                closeSpecModal();
            }
        });

        function viewLogs(project) {
            alert(`View logs for ${project}\n\nRun: ./remote-start.sh logs agent-${project.replace('/', '-')}`);
        }

        // Dev server control functions
        async function startDevServer(project) {
            try {
                const response = await fetch(`/api/projects/${encodeURIComponent(project)}/devserver/start`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                });

                const data = await response.json();

                if (!response.ok) {
                    alert(`Failed to start server: ${data.detail || data.message || 'Unknown error'}`);
                    return;
                }

                if (data.success) {
                    alert(`✅ Server started successfully!\n\nProject: ${project}\nStatus: ${data.status}`);
                    refresh(); // Refresh to show new status
                } else {
                    alert(`⚠️ ${data.message || 'Failed to start server'}`);
                }
            } catch (error) {
                alert(`❌ Error starting server: ${error.message}`);
            }
        }

        async function stopDevServer(project) {
            if (!confirm(`Stop dev server for ${project}?`)) {
                return;
            }

            try {
                const response = await fetch(`/api/projects/${encodeURIComponent(project)}/devserver/stop`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'}
                });

                const data = await response.json();

                if (!response.ok) {
                    alert(`Failed to stop server: ${data.detail || data.message || 'Unknown error'}`);
                    return;
                }

                if (data.success) {
                    alert(`✅ Server stopped successfully!\n\nProject: ${project}`);
                    refresh(); // Refresh to show new status
                } else {
                    alert(`⚠️ ${data.message || 'Failed to stop server'}`);
                }
            } catch (error) {
                alert(`❌ Error stopping server: ${error.message}`);
            }
        }

        async function changePort(project) {
            const inputEl = document.getElementById(`port-${project}`);
            const newPort = parseInt(inputEl.value);

            if (!newPort || newPort < 4000 || newPort > 4099) {
                alert('Port must be between 4000 and 4099');
                return;
            }

            if (!confirm(`Change port for ${project} to ${newPort}?\n\nNote: You may need to restart the dev server for the change to take effect.`)) {
                return;
            }

            try {
                const response = await fetch(`/api/projects/${encodeURIComponent(project)}/devserver/config`, {
                    method: 'PATCH',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ assigned_port: newPort })
                });

                const data = await response.json();

                if (!response.ok) {
                    alert(`Failed to change port: ${data.detail || 'Unknown error'}`);
                    return;
                }

                alert(`✅ Port changed successfully!\n\nProject: ${project}\nNew Port: ${data.assigned_port}\n\nThe dev command will now use this port.`);
                refresh(); // Refresh to show new port
            } catch (error) {
                alert(`❌ Error changing port: ${error.message}`);
            }
        }

        // Fetch and render data
        async function refresh() {
            try {
                const resp = await fetch('/api/status/devservers');
                const data = await resp.json();

                // Check if data changed
                const dataStr = JSON.stringify(data);
                if (dataStr === lastDataStr) return;
                lastDataStr = dataStr;

                // Update summary
                document.getElementById('running-count').textContent = data.summary.running;
                document.getElementById('agents-count').textContent = data.summary.agents;
                document.getElementById('idle-count').textContent = data.summary.idle;
                document.getElementById('total-count').textContent = data.count;

                // Update projects
                const projectsContainer = document.getElementById('projects');
                if (data.servers.length === 0) {
                    projectsContainer.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">📂</div>
                            <p>No projects registered yet</p>
                        </div>
                    `;
                } else {
                    projectsContainer.innerHTML = data.servers
                        .map(server => renderProject(server))
                        .join('');
                }

                // Update timestamp
                document.getElementById('last-update').textContent = formatTime(Date.now());

            } catch (e) {
                console.error('Refresh failed:', e);
            }
        }

        // Initial load
        refresh();
        setInterval(refresh, 5000);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html)
