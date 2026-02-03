"""
UAT Gateway Validation Utilities

Provides validation functions for user input:
- Journey name validation
- Field validation with clear error messages
- Validation rule definitions
"""

import re
import logging
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass


logger = logging.getLogger(__name__)


# ============================================================================
# Validation Exceptions
# ============================================================================

class ValidationError(Exception):
    """Base exception for validation errors"""

    def __init__(self, message: str, field: str = "unknown"):
        self.message = message
        self.field = field
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "error": "validation_error",
            "field": self.field,
            "message": self.message
        }


# ============================================================================
# Validation Rules
# ============================================================================

@dataclass
class ValidationResult:
    """Result of a validation operation"""
    is_valid: bool
    message: Optional[str] = None
    field: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "valid": self.is_valid,
            "field": self.field,
            "message": self.message if self.message else ""
        }


class JourneyNameValidator:
    """
    Validates journey names according to UAT Gateway standards

    Rules:
    - Required: Cannot be empty or None
    - Length: 3-100 characters
    - Characters: Letters, numbers, spaces, hyphens, underscores
    - No leading/trailing whitespace
    - No special characters that break file systems
    - Case-insensitive uniqueness (when checked against existing names)
    """

    # Journey name validation patterns
    MIN_LENGTH = 3
    MAX_LENGTH = 100
    ALLOWED_PATTERN = re.compile(r'^[\w\s\-]+$')
    FORBIDDEN_NAMES = {
        'null', 'undefined', 'none', 'void',
        'con', 'prn', 'aux', 'nul',  # Windows reserved
        'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
        'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
    }

    @classmethod
    def validate(cls, name: Optional[str], existing_names: Optional[List[str]] = None) -> ValidationResult:
        """
        Validate a journey name

        Args:
            name: The journey name to validate
            existing_names: Optional list of existing names for uniqueness check

        Returns:
            ValidationResult with is_valid flag and error message if invalid

        Examples:
            >>> JourneyNameValidator.validate("User Login")
            ValidationResult(is_valid=True, message=None)

            >>> JourneyNameValidator.validate("")
            ValidationResult(is_valid=False, message="Journey name cannot be empty")

            >>> JourneyNameValidator.validate("ab")
            ValidationResult(is_valid=False, message="Journey name must be at least 3 characters")
        """
        # Rule 1: Required field
        if name is None:
            logger.warning("Journey name validation failed: name is None")
            return ValidationResult(
                is_valid=False,
                message="Journey name is required",
                field="name"
            )

        # Rule 2: Must be string
        if not isinstance(name, str):
            logger.warning(f"Journey name validation failed: name is not a string (type: {type(name)})")
            return ValidationResult(
                is_valid=False,
                message="Journey name must be a string",
                field="name"
            )

        # Rule 3: Cannot be empty or whitespace only
        stripped_name = name.strip()
        if not stripped_name:
            logger.warning("Journey name validation failed: name is empty or whitespace only")
            return ValidationResult(
                is_valid=False,
                message="Journey name cannot be empty or contain only whitespace",
                field="name"
            )

        # Rule 4: No leading/trailing whitespace
        if name != stripped_name:
            logger.warning(f"Journey name validation failed: name has leading/trailing whitespace: '{name}'")
            return ValidationResult(
                is_valid=False,
                message="Journey name cannot start or end with whitespace",
                field="name"
            )

        # Rule 5: Minimum length
        if len(stripped_name) < cls.MIN_LENGTH:
            logger.warning(f"Journey name validation failed: name too short ({len(stripped_name)} < {cls.MIN_LENGTH})")
            return ValidationResult(
                is_valid=False,
                message=f"Journey name must be at least {cls.MIN_LENGTH} characters long (got {len(stripped_name)})",
                field="name"
            )

        # Rule 6: Maximum length
        if len(stripped_name) > cls.MAX_LENGTH:
            logger.warning(f"Journey name validation failed: name too long ({len(stripped_name)} > {cls.MAX_LENGTH})")
            return ValidationResult(
                is_valid=False,
                message=f"Journey name must be no more than {cls.MAX_LENGTH} characters long (got {len(stripped_name)})",
                field="name"
            )

        # Rule 7: Allowed characters only
        if not cls.ALLOWED_PATTERN.match(stripped_name):
            logger.warning(f"Journey name validation failed: invalid characters in '{stripped_name}'")
            return ValidationResult(
                is_valid=False,
                message="Journey name can only contain letters, numbers, spaces, hyphens, and underscores",
                field="name"
            )

        # Rule 8: Not a forbidden/reserved name (case-insensitive)
        if stripped_name.lower() in cls.FORBIDDEN_NAMES:
            logger.warning(f"Journey name validation failed: name is forbidden/reserved: '{stripped_name}'")
            return ValidationResult(
                is_valid=False,
                message=f"'{stripped_name}' is a reserved name and cannot be used",
                field="name"
            )

        # Rule 9: Case-insensitive uniqueness (if existing names provided)
        if existing_names:
            existing_lower = [n.lower() for n in existing_names]
            if stripped_name.lower() in existing_lower:
                logger.warning(f"Journey name validation failed: name already exists: '{stripped_name}'")
                return ValidationResult(
                    is_valid=False,
                    message=f"A journey with the name '{stripped_name}' already exists (names are case-insensitive)",
                    field="name"
                )

        # All validations passed
        logger.info(f"Journey name validation passed: '{stripped_name}'")
        return ValidationResult(
            is_valid=True,
            message=None,
            field="name"
        )

    @classmethod
    def validate_and_raise(cls, name: Optional[str], existing_names: Optional[List[str]] = None) -> str:
        """
        Validate journey name and raise ValidationError if invalid

        Args:
            name: The journey name to validate
            existing_names: Optional list of existing names for uniqueness check

        Returns:
            The validated (stripped) journey name

        Raises:
            ValidationError: If validation fails
        """
        result = cls.validate(name, existing_names)

        if not result.is_valid:
            raise ValidationError(result.message, result.field)

        return name.strip()


