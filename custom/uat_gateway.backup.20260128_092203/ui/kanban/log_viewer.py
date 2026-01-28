"""
Log Viewer Component for Kanban Results Modal

This module provides a log viewer component that displays console logs
with syntax highlighting, timestamps, and error highlighting.

Used in Feature #157: Results modal shows log viewer with syntax highlighting
"""

import re
import html
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

from custom.uat_gateway.test_executor.test_executor import ConsoleMessage


@dataclass
class LogEntry:
    """Enhanced log entry with formatted display data"""
    level: str
    text: str
    timestamp: float
    datetime_str: str
    url: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None

    # Formatted HTML fields
    formatted_text: str = ""
    formatted_timestamp: str = ""
    level_class: str = ""
    level_emoji: str = ""

    def __post_init__(self):
        """Format log entry for display"""
        # Format timestamp
        dt = datetime.fromtimestamp(self.timestamp)
        self.formatted_timestamp = dt.strftime("%H:%M:%S.%f")[:-3]  # Milliseconds
        self.datetime_str = dt.isoformat()

        # Format text with syntax highlighting
        self.formatted_text = self._format_text()

        # Set level class and emoji
        self.level_class, self.level_emoji = self._get_level_style()

    def _format_text(self) -> str:
        """
        Format log text with syntax highlighting

        Applies HTML escaping and syntax highlighting for:
        - URLs
        - Objects/JSON
        - Numbers
        - Booleans
        - Strings
        """
        text = html.escape(self.text)

        # Highlight error/warning keywords (before other formatting)
        if self.level in ('error', 'warning'):
            # Highlight common error keywords (word boundary before, colon after)
            text = re.sub(
                r'\b(Error:|Warning:|Failed:|Exception:|TypeError:|ReferenceError:|SyntaxError:)',
                r'<span class="log-keyword">\1</span>',
                text
            )

        # Highlight URLs FIRST (before numbers, so we can skip numbers inside URLs)
        text = re.sub(
            r'(https?://[^\s<>"]+)',
            r'<span class="log-url">\1</span>',
            text
        )

        # Highlight numbers, but NOT inside URL spans
        # This regex matches numbers that are NOT inside <span class="log-url">...</span>
        def replace_numbers_outside_urls(match):
            """Replace numbers but skip if inside a URL span"""
            number = match.group(0)
            # Check if we're inside a URL span by looking backwards
            pre_context = text[:match.start()]
            # Count opening and closing URL spans before this position
            open_spans = pre_context.count('<span class="log-url">')
            close_spans = pre_context.count('</span>')
            # If more opens than closes, we're inside a URL span
            if open_spans > close_spans:
                return number  # Don't highlight
            return f'<span class="log-number">{number}</span>'

        # Find all numbers and process them
        text = re.sub(r'(?<!\w)(\d+\.?\d*)(?!\w)', replace_numbers_outside_urls, text)

        # Highlight booleans
        text = re.sub(
            r'\b(true|false|null|undefined)\b',
            r'<span class="log-boolean">\1</span>',
            text,
            flags=re.IGNORECASE
        )

        return text

    def _get_level_style(self) -> tuple[str, str]:
        """Get CSS class and emoji for log level"""
        level_styles = {
            'error': ('log-error', '❌'),
            'warning': ('log-warning', '⚠️'),
            'info': ('log-info', 'ℹ️'),
            'log': ('log-log', '📝'),
            'debug': ('log-debug', '🔍'),
        }
        return level_styles.get(self.level.lower(), ('log-log', '📝'))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "level": self.level,
            "text": self.text,
            "formatted_text": self.formatted_text,
            "timestamp": self.timestamp,
            "datetime": self.datetime_str,
            "formatted_timestamp": self.formatted_timestamp,
            "url": self.url,
            "line": self.line,
            "column": self.column,
            "level_class": self.level_class,
            "level_emoji": self.level_emoji
        }


