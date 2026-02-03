"""
Timezone Utilities for UAT Gateway

Provides timezone conversion and formatting utilities for cross-timezone
timestamp display and management.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List
from dataclasses import dataclass
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


# Common timezones for user selection
COMMON_TIMEZONES = [
    # UTC
    "UTC",

    # North America
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "America/Toronto",
    "America/Vancouver",

    # Europe
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Rome",
    "Europe/Madrid",
    "Europe/Amsterdam",
    "Europe/Zurich",

    # Asia
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Hong_Kong",
    "Asia/Singapore",
    "Asia/Seoul",
    "Asia/Mumbai",
    "Asia/Dubai",

    # Australia
    "Australia/Sydney",
    "Australia/Melbourne",
    "Australia/Brisbane",
    "Australia/Perth",

    # Pacific
    "Pacific/Auckland",
]


@dataclass
class TimezoneInfo:
    """Information about a timezone"""
    name: str
    offset_hours: int
    offset_minutes: int
    display_name: str
    current_time: str

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "offset_hours": self.offset_hours,
            "offset_minutes": self.offset_minutes,
            "display_name": self.display_name,
            "current_time": self.current_time
        }


class TimezoneConverter:
    """
    Handles timezone conversion and formatting for timestamps
    """

    def __init__(self, default_timezone: str = "UTC"):
        """
        Initialize the timezone converter

        Args:
            default_timezone: Default timezone to use if none specified
        """
        self.default_timezone = default_timezone
        try:
            self._default_tz = ZoneInfo(default_timezone)
        except Exception:
            logger.warning(f"Unknown timezone {default_timezone}, falling back to UTC")
            self._default_tz = ZoneInfo("UTC")
            self.default_timezone = "UTC"

    def convert_to_timezone(
        self,
        dt: datetime,
        target_timezone: Optional[str] = None
    ) -> datetime:
        """
        Convert a datetime to a target timezone

        Args:
            dt: Datetime to convert (should be timezone-aware)
            target_timezone: Target timezone name (uses default if None)

        Returns:
            Datetime in target timezone
        """
        tz = self._get_timezone(target_timezone)

        # If datetime is naive, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
            logger.debug("Naive datetime treated as UTC")

        # Convert to target timezone
        return dt.astimezone(tz)

    def format_datetime(
        self,
        dt: datetime,
        target_timezone: Optional[str] = None,
        format_type: str = "full"
    ) -> str:
        """
        Format a datetime in a user-friendly way

        Args:
            dt: Datetime to format
            target_timezone: Target timezone name
            format_type: Type of format ("full", "short", "time", "date", "relative")

        Returns:
            Formatted datetime string
        """
        local_dt = self.convert_to_timezone(dt, target_timezone)

        if format_type == "full":
            # Full datetime: "2025-01-26 14:30:45 EST"
            tz_name = local_dt.tzinfo.tzname(local_dt) or "UTC"
            return local_dt.strftime("%Y-%m-%d %H:%M:%S") + f" {tz_name}"

        elif format_type == "short":
            # Short datetime: "Jan 26, 2:30 PM EST"
            tz_name = local_dt.tzinfo.tzname(local_dt) or "UTC"
            return local_dt.strftime("%b %d, %I:%M %p") + f" {tz_name}"

        elif format_type == "time":
            # Time only: "2:30 PM EST"
            tz_name = local_dt.tzinfo.tzname(local_dt) or "UTC"
            return local_dt.strftime("%I:%M %p") + f" {tz_name}"

        elif format_type == "date":
            # Date only: "Jan 26, 2025"
            return local_dt.strftime("%b %d, %Y")

        elif format_type == "relative":
            # Relative time: "2 hours ago"
            return self._format_relative_time(dt)

        else:
            return local_dt.isoformat()

    def format_relative_time(self, dt: datetime) -> str:
        """
        Format a datetime as relative time (e.g., "2 hours ago")

        Args:
            dt: Datetime to format

        Returns:
            Relative time string
        """
        return self._format_relative_time(dt)

    def _format_relative_time(self, dt: datetime) -> str:
        """Internal method to format relative time"""
        now = datetime.now(timezone.utc)

        # Ensure dt is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        delta = now - dt
        seconds = delta.total_seconds()

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days > 1 else ''} ago"
        elif seconds < 2592000:
            weeks = int(seconds / 604800)
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        elif seconds < 31536000:
            months = int(seconds / 2592000)
            return f"{months} month{'s' if months > 1 else ''} ago"
        else:
            years = int(seconds / 31536000)
            return f"{years} year{'s' if years > 1 else ''} ago"

    def get_timezone_info(self, tz_name: Optional[str] = None) -> TimezoneInfo:
        """
        Get information about a timezone

        Args:
            tz_name: Timezone name (uses default if None)

        Returns:
            TimezoneInfo object
        """
        tz = self._get_timezone(tz_name)
        now = datetime.now(timezone.utc).astimezone(tz)

        # Calculate UTC offset
        utc_offset = now.utcoffset()
        if utc_offset is None:
            offset_hours = 0
            offset_minutes = 0
        else:
            total_seconds = int(utc_offset.total_seconds())
            offset_hours = total_seconds // 3600
            offset_minutes = (total_seconds % 3600) // 60

        # Create display name
        tz_name_display = tz_name or self.default_timezone
        offset_str = f"{'+' if offset_hours >= 0 else ''}{offset_hours:02d}:{offset_minutes:02d}"
        display_name = f"{tz_name_display} (UTC{offset_str})"

        return TimezoneInfo(
            name=tz_name_display,
            offset_hours=offset_hours,
            offset_minutes=offset_minutes,
            display_name=display_name,
            current_time=now.strftime("%Y-%m-%d %H:%M:%S")
        )

    def list_available_timezones(self) -> List[str]:
        """
        List all available timezone names

        Returns:
            List of timezone names
        """
        return COMMON_TIMEZONES

    def list_all_timezone_info(self) -> List[TimezoneInfo]:
        """
        Get information about all common timezones

        Returns:
            List of TimezoneInfo objects
        """
        return [self.get_timezone_info(tz) for tz in COMMON_TIMEZONES]

    def validate_timezone(self, tz_name: str) -> bool:
        """
        Validate if a timezone name is valid

        Args:
            tz_name: Timezone name to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            ZoneInfo(tz_name)
            return True
        except Exception:
            return False

    def _get_timezone(self, tz_name: Optional[str] = None):
        """Get ZoneInfo timezone object"""
        if tz_name is None:
            return self._default_tz

        try:
            return ZoneInfo(tz_name)
        except Exception:
            logger.warning(f"Unknown timezone {tz_name}, using default")
            return self._default_tz

    def parse_iso_datetime(self, iso_string: str) -> datetime:
        """
        Parse an ISO format datetime string

        Args:
            iso_string: ISO format datetime string

        Returns:
            datetime object (timezone-aware if string contains timezone)
        """
        try:
            dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
            return dt
        except ValueError as e:
            logger.error(f"Failed to parse datetime: {iso_string} - {e}")
            # Return current time as fallback
            return datetime.now(timezone.utc)


# Singleton instance
_converter: Optional[TimezoneConverter] = None


def get_timezone_converter(default_timezone: str = "UTC") -> TimezoneConverter:
    """
    Get the global timezone converter instance

    Args:
        default_timezone: Default timezone (only used on first call)

    Returns:
        TimezoneConverter instance
    """
    global _converter
    if _converter is None:
        _converter = TimezoneConverter(default_timezone=default_timezone)
    return _converter


def format_timestamp_for_user(
    iso_timestamp: str,
    user_timezone: str,
    format_type: str = "short"
) -> str:
    """
    Convenience function to format a timestamp for a specific user

    Args:
        iso_timestamp: ISO format timestamp string
        user_timezone: User's timezone preference
        format_type: Type of format to use

    Returns:
        Formatted timestamp string
    """
    converter = get_timezone_converter()
    dt = converter.parse_iso_datetime(iso_timestamp)
    return converter.format_datetime(dt, user_timezone, format_type)
