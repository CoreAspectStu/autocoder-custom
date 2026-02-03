#!/usr/bin/env python3
"""
UAT AutoCoder Plugin - Configuration Management

This module provides configuration loading and validation for the UAT AutoCoder plugin.
It reads from ~/.autocoder/uat_autocoder/config.yaml and provides a simple interface
for accessing configuration values.

Author: AutoCoder Agent
Created: 2025-01-27
"""

import os
import yaml
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


class ValidationError(Exception):
    """
    Configuration validation error

    This exception is raised when configuration validation fails.
    It provides detailed error messages about what's wrong and how to fix it.
    """
    def __init__(self, errors: List[str]):
        """
        Initialize validation error

        Args:
            errors: List of error messages describing validation failures
        """
        self.errors = errors
        message = "Configuration validation failed:\n  - " + "\n  - ".join(errors)
        super().__init__(message)


@dataclass
class BrowserConfig:
    """Browser configuration"""
    name: str
    viewport: str

    # Valid browser names (Playwright browser types)
    VALID_BROWSERS = [
        "chromium", "firefox", "webkit",
        "chrome", "edge", "safari"
    ]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BrowserConfig':
        return cls(
            name=data["name"],
            viewport=data["viewport"]
        )

    def validate(self) -> List[str]:
        """
        Validate browser configuration

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Validate browser name
        if not self.name or not isinstance(self.name, str):
            errors.append(f"Browser name must be a non-empty string, got: {self.name}")
        else:
            # Allow common browser variants
            name_lower = self.name.lower().replace(" ", "_").replace("-", "_")
            valid_names = self.VALID_BROWSERS + [
                "chrome_mobile", "safari_mobile",
                "chromium_mobile", "firefox_mobile"
            ]
            if name_lower not in valid_names:
                errors.append(
                    f"Invalid browser name: '{self.name}'. "
                    f"Valid options: {', '.join(self.VALID_BROWSERS)}"
                )

        # Validate viewport format (should be WIDTHxHEIGHT or WxH)
        if self.viewport and isinstance(self.viewport, str):
            viewport_pattern = r'^\d+x\d+$'
            if not re.match(viewport_pattern, self.viewport):
                errors.append(
                    f"Invalid viewport format: '{self.viewport}'. "
                    f"Expected format: WIDTHxHEIGHT (e.g., '1920x1080')"
                )
        else:
            errors.append(f"Viewport must be a string in format WIDTHxHEIGHT, got: {self.viewport}")

        return errors


@dataclass
class EvidenceCollectionConfig:
    """Evidence collection settings"""
    screenshot_on_failure: bool = True
    video_on_failure: bool = True
    trace_on_failure: bool = False
    console_logs: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EvidenceCollectionConfig':
        return cls(
            screenshot_on_failure=data.get("screenshot_on_failure", True),
            video_on_failure=data.get("video_on_failure", True),
            trace_on_failure=data.get("trace_on_failure", False),
            console_logs=data.get("console_logs", True)
        )


@dataclass
class PhaseConfig:
    """Test phase configuration"""
    name: str
    enabled: bool = True
    max_tests: Optional[int] = None

    # Valid phase names
    VALID_PHASES = ["smoke", "functional", "regression", "uat", "integration"]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PhaseConfig':
        return cls(
            name=data["name"],
            enabled=data.get("enabled", True),
            max_tests=data.get("max_tests", None)
        )

    def validate(self) -> List[str]:
        """
        Validate phase configuration

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Validate phase name
        if not self.name or not isinstance(self.name, str):
            errors.append(f"Phase name must be a non-empty string, got: {self.name}")
        else:
            name_lower = self.name.lower()
            if name_lower not in self.VALID_PHASES:
                errors.append(
                    f"Invalid phase name: '{self.name}'. "
                    f"Valid options: {', '.join(self.VALID_PHASES)}"
                )

        # Validate enabled flag
        if not isinstance(self.enabled, bool):
            errors.append(f"Phase enabled must be boolean, got: {type(self.enabled).__name__}")

        # Validate max_tests
        if self.max_tests is not None:
            if not isinstance(self.max_tests, int):
                errors.append(f"Phase max_tests must be integer or null, got: {type(self.max_tests).__name__}")
            elif self.max_tests < 1:
                errors.append(f"Phase max_tests must be >= 1 or null, got: {self.max_tests}")

        return errors


