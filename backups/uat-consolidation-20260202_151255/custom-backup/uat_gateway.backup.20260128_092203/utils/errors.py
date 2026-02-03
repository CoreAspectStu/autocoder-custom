"""
UAT Gateway Error Handling Framework

Provides global exception handling with:
- Custom exception classes for UAT Gateway
- Error context tracking
- Stack trace capture
- Structured error logging
- Error recovery mechanisms
"""

import sys
import traceback
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from functools import wraps
from pathlib import Path


# ============================================================================
# Custom Exception Classes
# ============================================================================

class UATGatewayError(Exception):
    """Base exception for all UAT Gateway errors"""

    def __init__(self,
                 message: str,
                 component: str = "unknown",
                 context: Optional[Dict[str, Any]] = None):
        self.message = message
        self.component = component
        self.context = context or {}
        self.timestamp = datetime.now()
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "component": self.component,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }


class JourneyExtractionError(UATGatewayError):
    """Errors during journey extraction from specs"""
    pass


class TestGenerationError(UATGatewayError):
    """Errors during test generation"""
    pass


class TestExecutionError(UATGatewayError):
    """Errors during test execution"""
    pass


class TestSelectionError(UATGatewayError):
    """Errors during test selection and optimization"""
    pass


class ResultProcessingError(UATGatewayError):
    """Errors during result processing"""
    pass


class StateManagementError(UATGatewayError):
    """Errors during state management operations"""
    pass


class KanbanIntegrationError(UATGatewayError):
    """Errors during Kanban board operations"""
    pass


class ConfigurationError(UATGatewayError):
    """Errors in configuration"""
    pass


class OrchestratorError(UATGatewayError):
    """Errors during orchestration of the testing cycle"""
    pass


class AdapterError(UATGatewayError):
    """Errors during adapter operations (visual, a11y, API, etc.)"""
    pass


# ============================================================================
# Global Error Handler
# ============================================================================

