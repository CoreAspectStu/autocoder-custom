"""
User Authentication and Authorization Module

This module provides user authentication and role-based authorization
for the UAT Gateway system with comprehensive security audit logging.
"""

import secrets
import hashlib
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta


class UserRole(Enum):
    """User roles with different permission levels"""
    ADMIN = "admin"           # Full access to all operations
    TESTER = "tester"         # Can trigger and view UAT runs
    VIEWER = "viewer"         # Read-only access to results
    GUEST = "guest"           # Limited access, no UAT triggering


@dataclass
class User:
    """Represents a user in the system"""
    user_id: str
    username: str
    email: str
    role: UserRole
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True
    api_token_hash: Optional[str] = None
    # Two-Factor Authentication (2FA) fields
    totp_secret: Optional[str] = None  # TOTP secret for 2FA
    totp_enabled: bool = False  # Whether 2FA is enabled
    backup_codes: List[str] = field(default_factory=list)  # Backup codes for recovery
    totp_enabled_at: Optional[datetime] = None  # When 2FA was enabled

    def has_permission(self, required_role: UserRole) -> bool:
        """
        Check if user has the required permission level

        Role hierarchy: ADMIN > TESTER > VIEWER > GUEST
        """
        role_hierarchy = {
            UserRole.GUEST: 0,
            UserRole.VIEWER: 1,
            UserRole.TESTER: 2,
            UserRole.ADMIN: 3,
        }

        user_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        return user_level >= required_level if self.is_active else False

    def to_dict(self) -> Dict:
        """Convert to dictionary (excluding sensitive data)"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role.value,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "totp_enabled": self.totp_enabled,
            "totp_enabled_at": self.totp_enabled_at.isoformat() if self.totp_enabled_at else None,
        }


class UserAuth:
    """
    User authentication and authorization manager

    Manages users, validates credentials, and checks permissions.
    All security events are logged for audit purposes.
    """

    def __init__(self):
        """Initialize the authentication system"""
        self.users: Dict[str, User] = {}
        self.api_tokens: Dict[str, str] = {}  # token -> user_id

        # Initialize security audit logger
        self._init_security_logger()

        # Create default admin user for development
        self._create_default_admin()

    def _init_security_logger(self):
        """Initialize security audit logger (lazy import to avoid circular dependency)"""
        try:
            from uat_gateway.utils.security_audit_logger import get_security_audit_logger
            self.security_logger = get_security_audit_logger()
        except ImportError:
            # If security logger not available, use None
            self.security_logger = None

    def _create_default_admin(self):
        """Create a default admin user for development/testing"""
        admin = User(
            user_id="admin-001",
            username="admin",
            email="admin@uat-gateway.local",
            role=UserRole.ADMIN,
        )

        # Generate default API token
        default_token = "uat-admin-token-dev-001"
        token_hash = self._hash_token(default_token)

        admin.api_token_hash = token_hash
        self.users[admin.user_id] = admin
        self.api_tokens[default_token] = admin.user_id

    def _hash_token(self, token: str) -> str:
        """Hash an API token for storage"""
        return hashlib.sha256(token.encode()).hexdigest()

    def verify_token(self, token: str, ip_address: Optional[str] = None) -> Optional[User]:
        """
        Verify an API token and return the associated user

        Args:
            token: API token to verify
            ip_address: Client IP address for audit logging

        Returns:
            User object if token is valid, None otherwise
        """
        if not token:
            if self.security_logger:
                self.security_logger.log_token_invalid(ip_address=ip_address, reason="No token provided")
            return None

        token_hash = self._hash_token(token)
        user_id = self.api_tokens.get(token)

        if not user_id:
            if self.security_logger:
                self.security_logger.log_token_invalid(ip_address=ip_address, reason="Token not found in system")
            return None

        user = self.users.get(user_id)
        if not user or not user.is_active:
            if self.security_logger:
                self.security_logger.log_token_invalid(
                    ip_address=ip_address,
                    reason="User not found or inactive"
                )
            return None

        # Verify the hash matches
        if user.api_token_hash != token_hash:
            if self.security_logger:
                self.security_logger.log_token_invalid(
                    ip_address=ip_address,
                    reason="Token hash mismatch"
                )
            return None

        # Log successful token validation
        if self.security_logger:
            self.security_logger.log_token_validated(
                user_id=user.user_id,
                username=user.username,
                ip_address=ip_address
            )

        return user

    def create_user(
        self,
        username: str,
        email: str,
        role: UserRole,
        created_by: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> User:
        """
        Create a new user

        Args:
            username: Username
            email: Email address
            role: User role
            created_by: User ID of creator (for auditing)
            ip_address: IP address of creator (for audit logging)

        Returns:
            Created User object

        Raises:
            ValueError: If username/email already exists
        """
        # Check for duplicates
        for user in self.users.values():
            if user.username == username:
                raise ValueError(f"Username '{username}' already exists")
            if user.email == email:
                raise ValueError(f"Email '{email}' already exists")

        # Generate user ID and API token
        user_id = f"user-{secrets.token_hex(4)}"
        api_token = f"uat-token-{secrets.token_urlsafe(32)}"
        token_hash = self._hash_token(api_token)

        user = User(
            user_id=user_id,
            username=username,
            email=email,
            role=role,
            api_token_hash=token_hash,
        )

        self.users[user_id] = user
        self.api_tokens[api_token] = user_id

        # Log user creation
        if self.security_logger:
            self.security_logger.log_user_created(
                user_id=user_id,
                username=username,
                role=role.value,
                created_by=created_by,
                ip_address=ip_address
            )

        return user

    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID"""
        return self.users.get(user_id)

    def list_users(self) -> List[User]:
        """List all users"""
        return list(self.users.values())

    def deactivate_user(self, user_id: str, deactivated_by: Optional[str] = None, ip_address: Optional[str] = None) -> bool:
        """
        Deactivate a user account

        Args:
            user_id: ID of user to deactivate
            deactivated_by: User ID performing the deactivation
            ip_address: IP address for audit logging

        Returns:
            True if user was deactivated, False if not found
        """
        user = self.users.get(user_id)
        if user:
            username = user.username
            user.is_active = False

            # Log deactivation
            if self.security_logger:
                self.security_logger.log_user_deactivated(
                    user_id=user_id,
                    username=username,
                    deactivated_by=deactivated_by,
                    ip_address=ip_address
                )

            return True
        return False

    def check_permission(self, user: User, required_role: UserRole, resource: Optional[str] = None, ip_address: Optional[str] = None) -> bool:
        """
        Check if a user has the required permission level

        Args:
            user: User to check
            required_role: Required role level
            resource: Resource being accessed (for audit logging)
            ip_address: Client IP address (for audit logging)

        Returns:
            True if user has permission, False otherwise
        """
        has_permission = user.has_permission(required_role)

        # Log permission denial
        if not has_permission and self.security_logger:
            self.security_logger.log_permission_denied(
                user_id=user.user_id,
                username=user.username,
                resource=resource or "unknown",
                required_role=required_role.value,
                user_role=user.role.value,
                ip_address=ip_address
            )

        return has_permission

    # ========================================================================
    # Two-Factor Authentication (2FA) Methods
    # ========================================================================

    def enable_totp_for_user(
        self,
        user_id: str,
        totp_secret: str,
        backup_codes: List[str],
        enabled_by: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Enable TOTP (2FA) for a user

        Args:
            user_id: ID of user to enable 2FA for
            totp_secret: TOTP secret key
            backup_codes: List of backup codes for recovery
            enabled_by: User ID who enabled 2FA (for auditing)
            ip_address: IP address for audit logging

        Returns:
            True if 2FA was enabled, False if user not found
        """
        user = self.users.get(user_id)
        if not user:
            logger.warning(f"Cannot enable 2FA: user {user_id} not found")
            return False

        user.totp_secret = totp_secret
        user.totp_enabled = True
        user.backup_codes = backup_codes
        user.totp_enabled_at = datetime.now()

        logger.info(f"2FA enabled for user '{user.username}'")

        # Log 2FA enabled
        if self.security_logger:
            self.security_logger.log_security_event(
                event_type="2fa_enabled",
                user_id=user_id,
                username=user.username,
                details={"enabled_by": enabled_by},
                ip_address=ip_address
            )

        return True

    def disable_totp_for_user(
        self,
        user_id: str,
        disabled_by: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Disable TOTP (2FA) for a user

        Args:
            user_id: ID of user to disable 2FA for
            disabled_by: User ID who disabled 2FA (for auditing)
            ip_address: IP address for audit logging

        Returns:
            True if 2FA was disabled, False if user not found
        """
        user = self.users.get(user_id)
        if not user:
            logger.warning(f"Cannot disable 2FA: user {user_id} not found")
            return False

        username = user.username
        user.totp_secret = None
        user.totp_enabled = False
        user.backup_codes = []
        user.totp_enabled_at = None

        logger.info(f"2FA disabled for user '{username}'")

        # Log 2FA disabled
        if self.security_logger:
            self.security_logger.log_security_event(
                event_type="2fa_disabled",
                user_id=user_id,
                username=username,
                details={"disabled_by": disabled_by},
                ip_address=ip_address
            )

        return True

    def verify_totp_for_user(self, user_id: str, totp_code: str, ip_address: Optional[str] = None) -> bool:
        """
        Verify TOTP code for a user

        Args:
            user_id: ID of user
            totp_code: TOTP code to verify
            ip_address: IP address for audit logging

        Returns:
            True if code is valid, False otherwise
        """
        user = self.users.get(user_id)
        if not user or not user.totp_enabled or not user.totp_secret:
            logger.warning(f"TOTP verification failed: user {user_id} not found or 2FA not enabled")
            return False

        # Import TOTP authenticator
        from uat_gateway.utils.totp import get_totp_authenticator
        totp_auth = get_totp_authenticator()

        # Verify code
        is_valid = totp_auth.verify_totp(user.totp_secret, totp_code)

        if is_valid:
            logger.info(f"TOTP verified for user '{user.username}'")

            # Log successful 2FA verification
            if self.security_logger:
                self.security_logger.log_security_event(
                    event_type="2fa_verified",
                    user_id=user_id,
                    username=user.username,
                    details={"method": "totp"},
                    ip_address=ip_address
                )
        else:
            logger.warning(f"TOTP verification failed for user '{user.username}'")

            # Log failed 2FA attempt
            if self.security_logger:
                self.security_logger.log_security_event(
                    event_type="2fa_failed",
                    user_id=user_id,
                    username=user.username,
                    details={"method": "totp", "reason": "invalid_code"},
                    ip_address=ip_address
                )

        return is_valid

    def verify_backup_code_for_user(
        self,
        user_id: str,
        backup_code: str,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify and consume a backup code for a user

        Backup codes are single-use, so they are removed after successful verification.

        Args:
            user_id: ID of user
            backup_code: Backup code to verify
            ip_address: IP address for audit logging

        Returns:
            Tuple of (is_valid, remaining_count)
        """
        user = self.users.get(user_id)
        if not user or not user.totp_enabled:
            logger.warning(f"Backup code verification failed: user {user_id} not found or 2FA not enabled")
            return False, None

        # Import TOTP authenticator
        from uat_gateway.utils.totp import get_totp_authenticator
        totp_auth = get_totp_authenticator()

        # Verify backup code
        is_valid, used_code = totp_auth.verify_backup_code(backup_code, user.backup_codes)

        if is_valid and used_code:
            # Remove used backup code
            user.backup_codes.remove(used_code)

            logger.info(f"Backup code verified for user '{user.username}', {len(user.backup_codes)} remaining")

            # Log successful backup code use
            if self.security_logger:
                self.security_logger.log_security_event(
                    event_type="2fa_verified",
                    user_id=user_id,
                    username=user.username,
                    details={
                        "method": "backup_code",
                        "remaining_codes": len(user.backup_codes)
                    },
                    ip_address=ip_address
                )

            return True, f"{len(user.backup_codes)} codes remaining"
        else:
            logger.warning(f"Backup code verification failed for user '{user.username}'")

            # Log failed backup code attempt
            if self.security_logger:
                self.security_logger.log_security_event(
                    event_type="2fa_failed",
                    user_id=user_id,
                    username=user.username,
                    details={"method": "backup_code", "reason": "invalid_code"},
                    ip_address=ip_address
                )

            return False, None

    def regenerate_backup_codes_for_user(
        self,
        user_id: str,
        new_backup_codes: List[str],
        regenerated_by: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Regenerate backup codes for a user

        Args:
            user_id: ID of user
            new_backup_codes: New list of backup codes
            regenerated_by: User ID who regenerated codes (for auditing)
            ip_address: IP address for audit logging

        Returns:
            True if codes were regenerated, False if user not found or 2FA not enabled
        """
        user = self.users.get(user_id)
        if not user or not user.totp_enabled:
            logger.warning(f"Cannot regenerate backup codes: user {user_id} not found or 2FA not enabled")
            return False

        user.backup_codes = new_backup_codes

        logger.info(f"Backup codes regenerated for user '{user.username}' ({len(new_backup_codes)} codes)")

        # Log backup codes regenerated
        if self.security_logger:
            self.security_logger.log_security_event(
                event_type="2fa_backup_codes_regenerated",
                user_id=user_id,
                username=user.username,
                details={
                    "regenerated_by": regenerated_by,
                    "code_count": len(new_backup_codes)
                },
                ip_address=ip_address
            )

        return True
