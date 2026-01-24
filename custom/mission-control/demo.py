#!/usr/bin/env python3
"""
Mission Control Demo Script

Demonstrates DevLayer client usage (simulates agent behavior).

Usage:
    # Start AutoCoder UI first
    autocoder-ui

    # In another terminal:
    python custom/mission-control/demo.py
"""

import asyncio
import sys
from pathlib import Path

# Add autocoder to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom.mission_control.client import DevLayerClient, RequestPriority


async def demo_question():
    """Demo: Agent asks a question."""
    print("\n=== Demo: Ask Question ===\n")
    client = DevLayerClient(project_name="demo-project", timeout=60)

    print("Agent: Should I use REST or GraphQL for the API?")
    print("(Check DevLayer UI and respond...)")

    try:
        response = await client.ask_question(
            message="Should I use REST or GraphQL for the API?",
            context="Building a mobile app with 50 enterprise clients",
            priority=RequestPriority.NORMAL
        )
        print(f"Human response: {response}")
        print("Agent: Got it! Implementing REST API...")
    except TimeoutError:
        print("Timeout: No response received within 60 seconds")


async def demo_blocker():
    """Demo: Agent reports blocker."""
    print("\n=== Demo: Report Blocker ===\n")
    client = DevLayerClient(project_name="demo-project", timeout=60)

    print("Agent: Database migration failed!")
    print("(Check DevLayer UI and provide guidance...)")

    try:
        guidance = await client.report_blocker(
            message="Database migration failed - production DB is read-only",
            context="Error: SQLSTATE[42501]: Insufficient privilege",
            priority=RequestPriority.CRITICAL
        )
        print(f"Human guidance: {guidance}")
        print("Agent: Switching to staging database, thanks!")
    except TimeoutError:
        print("Timeout: No response received")


async def demo_chat():
    """Demo: Agent sends chat messages."""
    print("\n=== Demo: Chat Messages ===\n")
    client = DevLayerClient(project_name="demo-project")

    messages = [
        "Starting database migration...",
        "Migrated 50/200 tables (25%)",
        "Migrated 150/200 tables (75%)",
        "Migration complete! ✅"
    ]

    for msg in messages:
        print(f"Agent: {msg}")
        await client.send_chat(msg)
        await asyncio.sleep(2)

    print("(Check DevLayer chat to see messages)")


async def demo_annotation():
    """Demo: Agent creates annotations."""
    print("\n=== Demo: Annotations ===\n")
    client = DevLayerClient(project_name="demo-project")

    annotations = [
        ("bug", "Payment form validation fails on Safari"),
        ("workaround", "Auth API is flaky - added 3x retry with backoff"),
        ("idea", "Add dark mode toggle to settings"),
        ("comment", "Using Stripe test mode - remember to switch to prod")
    ]

    for ann_type, content in annotations:
        print(f"Creating {ann_type}: {content}")
        await client.create_annotation(ann_type, content)
        await asyncio.sleep(1)

    print("(Check DevLayer UI to see annotations)")


async def main():
    """Run all demos."""
    print("=" * 60)
    print("  Mission Control Demo")
    print("=" * 60)
    print("\nMake sure AutoCoder UI is running (autocoder-ui)")
    print("Press L in UI to open DevLayer mode\n")
    input("Press Enter to start demos...")

    # Run demos in sequence
    await demo_chat()
    await asyncio.sleep(2)

    await demo_annotation()
    await asyncio.sleep(2)

    # Interactive demos (require human response)
    print("\n" + "=" * 60)
    print("  Interactive Demos (require response in UI)")
    print("=" * 60)

    choice = input("\nRun interactive demos? (y/n): ")
    if choice.lower() == 'y':
        await demo_question()
        await asyncio.sleep(2)
        await demo_blocker()

    print("\n" + "=" * 60)
    print("  Demo Complete!")
    print("=" * 60)
    print("\nCheck the DevLayer UI to see all requests/chat/annotations")


if __name__ == "__main__":
    asyncio.run(main())
