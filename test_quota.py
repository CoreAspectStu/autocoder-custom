#!/usr/bin/env python3
"""
Quick test to verify API quota tracking is working.
"""

from api.quota_budget import get_quota_budget

def test_quota_tracking():
    """Test quota tracking functionality."""
    print("=" * 70)
    print("  QUOTA TRACKING TEST")
    print("=" * 70)
    print()

    quota = get_quota_budget()

    print("Initial quota stats:")
    stats = quota.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print()

    # Simulate some API usage
    print("Simulating 5 API calls...")
    for i in range(5):
        quota.track_usage(model="sonnet-4", prompts_used=1, project_name="test", agent_id=f"agent-{i}")
    print()

    print("Updated quota stats:")
    stats = quota.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print()

    # Test safe concurrency calculation
    safe_concurrency = quota.calculate_safe_concurrency(prompts_per_agent=20)
    print(f"Safe concurrency (20 prompts/agent): {safe_concurrency} agents")
    print()

    # Test quota availability
    is_available = quota.is_quota_available(prompts_needed=10)
    print(f"Quota available for 10 prompts: {is_available}")
    print()

    # Cleanup test entries
    print("Cleaning up old entries...")
    quota.cleanup_old_entries()
    print("Done!")
    print()

    print("=" * 70)
    print("  TEST COMPLETE")
    print("=" * 70)
    print()
    print("Quota tracking is working! Next steps:")
    print("  1. Start autocoder-ui to begin tracking real API usage")
    print("  2. Check Netdata dashboard for quota metrics")
    print("  3. Monitor Slack #alerts for quota threshold warnings")
    print()


if __name__ == "__main__":
    test_quota_tracking()
