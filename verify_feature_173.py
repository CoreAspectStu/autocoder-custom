#!/usr/bin/env python3
"""
Verification script for Feature #173: Fix AutoCoder UI build process

This script verifies that:
1. The production wrapper script exists and is executable
2. The systemd service file points to the wrapper script
3. The wrapper script successfully builds the frontend
4. TypeScript compilation works without errors
5. Vite bundling produces the dist directory
"""

import os
import subprocess
import sys
from pathlib import Path

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

def print_success(message: str) -> None:
    print(f"{GREEN}✅ {message}{RESET}")

def print_error(message: str) -> None:
    print(f"{RED}❌ {message}{RESET}")

def check_step(step_num: int, total: int, message: str) -> None:
    print(f"\n[{step_num}/{total}] {message}")
    print("-" * 60)

def main() -> int:
    print("=" * 60)
    print("Feature #173 Verification: AutoCoder UI Build Process")
    print("=" * 60)

    autocoder_dir = Path("/home/stu/projects/autocoder")
    ui_dir = autocoder_dir / "ui"
    wrapper_script = autocoder_dir / "start_ui_production.sh"
    systemd_service = Path.home() / ".config/systemd/user/autocoder-ui.service"

    total_checks = 6
    passed = 0

    # Check 1: Wrapper script exists
    check_step(1, total_checks, "Verify production wrapper script exists")
    if wrapper_script.exists():
        print_success(f"Wrapper script exists: {wrapper_script}")
        if os.access(wrapper_script, os.X_OK):
            print_success("Wrapper script is executable")
            passed += 1
        else:
            print_error("Wrapper script is NOT executable")
            print(f"Run: chmod +x {wrapper_script}")
    else:
        print_error(f"Wrapper script NOT found: {wrapper_script}")

    # Check 2: Systemd service configuration
    check_step(2, total_checks, "Verify systemd service uses wrapper script")
    if systemd_service.exists():
        content = systemd_service.read_text()
        if "ExecStart=/home/stu/projects/autocoder/start_ui_production.sh" in content:
            print_success("Systemd service ExecStart points to wrapper script")
            passed += 1
        else:
            print_error("Systemd service does NOT use wrapper script")
            print("Expected: ExecStart=/home/stu/projects/autocoder/start_ui_production.sh")
    else:
        print_error(f"Systemd service file not found: {systemd_service}")

    # Check 3: Wrapper script content
    check_step(3, total_checks, "Verify wrapper script contains build command")
    if wrapper_script.exists():
        content = wrapper_script.read_text()
        has_build = "npm run build" in content
        has_uvicorn = "uvicorn" in content
        if has_build and has_uvicorn:
            print_success("Wrapper script contains build command and uvicorn start")
            passed += 1
        else:
            print_error("Wrapper script missing build command or uvicorn start")
    else:
        print_error("Cannot check content - wrapper script doesn't exist")

    # Check 4: TypeScript configuration
    check_step(4, total_checks, "Verify TypeScript strict mode is enabled")
    tsconfig = ui_dir / "tsconfig.json"
    if tsconfig.exists():
        content = tsconfig.read_text()
        if '"strict": true' in content:
            print_success("TypeScript strict mode is enabled")
            passed += 1
        else:
            print_error("TypeScript strict mode is NOT enabled")
    else:
        print_error(f"tsconfig.json not found: {tsconfig}")

    # Check 5: TypeScript compilation works
    check_step(5, total_checks, "Test TypeScript compilation (tsc -b)")
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(ui_dir),
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode == 0:
            print_success("TypeScript compilation succeeded")
            print("Build output:")
            for line in result.stdout.split('\n')[-5:]:
                if line.strip():
                    print(f"  {line}")
            passed += 1
        else:
            print_error("TypeScript compilation FAILED")
            print("Error output:")
            print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
    except subprocess.TimeoutExpired:
        print_error("TypeScript compilation timed out after 120 seconds")
    except Exception as e:
        print_error(f"Error running TypeScript compilation: {e}")

    # Check 6: Dist directory exists and is recent
    check_step(6, total_checks, "Verify dist directory was created")
    dist_dir = ui_dir / "dist"
    if dist_dir.exists():
        print_success(f"dist directory exists: {dist_dir}")

        # Check if it has the expected files
        index_html = dist_dir / "index.html"
        assets_dir = dist_dir / "assets"

        if index_html.exists() and assets_dir.exists():
            print_success("dist directory contains index.html and assets/")
            passed += 1
        else:
            print_error("dist directory is missing expected files")
    else:
        print_error(f"dist directory NOT found: {dist_dir}")

    # Summary
    print("\n" + "=" * 60)
    print(f"VERIFICATION SUMMARY: {passed}/{total_checks} checks passed")
    print("=" * 60)

    if passed == total_checks:
        print_success("ALL CHECKS PASSED ✅")
        print("\nFeature #173 is working correctly!")
        print("\nNext steps:")
        print("1. Reload systemd: systemctl --user daemon-reload")
        print("2. Restart service: systemctl --user restart autocoder-ui")
        print("3. Verify service: systemctl --user status autocoder-ui")
        return 0
    else:
        print_error(f"SOME CHECKS FAILED ({total_checks - passed} failures)")
        print("\nPlease fix the issues above and run this script again.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
