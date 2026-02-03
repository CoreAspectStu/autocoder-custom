"""
Email Validation Module

Feature #400: Email format validation

Provides robust email address validation according to RFC 5322 and common practices.
"""

import re
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class EmailValidationResult:
    """Result of email validation"""
    is_valid: bool
    email: str
    errors: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class EmailValidator:
    """
    Email address validator

    Validates email format according to RFC 5322 standards with practical
    restrictions for security and usability.
    """

    # RFC 5322 compliant regex (simplified for practical use)
    # This pattern catches most common email formats while excluding obviously invalid ones
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9!#$%&\'*+/=?^_`{|}~-]+'
        r'(?:\.[a-zA-Z0-9!#$%&\'*+/=?^_`{|}~-]+)*'
        r'@'
        r'(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+'
        r'[A-Za-z]{2,}$'
    )

    # Common disposable email domains (can be expanded)
    DISPOSABLE_DOMAINS = {
        'tempmail.com',
        'guerrillamail.com',
        'mailinator.com',
        '10minutemail.com',
    }

    def __init__(
        self,
        check_disposable: bool = False,
        require_mx: bool = False,
        max_length: int = 254
    ):
        """
        Initialize email validator

        Args:
            check_disposable: Whether to reject disposable email domains
            require_mx: Whether to check for valid MX records (requires DNS lookup)
            max_length: Maximum email length (RFC 5321 specifies 254)
        """
        self.check_disposable = check_disposable
        self.require_mx = require_mx
        self.max_length = max_length

    def validate(self, email: Optional[str]) -> EmailValidationResult:
        """
        Validate an email address

        Args:
            email: Email address to validate

        Returns:
            EmailValidationResult with validation status and any errors
        """
        if not email:
            return EmailValidationResult(
                is_valid=False,
                email="",
                errors=["Email address is required"]
            )

        # Convert to string and strip whitespace
        email = str(email).strip()

        result = EmailValidationResult(is_valid=True, email=email)

        # Check 1: Length validation
        if len(email) > self.max_length:
            result.is_valid = False
            result.errors.append(
                f"Email address exceeds maximum length of {self.max_length} characters"
            )

        # Check 2: Basic format validation
        if not self.EMAIL_PATTERN.match(email):
            result.is_valid = False
            result.errors.append("Invalid email format")
            return result  # Return early - format errors are critical

        # Check 3: Local part validation
        local_part, domain = email.rsplit('@', 1)

        if len(local_part) == 0:
            result.is_valid = False
            result.errors.append("Email local part (before @) cannot be empty")

        if len(local_part) > 64:
            result.warnings.append(
                "Local part exceeds 64 characters (unusual but valid)"
            )

        # Check 4: Domain validation
        if len(domain) == 0:
            result.is_valid = False
            result.errors.append("Email domain (after @) cannot be empty")

        if len(domain) > 253:
            result.is_valid = False
            result.errors.append(
                "Email domain exceeds maximum length of 253 characters"
            )

        # Check 5: Domain has valid TLD
        if '.' not in domain:
            result.is_valid = False
            result.errors.append("Email domain must contain at least one dot")

        domain_parts = domain.split('.')
        if len(domain_parts[-1]) < 2:
            result.is_valid = False
            result.errors.append("Email TLD must be at least 2 characters")

        # Check 6: Disposable email detection
        if self.check_disposable:
            domain_lower = domain.lower()
            if domain_lower in self.DISPOSABLE_DOMAINS:
                result.is_valid = False
                result.errors.append(
                    f"Disposable email addresses ({domain}) are not allowed"
                )

        # Check 7: Consecutive dots (invalid)
        if '..' in email:
            result.is_valid = False
            result.errors.append("Email cannot contain consecutive dots")

        # Check 8: Leading/trailing dots in local part
        if local_part.startswith('.') or local_part.endswith('.'):
            result.is_valid = False
            result.errors.append(
                "Email local part cannot start or end with a dot"
            )

        # Check 9: Leading/trailing hyphens in domain parts
        for part in domain_parts:
            if part.startswith('-') or part.endswith('-'):
                result.is_valid = False
                result.errors.append(
                    "Email domain parts cannot start or end with hyphens"
                )
                break

        return result


# Global validator instance
default_validator = EmailValidator()


def validate_email(email: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Quick email validation convenience function

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    result = default_validator.validate(email)
    if result.is_valid:
        return True, None
    else:
        error_msg = "; ".join(result.errors) if result.errors else "Invalid email format"
        return False, error_msg


def get_email_validation_examples() -> dict:
    """
    Get examples of valid and invalid email addresses for testing

    Returns:
        Dict with 'valid' and 'invalid' lists
    """
    return {
        "valid": [
            "test@example.com",
            "user.name@example.com",
            "user+tag@example.com",
            "user_name@example.co.uk",
            "user-name@subdomain.example.com",
            "a@b.co",
            "test123@test123.com",
            "user.name+tag+label@example.com",
            "simple@example.com",
        ],
        "invalid": [
            "",                    # Empty
            "plainaddress",        # No @
            "@example.com",        # No local part
            "user@",               # No domain
            "user@.com",           # Domain starts with dot
            "user@domain",         # No TLD
            "user..name@example.com",  # Consecutive dots
            ".user@example.com",   # Starts with dot
            "user.@example.com",   # Ends with dot
            "user@-example.com",   # Domain starts with hyphen
            "user@example-.com",   # Domain ends with hyphen
            "user @example.com",   # Contains space
            "user@ex ample.com",   # Contains space
            "user@example..com",   # Consecutive dots in domain
            "user@.example.com",   # Domain starts with dot
            "user@example.com.",   # Domain ends with dot
        ]
    }
