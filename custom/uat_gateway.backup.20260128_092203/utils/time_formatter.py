"""
Time Formatter Utility

Feature #291: Relative time display (2 hours ago)

Provides utilities for formatting timestamps in both relative and absolute formats.
- Relative time: "2 hours ago", "just now", "yesterday at 3:45 PM"
- Absolute time: "January 26, 2025 at 2:30 PM"
"""

from datetime import datetime, timezone
from typing import Tuple


def format_relative_time(timestamp: datetime, now: datetime = None) -> str:
    """
    Format a timestamp as relative time (e.g., "2 hours ago", "just now")

    Args:
        timestamp: The timestamp to format
        now: Current time (defaults to datetime.now())

    Returns:
        Relative time string like "2 hours ago", "5 minutes ago", "just now"
    """
    if now is None:
        now = datetime.now(timestamp.tzinfo) if timestamp.tzinfo else datetime.now()

    # Ensure both are timezone-aware or both are naive
    if timestamp.tzinfo and not now.tzinfo:
        now = now.replace(tzinfo=timestamp.tzinfo)
    elif now.tzinfo and not timestamp.tzinfo:
        timestamp = timestamp.replace(tzinfo=now.tzinfo)

    delta = now - timestamp
    seconds = int(delta.total_seconds())

    # Less than a minute
    if seconds < 60:
        if seconds < 10:
            return "just now"
        return f"{seconds} seconds ago"

    # Less than an hour
    minutes = seconds // 60
    if minutes < 60:
        if minutes == 1:
            return "1 minute ago"
        return f"{minutes} minutes ago"

    # Less than a day
    hours = minutes // 60
    if hours < 24:
        if hours == 1:
            return "1 hour ago"
        return f"{hours} hours ago"

    # Less than a week
    days = hours // 24
    if days < 7:
        if days == 1:
            # Return "yesterday at HH:MM AM/PM"
            return timestamp.strftime("yesterday at %I:%M %p").lstrip("0")
        return f"{days} days ago"

    # Less than a month
    weeks = days // 7
    if weeks < 4:
        if weeks == 1:
            return "1 week ago"
        return f"{weeks} weeks ago"

    # More than a month - show date
    months = days // 30
    if months < 12:
        if months == 1:
            return "1 month ago"
        return f"{months} months ago"

    # More than a year
    years = days // 365
    if years == 1:
        return "1 year ago"
    return f"{years} years ago"


def format_absolute_time(timestamp: datetime) -> str:
    """
    Format a timestamp as absolute time (e.g., "January 26, 2025 at 2:30 PM")

    Args:
        timestamp: The timestamp to format

    Returns:
        Absolute time string like "January 26, 2025 at 2:30 PM"
    """
    # Format: "January 26, 2025 at 2:30 PM"
    return timestamp.strftime("%B %d, %Y at %I:%M %p").lstrip("0").replace(" 0", " ")


def format_time_with_tooltip(timestamp: datetime, now: datetime = None) -> Tuple[str, str]:
    """
    Format a timestamp for display with both relative and absolute time

    Args:
        timestamp: The timestamp to format
        now: Current time (defaults to datetime.now())

    Returns:
        Tuple of (relative_time, absolute_time) for tooltip
    """
    relative = format_relative_time(timestamp, now)
    absolute = format_absolute_time(timestamp)
    return (relative, absolute)


def format_iso8601(timestamp: datetime) -> str:
    """
    Format a timestamp as ISO 8601 string for datetime attribute

    Args:
        timestamp: The timestamp to format

    Returns:
        ISO 8601 formatted string like "2025-01-26T14:30:00"
    """
    if timestamp.tzinfo:
        return timestamp.strftime("%Y-%m-%dT%H:%M:%S%z")
    else:
        return timestamp.strftime("%Y-%m-%dT%H:%M:%S")


# JavaScript code for dynamic time updates
RELATIVE_TIME_JS = """
// Update relative times dynamically
function updateRelativeTimes() {
    const timeElements = document.querySelectorAll('[data-timestamp]');
    const now = new Date();

    timeElements.forEach(element => {
        const timestamp = new Date(element.getAttribute('data-timestamp'));
        const relativeTime = formatRelativeTime(timestamp, now);
        element.textContent = relativeTime;
    });
}

// Format relative time in JavaScript (mirrors Python logic)
function formatRelativeTime(timestamp, now) {
    const delta = now - timestamp;
    const seconds = Math.floor(delta / 1000);

    if (seconds < 60) {
        if (seconds < 10) return 'just now';
        return seconds + ' seconds ago';
    }

    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) {
        if (minutes === 1) return '1 minute ago';
        return minutes + ' minutes ago';
    }

    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
        if (hours === 1) return '1 hour ago';
        return hours + ' hours ago';
    }

    const days = Math.floor(hours / 24);
    if (days < 7) {
        if (days === 1) {
            return 'yesterday at ' + timestamp.toLocaleTimeString('en-US',
                { hour: 'numeric', minute: '2-digit', hour12: true });
        }
        return days + ' days ago';
    }

    const weeks = Math.floor(days / 7);
    if (weeks < 4) {
        if (weeks === 1) return '1 week ago';
        return weeks + ' weeks ago';
    }

    const months = Math.floor(days / 30);
    if (months < 12) {
        if (months === 1) return '1 month ago';
        return months + ' months ago';
    }

    const years = Math.floor(days / 365);
    if (years === 1) return '1 year ago';
    return years + ' years ago';
}

// Update times every minute
setInterval(updateRelativeTimes, 60000);

// Initial update
updateRelativeTimes();
"""
