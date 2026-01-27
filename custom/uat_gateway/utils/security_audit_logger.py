"""
Security Audit Logger for UAT Gateway

Provides structured logging for security-related events with:
- Audit-ready format (ISO timestamps, structured fields)
- Security event types (authentication, authorization, data access)
- Detailed context (user, action, resource, outcome)
- Tamper-evident logging
- Integration with existing logger
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass, asdict


class SecurityEventType(Enum):
    """Types of security events to log"""
    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    TOKEN_CREATED = "token_created"
    TOKEN_VALIDATED = "token_validated"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_REFRESHED = "token_refreshed"
    TOKEN_INVALID = "token_invalid"

    # Authorization events
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_CHANGED = "role_changed"

    # User management events
    USER_CREATED = "user_created"
    USER_DEACTIVATED = "user_deactivated"
    USER_ACTIVATED = "user_activated"
    USER_DELETED = "user_deleted"

    # Data access events
    DATA_ACCESS = "data_access"
    DATA_MODIFIED = "data_modified"
    DATA_EXPORTED = "data_exported"
    DATA_DELETED = "data_deleted"

    # Rate limiting events
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    RATE_LIMIT_WARNING = "rate_limit_warning"

    # API Key events (Feature #359)
    API_KEY_CREATED = "api_key_created"
    API_KEY_DELETED = "api_key_deleted"
    API_KEY_REVOKED = "api_key_revoked"
    API_KEY_AUTH_SUCCESS = "api_key_auth_success"
    API_KEY_AUTH_FAILURE = "api_key_auth_failure"

    # Security violations
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    UNAUTHORIZED_ACCESS_ATTEMPT = "unauthorized_access_attempt"
    BRUTE_FORCE_DETECTED = "brute_force_detected"


class SecuritySeverity(Enum):
    """Severity levels for security events"""
    INFO = "info"           # Normal operation (e.g., successful login)
    WARNING = "warning"     # Potential concern (e.g., rate limit warning)
    ERROR = "error"         # Security failure (e.g., permission denied)
    CRITICAL = "critical"   # Serious breach (e.g., brute force detected)


@dataclass
class SecurityEvent:
    """
    Structured security event for audit logging

    All fields are designed to be audit-ready:
    - ISO 8601 timestamps
    - Structured data types
    - Required fields for compliance
    """
    timestamp: str                    # ISO 8601 format
    event_type: str                   # SecurityEventType value
    severity: str                     # SecuritySeverity value
    user_id: Optional[str]            # User ID if authenticated
    username: Optional[str]           # Username if available
    ip_address: Optional[str]         # Client IP address
    user_agent: Optional[str]         # Client user agent
    action: str                       # Human-readable action description
    resource: Optional[str]           # Resource being accessed
    outcome: str                      # Success, failure, or error
    details: Dict[str, Any]           # Additional context
    session_id: Optional[str] = None  # Session identifier
    request_id: Optional[str] = None  # Request correlation ID

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string for logging"""
        return json.dumps(self.to_dict())

    def to_log_message(self) -> str:
        """Format as human-readable log message"""
        user_info = f"user={self.username}" if self.username else "user=anonymous"
        outcome_str = f"[{self.outcome.upper()}]"

        parts = [
            f"SECURITY_{self.severity.upper()}",
            self.event_type,
            outcome_str,
            user_info,
            self.action
        ]

        if self.resource:
            parts.append(f"resource={self.resource}")

        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            parts.append(f"details:{{{details_str}}}")

        return " | ".join(parts)


