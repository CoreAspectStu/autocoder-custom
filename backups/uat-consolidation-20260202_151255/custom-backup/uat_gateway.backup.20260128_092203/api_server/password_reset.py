"""
Password Reset Module with Expiring Tokens

Implements secure password reset functionality with time-limited tokens
that expire after a configurable duration (default: 1 hour).
"""

import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class PasswordResetToken:
    """Represents a password reset token with expiration"""
    token: str
    username: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    is_used: bool = False

    def __post_init__(self):
        """Set expiration time if not provided"""
        if self.expires_at is None:
            # Default: 1 hour expiration
            self.expires_at = self.created_at + timedelta(hours=1)

    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not used)"""
        if self.is_used:
            return False
        if datetime.now() > self.expires_at:
            return False
        return True

    def is_expired(self) -> bool:
        """Check if token is expired"""
        return datetime.now() > self.expires_at

    def to_dict(self) -> Dict:
        """Convert to dictionary (excluding sensitive token hash)"""
        return {
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "is_used": self.is_used,
            "is_valid": self.is_valid(),
            "is_expired": self.is_expired(),
        }


class PasswordResetManager:
    """
    Manages password reset tokens with expiration

    Features:
    - Generate secure reset tokens
    - Token expiration (default: 1 hour)
    - Token validation
    - Token usage tracking
    - Automatic cleanup of expired tokens
    """

    def __init__(self, token_expiry_hours: int = 1):
        """
        Initialize password reset manager

        Args:
            token_expiry_hours: Hours until token expires (default: 1)
        """
        self.token_expiry_hours = token_expiry_hours
        # Store tokens by token hash (SHA256 for security)
        self.tokens: Dict[str, PasswordResetToken] = {}
        # Index by username for quick lookup
        self.tokens_by_user: Dict[str, str] = {}  # username -> token_hash

        logger.info(f"Password reset manager initialized (token expiry: {token_expiry_hours}h)")

    def _hash_token(self, token: str) -> str:
        """Hash a token for secure storage"""
        return hashlib.sha256(token.encode()).hexdigest()

    def generate_token(self, username: str, email: str) -> str:
        """
        Generate a new password reset token

        Args:
            username: Username requesting reset
            email: Email address of user

        Returns:
            Raw reset token (to be sent to user via email)
        """
        # Invalidate any existing tokens for this user
        self.invalidate_user_tokens(username)

        # Generate secure random token
        token = secrets.token_urlsafe(32)

        # Create token record
        reset_token = PasswordResetToken(
            token=token,  # Will be stored hashed
            username=username,
            email=email,
            expires_at=datetime.now() + timedelta(hours=self.token_expiry_hours)
        )

        # Store hashed token
        token_hash = self._hash_token(token)
        self.tokens[token_hash] = reset_token
        self.tokens_by_user[username] = token_hash

        logger.info(f"Generated reset token for user '{username}' (expires: {reset_token.expires_at})")

        # Return raw token (to be sent via email)
        return token

    def validate_token(self, token: str) -> Optional[PasswordResetToken]:
        """
        Validate a password reset token

        Args:
            token: Reset token to validate

        Returns:
            PasswordResetToken if valid, None otherwise
        """
        token_hash = self._hash_token(token)
        reset_token = self.tokens.get(token_hash)

        if not reset_token:
            logger.warning(f"Invalid reset token attempted")
            return None

        if not reset_token.is_valid():
            if reset_token.is_used:
                logger.warning(f"Attempted to use already-used token for user '{reset_token.username}'")
            else:
                logger.warning(f"Attempted to use expired token for user '{reset_token.username}'")
            return None

        logger.info(f"Valid reset token for user '{reset_token.username}'")
        return reset_token

    def use_token(self, token: str) -> Optional[PasswordResetToken]:
        """
        Mark a token as used (after successful password reset)

        Args:
            token: Reset token to mark as used

        Returns:
            PasswordResetToken if valid, None otherwise
        """
        reset_token = self.validate_token(token)
        if reset_token:
            reset_token.is_used = True
            logger.info(f"Reset token marked as used for user '{reset_token.username}'")
        return reset_token

    def invalidate_user_tokens(self, username: str) -> int:
        """
        Invalidate all tokens for a specific user

        Args:
            username: Username to invalidate tokens for

        Returns:
            Number of tokens invalidated
        """
        token_hash = self.tokens_by_user.get(username)
        if token_hash and token_hash in self.tokens:
            reset_token = self.tokens[token_hash]
            reset_token.is_used = True  # Mark as used to invalidate
            logger.info(f"Invalidated existing token for user '{username}'")
            return 1
        return 0

    def cleanup_expired_tokens(self) -> int:
        """
        Remove expired tokens from storage

        Returns:
            Number of tokens removed
        """
        expired_hashes = [
            token_hash for token_hash, token in self.tokens.items()
            if token.is_expired()
        ]

        for token_hash in expired_hashes:
            token = self.tokens.pop(token_hash)
            # Remove from user index
            if token.username in self.tokens_by_user:
                if self.tokens_by_user[token.username] == token_hash:
                    del self.tokens_by_user[token.username]

        if expired_hashes:
            logger.info(f"Cleaned up {len(expired_hashes)} expired tokens")

        return len(expired_hashes)

    def get_token_info(self, username: str) -> Optional[Dict]:
        """
        Get information about the current active token for a user

        Args:
            username: Username to query

        Returns:
            Dictionary with token info or None if no active token
        """
        token_hash = self.tokens_by_user.get(username)
        if not token_hash:
            return None

        token = self.tokens.get(token_hash)
        if not token or not token.is_valid():
            return None

        return token.to_dict()


# Global password reset manager instance
_password_reset_manager = None


def get_password_reset_manager() -> PasswordResetManager:
    """Get the global password reset manager instance"""
    global _password_reset_manager
    if _password_reset_manager is None:
        _password_reset_manager = PasswordResetManager()
    return _password_reset_manager
