"""
User-Friendly Error Handler for UAT Gateway API

Transforms technical error messages into clear, actionable, user-friendly messages.
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ErrorCode:
    """Error code constants"""

    # Authentication errors (4xx)
    AUTH_NO_TOKEN = "AUTH_NO_TOKEN"
    AUTH_INVALID_TOKEN = "AUTH_INVALID_TOKEN"
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_NOT_ENABLED = "AUTH_NOT_ENABLED"

    # Rate limiting errors (429)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Timeout errors (408)
    REQUEST_TIMEOUT = "REQUEST_TIMEOUT"

    # Client errors (4xx)
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class ErrorMessage:
    """User-friendly error message templates"""

    _messages = {
        # Authentication errors
        ErrorCode.AUTH_NO_TOKEN: {
            "user_message": "Please sign in to access this feature",
            "action": "Navigate to the login page and enter your credentials",
            "technical": "No authentication token provided"
        },
        ErrorCode.AUTH_INVALID_TOKEN: {
            "user_message": "Your session has been invalidated. Please sign in again",
            "action": "Go to the login page and sign in with your credentials",
            "technical": "Invalid token"
        },
        ErrorCode.AUTH_TOKEN_EXPIRED: {
            "user_message": "Your session has expired. Please sign in again",
            "action": "Return to the login page to start a new session",
            "technical": "Token has expired"
        },
        ErrorCode.AUTH_INVALID_CREDENTIALS: {
            "user_message": "We couldn't verify your account details",
            "action": "Check your username and password, then try again. If you've forgotten your password, use the password reset link",
            "technical": "Invalid username or password"
        },
        ErrorCode.AUTH_NOT_ENABLED: {
            "user_message": "This feature is not currently available",
            "action": "Contact your system administrator to enable authentication",
            "technical": "Authentication not enabled"
        },

        # Rate limiting errors
        ErrorCode.RATE_LIMIT_EXCEEDED: {
            "user_message": "You're making requests too quickly. Please wait a moment",
            "action": "Slow down your request pace. You can try again in a few seconds",
            "technical": "Rate limit exceeded"
        },

        # Timeout errors
        ErrorCode.REQUEST_TIMEOUT: {
            "user_message": "The request took too long to complete",
            "action": "Try again. If the problem continues, the server may be under heavy load or there may be network issues",
            "technical": "Request timeout"
        },

        # Client errors
        ErrorCode.INVALID_REQUEST: {
            "user_message": "There was a problem with your request",
            "action": "Check your input and try again. Make sure all required fields are filled correctly",
            "technical": "Invalid request"
        },
        ErrorCode.NOT_FOUND: {
            "user_message": "The page or resource you're looking for doesn't exist",
            "action": "Verify the URL or return to the previous page",
            "technical": "Resource not found"
        },
        ErrorCode.METHOD_NOT_ALLOWED: {
            "user_message": "This action is not supported",
            "action": "Try navigating to the page using the provided menu or return to the previous page",
            "technical": "Method not allowed"
        },

        # Server errors
        ErrorCode.INTERNAL_ERROR: {
            "user_message": "Something went wrong on our end. Please try again",
            "action": "Refresh the page and retry. If the problem continues, contact support with the error code",
            "technical": "Internal server error"
        },
        ErrorCode.NOT_IMPLEMENTED: {
            "user_message": "This feature is still being developed",
            "action": "Check back later or contact support for availability information",
            "technical": "Not implemented"
        },
        ErrorCode.SERVICE_UNAVAILABLE: {
            "user_message": "The service is temporarily unavailable",
            "action": "Wait a few minutes and try again. If problems persist, check system status",
            "technical": "Service unavailable"
        }
    }

    @classmethod
    def get_message(cls, error_code: str) -> Dict[str, str]:
        """
        Get user-friendly error message for an error code

        Args:
            error_code: Error code constant

        Returns:
            Dictionary with user_message, action, and technical details
        """
        return cls._messages.get(error_code, {
            "user_message": "An unexpected error occurred",
            "action": "Try refreshing the page. If the problem continues, please contact support",
            "technical": "Unknown error"
        })


class UserFriendlyError:
    """
    User-friendly error response structure

    Provides clear, actionable error messages without technical jargon.
    """

    def __init__(
        self,
        error_code: str,
        status_code: int,
        user_message: Optional[str] = None,
        action: Optional[str] = None,
        technical: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Create a user-friendly error response

        Args:
            error_code: Error code constant from ErrorCode
            status_code: HTTP status code
            user_message: Override default user message
            action: Override default action message
            technical: Override technical message
            details: Additional error details (won't be shown to users)
        """
        self.error_code = error_code
        self.status_code = status_code
        # Ensure UTC timestamp with 'Z' suffix for ISO 8601 compliance
        self.timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

        # Get default messages
        defaults = ErrorMessage.get_message(error_code)

        # Use provided messages or defaults
        self.user_message = user_message or defaults["user_message"]
        self.action = action or defaults["action"]
        self.technical = technical or defaults["technical"]
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON response

        Returns:
            Dictionary with user-friendly error information
        """
        result = {
            "error": self.user_message,
            "error_code": self.error_code,
            "action": self.action,
            "timestamp": self.timestamp
        }

        # Include details if present (e.g., validation_errors)
        # Feature #406: Server-side validation - field-level errors must be returned
        if self.details:
            result["details"] = self.details

        return result

    def to_dict_with_technical(self) -> Dict[str, Any]:
        """
        Convert to dictionary with technical details (for debugging)

        Returns:
            Dictionary with user-friendly and technical error information
        """
        result = self.to_dict()
        result["technical"] = self.technical
        if self.details:
            result["details"] = self.details
        return result


class ErrorHandler:
    """
    Transforms technical errors into user-friendly responses

    Maps HTTP status codes and technical error messages to user-friendly
    error codes and messages.
    """

    @staticmethod
    def handle_auth_error(detail: str) -> UserFriendlyError:
        """
        Transform authentication error into user-friendly message

        Args:
            detail: Technical error detail

        Returns:
            UserFriendlyError with clear, actionable message
        """
        detail_lower = detail.lower()

        if "no token" in detail_lower or "not provided" in detail_lower:
            return UserFriendlyError(
                error_code=ErrorCode.AUTH_NO_TOKEN,
                status_code=401
            )
        elif "expired" in detail_lower:
            return UserFriendlyError(
                error_code=ErrorCode.AUTH_TOKEN_EXPIRED,
                status_code=401
            )
        elif "invalid" in detail_lower and "username" in detail_lower or "password" in detail_lower:
            return UserFriendlyError(
                error_code=ErrorCode.AUTH_INVALID_CREDENTIALS,
                status_code=401
            )
        elif "invalid token" in detail_lower:
            return UserFriendlyError(
                error_code=ErrorCode.AUTH_INVALID_TOKEN,
                status_code=401
            )
        elif "not enabled" in detail_lower:
            return UserFriendlyError(
                error_code=ErrorCode.AUTH_NOT_ENABLED,
                status_code=501
            )
        else:
            return UserFriendlyError(
                error_code=ErrorCode.AUTH_INVALID_TOKEN,
                status_code=401,
                user_message="There was a problem verifying your account",
                action="Please sign in again to continue"
            )

    @staticmethod
    def handle_rate_limit_error(detail: str, limit_info: Optional[Dict[str, Any]] = None) -> UserFriendlyError:
        """
        Transform rate limit error into user-friendly message

        Args:
            detail: Technical error detail
            limit_info: Optional rate limit information

        Returns:
            UserFriendlyError with clear, actionable message
        """
        details = {}
        if limit_info:
            details = {
                "limit": limit_info.get("limit"),
                "remaining": limit_info.get("remaining"),
                "reset_at": limit_info.get("reset_time")
            }

        return UserFriendlyError(
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=429,
            details=details
        )

    @staticmethod
    def handle_timeout_error(detail: str, timeout_duration: Optional[int] = None) -> UserFriendlyError:
        """
        Transform timeout error into user-friendly message

        Args:
            detail: Technical error detail
            timeout_duration: Optional timeout duration in seconds

        Returns:
            UserFriendlyError with clear, actionable message
        """
        details = {}
        if timeout_duration:
            details = {
                "timeout_duration_seconds": timeout_duration
            }

        return UserFriendlyError(
            error_code=ErrorCode.REQUEST_TIMEOUT,
            status_code=408,
            details=details
        )

    @staticmethod
    def handle_http_error(status_code: int, detail) -> UserFriendlyError:
        """
        Transform HTTP error into user-friendly message

        Args:
            status_code: HTTP status code
            detail: Technical error detail (string or dict)

        Returns:
            UserFriendlyError with clear, actionable message
        """
        # Feature #387: If detail is already a structured error dict, preserve it
        # This allows specific error types like "invalid_state_transition" to be returned
        if isinstance(detail, dict):
            # Check if it has error field - if so, it's already a proper error response
            if "error" in detail:
                # Convert dict to JSON string for technical field
                import json
                return UserFriendlyError(
                    error_code=detail.get("error", "UNKNOWN_ERROR"),
                    status_code=status_code,
                    technical=json.dumps(detail),
                    user_message=detail.get("message"),
                    details=detail
                )

        # For non-dict details, convert to string if needed
        detail_str = str(detail) if detail is not None else ""

        # Authentication errors (401)
        if status_code == 401:
            return ErrorHandler.handle_auth_error(detail_str)

        # Rate limiting (429)
        if status_code == 429:
            return ErrorHandler.handle_rate_limit_error(detail_str)

        # Request timeout (408)
        if status_code == 408:
            return ErrorHandler.handle_timeout_error(detail_str)

        # Not found (404)
        if status_code == 404:
            return UserFriendlyError(
                error_code=ErrorCode.NOT_FOUND,
                status_code=404,
                technical=detail_str
            )

        # Method not allowed (405)
        if status_code == 405:
            return UserFriendlyError(
                error_code=ErrorCode.METHOD_NOT_ALLOWED,
                status_code=405,
                technical=detail_str
            )

        # Client errors (400-499)
        if 400 <= status_code < 500:
            return UserFriendlyError(
                error_code=ErrorCode.INVALID_REQUEST,
                status_code=status_code,
                technical=detail_str
            )

        # Not implemented (501)
        if status_code == 501:
            return UserFriendlyError(
                error_code=ErrorCode.NOT_IMPLEMENTED,
                status_code=501,
                technical=detail
            )

        # Service unavailable (503)
        if status_code == 503:
            return UserFriendlyError(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                status_code=503,
                technical=detail
            )

        # Server errors (500-599)
        if 500 <= status_code < 600:
            return UserFriendlyError(
                error_code=ErrorCode.INTERNAL_ERROR,
                status_code=status_code,
                technical=detail
            )

        # Unknown status
        return UserFriendlyError(
            error_code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
            technical=detail
        )

    @staticmethod
    def handle_exception(exception: Exception) -> UserFriendlyError:
        """
        Transform any exception into user-friendly error

        Args:
            exception: Exception instance

        Returns:
            UserFriendlyError with clear, actionable message
        """
        logger.error(f"Unhandled exception: {type(exception).__name__}: {exception}")

        return UserFriendlyError(
            error_code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
            technical=f"{type(exception).__name__}: {str(exception)}"
        )


def create_error_response(status_code: int, detail: str) -> Dict[str, Any]:
    """
    Create a user-friendly error response dictionary

    Args:
        status_code: HTTP status code
        detail: Technical error detail

    Returns:
        Dictionary with user-friendly error information
    """
    error = ErrorHandler.handle_http_error(status_code, detail)
    return error.to_dict()


def create_error_response_with_technical(status_code: int, detail: str) -> Dict[str, Any]:
    """
    Create a user-friendly error response with technical details (for debugging)

    Args:
        status_code: HTTP status code
        detail: Technical error detail

    Returns:
        Dictionary with user-friendly and technical error information
    """
    error = ErrorHandler.handle_http_error(status_code, detail)
    return error.to_dict_with_technical()
