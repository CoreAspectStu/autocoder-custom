#!/usr/bin/env python3
"""
Mission Control Installation Script

Integrates Mission Control (DevLayer + Status Dashboard) with AutoCoder.

What this does:
1. Patches client.py to load Mission Control MCP server
2. Creates .env entry for MISSION_CONTROL_ENABLED
3. Validates integration

Usage:
    python custom/mission-control/install.py
    python custom/mission-control/install.py --uninstall
"""

import argparse
import sys
from pathlib import Path

# AutoCoder root
AUTOCODER_ROOT = Path(__file__).parent.parent.parent
CLIENT_PY = AUTOCODER_ROOT / "client.py"
ENV_FILE = AUTOCODER_ROOT / ".env"


def check_already_installed() -> bool:
    """Check if Mission Control is already installed."""
    if not CLIENT_PY.exists():
        print("ERROR: client.py not found!")
        return False

    content = CLIENT_PY.read_text()
    return "mission_control.integration" in content


def install():
    """Install Mission Control integration."""
    print("=== Mission Control Installation ===\n")

    # Check if already installed
    if check_already_installed():
        print("✓ Mission Control is already installed!")
        print("\nTo enable, set in .env:")
        print("  MISSION_CONTROL_ENABLED=true")
        return

    # Read client.py
    content = CLIENT_PY.read_text()

    # Find the mcp_servers dict construction (line ~274)
    marker = "# Build MCP servers config - features is always included"
    if marker not in content:
        print(f"ERROR: Could not find marker in client.py: {marker}")
        print("Manual installation required - see docs/mission-control-setup.md")
        sys.exit(1)

    # Add import at top of file (after other imports)
    import_marker = "from api.quota_budget import get_quota_budget"
    if import_marker not in content:
        print(f"ERROR: Could not find import marker in client.py")
        sys.exit(1)

    import_code = """
# Mission Control integration (optional)
from custom.mission_control.integration import add_mission_control_mcp
"""

    # Add integration call after mcp_servers is built
    integration_marker = '        mcp_servers["playwright"] = {'
    integration_code = """
    # Add Mission Control MCP server (if enabled via MISSION_CONTROL_ENABLED=true)
    mcp_servers = add_mission_control_mcp(mcp_servers, project_dir)

"""

    # Apply patches
    content = content.replace(import_marker, import_marker + import_code)
    content = content.replace(integration_marker, integration_code + "    " + integration_marker)

    # Write patched client.py
    CLIENT_PY.write_text(content)

    print("✓ Patched client.py with Mission Control integration")

    # Create/update .env
    env_content = ""
    if ENV_FILE.exists():
        env_content = ENV_FILE.read_text()

    if "MISSION_CONTROL_ENABLED" not in env_content:
        env_content += "\n# Mission Control (DevLayer + Status Dashboard)\n"
        env_content += "# Set to 'true' to enable human-in-the-loop capabilities\n"
        env_content += "MISSION_CONTROL_ENABLED=false\n"
        ENV_FILE.write_text(env_content)
        print("✓ Added MISSION_CONTROL_ENABLED to .env (disabled by default)")
    else:
        print("✓ .env already has MISSION_CONTROL_ENABLED")

    print("\n=== Installation Complete! ===\n")
    print("To enable Mission Control:")
    print("  1. Edit .env and set: MISSION_CONTROL_ENABLED=true")
    print("  2. Restart AutoCoder UI")
    print("  3. Press 'L' in UI to toggle DevLayer mode")
    print("\nDocumentation: custom/mission-control/README.md")


def uninstall():
    """Uninstall Mission Control integration."""
    print("=== Mission Control Uninstallation ===\n")

    if not check_already_installed():
        print("Mission Control is not installed.")
        return

    # Read client.py
    content = CLIENT_PY.read_text()

    # Remove import
    import_code = """
# Mission Control integration (optional)
from custom.mission_control.integration import add_mission_control_mcp
"""
    content = content.replace(import_code, "")

    # Remove integration call
    integration_code = """    # Add Mission Control MCP server (if enabled via MISSION_CONTROL_ENABLED=true)
    mcp_servers = add_mission_control_mcp(mcp_servers, project_dir)

"""
    content = content.replace(integration_code, "")

    # Write patched client.py
    CLIENT_PY.write_text(content)

    print("✓ Removed Mission Control from client.py")
    print("\nNote: .env file not modified (MISSION_CONTROL_ENABLED still present)")
    print("\n=== Uninstallation Complete! ===")


def main():
    parser = argparse.ArgumentParser(description="Mission Control installer")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall Mission Control")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    else:
        install()


if __name__ == "__main__":
    main()