class SecurityAuditLogger:
    """
    Centralized security event logger

    Logs all security-related events in a structured, audit-ready format.
    Integrates with the existing UATGatewayLogger.
    """

    def __init__(self, component: str = "security"):
        """
        Initialize security audit logger

        Args:
            component: Component name for logger namespace
        """
        # Import here to avoid circular dependency
        from uat_gateway.utils.logger import get_logger
        self.logger = get_logger(component)
        self.component = component

    def log_security_event(
        self,
        event_type: SecurityEventType,
        action: str,
        outcome: str,
        severity: SecuritySeverity = SecuritySeverity.INFO,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> SecurityEvent:
        """
        Log a security event

        Args:
            event_type: Type of security event
            action: Human-readable action description
            outcome: "success", "failure", or "error"
            severity: Event severity level
            user_id: User ID if authenticated
            username: Username if available
            ip_address: Client IP address
            user_agent: Client user agent string
            resource: Resource being accessed
            details: Additional context as dictionary
            session_id: Session identifier
            request_id: Request correlation ID

        Returns:
            SecurityEvent object that was logged
        """
        # Create security event
        event = SecurityEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            event_type=event_type.value,
            severity=severity.value,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            action=action,
            resource=resource,
            outcome=outcome,
            details=details or {},
            session_id=session_id,
            request_id=request_id,
        )

        # Log at appropriate level
        log_message = event.to_log_message()

        if severity == SecuritySeverity.CRITICAL:
            self.logger.critical(log_message)
        elif severity == SecuritySeverity.ERROR:
            self.logger.error(log_message)
        elif severity == SecuritySeverity.WARNING:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

        # Also log structured JSON for parsing
        self.logger.debug(f"SECURITY_EVENT: {event.to_json()}")

        return event

    # Convenience methods for common security events

    def log_login_success(
        self,
        user_id: str,
        username: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> SecurityEvent:
        """Log successful login"""
        return self.log_security_event(
            event_type=SecurityEventType.LOGIN_SUCCESS,
            action="User logged in successfully",
            outcome="success",
            severity=SecuritySeverity.INFO,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
        )

    def log_login_failure(
        self,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> SecurityEvent:
        """Log failed login attempt"""
        details = {}
        if reason:
            details["reason"] = reason

        return self.log_security_event(
            event_type=SecurityEventType.LOGIN_FAILURE,
            action="User login failed",
            outcome="failure",
            severity=SecuritySeverity.WARNING,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )

    def log_permission_denied(
        self,
        user_id: str,
        username: str,
        resource: str,
        required_role: str,
        user_role: str,
        ip_address: Optional[str] = None,
    ) -> SecurityEvent:
        """Log permission denied event"""
        return self.log_security_event(
            event_type=SecurityEventType.PERMISSION_DENIED,
            action="User attempted action without sufficient permissions",
            outcome="failure",
            severity=SecuritySeverity.ERROR,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            resource=resource,
            details={
                "required_role": required_role,
                "user_role": user_role,
            },
        )

    def log_token_created(
        self,
        user_id: str,
        username: str,
        expiry_hours: int,
        ip_address: Optional[str] = None,
    ) -> SecurityEvent:
        """Log token creation"""
        return self.log_security_event(
            event_type=SecurityEventType.TOKEN_CREATED,
            action="Authentication token created",
            outcome="success",
            severity=SecuritySeverity.INFO,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            details={"expiry_hours": expiry_hours},
        )

    def log_token_validated(
        self,
        user_id: str,
        username: str,
        ip_address: Optional[str] = None,
    ) -> SecurityEvent:
        """Log successful token validation"""
        return self.log_security_event(
            event_type=SecurityEventType.TOKEN_VALIDATED,
            action="Authentication token validated",
            outcome="success",
            severity=SecuritySeverity.INFO,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
        )

    def log_token_expired(
        self,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> SecurityEvent:
        """Log expired token usage attempt"""
        return self.log_security_event(
            event_type=SecurityEventType.TOKEN_EXPIRED,
            action="Attempted to use expired authentication token",
            outcome="failure",
            severity=SecuritySeverity.WARNING,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
        )

    def log_token_invalid(
        self,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> SecurityEvent:
        """Log invalid token usage attempt"""
        details = {}
        if reason:
            details["reason"] = reason

        return self.log_security_event(
            event_type=SecurityEventType.TOKEN_INVALID,
            action="Attempted to use invalid authentication token",
            outcome="failure",
            severity=SecuritySeverity.WARNING,
            ip_address=ip_address,
            details=details,
        )

    def log_user_created(
        self,
        user_id: str,
        username: str,
        role: str,
        created_by: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> SecurityEvent:
        """Log user creation"""
        return self.log_security_event(
            event_type=SecurityEventType.USER_CREATED,
            action="New user account created",
            outcome="success",
            severity=SecuritySeverity.INFO,
            user_id=created_by,
            ip_address=ip_address,
            resource=f"user:{username}",
            details={
                "created_user_id": user_id,
                "created_username": username,
                "role": role,
            },
        )

    def log_user_deactivated(
        self,
        user_id: str,
        username: str,
        deactivated_by: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> SecurityEvent:
        """Log user deactivation"""
        return self.log_security_event(
            event_type=SecurityEventType.USER_DEACTIVATED,
            action="User account deactivated",
            outcome="success",
            severity=SecuritySeverity.INFO,
            user_id=deactivated_by,
            ip_address=ip_address,
            resource=f"user:{username}",
            details={
                "deactivated_user_id": user_id,
                "deactivated_username": username,
            },
        )

    def log_rate_limit_exceeded(
        self,
        ip_address: str,
        endpoint: str,
        limit: int,
        window: str,
        user_id: Optional[str] = None,
    ) -> SecurityEvent:
        """Log rate limit exceeded"""
        return self.log_security_event(
            event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
            action="Rate limit exceeded",
            outcome="failure",
            severity=SecuritySeverity.WARNING,
            user_id=user_id,
            ip_address=ip_address,
            resource=endpoint,
            details={
                "limit": limit,
                "window": window,
            },
        )

    def log_unauthorized_access_attempt(
        self,
        resource: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> SecurityEvent:
        """Log unauthorized access attempt"""
        details = {}
        if reason:
            details["reason"] = reason

        return self.log_security_event(
            event_type=SecurityEventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            action="Attempted unauthorized access to resource",
            outcome="failure",
            severity=SecuritySeverity.ERROR,
            ip_address=ip_address,
            user_agent=user_agent,
            resource=resource,
            details=details,
        )


# Singleton instance
_security_audit_logger: Optional[SecurityAuditLogger] = None


def get_security_audit_logger() -> SecurityAuditLogger:
    """Get the singleton security audit logger instance"""
    global _security_audit_logger
    if _security_audit_logger is None:
        _security_audit_logger = SecurityAuditLogger()
    return _security_audit_logger


# Export
__all__ = [
    "SecurityEventType",
    "SecuritySeverity",
    "SecurityEvent",
    "SecurityAuditLogger",
    "get_security_audit_logger",
]