# ============================================================================
# Additional Validators (for future expansion)
# ============================================================================

class DescriptionValidator:
    """Validates journey and scenario descriptions"""

    MIN_LENGTH = 10
    MAX_LENGTH = 1000

    @classmethod
    def validate(cls, description: Optional[str]) -> ValidationResult:
        """Validate a description field"""
        if description is None:
            # Description is optional
            return ValidationResult(is_valid=True, message=None, field="description")

        if not isinstance(description, str):
            return ValidationResult(
                is_valid=False,
                message="Description must be a string",
                field="description"
            )

        if len(description.strip()) < cls.MIN_LENGTH:
            return ValidationResult(
                is_valid=False,
                message=f"Description must be at least {cls.MIN_LENGTH} characters long",
                field="description"
            )

        if len(description) > cls.MAX_LENGTH:
            return ValidationResult(
                is_valid=False,
                message=f"Description must be no more than {cls.MAX_LENGTH} characters long",
                field="description"
            )

        return ValidationResult(is_valid=True, message=None, field="description")


class PriorityValidator:
    """Validates journey priority values"""

    MIN_PRIORITY = 1
    MAX_PRIORITY = 10

    @classmethod
    def validate(cls, priority: int) -> ValidationResult:
        """Validate a priority value"""
        if not isinstance(priority, int):
            return ValidationResult(
                is_valid=False,
                message="Priority must be an integer",
                field="priority"
            )

        if priority < cls.MIN_PRIORITY or priority > cls.MAX_PRIORITY:
            return ValidationResult(
                is_valid=False,
                message=f"Priority must be between {cls.MIN_PRIORITY} and {cls.MAX_PRIORITY}",
                field="priority"
            )

        return ValidationResult(is_valid=True, message=None, field="priority")


