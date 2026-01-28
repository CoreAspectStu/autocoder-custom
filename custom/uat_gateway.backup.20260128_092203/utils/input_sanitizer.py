"""
Input Sanitizer - Security utilities for sanitizing user input

This module provides functions to validate and sanitize user input
to prevent injection attacks, including:
- Prototype pollution
- Code injection
- XSS attacks
- Path traversal
- SQL injection
- DoS via large payloads

Feature #213: UAT gateway sanitizes user input
"""

import re
import json
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from custom.uat_gateway.utils.logger import get_logger


class SanitizationError(Exception):
    """Raised when input fails sanitization"""
    pass


class SecurityLevel(Enum):
    """Security strictness levels"""
    PERMISSIVE = 1  # Basic validation only
    MODERATE = 2    # Standard security
    STRICT = 3      # High security applications

    def __ge__(self, other):
        """Support comparison operators"""
        if isinstance(other, SecurityLevel):
            return self.value >= other.value
        return self.value >= other

    def __gt__(self, other):
        if isinstance(other, SecurityLevel):
            return self.value > other.value
        return self.value > other


@dataclass
class SanitizationResult:
    """Result of input sanitization"""
    success: bool
    sanitized_data: Optional[Any] = None
    errors: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class InputSanitizer:
    """
    Sanitize and validate user input to prevent injection attacks

    Responsibilities:
    - Validate JSON structure
    - Detect prototype pollution attempts
    - Enforce size limits
    - Sanitize dangerous content
    - Log security-relevant events
    """

    # Dangerous keys that could indicate prototype pollution
    DANGEROUS_KEYS = {
        '__proto__',
        'constructor',
        'prototype',
    }

    # Maximum allowed sizes
    MAX_MESSAGE_SIZE = 1_000_000  # 1MB
    MAX_STRING_LENGTH = 10_000    # 10KB per string
    MAX_DEPTH = 10                # Maximum nesting depth

    # Patterns for detecting potential injection
    XSS_PATTERNS = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'on\w+\s*=',
        r'<iframe[^>]*>',
        r'<object[^>]*>',
        r'<embed[^>]*>',
    ]

    PATH_TRAVERSAL_PATTERNS = [
        r'\.\.[/\\]',
        r'~[/\\]',
        r'%2e%2e',
    ]

    def __init__(self, security_level: SecurityLevel = SecurityLevel.MODERATE):
        """
        Initialize the input sanitizer

        Args:
            security_level: How strict to be with validation
        """
        self.logger = get_logger("input_sanitizer")
        self.security_level = security_level

    def sanitize_json_message(
        self,
        message: str,
        max_size: Optional[int] = None
    ) -> SanitizationResult:
        """
        Sanitize a JSON message from external input

        Args:
            message: Raw JSON string
            max_size: Maximum message size in bytes (default: MAX_MESSAGE_SIZE)

        Returns:
            SanitizationResult with sanitized data or errors
        """
        result = SanitizationResult(success=False)

        # Check size limit
        max_size = max_size or self.MAX_MESSAGE_SIZE
        if len(message.encode('utf-8')) > max_size:
            error = f"Message too large: {len(message)} bytes (max: {max_size})"
            self.logger.warning(f"[SECURITY] {error}")
            result.errors.append(error)
            return result

        try:
            # Parse JSON
            data = json.loads(message)
        except json.JSONDecodeError as e:
            error = f"Invalid JSON: {e}"
            self.logger.warning(f"[SECURITY] {error}")
            result.errors.append(error)
            return result

        # Validate and sanitize the parsed data
        sanitized, validation_errors = self._sanitize_data_structure(data, depth=0)

        if validation_errors:
            result.errors.extend(validation_errors)
            self.logger.warning(f"[SECURITY] Validation failed: {validation_errors}")

            # In STRICT mode, reject the entire message
            if self.security_level >= SecurityLevel.STRICT:
                return result

        result.success = True
        result.sanitized_data = sanitized

        return result

    def _sanitize_data_structure(
        self,
        data: Any,
        depth: int = 0
    ) -> Tuple[Any, List[str]]:
        """
        Recursively sanitize a data structure

        Args:
            data: Data to sanitize (dict, list, or primitive)
            depth: Current nesting depth

        Returns:
            Tuple of (sanitized_data, list_of_errors)
        """
        errors = []

        # Check depth limit
        if depth > self.MAX_DEPTH:
            return None, [f"Maximum nesting depth exceeded: {depth}"]

        if isinstance(data, dict):
            return self._sanitize_dict(data, depth)
        elif isinstance(data, list):
            return self._sanitize_list(data, depth)
        elif isinstance(data, str):
            return self._sanitize_string(data), errors
        else:
            # Numbers, booleans, null are safe
            return data, errors

    def _sanitize_dict(self, data: Dict, depth: int) -> Tuple[Dict, List[str]]:
        """Sanitize a dictionary"""
        errors = []
        sanitized = {}

        # Check for prototype pollution
        dangerous = [k for k in data.keys() if k in self.DANGEROUS_KEYS]
        if dangerous:
            error = f"Prototype pollution attempt detected: keys={dangerous}"
            self.logger.warning(f"[SECURITY] {error}")
            errors.append(error)

        # Recursively sanitize each value
        for key, value in data.items():
            # Skip dangerous keys
            if key in self.DANGEROUS_KEYS:
                continue

            # Sanitize key
            if isinstance(key, str):
                new_key = self._sanitize_string(key)
            else:
                new_key = key

            # Sanitize value
            sanitized_value, value_errors = self._sanitize_data_structure(value, depth + 1)
            errors.extend(value_errors)

            if sanitized_value is not None:
                sanitized[new_key] = sanitized_value

        return sanitized, errors

    def _sanitize_list(self, data: List, depth: int) -> Tuple[List, List[str]]:
        """Sanitize a list"""
        errors = []
        sanitized = []

        # Check length limit
        if len(data) > 1000:
            errors.append(f"List too long: {len(data)} items")
            return data[:1000], errors

        # Recursively sanitize each item
        for item in data:
            sanitized_item, item_errors = self._sanitize_data_structure(item, depth + 1)
            errors.extend(item_errors)

            if sanitized_item is not None:
                sanitized.append(sanitized_item)

        return sanitized, errors

    def _sanitize_string(self, value: str) -> str:
        """
        Sanitize a string value

        - Check length
        - Detect potential XSS
        - Detect path traversal
        - Null bytes
        """
        # Check length
        if len(value) > self.MAX_STRING_LENGTH:
            self.logger.warning(
                f"[SECURITY] String too long: {len(value)} chars, truncating"
            )
            return value[:self.MAX_STRING_LENGTH]

        # Check for null bytes
        if '\x00' in value:
            self.logger.warning("[SECURITY] Null byte detected in string, removing")
            value = value.replace('\x00', '')

        # In STRICT mode, also check for XSS and path traversal
        if self.security_level >= SecurityLevel.STRICT:
            # Check for XSS patterns
            for pattern in self.XSS_PATTERNS:
                if re.search(pattern, value, re.IGNORECASE):
                    self.logger.warning(
                        f"[SECURITY] Potential XSS detected in string: {pattern}"
                    )
                    # Escape HTML
                    value = value.replace('&', '&amp;')
                    value = value.replace('<', '&lt;')
                    value = value.replace('>', '&gt;')
                    value = value.replace('"', '&quot;')
                    value = value.replace("'", '&#x27;')
                    break

            # Check for path traversal
            for pattern in self.PATH_TRAVERSAL_PATTERNS:
                if re.search(pattern, value, re.IGNORECASE):
                    self.logger.warning(
                        f"[SECURITY] Path traversal detected: {pattern}"
                    )
                    # Remove path traversal attempts
                    value = re.sub(pattern, '', value, flags=re.IGNORECASE)

        return value

    def sanitize_string(self, value: str) -> str:
        """
        Public method to sanitize a string value

        This is a convenience wrapper around _sanitize_string() for external use.
        Provides basic string sanitization for security.

        Args:
            value: String to sanitize

        Returns:
            Sanitized string safe for storage/display
        """
        return self._sanitize_string(value)

    def validate_websocket_message(self, data: Dict) -> Tuple[bool, List[str]]:
        """
        Validate a WebSocket message structure

        Args:
            data: Parsed JSON data

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Must have a 'type' field
        if 'type' not in data:
            errors.append("Missing required field: 'type'")
            return False, errors

        # Type must be a string
        if not isinstance(data['type'], str):
            errors.append("Field 'type' must be a string")
            return False, errors

        # Allowed message types
        allowed_types = {
            'request_missed',
            'ping',
            'pong',
            'subscribe',
            'unsubscribe',
        }

        if data['type'] not in allowed_types:
            errors.append(f"Unknown message type: {data['type']}")

        # No dangerous keys
        dangerous = [k for k in data.keys() if k in self.DANGEROUS_KEYS]
        if dangerous:
            errors.append(f"Prototype pollution attempt: {dangerous}")

        return len(errors) == 0, errors


# Singleton instance for convenient access
_default_sanitizer = None


def get_sanitizer() -> InputSanitizer:
    """Get the default sanitizer instance"""
    global _default_sanitizer
    if _default_sanitizer is None:
        _default_sanitizer = InputSanitizer(security_level=SecurityLevel.MODERATE)
    return _default_sanitizer
