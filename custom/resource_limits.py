"""
Dynamic Resource Limits for AutoCoder
======================================

Auto-detects API provider and calculates optimal concurrency limits based on:
1. Official API rate limits (RPM, concurrency)
2. Current usage tier (free/paid/enterprise)
3. Available hardware (CPU, RAM)
4. User-configurable overrides

Usage:
    from custom.resource_limits import get_resource_limits, update_concurrency_config

    # Get auto-detected limits
    limits = get_resource_limits()
    print(f"Max agents: {limits['max_concurrency']}")

    # Update configuration
    update_concurrency_config(mode='aggressive')
"""

import os
import psutil
from pathlib import Path
from typing import Literal, Optional
import yaml


# Official API Rate Limits (January 2026)
# Source: https://docs.anthropic.com/en/api/rate-limits
# Source: https://open.bigmodel.cn/dev/howuse/rate-limits

API_LIMITS = {
    "anthropic": {
        "rpm": 50,  # Requests per minute for all models
        "tpm_sonnet": 20000,  # Tokens per minute (Sonnet)
        "tpm_haiku": 50000,  # Tokens per minute (Haiku)
        "concurrency_limit": None,  # No hard concurrency limit, RPM-based
        "recommended_max": 40,  # Conservative: 1.25 RPM per agent
    },
    "glm": {
        # GLM-4 / Zhipu AI - actual model-specific concurrency from user dashboard
        # Source: https://s3.coreaspectai.com/test-screenshots/ai/2026%/01/
        "model_concurrency": {
            "glm-4.7": 1,           # GLM Coding Max plan - very limited!
            "glm-4-plus": 20,       # Best for multi-agent AutoCoder
            "glm-4.5": 10,          # Good alternative
            "glm-4.6v": 10,         # Good alternative
            "glm-4-32b": 15,        # Mid-range option
            "glm-4.5-air": 5,       # Low-end but fast
            "glm-4-air": 5,         # Low-end but fast
        },
        "default_model": "glm-4-plus",  # Use 4-Plus for 20 concurrent
        "recommended_max": 18,  # Safe margin (90% of 20)
    },
    "openai": {
        "rpm": 10,  # Tier 1 (most common)
        "tpm": 150000,
        "concurrency_limit": None,
        "recommended_max": 8,
    },
}


# Hardware resource guardrails
HARDWARE_LIMITS = {
    "cpu_percent_per_agent": 2,  # Each agent assumed to use 2% CPU (most are idle waiting for API)
    "ram_mb_per_agent": 256,     # Each agent assumed to use 256MB RAM (actual is ~100-200MB)
    "max_cpu_usage": 90,         # Don't exceed 90% CPU usage
    "max_ram_usage": 80,         # Don't exceed 80% RAM usage
}


# Concurrency modes
CONCURRENCY_MODES = {
    "conservative": 0.5,   # 50% of recommended max
    "balanced": 1.0,       # 100% of recommended max
    "aggressive": 1.5,     # 150% of recommended max
    "disaster": 2.0,       # 200% of recommended max (user beware!)
}


def detect_api_provider() -> str:
    """Detect which API provider is being used based on environment."""
    base_url = os.getenv("ANTHROPIC_BASE_URL", "")

    if base_url.startswith("https://api.z.ai"):
        return "glm"
    elif base_url.startswith("https://api.anthropic.com"):
        return "anthropic"
    elif "openai" in base_url.lower():
        return "openai"
    else:
        # Default to Anthropic if we can't detect
        return "anthropic"


def detect_glm_model() -> str:
    """Detect which GLM model is configured as default."""
    sonnet_model = os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
    opus_model = os.getenv("ANTHROPIC_DEFAULT_OPUS_MODEL", "")

    # Return the first non-empty model (prefer opus/sonnet for primary tasks)
    return opus_model or sonnet_model or "glm-4-plus"


