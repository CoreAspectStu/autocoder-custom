"""
UAT Gateway Logging System

Provides structured logging for all components with:
- Timestamp formatting
- Component-specific loggers
- Configurable log levels
- Rich console output with colors
- File logging support
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from rich.logging import RichHandler
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# Log format without rich (fallback)
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class UATGatewayLogger:
    """Centralized logger for UAT Gateway components"""

    _loggers = {}
    _configured = False

    @classmethod
    def configure(cls,
                  level: str = "INFO",
                  log_file: Optional[str] = None,
                  use_rich: bool = True) -> None:
        """
        Configure the logging system

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Optional path to log file
            use_rich: Use rich formatting if available
        """
        if cls._configured:
            return

        # Convert level string to logging constant
        numeric_level = getattr(logging, level.upper(), logging.INFO)

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)

        # Remove existing handlers
        root_logger.handlers.clear()

        # Console handler
        if RICH_AVAILABLE and use_rich:
            console_handler = RichHandler(
                console=Console(stderr=True),
                show_time=True,
                show_path=False,
                rich_tracebacks=True,
                tracebacks_show_locals=True,
                markup=True,
            )
            console_handler.setFormatter(logging.Formatter(
                "%(message)s",
                datefmt="[%X]"
            ))
        else:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(logging.Formatter(
                LOG_FORMAT,
                datefmt=DATE_FORMAT
            ))

        console_handler.setLevel(numeric_level)
        root_logger.addHandler(console_handler)

        # File handler (if specified)
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(
                LOG_FORMAT,
                datefmt=DATE_FORMAT
            ))
            file_handler.setLevel(numeric_level)
            root_logger.addHandler(file_handler)

        cls._configured = True

        # Log configuration
        logger = cls.get_logger("logging")
        logger.info(f"Logging system configured at {level} level")
        if log_file:
            logger.info(f"Logging to file: {log_file}")

    @classmethod
    def get_logger(cls, component: str) -> logging.Logger:
        """
        Get or create a logger for a specific component

        Args:
            component: Component name (e.g., "journey_extractor", "test_executor")

        Returns:
            Logger instance for the component
        """
        if component in cls._loggers:
            return cls._loggers[component]

        # Auto-configure if not already done
        if not cls._configured:
            cls.configure()

        # Create logger for component
        logger = logging.getLogger(f"uat_gateway.{component}")
        logger.setLevel(logging.DEBUG)  # Capture all levels, handlers will filter
        logger.propagate = True

        cls._loggers[component] = logger
        return logger


def get_logger(component: str) -> logging.Logger:
    """
    Convenience function to get a logger for a component

    Args:
        component: Component name

    Returns:
        Logger instance
    """
    return UATGatewayLogger.get_logger(component)


# Pre-configured loggers for main components
def get_journey_extractor_logger() -> logging.Logger:
    """Get logger for journey extractor component"""
    return get_logger("journey_extractor")


def get_test_generator_logger() -> logging.Logger:
    """Get logger for test generator component"""
    return get_logger("test_generator")


def get_test_executor_logger() -> logging.Logger:
    """Get logger for test executor component"""
    return get_logger("test_executor")


def get_result_processor_logger() -> logging.Logger:
    """Get logger for result processor component"""
    return get_logger("result_processor")


def get_state_manager_logger() -> logging.Logger:
    """Get logger for state manager component"""
    return get_logger("state_manager")


def get_kanban_integrator_logger() -> logging.Logger:
    """Get logger for kanban integrator component"""
    return get_logger("kanban_integrator")


def get_orchestrator_logger() -> logging.Logger:
    """Get logger for orchestrator component"""
    return get_logger("orchestrator")


# Export main logger class
__all__ = [
    "UATGatewayLogger",
    "get_logger",
    "get_journey_extractor_logger",
    "get_test_generator_logger",
    "get_test_executor_logger",
    "get_result_processor_logger",
    "get_state_manager_logger",
    "get_kanban_integrator_logger",
    "get_orchestrator_logger",
]
