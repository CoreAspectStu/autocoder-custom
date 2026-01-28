"""
UAT Gateway API Server

FastAPI-based REST API with JWT authentication and rate limiting middleware.
"""

from fastapi import FastAPI, Request, Response, HTTPException, status, Depends, Body, UploadFile, File
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import uvicorn
import logging
import os
import tempfile
import shutil
from pathlib import Path

from .rate_limiter import RateLimiterMiddleware, RateLimitError, RateLimitInfo
from .auth import JWTAuthenticator, AuthenticationError, TokenPayload
from .api_key_auth import APIKeyAuthenticator, APIKey
from .user_preferences import get_preferences_manager
from .error_handler import ErrorHandler, create_error_response, UserFriendlyError, ErrorCode
from .csrf import get_csrf_manager, verify_csrf_token, consume_csrf_token
from .password_validator import PasswordValidator, validate_password, get_password_requirements
from .password_reset import get_password_reset_manager
from .email_validator import EmailValidator, validate_email
from .journey_state_machine import (
    JourneyStatus,
    JourneyStateMachine,
    get_journey_state_machine
)
from .journey_persistence import get_journey_persistence
# from .two_factor_auth import register_2fa_routes  # Temporarily disabled - import error
from custom.uat_gateway.utils.validation import (
    JourneyNameValidator,
    validate_journey_name,
    validate_journey_data,
    ConfigValidator,
    ValidationError
)
from custom.uat_gateway.utils.file_validator import (
    FileUploadValidator,
    FileSecurityLevel,
    FileValidationResult
)
from custom.uat_gateway.utils.result_archiver import (
    ResultArchiver,
    TestResult,
    ArchiveConfig,
    create_result_archiver
)
from custom.uat_gateway.utils.result_annotations import (
    AnnotationStore,
    Annotation,
    get_annotation_store
)
from custom.uat_gateway.utils.pdf_exporter import create_pdf_exporter
from custom.uat_gateway.utils.input_sanitizer import (
    InputSanitizer,
    SecurityLevel,
    get_sanitizer,
    SanitizationResult
)
from custom.uat_gateway.utils.security_audit_logger import (
    get_security_audit_logger,
    SecurityEventType,
    SecuritySeverity
)


logger = logging.getLogger(__name__)
security_audit_logger = get_security_audit_logger()

# Security scheme for JWT tokens
security = HTTPBearer(auto_error=False)

# Feature #353: XSS Protection - Initialize input sanitizer
# Use MODERATE security level for production (detects and escapes XSS)
input_sanitizer = get_sanitizer()


def sanitize_string(value: Any) -> str:
    """
    Sanitize a string value to prevent XSS attacks

    Feature #353: XSS Protection in User Input
    - Escapes HTML special characters
    - Detects script tags and event handlers
    - Returns safe HTML entities

    Args:
        value: Any value to sanitize (converted to string)

    Returns:
        Sanitized string with HTML entities escaped
    """
    if value is None:
        return ""

    # Convert to string if not already
    text = str(value)

    # Use the input sanitizer to escape HTML
    # This converts < to &lt;, > to &gt;, etc.
    sanitized = input_sanitizer._sanitize_string(text)

    # Also explicitly escape HTML entities for display safety
    html_escape_map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#x27;',
        '/': '&#x2F;',
    }

    for char, entity in html_escape_map.items():
        sanitized = sanitized.replace(char, entity)

    return sanitized


def sanitize_dict(data: Dict[str, Any], fields_to_sanitize: List[str]) -> Dict[str, Any]:
    """
    Sanitize specific string fields in a dictionary

    Feature #353: XSS Protection
    - Recursively sanitizes specified fields
    - Escapes HTML to prevent script execution
    - Preserves non-string fields unchanged

    Args:
        data: Dictionary containing user input
        fields_to_sanitize: List of field names to sanitize

    Returns:
        Dictionary with specified fields sanitized
    """
    if not isinstance(data, dict):
        return data

    sanitized = data.copy()

    for field in fields_to_sanitize:
        if field in sanitized and sanitized[field] is not None:
            # Sanitize string values
            sanitized[field] = sanitize_string(sanitized[field])

    return sanitized


