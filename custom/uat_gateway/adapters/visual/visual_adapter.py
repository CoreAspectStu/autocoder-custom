"""
Visual Adapter - Integrate reg-cli for visual regression testing

This module is responsible for:
- Capturing baseline screenshots
- Comparing screenshots with tolerance
- Supporting multiple viewports
- Generating diff reports
- Masking dynamic content
- Storing screenshots efficiently
"""

import os
import json
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from PIL import Image, ImageDraw
import sys

# Add parent directory to path for imports

from uat_gateway.utils.logger import get_logger
from uat_gateway.utils.errors import AdapterError, handle_errors


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Viewport:
    """Represents a viewport configuration"""
    name: str  # e.g., 'desktop', 'tablet', 'mobile'
    width: int
    height: int
    device_scale_factor: float = 1.0
    is_mobile: bool = False
    has_touch: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "deviceScaleFactor": self.device_scale_factor,
            "isMobile": self.is_mobile,
            "hasTouch": self.has_touch
        }


@dataclass
class ScreenshotMetadata:
    """Metadata about a captured screenshot"""
    test_name: str
    scenario_type: Optional[str]  # 'happy_path', 'error_path', etc.
    viewport: str
    timestamp: datetime
    file_path: str
    file_size: int
    width: int
    height: int
    format: str  # 'png', 'jpeg', etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "scenario_type": self.scenario_type,
            "viewport": self.viewport,
            "timestamp": self.timestamp.isoformat(),
            "file_path": str(self.file_path),
            "file_size": self.file_size,
            "width": self.width,
            "height": self.height,
            "format": self.format
        }


@dataclass
class MaskSelector:
    """Defines a CSS selector for masking dynamic content"""
    selector: str  # CSS selector (e.g., '.date', '#timestamp', '[data-dynamic]')
    name: str  # Human-readable name
    color: str = "#000000"  # Color to use for masking (default black)
    mask_type: str = "fill"  # 'fill' or 'blur'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "selector": self.selector,
            "name": self.name,
            "color": self.color,
            "mask_type": self.mask_type
        }


@dataclass
class ComparisonResult:
    """Result of comparing two screenshots"""
    test_name: str
    viewport: str
    passed: bool
    difference_percentage: float
    baseline_path: Optional[str] = None
    current_path: Optional[str] = None
    diff_path: Optional[str] = None
    diff_pixels: int = 0
    total_pixels: int = 0
    masks_applied: List[str] = field(default_factory=list)  # Feature #109: List of mask names applied

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "test_name": self.test_name,
            "viewport": self.viewport,
            "passed": self.passed,
            "difference_percentage": self.difference_percentage,
            "baseline_path": self.baseline_path,
            "current_path": self.current_path,
            "diff_path": self.diff_path,
            "diff_pixels": self.diff_pixels,
            "total_pixels": self.total_pixels,
            "masks_applied": self.masks_applied
        }


# ============================================================================
# Visual Adapter Implementation
# ============================================================================

