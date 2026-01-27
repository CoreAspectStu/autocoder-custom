"""
Date Range Validation Utility

Provides validation for date ranges to ensure logical ordering.
Used in Feature #403: Date range validation.
"""

from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class DateRangeValidationResult:
    """Result of date range validation"""
    is_valid: bool
    error_message: Optional[str] = None
    swapped_range: Optional[Tuple[datetime, datetime]] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "is_valid": self.is_valid,
            "error_message": self.error_message,
            "swapped_start": self.swapped_range[0].isoformat() if self.swapped_range else None,
            "swapped_end": self.swapped_range[1].isoformat() if self.swapped_range else None,
        }


class DateRangeValidator:
    """
    Validator for date ranges

    Ensures that date ranges are logical (start date <= end date)
    and provides helpful error messages when validation fails.
    """

    @staticmethod
    def validate_date_range(
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        allow_swap: bool = False
    ) -> DateRangeValidationResult:
        """
        Validate a date range

        Args:
            start_date: Start of date range (or None for no start limit)
            end_date: End of date range (or None for no end limit)
            allow_swap: If True, auto-swap invalid ranges instead of error

        Returns:
            DateRangeValidationResult with validation status and error message
        """
        # Case 1: Both dates are None (valid - no filter)
        if start_date is None and end_date is None:
            return DateRangeValidationResult(
                is_valid=True,
                error_message=None
            )

        # Case 2: Only start date (valid - no end limit)
        if start_date is not None and end_date is None:
            return DateRangeValidationResult(
                is_valid=True,
                error_message=None
            )

        # Case 3: Only end date (valid - no start limit)
        if start_date is None and end_date is not None:
            return DateRangeValidationResult(
                is_valid=True,
                error_message=None
            )

        # Case 4: Both dates provided - check ordering
        if start_date > end_date:
            if allow_swap:
                # Auto-swap and return success with swapped dates
                return DateRangeValidationResult(
                    is_valid=True,
                    error_message=None,
                    swapped_range=(end_date, start_date)
                )
            else:
                # Return validation error
                return DateRangeValidationResult(
                    is_valid=False,
                    error_message=(
                        f"End date ({end_date.strftime('%Y-%m-%d')}) must be after "
                        f"start date ({start_date.strftime('%Y-%m-%d')})"
                    )
                )

        # Case 5: Valid range (start <= end)
        return DateRangeValidationResult(
            is_valid=True,
            error_message=None
        )

    @staticmethod
    def validate_date_range_strict(
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> Tuple[bool, Optional[str]]:
        """
        Strict validation - raises no automatic swaps

        Args:
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Tuple of (is_valid, error_message)
        """
        result = DateRangeValidator.validate_date_range(
            start_date,
            end_date,
            allow_swap=False
        )
        return (result.is_valid, result.error_message)


def validate_date_range(
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    allow_swap: bool = False
) -> DateRangeValidationResult:
    """
    Convenience function to validate a date range

    Args:
        start_date: Start of date range
        end_date: End of date range
        allow_swap: If True, auto-swap invalid ranges

    Returns:
        DateRangeValidationResult
    """
    return DateRangeValidator.validate_date_range(
        start_date,
        end_date,
        allow_swap
    )


def validate_date_range_strict(
    start_date: Optional[datetime],
    end_date: Optional[datetime]
) -> Tuple[bool, Optional[str]]:
    """
    Convenience function for strict validation

    Args:
        start_date: Start of date range
        end_date: End of date range

    Returns:
        Tuple of (is_valid, error_message)
    """
    return DateRangeValidator.validate_date_range_strict(
        start_date,
        end_date
    )