def get_hardware_capacity() -> dict:
    """Get available hardware resources."""
    cpu_count = psutil.cpu_count()
    cpu_percent = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()

    return {
        "cpu_count": cpu_count,
        "cpu_percent_used": cpu_percent,
        "cpu_available": max(0, 100 - cpu_percent),
        "ram_total_gb": ram.total / (1024**3),
        "ram_used_gb": ram.used / (1024**3),
        "ram_available_gb": ram.available / (1024**3),
        "ram_percent_used": ram.percent,
    }


def calculate_hardware_max_agents() -> int:
    """Calculate max agents based on available hardware."""
    hw = get_hardware_capacity()

    # CPU-based limit
    cpu_limit = int(hw["cpu_available"] / HARDWARE_LIMITS["cpu_percent_per_agent"])

    # RAM-based limit
    ram_available_mb = hw["ram_available_gb"] * 1024
    ram_limit = int(ram_available_mb / HARDWARE_LIMITS["ram_mb_per_agent"])

    # Return the more restrictive limit
    return min(cpu_limit, ram_limit)


def get_api_limits(provider: str) -> dict:
    """Get rate limits for the detected API provider."""
    return API_LIMITS.get(provider, API_LIMITS["anthropic"])


def calculate_optimal_concurrency(
    provider: Optional[str] = None,
    mode: Literal["conservative", "balanced", "aggressive", "disaster"] = "balanced",
    override_max: Optional[int] = None,
) -> dict:
    """
    Calculate optimal concurrency based on API limits and hardware.

    Args:
        provider: API provider (auto-detected if None)
        mode: Concurrency mode (conservative/balanced/aggressive/disaster)
        override_max: Manual override for max concurrency (skips all calculations)

    Returns:
        Dict with optimal limits and reasoning
    """
    if provider is None:
        provider = detect_api_provider()

    api_limits = get_api_limits(provider)
    hardware_max = calculate_hardware_max_agents()

    # Detect current GLM model for accurate limits
    current_model = detect_glm_model() if provider == "glm" else "default"

    # Determine API-based limit
    if provider == "glm":
        # GLM uses model-specific concurrency from user dashboard
        model_concurrency = api_limits.get("model_concurrency", {})
        api_max = model_concurrency.get(current_model, 20)  # Default to glm-4-plus
        api_recommended = api_limits.get("recommended_max", int(api_max * 0.9))
    else:
        # Anthropic/OpenAI use RPM
        api_max = api_limits.get("recommended_max", 10)
        api_recommended = api_max

    # Apply mode multiplier
    mode_multiplier = CONCURRENCY_MODES.get(mode, 1.0)
    mode_max = int(api_recommended * mode_multiplier)

    # Final limit is minimum of: API limit, hardware limit, mode limit
    if override_max:
        final_max = override_max
        hardware_limited = False
        api_limited = False
    else:
        final_max = min(mode_max, hardware_max, api_max)
        hardware_limited = final_max == hardware_max and hardware_max < mode_max
        api_limited = final_max == api_max and api_max < mode_max

    hw = get_hardware_capacity()

    return {
        "provider": provider,
        "model": current_model if provider == "glm" else "default",
        "max_concurrency": final_max,
        "max_total_agents": final_max * 2,  # Total processes limit
        "default_concurrency": max(1, int(final_max * 0.6)),  # 60% of max
        "mode": mode,
        "hardware": {
            "cpu_count": hw["cpu_count"],
            "cpu_available": hw["cpu_available"],
            "ram_available_gb": hw["ram_available_gb"],
            "hardware_max_agents": hardware_max,
            "hardware_limited": hardware_limited,
        },
        "api": {
            "provider": provider,
            "api_max_agents": api_max,
            "api_recommended": api_recommended,
            "api_limited": api_limited,
        },
        "reasoning": f"Based on {provider} {current_model} ({api_max} concurrent) and hardware ({hardware_max} agents), in {mode} mode",
    }


def get_resource_limits(
    mode: Literal["conservative", "balanced", "aggressive", "disaster"] = "balanced",
    override_max: Optional[int] = None,
) -> dict:
    """Get resource limits for current configuration."""
    return calculate_optimal_concurrency(mode=mode, override_max=override_max)


