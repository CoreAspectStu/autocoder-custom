"""
Network Failure Handler for UAT Gateway

Provides graceful network failure handling with:
- Network failure detection and classification
- Automatic retry with exponential backoff
- User-friendly error notifications
- Circuit breaker pattern for cascading failures
- Network health monitoring

This is the complete, fixed version.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import json
from pathlib import Path

# Add parent directory to path for imports
import sys

from uat_gateway.utils.logger import get_logger


# ============================================================================
# Network Failure Types
# ============================================================================

class NetworkFailureType(Enum):
    """Types of network failures"""
    CONNECTION_REFUSED = "connection_refused"
    CONNECTION_TIMEOUT = "connection_timeout"
    DNS_FAILURE = "dns_failure"
    NETWORK_UNREACHABLE = "network_unreachable"
    SSL_ERROR = "ssl_error"
    PROXY_ERROR = "proxy_error"
    REQUEST_TIMEOUT = "request_timeout"
    SERVER_ERROR_5XX = "server_error_5xx"
    RATE_LIMITED = "rate_limited"
    UNKNOWN = "unknown"


class NetworkErrorSeverity(Enum):
    """Severity levels for network errors"""
    LOW = "low"           # Temporary, auto-recoverable
    MEDIUM = "medium"     # May need user intervention
    HIGH = "high"         # Critical, requires attention
    CRITICAL = "critical" # System-wide issue


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class NetworkFailure:
    """Represents a network failure event"""
    failure_type: NetworkFailureType
    severity: NetworkErrorSeverity
    error_message: str
    url: Optional[str] = None
    status_code: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "failure_type": self.failure_type.value,
            "severity": self.severity.value,
            "error_message": self.error_message,
            "url": self.url,
            "status_code": self.status_code,
            "timestamp": self.timestamp.isoformat(),
            "retry_count": self.retry_count,
            "is_resolved": self.is_resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "context": self.context,
        }


@dataclass
class RetryConfig:
    """Configuration for retry logic"""
    max_retries: int = 3
    initial_backoff_ms: int = 1000
    max_backoff_ms: int = 10000
    backoff_multiplier: float = 2.0
    retry_on_timeout: bool = True
    retry_on_5xx: bool = True
    retry_on_connection_error: bool = True


@dataclass
class CircuitBreakerState:
    """Circuit breaker state to prevent cascading failures"""
    is_open: bool = False
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    success_count: int = 0
    last_success_time: Optional[datetime] = None

    # Thresholds
    failure_threshold: int = 5
    timeout_seconds: int = 60
    half_open_max_calls: int = 3


@dataclass
class NetworkHealthStatus:
    """Overall network health status"""
    is_healthy: bool = True
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    recent_failures: List[NetworkFailure] = field(default_factory=list)
    circuit_breaker_open: bool = False
    last_check: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100


# ============================================================================
# Network Failure Handler
# ============================================================================

class NetworkFailureHandler:
    """
    Handles network failures gracefully with retry logic and circuit breaker
    """

    def __init__(self,
                 retry_config: Optional[RetryConfig] = None,
                 logger: Optional[logging.Logger] = None):
        self.retry_config = retry_config or RetryConfig()
        self.logger = logger or get_logger("network_handler")

        # Circuit breaker state per host
        self.circuit_breakers: Dict[str, CircuitBreakerState] = {}

        # Network health tracking
        self.health_status = NetworkHealthStatus()

        # Failure history (last 100)
        self.failure_history: List[NetworkFailure] = []

        # User notification callbacks
        self.notification_callbacks: List[Callable[[NetworkFailure], None]] = []

    def add_notification_callback(self, callback: Callable[[NetworkFailure], None]):
        """Add a callback to be called on network failures"""
        self.notification_callbacks.append(callback)

    def _notify_user(self, failure: NetworkFailure):
        """Notify user about network failure"""
        for callback in self.notification_callbacks:
            try:
                callback(failure)
            except Exception as e:
                self.logger.error(f"Error in notification callback: {e}")

    def classify_error(self,
                      error: Exception,
                      url: Optional[str] = None,
                      status_code: Optional[int] = None) -> NetworkFailure:
        """
        Classify an exception into a NetworkFailure type

        Args:
            error: The exception that occurred
            url: The URL being requested
            status_code: HTTP status code if available

        Returns:
            NetworkFailure object with classification
        """
        error_message = str(error)
        error_type = NetworkFailureType.UNKNOWN
        severity = NetworkErrorSeverity.MEDIUM

        # Check exception type and message to classify
        error_class_name = error.__class__.__name__.lower()

        if "connectionrefused" in error_class_name or "refused" in error_message.lower():
            error_type = NetworkFailureType.CONNECTION_REFUSED
            severity = NetworkErrorSeverity.HIGH
        elif "connecttimeout" in error_class_name or ("connect" in error_class_name and "timeout" in error_class_name):
            # Specific check for connection timeout (ConnectTimeout)
            error_type = NetworkFailureType.CONNECTION_TIMEOUT
            severity = NetworkErrorSeverity.MEDIUM
        elif "readtimeout" in error_class_name:
            # Specific check for read timeout (ReadTimeout)
            error_type = NetworkFailureType.REQUEST_TIMEOUT
            severity = NetworkErrorSeverity.LOW
        elif "timeout" in error_class_name or "timeout" in error_message.lower():
            # Generic timeout - classify as request timeout
            error_type = NetworkFailureType.REQUEST_TIMEOUT
            severity = NetworkErrorSeverity.LOW
        elif "dns" in error_class_name or "nodename" in error_message.lower():
            error_type = NetworkFailureType.DNS_FAILURE
            severity = NetworkErrorSeverity.HIGH
        elif "networkunreachable" in error_class_name or "unreachable" in error_message.lower():
            error_type = NetworkFailureType.NETWORK_UNREACHABLE
            severity = NetworkErrorSeverity.HIGH
        elif "ssl" in error_class_name or "tls" in error_class_name or "certificate" in error_message.lower():
            error_type = NetworkFailureType.SSL_ERROR
            severity = NetworkErrorSeverity.HIGH
        elif "proxy" in error_class_name or "proxy" in error_message.lower():
            error_type = NetworkFailureType.PROXY_ERROR
            severity = NetworkErrorSeverity.MEDIUM
        elif status_code and 500 <= status_code < 600:
            error_type = NetworkFailureType.SERVER_ERROR_5XX
            severity = NetworkErrorSeverity.MEDIUM if status_code >= 500 else NetworkErrorSeverity.LOW
        elif status_code == 429:
            error_type = NetworkFailureType.RATE_LIMITED
            severity = NetworkErrorSeverity.MEDIUM

        return NetworkFailure(
            failure_type=error_type,
            severity=severity,
            error_message=error_message,
            url=url,
            status_code=status_code,
            context={
                "exception_class": error.__class__.__name__,
                "original_message": error_message,
            }
        )

    def should_retry(self, failure: NetworkFailure, retry_count: int) -> bool:
        """
        Determine if a request should be retried based on failure type

        Args:
            failure: The network failure that occurred
            retry_count: Current retry attempt number

        Returns:
            True if should retry, False otherwise
        """
        # Check max retries
        if retry_count >= self.retry_config.max_retries:
            return False

        # Check retry config based on failure type
        if failure.failure_type == NetworkFailureType.REQUEST_TIMEOUT:
            return self.retry_config.retry_on_timeout
        elif failure.failure_type == NetworkFailureType.SERVER_ERROR_5XX:
            return self.retry_config.retry_on_5xx
        elif failure.failure_type in [
            NetworkFailureType.CONNECTION_REFUSED,
            NetworkFailureType.CONNECTION_TIMEOUT,
            NetworkFailureType.NETWORK_UNREACHABLE,
            NetworkFailureType.DNS_FAILURE,
        ]:
            return self.retry_config.retry_on_connection_error
        elif failure.failure_type == NetworkFailureType.RATE_LIMITED:
            # Don't retry rate limits immediately, let caller handle with backoff
            return False
        elif failure.failure_type == NetworkFailureType.SSL_ERROR:
            # Don't retry SSL errors - won't succeed without fixing cert
            return False
        else:
            # Unknown errors - retry conservatively
            return retry_count < 1

    def calculate_backoff(self, retry_count: int) -> float:
        """
        Calculate exponential backoff delay

        Args:
            retry_count: Current retry attempt number

        Returns:
            Backoff delay in seconds
        """
        backoff = self.retry_config.initial_backoff_ms * (
            self.retry_config.backoff_multiplier ** retry_count
        )
        backoff = min(backoff, self.retry_config.max_backoff_ms)
        return backoff / 1000.0  # Convert to seconds

    def check_circuit_breaker(self, host: str) -> Tuple[bool, Optional[str]]:
        """
        Check if circuit breaker is open for a host

        Args:
            host: The host to check

        Returns:
            Tuple of (is_open, reason)
        """
        if host not in self.circuit_breakers:
            self.circuit_breakers[host] = CircuitBreakerState()

        cb = self.circuit_breakers[host]

        if cb.is_open:
            # Check if timeout has elapsed
            if cb.opened_at and (datetime.now() - cb.opened_at).total_seconds() > cb.timeout_seconds:
                # Transition to half-open state
                self.logger.info(f"Circuit breaker for {host} transitioning to half-open")
                cb.is_open = False
                cb.success_count = 0
                return False, "Circuit breaker half-open"
            else:
                return True, f"Circuit breaker open (opened {cb.opened_at.isoformat()})"

        return False, None

    def record_success(self, host: str):
        """
        Record a successful request for circuit breaker

        Args:
            host: The host that succeeded
        """
        if host not in self.circuit_breakers:
            self.circuit_breakers[host] = CircuitBreakerState()

        cb = self.circuit_breakers[host]

        cb.last_success_time = datetime.now()
        cb.success_count += 1

        # If we were in half-open and got enough successes, close circuit breaker
        if cb.success_count >= cb.half_open_max_calls:
            cb.failure_count = 0
            self.logger.info(f"Circuit breaker for {host} closed after {cb.success_count} successes")

    def record_failure(self, host: str, failure: NetworkFailure):
        """
        Record a failed request for circuit breaker

        Args:
            host: The host that failed
            failure: The failure that occurred
        """
        if host not in self.circuit_breakers:
            self.circuit_breakers[host] = CircuitBreakerState()

        cb = self.circuit_breakers[host]

        cb.failure_count += 1
        cb.last_failure_time = datetime.now()

        # Open circuit breaker if threshold exceeded
        if cb.failure_count >= cb.failure_threshold:
            if not cb.is_open:
                cb.is_open = True
                cb.opened_at = datetime.now()
                self.logger.warning(
                    f"Circuit breaker opened for {host} after {cb.failure_count} failures"
                )

        # Add to health status
        self.health_status.failed_requests += 1
        self.health_status.recent_failures.append(failure)

        # Keep only last 50 failures in recent list
        if len(self.health_status.recent_failures) > 50:
            self.health_status.recent_failures.pop(0)

        # Add to history
        self.failure_history.append(failure)
        if len(self.failure_history) > 100:
            self.failure_history.pop(0)

        # Notify user
        self._notify_user(failure)

    def get_health_status(self) -> NetworkHealthStatus:
        """Get current network health status"""
        self.health_status.last_check = datetime.now()
        self.health_status.circuit_breaker_open = any(
            cb.is_open for cb in self.circuit_breakers.values()
        )
        return self.health_status

    def get_user_friendly_message(self, failure: NetworkFailure) -> str:
        """
        Generate user-friendly error message for a network failure

        Args:
            failure: The network failure

        Returns:
            User-friendly error message
        """
        messages = {
            NetworkFailureType.CONNECTION_REFUSED: (
                "Unable to connect to the server. The server may be down or refusing connections. "
                "Please check your internet connection and try again."
            ),
            NetworkFailureType.CONNECTION_TIMEOUT: (
                "Connection timed out. The server took too long to respond. "
                "Please check your internet connection and try again."
            ),
            NetworkFailureType.DNS_FAILURE: (
                "Unable to find the server address. This may be a DNS issue or the server doesn't exist. "
                "Please check the URL and your internet connection."
            ),
            NetworkFailureType.NETWORK_UNREACHABLE: (
                "Network is unreachable. Please check your internet connection."
            ),
            NetworkFailureType.SSL_ERROR: (
                "Secure connection failed. There may be an issue with the server's security certificate. "
                "Please contact support if this persists."
            ),
            NetworkFailureType.PROXY_ERROR: (
                "Proxy error. There may be an issue with your proxy configuration."
            ),
            NetworkFailureType.REQUEST_TIMEOUT: (
                "Request timed out. The operation took too long to complete. "
                "Please try again."
            ),
            NetworkFailureType.SERVER_ERROR_5XX: (
                "Server error. The server encountered an error while processing your request. "
                "Please try again later. We've been notified of this issue."
            ),
            NetworkFailureType.RATE_LIMITED: (
                "Too many requests. Please wait a moment and try again."
            ),
            NetworkFailureType.UNKNOWN: (
                "Network error occurred. Please check your internet connection and try again."
            ),
        }

        base_message = messages.get(failure.failure_type, messages[NetworkFailureType.UNKNOWN])

        # Add retry info if applicable
        if failure.retry_count > 0:
            base_message += f" (retry attempt {failure.retry_count})"

        return base_message


# ============================================================================
# Decorators for Network Failure Handling
# ============================================================================

def handle_network_failures(
    handler: Optional[NetworkFailureHandler] = None,
    extract_host: Optional[Callable[[Any], str]] = None,
):
    """
    Decorator to handle network failures gracefully

    Args:
        handler: NetworkFailureHandler instance (created if not provided)
        extract_host: Function to extract host from function arguments

    Usage:
        @handle_network_failures()
        async def fetch_data(url):
            return await requests.get(url)
    """
    def decorator(func):
        # Detect if function is async or sync
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:
            # Async wrapper
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                nonlocal handler
                if handler is None:
                    handler = NetworkFailureHandler()

                # Extract URL/host if provided
                url = None
                host = None
                if extract_host:
                    try:
                        host = extract_host((args, kwargs))
                    except Exception:
                        pass

                retry_count = 0
                last_failure = None

                while True:
                    # Check circuit breaker
                    if host:
                        is_open, reason = handler.check_circuit_breaker(host)
                        if is_open:
                            handler.logger.warning(f"Circuit breaker open for {host}: {reason}")
                            # Return error but don't crash
                            return {
                                "success": False,
                                "error": "Service temporarily unavailable (circuit breaker)",
                                "retry_after": 60,
                            }

                    # Update health status
                    handler.health_status.total_requests += 1

                    try:
                        # Attempt the request
                        result = await func(*args, **kwargs)

                        # Record success
                        if host:
                            handler.record_success(host)
                        handler.health_status.successful_requests += 1

                        return result

                    except Exception as e:
                        # Classify the error
                        failure = handler.classify_error(e, url=url)
                        failure.retry_count = retry_count
                        last_failure = failure

                        handler.logger.warning(
                            f"Network error in {func.__name__}: {failure.failure_type.value} - {failure.error_message}"
                        )

                        # Check if we should retry
                        if handler.should_retry(failure, retry_count):
                            retry_count += 1
                            backoff = handler.calculate_backoff(retry_count)

                            handler.logger.info(
                                f"Retrying {func.__name__} in {backoff:.1f}s (attempt {retry_count}/{handler.retry_config.max_retries})"
                            )

                            await asyncio.sleep(backoff)
                            continue
                        else:
                            # Record failure and return error
                            if host:
                                handler.record_failure(host, failure)

                            # Return error response instead of raising
                            user_message = handler.get_user_friendly_message(failure)
                            return {
                                "success": False,
                                "error": user_message,
                                "error_type": failure.failure_type.value,
                                "severity": failure.severity.value,
                                "can_retry": retry_count < handler.retry_config.max_retries,
                                "retry_count": retry_count,
                            }

            return async_wrapper

        else:
            # Sync wrapper
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                nonlocal handler
                if handler is None:
                    handler = NetworkFailureHandler()

                # Extract URL/host if provided
                url = None
                host = None
                if extract_host:
                    try:
                        host = extract_host((args, kwargs))
                    except Exception:
                        pass

                retry_count = 0
                last_failure = None

                while True:
                    # Check circuit breaker
                    if host:
                        is_open, reason = handler.check_circuit_breaker(host)
                        if is_open:
                            handler.logger.warning(f"Circuit breaker open for {host}: {reason}")
                            # Return error but don't crash
                            return {
                                "success": False,
                                "error": "Service temporarily unavailable (circuit breaker)",
                                "retry_after": 60,
                            }

                    # Update health status
                    handler.health_status.total_requests += 1

                    try:
                        # Attempt the request
                        result = func(*args, **kwargs)

                        # Record success
                        if host:
                            handler.record_success(host)
                        handler.health_status.successful_requests += 1

                        return result

                    except Exception as e:
                        # Classify the error
                        failure = handler.classify_error(e, url=url)
                        failure.retry_count = retry_count
                        last_failure = failure

                        handler.logger.warning(
                            f"Network error in {func.__name__}: {failure.failure_type.value} - {failure.error_message}"
                        )

                        # Check if we should retry
                        if handler.should_retry(failure, retry_count):
                            retry_count += 1
                            backoff = handler.calculate_backoff(retry_count)

                            handler.logger.info(
                                f"Retrying {func.__name__} in {backoff:.1f}s (attempt {retry_count}/{handler.retry_config.max_retries})"
                            )

                            time.sleep(backoff)
                            continue
                        else:
                            # Record failure and return error
                            if host:
                                handler.record_failure(host, failure)

                            # Return error response instead of raising
                            user_message = handler.get_user_friendly_message(failure)
                            return {
                                "success": False,
                                "error": user_message,
                                "error_type": failure.failure_type.value,
                                "severity": failure.severity.value,
                                "can_retry": retry_count < handler.retry_config.max_retries,
                                "retry_count": retry_count,
                            }

            return sync_wrapper

    return decorator


# ============================================================================
# Export
# ============================================================================

__all__ = [
    "NetworkFailureType",
    "NetworkErrorSeverity",
    "NetworkFailure",
    "RetryConfig",
    "CircuitBreakerState",
    "NetworkHealthStatus",
    "NetworkFailureHandler",
    "handle_network_failures",
]