class LogViewer:
    """
    Log Viewer Component for displaying console logs with syntax highlighting

    Features:
    - Syntax highlighting for URLs, numbers, booleans, and keywords
    - Timestamp display with milliseconds
    - Error log highlighting with visual indicators
    - Source location (URL, line, column)
    - Filtering by log level
    - HTML output for modal display
    """

    def __init__(self, console_logs: List[ConsoleMessage]):
        """
        Initialize log viewer with console messages

        Args:
            console_logs: List of ConsoleMessage objects from test execution
        """
        self.console_logs = console_logs
        self.entries: List[LogEntry] = []
        self._process_logs()

    def _process_logs(self):
        """Convert ConsoleMessage objects to LogEntry objects"""
        self.entries = [
            LogEntry(
                level=log.level,
                text=log.text,
                timestamp=log.timestamp,
                datetime_str="",  # Will be set in __post_init__
                url=log.url,
                line=log.line,
                column=log.column
            )
            for log in self.console_logs
        ]

    def get_entries(self, level_filter: Optional[str] = None) -> List[LogEntry]:
        """
        Get log entries, optionally filtered by level

        Args:
            level_filter: Optional log level filter ('error', 'warning', etc.)

        Returns:
            List of LogEntry objects
        """
        if level_filter:
            return [e for e in self.entries if e.level.lower() == level_filter.lower()]
        return self.entries

    def get_error_logs(self) -> List[LogEntry]:
        """Get only error-level logs"""
        return self.get_entries('error')

    def get_warning_logs(self) -> List[LogEntry]:
        """Get only warning-level logs"""
        return self.get_entries('warning')

    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about log levels

        Returns:
            Dictionary with counts per level
        """
        stats = {
            'error': 0,
            'warning': 0,
            'info': 0,
            'log': 0,
            'debug': 0,
        }
        for entry in self.entries:
            level = entry.level.lower()
            if level in stats:
                stats[level] += 1
        return stats

    def to_html(self, level_filter: Optional[str] = None) -> str:
        """
        Generate HTML representation of log viewer

        Args:
            level_filter: Optional log level filter

        Returns:
            HTML string with formatted log entries
        """
        entries = self.get_entries(level_filter)

        if not entries:
            return self._empty_state_html()

        html_parts = ['<div class="log-viewer">']

        # Header with stats
        html_parts.append('<div class="log-viewer__header">')
        html_parts.append('<h4 class="log-viewer__title">📋 Console Logs</h4>')
        stats = self.get_stats()
        html_parts.append('<div class="log-viewer__stats">')
        html_parts.append(f'<span class="log-stat log-stat--error">❌ {stats["error"]}</span>')
        html_parts.append(f'<span class="log-stat log-stat--warning">⚠️ {stats["warning"]}</span>')
        html_parts.append(f'<span class="log-stat log-stat--info">ℹ️ {stats["info"]}</span>')
        html_parts.append(f'<span class="log-stat log-stat--log">📝 {stats["log"]}</span>')
        html_parts.append('</div>')
        html_parts.append('</div>')

        # Log entries
        html_parts.append('<div class="log-viewer__entries">')
        for entry in entries:
            html_parts.append(self._entry_to_html(entry))
        html_parts.append('</div>')

        html_parts.append('</div>')
        return '\n'.join(html_parts)

    def _entry_to_html(self, entry: LogEntry) -> str:
        """Convert a single log entry to HTML"""
        source_info = ""
        if entry.url or entry.line:
            parts = []
            if entry.url:
                # Shorten URL for display
                short_url = entry.url.split('/')[-1][:40]
                parts.append(f'<span class="log-source-url">{short_url}</span>')
            if entry.line:
                parts.append(f'<span class="log-source-line">:{entry.line}</span>')
            if entry.column:
                parts.append(f'<span class="log-source-col">:{entry.column}</span>')
            source_info = f'<div class="log-entry__source">{"".join(parts)}</div>'

        return f'''
        <div class="log-entry {entry.level_class}">
            <div class="log-entry__header">
                <span class="log-entry__emoji">{entry.level_emoji}</span>
                <span class="log-entry__timestamp">{entry.formatted_timestamp}</span>
                <span class="log-entry__level">{entry.level.upper()}</span>
            </div>
            <div class="log-entry__message">{entry.formatted_text}</div>
            {source_info}
        </div>
        '''

    def _empty_state_html(self) -> str:
        """Generate HTML for empty log state"""
        return '''
        <div class="log-viewer log-viewer--empty">
            <div class="log-viewer__empty">
                <span class="log-viewer__empty-emoji">📭</span>
                <p class="log-viewer__empty-text">No console logs available</p>
            </div>
        </div>
        '''

    def to_markdown(self, level_filter: Optional[str] = None) -> str:
        """
        Generate markdown representation of log viewer

        Useful for embedding in Kanban card comments

        Args:
            level_filter: Optional log level filter

        Returns:
            Markdown string with formatted log entries
        """
        entries = self.get_entries(level_filter)

        if not entries:
            return "## 📋 Console Logs\n\nNo console logs available."

        lines = ["## 📋 Console Logs\n"]

        # Add summary
        stats = self.get_stats()
        lines.append(f"**Summary:** ❌ {stats['error']} | ⚠️ {stats['warning']} | ℹ️ {stats['info']} | 📝 {stats['log']}\n")

        # Add entries
        for entry in entries:
            lines.append(f"### {entry.level_emoji} {entry.level.upper()} at {entry.formatted_timestamp}")

            if entry.url:
                lines.append(f"**Source:** {entry.url}:{entry.line or '?'}:{entry.column or '?'}")

            lines.append(f"**Message:**\n```\n{entry.text}\n```\n")

        return '\n'.join(lines)

    def get_css_styles(self) -> str:
        """
        Get CSS styles for log viewer

        Returns:
            CSS string for styling the log viewer HTML
        """
        return """
        .log-viewer {
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 13px;
            line-height: 1.5;
            background: #1e1e1e;
            border-radius: 8px;
            overflow: hidden;
        }

        .log-viewer__header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            background: #2d2d2d;
            border-bottom: 1px solid #3e3e3e;
        }

        .log-viewer__title {
            margin: 0;
            font-size: 14px;
            color: #e0e0e0;
        }

        .log-viewer__stats {
            display: flex;
            gap: 12px;
        }

        .log-stat {
            font-size: 12px;
            padding: 2px 8px;
            border-radius: 4px;
            background: #3e3e3e;
        }

        .log-stat--error { color: #ff6b6b; }
        .log-stat--warning { color: #ffa502; }
        .log-stat--info { color: #74b9ff; }
        .log-stat--log { color: #a4b0be; }

        .log-viewer__entries {
            max-height: 500px;
            overflow-y: auto;
            padding: 8px;
        }

        .log-entry {
            padding: 8px 12px;
            margin-bottom: 4px;
            border-radius: 4px;
            border-left: 3px solid transparent;
        }

        .log-entry:hover {
            background: #2d2d2d;
        }

        .log-error {
            border-left-color: #ff6b6b;
            background: rgba(255, 107, 107, 0.05);
        }

        .log-warning {
            border-left-color: #ffa502;
            background: rgba(255, 165, 2, 0.05);
        }

        .log-info {
            border-left-color: #74b9ff;
        }

        .log-debug {
            border-left-color: #a4b0be;
        }

        .log-entry__header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }

        .log-entry__emoji {
            font-size: 12px;
        }

        .log-entry__timestamp {
            color: #7f8c8d;
            font-size: 11px;
        }

        .log-entry__level {
            font-size: 10px;
            font-weight: bold;
            padding: 2px 6px;
            border-radius: 3px;
            text-transform: uppercase;
        }

        .log-error .log-entry__level { background: #ff6b6b; color: #1e1e1e; }
        .log-warning .log-entry__level { background: #ffa502; color: #1e1e1e; }
        .log-info .log-entry__level { background: #74b9ff; color: #1e1e1e; }
        .log-debug .log-entry__level { background: #a4b0be; color: #1e1e1e; }

        .log-entry__message {
            color: #e0e0e0;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .log-entry__source {
            margin-top: 4px;
            font-size: 11px;
            color: #7f8c8d;
        }

        .log-source-url {
            color: #74b9ff;
        }

        .log-source-line,
        .log-source-col {
            color: #a4b0be;
        }

        /* Syntax highlighting */
        .log-url {
            color: #74b9ff;
            text-decoration: underline;
        }

        .log-number {
            color: #f39c12;
        }

        .log-boolean {
            color: #9b59b6;
        }

        .log-keyword {
            color: #e74c3c;
            font-weight: bold;
        }

        /* Empty state */
        .log-viewer--empty {
            padding: 40px;
            text-align: center;
        }

        .log-viewer__empty-emoji {
            font-size: 48px;
            display: block;
            margin-bottom: 12px;
        }

        .log-viewer__empty-text {
            color: #7f8c8d;
            margin: 0;
        }

        /* Scrollbar styling */
        .log-viewer__entries::-webkit-scrollbar {
            width: 8px;
        }

        .log-viewer__entries::-webkit-scrollbar-track {
            background: #1e1e1e;
        }

        .log-viewer__entries::-webkit-scrollbar-thumb {
            background: #3e3e3e;
            border-radius: 4px;
        }

        .log-viewer__entries::-webkit-scrollbar-thumb:hover {
            background: #4e4e4e;
        }
        """