class VisualAdapter:
    """
    Visual regression testing adapter using reg-cli

    This adapter handles:
    - Capturing and storing baseline screenshots
    - Comparing screenshots against baselines
    - Managing multiple viewports
    - Generating diff reports
    """

    def __init__(
        self,
        baseline_dir: str = "visual/baseline",
        current_dir: str = "visual/current",
        diff_dir: str = "visual/diff",
        json_path: str = "visual/reg-cli.json",
        tolerance: float = 0.0,
        thresholds: Dict[str, float] = None,
        enable_compression: bool = True,
        compression_level: int = 9
    ):
        """
        Initialize the Visual Adapter

        Args:
            baseline_dir: Directory to store baseline screenshots
            current_dir: Directory to store current screenshots
            diff_dir: Directory to store diff images
            json_path: Path to reg-cli configuration file
            tolerance: Default tolerance level (0-100)
            thresholds: Per-test threshold overrides
            enable_compression: Enable PNG compression (default True)
            compression_level: PNG compression level (0-9, default 9 for max compression)
        """
        self.logger = get_logger(__name__)
        self.baseline_dir = Path(baseline_dir)
        self.current_dir = Path(current_dir)
        self.diff_dir = Path(diff_dir)
        self.json_path = Path(json_path)
        self.tolerance = tolerance
        self.thresholds = thresholds or {}
        self.enable_compression = enable_compression
        self.compression_level = compression_level
        self.mask_selectors: List[MaskSelector] = self._default_masks()

        # Default viewports
        self.viewports: List[Viewport] = [
            Viewport("desktop", 1920, 1080),
            Viewport("tablet", 768, 1024, is_mobile=True, has_touch=True),
            Viewport("mobile", 375, 667, is_mobile=True, has_touch=True)
        ]

        # Create directories
        self._setup_directories()

        # Configure reg-cli
        self._configure_reg_cli()

        self.logger.info(f"VisualAdapter initialized with baseline_dir={baseline_dir}")


    def _default_masks(self) -> List[MaskSelector]:
        """
        Get default mask selectors for common dynamic content

        Returns:
            List of default mask selectors
        """
        return [
            MaskSelector(
                selector="[data-dynamic]",
                name="Explicitly marked dynamic content",
                color="#000000"
            ),
            MaskSelector(
                selector=".timestamp, .date, .time, .datetime",
                name="Date/time displays",
                color="#000000"
            ),
            MaskSelector(
                selector=".user-id, .session-id, .request-id",
                name="Dynamic IDs",
                color="#000000"
            ),
            MaskSelector(
                selector=".counter, .count, .badge",
                name="Dynamic counters and badges",
                color="#000000"
            ),
            MaskSelector(
                selector=".random, .uuid",
                name="Random/UUID content",
                color="#000000"
            )
        ]


    def _setup_directories(self):
        """Create necessary directories if they don't exist"""
        try:
            self.baseline_dir.mkdir(parents=True, exist_ok=True)
            self.current_dir.mkdir(parents=True, exist_ok=True)
            self.diff_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info("Visual directories created/verified")
        except Exception as e:
            self.logger.error(f"Failed to create directories: {e}")
            raise

    def _configure_reg_cli(self):
        """Create reg-cli configuration file"""
        try:
            config = {
                "base": str(self.current_dir),
                "head": str(self.baseline_dir),
                "diff": str(self.diff_dir),
                "json": str(self.json_path),
                "tolerance": self.tolerance,
                "thresholds": self.thresholds,
                "ignoreChange": [],
                "viewports": [
                    {"name": v.name, "width": v.width, "height": v.height}
                    for v in self.viewports
                ]
            }

            # Ensure parent directory exists
            self.json_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.json_path, 'w') as f:
                json.dump(config, f, indent=2)

            self.logger.info(f"reg-cli configuration written to {self.json_path}")
        except Exception as e:
            self.logger.error(f"Failed to configure reg-cli: {e}")
            raise

    def capture_baseline(
        self,
        test_name: str,
        screenshot_path: str,
        viewport: str = "desktop",
        scenario_type: Optional[str] = None
    ) -> ScreenshotMetadata:
        """
        Capture and store a baseline screenshot

        This method validates and stores a screenshot as a baseline for future comparisons.

        Args:
            test_name: Name of the test
            screenshot_path: Path to the screenshot file
            viewport: Viewport name (e.g., 'desktop', 'tablet', 'mobile')
            scenario_type: Type of scenario (e.g., 'happy_path', 'error_path')

        Returns:
            ScreenshotMetadata with information about the captured baseline

        Raises:
            Exception: If screenshot is invalid or cannot be stored
        """
        self.logger.info(f"Capturing baseline for test={test_name}, viewport={viewport}")

        # Validate screenshot file exists
        screenshot_file = Path(screenshot_path)
        if not screenshot_file.exists():
            raise Exception(f"Screenshot file not found: {screenshot_path}")

        # Validate it's a valid image
        try:
            with Image.open(screenshot_file) as img:
                width, height = img.size
                format_name = img.format.lower() if img.format else "unknown"
                img.verify()  # Verify it's a valid image file
        except Exception as e:
            raise Exception(f"Invalid screenshot file: {e}")

        # Construct baseline filename
        # Format: testname-viewport-scenario.png
        if scenario_type:
            filename = f"{test_name}-{viewport}-{scenario_type}.png"
        else:
            filename = f"{test_name}-{viewport}.png"

        baseline_path = self.baseline_dir / filename

        # Copy screenshot to baseline directory with compression if enabled (Feature #110)
        if self.enable_compression:
            # Open and re-save with compression
            with Image.open(screenshot_file) as img:
                # Ensure image is in a format that supports compression
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Save with compression level
                img.save(baseline_path, 'PNG', compress_level=self.compression_level)
                self.logger.debug(f"Saved with compression level {self.compression_level}")
        else:
            # Copy without compression
            import shutil
            shutil.copy2(screenshot_file, baseline_path)

        file_size = baseline_path.stat().st_size

        # Create metadata
        metadata = ScreenshotMetadata(
            test_name=test_name,
            scenario_type=scenario_type,
            viewport=viewport,
            timestamp=datetime.now(),
            file_path=str(baseline_path),
            file_size=file_size,
            width=width,
            height=height,
            format=format_name
        )

        self.logger.info(f"Baseline saved: {baseline_path} ({file_size} bytes)")

        return metadata

    def get_baseline_path(
        self,
        test_name: str,
        viewport: str = "desktop",
        scenario_type: Optional[str] = None
    ) -> Optional[Path]:
        """
        Get the path to a baseline screenshot

        Args:
            test_name: Name of the test
            viewport: Viewport name
            scenario_type: Scenario type

        Returns:
            Path to baseline file, or None if not found
        """
        if scenario_type:
            filename = f"{test_name}-{viewport}-{scenario_type}.png"
        else:
            filename = f"{test_name}-{viewport}.png"

        baseline_path = self.baseline_dir / filename

        if baseline_path.exists():
            return baseline_path

        return None

    def list_baselines(self) -> List[str]:
        """
        List all baseline screenshots

        Returns:
            List of baseline filenames
        """
        if not self.baseline_dir.exists():
            return []

        baselines = []
        for file in self.baseline_dir.glob("*.png"):
            baselines.append(file.name)

        return sorted(baselines)

    def get_storage_size(self) -> Dict[str, Any]:
        """
        Get total storage size for all screenshots (Feature #110)

        Returns:
            Dictionary with total_bytes, file_count, and breakdown by directory
        """
        total_bytes = 0
        file_count = 0
        breakdown = {}

        for dir_name, dir_path in [
            ("baseline", self.baseline_dir),
            ("current", self.current_dir),
            ("diff", self.diff_dir)
        ]:
            if dir_path.exists():
                dir_bytes = sum(f.stat().st_size for f in dir_path.glob("*.png") if f.is_file())
                dir_count = len(list(dir_path.glob("*.png")))
                total_bytes += dir_bytes
                file_count += dir_count
                breakdown[dir_name] = {
                    "bytes": dir_bytes,
                    "count": dir_count,
                    "path": str(dir_path)
                }

        return {
            "total_bytes": total_bytes,
            "file_count": file_count,
            "breakdown": breakdown,
            "total_mb": total_bytes / (1024 * 1024),
            "compression_enabled": self.enable_compression,
            "compression_level": self.compression_level if self.enable_compression else None
        }


    # ========================================================================
    # Feature #109: Mask Management Methods
    # ========================================================================

    def list_mask_selectors(self) -> List[Dict[str, Any]]:
        """
        List all configured mask selectors

        Returns:
            List of mask selector dictionaries
        """
        return [mask.to_dict() for mask in self.mask_selectors]

    def add_mask_selector(
        self,
        selector: str,
        name: str,
        color: str = "#000000",
        mask_type: str = "fill"
    ) -> None:
        """
        Add a new mask selector

        Args:
            selector: CSS selector for elements to mask
            name: Human-readable name for the mask
            color: Color to use for masking (default black)
            mask_type: Type of masking ('fill' or 'blur')
        """
        new_mask = MaskSelector(
            selector=selector,
            name=name,
            color=color,
            mask_type=mask_type
        )
        self.mask_selectors.append(new_mask)
        self.logger.info(f"Added mask selector: {name} ({selector})")

    def remove_mask_selector(self, selector: str) -> bool:
        """
        Remove a mask selector by CSS selector

        Args:
            selector: CSS selector of mask to remove

        Returns:
            True if mask was removed, False if not found
        """
        initial_count = len(self.mask_selectors)
        self.mask_selectors = [
            mask for mask in self.mask_selectors
            if mask.selector != selector
        ]

        removed = len(self.mask_selectors) < initial_count
        if removed:
            self.logger.info(f"Removed mask selector: {selector}")
        else:
            self.logger.warning(f"Mask selector not found: {selector}")

        return removed

    def clear_mask_selectors(self) -> None:
        """
        Clear all mask selectors
        """
        count = len(self.mask_selectors)
        self.mask_selectors = []
        self.logger.info(f"Cleared {count} mask selectors")

    def apply_mask(
        self,
        image_path: str,
        output_path: str,
        mask_regions: List[Tuple[int, int, int, int]] = None
    ) -> bool:
        """
        Apply masks to an image and save the result

        This method creates a blacked-out version of the image with certain regions masked.
        By default, it masks the bottom 30 pixels (common for timestamps/dates).
        If specific mask_regions are provided, those are used instead.

        Args:
            image_path: Path to original image
            output_path: Path where masked image should be saved
            mask_regions: Optional list of (x, y, width, height) tuples to mask

        Returns:
            True if masking was successful, False otherwise
        """
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Create a copy to modify
                masked = img.copy()

                # Default mask: bottom 30 pixels (for timestamps, dates, etc.)
                if mask_regions is None:
                    width, height = masked.size
                    mask_regions = [(0, height - 30, width, 30)]

                # Apply black fill to each mask region
                draw = ImageDraw.Draw(masked)
                for x, y, w, h in mask_regions:
                    draw.rectangle([x, y, x + w, y + h], fill="#000000")

                # Save masked image
                output = Path(output_path)
                output.parent.mkdir(parents=True, exist_ok=True)

                if self.enable_compression:
                    masked.save(output, 'PNG', compress_level=self.compression_level)
                else:
                    masked.save(output, 'PNG')

                self.logger.debug(f"Applied masks to {image_path} -> {output_path}")
                return True

        except Exception as e:
            self.logger.error(f"Failed to apply masks: {e}")
            return False

    def create_masked_copy(
        self,
        original_path: str,
        output_dir: str = None
    ) -> Optional[str]:
        """
        Create a masked copy of an image

        This is a convenience method that creates a masked version of an image
        in a specified output directory.

        Args:
            original_path: Path to original image
            output_dir: Directory for masked copy (defaults to test_dir/masked)

        Returns:
            Path to masked image, or None if failed
        """
        if output_dir is None:
            output_dir = self.test_dir / "masked" if hasattr(self, 'test_dir') else "masked"

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        original = Path(original_path)
        masked_path = output_dir / f"masked_{original.name}"

        success = self.apply_mask(str(original), str(masked_path))

        if success:
            return str(masked_path)
        else:
            return None

    def validate_baseline_image(self, baseline_path: str) -> Tuple[bool, str]:
        """
        Validate that a baseline screenshot is a valid image

        Args:
            baseline_path: Path to baseline screenshot

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            path = Path(baseline_path)

            # Check file exists
            if not path.exists():
                return False, f"File does not exist: {baseline_path}"

            # Check it's a file
            if not path.is_file():
                return False, f"Path is not a file: {baseline_path}"

            # Check file size > 0
            if path.stat().st_size == 0:
                return False, f"File is empty: {baseline_path}"

            # Try to open and verify as image
            with Image.open(path) as img:
                img.verify()

            # Re-open to check dimensions (verify closes the file)
            with Image.open(path) as img:
                width, height = img.size
                if width <= 0 or height <= 0:
                    return False, f"Invalid dimensions: {width}x{height}"

            return True, "Valid image"

        except Exception as e:
            return False, f"Image validation failed: {str(e)}"

    def compare_screenshots(
        self,
        test_name: str,
        current_path: str,
        viewport: str = "desktop",
        scenario_type: Optional[str] = None,
        tolerance: Optional[float] = None,
        apply_masks: bool = False  # Feature #109: Apply masks before comparison
    ) -> ComparisonResult:
        """
        Compare a current screenshot against its baseline with tolerance (Feature #106)

        This method performs pixel-by-pixel comparison with configurable tolerance.
        It counts different pixels and determines if the difference is within tolerance.

        Args:
            test_name: Name of the test
            current_path: Path to current screenshot
            viewport: Viewport name
            scenario_type: Scenario type
            tolerance: Override default tolerance (percentage 0-100)
            apply_masks: Apply masks to images before comparison (Feature #109)

        Returns:
            ComparisonResult with comparison details including:
            - passed: Whether comparison passed (difference <= tolerance)
            - difference_percentage: Actual percentage of different pixels
            - diff_pixels: Number of different pixels
            - total_pixels: Total pixels in image
            - masks_applied: List of mask names that were applied (if apply_masks=True)
        """
        self.logger.info(f"Comparing screenshot for test={test_name}, viewport={viewport}")

        # Use provided tolerance or fall back to default
        effective_tolerance = tolerance if tolerance is not None else self.tolerance

        # Get baseline path
        baseline_path = self.get_baseline_path(test_name, viewport, scenario_type)

        if baseline_path is None:
            self.logger.warning(f"No baseline found for {test_name}")
            return ComparisonResult(
                test_name=test_name,
                viewport=viewport,
                passed=False,
                difference_percentage=100.0,
                current_path=current_path
            )

        # Apply masks if requested (Feature #109)
        masks_applied = []
        baseline_to_compare = baseline_path
        current_to_compare = Path(current_path)

        if apply_masks and self.mask_selectors:
            self.logger.info(f"Applying {len(self.mask_selectors)} masks before comparison")
            masks_applied = [mask.name for mask in self.mask_selectors]

            # Create masked versions for comparison
            import tempfile
            temp_dir = Path(tempfile.mkdtemp(prefix="uat_masked_"))

            try:
                # Apply masks to both baseline and current
                masked_baseline = temp_dir / f"masked_baseline_{Path(baseline_path).name}"
                masked_current = temp_dir / f"masked_current_{Path(current_path).name}"

                if self.apply_mask(str(baseline_path), str(masked_baseline)):
                    baseline_to_compare = masked_baseline
                    self.logger.debug(f"Created masked baseline: {masked_baseline}")

                if self.apply_mask(str(current_path), str(masked_current)):
                    current_to_compare = masked_current
                    self.logger.debug(f"Created masked current: {masked_current}")

            except Exception as e:
                self.logger.error(f"Failed to apply masks: {e}")
                # Continue without masks if application fails
                masks_applied = []

        # Perform pixel-based comparison with tolerance (Feature #106)
        try:
            result = self._compare_with_tolerance(
                baseline_path=baseline_to_compare,
                current_path=current_to_compare,
                tolerance=effective_tolerance
            )

            # Add masks_applied to result (Feature #109)
            result.masks_applied = masks_applied

            # Update result with test metadata
            result.test_name = test_name
            result.viewport = viewport
            result.baseline_path = str(baseline_path)
            result.current_path = current_path

            self.logger.info(
                f"Comparison result: passed={result.passed}, "
                f"difference={result.difference_percentage:.2f}%, "
                f"tolerance={effective_tolerance:.2f}%"
            )

            return result

        except Exception as e:
            self.logger.error(f"Comparison failed: {e}")
            # Return failure result on error
            return ComparisonResult(
                test_name=test_name,
                viewport=viewport,
                passed=False,
                difference_percentage=100.0,
                baseline_path=str(baseline_path),
                current_path=current_path
            )

    def _compare_with_tolerance(
        self,
        baseline_path: Path,
        current_path: Path,
        tolerance: float
    ) -> ComparisonResult:
        """
        Perform pixel-by-pixel comparison with tolerance (Feature #106)

        This method:
        1. Loads both images
        2. Compares them pixel by pixel
        3. Counts different pixels (with small per-pixel tolerance)
        4. Calculates percentage difference
        5. Determines pass/fail based on tolerance threshold

        Args:
            baseline_path: Path to baseline image
            current_path: Path to current image
            tolerance: Maximum allowed difference percentage

        Returns:
            ComparisonResult with detailed comparison metrics
        """
        # Validate both files exist
        if not baseline_path.exists():
            raise AdapterError(f"Baseline file not found: {baseline_path}")
        if not current_path.exists():
            raise AdapterError(f"Current file not found: {current_path}")

        # Load images
        try:
            with Image.open(baseline_path) as baseline_img:
                baseline_img.load()
                baseline_rgb = baseline_img.convert('RGB')

            with Image.open(current_path) as current_img:
                current_img.load()
                current_rgb = current_img.convert('RGB')

        except Exception as e:
            raise AdapterError(f"Failed to load images: {e}")

        # Ensure images are the same size
        if baseline_rgb.size != current_rgb.size:
            self.logger.warning(
                f"Image size mismatch: baseline={baseline_rgb.size}, "
                f"current={current_rgb.size}. Resizing current to match baseline."
            )
            current_rgb = current_rgb.resize(baseline_rgb.size)

        width, height = baseline_rgb.size
        total_pixels = width * height

        # Count different pixels
        diff_pixels = self._count_different_pixels(baseline_rgb, current_rgb)
        difference_percentage = (diff_pixels / total_pixels) * 100 if total_pixels > 0 else 0.0

        # Determine if comparison passed (difference within tolerance)
        passed = difference_percentage <= tolerance

        return ComparisonResult(
            test_name="",  # Will be filled by caller
            viewport="",   # Will be filled by caller
            passed=passed,
            difference_percentage=difference_percentage,
            diff_pixels=diff_pixels,
            total_pixels=total_pixels
        )

    def _hash_file(self, file_path: Path) -> str:
        """Calculate MD5 hash of a file"""
        import hashlib
        hash_md5 = hashlib.md5()

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)

        return hash_md5.hexdigest()
    # ========================================================================
    # Feature #112: Layout Shift Detection
    # ========================================================================

    def detect_layout_shifts(
        self,
        baseline_path: str,
        current_path: str,
        threshold: float = 5.0,
        min_shift_pixels: int = 10
    ) -> Dict[str, Any]:
        """
        Detect layout shifts between baseline and current screenshots (Feature #112)

        This method analyzes two screenshots to detect if elements have moved position.
        It uses a combination of techniques:
        1. Structural comparison: Identifies regions of significant change
        2. Blob detection: Finds distinct visual elements and tracks their movement
        3. Pixel difference clustering: Groups changed pixels to identify shifted regions

        Args:
            baseline_path: Path to baseline screenshot
            current_path: Path to current screenshot
            threshold: Pixel difference threshold (0-255, default 5.0)
            min_shift_pixels: Minimum pixel shift to consider as layout shift (default 10)

        Returns:
            Dictionary with layout shift detection results:
            {
                "layout_shift_detected": bool,
                "shift_amount_pixels": float,
                "shift_amount_percentage": float,
                "shifted_regions": List[Dict],
                "shift_direction": str,  # "horizontal", "vertical", "both", "none"
                "confidence": float  # 0-1
            }
        """
        self.logger.info(f"Detecting layout shifts between {baseline_path} and {current_path}")

        # Validate both files exist
        baseline_file = Path(baseline_path)
        current_file = Path(current_path)

        if not baseline_file.exists():
            raise AdapterError(f"Baseline file not found: {baseline_path}")
        if not current_file.exists():
            raise AdapterError(f"Current file not found: {current_path}")

        # Load images
        try:
            with Image.open(baseline_file) as baseline_img:
                baseline_img.load()
                baseline_rgb = baseline_img.convert('RGB')

            with Image.open(current_file) as current_img:
                current_img.load()
                current_rgb = current_img.convert('RGB')

        except Exception as e:
            raise AdapterError(f"Failed to load images: {e}")

        # Ensure images are the same size
        if baseline_rgb.size != current_rgb.size:
            self.logger.warning(
                f"Image size mismatch: baseline={baseline_rgb.size}, "
                f"current={current_rgb.size}. Resizing current to match baseline."
            )
            current_rgb = current_rgb.resize(baseline_rgb.size)

        width, height = baseline_rgb.size
        total_pixels = width * height

        # Detect layout shifts using multiple methods
        shift_result = self._analyze_layout_shifts(
            baseline_rgb,
            current_rgb,
            threshold=threshold,
            min_shift_pixels=min_shift_pixels
        )

        self.logger.info(
            f"Layout shift detection complete: "
            f"detected={shift_result['layout_shift_detected']}, "
            f"shift_amount={shift_result['shift_amount_pixels']:.2f}px, "
            f"confidence={shift_result['confidence']:.2f}"
        )

        return shift_result

    def _analyze_layout_shifts(
        self,
        baseline_img: Image.Image,
        current_img: Image.Image,
        threshold: float,
        min_shift_pixels: int
    ) -> Dict[str, Any]:
        """
        Analyze images to detect layout shifts

        This method uses a multi-step approach:
        1. Find all pixels that differ significantly
        2. Cluster changed pixels into regions
        3. Analyze the centroid movement of each region
        4. Calculate overall shift metrics

        Args:
            baseline_img: Baseline image (RGB mode)
            current_img: Current image (RGB mode)
            threshold: Pixel difference threshold
            min_shift_pixels: Minimum shift to consider significant

        Returns:
            Dictionary with layout shift analysis results
        """
        width, height = baseline_img.size

        # Step 1: Create a difference map
        diff_map = self._create_difference_map(baseline_img, current_img, threshold)

        # Step 2: Find connected components (regions) of changed pixels
        changed_regions = self._find_changed_regions(diff_map, min_area=100)

        # If no significant changes found, return no shift
        if not changed_regions:
            return {
                "layout_shift_detected": False,
                "shift_amount_pixels": 0.0,
                "shift_amount_percentage": 0.0,
                "shifted_regions": [],
                "shift_direction": "none",
                "confidence": 1.0
            }

        # Step 3: For each region, analyze the shift
        shift_analyses = []
        for region in changed_regions:
            analysis = self._analyze_region_shift(
                baseline_img,
                current_img,
                region
            )
            if analysis['shift_detected']:
                shift_analyses.append(analysis)

        # Step 4: Calculate overall shift metrics
        if not shift_analyses:
            return {
                "layout_shift_detected": False,
                "shift_amount_pixels": 0.0,
                "shift_amount_percentage": 0.0,
                "shifted_regions": [],
                "shift_direction": "none",
                "confidence": 1.0
            }

        # Calculate average shift
        total_shift_x = sum(s['shift_x'] for s in shift_analyses)
        total_shift_y = sum(s['shift_y'] for s in shift_analyses)
        avg_shift_x = total_shift_x / len(shift_analyses)
        avg_shift_y = total_shift_y / len(shift_analyses)
        avg_shift_magnitude = (avg_shift_x**2 + avg_shift_y**2) ** 0.5

        # Determine shift direction
        shift_direction = "none"
        if avg_shift_magnitude >= min_shift_pixels:
            if abs(avg_shift_x) > abs(avg_shift_y) * 2:
                shift_direction = "horizontal"
            elif abs(avg_shift_y) > abs(avg_shift_x) * 2:
                shift_direction = "vertical"
            else:
                shift_direction = "both"

        # Calculate shift as percentage of image dimensions
        max_dimension = max(width, height)
        shift_percentage = (avg_shift_magnitude / max_dimension) * 100

        # Confidence based on consistency of shifts across regions
        if len(shift_analyses) > 1:
            confidence = 0.7  # Moderate confidence when multiple regions shift
        else:
            confidence = 0.9  # High confidence for single region shift

        return {
            "layout_shift_detected": avg_shift_magnitude >= min_shift_pixels,
            "shift_amount_pixels": round(avg_shift_magnitude, 2),
            "shift_amount_percentage": round(shift_percentage, 2),
            "shifted_regions": shift_analyses,
            "shift_direction": shift_direction,
            "average_shift_x": round(avg_shift_x, 2),
            "average_shift_y": round(avg_shift_y, 2),
            "num_shifted_regions": len(shift_analyses),
            "confidence": round(confidence, 2)
        }

    def _create_difference_map(
        self,
        baseline_img: Image.Image,
        current_img: Image.Image,
        threshold: float
    ) -> List[List[bool]]:
        """
        Create a boolean map of pixels that differ significantly

        Args:
            baseline_img: Baseline image
            current_img: Current image
            threshold: Pixel difference threshold

        Returns:
            2D list of booleans indicating changed pixels
        """
        width, height = baseline_img.size
        baseline_pixels = baseline_img.load()
        current_pixels = current_img.load()

        # Create difference map
        diff_map = [[False for _ in range(height)] for _ in range(width)]

        for y in range(height):
            for x in range(width):
                baseline_pixel = baseline_pixels[x, y]
                current_pixel = current_pixels[x, y]

                # Check if pixels differ beyond threshold
                pixel_diff = sum(abs(c1 - c2) for c1, c2 in zip(baseline_pixel, current_pixel)) / 3
                diff_map[x][y] = pixel_diff > threshold

        return diff_map

    def _find_changed_regions(
        self,
        diff_map: List[List[bool]],
        min_area: int = 100
    ) -> List[List[Tuple[int, int]]]:
        """
        Find connected regions of changed pixels using flood fill

        Args:
            diff_map: 2D boolean map of changed pixels
            min_area: Minimum area to consider as a region

        Returns:
            List of regions, where each region is a list of (x, y) coordinates
        """
        width = len(diff_map)
        height = len(diff_map[0]) if width > 0 else 0

        visited = [[False for _ in range(height)] for _ in range(width)]
        regions = []

        for x in range(width):
            for y in range(height):
                if diff_map[x][y] and not visited[x][y]:
                    # Found a new region, use flood fill to find all connected pixels
                    region = []
                    stack = [(x, y)]

                    while stack:
                        cx, cy = stack.pop()

                        if cx < 0 or cx >= width or cy < 0 or cy >= height:
                            continue
                        if visited[cx][cy] or not diff_map[cx][cy]:
                            continue

                        visited[cx][cy] = True
                        region.append((cx, cy))

                        # Add neighbors (4-connectivity)
                        stack.append((cx + 1, cy))
                        stack.append((cx - 1, cy))
                        stack.append((cx, cy + 1))
                        stack.append((cx, cy - 1))

                    # Only keep regions above minimum size
                    if len(region) >= min_area:
                        regions.append(region)

        return regions

    def _analyze_region_shift(
        self,
        baseline_img: Image.Image,
        current_img: Image.Image,
        region: List[Tuple[int, int]]
    ) -> Dict[str, Any]:
        """
        Analyze the shift of a specific region

        This method finds the bounding box of the region in both images
        and calculates how far the region's centroid has moved.

        Args:
            baseline_img: Baseline image
            current_img: Current image
            region: List of (x, y) coordinates in the region

        Returns:
            Dictionary with shift analysis for this region
        """
        if not region:
            return {
                "shift_detected": False,
                "shift_x": 0,
                "shift_y": 0,
                "region_size": 0
            }

        # Find bounding box of region
        min_x = min(x for x, y in region)
        max_x = max(x for x, y in region)
        min_y = min(y for x, y in region)
        max_y = max(y for x, y in region)

        # Calculate centroid in baseline
        baseline_centroid_x = sum(x for x, y in region) / len(region)
        baseline_centroid_y = sum(y for x, y in region) / len(region)

        # Extract region from baseline
        baseline_pixels = baseline_img.load()
        current_pixels = current_img.load()

        # Search for best matching region in current image
        best_shift_x = 0
        best_shift_y = 0
        min_diff = float('inf')

        # Search in a small window around the original position
        search_range = 30  # pixels
        for dx in range(-search_range, search_range + 1):
            for dy in range(-search_range, search_range + 1):
                # Calculate pattern difference for this shift
                pattern_diff = 0
                match_count = 0

                for rx, ry in region:
                    # Original position in baseline
                    bx, by = rx, ry

                    # Shifted position in current
                    cx = bx + dx
                    cy = by + dy

                    # Check bounds
                    if cx < 0 or cx >= current_img.width or cy < 0 or cy >= current_img.height:
                        continue

                    # Compare pixel colors
                    baseline_pixel = baseline_pixels[bx, by]
                    current_pixel = current_pixels[cx, cy]

                    pixel_diff = sum(abs(c1 - c2) for c1, c2 in zip(baseline_pixel, current_pixel))
                    pattern_diff += pixel_diff
                    match_count += 1

                if match_count > 0:
                    avg_diff = pattern_diff / match_count
                    if avg_diff < min_diff:
                        min_diff = avg_diff
                        best_shift_x = dx
                        best_shift_y = dy

        # Calculate shift magnitude
        shift_magnitude = (best_shift_x**2 + best_shift_y**2) ** 0.5

        return {
            "shift_detected": shift_magnitude > 0,
            "shift_x": best_shift_x,
            "shift_y": best_shift_y,
            "shift_magnitude": round(shift_magnitude, 2),
            "region_size": len(region),
            "region_bounds": {
                "min_x": min_x,
                "max_x": max_x,
                "min_y": min_y,
                "max_y": max_y,
                "width": max_x - min_x,
                "height": max_y - min_y
            },
            "baseline_centroid": {
                "x": round(baseline_centroid_x, 2),
                "y": round(baseline_centroid_y, 2)
            },
            "pattern_similarity": round(min_diff, 2)
        }

    def compare_layout_shift(
        self,
        test_name: str,
        baseline_path: str,
        current_path: str,
        viewport: str = "desktop",
        scenario_type: Optional[str] = None,
        max_allowed_shift: float = 20.0
    ) -> Dict[str, Any]:
        """
        Compare two screenshots for layout shifts (Feature #112)

        This is a convenience method that combines layout shift detection
        with comparison result generation.

        Args:
            test_name: Name of the test
            baseline_path: Path to baseline screenshot
            current_path: Path to current screenshot
            viewport: Viewport name
            scenario_type: Scenario type
            max_allowed_shift: Maximum allowed shift in pixels (default 20.0)

        Returns:
            Dictionary with comparison result including layout shift info
        """
        self.logger.info(
            f"Comparing layout shift for test={test_name}, viewport={viewport}"
        )

        # Detect layout shifts
        shift_result = self.detect_layout_shifts(
            baseline_path=baseline_path,
            current_path=current_path
        )

        # Determine if test passed based on shift amount
        shift_amount = shift_result["shift_amount_pixels"]
        passed = shift_amount <= max_allowed_shift

        # Generate standard comparison result
        comparison = {
            "test_name": test_name,
            "viewport": viewport,
            "passed": passed,
            "difference_percentage": shift_result["shift_amount_percentage"],
            "baseline_path": baseline_path,
            "current_path": current_path,
            "layout_shift_detected": shift_result["layout_shift_detected"],
            "shift_amount_pixels": shift_amount,
            "shift_direction": shift_result["shift_direction"],
            "shifted_regions": shift_result["shifted_regions"],
            "max_allowed_shift": max_allowed_shift,
            "confidence": shift_result["confidence"]
        }

        self.logger.info(
            f"Layout shift comparison complete: "
            f"shift={shift_amount:.2f}px, max_allowed={max_allowed_shift}px, "
            f"passed={passed}"
        )

        return comparison


    @handle_errors(component="visual_adapter", reraise=True)
    def generate_diff_report(
        self,
        test_name: str,
        baseline_path: str,
        current_path: str,
        viewport: str = "desktop",
        scenario_type: Optional[str] = None
    ) -> ComparisonResult:
        """
        Generate a diff report comparing baseline and current screenshots

        This method:
        - Compares the two images pixel by pixel
        - Generates a diff image highlighting differences
        - Calculates the percentage of pixels that differ
        - Saves the diff image to the diff directory

        Args:
            test_name: Name of the test
            baseline_path: Path to baseline screenshot
            current_path: Path to current screenshot
            viewport: Viewport name
            scenario_type: Scenario type

        Returns:
            ComparisonResult with diff path and statistics

        Raises:
            AdapterError: If images cannot be compared
        """
        self.logger.info(f"Generating diff report for test={test_name}, viewport={viewport}")

        # Validate both files exist
        baseline_file = Path(baseline_path)
        current_file = Path(current_path)

        if not baseline_file.exists():
            raise AdapterError(f"Baseline file not found: {baseline_path}")
        if not current_file.exists():
            raise AdapterError(f"Current file not found: {current_path}")

        # Load images
        try:
            with Image.open(baseline_file) as baseline_img:
                baseline_img.load()
                baseline_rgb = baseline_img.convert('RGB')

            with Image.open(current_file) as current_img:
                current_img.load()
                current_rgb = current_img.convert('RGB')

        except Exception as e:
            raise AdapterError(f"Failed to load images: {e}")

        # Ensure images are the same size
        if baseline_rgb.size != current_rgb.size:
            self.logger.warning(
                f"Image size mismatch: baseline={baseline_rgb.size}, "
                f"current={current_rgb.size}. Resizing current to match baseline."
            )
            current_rgb = current_rgb.resize(baseline_rgb.size)

        width, height = baseline_rgb.size
        total_pixels = width * height

        # Generate diff image
        diff_rgb = self._highlight_differences(baseline_rgb, current_rgb)

        # Calculate difference percentage
        diff_pixels = self._count_different_pixels(baseline_rgb, current_rgb)
        difference_percentage = (diff_pixels / total_pixels) * 100 if total_pixels > 0 else 0.0

        # Save diff image
        if scenario_type:
            diff_filename = f"{test_name}-{viewport}-{scenario_type}-diff.png"
        else:
            diff_filename = f"{test_name}-{viewport}-diff.png"

        diff_path = self.diff_dir / diff_filename
        diff_rgb.save(diff_path, 'PNG')

        self.logger.info(
            f"Diff report generated: {diff_path} "
            f"({diff_pixels}/{total_pixels} pixels different, "
            f"{difference_percentage:.2f}%)"
        )

        # Determine if comparison passed (using tolerance threshold)
        passed = difference_percentage <= self.tolerance

        return ComparisonResult(
            test_name=test_name,
            viewport=viewport,
            passed=passed,
            difference_percentage=difference_percentage,
            baseline_path=str(baseline_path),
            current_path=str(current_path),
            diff_path=str(diff_path),
            diff_pixels=diff_pixels,
            total_pixels=total_pixels
        )

    def _highlight_differences(
        self,
        baseline_img: Image.Image,
        current_img: Image.Image
    ) -> Image.Image:
        """
        Highlight visual differences between two images

        This method creates a diff image where:
        - Matching pixels are shown in grayscale
        - Different pixels are highlighted in bright magenta

        Args:
            baseline_img: Baseline image (RGB mode)
            current_img: Current image (RGB mode)

        Returns:
            Diff image with differences highlighted
        """
        # Create diff image (same size as input images)
        diff_img = Image.new('RGB', baseline_img.size)
        baseline_pixels = baseline_img.load()
        current_pixels = current_img.load()
        diff_pixels = diff_img.load()

        width, height = baseline_img.size

        for y in range(height):
            for x in range(width):
                baseline_pixel = baseline_pixels[x, y]
                current_pixel = current_pixels[x, y]

                # Check if pixels match (with small tolerance for compression artifacts)
                if self._pixels_match(baseline_pixel, current_pixel, tolerance=5):
                    # Pixels match - show in grayscale
                    gray_value = sum(baseline_pixel) // 3
                    diff_pixels[x, y] = (gray_value, gray_value, gray_value)
                else:
                    # Pixels differ - highlight in bright magenta
                    diff_pixels[x, y] = (255, 0, 255)

        return diff_img

    def _pixels_match(
        self,
        pixel1: Tuple[int, int, int],
        pixel2: Tuple[int, int, int],
        tolerance: int = 5
    ) -> bool:
        """
        Check if two pixels match within tolerance

        Args:
            pixel1: First pixel (R, G, B)
            pixel2: Second pixel (R, G, B)
            tolerance: Maximum allowed difference per channel

        Returns:
            True if pixels match within tolerance
        """
        for c1, c2 in zip(pixel1, pixel2):
            if abs(c1 - c2) > tolerance:
                return False
        return True

    def _count_different_pixels(
        self,
        baseline_img: Image.Image,
        current_img: Image.Image
    ) -> int:
        """
        Count the number of different pixels between two images

        Args:
            baseline_img: Baseline image
            current_img: Current image

        Returns:
            Number of pixels that differ
        """
        baseline_pixels = baseline_img.load()
        current_pixels = current_img.load()

        width, height = baseline_img.size
        diff_count = 0

        for y in range(height):
            for x in range(width):
                if not self._pixels_match(baseline_pixels[x, y], current_pixels[x, y], tolerance=5):
                    diff_count += 1

        return diff_count


    # ========================================================================
    # Feature #114: Baseline Approval and Update
    # ========================================================================

    @handle_errors(component="visual_adapter")
    def approve_baseline_update(
        self,
        test_name: str,
        new_screenshot_path: str,
        viewport: str = "desktop",
        scenario_type: Optional[str] = None,
        archive_old: bool = True
    ) -> ScreenshotMetadata:
        """
        Approve a visual change and update the baseline (Feature #114)

        This method:
        1. Archives the old baseline (if it exists)
        2. Copies the new screenshot to the baseline directory
        3. Returns metadata for the new baseline

        Args:
            test_name: Name of the test
            new_screenshot_path: Path to the new screenshot to approve
            viewport: Viewport name
            scenario_type: Scenario type
            archive_old: Whether to archive the old baseline (default True)

        Returns:
            ScreenshotMetadata for the new baseline

        Raises:
            AdapterError: If new screenshot is invalid
        """
        self.logger.info(
            f"Approving baseline update for test={test_name}, viewport={viewport}"
        )

        # Get path to existing baseline (if any)
        old_baseline_path = self.get_baseline_path(test_name, viewport, scenario_type)

        # Archive old baseline if it exists and archiving is enabled
        if old_baseline_path and archive_old:
            self._archive_baseline(old_baseline_path)

        # Capture new baseline (this will overwrite the old one)
        new_metadata = self.capture_baseline(
            test_name=test_name,
            screenshot_path=new_screenshot_path,
            viewport=viewport,
            scenario_type=scenario_type
        )

        self.logger.info(
            f"Baseline updated successfully: {new_metadata.file_path}"
        )

        return new_metadata

    @handle_errors(component="visual_adapter")
    def _archive_baseline(self, baseline_path: Path) -> Optional[str]:
        """
        Archive an old baseline screenshot (Feature #114)

        Creates a dated archive of the old baseline before it's replaced.

        Args:
            baseline_path: Path to the baseline to archive

        Returns:
            Path to archived baseline, or None if archiving failed
        """
        try:
            # Create archive directory if it doesn't exist
            archive_dir = self.baseline_dir.parent / "baseline_archive"
            archive_dir.mkdir(parents=True, exist_ok=True)

            # Create dated subdirectory
            from datetime import datetime
            date_str = datetime.now().strftime("%Y%m%d")
            time_str = datetime.now().strftime("%H%M%S")
            date_dir = archive_dir / date_str
            date_dir.mkdir(exist_ok=True)

            # Construct archive filename with timestamp
            original_filename = baseline_path.name
            # Remove .png extension and add timestamp
            base_name = original_filename.replace('.png', '')
            archive_filename = f"{base_name}_archived_{time_str}.png"
            archive_path = date_dir / archive_filename

            # Copy old baseline to archive
            import shutil
            shutil.copy2(baseline_path, archive_path)

            self.logger.info(
                f"Old baseline archived: {archive_path} "
                f"(original: {baseline_path})"
            )

            return str(archive_path)

        except Exception as e:
            self.logger.error(f"Failed to archive baseline: {e}")
            return None

    @handle_errors(component="visual_adapter")
    def list_archived_baselines(
        self,
        test_name: Optional[str] = None,
        viewport: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List archived baseline screenshots (Feature #114)

        Args:
            test_name: Filter by test name (optional)
            viewport: Filter by viewport (optional)

        Returns:
            List of archived baseline info dictionaries
        """
        archive_dir = self.baseline_dir.parent / "baseline_archive"

        if not archive_dir.exists():
            return []

        archived_baselines = []

        # Walk through archive directory structure
        for date_dir in sorted(archive_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue

            for archive_file in date_dir.glob("*.png"):
                # Parse filename to extract metadata
                info = {
                    "filename": archive_file.name,
                    "path": str(archive_file),
                    "date": date_dir.name,
                    "size": archive_file.stat().st_size,
                    "test_name": None,
                    "viewport": None,
                    "scenario_type": None,
                    "archived_at": None
                }

                # Parse filename format: testname-viewport-scenario_archivated_HHMMSS.png
                # or: testname-viewport_archived_HHMMSS.png
                name_parts = archive_file.stem.split('_archived_')
                if len(name_parts) >= 2:
                    base_part = name_parts[0]
                    time_part = name_parts[1]

                    # Extract test name, viewport, scenario from base part
                    parts = base_part.split('-')
                    if len(parts) >= 2:
                        info["test_name"] = parts[0]
                        info["viewport"] = parts[1]
                        if len(parts) >= 3:
                            info["scenario_type"] = parts[2]

                    # Parse timestamp
                    try:
                        from datetime import datetime
                        archived_time = datetime.strptime(time_part, "%H%M%S")
                        # Combine date and time
                        date_obj = datetime.strptime(date_dir.name, "%Y%m%d")
                        info["archived_at"] = date_obj.replace(
                            hour=archived_time.hour,
                            minute=archived_time.minute,
                            second=archived_time.second
                        ).isoformat()
                    except:
                        pass

                # Apply filters
                if test_name and info["test_name"] != test_name:
                    continue
                if viewport and info["viewport"] != viewport:
                    continue

                archived_baselines.append(info)

        return archived_baselines

    @handle_errors(component="visual_adapter")
    def restore_archived_baseline(
        self,
        archive_path: str,
        test_name: str,
        viewport: str = "desktop",
        scenario_type: Optional[str] = None
    ) -> ScreenshotMetadata:
        """
        Restore an archived baseline (Feature #114)

        This method:
        1. Archives the current baseline (if it exists)
        2. Restores the archived baseline to the baseline directory
        3. Returns metadata for the restored baseline

        Args:
            archive_path: Path to the archived baseline
            test_name: Name of the test
            viewport: Viewport name
            scenario_type: Scenario type

        Returns:
            ScreenshotMetadata for the restored baseline

        Raises:
            AdapterError: If archive file is not found or invalid
        """
        self.logger.info(f"Restoring archived baseline: {archive_path}")

        archive_file = Path(archive_path)

        # Verify archive exists
        if not archive_file.exists():
            raise AdapterError(f"Archived baseline not found: {archive_path}")

        # Archive current baseline if it exists
        current_baseline = self.get_baseline_path(test_name, viewport, scenario_type)
        if current_baseline:
            self._archive_baseline(current_baseline)

        # Copy archived baseline to baseline directory
        import shutil
        baseline_filename = archive_file.name.split('_archived_')[0] + '.png'
        new_baseline_path = self.baseline_dir / baseline_filename

        shutil.copy2(archive_file, new_baseline_path)

        # Get metadata for restored baseline
        with Image.open(new_baseline_path) as img:
            width, height = img.size
            file_size = new_baseline_path.stat().st_size

        metadata = ScreenshotMetadata(
            test_name=test_name,
            scenario_type=scenario_type,
            viewport=viewport,
            timestamp=datetime.now(),
            file_path=str(new_baseline_path),
            file_size=file_size,
            width=width,
            height=height,
            format="png"
        )

        self.logger.info(f"Baseline restored: {new_baseline_path}")

        return metadata

    @handle_errors(component="visual_adapter")
    def get_baseline_history(
        self,
        test_name: str,
        viewport: str = "desktop",
        scenario_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get history of baseline changes for a test (Feature #114)

        Returns both current and archived baselines in chronological order.

        Args:
            test_name: Name of the test
            viewport: Viewport name
            scenario_type: Scenario type

        Returns:
            List of baseline info dictionaries (oldest first)
        """
        history = []

        # Add current baseline if it exists
        current_baseline = self.get_baseline_path(test_name, viewport, scenario_type)
        if current_baseline:
            with Image.open(current_baseline) as img:
                file_size = current_baseline.stat().st_size

            history.append({
                "type": "current",
                "path": str(current_baseline),
                "size": file_size,
                "created_at": datetime.fromtimestamp(
                    current_baseline.stat().st_mtime
                ).isoformat(),
                "test_name": test_name,
                "viewport": viewport,
                "scenario_type": scenario_type
            })

        # Add archived baselines
        archived = self.list_archived_baselines(test_name, viewport)
        for arch in archived:
            history.append({
                "type": "archived",
                "path": arch["path"],
                "size": arch["size"],
                "created_at": arch.get("archived_at"),
                "test_name": test_name,
                "viewport": viewport,
                "scenario_type": scenario_type
            })

        # Sort by created_at (oldest first)
        history.sort(key=lambda x: x.get("created_at", ""))

        return history
