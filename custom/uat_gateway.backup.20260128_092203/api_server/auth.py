"""
JWT Authentication for UAT Gateway API

Implements JWT token-based authentication for API endpoints
with comprehensive security audit logging.
"""

import os
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass
import secrets
import logging

logger = logging.getLogger(__name__)


@dataclass
class AuthConfig:
    """Configuration for JWT authentication"""
    secret_key: str
    algorithm: str = "HS256"
    token_expiry_hours: int = 24


@dataclass
class TokenPayload:
    """JWT token payload"""
    user_id: str
    username: str
    role: str = "user"  # Default role for backward compatibility
    exp: datetime = None
    iat: datetime = None


class AuthenticationError(Exception):
    """Raised when authentication fails"""
    pass


class JWTAuthenticator:
    """
    JWT-based authentication for API endpoints

    Features:
    - JWT token generation
    - Token validation
    - Token refresh support
    - Configurable expiry time
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        token_expiry_hours: int = 24
    ):
        """
        Initialize JWT authenticator

        Args:
            secret_key: Secret key for signing tokens (default: from env or random)
            algorithm: JWT algorithm (default: HS256)
            token_expiry_hours: Token expiry time in hours (default: 24)
        """
        # Use provided secret, environment variable, or generate a random one
        self.secret_key = secret_key or os.getenv(
            "JWT_SECRET_KEY",
            secrets.token_hex(32)  # Generate random key for development
        )

        # Warn if using random key (not suitable for production)
        if not secret_key and not os.getenv("JWT_SECRET_KEY"):
            logger.warning(
                "Using randomly generated JWT secret key. "
                "Set JWT_SECRET_KEY environment variable for production."
            )
            logger.warning(f"Generated key: {self.secret_key}")

        self.config = AuthConfig(
            secret_key=self.secret_key,
            algorithm=algorithm,
            token_expiry_hours=token_expiry_hours
        )

        # Initialize security audit logger
        self._init_security_logger()

        logger.info(f"JWT authenticator initialized (algorithm: {algorithm})")

    def _init_security_logger(self):
        """Initialize security audit logger (lazy import to avoid circular dependency)"""
        try:
            from custom.uat_gateway.utils.security_audit_logger import get_security_audit_logger
            self.security_logger = get_security_audit_logger()
        except ImportError:
            # If security logger not available, use None
            self.security_logger = None

    def create_token(
        self,
        user_id: str,
        username: str,
        role: str = "user",
        expiry_hours: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """
        Create a JWT token for a user

        Args:
            user_id: User's unique identifier
            username: User's username
            role: User's role (admin, user, viewer, etc.)
            expiry_hours: Override default expiry time
            ip_address: Client IP address for audit logging

        Returns:
            JWT token string
        """
        now = datetime.utcnow()
        expiry_hours_final = expiry_hours or self.config.token_expiry_hours
        expiry = now + timedelta(hours=expiry_hours_final)

        payload = {
            "user_id": user_id,
            "username": username,
            "role": role,
            "iat": now.timestamp(),
            "exp": expiry.timestamp()
        }

        token = jwt.encode(
            payload,
            self.config.secret_key,
            algorithm=self.config.algorithm
        )

        logger.debug(f"Created token for user '{username}' (expires: {expiry})")

        # Log token creation
        if self.security_logger:
            self.security_logger.log_token_created(
                user_id=user_id,
                username=username,
                expiry_hours=expiry_hours_final,
                ip_address=ip_address
            )

        return token

    def validate_token(self, token: str, ip_address: Optional[str] = None) -> TokenPayload:
        """
        Validate a JWT token

        Args:
            token: JWT token string
            ip_address: Client IP address for audit logging

        Returns:
            TokenPayload with decoded token data

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        try:
            # Decode and verify token
            decoded = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm]
            )

            # Extract payload fields
            user_id = decoded.get("user_id")
            username = decoded.get("username")
            role = decoded.get("role", "user")  # Default to 'user' for backward compatibility
            exp_timestamp = decoded.get("exp")
            iat_timestamp = decoded.get("iat")

            # Validate required fields
            if not all([user_id, username, exp_timestamp, iat_timestamp]):
                raise AuthenticationError("Token missing required fields")

            # Convert timestamps to datetime (UTC for consistency)
            exp = datetime.utcfromtimestamp(exp_timestamp)
            iat = datetime.utcfromtimestamp(iat_timestamp)

            payload = TokenPayload(
                user_id=user_id,
                username=username,
                role=role,
                exp=exp,
                iat=iat
            )

            logger.debug(f"Validated token for user '{username}'")

            # Log successful token validation
            if self.security_logger:
                self.security_logger.log_token_validated(
                    user_id=user_id,
                    username=username,
                    ip_address=ip_address
                )

            return payload

        except jwt.ExpiredSignatureError:
            # Log expired token attempt
            if self.security_logger:
                self.security_logger.log_token_expired(ip_address=ip_address)
            raise AuthenticationError("Token has expired")
        except jwt.InvalidTokenError as e:
            # Log invalid token attempt
            if self.security_logger:
                self.security_logger.log_token_invalid(
                    ip_address=ip_address,
                    reason=str(e)
                )
            raise AuthenticationError(f"Invalid token: {str(e)}")
        except Exception as e:
            if self.security_logger:
                self.security_logger.log_token_invalid(
                    ip_address=ip_address,
                    reason=str(e)
                )
            raise AuthenticationError(f"Token validation failed: {str(e)}")

    def refresh_token(self, token: str) -> str:
        """
        Refresh an existing token

        Args:
            token: Current valid token

        Returns:
            New JWT token with extended expiry

        Raises:
            AuthenticationError: If current token is invalid
        """
        # Validate current token
        payload = self.validate_token(token)

        # Create new token with same user data
        return self.create_token(
            user_id=payload.user_id,
            username=payload.username,
            role=payload.role
        )

    def get_token_expiry(self, token: str) -> datetime:
        """
        Get expiry datetime of a token

        Args:
            token: JWT token string

        Returns:
            Datetime when token expires

        Raises:
            AuthenticationError: If token is invalid
        """
        payload = self.validate_token(token)
        return payload.exp

    def is_token_expired(self, token: str) -> bool:
        """
        Check if a token is expired

        Args:
            token: JWT token string

        Returns:
            True if token is expired, False otherwise
        """
        try:
            expiry = self.get_token_expiry(token)
            return datetime.utcnow() > expiry
        except AuthenticationError:
            return True


def create_authenticator() -> JWTAuthenticator:
    """
    Create a JWT authenticator with default configuration

    Returns:
        JWTAuthenticator instance
    """
    return JWTAuthenticator()


# Note: get_current_user and get_current_user_optional are defined in server.py
# because they need access to the enable_auth flag and authenticator instance
# They are FastAPI dependencies used throughout the API
