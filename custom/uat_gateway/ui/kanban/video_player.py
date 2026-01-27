"""
Video Player Component for Kanban Results Modal

This module provides video playback functionality for test failure videos
in the Kanban results modal. It supports standard HTML5 video controls
with enhanced features for debugging test failures.

Feature #156: Results modal shows video playback
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


class VideoPlayerError(Exception):
    """Exception raised for video player errors"""
    pass


@dataclass
class VideoMetadata:
    """Metadata about a video file"""
    duration: float = 0.0  # Duration in seconds
    width: int = 0
    height: int = 0
    format: str = "webm"  # Video format (webm, mp4, etc.)
    size_bytes: int = 0
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class VideoPlayer:
    """
    Video player component for test failure videos

    Features:
    - HTML5 video playback with standard controls
    - Play/pause, seek, volume, fullscreen
    - Video metadata extraction
    - Error handling for missing videos
    - Responsive design for different screen sizes
    - Accessibility support
    - Download link for offline viewing

    Usage:
        # Create from test result
        result = TestResult(
            test_name="login_test",
            passed=False,
            video_path="/artifacts/videos/login-failure.webm"
        )
        player = VideoPlayer.from_test_result(result)

        # Render in modal
        html = player.to_html()

        # Control playback (programmatic)
        player.play()
        player.seek_to(5.0)
        player.pause()
    """

    def __init__(
        self,
        video_path: Optional[str] = None,
        test_name: Optional[str] = None,
        autoplay: bool = False,
        loop: bool = False,
        muted: bool = False
    ):
        """
        Initialize video player

        Args:
            video_path: Path to video file (relative or absolute)
            test_name: Name of the test for context/labeling
            autoplay: Whether to autoplay the video
            loop: Whether to loop the video
            muted: Whether to start muted
        """
        self.video_path = video_path
        self.test_name = test_name or "Test Video"
        self.autoplay = autoplay
        self._loop = loop
        self._muted = muted

        # Playback state (for programmatic control simulation)
        self._is_playing = False
        self._current_time = 0.0
        self._duration = 0.0
        self._volume = 1.0
        self._playback_rate = 1.0
        self._is_fullscreen = False

        # Video metadata
        self.metadata: Optional[VideoMetadata] = None

        # Load metadata if file exists
        if self.video_exists():
            self._load_metadata()

    @classmethod
    def from_test_result(cls, test_result: 'TestResult') -> 'VideoPlayer':
        """
        Create video player from test result

        Args:
            test_result: TestResult object with video_path

        Returns:
            VideoPlayer instance
        """
        return cls(
            video_path=test_result.video_path,
            test_name=test_result.test_name
        )

    def is_ready(self) -> bool:
        """
        Check if video player is ready (has video path)

        Returns:
            True if video path is set
        """
        return self.video_path is not None and len(self.video_path) > 0

    def video_exists(self) -> bool:
        """
        Check if video file exists on filesystem

        Returns:
            True if video file exists
        """
        if not self.video_path:
            return False

        # Handle both relative and absolute paths
        video_file = Path(self.video_path)
        if not video_file.is_absolute():
            # Assume relative to project root
            video_file = Path.cwd() / self.video_path

        return video_file.exists() and video_file.is_file()

    def _load_metadata(self):
        """Load video metadata from file"""
        if not self.video_path:
            return

        video_file = Path(self.video_path)
        if not video_file.is_absolute():
            video_file = Path.cwd() / self.video_path

        if video_file.exists():
            stat = video_file.stat()
            self.metadata = VideoMetadata(
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_ctime),
                format=video_file.suffix.lstrip('.')
            )
            # Default duration (in real implementation, would use ffprobe or similar)
            self.metadata.duration = self._duration

    def get_video_metadata(self) -> Optional[Dict[str, Any]]:
        """
        Get video metadata

        Returns:
            Dictionary with video metadata or None if not available
        """
        if self.metadata:
            return self.metadata.to_dict()
        return None

    # ========================================================================
    # Playback Control Methods (Simulated for testing)
    # ========================================================================

    def play(self):
        """Start video playback"""
        if self.is_ready():
            self._is_playing = True
        else:
            raise VideoPlayerError("Cannot play: video not ready")

    def pause(self):
        """Pause video playback"""
        self._is_playing = False

    def toggle_playback(self):
        """Toggle between play and pause"""
        if self._is_playing:
            self.pause()
        else:
            self.play()

    def stop(self):
        """Stop video playback and reset to beginning"""
        self._is_playing = False
        self._current_time = 0.0

    @property
    def is_playing(self) -> bool:
        """Check if video is currently playing"""
        return self._is_playing

    def seek_to(self, time_seconds: float):
        """
        Seek to specific time in video

        Args:
            time_seconds: Time in seconds to seek to
        """
        # Clamp to valid range
        self._current_time = max(0.0, min(time_seconds, self._duration))

    def seek_forward(self, seconds: float = 5.0):
        """
        Seek forward by specified amount

        Args:
            seconds: Number of seconds to seek forward
        """
        self.seek_to(self._current_time + seconds)

    def seek_backward(self, seconds: float = 5.0):
        """
        Seek backward by specified amount

        Args:
            seconds: Number of seconds to seek backward
        """
        self.seek_to(self._current_time - seconds)

    def get_current_time(self) -> float:
        """Get current playback position in seconds"""
        return self._current_time

    def set_current_time(self, time_seconds: float):
        """Set current playback position"""
        self._current_time = max(0.0, time_seconds)

    def get_duration(self) -> float:
        """Get video duration in seconds"""
        return self._duration

    def set_duration(self, duration: float):
        """Set video duration (for testing)"""
        self._duration = max(0.0, duration)

    def has_ended(self) -> bool:
        """Check if video has reached the end"""
        return self._duration > 0 and self._current_time >= self._duration

    def set_playback_rate(self, rate: float):
        """
        Set playback rate (speed)

        Args:
            rate: Playback rate (0.5 = half speed, 1.0 = normal, 2.0 = double)
        """
        self._playback_rate = max(0.25, min(rate, 2.0))

    def get_playback_rate(self) -> float:
        """Get current playback rate"""
        return self._playback_rate

    def set_volume(self, volume: float):
        """
        Set volume level

        Args:
            volume: Volume level (0.0 = mute, 1.0 = max)
        """
        self._volume = max(0.0, min(volume, 1.0))

    def get_volume(self) -> float:
        """Get current volume level"""
        return self._volume

    def mute(self):
        """Mute video"""
        self._muted = True

    def unmute(self):
        """Unmute video"""
        self._muted = False

    def is_muted(self) -> bool:
        """Check if video is muted"""
        return self._muted

    def set_loop(self, loop: bool):
        """Enable or disable looping"""
        self._loop = loop

    def is_looping(self) -> bool:
        """Check if video is set to loop"""
        return self._loop

    def enter_fullscreen(self):
        """Enter fullscreen mode"""
        self._is_fullscreen = True

    def exit_fullscreen(self):
        """Exit fullscreen mode"""
        self._is_fullscreen = False

    def is_fullscreen(self) -> bool:
        """Check if video is in fullscreen mode"""
        return self._is_fullscreen

    # ========================================================================
    # HTML Rendering
    # ========================================================================

    def to_html(self) -> str:
        """
        Generate HTML for video player

        Returns:
            HTML string with video player markup
        """
        if not self.is_ready():
            return self._render_no_video_message()

        # Check if file exists, show warning if not
        if not self.video_exists():
            return self._render_missing_file_message()

        # Build video element attributes
        attrs = [
            'controls',
            f'preload="metadata"',
            f'class="video-player"',
            f'title="{self.test_name}"'
        ]

        if self.autoplay:
            attrs.append('autoplay')

        if self._loop:
            attrs.append('loop')

        if self._muted:
            attrs.append('muted')

        # Build video source URL
        # If it's a relative path, make it absolute from /artifacts
        video_url = self.video_path
        if not video_url.startswith('/') and not video_url.startswith('http'):
            video_url = f"/artifacts/videos/{video_url}"

        # Generate HTML
        html = f'''
<div class="video-container" style="margin: 16px 0;">
    <div class="video-header" style="margin-bottom: 8px;">
        <h4 style="margin: 0; font-size: 14px; color: #666;">📹 {self.test_name}</h4>
    </div>
    <video {' '.join(attrs)} style="width: 100%; max-width: 800px; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <source src="{video_url}" type="video/webm">
        <source src="{video_url}" type="video/mp4">
        <p style="padding: 20px; text-align: center; color: #999;">
            Your browser doesn't support HTML5 video playback.
            <a href="{video_url}" download style="color: #0066cc;">Download the video</a> to view it.
        </p>
    </video>
    <div class="video-footer" style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 12px; color: #999;">
            {self._get_file_info()}
        </span>
        <a href="{video_url}" download style="font-size: 12px; color: #0066cc; text-decoration: none;">
            ⬇️ Download Video
        </a>
    </div>
</div>
'''

        return html.strip()

    def _render_no_video_message(self) -> str:
        """Render message when no video is available"""
        return '''
<div class="video-not-available" style="padding: 40px; text-align: center; background: #f5f5f5; border-radius: 8px; margin: 16px 0;">
    <div style="font-size: 48px; margin-bottom: 16px;">🎬</div>
    <h4 style="margin: 0 0 8px 0; color: #666;">No Video Available</h4>
    <p style="margin: 0; color: #999; font-size: 14px;">
        This test result does not have an associated video recording.
    </p>
</div>
'''

    def _render_missing_file_message(self) -> str:
        """Render message when video file is missing"""
        return f'''
<div class="video-file-missing" style="padding: 40px; text-align: center; background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; margin: 16px 0;">
    <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
    <h4 style="margin: 0 0 8px 0; color: #856404;">Video File Not Found</h4>
    <p style="margin: 0; color: #999; font-size: 14px;">
        The video file for this test could not be found: <code style="background: #eee; padding: 2px 6px; border-radius: 4px;">{self.video_path}</code>
    </p>
</div>
'''

    def _get_file_info(self) -> str:
        """Get file information string"""
        if self.metadata:
            size_mb = self.metadata.size_bytes / (1024 * 1024)
            return f"{self.metadata.format.upper()} • {size_mb:.1f} MB"
        return "Video file"


# ============================================================================
# Helper Functions
# ============================================================================

def create_video_player_modal(test_results: list) -> str:
    """
    Create HTML for a modal with multiple video players

    Args:
        test_results: List of TestResult objects

    Returns:
        HTML string with modal content
    """
    videos_html = ""

    for result in test_results:
        if result.video_path:
            player = VideoPlayer.from_test_result(result)
            videos_html += player.to_html()

    if not videos_html:
        videos_html = '<p style="text-align: center; color: #999; padding: 40px;">No videos available for these test results.</p>'

    return f'''
<div class="videos-modal" style="padding: 20px;">
    <h3 style="margin-top: 0;">Test Failure Videos</h3>
    {videos_html}
</div>
'''


def render_video_thumbnail(video_path: str, test_name: str) -> str:
    """
    Render a clickable thumbnail for a video

    Args:
        video_path: Path to video file
        test_name: Name of the test

    Returns:
        HTML string with thumbnail
    """
    return f'''
<div class="video-thumbnail" style="cursor: pointer; position: relative; overflow: hidden; border-radius: 8px;" onclick="openVideoModal('{video_path}')">
    <div style="background: #333; width: 100%; height: 150px; display: flex; align-items: center; justify-content: center;">
        <div style="width: 60px; height: 60px; background: rgba(255,255,255,0.9); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
            <span style="font-size: 24px; margin-left: 4px;">▶</span>
        </div>
    </div>
    <div style="position: absolute; bottom: 0; left: 0; right: 0; padding: 8px; background: linear-gradient(transparent, rgba(0,0,0,0.7)); color: white; font-size: 12px;">
        {test_name}
    </div>
</div>
'''
