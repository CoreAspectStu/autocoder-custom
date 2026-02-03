"""
Password Validation Module

Implements secure password requirements and validation.
"""

import re
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class PasswordPolicy:
    """Password security policy configuration"""
    min_length: int = 8
    max_length: int = 128
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = True
    special_chars: str = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    forbidden_patterns: List[str] = None
    forbidden_common_passwords: List[str] = None

    def __post_init__(self):
        """Initialize default values for lists"""
        if self.forbidden_patterns is None:
            # Common patterns that should be avoided
            self.forbidden_patterns = [
                r"123456",          # Sequential numbers
                r"abcde",           # Sequential letters
                r"qwerty",          # Keyboard patterns
                r"password",        # Word "password"
                r"admin",           # Word "admin"
                r"(.)\1{4,}",       # Same character repeated 5+ times (e.g., "aaaaa")
            ]

        if self.forbidden_common_passwords is None:
            # Top most common weak passwords
            self.forbidden_common_passwords = [
                "password", "Password1", "password123",
                "12345678", "123456789", "qwerty123",
                "abc123", "letmein", "welcome1",
                "admin123", "root123", "test123",
                "passw0rd", "P@ssw0rd", "Password123!"
            ]


@dataclass
class ValidationResult:
    """Result of password validation"""
    is_valid: bool
    errors: List[str]
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class PasswordValidator:
    """
    Validates passwords against security policy

    Enforces strong password requirements to protect user accounts.
    """

    def __init__(self, policy: PasswordPolicy = None):
        """
        Initialize password validator

        Args:
            policy: Password policy (uses defaults if not provided)
        """
        self.policy = policy or PasswordPolicy()

    def validate(self, password: str, username: str = None) -> ValidationResult:
        """
        Validate a password against the security policy

        Args:
            password: Password to validate
            username: Username to check against (optional, for similarity check)

        Returns:
            ValidationResult with validation status and error messages
        """
        errors = []
        warnings = []

        # Check length
        if len(password) < self.policy.min_length:
            errors.append(
                f"Password must be at least {self.policy.min_length} characters long"
            )

        if len(password) > self.policy.max_length:
            errors.append(
                f"Password must not exceed {self.policy.max_length} characters"
            )

        # Check character requirements
        if self.policy.require_uppercase and not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")

        if self.policy.require_lowercase and not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")

        if self.policy.require_digit and not re.search(r"\d", password):
            errors.append("Password must contain at least one digit")

        if self.policy.require_special:
            if not re.search(f"[{re.escape(self.policy.special_chars)}]", password):
                errors.append(
                    f"Password must contain at least one special character: {self.policy.special_chars}"
                )

        # Check for forbidden patterns
        for pattern in self.policy.forbidden_patterns:
            if re.search(pattern, password, re.IGNORECASE):
                errors.append("Password contains a forbidden pattern")

        # Check against common passwords
        if password.lower() in [p.lower() for p in self.policy.forbidden_common_passwords]:
            errors.append("Password is too common and easily guessable")

        # Check if password contains username (weak practice)
        if username and username.lower() in password.lower():
            errors.append("Password must not contain your username")

        # Warnings (optional improvements)
        if len(password) < 12:
            warnings.append("Consider using a longer password (12+ characters) for better security")

        if not re.search(r".*[A-Z].*[a-z].*", password) or not re.search(r".*[a-z].*[A-Z].*", password):
            # Check if uppercase and lowercase are mixed (not just at start/end)
            if re.search(r"[A-Z]", password) and re.search(r"[a-z]", password):
                # Only warn if both exist but might be poorly placed
                if password[0].isupper() and password[-1:].isdigit():
                    warnings.append("Consider mixing uppercase and lowercase throughout the password")

        is_valid = len(errors) == 0
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

    def get_password_strength(self, password: str) -> str:
        """
        Get password strength indicator

        Args:
            password: Password to check

        Returns:
            Strength level: "weak", "fair", "good", or "strong"
        """
        result = self.validate(password)

        if not result.is_valid:
            return "weak"

        score = 0

        # Length scoring
        if len(password) >= 8:
            score += 1
        if len(password) >= 12:
            score += 1
        if len(password) >= 16:
            score += 1

        # Character variety
        if re.search(r"[A-Z]", password):
            score += 1
        if re.search(r"[a-z]", password):
            score += 1
        if re.search(r"\d", password):
            score += 1
        if re.search(f"[{re.escape(self.policy.special_chars)}]", password):
            score += 1

        # Determine strength
        if score <= 3:
            return "fair"
        elif score <= 5:
            return "good"
        else:
            return "strong"

    def get_requirements_text(self) -> List[str]:
        """
        Get human-readable password requirements

        Returns:
            List of requirement descriptions
        """
        requirements = []

        requirements.append(f"At least {self.policy.min_length} characters long")

        if self.policy.require_uppercase:
            requirements.append("At least one uppercase letter")

        if self.policy.require_lowercase:
            requirements.append("At least one lowercase letter")

        if self.policy.require_digit:
            requirements.append("At least one digit")

        if self.policy.require_special:
            requirements.append(
                f"At least one special character ({self.policy.special_chars})"
            )

        return requirements


# Create default validator instance
default_validator = PasswordValidator()


def validate_password(password: str, username: str = None) -> ValidationResult:
    """
    Validate password using default policy

    Convenience function that uses the default validator.

    Args:
        password: Password to validate
        username: Username to check against (optional)

    Returns:
        ValidationResult with validation status
    """
    return default_validator.validate(password, username)


def get_password_requirements() -> List[str]:
    """
    Get password requirements using default policy

    Returns:
        List of requirement descriptions
    """
    return default_validator.get_requirements_text()
