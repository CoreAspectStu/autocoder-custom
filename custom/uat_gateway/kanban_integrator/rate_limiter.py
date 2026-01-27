"""
Rate Limiter for Kanban API calls

Implements token bucket rate limiting with:
- Configurable requests per time window
- Automatic retry with exponential backoff
- Rate limit error detection
- Graceful handling of API limits
"""

import time
import logging
import sys
from pathlib import Path
from typing import Optional, Callable, Any, Dict
from functools import wraps
from datetime import datetime, timedelta
from threading import Lock


from uat_gateway.utils.errors import KanbanIntegrationError
from uat_gateway.utils.logger import get_logger


class RateLimitError(KanbanIntegrationError):
    """Raised when API rate limit is exceeded"""
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class RateLimiter:
    """
    Token bucket rate limiter for API calls

    Ensures API calls don't exceed configured rate limits by tracking
    available tokens and replenishing them over time.

    Example:
        limiter = RateLimiter(requests_per_second=10)

        @limiter.rate_limited
        def make_api_call():
            # This will automatically wait if rate limit is approached
            return api_client.create_card(...)

    Usage:
        # Create limiter: 100 requests per minute
        limiter = RateLimiter(requests_per_minute=100)

        # Use as decorator
        @limiter.rate_limited
        def create_card(card_data):
            return api.create(card_data)

        # Or use context manager
        with limiter:
            result = api.create_card(card_data)
    """

    def __init__(self,
                 requests_per_second: Optional[float] = None,
                 requests_per_minute: Optional[int] = None,
                 burst_capacity: int = 10):
        """
        Initialize rate limiter

        Args:
            requests_per_second: Maximum requests per second (alternative to per_minute)
            requests_per_minute: Maximum requests per minute (default: 60 if not specified)
            burst_capacity: Maximum burst size (default: 10)
        """
        self.logger = get_logger(__name__)
        self._lock = Lock()

        # Determine rate limit
        if requests_per_second is not None:
            self.requests_per_second = requests_per_second
            self.requests_per_minute = int(requests_per_second * 60)
        elif requests_per_minute is not None:
            self.requests_per_minute = requests_per_minute
            self.requests_per_second = requests_per_minute / 60.0
        else:
            # Default: 60 requests per minute (1 per second)
            self.requests_per_minute = 60
            self.requests_per_second = 1.0

        # Token bucket parameters
        self.burst_capacity = burst_capacity
        self.tokens = float(burst_capacity)  # Start with full bucket
        self.last_update = datetime.now()

        # Rate limit window tracking
        self.request_timestamps = []  # Track request times for sliding window

        # Statistics
        self.total_requests = 0
        self.rate_limit_hits = 0
        self.total_wait_time = 0.0

        self.logger.info(
            f"RateLimiter initialized: {self.requests_per_minute} req/min, "
            f"burst capacity: {burst_capacity}"
        )

    def _add_request_timestamp(self):
        """Add current request timestamp and clean old ones"""
        now = datetime.now()
        window_start = now - timedelta(minutes=1)

        # Add current request
        self.request_timestamps.append(now)

        # Remove timestamps older than 1 minute
        self.request_timestamps = [
            ts for ts in self.request_timestamps if ts > window_start
        ]

    def _get_requests_in_last_minute(self) -> int:
        """Get count of requests in the last minute"""
        window_start = datetime.now() - timedelta(minutes=1)
        return len([ts for ts in self.request_timestamps if ts > window_start])

    def _would_exceed_rate_limit(self) -> bool:
        """Check if making a request now would exceed rate limit"""
        requests_in_window = self._get_requests_in_last_minute()
        return requests_in_window >= self.requests_per_minute

    def _wait_until_available(self, timeout: float = 60.0):
        """
        Wait until rate limit capacity is available

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            RateLimitError: If timeout is exceeded
        """
        start_time = time.time()

        while self._would_exceed_rate_limit():
            elapsed = time.time() - start_time

            if elapsed >= timeout:
                raise RateLimitError(
                    f"Rate limit timeout after {timeout}s waiting for capacity",
                    retry_after=1.0
                )

            # Calculate how long to wait
            requests_in_window = self._get_requests_in_last_minute()
            if requests_in_window > 0:
                # Wait until oldest request is outside the window
                oldest_request = self.request_timestamps[0]
                wait_until = oldest_request + timedelta(minutes=1)
                wait_seconds = (wait_until - datetime.now()).total_seconds()

                if wait_seconds > 0:
                    # Add small buffer and cap wait time
                    wait_seconds = min(wait_seconds + 0.1, 1.0)
                    self.logger.debug(
                        f"Rate limit approaching, waiting {wait_seconds:.2f}s "
                        f"({requests_in_window}/{self.requests_per_minute} requests)"
                    )
                    time.sleep(wait_seconds)
                    self.total_wait_time += wait_seconds
            else:
                # Shouldn't happen, but sleep briefly just in case
                time.sleep(0.1)

    def acquire(self, timeout: float = 60.0):
        """
        Acquire permission to make an API request

        Blocks until rate limit capacity is available.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            RateLimitError: If timeout is exceeded
        """
        with self._lock:
            self._wait_until_available(timeout)
            self._add_request_timestamp()
            self.total_requests += 1

    def release(self):
        """
        Release a request (for error cases where request wasn't actually made)

        This is called when a request fails before actually hitting the API.
        """
        with self._lock:
            if self.request_timestamps:
                self.request_timestamps.pop()
                self.total_requests = max(0, self.total_requests - 1)

    def __enter__(self):
        """Context manager entry - acquire rate limit"""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - nothing to clean up"""
        return False

    def rate_limited(self, max_retries: int = 3, initial_backoff: float = 1.0):
        """
        Decorator to make a function rate-limited with retry logic

        Args:
            max_retries: Maximum number of retries on rate limit errors
            initial_backoff: Initial backoff time in seconds (doubles each retry)

        Example:
            @limiter.rate_limited(max_retries=3)
            def create_card(data):
                return api.create(data)
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                backoff = initial_backoff

                for attempt in range(max_retries + 1):
                    try:
                        # Acquire rate limit
                        self.acquire()

                        # Call the function
                        return func(*args, **kwargs)

                    except RateLimitError as e:
                        self.logger.warning(
                            f"Rate limit hit in {func.__name__} "
                            f"(attempt {attempt + 1}/{max_retries + 1})"
                        )
                        self.rate_limit_hits += 1

                        # Release the failed attempt
                        self.release()

                        # If we have retries left, wait and retry
                        if attempt < max_retries:
                            wait_time = backoff * (2 ** attempt)
                            self.logger.info(
                                f"Retrying {func.__name__} after {wait_time:.2f}s"
                            )
                            time.sleep(wait_time)
                        else:
                            # Re-raise after final attempt
                            raise

                    except Exception as e:
                        # For non-rate-limit errors, release and re-raise
                        self.release()
                        raise

                # Shouldn't reach here, but just in case
                raise KanbanIntegrationError(
                    f"Failed after {max_retries} retries"
                )

            return wrapper
        return decorator

    def get_stats(self) -> Dict[str, Any]:
        """
        Get rate limiter statistics

        Returns:
            Dictionary with statistics
        """
        requests_in_window = self._get_requests_in_last_minute()

        return {
            "requests_per_minute_limit": self.requests_per_minute,
            "requests_in_last_minute": requests_in_window,
            "remaining_capacity": max(0, self.requests_per_minute - requests_in_window),
            "total_requests": self.total_requests,
            "rate_limit_hits": self.rate_limit_hits,
            "total_wait_time_seconds": round(self.total_wait_time, 2),
            "average_wait_time_seconds": round(
                self.total_wait_time / max(1, self.total_requests), 3
            ) if self.total_requests > 0 else 0.0,
        }

    def reset_stats(self):
        """Reset statistics counters"""
        with self._lock:
            self.total_requests = 0
            self.rate_limit_hits = 0
            self.total_wait_time = 0.0
            self.request_timestamps = []


