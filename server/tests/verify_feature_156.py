#!/usr/bin/env python3
"""
Verification script for Feature #156: Backend Test Database Auto-Creation

This script runs the test_assistant_database.py tests and verifies they all pass.
"""

import sys
import subprocess
from pathlib import Path

def main():
    print("=" * 80)
    print("VERIFICATION: Feature #156 - Backend Test Database Auto-Creation")
    print("=" * 80)
    print()

    # Add autocoder to Python path
    autocoder_path = Path("/home/stu/projects/autocoder")
    sys.path.insert(0, str(autocoder_path))

    test_file = autocoder_path / "server/tests/test_assistant_database.py"

    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return 1

    print(f"✅ Test file found: {test_file}")
    print()

    # Run pytest with proper environment
    env = {
        "PYTHONPATH": str(autocoder_path),
    }

    cmd = [
        sys.executable,
        "-m", "pytest",
        str(test_file),
        "-v",
        "--tb=short",
        "--color=yes"
    ]

    print("Running tests...")
    print("-" * 80)

    result = subprocess.run(
        cmd,
        cwd=str(autocoder_path),
        env={**subprocess.os.environ, **env},
        capture_output=False,
        text=True
    )

    print("-" * 80)
    print()

    if result.returncode == 0:
        print("✅ ALL TESTS PASSED!")
        print()
        print("Feature #156 is fully implemented and verified:")
        print("  ✅ Database file auto-creation works")
        print("  ✅ Tables are created automatically")
        print("  ✅ Schema is correct")
        print("  ✅ Parent directories are created")
        print("  ✅ Database is usable immediately")
        print("  ✅ Engine caching works")
        print("  ✅ Cross-project isolation works")
        print("  ✅ Indexes are created")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print()
        print("Please review the test output above to fix any issues.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