@dataclass
class DevLayerConfig:
    """DevLayer integration settings"""
    auto_create_cards: bool = True
    card_severity: str = "medium"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DevLayerConfig':
        return cls(
            auto_create_cards=data.get("auto_create_cards", True),
            card_severity=data.get("card_severity", "medium")
        )


@dataclass
class IntegrationConfig:
    """Integration settings"""
    devlayer: DevLayerConfig = field(default_factory=DevLayerConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IntegrationConfig':
        return cls(
            devlayer=DevLayerConfig.from_dict(data.get("devlayer", {}))
        )


@dataclass
class UATConfig:
    """
    Main UAT AutoCoder configuration

    This class holds all configuration values for the UAT AutoCoder plugin.
    It provides type-safe access to configuration values with defaults.
    """
    # Agent settings
    max_concurrent_agents: int = 3
    agent_startup_delay_seconds: int = 2
    test_timeout_seconds: int = 300
    max_retries: int = 1
    retry_delay_seconds: int = 5

    # Browser and evidence settings
    browsers: List[BrowserConfig] = field(default_factory=list)
    evidence_collection: EvidenceCollectionConfig = field(default_factory=EvidenceCollectionConfig)

    # Test phases
    phases: List[PhaseConfig] = field(default_factory=list)

    # Integration settings
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UATConfig':
        """Create UATConfig from dictionary"""
        autocoder_data = data.get("autocoder", {})

        return cls(
            max_concurrent_agents=autocoder_data.get("max_concurrent_agents", 3),
            agent_startup_delay_seconds=autocoder_data.get("agent_startup_delay_seconds", 2),
            test_timeout_seconds=autocoder_data.get("test_timeout_seconds", 300),
            max_retries=autocoder_data.get("max_retries", 1),
            retry_delay_seconds=autocoder_data.get("retry_delay_seconds", 5),
            browsers=[
                BrowserConfig.from_dict(b) for b in autocoder_data.get("browsers", [])
            ],
            evidence_collection=EvidenceCollectionConfig.from_dict(
                autocoder_data.get("evidence_collection", {})
            ),
            phases=[
                PhaseConfig.from_dict(p) for p in autocoder_data.get("phases", [])
            ],
            integration=IntegrationConfig.from_dict(
                autocoder_data.get("integration", {})
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "autocoder": {
                "max_concurrent_agents": self.max_concurrent_agents,
                "agent_startup_delay_seconds": self.agent_startup_delay_seconds,
                "test_timeout_seconds": self.test_timeout_seconds,
                "max_retries": self.max_retries,
                "retry_delay_seconds": self.retry_delay_seconds,
                "browsers": [
                    {"name": b.name, "viewport": b.viewport} for b in self.browsers
                ],
                "evidence_collection": {
                    "screenshot_on_failure": self.evidence_collection.screenshot_on_failure,
                    "video_on_failure": self.evidence_collection.video_on_failure,
                    "trace_on_failure": self.evidence_collection.trace_on_failure,
                    "console_logs": self.evidence_collection.console_logs
                },
                "phases": [
                    {
                        "name": p.name,
                        "enabled": p.enabled,
                        "max_tests": p.max_tests
                    } for p in self.phases
                ],
                "integration": {
                    "devlayer": {
                        "auto_create_cards": self.integration.devlayer.auto_create_cards,
                        "card_severity": self.integration.devlayer.card_severity
                    }
                }
            }
        }

    def validate(self) -> List[str]:
        """
        Validate entire configuration

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Validate agent settings
        if not isinstance(self.max_concurrent_agents, int):
            errors.append(f"max_concurrent_agents must be integer, got: {type(self.max_concurrent_agents).__name__}")
        elif self.max_concurrent_agents < 1:
            errors.append(f"max_concurrent_agents must be >= 1, got: {self.max_concurrent_agents}")

        if not isinstance(self.agent_startup_delay_seconds, int):
            errors.append(f"agent_startup_delay_seconds must be integer, got: {type(self.agent_startup_delay_seconds).__name__}")
        elif self.agent_startup_delay_seconds < 0:
            errors.append(f"agent_startup_delay_seconds must be >= 0, got: {self.agent_startup_delay_seconds}")

        if not isinstance(self.test_timeout_seconds, int):
            errors.append(f"test_timeout_seconds must be integer, got: {type(self.test_timeout_seconds).__name__}")
        elif self.test_timeout_seconds < 1:
            errors.append(f"test_timeout_seconds must be >= 1, got: {self.test_timeout_seconds}")

        if not isinstance(self.max_retries, int):
            errors.append(f"max_retries must be integer, got: {type(self.max_retries).__name__}")
        elif self.max_retries < 0:
            errors.append(f"max_retries must be >= 0, got: {self.max_retries}")

        if not isinstance(self.retry_delay_seconds, int):
            errors.append(f"retry_delay_seconds must be integer, got: {type(self.retry_delay_seconds).__name__}")
        elif self.retry_delay_seconds < 0:
            errors.append(f"retry_delay_seconds must be >= 0, got: {self.retry_delay_seconds}")

        # Validate browsers
        if not self.browsers:
            errors.append("At least one browser must be configured")

        for idx, browser in enumerate(self.browsers):
            browser_errors = browser.validate()
            for error in browser_errors:
                errors.append(f"Browser #{idx + 1}: {error}")

        # Validate phases
        if not self.phases:
            errors.append("At least one phase must be configured")

        for idx, phase in enumerate(self.phases):
            phase_errors = phase.validate()
            for error in phase_errors:
                errors.append(f"Phase '{phase.name}': {error}")

        # Validate evidence collection
        if not isinstance(self.evidence_collection.screenshot_on_failure, bool):
            errors.append(f"evidence_collection.screenshot_on_failure must be boolean, got: {type(self.evidence_collection.screenshot_on_failure).__name__}")

        if not isinstance(self.evidence_collection.video_on_failure, bool):
            errors.append(f"evidence_collection.video_on_failure must be boolean, got: {type(self.evidence_collection.video_on_failure).__name__}")

        if not isinstance(self.evidence_collection.trace_on_failure, bool):
            errors.append(f"evidence_collection.trace_on_failure must be boolean, got: {type(self.evidence_collection.trace_on_failure).__name__}")

        if not isinstance(self.evidence_collection.console_logs, bool):
            errors.append(f"evidence_collection.console_logs must be boolean, got: {type(self.evidence_collection.console_logs).__name__}")

        # Validate integration settings
        valid_severities = ["low", "medium", "high", "critical"]
        severity = self.integration.devlayer.card_severity
        if severity not in valid_severities:
            errors.append(
                f"integration.devlayer.card_severity must be one of {valid_severities}, "
                f"got: '{severity}'"
            )

        if not isinstance(self.integration.devlayer.auto_create_cards, bool):
            errors.append(f"integration.devlayer.auto_create_cards must be boolean, got: {type(self.integration.devlayer.auto_create_cards).__name__}")

        return errors


class ConfigManager:
    """
    Configuration manager for UAT AutoCoder plugin

    This class handles loading, caching, and providing access to the configuration.
    It implements a singleton pattern to ensure only one configuration is loaded.

    Usage:
        config = ConfigManager.get_config()
        print(config.max_concurrent_agents)
    """

    _instance: Optional['ConfigManager'] = None
    _config: Optional[UATConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize configuration manager (loads config on first use)"""
        if self._config is None:
            self._load_config()

    @property
    def config_dir(self) -> Path:
        """Get configuration directory path"""
        return Path.home() / ".autocoder" / "uat_autocoder"

    @property
    def config_file(self) -> Path:
        """Get configuration file path"""
        return self.config_dir / "config.yaml"

    def _load_config(self, validate: bool = True) -> None:
        """
        Load configuration from YAML file

        Args:
            validate: If True, validate configuration after loading

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config file has invalid YAML syntax
            ValidationError: If configuration validation fails
        """
        if not self.config_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_file}\n"
                f"Please create the configuration file first."
            )

        with open(self.config_file, 'r') as f:
            data = yaml.safe_load(f)

        self._config = UATConfig.from_dict(data)

        # Validate configuration if requested
        if validate:
            errors = self._config.validate()
            if errors:
                raise ValidationError(errors)

    def reload_config(self, validate: bool = True) -> None:
        """
        Force reload of configuration file

        Args:
            validate: If True, validate configuration after loading

        Raises:
            ValidationError: If configuration validation fails
        """
        self._load_config(validate=validate)

    def get_config(self) -> UATConfig:
        """
        Get current configuration

        Returns:
            UATConfig: Current configuration object
        """
        if self._config is None:
            self._load_config()
        return self._config

    def save_config(self, config: UATConfig) -> None:
        """
        Save configuration to YAML file

        Args:
            config: Configuration object to save

        Raises:
            OSError: If unable to write config file
        """
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Convert to dict and save
        data = config.to_dict()

        with open(self.config_file, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

        # Update cached config
        self._config = config


# Convenience functions for easy access

def validate_config(config: UATConfig) -> List[str]:
    """
    Validate a configuration object

    Args:
        config: Configuration object to validate

    Returns:
        List of error messages (empty if valid)

    Usage:
        errors = validate_config(config)
        if errors:
            print("Validation failed:")
            for error in errors:
                print(f"  - {error}")
    """
    return config.validate()


def get_config(validate: bool = True) -> UATConfig:
    """
    Get current configuration (convenience function)

    Args:
        validate: If True, validate configuration (default: True)

    Usage:
        from uat_plugin.config import get_config
        config = get_config()
        print(config.max_concurrent_agents)

    Returns:
        UATConfig: Current configuration object
    """
    manager = ConfigManager()
    if validate:
        return manager.get_config()  # Already validated in _load_config
    else:
        return manager._config


def reload_config(validate: bool = True) -> None:
    """
    Reload configuration file (convenience function)

    Args:
        validate: If True, validate configuration after reloading (default: True)
    """
    manager = ConfigManager()
    manager.reload_config(validate=validate)


def save_config(config: UATConfig) -> None:
    """Save configuration to file (convenience function)"""
    manager = ConfigManager()
    manager.save_config(config)


# CLI for testing configuration

if __name__ == "__main__":
    import sys

    print("UAT AutoCoder Configuration Manager")
    print("=" * 60)

    # Check for validation mode
    if len(sys.argv) > 1 and sys.argv[1] == "--validate":
        try:
            config = get_config(validate=True)
            errors = config.validate()

            if errors:
                print("\n❌ Configuration validation FAILED")
                print("\nErrors found:")
                for error in errors:
                    print(f"  ✗ {error}")
                sys.exit(1)
            else:
                print("\n✅ Configuration validation PASSED")
                print("All configuration values are valid.")
                sys.exit(0)

        except ValidationError as e:
            print(f"\n❌ {e}")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error: {e}", file=sys.stderr)
            sys.exit(1)

    # Normal mode: load and display configuration
    try:
        config = get_config(validate=True)

        print(f"\nAgent Settings:")
        print(f"  Max concurrent agents: {config.max_concurrent_agents}")
        print(f"  Agent startup delay: {config.agent_startup_delay_seconds}s")
        print(f"  Test timeout: {config.test_timeout_seconds}s")
        print(f"  Max retries: {config.max_retries}")
        print(f"  Retry delay: {config.retry_delay_seconds}s")

        print(f"\nBrowsers ({len(config.browsers)}):")
        for browser in config.browsers:
            print(f"  - {browser.name} ({browser.viewport})")

        print(f"\nEvidence Collection:")
        print(f"  Screenshot on failure: {config.evidence_collection.screenshot_on_failure}")
        print(f"  Video on failure: {config.evidence_collection.video_on_failure}")
        print(f"  Trace on failure: {config.evidence_collection.trace_on_failure}")
        print(f"  Console logs: {config.evidence_collection.console_logs}")

        print(f"\nPhases ({len(config.phases)}):")
        for phase in config.phases:
            max_tests = phase.max_tests if phase.max_tests else "unlimited"
            status = "enabled" if phase.enabled else "disabled"
            print(f"  - {phase.name}: {status} (max {max_tests})")

        print(f"\nIntegration:")
        print(f"  DevLayer:")
        print(f"    Auto create cards: {config.integration.devlayer.auto_create_cards}")
        print(f"    Card severity: {config.integration.devlayer.card_severity}")

        print("\n" + "=" * 60)
        print("✅ Configuration loaded and validated successfully!")
        sys.exit(0)

    except ValidationError as e:
        print(f"\n❌ Configuration validation failed:")
        print(f"{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)