def sanitize_test_result(result_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize test result data to prevent XSS

    Feature #353: Sanitizes user-provided test data
    - test_name: May contain malicious scripts
    - error_message: May contain malicious scripts
    - metadata values: May contain malicious scripts

    Args:
        result_data: Raw test result data

    Returns:
        Sanitized test result data
    """
    # Fields that may contain user input and need sanitization
    user_input_fields = ['test_name', 'error_message', 'journey_id']

    sanitized = sanitize_dict(result_data, user_input_fields)

    # Also sanitize metadata values if present
    if 'metadata' in sanitized and isinstance(sanitized['metadata'], dict):
        sanitized['metadata'] = {
            k: sanitize_string(v) if isinstance(v, str) else v
            for k, v in sanitized['metadata'].items()
        }

    return sanitized


def sanitize_journey_data(journey_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize journey data to prevent XSS

    Feature #353: Sanitizes user-provided journey data
    - name: Journey name may contain scripts
    - description: Description may contain scripts
    - scenario names: May contain scripts

    Args:
        journey_data: Raw journey data

    Returns:
        Sanitized journey data
    """
    # Fields that may contain user input
    user_input_fields = ['name', 'description']

    sanitized = sanitize_dict(journey_data, user_input_fields)

    # Also sanitize step names if present
    if 'steps' in sanitized and isinstance(sanitized['steps'], list):
        for step in sanitized['steps']:
            if isinstance(step, dict) and 'name' in step:
                step['name'] = sanitize_string(step['name'])

    # Sanitize scenario names
    if 'scenarios' in sanitized and isinstance(sanitized['scenarios'], list):
        for scenario in sanitized['scenarios']:
            if isinstance(scenario, dict) and 'name' in scenario:
                scenario['name'] = sanitize_string(scenario['name'])

    return sanitized





def get_session_token(request: Request) -> Optional[str]:
    """
    Extract session token from cookie

    Feature #362: Support cookie-based authentication

    Args:
        request: FastAPI request

    Returns:
        Session token from cookie or None
    """
    return request.cookies.get("session_token")


def get_auth_token(
    request: Request,
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """
    Get authentication token from either:
    1. Authorization header (Bearer token) for APIs
    2. Session cookie for web UI

    Feature #362: Hybrid authentication support

    Args:
        request: FastAPI request
        bearer_token: Bearer token from Authorization header

    Returns:
        JWT token or None
    """
    # First check Authorization header (API clients)
    if bearer_token:
        return bearer_token.credentials

    # Then check session cookie (web UI)
    session_token = get_session_token(request)
    if session_token:
        return session_token

    return None


# Security scheme for API keys (X-API-Key header)
class APIKeyHeader:
    """Custom security scheme for X-API-Key header"""
    async def __call__(self, request: Request) -> Optional[str]:
        return request.headers.get("X-API-Key")

api_key_security = APIKeyHeader()


# Demo users for testing (in production, use a real database)
# Each user has a role: admin, user, or viewer
DEMO_USERS = {
    "admin": {"password": "admin123", "role": "admin"},  # Change in production!
    "test": {"password": "test123", "role": "user"},
    "user": {"password": "user123", "role": "user"},
    "viewer": {"password": "viewer123", "role": "viewer"}
}


def create_app(
    jwt_secret_key: Optional[str] = None,
    requests_per_minute: int = 60,
    requests_per_hour: int = 1000,
    burst_size: int = 10,
    enable_rate_limiting: bool = True,
    enable_auth: bool = True
) -> FastAPI:
    """
    Create and configure FastAPI application

    Args:
        jwt_secret_key: Secret key for JWT signing
        requests_per_minute: Rate limit per minute per client
        requests_per_hour: Rate limit per hour per client
        burst_size: Maximum burst size
        enable_rate_limiting: Whether to enable rate limiting
        enable_auth: Whether to enable JWT authentication

    Returns:
        Configured FastAPI application
    """

    app = FastAPI(
        title="UAT Gateway API",
        description="User Acceptance Testing Gateway API with authentication and rate limiting",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify allowed origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize JWT authenticator
    authenticator = None
    if enable_auth:
        authenticator = JWTAuthenticator(secret_key=jwt_secret_key)
        logger.info("JWT authentication enabled")

    # Initialize API key authenticator
    api_key_authenticator = None
    if enable_auth:
        api_key_authenticator = APIKeyAuthenticator()
        logger.info("API key authentication enabled")

    # Initialize rate limiter
    rate_limiter = None
    if enable_rate_limiting:
        rate_limiter = RateLimiterMiddleware(
            requests_per_minute=requests_per_minute,
            requests_per_hour=requests_per_hour,
            burst_size=burst_size
        )

    # Rate limiting middleware
    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        """Apply rate limiting to all requests"""
        if not rate_limiter:
            # Rate limiting disabled, proceed normally
            return await call_next(request)

        # Skip rate limiting for health check and documentation
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        try:
            # Check rate limit
            allowed, rate_limit_info = await rate_limiter.check_rate_limit(request)

            # Add rate limit headers to all responses
            response = await call_next(request)

            if rate_limit_info:
                headers = rate_limiter.get_rate_limit_headers(rate_limit_info)
                for key, value in headers.items():
                    response.headers[key] = value

            return response

        except RateLimitError as e:
            # Rate limit exceeded - return user-friendly error
            rate_limit_info = e.rate_limit_info
            headers = rate_limiter.get_rate_limit_headers(rate_limit_info)

            # Transform to user-friendly error
            user_friendly_error = ErrorHandler.handle_rate_limit_error(
                str(e),
                {
                    "limit": rate_limit_info.limit,
                    "remaining": rate_limit_info.remaining,
                    "reset_time": rate_limit_info.reset_time.isoformat()
                }
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=user_friendly_error.to_dict(),
                headers=headers
            )

    # Security headers middleware
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        """Add security headers to all responses"""
        response = await call_next(request)

        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Content Security Policy
        # Allow only same-origin by default, with specific exceptions
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Allow inline scripts for development
            "style-src 'self' 'unsafe-inline'",  # Allow inline styles
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # XSS Protection (legacy, but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy (restrict browser features)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # HSTS (HTTP Strict Transport Security) - only in production with HTTPS
        # Commented out for development (HTTP)
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response

    # ========================================================================
    # Authentication Dependencies
    # ========================================================================

    async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> TokenPayload:
        """
        Validate JWT token and return current user

        Args:
            credentials: HTTP Bearer credentials

        Returns:
            TokenPayload with user information, or anonymous user if auth disabled

        Raises:
            HTTPException: If authentication fails
        """
        if not enable_auth or authenticator is None:
            # Auth disabled - return anonymous user
            now = datetime.now()
            return TokenPayload(
                user_id="anonymous",
                username="anonymous",
                role="viewer",  # Anonymous users have viewer role
                exp=now + timedelta(hours=24),  # No real expiry for anonymous
                iat=now
            )

        if credentials is None:
            # Transform to user-friendly error message
            user_friendly_error = ErrorHandler.handle_auth_error("No authentication token provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=user_friendly_error.user_message,
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = credentials.credentials

        try:
            # Validate token
            payload = authenticator.validate_token(token)
            return payload

        except AuthenticationError as e:
            # Transform authentication error to user-friendly message
            user_friendly_error = ErrorHandler.handle_auth_error(str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=user_friendly_error.user_message,
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def get_current_user_optional(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> Optional[TokenPayload]:
        """
        Validate JWT token and return current user (optional authentication)

        Unlike get_current_user, this returns None instead of raising an exception
        if authentication fails. Useful for endpoints that work with or without auth.

        Args:
            credentials: HTTP Bearer credentials (optional)

        Returns:
            TokenPayload with user information, or None if not authenticated
        """
        if not enable_auth or authenticator is None:
            # Auth disabled - return anonymous user
            now = datetime.now()
            return TokenPayload(
                user_id="anonymous",
                username="anonymous",
                exp=now + timedelta(hours=24),  # No real expiry for anonymous
                iat=now
            )

        if credentials is None:
            # No credentials provided - return None
            return None

        token = credentials.credentials

        try:
            # Validate token
            payload = authenticator.validate_token(token)
            return payload
        except AuthenticationError:
            # Authentication failed - return None instead of raising exception
            return None

    def require_role(*allowed_roles: str):
        """
        Dependency factory that requires specific role(s) to access endpoint

        Args:
            *allowed_roles: One or more allowed roles (e.g., "admin", "user", "viewer")

        Returns:
            Dependency function that checks user role

        Raises:
            HTTPException: If user doesn't have required role
        """
        async def role_checker(current_user: TokenPayload = Depends(get_current_user)) -> TokenPayload:
            """
            Check if current user has required role

            Args:
                current_user: Authenticated user

            Returns:
                TokenPayload if user has required role

            Raises:
                HTTPException: If user lacks required role
            """
            if current_user.role not in allowed_roles:
                logger.warning(
                    f"User '{current_user.username}' (role: {current_user.role}) "
                    f"attempted to access endpoint requiring roles: {allowed_roles}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "user_message": "You do not have permission to access this resource",
                        "required_roles": list(allowed_roles),
                        "your_role": current_user.role
                    }
                )
            return current_user

        return role_checker

    # ========================================================================
    # Public Endpoints (No Authentication Required)
    # ========================================================================

    @app.get("/health")
    async def health_check() -> Dict[str, str]:
        """
        Health check endpoint (not rate limited, no auth required)

        Returns:
            Health status
        """
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat()
        }

    @app.get("/")
    async def root() -> Dict[str, Any]:
        """
        Root endpoint with API information (no auth required)

        Returns:
            API information
        """
        return {
            "name": "UAT Gateway API",
            "version": "1.0.0",
            "status": "operational",
            "authentication": "enabled" if enable_auth else "disabled",
            "endpoints": {
                "health": "/health",
                "login": "/auth/login",
                "tests": "/api/tests",
                "test_run": "/api/test-runs",
                "results": "/api/results",
                "upload": "/api/upload",
                "config": "/api/config",
                "journeys": "/api/journeys",
                "docs": "/docs"
            }
        }

    @app.post("/auth/register")
    async def register(username: str, password: str, email: str = None) -> Dict[str, Any]:
        """
        Register a new user with password and email validation

        Feature #354: Enforces secure password requirements
        Feature #400: Validates email format

        Password requirements:
        - Minimum 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character
        - Must not contain username
        - Must not be a common password

        Email requirements:
        - Must be valid email format (if provided)
        - Must pass RFC 5322 format validation

        Args:
            username: Username (must be unique)
            password: Password (must meet security requirements)
            email: Email address (optional, but must be valid if provided)

        Returns:
            User info and registration status

        Raises:
            HTTPException: If validation fails or username exists
        """
        if not enable_auth or authenticator is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Authentication not enabled"
            )

        # Validate username
        if not username or len(username.strip()) < 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username must be at least 3 characters long"
            )

        username = username.strip()

        # Check if username already exists
        if username in DEMO_USERS:
            logger.warning(f"Registration attempt with existing username: {username}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists"
            )

        # Feature #400: Validate email format if provided
        if email and email.strip():
            email_valid, email_error = validate_email(email.strip())
            if not email_valid:
                logger.warning(f"Registration attempt for {username} failed email validation: {email_error}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Invalid email format",
                        "email_error": email_error
                    }
                )
            email = email.strip()  # Store trimmed email

        # Validate password against security policy
        password_result = validate_password(password, username)

        if not password_result.is_valid:
            # Password validation failed
            logger.warning(f"Registration attempt for {username} failed password validation")

            # Include requirements in error message
            requirements = get_password_requirements()
            requirements_text = "; ".join(requirements)

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Password does not meet security requirements",
                    "errors": password_result.errors,
                    "warnings": password_result.warnings,
                    "requirements": requirements_text
                }
            )

        # In a production system, you would:
        # 1. Hash the password with bcrypt
        # 2. Store user in database
        # 3. Send verification email

        # For demo purposes, store in DEMO_USERS dict
        # Note: In production, NEVER store plain text passwords!
        # Store in new format with password and role
        DEMO_USERS[username] = {
            "password": password,
            "role": "user"  # Default role for new registrations
        }

        logger.info(f"New user registered: {username}")

        # Get password strength
        from .password_validator import default_validator
        strength = default_validator.get_password_strength(password)

        return {
            "message": "User registered successfully",
            "username": username,
            "email": email,
            "requirements_met": True,
            "password_strength": strength
        }

    @app.post("/auth/password/validate")
    async def validate_password_endpoint(password: str, username: str = None) -> Dict[str, Any]:
        """
        Validate a password against security policy

        Feature #354: Provides validation endpoint for password requirements

        Args:
            password: Password to validate
            username: Username to check against (optional)

        Returns:
            Validation result with requirements and errors
        """
        password_result = validate_password(password, username)
        requirements = get_password_requirements()

        return {
            "is_valid": password_result.is_valid,
            "errors": password_result.errors,
            "warnings": password_result.warnings,
            "requirements": requirements
        }

    @app.get("/auth/password/requirements")
    async def get_password_requirements_endpoint() -> Dict[str, Any]:
        """
        Get current password requirements

        Feature #354: Provides password requirements to UI

        Returns:
            Password requirements list
        """
        requirements = get_password_requirements()

        return {
            "requirements": requirements,
            "min_length": 8,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_digit": True,
            "require_special": True
        }

    # ========================================================================
    # API Key Management Endpoints (Feature #359)
    # ========================================================================

    @app.post("/auth/api-keys")
    async def create_api_key(
        name: str = Body(..., embed=True),
        scopes: Optional[List[str]] = Body(None, embed=True),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Generate a new API key

        Feature #359: API key generation endpoint

        Args:
            name: Descriptive name for the key
            scopes: List of permissions (optional)
            current_user: Authenticated user

        Returns:
            Generated API key (only time it's shown!) and key details
        """
        if not enable_auth or api_key_authenticator is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="API key authentication not enabled"
            )

        # Generate API key
        api_key = api_key_authenticator.generate_api_key(
            name=name,
            scopes=scopes or ["read", "write"]
        )

        # Log API key creation
        security_audit_logger.log_security_event(
            event_type=SecurityEventType.API_KEY_CREATED,
            action="API key created",
            outcome="success",
            severity=SecuritySeverity.INFO,
            username=current_user.username,
            details={
                "key_name": name,
                "scopes": scopes or ["read", "write"]
            }
        )

        return {
            "api_key": api_key,
            "name": name,
            "message": "Store this key securely - it will not be shown again!",
            "created_at": datetime.now().isoformat()
        }

    @app.get("/auth/api-keys")
    async def list_api_keys(
        include_inactive: bool = False,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        List all API keys

        Feature #359: API key listing endpoint

        Args:
            include_inactive: Whether to include inactive/revoked keys
            current_user: Authenticated user

        Returns:
            List of API keys (without sensitive data)
        """
        if not enable_auth or api_key_authenticator is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="API key authentication not enabled"
            )

        api_keys = api_key_authenticator.list_api_keys(
            include_inactive=include_inactive
        )

        return {
            "api_keys": api_keys,
            "count": len(api_keys)
        }

    @app.delete("/auth/api-keys/{key_id}")
    async def delete_api_key(
        key_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Delete an API key

        Feature #359: API key deletion endpoint

        Args:
            key_id: ID of the key to delete
            current_user: Authenticated user

        Returns:
            Success message
        """
        if not enable_auth or api_key_authenticator is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="API key authentication not enabled"
            )

        success = api_key_authenticator.delete_api_key(key_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )

        # Log API key deletion
        security_audit_logger.log_security_event(
            event_type=SecurityEventType.API_KEY_DELETED,
            action="API key deleted",
            outcome="success",
            severity=SecuritySeverity.INFO,
            username=current_user.username,
            details={"key_id": key_id}
        )

        return {
            "message": "API key deleted successfully",
            "key_id": key_id
        }

    @app.post("/auth/api-keys/{key_id}/revoke")
    async def revoke_api_key(
        key_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Revoke (deactivate) an API key

        Feature #359: API key revocation endpoint

        Args:
            key_id: ID of the key to revoke
            current_user: Authenticated user

        Returns:
            Success message
        """
        if not enable_auth or api_key_authenticator is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="API key authentication not enabled"
            )

        success = api_key_authenticator.revoke_api_key(key_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )

        # Log API key revocation
        security_audit_logger.log_security_event(
            event_type=SecurityEventType.API_KEY_REVOKED,
            action="API key revoked",
            outcome="success",
            severity=SecuritySeverity.INFO,
            username=current_user.username,
            details={"key_id": key_id}
        )

        return {
            "message": "API key revoked successfully",
            "key_id": key_id
        }

    @app.post("/auth/login")
    async def login(
        response: Response,
        username: str,
        password: str,
        next: Optional[str] = None  # Feature #369: Return URL parameter
    ) -> Dict[str, Any]:
        """
        Authenticate user and return JWT token

        Feature #369: Supports post-login redirect via 'next' parameter

        This is a demo implementation. In production, you would:
        1. Hash passwords with bcrypt
        2. Store users in a database
        3. Use proper authentication flow

        Args:
            username: Username
            password: Password
            next: Optional URL to redirect to after successful login

        Returns:
            JWT token and user info (includes return_url if 'next' provided)
        """
        if not enable_auth or authenticator is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Authentication not enabled"
            )

        # Validate credentials (demo only!)
        if username not in DEMO_USERS or DEMO_USERS[username]["password"] != password:
            logger.warning(f"Failed login attempt for user: {username}")
            # Transform to user-friendly error message
            user_friendly_error = ErrorHandler.handle_auth_error("Invalid username or password")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=user_friendly_error.user_message,
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Get user role
        user_role = DEMO_USERS[username]["role"]

        # Create JWT token with role
        expiry_hours_final = 24  # Default 24 hours

        token = authenticator.create_token(
            user_id=username,  # In production, use real user ID
            username=username,
            role=user_role,
            expiry_hours=expiry_hours_final
        )

        # Get expiry time
        expiry = authenticator.get_token_expiry(token)

        logger.info(f"User '{username}' (role: {user_role}) logged in successfully")

        # Set secure session cookie (Feature #362)
        # Cookie flags:
        # - Secure: Only sent over HTTPS
        # - HttpOnly: Not accessible via JavaScript (prevents XSS)
        # - SameSite=strict: Prevents CSRF attacks
        # - Max-age: 24 hours (same as JWT token)
        max_age = expiry_hours_final * 3600 if 'expiry_hours_final' in locals() else 24 * 3600

        # Convert expiry to UTC for cookie (required by Starlette)
        from datetime import timezone
        expiry_utc = expiry.replace(tzinfo=timezone.utc)

        response.set_cookie(
            key="session_token",
            value=token,
            max_age=max_age,
            expires=expiry_utc,
            path="/",
            domain=None,
            secure=True,  # Feature #362: Secure flag
            httponly=True,  # Feature #362: HttpOnly flag
            samesite="strict"  # Feature #362: SameSite=strict
        )

        # Feature #369: Include return URL in response
        result = {
            "access_token": token,
            "token_type": "bearer",
            "expires_at": expiry.isoformat(),
            "username": username,
            "role": user_role,
            "session_cookie": "set"  # Indicate cookie was set
        }

        # Add return URL if provided
        if next:
            result["return_url"] = next
            logger.info(f"Login successful for '{username}', will redirect to: {next}")

        return result

    @app.post("/auth/logout")
    async def logout(response: Response) -> Dict[str, Any]:
        """
        Logout user and clear session cookie

        Feature #362: Secure session management

        Returns:
            Success message
        """
        # Clear session cookie
        response.delete_cookie(
            key="session_token",
            path="/",
            domain=None,
            secure=True,
            httponly=True,
            samesite="strict"
        )

        logger.info("User logged out")

        return {
            "message": "Logged out successfully",
            "session_cookie": "cleared"
        }

    @app.post("/auth/password-reset/request")
    async def request_password_reset(username: str) -> Dict[str, Any]:
        """
        Request a password reset token

        In production, this would:
        1. Verify the user exists
        2. Generate a reset token
        3. Send the token via email

        For development/testing, the token is returned in the response.

        Args:
            username: Username requesting password reset

        Returns:
            Reset token and expiry information
        """
        # Verify user exists
        if username not in DEMO_USERS:
            # For security, don't reveal if user exists
            logger.warning(f"Password reset requested for non-existent user: {username}")
            return {
                "message": "If the user exists, a password reset token has been generated",
                "username": username
            }

        # Get user email (in production, from database)
        # For demo, use a placeholder email
        email = f"{username}@uat-gateway.local"

        # Generate reset token
        reset_manager = get_password_reset_manager()
        reset_token = reset_manager.generate_token(username, email)

        # Get token info
        token_info = reset_manager.get_token_info(username)

        logger.info(f"Password reset requested for user '{username}'")

        # In production, send email with reset link
        # For development, return token in response
        return {
            "message": "Password reset token generated",
            "reset_token": reset_token,  # In production, REMOVE THIS - send via email
            "username": username,
            "email": email,
            "expires_at": token_info["expires_at"] if token_info else None,
            "note": "In production, this token would be sent via email"
        }

    @app.post("/auth/password-reset/validate")
    async def validate_password_reset_token(token: str) -> Dict[str, Any]:
        """
        Validate a password reset token

        Args:
            token: Reset token to validate

        Returns:
            Token validation result
        """
        reset_manager = get_password_reset_manager()
        reset_token = reset_manager.validate_token(token)

        if reset_token is None:
            logger.warning(f"Invalid or expired reset token validation attempted")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired reset token"
            )

        return {
            "valid": True,
            "username": reset_token.username,
            "email": reset_token.email,
            "expires_at": reset_token.expires_at.isoformat(),
            "remaining_seconds": (reset_token.expires_at - datetime.now()).total_seconds()
        }

    @app.post("/auth/password-reset/reset")
    async def reset_password(
        token: str,
        new_password: str
    ) -> Dict[str, Any]:
        """
        Reset password using a valid token

        Args:
            token: Valid reset token
            new_password: New password

        Returns:
            Password reset result
        """
        # Validate token
        reset_manager = get_password_reset_manager()
        reset_token = reset_manager.validate_token(token)

        if reset_token is None:
            logger.warning(f"Password reset attempted with invalid/expired token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired reset token"
            )

        # Validate new password
        try:
            validate_password(new_password)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )

        # Update password (in production, hash with bcrypt)
        username = reset_token.username
        DEMO_USERS[username] = new_password

        # Mark token as used
        reset_manager.use_token(token)

        logger.info(f"Password reset successfully for user '{username}'")

        return {
            "message": "Password reset successfully",
            "username": username
        }

    @app.get("/api/csrf-token")
    async def get_csrf_token() -> Dict[str, str]:
        """
        Get a CSRF token for state-changing operations

        Returns:
            CSRF token
        """
        csrf_manager = get_csrf_manager()
        token = csrf_manager.generate_token()

        return {
            "csrf_token": token,
            "token_type": "csrf"
        }

    # ========================================================================
    # Protected Endpoints (Authentication Required)
    # ========================================================================

    @app.get("/api/tests")
    async def list_tests(
        page: int = 1,
        limit: int = 10,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        List available tests (authentication required)

        Args:
            page: Page number
            limit: Items per page
            current_user: Authenticated user (injected by dependency)

        Returns:
            List of tests
        """
        return {
            "tests": [],
            "page": page,
            "limit": limit,
            "total": 0,
            "message": "Test listing endpoint",
            "user": current_user.username
        }

    @app.post("/api/test-runs")
    async def create_test_run(
        test_data: Dict[str, Any],
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Any:
        """
        Create a new test run (authentication required)

        Feature #315: Implements Post/Redirect/Get pattern

        Args:
            test_data: Test configuration
            current_user: Authenticated user (injected by dependency)

        Returns:
            Redirect to test run details
        """
        # Feature #315: Return 303 redirect instead of JSON
        run_id = "test-run-123"
        return RedirectResponse(
            url=f"/api/test-runs/{run_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    @app.get("/api/test-runs/{run_id}")
    async def get_test_run(
        run_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get test run details (authentication required)

        Args:
            run_id: Test run ID
            current_user: Authenticated user (injected by dependency)

        Returns:
            Test run details
        """
        return {
            "id": run_id,
            "status": "running",
            "message": "Test run details",
            "user": current_user.username
        }

    @app.get("/api/stats")
    async def get_stats(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get rate limiting statistics (authentication required)

        Args:
            current_user: Authenticated user (injected by dependency)

        Returns:
            Rate limiting statistics
        """
        if rate_limiter:
            stats = rate_limiter.get_stats()
            return {
                "rate_limiting": {
                    "enabled": True,
                    **stats
                },
                "message": "Statistics",
                "user": current_user.username
            }
        else:
            return {
                "rate_limiting": {
                    "enabled": False
                },
                "user": current_user.username
            }

    @app.post("/api/admin/reset-rate-limit")
    async def reset_rate_limit(
        client_id: str,
        current_user: TokenPayload = Depends(require_role("admin"))
    ) -> Dict[str, str]:
        """
        Reset rate limit for a client (admin endpoint, admin role required)

        Args:
            client_id: Client identifier to reset
            current_user: Authenticated user with admin role (injected by dependency)

        Returns:
            Reset confirmation

        Raises:
            HTTPException: If user doesn't have admin role
        """
        if rate_limiter:
            rate_limiter.reset_client(client_id)
            return {
                "status": "success",
                "message": f"Rate limit reset for client: {client_id}",
                "user": current_user.username
            }
        else:
            return {
                "status": "error",
                "message": "Rate limiting is not enabled",
                "user": current_user.username
            }

    # ========================================================================
    # User Preferences Endpoints
    # ========================================================================

    @app.get("/api/preferences")
    async def get_preferences(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get all user preferences (authentication required)

        Args:
            current_user: Authenticated user (injected by dependency)

        Returns:
            All user preferences
        """
        prefs_manager = get_preferences_manager()
        preferences = prefs_manager.get_all_preferences(current_user.user_id)

        return {
            "user_id": current_user.user_id,
            "preferences": preferences,
            "message": "User preferences retrieved"
        }

    @app.get("/api/preferences/{key}")
    async def get_preference(
        key: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get a specific user preference (authentication required)

        Args:
            key: Preference key
            current_user: Authenticated user (injected by dependency)

        Returns:
            Preference value
        """
        prefs_manager = get_preferences_manager()
        value = prefs_manager.get_preference(current_user.user_id, key)

        if value is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preference '{key}' not found"
            )

        return {
            "user_id": current_user.user_id,
            "key": key,
            "value": value
        }

    @app.put("/api/preferences/{key}")
    async def set_preference(
        key: str,
        value: Any = Body(..., embed=True),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Set a user preference (authentication required)

        Args:
            key: Preference key
            value: Preference value (will be JSON-decoded from request body)
            current_user: Authenticated user (injected by dependency)

        Returns:
            Updated preference
        """
        prefs_manager = get_preferences_manager()
        prefs_manager.set_preference(current_user.user_id, key, value)

        return {
            "user_id": current_user.user_id,
            "key": key,
            "value": value,
            "message": "Preference updated"
        }

    @app.post("/api/preferences")
    async def set_preferences(
        preferences: Dict[str, Any],
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Set multiple user preferences (authentication required)

        Args:
            preferences: Dictionary of preferences to set
            current_user: Authenticated user (injected by dependency)

        Returns:
            Updated preferences summary
        """
        prefs_manager = get_preferences_manager()
        prefs_manager.set_preferences(current_user.user_id, preferences)

        return {
            "user_id": current_user.user_id,
            "updated_count": len(preferences),
            "message": f"Updated {len(preferences)} preferences"
        }

    @app.delete("/api/preferences/{key}")
    async def delete_preference(
        key: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Delete a user preference (authentication required)

        Args:
            key: Preference key
            current_user: Authenticated user (injected by dependency)

        Returns:
            Deletion confirmation
        """
        prefs_manager = get_preferences_manager()
        deleted = prefs_manager.delete_preference(current_user.user_id, key)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preference '{key}' not found"
            )

        return {
            "user_id": current_user.user_id,
            "key": key,
            "message": "Preference deleted"
        }

    @app.post("/api/preferences/reset")
    async def reset_preferences(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Reset all user preferences to default (authentication required)

        Args:
            current_user: Authenticated user (injected by dependency)

        Returns:
            Reset confirmation
        """
        prefs_manager = get_preferences_manager()
        prefs_manager.reset_user_preferences(current_user.user_id)

        return {
            "user_id": current_user.user_id,
            "message": "All preferences reset to defaults"
        }

    # ========================================================================
    # Timezone Endpoints (Feature #292)
    # ========================================================================

    from custom.uat_gateway.utils.timezone_utils import get_timezone_converter, COMMON_TIMEZONES

    @app.get("/api/timezones")
    async def list_timezones() -> Dict[str, Any]:
        """
        List all available timezones

        Returns:
            List of available timezone names with information
        """
        converter = get_timezone_converter()
        timezone_info_list = converter.list_all_timezone_info()

        return {
            "timezones": [tz_info.to_dict() for tz_info in timezone_info_list],
            "count": len(timezone_info_list),
            "message": "Available timezones retrieved"
        }

    @app.get("/api/timezones/current")
    async def get_current_timezone(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get the current user's timezone preference

        Returns:
            Current timezone and information about it
        """
        prefs_manager = get_preferences_manager()
        user_timezone = prefs_manager.get_preference(current_user.user_id, "timezone", "UTC")

        converter = get_timezone_converter()
        tz_info = converter.get_timezone_info(user_timezone)

        return {
            "user_id": current_user.user_id,
            "timezone": user_timezone,
            "timezone_info": tz_info.to_dict(),
            "message": "Current timezone retrieved"
        }

    @app.put("/api/timezones/current")
    async def set_timezone(
        timezone_name: str = Body(..., embed=True),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Set the user's timezone preference

        Feature #292: Allows users to change their timezone for accurate
        timestamp display across different timezones

        Args:
            timezone_name: Timezone name (e.g., "America/New_York", "UTC")
            current_user: Authenticated user

        Returns:
            Updated timezone information
        """
        # Validate timezone
        converter = get_timezone_converter()
        if not converter.validate_timezone(timezone_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid timezone: {timezone_name}"
            )

        # Save preference
        prefs_manager = get_preferences_manager()
        prefs_manager.set_preference(current_user.user_id, "timezone", timezone_name)

        # Get timezone info
        tz_info = converter.get_timezone_info(timezone_name)

        logger.info(f"User '{current_user.username}' set timezone to '{timezone_name}'")

        return {
            "user_id": current_user.user_id,
            "timezone": timezone_name,
            "timezone_info": tz_info.to_dict(),
            "message": "Timezone updated successfully"
        }

    @app.post("/api/timezones/convert")
    async def convert_timestamp(
        timestamp: str = Body(..., embed=True),
        target_timezone: Optional[str] = Body(None, embed=True),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Convert a timestamp to the user's timezone

        Feature #292: Converts UTC timestamps to user's local timezone
        for accurate display

        Args:
            timestamp: ISO format timestamp to convert
            target_timezone: Target timezone (uses user preference if None)
            current_user: Authenticated user

        Returns:
            Converted timestamp in multiple formats
        """
        # Get target timezone
        if target_timezone is None:
            prefs_manager = get_preferences_manager()
            target_timezone = prefs_manager.get_preference(current_user.user_id, "timezone", "UTC")

        # Convert timestamp
        converter = get_timezone_converter()
        dt = converter.parse_iso_datetime(timestamp)

        return {
            "user_id": current_user.user_id,
            "original_timestamp": timestamp,
            "target_timezone": target_timezone,
            "converted": {
                "full": converter.format_datetime(dt, target_timezone, "full"),
                "short": converter.format_datetime(dt, target_timezone, "short"),
                "time": converter.format_datetime(dt, target_timezone, "time"),
                "date": converter.format_datetime(dt, target_timezone, "date"),
                "relative": converter.format_datetime(dt, target_timezone, "relative"),
                "iso": converter.convert_to_timezone(dt, target_timezone).isoformat()
            },
            "message": "Timestamp converted successfully"
        }

    # ========================================================================
    # Configuration Validation Endpoints (Feature #230)
    # ========================================================================

    # In-memory storage for validated configurations (demo only)
    config_store: Dict[str, Dict[str, Any]] = {}

    @app.post("/api/config/validate")
    async def validate_configuration(
        config: Dict[str, Any],
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Validate configuration settings before saving

        Feature #230: Validates configuration data and returns detailed errors
        - Port must be between 1024-65535
        - Max parallel tests must be between 1-10
        - Max retries must be between 0-5
        - Timeout must be between 1-300 seconds
        - Diff threshold must be between 0.0-1.0
        - Boolean fields must be actual booleans
        - URLs must be valid if provided

        Returns 400 with validation errors if validation fails
        Returns 200 with validation success message if valid
        """
        logger.info(f"User '{current_user.username}' validating configuration")

        # Validate configuration
        is_valid, validation_errors = ConfigValidator.validate_config(config)

        if not is_valid:
            # Validation failed - return detailed error messages
            logger.warning(f"Configuration validation failed for user '{current_user.username}': {len(validation_errors)} errors")

            error_details = [
                {
                    "field": error.field,
                    "message": error.message
                }
                for error in validation_errors
            ]

            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "valid": False,
                    "errors": error_details,
                    "message": f"Configuration validation failed with {len(validation_errors)} error(s)",
                    "user": current_user.username
                }
            )

        # Validation succeeded
        logger.info(f"Configuration validation passed for user '{current_user.username}'")

        return {
            "success": True,
            "valid": True,
            "message": "Configuration is valid and ready to save",
            "user": current_user.username
        }

    @app.post("/api/config/save")
    async def save_configuration(
        config: Dict[str, Any],
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Save configuration settings after validation

        Feature #230: Validates configuration before saving
        - If validation fails, returns 400 with errors
        - If validation passes, saves configuration and returns 201

        This prevents invalid configurations from being saved
        """
        logger.info(f"User '{current_user.username}' attempting to save configuration")

        # First validate the configuration
        is_valid, validation_errors = ConfigValidator.validate_config(config)

        if not is_valid:
            # Validation failed - prevent save
            logger.warning(f"Save blocked: Configuration validation failed for user '{current_user.username}'")

            error_details = [
                {
                    "field": error.field,
                    "message": error.message
                }
                for error in validation_errors
            ]

            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "saved": False,
                    "errors": error_details,
                    "message": "Cannot save invalid configuration. Please fix the errors and try again.",
                    "user": current_user.username
                }
            )

        # Validation passed - save the configuration
        # Use microseconds + random for uniqueness to handle rapid successive saves
        import uuid
        unique_suffix = uuid.uuid4().hex[:8]
        config_id = f"config_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{unique_suffix}_{current_user.user_id}"
        config_store[config_id] = {
            "id": config_id,
            "config": config,
            "user_id": current_user.user_id,
            "created_at": datetime.now().isoformat()
        }

        logger.info(f"Configuration saved successfully: {config_id} by user '{current_user.username}'")

        # Feature #315: Implement Post/Redirect/Get pattern
        # Return 303 redirect to prevent form resubmission on back button
        return RedirectResponse(
            url="/api/config",  # Redirect to config list page
            status_code=status.HTTP_303_SEE_OTHER
        )

    @app.get("/api/config")
    async def get_configurations(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get all saved configurations for the current user

        Feature #230: Returns list of user's saved configurations
        """
        user_configs = [
            cfg for cfg in config_store.values()
            if cfg["user_id"] == current_user.user_id
        ]

        return {
            "configurations": user_configs,
            "total": len(user_configs),
            "user": current_user.username
        }

    @app.get("/api/config/export")
    async def export_configuration(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> FileResponse:
        """
        Export current user's configurations as JSON file

        Feature #297: Export configuration settings
        - Downloads all user's configurations as a JSON file
        - File is named: uat_config_export_{timestamp}.json
        - Returns proper Content-Disposition for download
        """
        import json
        from pathlib import Path

        logger.info(f"User '{current_user.username}' exporting configurations")

        # Get all user configurations
        user_configs = [
            cfg for cfg in config_store.values()
            if cfg["user_id"] == current_user.user_id
        ]

        # Create export data structure
        export_data = {
            "exported_at": datetime.now().isoformat(),
            "exported_by": current_user.username,
            "total_configs": len(user_configs),
            "configurations": user_configs
        }

        # Create temporary file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"uat_config_export_{timestamp}.json"
        temp_file = Path(tempfile.gettempdir()) / filename

        # Write JSON to file
        with open(temp_file, 'w') as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Configuration export created: {filename} ({len(user_configs)} configs)")

        # Return file for download
        return FileResponse(
            path=str(temp_file),
            filename=filename,
            media_type='application/json',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )

    @app.post("/api/config/import")
    async def import_configuration(
        file: UploadFile = File(...),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Import configuration settings from JSON file

        Feature #298: Import configuration settings
        - Uploads a JSON configuration file
        - Validates all configurations before importing
        - Applies valid configurations to the system
        - Returns detailed import results with success/error counts
        - Prevents invalid configurations from being applied

        Expected JSON format (same as export):
        {
            "exported_at": "ISO timestamp",
            "exported_by": "username",
            "total_configs": 1,
            "configurations": [
                {
                    "id": "config_id",
                    "config": { ... configuration settings ... },
                    "user_id": "user_id",
                    "created_at": "ISO timestamp"
                }
            ]
        }
        """
        import json
        from pathlib import Path

        logger.info(f"User '{current_user.username}' importing configuration from file: {file.filename}")

        # Validate file type
        if not file.filename.endswith('.json'):
            logger.warning(f"Invalid file type for import: {file.filename}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "imported": False,
                    "error": "Invalid file type. Only JSON files are supported.",
                    "user": current_user.username
                }
            )

        # Read file content
        try:
            content = await file.read()
            import_data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse import file: {e}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "imported": False,
                    "error": f"Invalid JSON format: {str(e)}",
                    "user": current_user.username
                }
            )
        except Exception as e:
            logger.error(f"Failed to read import file: {e}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "imported": False,
                    "error": f"Failed to read file: {str(e)}",
                    "user": current_user.username
                }
            )

        # Validate import data structure
        if "configurations" not in import_data:
            logger.error("Import file missing 'configurations' key")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "imported": False,
                    "error": "Invalid import format. Missing 'configurations' key.",
                    "user": current_user.username
                }
            )

        configurations = import_data.get("configurations", [])
        total_configs = len(configurations)

        if total_configs == 0:
            logger.warning("Import file contains no configurations")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "imported": False,
                    "error": "Import file contains no configurations to import.",
                    "total_configs": 0,
                    "user": current_user.username
                }
            )

        # Import results tracking
        imported_count = 0
        skipped_count = 0
        failed_count = 0
        validation_errors = []

        logger.info(f"Starting import of {total_configs} configuration(s) for user '{current_user.username}'")

        # Process each configuration
        for idx, config_entry in enumerate(configurations):
            config_id = config_entry.get("id", f"imported_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}")
            config_data = config_entry.get("config", {})
            original_user_id = config_entry.get("user_id", "")

            # Skip configurations from other users (security)
            if original_user_id and original_user_id != current_user.user_id:
                logger.warning(f"Skipping config {config_id} from different user: {original_user_id}")
                skipped_count += 1
                continue

            # Validate configuration before importing
            is_valid, validation_error_list = ConfigValidator.validate_config(config_data)

            if not is_valid:
                # Validation failed - skip this configuration
                error_messages = [f"{err.field}: {err.message}" for err in validation_error_list]
                logger.warning(f"Configuration validation failed for {config_id}: {error_messages}")
                failed_count += 1
                validation_errors.extend([
                    {
                        "config_id": config_id,
                        "errors": error_messages
                    }
                ])
                continue

            # Validation passed - import the configuration
            new_config_id = f"config_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{current_user.user_id}"
            config_store[new_config_id] = {
                "id": new_config_id,
                "config": config_data,
                "user_id": current_user.user_id,
                "created_at": datetime.now().isoformat(),
                "imported_from": config_id
            }

            imported_count += 1
            logger.info(f"Successfully imported configuration: {new_config_id} (original: {config_id})")

        # Prepare import summary
        import_summary = {
            "total_configs": total_configs,
            "imported": imported_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "validation_errors": validation_errors if validation_errors else None
        }

        # Determine overall success
        all_imported = (imported_count == total_configs and failed_count == 0)
        partial_import = (imported_count > 0 and failed_count > 0)
        complete_failure = (imported_count == 0)

        if complete_failure:
            # All configurations failed validation
            logger.error(f"Configuration import completely failed for user '{current_user.username}': {failed_count}/{total_configs} failed")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "imported": False,
                    "message": "Configuration import failed. All configurations had validation errors.",
                    "summary": import_summary,
                    "user": current_user.username
                }
            )
        elif partial_import:
            # Some configurations imported, some failed
            logger.warning(f"Partial import for user '{current_user.username}': {imported_count}/{total_configs} imported, {failed_count} failed")
            return JSONResponse(
                status_code=status.HTTP_207_MULTI_STATUS,  # Multi-status for partial success
                content={
                    "success": True,
                    "imported": True,
                    "partial": True,
                    "message": f"Configuration import partially completed. {imported_count} imported, {failed_count} failed, {skipped_count} skipped.",
                    "summary": import_summary,
                    "user": current_user.username
                }
            )
        else:
            # All configurations imported successfully
            logger.info(f"Configuration import successful for user '{current_user.username}': {imported_count}/{total_configs} imported")
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={
                    "success": True,
                    "imported": True,
                    "message": f"Successfully imported {imported_count} configuration(s).",
                    "summary": import_summary,
                    "user": current_user.username
                }
            )

    @app.get("/api/data/export")
    async def export_journey_and_test_data(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> FileResponse:
        """
        Export all journeys, scenarios, and test results as JSON file

        Feature #300: Export journey and test data
        - Downloads all journeys with their scenarios
        - Downloads all test results (both active and archived)
        - File is named: uat_data_export_{timestamp}.json
        - Returns proper Content-Disposition for download
        - Export format is documented in the response
        """
        import json
        from pathlib import Path

        logger.info(f"User '{current_user.username}' exporting journey and test data")

        # Get all journeys (which include scenarios)
        all_journeys = list(journeys_store.values())

        # Flatten scenarios from all journeys
        all_scenarios = []
        for journey in all_journeys:
            scenarios = journey.get("scenarios", [])
            for scenario in scenarios:
                # Add journey_id to each scenario for context
                scenario_with_context = scenario.copy()
                scenario_with_context["journey_id"] = journey.get("journey_id")
                scenario_with_context["journey_name"] = journey.get("name")
                all_scenarios.append(scenario_with_context)

        # Get all test results (active and archived)
        archiver = get_result_archiver()
        active_results = archiver.get_active_results()
        archived_results = archiver.get_archived_results()

        # Convert test results to dict format
        active_results_dict = [r.to_dict() for r in active_results]
        archived_results_dict = [r.to_dict() for r in archived_results]

        # Create export data structure with documented format
        export_data = {
            "export_metadata": {
                "exported_at": datetime.now().isoformat(),
                "exported_by": current_user.username,
                "export_version": "1.0",
                "export_format": "uat_gateway_data_export"
            },
            "data_summary": {
                "total_journeys": len(all_journeys),
                "total_scenarios": len(all_scenarios),
                "total_active_results": len(active_results),
                "total_archived_results": len(archived_results),
                "total_results": len(active_results) + len(archived_results)
            },
            "journeys": all_journeys,
            "scenarios": all_scenarios,
            "test_results": {
                "active": active_results_dict,
                "archived": archived_results_dict
            },
            "format_documentation": {
                "export_metadata": "Information about when and who exported the data",
                "data_summary": "Summary counts of all exported data",
                "journeys": "List of all journey definitions with metadata",
                "scenarios": "List of all scenarios from all journeys, with journey context",
                "test_results": {
                    "active": "Test results that are currently active (not archived)",
                    "archived": "Test results that have been archived"
                },
                "journey_structure": {
                    "journey_id": "Unique identifier for the journey",
                    "name": "Human-readable journey name",
                    "description": "Detailed description of the journey",
                    "priority": "Priority level (high, medium, low)",
                    "scenarios": "List of scenarios belonging to this journey"
                },
                "scenario_structure": {
                    "scenario_id": "Unique identifier for the scenario",
                    "name": "Human-readable scenario name",
                    "description": "Detailed description of the scenario",
                    "steps": "List of test steps in the scenario",
                    "journey_id": "ID of the parent journey",
                    "journey_name": "Name of the parent journey"
                },
                "test_result_structure": {
                    "test_id": "Unique identifier for the test result",
                    "test_name": "Name of the test",
                    "status": "Test status (passed, failed, or skipped)",
                    "duration_ms": "Test execution duration in milliseconds",
                    "timestamp": "When the test was executed",
                    "journey_id": "ID of the journey this test belongs to",
                    "error_message": "Error message if test failed",
                    "metadata": "Additional metadata about the test"
                }
            }
        }

        # Create temporary file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"uat_data_export_{timestamp}.json"
        temp_file = Path(tempfile.gettempdir()) / filename

        # Write JSON to file
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        logger.info(
            f"Data export created: {filename} "
            f"({len(all_journeys)} journeys, {len(all_scenarios)} scenarios, "
            f"{len(active_results)} active results, {len(archived_results)} archived results)"
        )

        # Return file for download
        return FileResponse(
            path=str(temp_file),
            filename=filename,
            media_type='application/json',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )

    # ========================================================================
    # Journey Management Endpoints (Feature #229)
    # ========================================================================

    # In-memory storage for journeys (demo only - use database in production)
    journeys_store: Dict[str, Dict[str, Any]] = {}

    @app.get("/api/journeys")
    async def list_journeys(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        List all journeys (authentication required)

        Feature #229: Returns list of journeys with metadata
        Feature #364: Filter journeys by current user
        """
        logger.info(f"User '{current_user.username}' listing journeys")

        # Feature #364: Filter journeys by user_id
        user_journeys = [
            j for j in journeys_store.values()
            if j.get("user_id") == current_user.user_id
        ]

        return {
            "journeys": user_journeys,
            "total": len(user_journeys),
            "user": current_user.username
        }

    @app.get("/api/journeys/{journey_id}")
    async def get_journey(
        journey_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get a specific journey by ID (authentication required)

        Feature #229: Returns journey details or 404 if not found
        Feature #364: Users can only access their own journeys
        """
        if journey_id not in journeys_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journey with ID '{journey_id}' not found"
            )

        journey = journeys_store[journey_id]

        # Feature #364: Check user owns this journey
        if journey.get("user_id") != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to access journey '{journey_id}' "
                f"owned by user '{journey.get('user_id')}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this journey"
            )

        logger.info(f"User '{current_user.username}' retrieved journey: {journey_id}")

        return journey

    @app.post("/api/journeys")
    async def create_journey(
        journey_data: Dict[str, Any],
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Create a new journey (authentication + CSRF required)

        Feature #229: Validates journey name before creation
        - Name must be 3-100 characters
        - Only letters, numbers, spaces, hyphens, underscores allowed
        - Cannot be empty or whitespace only
        - Must be unique (case-insensitive)

        Feature #351: CSRF protection enabled
        - Requires valid CSRF token in X-CSRF-Token header or csrf_token body field
        - Returns 403 if CSRF token is missing or invalid

        Returns 400 with validation error if validation fails
        Returns 403 if CSRF token is missing or invalid
        Returns 201 with journey data if successful
        """
        # Verify CSRF token
        await verify_csrf_token(request)

        # Get existing journey names for uniqueness check
        # Get existing journey names for uniqueness check
        existing_names = [j.get("name") for j in journeys_store.values()]

        # Validate journey data (including name)
        is_valid, validation_errors = validate_journey_data(journey_data, existing_names)

        if not is_valid:
            # Validation failed - return detailed error messages
            logger.warning(f"Journey validation failed for user '{current_user.username}': {validation_errors}")

            error_details = [
                {
                    "field": error.field,
                    "message": error.message
                }
                for error in validation_errors
            ]

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "message": "Journey data validation failed",
                    "validation_errors": error_details
                }
            )

        # Validation passed - create journey
        import uuid
        journey_id = f"journey-{uuid.uuid4().hex[:8]}"

        journey = {
            "id": journey_id,
            "name": journey_data["name"],
            "description": journey_data.get("description", ""),
            "priority": journey_data.get("priority", 5),
            "status": JourneyStatus.PENDING.value,  # Feature #387: All journeys start in PENDING state
            "created_at": datetime.now().isoformat(),
            "created_by": current_user.username,
            "user_id": current_user.user_id,  # Feature #364: User isolation
            "steps": journey_data.get("steps", []),
            "scenarios": journey_data.get("scenarios", [])
        }

        # Feature #450: Initialize version to 1 for new journeys
        journey["version"] = 1

        journeys_store[journey_id] = journey

        logger.info(f"User '{current_user.username}' created journey '{journey['name']}' (ID: {journey_id})")

        # Consume CSRF token after successful creation
        consume_csrf_token(request)

        # Feature #315: Implement Post/Redirect/Get pattern
        # Return 303 redirect to prevent form resubmission on back button
        return RedirectResponse(
            url=f"/api/journeys/{journey_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    @app.put("/api/journeys/{journey_id}")
    async def update_journey(
        journey_id: str,
        journey_data: Dict[str, Any],
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Update an existing journey (authentication + CSRF required)

        Feature #229: Validates journey name before update
        - Same validation rules as create
        - Name uniqueness check excludes current journey

        Feature #323: Cascading UI updates
        - When journey name changes, all linked test results update automatically
        - Updates journey_name field in all matching test results
        - Updates test_name if it contains the old journey name

        Feature #351: CSRF protection enabled
        """
        # Verify CSRF token
        await verify_csrf_token(request)
        if journey_id not in journeys_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journey with ID '{journey_id}' not found"
            )

        # Feature #353: XSS Protection - Sanitize user input
        journey_data = sanitize_journey_data(journey_data)

        # Get existing journey names for uniqueness check (excluding current journey)
        existing_names = [
            j.get("name")
            for j_id, j in journeys_store.items()
            if j_id != journey_id  # Exclude current journey from uniqueness check
        ]

        # Validate journey data (including name)
        is_valid, validation_errors = validate_journey_data(journey_data, existing_names)

        if not is_valid:
            # Validation failed - return detailed error messages
            logger.warning(f"Journey validation failed for user '{current_user.username}': {validation_errors}")

            error_details = [
                {
                    "field": error.field,
                    "message": error.message
                }
                for error in validation_errors
            ]

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "message": "Journey data validation failed",
                    "validation_errors": error_details
                }
            )

        # Feature #450: Concurrent Edits - Version check for optimistic locking
        journey = journeys_store[journey_id]
        old_name = journey["name"]
        new_name = journey_data["name"]

        # Get current version
        current_version = journey.get("version", 1)
        client_version = journey_data.get("version")

        # Check for version mismatch (conflict detection)
        if client_version is not None and client_version != current_version:
            force_overwrite = journey_data.get("_force", False)

            if not force_overwrite:
                # Version conflict - user has stale data
                logger.warning(
                    f"Version conflict for journey '{journey_id}': "
                    f"client has v{client_version}, server has v{current_version}"
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "version_conflict",
                        "message": "This journey was modified by another user",
                        "current_version": current_version,
                        "client_version": client_version,
                        "action": "Refresh the page to get the latest version, or force overwrite to discard other changes"
                    }
                )
            else:
                # Force overwrite - log warning but allow
                logger.warning(
                    f"User '{current_user.username}' force overwriting journey '{journey_id}' "
                    f"(client v{client_version} vs server v{current_version})"
                )

        # Validation passed - update journey
        journey["name"] = new_name
        journey["description"] = journey_data.get("description", journey["description"])
        journey["priority"] = journey_data.get("priority", journey["priority"])

        # Feature #450: Increment version on each update
        journey["version"] = current_version + 1
        journey["updated_at"] = datetime.now().isoformat()
        journey["updated_by"] = current_user.username

        if "steps" in journey_data:
            journey["steps"] = journey_data["steps"]
        if "scenarios" in journey_data:
            journey["scenarios"] = journey_data["scenarios"]

        # Feature #323: Cascading updates - update all linked test results
        # If the journey name changed, we would update all test results linked to this journey
        # Note: Test results are now managed by the result_archiver, not a simple dictionary store
        # The cascade update logic will be handled separately through the archiver API
        if old_name != new_name:
            logger.info(
                f"Journey name changed from '{old_name}' -> '{new_name}' (ID: {journey_id})"
            )
            # TODO: Implement cascade update through result_archiver
            # This would require adding an update_journey_name method to the archiver

        logger.info(f"User '{current_user.username}' updated journey '{journey['name']}' (ID: {journey_id})")

        # Consume CSRF token after successful update
        consume_csrf_token(request)

        # Feature #450: Return updated version in response
        logger.info(
            f"Journey '{journey['name']}' updated to version {journey.get('version', 1)} "
            f"by '{current_user.username}'"
        )

        return journey

    @app.delete("/api/journeys/{journey_id}")
    async def delete_journey(
        journey_id: str,
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Delete a journey (authentication + CSRF required)

        Feature #229: Deletes journey or returns 404 if not found
        Feature #351: CSRF protection enabled
        """
        # Verify CSRF token
        await verify_csrf_token(request)

        if journey_id not in journeys_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journey with ID '{journey_id}' not found"
            )

        # Feature #364: Check user owns this journey
        journey = journeys_store[journey_id]
        if journey.get("user_id") != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to delete journey '{journey_id}' "
                f"owned by user '{journey.get('user_id')}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this journey"
            )

        journey_name = journey["name"]
        del journeys_store[journey_id]

        logger.info(f"User '{current_user.username}' deleted journey '{journey_name}' (ID: {journey_id})")

        # Audit log the sensitive action
        security_audit_logger.log_security_event(
            event_type=SecurityEventType.DATA_DELETED,
            action=f"Deleted journey '{journey_name}'",
            outcome="success",
            severity=SecuritySeverity.INFO,
            user_id=current_user.user_id,
            username=current_user.username,
            resource=f"journey:{journey_id}",
            details={
                "journey_name": journey_name,
                "journey_id": journey_id
            }
        )

        # Consume CSRF token after successful deletion
        consume_csrf_token(request)

        return {
            "status": "success",
            "message": f"Journey '{journey_name}' deleted successfully",
            "deleted_journey_id": journey_id
        }

    # ========================================================================
    # Journey State Transition Endpoints (Feature #387)
    # ========================================================================

    @app.post("/api/journeys/{journey_id}/start")
    async def start_journey(
        journey_id: str,
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Start journey execution (PENDING → RUNNING)

        Feature #387: State transitions work correctly

        Transitions journey from PENDING to RUNNING state.
        Validates the transition and returns error if invalid.

        Args:
            journey_id: Journey to start
            current_user: Authenticated user

        Returns:
            Updated journey with new status

        Raises:
            404: Journey not found
            403: User doesn't own the journey
            400: Invalid state transition
        """
        if journey_id not in journeys_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journey with ID '{journey_id}' not found"
            )

        journey = journeys_store[journey_id]

        # Feature #364: Check user owns this journey
        if journey.get("user_id") != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to start journey '{journey_id}' "
                f"owned by user '{journey.get('user_id')}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to start this journey"
            )

        # Get state machine and validate transition
        state_machine = get_journey_state_machine()
        current_status = journey.get("status", JourneyStatus.PENDING.value)
        transition = state_machine.validate_transition(
            current_status,
            JourneyStatus.RUNNING.value
        )

        if not transition.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_state_transition",
                    "message": transition.reason,
                    "current_status": current_status,
                    "requested_status": JourneyStatus.RUNNING.value
                }
            )

        # Update journey status
        journey["status"] = JourneyStatus.RUNNING.value
        journey["started_at"] = datetime.now().isoformat()
        journey["started_by"] = current_user.username

        logger.info(
            f"User '{current_user.username}' started journey '{journey['name']}' "
            f"(ID: {journey_id}) - Status: {current_status} → {JourneyStatus.RUNNING.value}"
        )

        # Persist to journey persistence
        try:
            journey_persistence = get_journey_persistence()
            journey_persistence.update_journey(journey_id, journey)
        except Exception as e:
            logger.warning(f"Could not persist journey state: {e}")

        return journey

    @app.post("/api/journeys/{journey_id}/complete")
    async def complete_journey(
        journey_id: str,
        completion_data: Dict[str, Any] = Body(...),
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Complete journey execution (RUNNING → COMPLETED/FAILED)

        Feature #387: State transitions work correctly

        Transitions journey from RUNNING to COMPLETED or FAILED state.
        Validates the transition and returns error if invalid.

        Args:
            journey_id: Journey to complete
            completion_data: {"success": true/false, "summary": "..."}
            current_user: Authenticated user

        Returns:
            Updated journey with new status

        Raises:
            404: Journey not found
            403: User doesn't own the journey
            400: Invalid state transition
        """
        if journey_id not in journeys_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journey with ID '{journey_id}' not found"
            )

        journey = journeys_store[journey_id]

        # Feature #364: Check user owns this journey
        if journey.get("user_id") != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to complete journey '{journey_id}' "
                f"owned by user '{journey.get('user_id')}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to complete this journey"
            )

        # Determine target status based on success flag
        success = completion_data.get("success", True)
        target_status = JourneyStatus.COMPLETED.value if success else JourneyStatus.FAILED.value

        # Get state machine and validate transition
        state_machine = get_journey_state_machine()
        current_status = journey.get("status", JourneyStatus.PENDING.value)
        transition = state_machine.validate_transition(current_status, target_status)

        if not transition.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_state_transition",
                    "message": transition.reason,
                    "current_status": current_status,
                    "requested_status": target_status
                }
            )

        # Update journey status
        journey["status"] = target_status
        journey["completed_at"] = datetime.now().isoformat()
        journey["completed_by"] = current_user.username
        journey["completion_summary"] = completion_data.get("summary", "")

        logger.info(
            f"User '{current_user.username}' completed journey '{journey['name']}' "
            f"(ID: {journey_id}) - Status: {current_status} → {target_status}"
        )

        # Persist to journey persistence
        try:
            journey_persistence = get_journey_persistence()
            journey_persistence.update_journey(journey_id, journey)
        except Exception as e:
            logger.warning(f"Could not persist journey state: {e}")

        return journey

    @app.post("/api/journeys/{journey_id}/cancel")
    async def cancel_journey(
        journey_id: str,
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Cancel journey execution (any state → CANCELLED)

        Feature #387: State transitions work correctly

        Transitions journey from PENDING or RUNNING to CANCELLED state.
        Validates the transition and returns error if invalid.

        Args:
            journey_id: Journey to cancel
            current_user: Authenticated user

        Returns:
            Updated journey with new status

        Raises:
            404: Journey not found
            403: User doesn't own the journey
            400: Invalid state transition
        """
        if journey_id not in journeys_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journey with ID '{journey_id}' not found"
            )

        journey = journeys_store[journey_id]

        # Feature #364: Check user owns this journey
        if journey.get("user_id") != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to cancel journey '{journey_id}' "
                f"owned by user '{journey.get('user_id')}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to cancel this journey"
            )

        # Get state machine and validate transition
        state_machine = get_journey_state_machine()
        current_status = journey.get("status", JourneyStatus.PENDING.value)
        transition = state_machine.validate_transition(
            current_status,
            JourneyStatus.CANCELLED.value
        )

        if not transition.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_state_transition",
                    "message": transition.reason,
                    "current_status": current_status,
                    "requested_status": JourneyStatus.CANCELLED.value
                }
            )

        # Update journey status
        journey["status"] = JourneyStatus.CANCELLED.value
        journey["cancelled_at"] = datetime.now().isoformat()
        journey["cancelled_by"] = current_user.username

        logger.info(
            f"User '{current_user.username}' cancelled journey '{journey['name']}' "
            f"(ID: {journey_id}) - Status: {current_status} → {JourneyStatus.CANCELLED.value}"
        )

        # Persist to journey persistence
        try:
            journey_persistence = get_journey_persistence()
            journey_persistence.update_journey(journey_id, journey)
        except Exception as e:
            logger.warning(f"Could not persist journey state: {e}")

        return journey

    @app.post("/api/journeys/{journey_id}/reset")
    async def reset_journey(
        journey_id: str,
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Reset journey to PENDING state (COMPLETED/FAILED/CANCELLED → PENDING)

        Feature #387: State transitions work correctly

        Allows restarting a journey by resetting it to PENDING state.
        Clears timestamps and prepares for re-execution.

        Args:
            journey_id: Journey to reset
            current_user: Authenticated user

        Returns:
            Updated journey with PENDING status

        Raises:
            404: Journey not found
            403: User doesn't own the journey
            400: Invalid state transition
        """
        if journey_id not in journeys_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journey with ID '{journey_id}' not found"
            )

        journey = journeys_store[journey_id]

        # Feature #364: Check user owns this journey
        if journey.get("user_id") != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to reset journey '{journey_id}' "
                f"owned by user '{journey.get('user_id')}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to reset this journey"
            )

        # Get state machine and validate transition
        state_machine = get_journey_state_machine()
        current_status = journey.get("status", JourneyStatus.PENDING.value)
        transition = state_machine.validate_transition(
            current_status,
            JourneyStatus.PENDING.value
        )

        if not transition.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_state_transition",
                    "message": transition.reason,
                    "current_status": current_status,
                    "requested_status": JourneyStatus.PENDING.value
                }
            )

        # Update journey status and clear execution timestamps
        journey["status"] = JourneyStatus.PENDING.value

        # Clear execution-related timestamps
        journey.pop("started_at", None)
        journey.pop("started_by", None)
        journey.pop("completed_at", None)
        journey.pop("completed_by", None)
        journey.pop("cancelled_at", None)
        journey.pop("cancelled_by", None)
        journey.pop("completion_summary", None)

        logger.info(
            f"User '{current_user.username}' reset journey '{journey['name']}' "
            f"(ID: {journey_id}) - Status: {current_status} → {JourneyStatus.PENDING.value}"
        )

        # Persist to journey persistence
        try:
            journey_persistence = get_journey_persistence()
            journey_persistence.update_journey(journey_id, journey)
        except Exception as e:
            logger.warning(f"Could not persist journey state: {e}")

        return journey

    @app.get("/api/journeys/{journey_id}/valid-transitions")
    async def get_valid_transitions(
        journey_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get valid state transitions for a journey

        Feature #387: State transitions work correctly

        Returns list of valid next states from the current state.

        Args:
            journey_id: Journey to query
            current_user: Authenticated user

        Returns:
            Dictionary with current status and valid next states

        Raises:
            404: Journey not found
            403: User doesn't own the journey
        """
        if journey_id not in journeys_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Journey with ID '{journey_id}' not found"
            )

        journey = journeys_store[journey_id]

        # Feature #364: Check user owns this journey
        if journey.get("user_id") != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to query transitions for journey '{journey_id}' "
                f"owned by user '{journey.get('user_id')}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this journey"
            )

        # Get state machine and valid next states
        state_machine = get_journey_state_machine()
        current_status = journey.get("status", JourneyStatus.PENDING.value)
        valid_next_states = state_machine.get_valid_next_states(current_status)

        return {
            "journey_id": journey_id,
            "journey_name": journey.get("name"),
            "current_status": current_status,
            "valid_transitions": valid_next_states,
            "can_start": state_machine.can_start(current_status),
            "can_complete": state_machine.can_complete(current_status)[0],
            "can_cancel": state_machine.can_cancel(current_status),
            "can_restart": state_machine.can_restart(current_status)
        }

    # ========================================================================
    # Scenario Management Endpoints (Feature #385)
    # ========================================================================

    # In-memory storage for scenarios
    # Note: Scenarios are stored both here and within journeys for dual access
    scenarios_store: Dict[str, Dict[str, Any]] = {}

    @app.post("/api/scenarios")
    async def create_scenario(
        scenario_data: Dict[str, Any],
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Create a new scenario (authentication + CSRF required)

        Feature #385: Create test scenario
        - Validates scenario name and required fields
        - Links to parent journey if journey_id provided
        - CSRF protection enabled
        - User isolation enforced
        """
        # Verify CSRF token
        await verify_csrf_token(request)

        # Validate required fields
        if "name" not in scenario_data or not scenario_data["name"].strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "message": "Scenario name is required"
                }
            )

        scenario_name = scenario_data["name"].strip()

        # Validate name length
        if len(scenario_name) < 3 or len(scenario_name) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "message": "Scenario name must be between 3 and 100 characters"
                }
            )

        # Feature #353: XSS Protection - Sanitize user input
        scenario_data = sanitize_journey_data(scenario_data)

        # Generate unique scenario ID
        import uuid
        scenario_id = f"scenario-{uuid.uuid4().hex[:8]}"

        # Check if journey_id is provided and valid
        journey_id = scenario_data.get("journey_id")
        if journey_id:
            if journey_id not in journeys_store:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Journey with ID '{journey_id}' not found"
                )

            # Feature #364: Check user owns the parent journey
            journey = journeys_store[journey_id]
            if journey.get("user_id") != current_user.user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to add scenarios to this journey"
                )

        # Create scenario
        scenario = {
            "id": scenario_id,
            "name": scenario_name,
            "description": scenario_data.get("description", ""),
            "steps": scenario_data.get("steps", []),
            "journey_id": journey_id,
            "created_at": datetime.now().isoformat(),
            "created_by": current_user.username,
            "user_id": current_user.user_id,  # Feature #364: User isolation
            "priority": scenario_data.get("priority", 5),
            "metadata": scenario_data.get("metadata", {})
        }

        # Store in scenarios_store
        scenarios_store[scenario_id] = scenario

        # If journey_id provided, also add to journey's scenarios array
        if journey_id:
            journey = journeys_store[journey_id]
            if "scenarios" not in journey:
                journey["scenarios"] = []

            # Check if scenario already exists in journey (by name)
            existing_scenario_names = [s.get("name") for s in journey["scenarios"]]
            if scenario_name in existing_scenario_names:
                # Rollback - remove from scenarios_store
                del scenarios_store[scenario_id]
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "validation_error",
                        "message": f"Scenario '{scenario_name}' already exists in this journey"
                    }
                )

            # Add scenario reference to journey
            journey["scenarios"].append({
                "id": scenario_id,
                "name": scenario_name,
                "description": scenario.get("description", "")
            })
            journey["updated_at"] = datetime.now().isoformat()

        logger.info(
            f"User '{current_user.username}' created scenario '{scenario_name}' "
            f"(ID: {scenario_id})" + (f" in journey '{journey_id}'" if journey_id else "")
        )

        # Consume CSRF token after successful creation
        consume_csrf_token(request)

        # Return scenario details
        return scenario

    @app.get("/api/scenarios")
    async def list_scenarios(
        journey_id: Optional[str] = None,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        List all scenarios (authentication required)

        Feature #385: Read scenario details
        - Filter by journey_id if provided
        - Feature #364: Only return scenarios owned by current user
        """
        logger.info(f"User '{current_user.username}' listing scenarios")

        # Filter scenarios by user_id
        user_scenarios = [
            s for s in scenarios_store.values()
            if s.get("user_id") == current_user.user_id
        ]

        # Further filter by journey_id if provided
        if journey_id:
            user_scenarios = [
                s for s in user_scenarios
                if s.get("journey_id") == journey_id
            ]

        return {
            "scenarios": user_scenarios,
            "total": len(user_scenarios),
            "user": current_user.username,
            "journey_filter": journey_id
        }

    @app.get("/api/scenarios/{scenario_id}")
    async def get_scenario(
        scenario_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get a specific scenario by ID (authentication required)

        Feature #385: Read scenario details
        - Feature #364: Users can only access their own scenarios
        """
        if scenario_id not in scenarios_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario with ID '{scenario_id}' not found"
            )

        scenario = scenarios_store[scenario_id]

        # Feature #364: Check user owns this scenario
        if scenario.get("user_id") != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to access scenario '{scenario_id}' "
                f"owned by user '{scenario.get('user_id')}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this scenario"
            )

        logger.info(f"User '{current_user.username}' retrieved scenario: {scenario_id}")

        return scenario

    @app.put("/api/scenarios/{scenario_id}")
    async def update_scenario(
        scenario_id: str,
        scenario_data: Dict[str, Any],
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Update an existing scenario (authentication + CSRF required)

        Feature #385: Update scenario steps
        - Validates scenario name
        - CSRF protection enabled
        - Feature #364: Users can only update their own scenarios
        - Updates scenario in both scenarios_store and parent journey
        """
        # Verify CSRF token
        await verify_csrf_token(request)

        if scenario_id not in scenarios_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario with ID '{scenario_id}' not found"
            )

        scenario = scenarios_store[scenario_id]

        # Feature #364: Check user owns this scenario
        if scenario.get("user_id") != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this scenario"
            )

        # Feature #353: XSS Protection - Sanitize user input
        scenario_data = sanitize_journey_data(scenario_data)

        # Validate name if provided
        if "name" in scenario_data:
            new_name = scenario_data["name"].strip()
            if not new_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "validation_error", "message": "Scenario name cannot be empty"}
                )

            if len(new_name) < 3 or len(new_name) > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "validation_error",
                        "message": "Scenario name must be between 3 and 100 characters"
                    }
                )

        # Update scenario fields
        if "name" in scenario_data:
            old_name = scenario["name"]
            scenario["name"] = scenario_data["name"]

            # Update scenario name in parent journey if exists
            journey_id = scenario.get("journey_id")
            if journey_id and journey_id in journeys_store:
                journey = journeys_store[journey_id]
                for s in journey.get("scenarios", []):
                    if s.get("id") == scenario_id:
                        s["name"] = scenario_data["name"]
                journey["updated_at"] = datetime.now().isoformat()

        if "description" in scenario_data:
            scenario["description"] = scenario_data["description"]

        if "steps" in scenario_data:
            scenario["steps"] = scenario_data["steps"]

        if "priority" in scenario_data:
            scenario["priority"] = scenario_data["priority"]

        if "metadata" in scenario_data:
            scenario["metadata"] = scenario_data["metadata"]

        scenario["updated_at"] = datetime.now().isoformat()
        scenario["updated_by"] = current_user.username

        logger.info(f"User '{current_user.username}' updated scenario '{scenario['name']}' (ID: {scenario_id})")

        # Consume CSRF token after successful update
        consume_csrf_token(request)

        return scenario

    @app.delete("/api/scenarios/{scenario_id}")
    async def delete_scenario(
        scenario_id: str,
        current_user: TokenPayload = Depends(get_current_user),
        request: Request = None
    ) -> Dict[str, Any]:
        """
        Delete a scenario (authentication + CSRF required)

        Feature #385: Delete scenario
        - CSRF protection enabled
        - Feature #364: Users can only delete their own scenarios
        - Removes scenario from both scenarios_store and parent journey
        """
        # Verify CSRF token
        await verify_csrf_token(request)

        if scenario_id not in scenarios_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario with ID '{scenario_id}' not found"
            )

        scenario = scenarios_store[scenario_id]

        # Feature #364: Check user owns this scenario
        if scenario.get("user_id") != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to delete scenario '{scenario_id}' "
                f"owned by user '{scenario.get('user_id')}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this scenario"
            )

        scenario_name = scenario["name"]
        journey_id = scenario.get("journey_id")

        # Remove from scenarios_store
        del scenarios_store[scenario_id]

        # Remove from parent journey's scenarios array if exists
        if journey_id and journey_id in journeys_store:
            journey = journeys_store[journey_id]
            journey["scenarios"] = [
                s for s in journey.get("scenarios", [])
                if s.get("id") != scenario_id
            ]
            journey["updated_at"] = datetime.now().isoformat()

        logger.info(
            f"User '{current_user.username}' deleted scenario '{scenario_name}' "
            f"(ID: {scenario_id})" + (f" from journey '{journey_id}'" if journey_id else "")
        )

        # Audit log the sensitive action
        security_audit_logger.log_security_event(
            event_type=SecurityEventType.DATA_DELETED,
            action=f"Deleted scenario '{scenario_name}'",
            outcome="success",
            severity=SecuritySeverity.INFO,
            user_id=current_user.user_id,
            username=current_user.username,
            resource=f"scenario:{scenario_id}",
            details={
                "scenario_name": scenario_name,
                "scenario_id": scenario_id,
                "journey_id": journey_id
            }
        )

        # Consume CSRF token after successful deletion
        consume_csrf_token(request)

        return {
            "status": "success",
            "message": f"Scenario '{scenario_name}' deleted successfully",
            "deleted_scenario_id": scenario_id
        }

    # ========================================================================
    # File Upload Endpoints (Feature #217)
    # ========================================================================

    # Configure upload directory
    upload_dir = os.path.join(tempfile.gettempdir(), "uat_uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # In-memory storage for uploaded file metadata
    uploaded_files_store: Dict[str, Dict[str, Any]] = {}

    # Initialize file validator
    file_validator = FileUploadValidator(security_level=FileSecurityLevel.MODERATE)

    @app.post("/api/upload")
    async def upload_file(
        file: UploadFile = File(...),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Upload and validate a file

        Feature #217: Validates uploaded files for security threats
        - Checks file extensions against allowlist
        - Validates MIME types match extensions
        - Enforces file size limits (max 10MB by default)
        - Scans file contents for malicious signatures
        - Detects polyglot files (files with multiple formats)
        - Prevents executable uploads

        Returns 400 with validation errors if file is rejected
        Returns 201 with file metadata if file is accepted
        """
        logger.info(f"User '{current_user.username}' attempting to upload file: {file.filename}")

        # Validate filename is provided
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filename provided"
            )

        # Save uploaded file to temporary location for validation
        temp_file_path = None
        try:
            # Create temporary file
            temp_file_path = os.path.join(upload_dir, f"temp_{current_user.user_id}_{file.filename}")

            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Validate the file
            validation_result = file_validator.validate_file(
                temp_file_path,
                file.filename,
                check_content=True
            )

            if not validation_result.is_valid:
                # Validation failed - delete file and return errors
                logger.warning(
                    f"[SECURITY] File upload rejected for user '{current_user.username}': "
                    f"{file.filename} - {validation_result.errors}"
                )

                # Clean up rejected file
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)

                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "success": False,
                        "uploaded": False,
                        "filename": file.filename,
                        "errors": validation_result.errors,
                        "warnings": validation_result.warnings,
                        "message": "File upload rejected due to security validation failure",
                        "user": current_user.username
                    }
                )

            # Validation passed - move file to permanent storage
            import uuid
            file_id = f"file_{uuid.uuid4().hex}"
            safe_filename = f"{file_id}_{file.filename}"
            permanent_path = os.path.join(upload_dir, safe_filename)

            # Move file from temp to permanent location
            shutil.move(temp_file_path, permanent_path)

            # Store file metadata
            file_metadata = {
                "id": file_id,
                "filename": file.filename,
                "safe_filename": safe_filename,
                "storage_path": permanent_path,
                "size": validation_result.file_info.get('size', 0),
                "extension": validation_result.file_info.get('extension', ''),
                "detected_mime_type": validation_result.file_info.get('detected_mime_type', ''),
                "uploaded_by": current_user.username,
                "uploaded_at": datetime.now().isoformat()
            }
            uploaded_files_store[file_id] = file_metadata

            logger.info(
                f"File uploaded successfully by user '{current_user.username}': "
                f"{file.filename} (ID: {file_id}, Size: {file_metadata['size']} bytes)"
            )

            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content={
                    "success": True,
                    "uploaded": True,
                    "file": file_metadata,
                    "message": "File uploaded and validated successfully",
                    "warnings": validation_result.warnings,
                    "user": current_user.username
                }
            )

        except Exception as e:
            # Clean up temp file on error
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass

            logger.error(f"Error processing file upload from user '{current_user.username}': {e}")

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing file upload: {str(e)}"
            )

    @app.get("/api/upload/{file_id}")
    async def get_uploaded_file(
        file_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get metadata for an uploaded file (authentication required)

        Feature #217: Returns file metadata or 404 if not found
        """
        if file_id not in uploaded_files_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File with ID '{file_id}' not found"
            )

        file_metadata = uploaded_files_store[file_id]
        logger.info(f"User '{current_user.username}' retrieved file metadata: {file_id}")

        return file_metadata

    @app.get("/api/upload")
    async def list_uploaded_files(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        List all uploaded files for the current user (authentication required)

        Feature #217: Returns list of user's uploaded files
        """
        user_files = [
            file for file in uploaded_files_store.values()
            if file.get("uploaded_by") == current_user.username
        ]

        return {
            "files": user_files,
            "total": len(user_files),
            "user": current_user.username
        }

    @app.delete("/api/upload/{file_id}")
    async def delete_uploaded_file(
        file_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Delete an uploaded file (authentication required)

        Feature #217: Deletes file or returns 404 if not found
        """
        if file_id not in uploaded_files_store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File with ID '{file_id}' not found"
            )

        file_metadata = uploaded_files_store[file_id]

        # Check ownership
        if file_metadata.get("uploaded_by") != current_user.username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this file"
            )

        # Delete from storage
        try:
            if os.path.exists(file_metadata["storage_path"]):
                os.remove(file_metadata["storage_path"])
        except Exception as e:
            logger.error(f"Error deleting file {file_id}: {e}")

        # Remove from store
        del uploaded_files_store[file_id]

        logger.info(
            f"User '{current_user.username}' deleted file: "
            f"{file_metadata['filename']} (ID: {file_id})"
        )

        return {
            "status": "success",
            "message": f"File '{file_metadata['filename']}' deleted successfully",
            "deleted_file_id": file_id
        }

    # ========================================================================
    # Result Archiving Endpoints (Feature #225)
    # ========================================================================

    # In-memory storage for result archiver (demo only - use database in production)
    result_archiver_storage: Dict[str, Any] = {
        "archiver": None,  # Will be initialized on first use
        "config": {
            "archive_age_days": 30,  # Archive results older than 30 days
            "max_active_results": 500,  # Keep 500 recent results active
            "archive_after_count": 1000  # Archive when exceeding 1000 results
        }
    }

    def get_result_archiver() -> ResultArchiver:
        """Get or create the result archiver instance"""
        if result_archiver_storage["archiver"] is None:
            config = ArchiveConfig(
                archive_age_days=result_archiver_storage["config"]["archive_age_days"],
                max_active_results=result_archiver_storage["config"]["max_active_results"],
                archive_after_count=result_archiver_storage["config"]["archive_after_count"]
            )
            result_archiver_storage["archiver"] = ResultArchiver(config)
            logger.info("Result archiver initialized")
        return result_archiver_storage["archiver"]

    @app.post("/api/results")
    async def add_test_result(
        result_data: Dict[str, Any] = Body(...),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Add a new test result (authentication required)

        Feature #225: Stores test result with timestamp
        Automatically archives old results if thresholds exceeded

        Args:
            result_data: Test result data
            current_user: Authenticated user (injected by dependency)

        Returns:
            Confirmation with result ID
        """
        import uuid

        # Create test result
        result = TestResult(
            test_id=result_data.get("test_id", f"test_{uuid.uuid4().hex}"),
            test_name=result_data.get("test_name", "Unknown Test"),
            journey_id=result_data.get("journey_id", "unknown"),
            status=result_data.get("status", "unknown"),
            timestamp=datetime.now(),
            duration_ms=result_data.get("duration_ms", 0),
            error_message=result_data.get("error_message"),
            metadata=result_data.get("metadata", {}),
            user_id=current_user.user_id  # Feature #364: User isolation
        )

        archiver = get_result_archiver()
        archiver.add_result(result)

        logger.info(
            f"User '{current_user.username}' added test result: "
            f"{result.test_name} (status={result.status})"
        )

        # Check if we need to archive old results
        archive_stats = archiver.archive_old_results()

        # Feature #315: Implement Post/Redirect/Get pattern
        # Return 303 redirect to prevent form resubmission on back button
        return RedirectResponse(
            url=f"/api/results/{result.test_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    @app.get("/api/results/{test_id}")
    async def get_test_result(
        test_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get a specific test result by ID (authentication required)

        Feature #225: Returns result from active or archived storage
        Returns 404 if not found

        Args:
            test_id: Test result ID
            current_user: Authenticated user (injected by dependency)

        Returns:
            Test result data
        """
        archiver = get_result_archiver()
        result = archiver.get_result(test_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Test result with ID '{test_id}' not found"
            )

        # Feature #364: Check user owns this result
        if result.user_id != current_user.user_id:
            logger.warning(
                f"User '{current_user.username}' attempted to access test result '{test_id}' "
                f"owned by user '{result.user_id}'"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this test result"
            )

        logger.info(f"User '{current_user.username}' retrieved test result: {test_id}")

        return result.to_dict()

    @app.get("/api/results")
    async def list_test_results(
        scope: str = "active",  # 'active', 'archived', or 'all'
        limit: Optional[int] = None,
        offset: int = 0,  # Feature #311: Pagination offset
        status: Optional[str] = None,  # Feature #286: Filter by status (all, passed, failed)
        journey_id: Optional[str] = None,  # Feature #286: Filter by journey ID
        search: Optional[str] = None,  # Feature #280: Search by test name
        sort_by: Optional[str] = "test_name",  # Feature #327: Sort field
        sort_order: Optional[str] = "asc",     # Feature #327: Sort order (asc/desc)
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        List test results (authentication required)

        Feature #225: Returns active, archived, or all results
        Feature #280: Search results by test name
        Feature #286: Filter by status and journey ID via URL parameters
        Feature #311: Pagination support with offset and limit
        Feature #327: Sort by field with order (asc/desc)

        Args:
            scope: Which results to return ('active', 'archived', or 'all')
            limit: Optional limit on number of results (default: 20 if offset provided)
            offset: Number of results to skip (for pagination, default: 0)
            status: Optional status filter ('all', 'passed', 'failed')
            journey_id: Optional journey ID to filter by
            search: Optional search term to filter test names (case-insensitive)
            sort_by: Optional field to sort by (test_name, duration, timestamp)
            sort_order: Optional sort order ('asc' or 'desc')
            current_user: Authenticated user (injected by dependency)

        Returns:
            Paginated list of test results with metadata

        Examples:
            /api/results?status=passed&journey_id=journey-1-login
            /api/results?search=login&status=failed
            /api/results?scope=archived&status=passed
            /api/results?offset=0&limit=20  # First page
            /api/results?offset=20&limit=20  # Second page
            /api/results?sort_by=test_name&sort_order=asc  # Sort by name A-Z
            /api/results?sort_by=duration&sort_order=desc  # Sort by duration, longest first
        """
        archiver = get_result_archiver()

        # Get all results (without limit) - we'll apply pagination later
        if scope == "active":
            results = archiver.get_active_results(limit=None)
        elif scope == "archived":
            results = archiver.get_archived_results(limit=None)
        elif scope == "all":
            results = archiver.get_all_results(limit=None)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scope '{scope}'. Must be 'active', 'archived', or 'all'"
            )

        # Feature #286: Apply filters if provided
        from custom.uat_gateway.ui.kanban.results_filter import ResultsFilter, ResultStatus
        filter_obj = ResultsFilter(results)

        # Apply status filter
        if status and status.strip():
            try:
                status_enum = ResultStatus(status.lower())
                filter_obj.filter(status_enum)
            except ValueError:
                # Invalid status, ignore filter
                pass

        # Apply journey filter
        if journey_id and journey_id.strip():
            filter_obj.filter_by_journey(journey_id)

        # Apply search filter
        if search and search.strip():
            filter_obj.search(search)

        # Get final filtered results using all three filters
        if status or journey_id or search:
            # Use filter_all_three to apply all active filters
            status_enum = ResultStatus(status.lower()) if (status and status.strip()) else ResultStatus.ALL
            results = filter_obj.filter_all_three(
                status_enum,
                journey_id if (journey_id and journey_id.strip()) else None,
                search if (search and search.strip()) else ""
            )

        # Feature #364: Filter results by user_id
        user_results = [r for r in results if r.user_id == current_user.user_id]

        # Feature #327: Apply sorting
        if sort_by and sort_by.strip():
            # Create a new filter object with the filtered results to sort them
            sort_filter_obj = ResultsFilter(user_results)
            user_results = sort_filter_obj.sort(sort_by, sort_order or "asc")

        # Log the request
        log_parts = [f"scope={scope}"]
        if status:
            log_parts.append(f"status={status}")
        if journey_id:
            log_parts.append(f"journey_id={journey_id}")
        if search:
            log_parts.append(f"search='{search}'")
        if sort_by:
            log_parts.append(f"sort_by={sort_by}")
            log_parts.append(f"sort_order={sort_order or 'asc'}")

        logger.info(
            f"User '{current_user.username}' listed test results: "
            f"{', '.join(log_parts)}, count={len(user_results)}"
        )

        # Feature #311: Apply pagination
        total_count = len(user_results)

        # Set default limit if offset is provided but limit is not
        if offset > 0 and limit is None:
            limit = 20

        # Apply offset and limit
        paginated_results = user_results[offset:offset + limit] if limit is not None else user_results

        # Calculate if there are more results
        # Use the actual limit (or default 20) to check if there are more results
        page_size = limit if limit is not None else len(user_results)
        has_more = (offset + page_size) < total_count if page_size else False

        return {
            "scope": scope,
            "filters": {
                "status": status if (status and status.strip()) else None,
                "journey_id": journey_id if (journey_id and journey_id.strip()) else None,
                "search": search if (search and search.strip()) else None
            },
            "sort": {
                "sort_by": sort_by if (sort_by and sort_by.strip()) else None,
                "sort_order": sort_order if (sort_order and sort_order.strip()) else None
            },
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": total_count,
                "has_more": has_more
            },
            "count": len(paginated_results),
            "results": [r.to_dict() for r in paginated_results]
        }

    @app.post("/api/results/archive")
    async def archive_old_results(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Manually trigger archiving of old results (authentication required)

        Feature #225: Archives old results based on configured criteria
        Returns statistics about what was archived

        Args:
            current_user: Authenticated user (injected by dependency)

        Returns:
            Archiving statistics
        """
        archiver = get_result_archiver()
        stats = archiver.archive_old_results()

        logger.info(
            f"User '{current_user.username}' triggered manual archive: "
            f"{stats['total_archived']} results archived"
        )

        return {
            "status": "success",
            "message": f"Archived {stats['total_archived']} results",
            "stats": stats
        }

    @app.get("/api/results/statistics")
    async def get_result_statistics(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get statistics about test results and archiving (authentication required)

        Feature #225: Returns statistics about active and archived results

        Args:
            current_user: Authenticated user (injected by dependency)

        Returns:
            Result statistics
        """
        archiver = get_result_archiver()
        stats = archiver.get_statistics()

        logger.info(f"User '{current_user.username}' retrieved result statistics")

        return stats

    @app.delete("/api/results/archived")
    async def clear_archived_results(
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Clear all archived results from memory (authentication required)

        Feature #225: Clears archived results (does not affect active results)
        Archived results remain on disk and can be reloaded

        Args:
            current_user: Authenticated user (injected by dependency)

        Returns:
            Confirmation with count of cleared results
        """
        archiver = get_result_archiver()
        count = archiver.clear_archived_results()

        logger.info(
            f"User '{current_user.username}' cleared archived results: {count} results"
        )

        return {
            "status": "success",
            "message": f"Cleared {count} archived results from memory",
            "count": count
        }

    @app.delete("/api/results/{test_id}")
    async def delete_test_result(
        test_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Delete a specific test result (authentication required)

        Feature #318: Support deleting individual test results
        Enables testing deleted record handling - when viewing a deleted result,
        users see a helpful error message

        Args:
            test_id: ID of the test result to delete
            current_user: Authenticated user (injected by dependency)

        Returns:
            Confirmation message or 404 if not found
        """
        archiver = get_result_archiver()
        deleted = archiver.delete_result(test_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Test result with ID '{test_id}' not found"
            )

        logger.info(
            f"User '{current_user.username}' deleted test result: {test_id}"
        )

        # Audit log the sensitive action
        security_audit_logger.log_security_event(
            event_type=SecurityEventType.DATA_DELETED,
            action=f"Deleted test result '{test_id}'",
            outcome="success",
            severity=SecuritySeverity.INFO,
            user_id=current_user.user_id,
            username=current_user.username,
            resource=f"test_result:{test_id}",
            details={
                "test_id": test_id,
                "action": "delete"
            }
        )

        return {
            "status": "success",
            "message": f"Test result '{test_id}' has been deleted",
            "test_id": test_id
        }

    @app.post("/api/results/bulk/delete")
    async def bulk_delete_test_results(
        test_ids: List[str] = Body(..., embed=True),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Delete multiple test results at once (authentication required)

        Feature #389: Bulk operations work
        Allows users to select multiple test results and delete them in a single action

        Args:
            test_ids: List of test result IDs to delete
            current_user: Authenticated user (injected by dependency)

        Returns:
            Summary of deletion results with success/failure counts
        """
        archiver = get_result_archiver()

        deleted_count = 0
        failed_count = 0
        failed_ids = []

        for test_id in test_ids:
            deleted = archiver.delete_result(test_id)
            if deleted:
                deleted_count += 1
            else:
                failed_count += 1
                failed_ids.append(test_id)

        logger.info(
            f"User '{current_user.username}' bulk deleted test results: "
            f"{deleted_count} deleted, {failed_count} failed"
        )

        # Audit log the sensitive bulk action
        security_audit_logger.log_security_event(
            event_type=SecurityEventType.DATA_DELETED,
            action=f"Bulk deleted {deleted_count} test results",
            outcome="success" if failed_count == 0 else "partial",
            severity=SecuritySeverity.INFO,
            user_id=current_user.user_id,
            username=current_user.username,
            resource=f"test_results:bulk",
            details={
                "total_requested": len(test_ids),
                "deleted_count": deleted_count,
                "failed_count": failed_count,
                "failed_ids": failed_ids
            }
        )

        return {
            "status": "success",
            "message": f"Bulk delete completed: {deleted_count} deleted, {failed_count} failed",
            "summary": {
                "total_requested": len(test_ids),
                "deleted_count": deleted_count,
                "failed_count": failed_count,
                "failed_ids": failed_ids
            }
        }

    @app.post("/api/results/bulk/archive")
    async def bulk_archive_test_results(
        test_ids: List[str] = Body(..., embed=True),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Archive multiple test results at once (authentication required)

        Feature #389: Bulk operations work
        Allows users to select multiple test results and archive them in a single action

        Args:
            test_ids: List of test result IDs to archive
            current_user: Authenticated user (injected by dependency)

        Returns:
            Summary of archival results with success/failure counts
        """
        archiver = get_result_archiver()

        archived_count = 0
        failed_count = 0
        failed_ids = []

        for test_id in test_ids:
            # Get the result
            all_results = archiver.get_all_results()
            result = next((r for r in all_results if r.test_id == test_id), None)

            if result and result.is_active:
                result.archive()
                archived_count += 1
            else:
                failed_count += 1
                failed_ids.append(test_id)

        logger.info(
            f"User '{current_user.username}' bulk archived test results: "
            f"{archived_count} archived, {failed_count} failed"
        )

        # Audit log the bulk action
        security_audit_logger.log_security_event(
            event_type=SecurityEventType.DATA_UPDATED,
            action=f"Bulk archived {archived_count} test results",
            outcome="success" if failed_count == 0 else "partial",
            severity=SecuritySeverity.INFO,
            user_id=current_user.user_id,
            username=current_user.username,
            resource=f"test_results:bulk",
            details={
                "total_requested": len(test_ids),
                "archived_count": archived_count,
                "failed_count": failed_count,
                "failed_ids": failed_ids
            }
        )

        return {
            "status": "success",
            "message": f"Bulk archive completed: {archived_count} archived, {failed_count} failed",
            "summary": {
                "total_requested": len(test_ids),
                "archived_count": archived_count,
                "failed_count": failed_count,
                "failed_ids": failed_ids
            }
        }

    # ========================================================================
    # Result Annotations - Feature #386
    # ========================================================================

    @app.post("/api/results/{test_id}/annotations")
    async def add_annotation(
        test_id: str,
        annotation_data: Dict[str, Any] = Body(...),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Add an annotation to a test result (authentication required)

        Feature #386: Complete CRUD workflow for results
        Allows users to add notes/annotations to test results for documentation

        Args:
            test_id: Test result ID
            annotation_data: Annotation data with 'content' field
            current_user: Authenticated user (injected by dependency)

        Returns:
            Created annotation
        """
        # Verify the test result exists
        archiver = get_result_archiver()
        result = archiver.get_result(test_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Test result with ID '{test_id}' not found"
            )

        # Feature #364: Check user owns this result
        if result.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to annotate this test result"
            )

        # Validate annotation content
        content = annotation_data.get("content", "").strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Annotation content cannot be empty"
            )

        # Sanitize content to prevent XSS
        sanitizer = InputSanitizer(security_level=SecurityLevel.MODERATE)
        content = sanitizer.sanitize_string(content)

        # Add annotation
        annotation_store = get_annotation_store()
        annotation = annotation_store.add_annotation(
            test_id=test_id,
            content=content,
            user_id=current_user.user_id,
            username=current_user.username
        )

        logger.info(
            f"User '{current_user.username}' added annotation to test result '{test_id}'"
        )

        return {
            "status": "success",
            "message": "Annotation added successfully",
            "annotation": annotation.to_dict()
        }

    @app.get("/api/results/{test_id}/annotations")
    async def get_annotations(
        test_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Get all annotations for a test result (authentication required)

        Feature #386: Complete CRUD workflow for results
        Returns all annotations for a specific test result

        Args:
            test_id: Test result ID
            current_user: Authenticated user (injected by dependency)

        Returns:
            List of annotations
        """
        # Verify the test result exists
        archiver = get_result_archiver()
        result = archiver.get_result(test_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Test result with ID '{test_id}' not found"
            )

        # Feature #364: Check user owns this result
        if result.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view annotations on this test result"
            )

        # Get annotations
        annotation_store = get_annotation_store()
        annotations = annotation_store.get_annotations(test_id)

        return {
            "test_id": test_id,
            "annotations": [a.to_dict() for a in annotations],
            "count": len(annotations)
        }

    @app.put("/api/results/{test_id}/annotations/{annotation_id}")
    async def update_annotation(
        test_id: str,
        annotation_id: str,
        annotation_data: Dict[str, Any] = Body(...),
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Update an annotation (authentication required)

        Feature #386: Complete CRUD workflow for results
        Allows users to update their own annotations

        Args:
            test_id: Test result ID (for URL consistency)
            annotation_id: Annotation ID
            annotation_data: Annotation data with 'content' field
            current_user: Authenticated user (injected by dependency)

        Returns:
            Updated annotation
        """
        # Validate annotation content
        content = annotation_data.get("content", "").strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Annotation content cannot be empty"
            )

        # Sanitize content to prevent XSS
        sanitizer = InputSanitizer(security_level=SecurityLevel.MODERATE)
        content = sanitizer.sanitize_string(content)

        # Update annotation
        annotation_store = get_annotation_store()
        annotation = annotation_store.update_annotation(
            annotation_id=annotation_id,
            content=content,
            user_id=current_user.user_id,
            username=current_user.username
        )

        if not annotation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Annotation with ID '{annotation_id}' not found or you don't have permission to update it"
            )

        logger.info(
            f"User '{current_user.username}' updated annotation '{annotation_id}' "
            f"on test result '{test_id}'"
        )

        return {
            "status": "success",
            "message": "Annotation updated successfully",
            "annotation": annotation.to_dict()
        }

    @app.delete("/api/results/{test_id}/annotations/{annotation_id}")
    async def delete_annotation(
        test_id: str,
        annotation_id: str,
        current_user: TokenPayload = Depends(get_current_user)
    ) -> Dict[str, Any]:
        """
        Delete an annotation (authentication required)

        Feature #386: Complete CRUD workflow for results
        Allows users to delete their own annotations

        Args:
            test_id: Test result ID (for URL consistency)
            annotation_id: Annotation ID
            current_user: Authenticated user (injected by dependency)

        Returns:
            Confirmation message
        """
        annotation_store = get_annotation_store()
        deleted = annotation_store.delete_annotation(
            annotation_id=annotation_id,
            user_id=current_user.user_id,
            username=current_user.username
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Annotation with ID '{annotation_id}' not found or you don't have permission to delete it"
            )

        logger.info(
            f"User '{current_user.username}' deleted annotation '{annotation_id}' "
            f"on test result '{test_id}'"
        )

        return {
            "status": "success",
            "message": "Annotation deleted successfully",
            "annotation_id": annotation_id
        }

    @app.get("/api/results/export/pdf")
    async def export_results_pdf(
        scope: str = "active",  # 'active', 'archived', or 'all'
        status: Optional[str] = None,  # 'passed', 'failed', 'skipped'
        journey_id: Optional[str] = None,
        search: Optional[str] = None,
        current_user: TokenPayload = Depends(get_current_user)
    ):
        """
        Export test results as PDF report (authentication required)

        Feature #296: Export test results as PDF report
        Generates a professional PDF report with test summary and detailed results

        Args:
            scope: Which results to include ('active', 'archived', 'all')
            status: Filter by test status ('passed', 'failed', 'skipped')
            journey_id: Filter by journey ID
            search: Search term to filter results
            current_user: Authenticated user (injected by dependency)

        Returns:
            PDF file as downloadable response
        """
        from fastapi.responses import Response

        archiver = get_result_archiver()

        # Get results based on scope
        if scope == "active":
            all_results = archiver.get_active_results()
        elif scope == "archived":
            all_results = archiver.get_archived_results()
        else:  # all
            all_results = archiver.get_all_results()

        # Apply filters (same logic as list_test_results endpoint)
        from custom.uat_gateway.ui.kanban.results_filter import ResultsFilter, ResultStatus

        filter_obj = ResultsFilter(all_results)

        # Apply status filter
        if status and status.strip():
            try:
                status_enum = ResultStatus(status.lower())
                filter_obj.filter(status_enum)
            except ValueError:
                pass  # Invalid status, ignore filter

        # Apply journey filter
        if journey_id and journey_id.strip():
            filter_obj.filter_by_journey(journey_id)

        # Apply search filter
        if search and search.strip():
            filter_obj.search(search)

        # Get final filtered results
        if status or journey_id or search:
            status_enum = ResultStatus(status.lower()) if (status and status.strip()) else ResultStatus.ALL
            results = filter_obj.filter_all_three(
                status_enum,
                journey_id if (journey_id and journey_id.strip()) else None,
                search if (search and search.strip()) else ""
            )
        else:
            results = all_results

        # Generate PDF
        pdf_exporter = create_pdf_exporter()

        # Prepare metadata
        metadata = {
            "exported_by": current_user.username,
            "export_date": datetime.now().isoformat(),
            "scope": scope,
            "total_results": len(results)
        }
        if status:
            metadata["status_filter"] = status
        if journey_id:
            metadata["journey_id"] = journey_id
        if search:
            metadata["search_term"] = search

        # Generate PDF
        pdf_bytes = pdf_exporter.export_test_results(
            results=[r.to_dict() for r in results],
            title="UAT Test Results Report",
            metadata=metadata
        )

        # Log the export
        log_parts = [f"scope={scope}", f"count={len(results)}"]
        if status:
            log_parts.append(f"status={status}")
        if journey_id:
            log_parts.append(f"journey_id={journey_id}")
        if search:
            log_parts.append(f"search='{search}'")

        logger.info(
            f"User '{current_user.username}' exported test results as PDF: "
            f"{', '.join(log_parts)}"
        )

        # Return PDF as downloadable file
        filename = f"uat_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    @app.get("/api/results/export/json")
    async def export_results_json(
        scope: str = "active",  # 'active', 'archived', or 'all'
        status: Optional[str] = None,  # 'passed', 'failed', 'skipped'
        journey_id: Optional[str] = None,
        search: Optional[str] = None,
        current_user: TokenPayload = Depends(get_current_user)
    ):
        """
        Export test results as JSON file (authentication required)

        Feature #455: Full data export works
        Exports all test results as a downloadable JSON file with complete data

        Args:
            scope: Which results to include ('active', 'archived', 'all')
            status: Filter by test status ('passed', 'failed', 'skipped')
            journey_id: Filter by journey ID
            search: Search term to filter results
            current_user: Authenticated user (injected by dependency)

        Returns:
            JSON file as downloadable response
        """
        archiver = get_result_archiver()

        # Get results based on scope
        if scope == "active":
            base_results = archiver.get_active_results()
        elif scope == "archived":
            base_results = archiver.get_archived_results()
        else:  # scope == "all"
            active = archiver.get_active_results()
            archived = archiver.get_archived_results()
            base_results = active + archived

        # Apply filters
        if status:
            if status == "passed":
                results = [r for r in base_results if r.status == "passed"]
            elif status == "failed":
                results = [r for r in base_results if r.status == "failed"]
            else:
                results = base_results
        else:
            results = base_results

        if journey_id:
            results = [r for r in results if r.journey_id == journey_id]

        if search:
            search_lower = search.lower()
            results = [r for r in results if search_lower in r.test_name.lower()]

        # Prepare export data
        export_data = {
            "export_metadata": {
                "exported_at": datetime.now().isoformat(),
                "exported_by": current_user.username,
                "export_version": "1.0",
                "export_format": "uat_gateway_json_export"
            },
            "data_summary": {
                "total_results": len(results),
                "passed_results": sum(1 for r in results if r.status == "passed"),
                "failed_results": sum(1 for r in results if r.status == "failed"),
                "scope": scope
            },
            "test_results": [r.to_dict() for r in results]
        }

        # Add filter info to summary
        if status:
            export_data["data_summary"]["status_filter"] = status
        if journey_id:
            export_data["data_summary"]["journey_id"] = journey_id
        if search:
            export_data["data_summary"]["search_term"] = search

        # Create temporary file
        import json
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"uat_test_results_{timestamp}.json"
        temp_file = Path(tempfile.gettempdir()) / filename

        # Write JSON to file
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        # Log the export
        log_parts = [f"scope={scope}", f"count={len(results)}"]
        if status:
            log_parts.append(f"status={status}")
        if journey_id:
            log_parts.append(f"journey_id={journey_id}")
        if search:
            log_parts.append(f"search='{search}'")

        logger.info(
            f"User '{current_user.username}' exported test results as JSON: "
            f"{', '.join(log_parts)}"
        )

        # Return JSON as downloadable file
        return FileResponse(
            path=str(temp_file),
            filename=filename,
            media_type='application/json',
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    @app.get("/api/results/export/csv")
    async def export_results_csv(
        scope: str = "active",  # 'active', 'archived', or 'all'
        status: Optional[str] = None,  # 'passed', 'failed', 'skipped'
        journey_id: Optional[str] = None,
        search: Optional[str] = None,
        current_user: TokenPayload = Depends(get_current_user)
    ):
        """
        Export test results as CSV file (authentication required)

        Feature #461: Multiple export formats
        Exports test results as a downloadable CSV file with tabular data

        Args:
            scope: Which results to include ('active', 'archived', 'all')
            status: Filter by test status ('passed', 'failed', 'skipped')
            journey_id: Filter by journey ID
            search: Search term to filter results
            current_user: Authenticated user (injected by dependency)

        Returns:
            CSV file as downloadable response
        """
        from custom.uat_gateway.utils.csv_exporter import create_csv_exporter

        archiver = get_result_archiver()

        # Get results based on scope
        if scope == "active":
            base_results = archiver.get_active_results()
        elif scope == "archived":
            base_results = archiver.get_archived_results()
        else:  # scope == "all"
            active = archiver.get_active_results()
            archived = archiver.get_archived_results()
            base_results = active + archived

        # Apply filters (same logic as JSON export)
        if status:
            if status == "passed":
                results = [r for r in base_results if r.status == "passed"]
            elif status == "failed":
                results = [r for r in base_results if r.status == "failed"]
            else:
                results = base_results
        else:
            results = base_results

        if journey_id:
            results = [r for r in results if r.journey_id == journey_id]

        if search:
            search_lower = search.lower()
            results = [r for r in results if search_lower in r.test_name.lower()]

        # Generate CSV
        csv_exporter = create_csv_exporter()

        # Convert results to dictionaries for CSV export
        results_dicts = [r.to_dict() for r in results]

        # Export to CSV
        csv_path = csv_exporter.export_test_results(
            results=results_dicts,
            include_metadata=True
        )

        # Log the export
        log_parts = [f"scope={scope}", f"count={len(results)}"]
        if status:
            log_parts.append(f"status={status}")
        if journey_id:
            log_parts.append(f"journey_id={journey_id}")
        if search:
            log_parts.append(f"search='{search}'")

        logger.info(
            f"User '{current_user.username}' exported test results as CSV: "
            f"{', '.join(log_parts)}"
        )

        # Return CSV as downloadable file
        filename = Path(csv_path).name

        return FileResponse(
            path=csv_path,
            filename=filename,
            media_type='text/csv',
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    # ========================================================================
    # Test Endpoints (for development and testing)
    # ========================================================================

    @app.get("/api/test/delay")
    async def test_delay_endpoint(
        ms: int = 1000,
        current_user: TokenPayload = Depends(get_current_user_optional)
    ) -> Dict[str, Any]:
        """
        Test endpoint that simulates delayed API responses

        Feature #320: Late API response handling
        Used to test loading indicators, request cancellation, and timeout handling

        Args:
            ms: Delay in milliseconds (default: 1000, max: 30000)
            current_user: Authenticated user (optional for testing)

        Returns:
            Response with delay information
        """
        import asyncio

        # Clamp delay to reasonable values
        delay_ms = max(100, min(30000, ms))
        delay_seconds = delay_ms / 1000.0

        logger.info(
            f"Test delay endpoint called: {delay_ms}ms delay "
            f"(user: {current_user.username if current_user else 'anonymous'})"
        )

        # Simulate delay
        await asyncio.sleep(delay_seconds)

        return {
            "status": "success",
            "message": f"Response delayed by {delay_ms}ms",
            "delay_ms": delay_ms,
            "timestamp": datetime.now().isoformat(),
            "user": current_user.username if current_user else "anonymous"
        }

    @app.get("/api/test/random")
    async def test_random_delay_endpoint(
        min_ms: int = 500,
        max_ms: int = 5000,
        current_user: TokenPayload = Depends(get_current_user_optional)
    ) -> Dict[str, Any]:
        """
        Test endpoint with random delay

        Feature #320: Late API response handling
        Simulates unpredictable response times

        Args:
            min_ms: Minimum delay in milliseconds
            max_ms: Maximum delay in milliseconds
            current_user: Authenticated user (optional)

        Returns:
            Response with actual delay information
        """
        import asyncio
        import random

        delay_ms = random.randint(min_ms, max_ms)
        delay_seconds = delay_ms / 1000.0

        logger.info(
            f"Test random delay endpoint called: {delay_ms}ms delay "
            f"(user: {current_user.username if current_user else 'anonymous'})"
        )

        await asyncio.sleep(delay_seconds)

        return {
            "status": "success",
            "message": f"Response delayed by random amount: {delay_ms}ms",
            "delay_ms": delay_ms,
            "min_ms": min_ms,
            "max_ms": max_ms,
            "timestamp": datetime.now().isoformat(),
            "user": current_user.username if current_user else "anonymous"
        }

    # ========================================================================
    # Web UI Endpoints
    # ========================================================================

    # Initialize templates
    templates = Jinja2Templates(directory="src/api_server/templates")

    @app.get("/results/search", response_class=HTMLResponse)
    async def get_results_search_page(
        request: Request,
        current_user: Optional[TokenPayload] = Depends(get_current_user_optional)
    ):
        """
        Display results search page with empty state handling (Feature #280)

        Feature #280: Search returns no results gracefully
        - Search for test results by name
        - Shows helpful message when no results found
        - Provides option to clear search
        - UI remains functional after empty search

        Feature #337: ARIA labeling for accessibility
        - Page loads without auth for testing accessibility
        - All interactive elements have ARIA labels

        Args:
            request: FastAPI request object
            current_user: Authenticated user (optional, for testing)

        Returns:
            HTML page with search interface
        """
        username = current_user.username if current_user else "anonymous"
        logger.info(f"User '{username}' accessed results search page")

        return templates.TemplateResponse(
            "results_search.html",
            {
                "request": request,
                "user": username
            }
        )

    @app.get("/upload", response_class=HTMLResponse)
    async def get_file_upload_page(
        request: Request,
        current_user: TokenPayload = Depends(get_current_user)
    ):
        """
        Display file upload page with progress indicator

        Feature #310: Upload progress indicator
        - Shows file upload interface
        - Displays progress bar during upload
        - Shows upload percentage and speed
        - Indicates completion status

        Args:
            request: FastAPI request object
            current_user: Authenticated user (injected by dependency)

        Returns:
            HTML page with file upload interface
        """
        logger.info(f"User '{current_user.username}' accessed file upload page")

        return templates.TemplateResponse(
            "file_upload.html",
            {
                "request": request,
                "user": current_user.username
            }
        )

    @app.get("/test/delay.html", response_class=HTMLResponse)
    async def get_test_delay_page(
        request: Request,
        current_user: Optional[TokenPayload] = Depends(get_current_user_optional)
    ):
        """
        Display test delay page for loading indicator testing

        Feature #396: Loading state during slow operations
        - Test page for loading indicators
        - Shows spinner during API delays
        - Demonstrates progress feedback
        - Tests indicator disappearance on completion

        Args:
            request: FastAPI request object
            current_user: Authenticated user (optional for testing)

        Returns:
            HTML page with delay testing interface
        """
        logger.info(
            f"Test delay page accessed "
            f"(user: {current_user.username if current_user else 'anonymous'})"
        )

        return templates.TemplateResponse(
            "test-delay.html",
            {
                "request": request,
                "user": current_user.username if current_user else "anonymous"
            }
        )

    @app.get("/results/{test_id}", response_class=HTMLResponse)
    async def get_test_result_page(
        test_id: str,
        request: Request,
        current_user: Optional[TokenPayload] = Depends(get_current_user_optional)
    ):
        """
        Display test result details as HTML page

        Feature #285: Direct URL access to test results
        Allows users to bookmark and share direct links to test results

        Args:
            test_id: Test result ID
            request: FastAPI request object
            current_user: Authenticated user (injected by dependency)

        Returns:
            HTML page with test result details
        """
        archiver = get_result_archiver()
        result = archiver.get_result(test_id)

        if not result:
            return templates.TemplateResponse(
                "result_detail.html",
                {
                    "request": request,
                    "test_id": test_id,
                    "error": f"Test result with ID '{test_id}' not found",
                    "status": "not_found"
                }
            )

        # Convert result to dict for template
        result_dict = result.to_dict()

        # Add request context for template
        result_dict["request"] = request

        logger.info(f"User '{current_user.username}' viewed test result page: {test_id}")

        return templates.TemplateResponse(
            "result_detail.html",
            result_dict
        )

    # ========================================================================
    # Feature #393: API Error Response Handling - Test Endpoints
    # ========================================================================

    @app.get("/api/test-rate-limit")
    async def test_rate_limit_endpoint(request: Request):
        """
        Test endpoint that triggers rate limit error

        Feature #393: Used to verify rate limit error handling
        """
        # Return rate limit error
        error = ErrorHandler.handle_rate_limit_error("Rate limit test endpoint", {
            "limit": 10,
            "remaining": 0,
            "reset_time": (datetime.now() + timedelta(seconds=60)).isoformat()
        })
        return JSONResponse(status_code=429, content=error.to_dict())

    @app.get("/api/test-internal-error")
    async def test_internal_error_endpoint(request: Request):
        """
        Test endpoint that triggers internal server error

        Feature #393: Used to verify 500 error handling
        """
        # Raise HTTPException which will be caught by exception handler
        raise HTTPException(
            status_code=500,
            detail="Test internal error for feature #393"
        )

    @app.get("/api/test-not-implemented")
    async def test_not_implemented_endpoint(request: Request):
        """
        Test endpoint that triggers not implemented error

        Feature #393: Used to verify 501 error handling
        """
        # Return 501 error
        error = UserFriendlyError(
            error_code=ErrorCode.NOT_IMPLEMENTED,
            status_code=501,
            technical="Feature #393 test endpoint"
        )
        return JSONResponse(status_code=501, content=error.to_dict())

    logger.info("Feature #393 error handling test endpoints registered")

    # ========================================================================
    # Feature #411: Loading Spinners for Async Operations - Demo Page
    # ========================================================================

    @app.get("/demo/feature411-loading-spinners", response_class=HTMLResponse)
    async def feature411_loading_spinners_demo(request: Request):
        """
        Demo page for Feature #411: Loading spinners for async operations

        This demo page showcases:
        - Loading spinners that appear during async operations
        - Button disable state to prevent duplicate submissions
        - Visual feedback during operation execution
        - Automatic cleanup after completion

        Acceptance Criteria:
        - AC1: User can trigger async operation
        - AC2: Loading spinner appears during operation
        - AC3: Button disabled during operation (prevents retry)
        - AC4: Operation completes successfully
        - AC5: Spinner disappears, button re-enabled after completion
        """
        demo_file = Path("src/ui/kanban/feature411-loading-spinners.html")

        if not demo_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Demo page not found. Please ensure the feature411-loading-spinners.html file exists."
            )

        return FileResponse(demo_file)

    logger.info("Feature #411 loading spinners demo endpoint registered")

    # ========================================================================
    # Feature #453: Rapid Navigation Demo
    # ========================================================================
    @app.get("/test/feature453-rapid-navigation", response_class=HTMLResponse)
    async def feature453_rapid_navigation_demo():
        """
        Feature #453: Rapid Navigation Demo Page

        Demonstrates and tests rapid page navigation with:
        - AC1: Navigate quickly between pages
        - AC2: Verify each page loads
        - AC3: Verify old requests cancelled
        - AC4: Verify final page correct
        - AC5: Verify no errors occur
        """
        demo_file = Path("src/ui/kanban/feature453-rapid-navigation.html")

        if not demo_file.exists():
            raise HTTPException(
                status_code=404,
                detail="Demo page not found. Please ensure the feature453-rapid-navigation.html file exists."
            )

        return FileResponse(demo_file)

    logger.info("Feature #453 rapid navigation demo endpoint registered")

    # ========================================================================
    # Enhanced 404 Not Found Handler
    # ========================================================================

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: HTTPException):
        """
        Handle 404 Not Found errors with user-friendly messages

        Feature #221: Provides helpful error messages and navigation options
        Feature #325: Uses user-friendly error format with error_code, action, timestamp
        """
        requested_path = request.url.path

        # Use user-friendly error handler
        user_friendly_error = ErrorHandler.handle_http_error(404, f"Path: {requested_path}")

        # Get the base error response
        error_response = user_friendly_error.to_dict()

        # Add helpful navigation information (for debugging/development)
        error_response["requested_path"] = requested_path
        error_response["available_endpoints"] = {
            "public": {
                "root": "/",
                "health_check": "/health",
                "api_documentation": "/docs",
                "redoc": "/redoc",
                "openapi_spec": "/openapi.json"
            },
            "authentication": {
                "login": "/auth/login (POST)"
            },
            "protected": {
                "tests": "/api/tests (GET)",
                "create_test_run": "/api/test-runs (POST)",
                "test_run_details": "/api/test-runs/{run_id} (GET)",
                "results": "/api/results (GET)",
                "statistics": "/api/stats (GET)",
                "admin_reset_rate_limit": "/api/admin/reset-rate-limit (POST)"
            }
        }

        return JSONResponse(
            status_code=404,
            content=error_response
        )

    # ========================================================================
    # 405 Method Not Allowed Handler
    # ========================================================================

    @app.exception_handler(405)
    async def method_not_allowed_handler(request: Request, exc: HTTPException):
        """
        Handle 405 Method Not Allowed errors with user-friendly messages

        Feature #393: API error response handling
        Ensures 405 errors follow the same user-friendly format as other errors
        """
        # Use user-friendly error handler
        user_friendly_error = ErrorHandler.handle_http_error(405, exc.detail)

        return JSONResponse(
            status_code=405,
            content=user_friendly_error.to_dict()
        )

    # ========================================================================
    # Request Validation Error Handler
    # ========================================================================

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
        Handle FastAPI request validation errors with user-friendly messages

        Feature #393: API error response handling
        Ensures validation errors follow the same user-friendly format as other errors
        """
        # Format validation errors into a user-friendly message
        errors = exc.errors()
        error_details = []

        for error in errors:
            field = " -> ".join(str(loc) for loc in error["loc"])
            error_details.append(f"{field}: {error['msg']}")

        error_message = "There was a problem with your request"
        if len(error_details) == 1:
            error_message = f"Invalid input: {error_details[0]}"
        elif len(error_details) > 1:
            error_message = f"Multiple validation errors: {'; '.join(error_details[:3])}"

        # Use user-friendly error handler
        user_friendly_error = UserFriendlyError(
            error_code=ErrorCode.INVALID_REQUEST,
            status_code=400,
            user_message=error_message,
            action="Check your input and try again. Make sure all required fields are filled correctly",
            technical=f"Validation errors: {errors}"
        )

        return JSONResponse(
            status_code=400,
            content=user_friendly_error.to_dict()
        )

    # ========================================================================
    # Other Error Handlers
    # ========================================================================

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """
        Handle HTTP exceptions (4xx, 5xx) with user-friendly messages

        Feature #227: Transforms technical errors into clear, actionable responses
        Feature #325: All errors use consistent format with error_code, action, timestamp
        """
        # Transform to user-friendly error (including 404)
        user_friendly_error = ErrorHandler.handle_http_error(exc.status_code, exc.detail)

        return JSONResponse(
            status_code=exc.status_code,
            content=user_friendly_error.to_dict()
        )

    # Register Two-Factor Authentication (2FA) routes
    # Feature #356: Two-factor authentication support
    # register_2fa_routes(app, enable_auth, authenticator, DEMO_USERS, get_current_user_optional)  # Temporarily disabled - import error
    # logger.info("2FA endpoints registered")

    return app


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    requests_per_minute: int = 60,
    requests_per_hour: int = 1000,
    reload: bool = False
):
    """
    Run the UAT Gateway API server

    Args:
        host: Host to bind to
        port: Port to bind to
        requests_per_minute: Rate limit per minute
        requests_per_hour: Rate limit per hour
        reload: Enable auto-reload for development
    """
    app = create_app(
        requests_per_minute=requests_per_minute,
        requests_per_hour=requests_per_hour
    )

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload
    )


if __name__ == "__main__":
    import sys

    # Parse command line arguments
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000

    run_server(host=host, port=port, reload=True)


# Create app instance for uvicorn import
app = create_app()