class ErrorHandler:
    """Global error handler for UAT Gateway"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("uat_gateway.error_handler")
        self.error_counts = {}
        self.recent_errors = []

    def handle_exception(self,
                        exc: Exception,
                        context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Handle an exception with full logging and context tracking

        Args:
            exc: The exception to handle
            context: Additional context information

        Returns:
            Dictionary with error details
        """
        # Get stack trace
        stack_trace = traceback.format_exc()

        # Build error info
        error_info = {
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "stack_trace": stack_trace,
            "timestamp": datetime.now().isoformat(),
        }

        # Add context if exception is UATGatewayError
        if isinstance(exc, UATGatewayError):
            error_info["component"] = exc.component
            error_info["context"] = exc.context
            error_info["original_message"] = exc.message
        elif context:
            error_info["context"] = context

        # Log the error
        self.logger.error(
            f"Exception in {error_info.get('component', 'unknown')}: "
            f"{error_info['error_message']}",
            extra={"error_info": error_info}
        )

        # Track error statistics
        error_key = f"{error_info['error_type']}:{error_info.get('component', 'unknown')}"
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1

        # Keep recent errors (last 100)
        self.recent_errors.append(error_info)
        if len(self.recent_errors) > 100:
            self.recent_errors.pop(0)

        return error_info

    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of errors encountered"""
        return {
            "total_errors": sum(self.error_counts.values()),
            "error_counts": self.error_counts,
            "recent_error_count": len(self.recent_errors),
        }


# Global error handler instance
_global_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """Get the global error handler instance"""
    global _global_error_handler
    if _global_error_handler is None:
        from utils.logger import get_logger
        _global_error_handler = ErrorHandler(get_logger("error_handler"))
    return _global_error_handler


# ============================================================================
# Exception Handling Decorators
# ============================================================================

def handle_errors(*decorator_args, component: str = "unknown", reraise: bool = False, default_return: Any = None):
    """
    Decorator to automatically handle exceptions in functions

    Can be used with or without arguments:
    - @handle_errors(component="visual_adapter")
    - @handle_errors

    Args:
        component: Component name for error tracking
        reraise: Whether to re-raise the exception after handling
        default_return: Value to return on error (if not reraising)
    """

    # Check if decorator was called with or without arguments
    if decorator_args and callable(decorator_args[0]):
        # Called as @handle_errors (without parentheses)
        func = decorator_args[0]
        # Apply wrapper directly with default values
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_handler = get_error_handler()
                context = {
                    "function": func.__name__,
                    "args": str(args)[:200],  # Truncate long args
                    "kwargs": str(kwargs)[:200],
                }
                error_handler.handle_exception(e, context)

                if reraise:
                    raise
                return default_return

        return wrapper
    else:
        # Called as @handle_errors(component="...", ...)
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_handler = get_error_handler()
                    context = {
                        "function": func.__name__,
                        "args": str(args)[:200],  # Truncate long args
                        "kwargs": str(kwargs)[:200],
                    }
                    error_handler.handle_exception(e, context)

                    if reraise:
                        raise
                    return default_return

            return wrapper
        return decorator


def safe_execute(func,
                component: str = "unknown",
                default_return: Any = None,
                log_errors: bool = True) -> Any:
    """
    Safely execute a function with error handling

    Args:
        func: Function to execute
        component: Component name for error tracking
        default_return: Value to return on error
        log_errors: Whether to log errors

    Returns:
        Function result or default_return on error
    """
    try:
        return func()
    except Exception as e:
        if log_errors:
            error_handler = get_error_handler()
            error_handler.handle_exception(e, {"component": component})
        return default_return


# ============================================================================
# Exception Context Manager
# ============================================================================

class ErrorContext:
    """Context manager for error tracking with custom context"""

    def __init__(self,
                 component: str,
                 context: Optional[Dict[str, Any]] = None,
                 reraise: bool = False):
        self.component = component
        self.context = context or {}
        self.reraise = reraise
        self.error_handler = get_error_handler()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Add context if it's a UAT Gateway error
            if isinstance(exc_val, UATGatewayError):
                exc_val.context.update(self.context)

            # Handle the exception
            full_context = {
                "component": self.component,
                **self.context
            }
            self.error_handler.handle_exception(exc_val, full_context)

            # Don't suppress if reraise is True
            return not self.reraise
        return False


# ============================================================================
# Utility Functions
# ============================================================================

def format_error_for_display(error_info: Dict[str, Any]) -> str:
    """Format error info for user-friendly display"""
    lines = [
        f"❌ Error: {error_info['error_type']}",
        f"Message: {error_info['error_message']}",
    ]

    if 'component' in error_info:
        lines.append(f"Component: {error_info['component']}")

    if 'context' in error_info and error_info['context']:
        lines.append("Context:")
        for key, value in error_info['context'].items():
            lines.append(f"  {key}: {value}")

    return "\n".join(lines)


def get_recent_errors(count: int = 10) -> list:
    """Get recent errors from the error handler"""
    handler = get_error_handler()
    return handler.recent_errors[-count:]


# ============================================================================
# Global Exception Hook (for unhandled exceptions)
# ============================================================================

def install_global_exception_hook():
    """Install global exception handler for unhandled exceptions"""

    def global_exception_handler(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            # Allow keyboard interrupts to pass through
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        # Log the unhandled exception
        error_handler = get_error_handler()
        error_handler.logger.critical(
            f"Unhandled exception: {exc_type.__name__}: {exc_value}",
            exc_info=(exc_type, exc_value, exc_traceback)
        )

        # Handle with error handler
        error_info = error_handler.handle_exception(exc_value)

    sys.excepthook = global_exception_handler


# Auto-install on import
_install_attempted = False
def _ensure_hook_installed():
    global _install_attempted
    if not _install_attempted:
        install_global_exception_hook()
        _install_attempted = True


# Export main classes and functions
__all__ = [
    # Exception classes
    "UATGatewayError",
    "JourneyExtractionError",
    "TestGenerationError",
    "TestExecutionError",
    "TestSelectionError",
    "ResultProcessingError",
    "StateManagementError",
    "KanbanIntegrationError",
    "ConfigurationError",
    "OrchestratorError",
    "AdapterError",
    # Error handling
    "ErrorHandler",
    "get_error_handler",
    "handle_errors",
    "safe_execute",
    "ErrorContext",
    # Utilities
    "format_error_for_display",
    "get_recent_errors",
    "install_global_exception_hook",
]