# ============================================================================
# Convenience Functions
# ============================================================================

def validate_journey_name(name: Optional[str], existing_names: Optional[List[str]] = None) -> ValidationResult:
    """
    Convenience function for journey name validation

    Args:
        name: The journey name to validate
        existing_names: Optional list of existing names for uniqueness check

    Returns:
        ValidationResult with validation status

    Example:
        >>> result = validate_journey_name("User Login")
        >>> if result.is_valid:
        ...     print("Valid!")
        ... else:
        ...     print(f"Error: {result.message}")
    """
    return JourneyNameValidator.validate(name, existing_names)


def validate_journey_data(data: Dict[str, Any], existing_names: Optional[List[str]] = None) -> Tuple[bool, List[ValidationError]]:
    """
    Validate complete journey data

    Args:
        data: Dictionary containing journey data (name, description, priority, etc.)
        existing_names: Optional list of existing journey names for uniqueness check

    Returns:
        Tuple of (is_valid, list_of_validation_errors)

    Example:
        >>> is_valid, errors = validate_journey_data({
        ...     "name": "User Login",
        ...     "description": "User authentication flow",
        ...     "priority": 5
        ... })
        >>> if is_valid:
        ...     print("Journey data is valid!")
        ... else:
        ...     for error in errors:
        ...         print(f"Error in {error.field}: {error.message}")
    """
    errors = []

    # Validate name (required)
    name = data.get("name")
    name_result = JourneyNameValidator.validate(name, existing_names)
    if not name_result.is_valid:
        errors.append(ValidationError(name_result.message, name_result.field))

    # Validate description (optional but has constraints if provided)
    description = data.get("description")
    if description is not None:
        desc_result = DescriptionValidator.validate(description)
        if not desc_result.is_valid:
            errors.append(ValidationError(desc_result.message, desc_result.field))

    # Validate priority (optional but has constraints if provided)
    priority = data.get("priority")
    if priority is not None:
        priority_result = PriorityValidator.validate(priority)
        if not priority_result.is_valid:
            errors.append(ValidationError(priority_result.message, priority_result.field))

    return len(errors) == 0, errors


# ============================================================================
# Configuration Validators (Feature #230)
# ============================================================================

