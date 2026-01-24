#!/usr/bin/env python3
"""
Check if running inside systemd service with resource guardrails.
Exits with error if not running in autocoder-ui.service cgroup.
"""
import os
import sys
from pathlib import Path

def check_systemd_cgroup():
    """Check if we're running in the autocoder-ui.service cgroup."""
    # Check cgroup v2 (modern systems)
    try:
        cgroup_path = Path("/proc/self/cgroup")
        if cgroup_path.exists():
            cgroup_content = cgroup_path.read_text()
            if "autocoder-ui.service" in cgroup_content:
                return True
    except Exception:
        pass
    
    # Fallback: Check for environment variable set by systemd
    # We'll set this in the service file
    if os.environ.get("AUTOCODER_SYSTEMD_SERVICE") == "1":
        return True
    
    return False

def main():
    if not check_systemd_cgroup():
        print("=" * 70, file=sys.stderr)
        print("ERROR: AutoCoder must run inside systemd service!", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print()
        print("AutoCoder requires resource guardrails (CPU, memory, process limits).", file=sys.stderr)
        print("You tried to run it manually without these protections.", file=sys.stderr)
        print()
        print("To start AutoCoder properly:", file=sys.stderr)
        print("  systemctl --user start autocoder-ui.service", file=sys.stderr)
        print()
        print("Or use the convenience command:", file=sys.stderr)
        print("  autocoder-ui    # Starts the systemd service", file=sys.stderr)
        print()
        print("To check status:", file=sys.stderr)
        print("  systemctl --user status autocoder-ui.service", file=sys.stderr)
        print()
        print("To view logs:", file=sys.stderr)
        print("  journalctl --user -u autocoder-ui.service -f", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(1)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