def get_config_file() -> Path:
    """Get path to resource limits config file."""
    config_dir = Path.home() / ".autocoder"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "resource_limits.yaml"


def load_config() -> dict:
    """Load resource limits configuration from file."""
    config_file = get_config_file()

    if not config_file.exists():
        # Create default config
        default_config = {
            "mode": "balanced",
            "override_max": None,
            "auto_detect": True,
            "hardware_headroom_percent": 20,
        }
        save_config(default_config)
        return default_config

    with open(config_file) as f:
        return yaml.safe_load(f)


def save_config(config: dict) -> None:
    """Save resource limits configuration to file."""
    config_file = get_config_file()
    with open(config_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def update_concurrency_config(
    mode: Optional[Literal["conservative", "balanced", "aggressive", "disaster"]] = None,
    override_max: Optional[int] = None,
) -> dict:
    """
    Update concurrency configuration.

    Args:
        mode: New mode (conservative/balanced/aggressive/disaster)
        override_max: Manual override for max concurrency

    Returns:
        Updated configuration with calculated limits
    """
    config = load_config()

    if mode:
        config["mode"] = mode
    if override_max is not None:
        config["override_max"] = override_max

    save_config(config)

    # Calculate actual limits
    limits = calculate_optimal_concurrency(
        mode=config.get("mode", "balanced"),
        override_max=config.get("override_max"),
    )

    return {
        "config": config,
        "limits": limits,
    }


def print_resource_status() -> None:
    """Print current resource status and limits."""
    provider = detect_api_provider()
    hw = get_hardware_capacity()
    config = load_config()
    limits = get_resource_limits(
        mode=config.get("mode", "balanced"),
        override_max=config.get("override_max"),
    )

    print("=" * 60)
    print("  AUTOCODER RESOURCE LIMITS")
    print("=" * 60)
    print()
    print("API Provider:", provider.upper())
    if provider == "glm":
        print(f"Model: {limits.get('model', 'glm-4-plus')}")
    print("Hardware:")
    print(f"  CPU: {hw['cpu_count']} cores ({hw['cpu_available']:.1f}% available)")
    print(f"  RAM: {hw['ram_total_gb']:.1f}GB ({hw['ram_available_gb']:.1f}GB available)")
    print()
    print("Calculated Limits:")
    print(f"  Max concurrent agents: {limits['max_concurrency']}")
    print(f"  Max total processes: {limits['max_total_agents']}")
    print(f"  Default concurrency: {limits['default_concurrency']}")
    print(f"  Mode: {limits['mode']}")
    print()
    print(limits["reasoning"])
    print("=" * 60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "status":
            print_resource_status()

        elif cmd == "set-mode":
            if len(sys.argv) < 3:
                print("Usage: python resource_limits.py set-mode <conservative|balanced|aggressive|disaster>")
                sys.exit(1)

            mode = sys.argv[2]
            if mode not in CONCURRENCY_MODES:
                print(f"Invalid mode. Choose from: {', '.join(CONCURRENCY_MODES.keys())}")
                sys.exit(1)

            result = update_concurrency_config(mode=mode)
            print(f"Mode set to: {mode}")
            print(f"New limits: max={result['limits']['max_concurrency']} agents")

        elif cmd == "set-max":
            if len(sys.argv) < 3:
                print("Usage: python resource_limits.py set-max <number>")
                sys.exit(1)

            try:
                max_agents = int(sys.argv[2])
            except ValueError:
                print("Error: max must be a number")
                sys.exit(1)

            result = update_concurrency_config(override_max=max_agents)
            print(f"Max concurrency set to: {max_agents}")

        else:
            print("Available commands:")
            print("  status    - Show current resource status and limits")
            print("  set-mode  - Set concurrency mode (conservative|balanced|aggressive|disaster)")
            print("  set-max   - Set manual override for max concurrency")
    else:
        print_resource_status()
