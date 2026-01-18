"""
Status Router
=============

Simple endpoint to list all running dev servers across all projects.
Useful for quickly seeing what's running and on which ports.
"""

import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

# Add root to path for registry import
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from registry import list_registered_projects
from ..services.dev_server_manager import get_devserver_manager

router = APIRouter(tags=["status"])


@router.get("/api/status/devservers")
async def list_all_devservers():
    """
    List all dev servers across all registered projects.

    Returns a list of running dev servers with their URLs and ports.
    """
    projects = list_registered_projects()
    servers = []

    for name, info in projects.items():
        project_path = Path(info.get("path", ""))
        if not project_path.exists():
            continue

        manager = get_devserver_manager(name, project_path)
        await manager.healthcheck()

        if manager.status != "stopped":
            servers.append({
                "project": name,
                "status": manager.status,
                "url": manager.detected_url,
                "pid": manager.pid,
            })

    return {"servers": servers, "count": len(servers)}


@router.get("/status", response_class=HTMLResponse)
async def status_page():
    """
    Simple HTML status page showing all running dev servers.

    Access at: http://localhost:8889/status
    """
    projects = list_registered_projects()

    rows = []
    for name, info in projects.items():
        project_path = Path(info.get("path", ""))
        if not project_path.exists():
            continue

        manager = get_devserver_manager(name, project_path)
        await manager.healthcheck()

        status = manager.status
        url = manager.detected_url or "-"

        # Extract port from URL
        port = "-"
        if manager.detected_url:
            import re
            match = re.search(r':(\d+)', manager.detected_url)
            if match:
                port = match.group(1)

        # Status color
        if status == "running":
            status_badge = '<span style="color: #10b981; font-weight: bold;">● Running</span>'
        elif status == "crashed":
            status_badge = '<span style="color: #ef4444; font-weight: bold;">● Crashed</span>'
        else:
            status_badge = '<span style="color: #6b7280;">○ Stopped</span>'

        # Make URL clickable if running
        url_cell = f'<a href="{url}" target="_blank" style="color: #3b82f6;">{url}</a>' if url != "-" else "-"

        rows.append(f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-weight: 500;">{name}</td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{status_badge}</td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; font-family: monospace;">{port}</td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{url_cell}</td>
        </tr>
        """)

    table_rows = "\n".join(rows) if rows else '<tr><td colspan="4" style="padding: 20px; text-align: center; color: #6b7280;">No projects found</td></tr>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AutoCoder - Dev Servers</title>
        <meta http-equiv="refresh" content="5">
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
                <tbody>
                    {table_rows}
                </tbody>
            </table>

            <p class="refresh-note">Auto-refreshes every 5 seconds</p>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)
