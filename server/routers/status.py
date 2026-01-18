"""
Status Router
=============

Shows all registered projects and detects if their dev servers are running
by checking if the configured port is actually listening.
"""

import json
import re
import socket
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

# Add root to path for registry import
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from registry import list_registered_projects

router = APIRouter(tags=["status"])


def get_project_port(project_path: Path) -> int | None:
    """
    Get the configured dev server port from project config files.
    Checks vite.config.js, next.config.js, and package.json.
    """
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
    """Check if something is listening on the given port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            result = s.connect_ex(('127.0.0.1', port))
            return result == 0
    except Exception:
        return False


@router.get("/api/status/devservers")
async def list_all_devservers():
    """
    List all registered projects with their actual running status.
    Detects servers by checking if configured port is listening.
    """
    projects = list_registered_projects()
    servers = []

    for name, info in projects.items():
        project_path = Path(info.get("path", ""))
        if not project_path.exists():
            continue

        port = get_project_port(project_path)
        is_running = port is not None and is_port_listening(port)

        servers.append({
            "project": name,
            "status": "running" if is_running else "stopped",
            "port": port,
            "url": f"http://localhost:{port}/" if is_running and port else None,
        })

    return {"servers": servers, "count": len(servers)}


@router.get("/status", response_class=HTMLResponse)
async def status_page():
    """
    Status page showing all registered projects and their dev server status.
    """
    projects = list_registered_projects()

    rows = []
    for name, info in projects.items():
        project_path = Path(info.get("path", ""))
        if not project_path.exists():
            continue

        port = get_project_port(project_path)
        is_running = port is not None and is_port_listening(port)

        port_display = str(port) if port else "-"

        if is_running:
            status_badge = '<span class="running">● Running</span>'
            url = f"http://localhost:{port}/"
            url_cell = f'<a href="{url}" target="_blank">{url}</a>'
        else:
            status_badge = '<span class="stopped">○ Stopped</span>'
            url_cell = "-"

        rows.append(f"""
        <tr data-project="{name}">
            <td class="name">{name}</td>
            <td class="status">{status_badge}</td>
            <td class="port">{port_display}</td>
            <td class="url">{url_cell}</td>
        </tr>
        """)

    table_rows = "\n".join(rows) if rows else '<tr><td colspan="4" class="empty">No projects registered</td></tr>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AutoCoder - Dev Servers</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #f9fafb;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
            }}
            h1 {{
                color: #111827;
                font-size: 24px;
                margin-bottom: 8px;
            }}
            .subtitle {{
                color: #6b7280;
                font-size: 14px;
                margin-bottom: 24px;
            }}
            table {{
                width: 100%;
                background: white;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                border-collapse: collapse;
            }}
            th {{
                text-align: left;
                padding: 12px;
                background: #f9fafb;
                border-bottom: 2px solid #e5e7eb;
                font-weight: 600;
                color: #374151;
            }}
            td {{
                padding: 12px;
                border-bottom: 1px solid #e5e7eb;
            }}
            td.name {{ font-weight: 500; }}
            td.port {{ font-family: monospace; }}
            td.empty {{ text-align: center; color: #6b7280; padding: 20px; }}
            a {{ color: #3b82f6; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .running {{ color: #10b981; font-weight: bold; }}
            .stopped {{ color: #6b7280; }}
            .refresh-note {{
                margin-top: 16px;
                font-size: 12px;
                color: #9ca3af;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Dev Servers</h1>
            <p class="subtitle">All registered AutoCoder projects and their dev server status</p>

            <table>
                <thead>
                    <tr>
                        <th>Project</th>
                        <th>Status</th>
                        <th>Port</th>
                        <th>URL</th>
                    </tr>
                </thead>
                <tbody id="servers">
                    {table_rows}
                </tbody>
            </table>

            <p class="refresh-note">Auto-refreshes every 5 seconds</p>
        </div>
        <script>
            let lastData = null;

            async function refresh() {{
                try {{
                    const resp = await fetch('/api/status/devservers');
                    const data = await resp.json();

                    // Only update if data changed (prevents flashing)
                    const dataStr = JSON.stringify(data);
                    if (dataStr === lastData) return;
                    lastData = dataStr;

                    const tbody = document.getElementById('servers');

                    if (data.servers.length === 0) {{
                        tbody.innerHTML = '<tr><td colspan="4" class="empty">No projects registered</td></tr>';
                        return;
                    }}

                    tbody.innerHTML = data.servers.map(s => {{
                        const statusClass = s.status === 'running' ? 'running' : 'stopped';
                        const statusIcon = s.status === 'running' ? '●' : '○';
                        const statusText = s.status.charAt(0).toUpperCase() + s.status.slice(1);
                        const portDisplay = s.port || '-';
                        const urlCell = s.url ? `<a href="${{s.url}}" target="_blank">${{s.url}}</a>` : '-';

                        return `<tr data-project="${{s.project}}">
                            <td class="name">${{s.project}}</td>
                            <td class="status"><span class="${{statusClass}}">${{statusIcon}} ${{statusText}}</span></td>
                            <td class="port">${{portDisplay}}</td>
                            <td class="url">${{urlCell}}</td>
                        </tr>`;
                    }}).join('');
                }} catch (e) {{
                    console.error('Refresh failed:', e);
                }}
            }}

            // Initial refresh after short delay
            setTimeout(refresh, 500);
            setInterval(refresh, 5000);
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html)