# ============================================================================
# Default rate limiter instance
# ============================================================================

# Default limiter: 100 requests per minute (industry standard for many APIs)
_default_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the default rate limiter instance"""
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = RateLimiter(requests_per_minute=100)
    return _default_limiter


def reset_rate_limiter():
    """Reset the default rate limiter (mainly for testing)"""
    global _default_limiter
    _default_limiter = None


# ============================================================================
# Utility functions
# ============================================================================

def retry_on_rate_limit(max_retries: int = 3,
                       initial_backoff: float = 1.0,
                       rate_limiter: Optional[RateLimiter] = None):
    """
    Decorator to retry function calls on rate limit errors

    Args:
        max_retries: Maximum number of retries
        initial_backoff: Initial backoff time in seconds
        rate_limiter: Custom rate limiter (uses default if None)

    Example:
        @retry_on_rate_limit(max_retries=5)
        def create_many_cards(cards):
            for card in cards:
                api.create(card)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            limiter = rate_limiter or get_rate_limiter()
            backoff = initial_backoff

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:
                    if attempt < max_retries:
                        wait_time = backoff * (2 ** attempt)
                        get_logger(__name__).warning(
                            f"Rate limit in {func.__name__}, "
                            f"retrying in {wait_time:.2f}s (attempt {attempt + 1})"
                        )
                        time.sleep(wait_time)
                    else:
                        raise

            raise KanbanIntegrationError(
                f"Failed {func.__name__} after {max_retries} retries"
            )

        return wrapper
    return decorator


__all__ = [
    "RateLimiter",
    "RateLimitError",
    "get_rate_limiter",
    "reset_rate_limiter",
    "retry_on_rate_limit",
]