class ConfigValidator:
    """
    Validates UAT Gateway configuration settings

    Rules:
    - Port must be between 1024-65535 (non-privileged)
    - Max parallel tests must be between 1-10
    - Retry attempts must be between 0-5
    - Timeout must be between 1-300 seconds
    - Diff threshold must be between 0.0-1.0
    - Boolean fields must be actual booleans
    - URLs must be valid if provided
    """

    MIN_PORT = 1024
    MAX_PORT = 65535
    MIN_PARALLEL = 1
    MAX_PARALLEL = 10
    MIN_RETRIES = 0
    MAX_RETRIES = 5
    MIN_TIMEOUT = 1
    MAX_TIMEOUT = 300
    MIN_DIFF_THRESHOLD = 0.0
    MAX_DIFF_THRESHOLD = 1.0

    # URL validation pattern
    URL_PATTERN = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:\S+(?::\S*)?@)?'  # optional username:password@
        r'(?:'  # IP address exclusion
        r'(?:[1-9]\d?|1\d\d|2[01]\d|22[0-3])'  # IP range
        r'\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])'  # IP range
        r'\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])'  # IP range
        r'\.(?:1?\d{1,2}|2[0-4]\d|25[0-5])'  # IP range
        r'|'  # or domain name
        r'(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+'  # domain
        r'(?:\.(?:[a-z\u00a1-\uffff0-9]-*)*[a-z\u00a1-\uffff0-9]+)*'  # subdomains
        r')'
        r'(?::\d{2,5})?'  # optional port
        r'(?:/[^\s]*)?'  # optional path
        r'$', re.IGNORECASE
    )

    @classmethod
    def validate_port(cls, port: Any) -> ValidationResult:
        """Validate server port configuration"""
        if not isinstance(port, int):
            return ValidationResult(
                is_valid=False,
                message="Port must be an integer",
                field="port"
            )

        if port < cls.MIN_PORT or port > cls.MAX_PORT:
            return ValidationResult(
                is_valid=False,
                message=f"Port must be between {cls.MIN_PORT} and {cls.MAX_PORT} (got {port})",
                field="port"
            )

        return ValidationResult(is_valid=True, message=None, field="port")

    @classmethod
    def validate_parallel_tests(cls, max_parallel: Any) -> ValidationResult:
        """Validate max parallel tests configuration"""
        if not isinstance(max_parallel, int):
            return ValidationResult(
                is_valid=False,
                message="Max parallel tests must be an integer",
                field="max_parallel_tests"
            )

        if max_parallel < cls.MIN_PARALLEL or max_parallel > cls.MAX_PARALLEL:
            return ValidationResult(
                is_valid=False,
                message=f"Max parallel tests must be between {cls.MIN_PARALLEL} and {cls.MAX_PARALLEL} (got {max_parallel})",
                field="max_parallel_tests"
            )

        return ValidationResult(is_valid=True, message=None, field="max_parallel_tests")

    @classmethod
    def validate_retries(cls, max_retries: Any) -> ValidationResult:
        """Validate max retries configuration"""
        if not isinstance(max_retries, int):
            return ValidationResult(
                is_valid=False,
                message="Max retries must be an integer",
                field="max_retries"
            )

        if max_retries < cls.MIN_RETRIES or max_retries > cls.MAX_RETRIES:
            return ValidationResult(
                is_valid=False,
                message=f"Max retries must be between {cls.MIN_RETRIES} and {cls.MAX_RETRIES} (got {max_retries})",
                field="max_retries"
            )

        return ValidationResult(is_valid=True, message=None, field="max_retries")

    @classmethod
    def validate_timeout(cls, timeout: Any) -> ValidationResult:
        """Validate timeout configuration (in seconds)"""
        if not isinstance(timeout, int):
            return ValidationResult(
                is_valid=False,
                message="Timeout must be an integer (seconds)",
                field="timeout"
            )

        if timeout < cls.MIN_TIMEOUT or timeout > cls.MAX_TIMEOUT:
            return ValidationResult(
                is_valid=False,
                message=f"Timeout must be between {cls.MIN_TIMEOUT} and {cls.MAX_TIMEOUT} seconds (got {timeout})",
                field="timeout"
            )

        return ValidationResult(is_valid=True, message=None, field="timeout")

    @classmethod
    def validate_diff_threshold(cls, threshold: Any) -> ValidationResult:
        """Validate visual diff threshold (0.0 to 1.0)"""
        if not isinstance(threshold, (int, float)):
            return ValidationResult(
                is_valid=False,
                message="Diff threshold must be a number",
                field="diff_threshold"
            )

        try:
            threshold_float = float(threshold)
        except (ValueError, TypeError):
            return ValidationResult(
                is_valid=False,
                message="Diff threshold must be a valid number",
                field="diff_threshold"
            )

        if threshold_float < cls.MIN_DIFF_THRESHOLD or threshold_float > cls.MAX_DIFF_THRESHOLD:
            return ValidationResult(
                is_valid=False,
                message=f"Diff threshold must be between {cls.MIN_DIFF_THRESHOLD} and {cls.MAX_DIFF_THRESHOLD} (got {threshold_float})",
                field="diff_threshold"
            )

        return ValidationResult(is_valid=True, message=None, field="diff_threshold")

    @classmethod
    def validate_boolean(cls, value: Any, field_name: str) -> ValidationResult:
        """Validate a boolean configuration field"""
        if not isinstance(value, bool):
            return ValidationResult(
                is_valid=False,
                message=f"{field_name} must be a boolean (true or false)",
                field=field_name
            )

        return ValidationResult(is_valid=True, message=None, field=field_name)

    @classmethod
    def validate_url(cls, url: Any, field_name: str) -> ValidationResult:
        """Validate a URL configuration field"""
        if url is None:
            # URL is optional
            return ValidationResult(is_valid=True, message=None, field=field_name)

        if not isinstance(url, str):
            return ValidationResult(
                is_valid=False,
                message=f"{field_name} must be a string",
                field=field_name
            )

        if not cls.URL_PATTERN.match(url):
            return ValidationResult(
                is_valid=False,
                message=f"{field_name} must be a valid URL (e.g., http://localhost:8000)",
                field=field_name
            )

        return ValidationResult(is_valid=True, message=None, field=field_name)

    @classmethod
    def validate_config(cls, config: Dict[str, Any]) -> Tuple[bool, List[ValidationError]]:
        """
        Validate complete configuration dictionary

        Args:
            config: Dictionary containing configuration settings

        Returns:
            Tuple of (is_valid, list_of_validation_errors)

        Example:
            >>> config = {
            ...     "port": 8000,
            ...     "max_parallel_tests": 3,
            ...     "max_retries": 2,
            ...     "timeout": 30,
            ...     "diff_threshold": 0.1
            ... }
            >>> is_valid, errors = ConfigValidator.validate_config(config)
        """
        errors = []

        # Validate port (if provided)
        if "port" in config:
            port_result = cls.validate_port(config["port"])
            if not port_result.is_valid:
                errors.append(ValidationError(port_result.message, port_result.field))

        # Validate max_parallel_tests (if provided)
        if "max_parallel_tests" in config:
            parallel_result = cls.validate_parallel_tests(config["max_parallel_tests"])
            if not parallel_result.is_valid:
                errors.append(ValidationError(parallel_result.message, parallel_result.field))

        # Validate max_retries (if provided)
        if "max_retries" in config:
            retries_result = cls.validate_retries(config["max_retries"])
            if not retries_result.is_valid:
                errors.append(ValidationError(retries_result.message, retries_result.field))

        # Validate timeout (if provided)
        if "timeout" in config:
            timeout_result = cls.validate_timeout(config["timeout"])
            if not timeout_result.is_valid:
                errors.append(ValidationError(timeout_result.message, timeout_result.field))

        # Validate diff_threshold (if provided)
        if "diff_threshold" in config:
            diff_result = cls.validate_diff_threshold(config["diff_threshold"])
            if not diff_result.is_valid:
                errors.append(ValidationError(diff_result.message, diff_result.field))

        # Validate boolean fields
        boolean_fields = ["headless", "parallel_execution", "retry_flaky_tests",
                         "track_execution_times", "detect_regressions"]
        for field in boolean_fields:
            if field in config:
                bool_result = cls.validate_boolean(config[field], field)
                if not bool_result.is_valid:
                    errors.append(ValidationError(bool_result.message, bool_result.field))

        # Validate URL fields
        url_fields = ["kanban_api_url", "webhook_url", "api_url"]
        for field in url_fields:
            if field in config:
                url_result = cls.validate_url(config[field], field)
                if not url_result.is_valid:
                    errors.append(ValidationError(url_result.message, url_result.field))

        return len(errors) == 0, errors

    @classmethod
    def get_defaults(cls) -> Dict[str, Any]:
        """
        Get default configuration values

        Returns the default configuration dictionary with all recommended settings.
        Used by the reset button to restore form to initial state.

        Returns:
            Dictionary containing default configuration values

        Example:
            >>> defaults = ConfigValidator.get_defaults()
            >>> print(defaults['port'])
            8000
        """
        return {
            "port": 8000,
            "timeout": 30,
            "max_parallel_tests": 3,
            "max_retries": 2,
            "diff_threshold": 0.1,
            "kanban_api_url": None,
            "headless": True,
            "parallel_execution": True
        }
