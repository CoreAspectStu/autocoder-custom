"""
UAT Gateway API Server

Provides a REST API for the UAT Gateway with JWT authentication and rate limiting.
"""

from .server import create_app
from .rate_limiter import RateLimiterMiddleware, RateLimitError
from .auth import JWTAuthenticator, AuthenticationError, TokenPayload

__all__ = [
    'create_app',
    'RateLimiterMiddleware',
    'RateLimitError',
    'JWTAuthenticator',
    'AuthenticationError',
    'TokenPayload'
]
