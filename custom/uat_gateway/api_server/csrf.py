"""
CSRF Protection Middleware for UAT Gateway API

Implements CSRF token validation for state-changing operations.
While JWT Bearer tokens are used for authentication, CSRF protection
adds an additional layer of security against cross-site request forgery.
"""

import secrets
import logging
from typing import Optional, Dict, Set
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class CSRFTokenManager:
    """
    Manages CSRF token generation and validation

    CSRF tokens are stored in-memory with a timestamp for expiry.
    In production, consider using Redis or another distributed cache.
    """

    def __init__(self, token_expiry_minutes: int = 60):
        """
        Initialize CSRF token manager

        Args:
            token_expiry_minutes: How long tokens remain valid (default: 60 minutes)
        """
        self.token_expiry_minutes = token_expiry_minutes
        # In-memory token storage (token -> timestamp)
        self._tokens: Dict[str, datetime] = {}
        # Track which tokens have been used (to prevent replay attacks)
        self._used_tokens: Set[str] = set()

        logger.info(f"CSRF token manager initialized (expiry: {token_expiry_minutes} minutes)")

    def generate_token(self) -> str:
        """
        Generate a new CSRF token

        Returns:
            URL-safe random token
        """
        token = secrets.token_urlsafe(32)
        self._tokens[token] = datetime.utcnow()
        logger.debug(f"Generated CSRF token: {token[:8]}... (length: {len(token)})")
        return token

    def validate_token(self, token: str) -> bool:
        """
        Validate a CSRF token

        Args:
            token: CSRF token to validate

        Returns:
            True if token is valid, False otherwise
        """
        # Check if token has already been used (replay attack prevention)
        if token in self._used_tokens:
            logger.warning(f"CSRF token already used: {token[:8]}...")
            return False

        # Check if token exists
        if token not in self._tokens:
            logger.warning(f"CSRF token not found: {token[:8]}...")
            return False

        # Check if token has expired
        token_time = self._tokens[token]
        expiry_time = datetime.utcnow() - timedelta(minutes=self.token_expiry_minutes)

        if token_time < expiry_time:
            logger.warning(f"CSRF token expired: {token[:8]}...")
            # Clean up expired token
            del self._tokens[token]
            return False

        logger.debug(f"CSRF token validated: {token[:8]}...")
        return True

    def consume_token(self, token: str) -> bool:
        """
        Validate and consume a CSRF token (prevents reuse)

        Args:
            token: CSRF token to consume

        Returns:
            True if token was valid and consumed, False otherwise
        """
        if not self.validate_token(token):
            return False

        # Mark token as used
        self._used_tokens.add(token)
        # Remove from active tokens
        del self._tokens[token]

        logger.debug(f"CSRF token consumed: {token[:8]}...")
        return True

    def clean_expired_tokens(self):
        """Remove expired tokens from storage (maintenance)"""
        expiry_time = datetime.utcnow() - timedelta(minutes=self.token_expiry_minutes)
        expired = [t for t, time in self._tokens.items() if time < expiry_time]

        for token in expired:
            del self._tokens[token]

        if expired:
            logger.info(f"Cleaned {len(expired)} expired CSRF tokens")

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about token storage"""
        return {
            "active_tokens": len(self._tokens),
            "used_tokens": len(self._used_tokens)
        }


# Global CSRF token manager instance
_csrf_manager: Optional[CSRFTokenManager] = None


def get_csrf_manager() -> CSRFTokenManager:
    """Get the global CSRF token manager instance"""
    global _csrf_manager
    if _csrf_manager is None:
        _csrf_manager = CSRFTokenManager()
    return _csrf_manager


async def verify_csrf_token(request: Request) -> None:
    """
    Dependency function to verify CSRF token for state-changing requests

    This should be used in POST, PUT, DELETE, PATCH endpoints.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: If CSRF token is missing or invalid
    """
    # Skip CSRF check for safe methods
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return

    # Get CSRF token from header first (preferred method)
    csrf_token = request.headers.get("X-CSRF-Token")

    # Only try to read body if token not in header
    # NOTE: We don't read the body here to avoid consuming it
    # If client wants CSRF in body, they MUST use header

    # Validate token
    if not csrf_token:
        logger.warning(f"CSRF token missing for {request.method} {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "csrf_token_missing",
                "message": "CSRF token is required for this request",
                "hint": "Include X-CSRF-Token header with valid CSRF token"
            }
        )

    csrf_manager = get_csrf_manager()

    if not csrf_manager.validate_token(csrf_token):
        logger.warning(f"CSRF token invalid for {request.method} {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "csrf_token_invalid",
                "message": "CSRF token is invalid or expired",
                "hint": "Get a fresh CSRF token from /api/csrf-token"
            }
        )

    # Token is valid, but don't consume it yet
    # (consumption happens after the main endpoint succeeds)
    request.state.csrf_token = csrf_token
    logger.debug(f"CSRF token verified for {request.method} {request.url.path}")


def consume_csrf_token(request: Request) -> None:
    """
    Consume a validated CSRF token after successful request

    This should be called after the main endpoint logic succeeds

    Args:
        request: FastAPI request object
    """
    csrf_token = getattr(request.state, "csrf_token", None)
    if csrf_token:
        csrf_manager = get_csrf_manager()
        csrf_manager.consume_token(csrf_token)
        logger.debug(f"CSRF token consumed after successful {request.method} {request.url.path}")
