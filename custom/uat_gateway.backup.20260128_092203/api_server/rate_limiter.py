"""
Rate Limiting Middleware for UAT Gateway API

Implements token bucket rate limiting to prevent API abuse.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
import hashlib


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    requests_per_minute: int = 60  # Default: 60 requests per minute
    requests_per_hour: int = 1000   # Default: 1000 requests per hour
    burst_size: int = 10            # Default: Allow bursts of 10


@dataclass
class ClientBucket:
    """Token bucket for a client"""
    tokens: float  # Current token count
    last_update: float  # Unix timestamp of last update
    requests_in_window: list = field(default_factory=list)  # Request timestamps in current window


@dataclass
class RateLimitInfo:
    """Information about current rate limit status"""
    remaining: int  # Remaining requests in current window
    reset_time: datetime  # When the rate limit window resets
    limit: int  # Maximum requests per window
    window: str  # Window size ('minute' or 'hour')


class RateLimiterMiddleware:
    """
    Rate limiting middleware using sliding window algorithm

    Features:
    - Per-client rate limiting (identified by IP address or API key)
    - Sliding window for accurate rate limiting
    - Configurable limits (per-minute and per-hour)
    - Returns 429 status when limit exceeded
    - Includes Retry-After header
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_size: int = 10,
        redis_url: Optional[str] = None
    ):
        """
        Initialize rate limiter

        Args:
            requests_per_minute: Maximum requests per minute per client
            requests_per_hour: Maximum requests per hour per client
            burst_size: Maximum burst size (allows temporary spikes)
            redis_url: Optional Redis URL for distributed rate limiting
        """
        self.config = RateLimitConfig(
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
            burst_size=burst_size
        )

        # Use in-memory storage for single-instance deployment
        # Redis would be used for distributed deployments
        self.client_buckets: Dict[str, ClientBucket] = defaultdict(
            lambda: ClientBucket(
                tokens=float(burst_size),
                last_update=time.time()
            )
        )

        self.redis_enabled = redis_url is not None
        if self.redis_enabled:
            # TODO: Initialize Redis client for distributed rate limiting
            pass

    def _get_client_identifier(self, request) -> str:
        """
        Get unique identifier for client

        Priority:
        1. API key from X-API-Key header
        2. X-Client-ID header (for testing/debugging)
        3. API key from query parameter
        4. Client IP address

        Args:
            request: FastAPI request object

        Returns:
            Client identifier string
        """
        # Try API key from header first
        api_key = request.headers.get('X-API-Key')
        if api_key:
            # Hash API key for privacy
            return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

        # Try X-Client-ID header (useful for testing)
        client_id = request.headers.get('X-Client-ID')
        if client_id:
            return f"client:{client_id}"

        # Try API key from query parameter
        if hasattr(request, 'query_params'):
            api_key = request.query_params.get('api_key')
            if api_key:
                return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

        # Fall back to IP address
        if hasattr(request, 'client') and request.client:
            return f"ip:{request.client.host}"

        # Last resort: use test client identifier for consistent testing
        # In production with real requests, request.client should always be set
        return "testclient:default"

    def _clean_old_requests(self, bucket: ClientBucket, window_seconds: int) -> None:
        """
        Remove request timestamps outside the current time window

        Args:
            bucket: Client's token bucket
            window_seconds: Window size in seconds (60 for minute, 3600 for hour)
        """
        current_time = time.time()
        cutoff_time = current_time - window_seconds

        # Remove timestamps outside the window
        bucket.requests_in_window = [
            ts for ts in bucket.requests_in_window
            if ts > cutoff_time
        ]

    def _check_rate_limit(
        self,
        client_id: str,
        window: str = 'minute'
    ) -> Tuple[bool, RateLimitInfo]:
        """
        Check if client has exceeded rate limit

        Args:
            client_id: Unique client identifier
            window: 'minute' or 'hour'

        Returns:
            Tuple of (allowed: bool, rate_limit_info: RateLimitInfo)
        """
        # Determine window size and limit
        if window == 'minute':
            window_seconds = 60
            limit = self.config.requests_per_minute
        elif window == 'hour':
            window_seconds = 3600
            limit = self.config.requests_per_hour
        else:
            raise ValueError(f"Invalid window: {window}. Use 'minute' or 'hour'")

        # Get or create client bucket
        bucket = self.client_buckets[client_id]
        current_time = time.time()

        # Clean old requests outside the window
        self._clean_old_requests(bucket, window_seconds)

        # Check if limit exceeded
        request_count = len(bucket.requests_in_window)
        remaining = max(0, limit - request_count)
        allowed = request_count < limit

        # Calculate reset time
        if bucket.requests_in_window:
            oldest_request = min(bucket.requests_in_window)
            reset_timestamp = oldest_request + window_seconds
        else:
            reset_timestamp = current_time + window_seconds

        reset_time = datetime.fromtimestamp(reset_timestamp)

        rate_limit_info = RateLimitInfo(
            remaining=remaining,
            reset_time=reset_time,
            limit=limit,
            window=window
        )

        return allowed, rate_limit_info

    def _record_request(self, client_id: str) -> None:
        """
        Record a request for the client

        Args:
            client_id: Unique client identifier
        """
        bucket = self.client_buckets[client_id]
        bucket.last_update = time.time()
        bucket.requests_in_window.append(time.time())

    async def check_rate_limit(self, request) -> Tuple[bool, Optional[RateLimitInfo]]:
        """
        Check if request should be rate limited

        This is the main entry point for middleware integration

        Args:
            request: FastAPI request object

        Returns:
            Tuple of (allowed: bool, rate_limit_info: Optional[RateLimitInfo])

        Raises:
            RateLimitError: If rate limit is exceeded
        """
        client_id = self._get_client_identifier(request)

        # Check per-minute limit
        allowed_minute, info_minute = self._check_rate_limit(client_id, 'minute')

        if not allowed_minute:
            # Rate limit exceeded - raise error
            raise RateLimitError(info_minute)

        # Check per-hour limit
        allowed_hour, info_hour = self._check_rate_limit(client_id, 'hour')

        if not allowed_hour:
            # Hourly limit exceeded - raise error
            raise RateLimitError(info_hour)

        # Request allowed - record it
        self._record_request(client_id)

        # Return most restrictive limit info
        return True, info_minute if info_minute.remaining < info_hour.remaining else info_hour

    def get_retry_after_seconds(self, rate_limit_info: RateLimitInfo) -> int:
        """
        Calculate Retry-After header value in seconds

        Args:
            rate_limit_info: Rate limit information

        Returns:
            Seconds until client can retry
        """
        current_time = datetime.now()
        delta = rate_limit_info.reset_time - current_time
        return max(1, int(delta.total_seconds()))

    def get_rate_limit_headers(self, rate_limit_info: RateLimitInfo) -> Dict[str, str]:
        """
        Generate rate limit headers for response

        Args:
            rate_limit_info: Rate limit information

        Returns:
            Dictionary of headers to include in response
        """
        retry_after = self.get_retry_after_seconds(rate_limit_info)

        return {
            'X-RateLimit-Limit': str(rate_limit_info.limit),
            'X-RateLimit-Remaining': str(rate_limit_info.remaining),
            'X-RateLimit-Reset': rate_limit_info.reset_time.isoformat(),
            'Retry-After': str(retry_after)
        }

    def reset_client(self, client_id: str) -> None:
        """
        Reset rate limit for a specific client (admin function)

        Args:
            client_id: Client identifier to reset
        """
        if client_id in self.client_buckets:
            del self.client_buckets[client_id]

    def get_stats(self) -> Dict[str, any]:
        """
        Get statistics about rate limiting

        Returns:
            Dictionary with rate limiting statistics
        """
        total_clients = len(self.client_buckets)
        total_requests = sum(
            len(bucket.requests_in_window)
            for bucket in self.client_buckets.values()
        )

        return {
            'total_clients': total_clients,
            'total_requests_in_window': total_requests,
            'requests_per_minute': self.config.requests_per_minute,
            'requests_per_hour': self.config.requests_per_hour,
            'burst_size': self.config.burst_size
        }


class RateLimitError(Exception):
    """Exception raised when rate limit is exceeded"""

    def __init__(self, rate_limit_info: RateLimitInfo):
        self.rate_limit_info = rate_limit_info
        super().__init__(
            f"Rate limit exceeded: {rate_limit_info.remaining}/{rate_limit_info.limit} "
            f"requests remaining for {rate_limit_info.window} window. "
            f"Resets at {rate_limit_info.reset_time.isoformat()}"
        )
