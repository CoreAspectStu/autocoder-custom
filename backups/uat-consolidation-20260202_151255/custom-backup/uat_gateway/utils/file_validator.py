"""
File Upload Validator - Security utilities for validating uploaded files

This module provides comprehensive file upload validation to prevent:
- Malicious file uploads
- Executable files
- Files with dangerous extensions
- Files exceeding size limits
- MIME type mismatches
- Files containing malicious content

Feature #217: UAT gateway validates file uploads
"""

import os
import logging
from typing import List, Optional, Tuple, Set, Dict, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from uat_gateway.utils.logger import get_logger

# Try to import python-magic for MIME type detection
# If not available, validation will still work but without MIME type checking
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
    logging.warning("python-magic not installed - MIME type detection will be limited")


class FileValidationError(Exception):
    """Raised when file validation fails"""
    pass


class FileSecurityLevel(Enum):
    """Security strictness levels for file uploads"""
    PERMISSIVE = 1  # Allow most file types
    MODERATE = 2    # Standard security (default)
    STRICT = 3      # High security - minimal allowed types

    def __ge__(self, other):
        if isinstance(other, FileSecurityLevel):
            return self.value >= other.value
        return self.value >= other


@dataclass
class FileValidationResult:
    """Result of file validation"""
    is_valid: bool
    filename: str
    errors: List[str]
    warnings: List[str]
    file_info: Dict[str, Any]

    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.file_info is None:
            self.file_info = {}


class FileUploadValidator:
    """
    Validate uploaded files for security threats

    Responsibilities:
    - Check file extensions against allowlist
    - Validate MIME types match extensions
    - Enforce file size limits
    - Scan file contents for threats
    - Detect polyglot files (files with multiple formats)
    - Prevent executable uploads
    - Log security-relevant events
    """

    # Dangerous extensions that should NEVER be allowed
    DANGEROUS_EXTENSIONS = {
        # Executables
        '.exe', '.dll', '.so', '.dylib', '.app', '.deb', '.rpm',
        '.bat', '.cmd', '.sh', '.bash', '.ps1', '.vbs', '.js', '.jar',
        # Scripts
        '.pl', '.py', '.rb', '.php', '.asp', '.aspx', '.jsp', '.cgi',
        # Documents with macros
        '.doc', '.docm', '.dotm', '.xls', '.xlsm', '.xltm', '.ppt', '.pptm',
        # Config files that could execute
        '.htaccess', '.htpasswd', '.ini', '.conf', '.config',
        # Other dangerous files
        '.scf', '.lnk', '.url', '.system',
    }

    # Extensions commonly used in web applications (MODERATE security)
    ALLOWED_EXTENSIONS_MODERATE = {
        # Images
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp',
        # Documents
        '.pdf', '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp',
        # Text and data
        '.txt', '.csv', '.json', '.xml', '.yaml', '.yml', '.md',
        # Archives
        '.zip', '.tar', '.gz', '.7z', '.rar',
        # Media
        '.mp4', '.mp3', '.wav', '.avi', '.mov', '.webm', '.ogg',
    }

    # Minimal allowed extensions (STRICT security)
    ALLOWED_EXTENSIONS_STRICT = {
        '.jpg', '.jpeg', '.png', '.gif', '.pdf', '.txt', '.csv'
    }

    # MIME types to extensions mapping
    # Note: text/plain can include .txt, .csv, .md, and other text formats
    # libmagic often returns text/plain for simple text files
    MIME_TYPE_MAP = {
        'image/jpeg': ['.jpg', '.jpeg'],
        'image/png': ['.png'],
        'image/gif': ['.gif'],
        'image/webp': ['.webp'],
        'image/svg+xml': ['.svg'],
        'image/x-icon': ['.ico'],
        'image/bmp': ['.bmp'],
        'application/pdf': ['.pdf'],
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
        'text/plain': ['.txt', '.csv', '.md'],  # Include CSV and markdown as text/plain
        'text/csv': ['.csv'],
        'application/json': ['.json'],
        'application/xml': ['.xml'],
        'text/xml': ['.xml'],
        'application/x-yaml': ['.yaml', '.yml'],
        'text/markdown': ['.md'],
        'application/zip': ['.zip'],
        'application/x-tar': ['.tar'],
        'application/gzip': ['.gz'],
        'application/x-7z-compressed': ['.7z'],
        'application/x-rar-compressed': ['.rar'],
        'video/mp4': ['.mp4'],
        'audio/mpeg': ['.mp3'],
        'audio/wav': ['.wav'],
        'video/x-msvideo': ['.avi'],
        'video/quicktime': ['.mov'],
        'video/webm': ['.webm'],
        'audio/ogg': ['.ogg'],
    }

    # Maximum file sizes (in bytes)
    MAX_FILE_SIZE_PERMISSIVE = 50 * 1024 * 1024  # 50MB
    MAX_FILE_SIZE_MODERATE = 10 * 1024 * 1024    # 10MB
    MAX_FILE_SIZE_STRICT = 2 * 1024 * 1024       # 2MB

    # Signatures of malicious files (magic bytes)
    MALICIOUS_SIGNATURES = {
        # PE executable (Windows)
        b'MZ': ['.exe', '.dll', '.sys', '.scr'],
        # ELF executable (Linux)
        b'\x7fELF': ['.so', '.bin'],
        # Mach-O executable (macOS)
        b'\xfe\xed\xfa': ['.dylib', '.bundle'],
        b'\xce\xfa\xed\xfe': ['.dylib', '.bundle'],
        b'\xca\xfe\xba\xbe': ['.class'],
        # Java archive
        b'PK\x03\x04': ['.jar', '.zip'],  # ZIP format, need to check extension
        # Script files (check content)
    }

    def __init__(
        self,
        security_level: FileSecurityLevel = FileSecurityLevel.MODERATE,
        custom_allowed_extensions: Optional[Set[str]] = None,
        custom_max_size: Optional[int] = None
    ):
        """
        Initialize the file upload validator

        Args:
            security_level: How strict to be with validation
            custom_allowed_extensions: Override default allowed extensions
            custom_max_size: Override default max file size
        """
        self.logger = get_logger("file_validator")
        self.security_level = security_level
        self.custom_allowed_extensions = custom_allowed_extensions
        self.custom_max_size = custom_max_size

        # Initialize python-magic for MIME type detection
        self.magic = None
        if MAGIC_AVAILABLE:
            try:
                self.magic = magic.Magic(mime=True)
                self.logger.info("MIME type detection enabled")
            except Exception as e:
                self.logger.warning(f"Failed to initialize python-magic: {e}")
        else:
            self.logger.warning("python-magic not available - MIME type detection disabled")

    def validate_file(
        self,
        file_path: str,
        filename: str,
        check_content: bool = True
    ) -> FileValidationResult:
        """
        Validate an uploaded file

        Args:
            file_path: Path to the uploaded file on disk
            filename: Original filename of the uploaded file
            check_content: Whether to scan file contents (slower but more secure)

        Returns:
            FileValidationResult with validation status and details
        """
        result = FileValidationResult(
            is_valid=False,
            filename=filename,
            errors=[],
            warnings=[],
            file_info={}
        )

        try:
            # Basic file info
            if not os.path.exists(file_path):
                result.errors.append("File does not exist on disk")
                return result

            file_size = os.path.getsize(file_path)
            result.file_info['size'] = file_size
            result.file_info['path'] = file_path

            # Extract file extension
            file_ext = self._get_file_extension(filename)
            result.file_info['extension'] = file_ext

            # Step 1: Check for dangerous extensions
            if self._is_dangerous_extension(file_ext):
                result.errors.append(
                    f"File extension '{file_ext}' is not allowed for security reasons"
                )
                self.logger.warning(
                    f"[SECURITY] Blocked dangerous file extension: {file_ext} "
                    f"in file: {filename}"
                )
                return result

            # Step 2: Check if extension is allowed
            allowed_extensions = self._get_allowed_extensions()
            if file_ext.lower() not in allowed_extensions:
                result.errors.append(
                    f"File extension '{file_ext}' is not allowed. "
                    f"Allowed extensions: {', '.join(sorted(allowed_extensions))}"
                )
                self.logger.warning(
                    f"[SECURITY] Blocked disallowed file extension: {file_ext} "
                    f"in file: {filename}"
                )
                return result

            # Step 3: Check file size
            max_size = self._get_max_file_size()
            if file_size > max_size:
                result.errors.append(
                    f"File size {file_size} bytes exceeds maximum allowed {max_size} bytes"
                )
                self.logger.warning(
                    f"[SECURITY] Blocked oversized file: {filename} "
                    f"({file_size} > {max_size} bytes)"
                )
                return result

            # Step 4: Validate MIME type
            if self.magic:
                detected_mime = self._detect_mime_type(file_path)
                result.file_info['detected_mime_type'] = detected_mime

                # Check if MIME type matches extension
                mime_valid, mime_error = self._validate_mime_type_extension(
                    detected_mime, file_ext
                )

                if not mime_valid:
                    result.errors.append(mime_error)
                    self.logger.warning(
                        f"[SECURITY] MIME type mismatch in file: {filename} "
                        f"(detected: {detected_mime}, extension: {file_ext})"
                    )
                    return result

            # Step 5: Scan file contents for threats
            if check_content:
                content_valid, content_errors = self._scan_file_contents(
                    file_path, file_ext
                )

                if not content_valid:
                    result.errors.extend(content_errors)
                    self.logger.warning(
                        f"[SECURITY] Malicious content detected in file: {filename}"
                    )
                    return result

            # All checks passed
            result.is_valid = True
            self.logger.info(f"File validation passed: {filename}")

        except Exception as e:
            result.errors.append(f"Validation error: {str(e)}")
            self.logger.error(f"Error validating file {filename}: {e}")

        return result

    def _get_file_extension(self, filename: str) -> str:
        """Extract file extension from filename"""
        return os.path.splitext(filename)[1].lower()

    def _is_dangerous_extension(self, ext: str) -> bool:
        """Check if extension is in dangerous list"""
        return ext.lower() in self.DANGEROUS_EXTENSIONS

    def _get_allowed_extensions(self) -> Set[str]:
        """Get allowed extensions based on security level"""
        if self.custom_allowed_extensions:
            return self.custom_allowed_extensions

        if self.security_level == FileSecurityLevel.PERMISSIVE:
            return self.ALLOWED_EXTENSIONS_MODERATE | {
                '.doc', '.docm', '.xls', '.xlsm', '.ppt'
            }
        elif self.security_level == FileSecurityLevel.STRICT:
            return self.ALLOWED_EXTENSIONS_STRICT
        else:  # MODERATE
            return self.ALLOWED_EXTENSIONS_MODERATE

    def _get_max_file_size(self) -> int:
        """Get maximum file size based on security level"""
        if self.custom_max_size:
            return self.custom_max_size

        if self.security_level == FileSecurityLevel.PERMISSIVE:
            return self.MAX_FILE_SIZE_PERMISSIVE
        elif self.security_level == FileSecurityLevel.STRICT:
            return self.MAX_FILE_SIZE_STRICT
        else:  # MODERATE
            return self.MAX_FILE_SIZE_MODERATE

    def _detect_mime_type(self, file_path: str) -> Optional[str]:
        """Detect MIME type of file using libmagic"""
        try:
            if self.magic:
                return self.magic.from_file(file_path)
        except Exception as e:
            self.logger.warning(f"Failed to detect MIME type: {e}")
        return None

    def _validate_mime_type_extension(
        self,
        mime_type: Optional[str],
        extension: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that detected MIME type matches file extension

        This prevents extension spoofing attacks (e.g., renaming .exe to .jpg)
        """
        if not mime_type:
            # Could not detect MIME type - allow but warn
            return True, None

        # Get expected extensions for this MIME type
        expected_extensions = self.MIME_TYPE_MAP.get(mime_type, [])

        if not expected_extensions:
            # Unknown MIME type - allow but warn
            return True, None

        # Check if the actual extension matches expected
        if extension.lower() not in expected_extensions:
            # MIME type doesn't match extension
            return False, (
                f"File extension '{extension}' does not match detected "
                f"MIME type '{mime_type}'. Expected extensions: {expected_extensions}"
            )

        return True, None

    def _scan_file_contents(
        self,
        file_path: str,
        extension: str
    ) -> Tuple[bool, List[str]]:
        """
        Scan file contents for malicious signatures

        Args:
            file_path: Path to file
            extension: File extension (for context)

        Returns:
            Tuple of (is_safe, list_of_errors)
        """
        errors = []

        try:
            # Read first 16 bytes for magic number detection
            with open(file_path, 'rb') as f:
                header = f.read(16)

            # Check against malicious signatures
            for signature, dangerous_exts in self.MALICIOUS_SIGNATURES.items():
                if header.startswith(signature):
                    # This signature might be legitimate for some file types
                    if extension.lower() in dangerous_exts:
                        errors.append(
                            f"File contains executable signature matching '{dangerous_exts}' "
                            f"file format. This may be a disguised executable."
                        )

            # Additional content checks based on file type
            if extension in ['.svg', '.xml', '.html']:
                # Check for SVG/XML exploits
                self._check_svg_xml_exploits(file_path, errors)

            elif extension in ['.jpg', '.jpeg', '.png', '.gif']:
                # Check for image file exploits (polyglot files)
                self._check_image_exploits(file_path, errors)

        except Exception as e:
            self.logger.warning(f"Error scanning file contents: {e}")

        return len(errors) == 0, errors

    def _check_svg_xml_exploits(self, file_path: str, errors: List[str]):
        """Check SVG/XML files for script injection and other exploits"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(10000)  # Read first 10KB

            # Check for dangerous patterns
            dangerous_patterns = [
                '<script',
                'javascript:',
                'onload=',
                'onerror=',
                'eval(',
                'document.',
                'window.',
                '<iframe',
                '<embed',
                '<object',
            ]

            for pattern in dangerous_patterns:
                if pattern.lower() in content.lower():
                    errors.append(
                        f"File contains potentially dangerous content: '{pattern}'"
                    )
                    break

        except Exception as e:
            self.logger.warning(f"Error checking SVG/XML exploits: {e}")

    def _check_image_exploits(self, file_path: str, errors: List[str]):
        """Check image files for polyglot file attacks"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(32)

            # Check for polyglot files (files with multiple format signatures)
            # This is a simplified check - production systems should use more robust tools
            image_signatures = {
                b'\xff\xd8\xff': 'JPEG',
                b'\x89PNG\r\n\x1a\n': 'PNG',
                b'GIF87a': 'GIF',
                b'GIF89a': 'GIF',
            }

            found_formats = []
            for sig, fmt in image_signatures.items():
                if header.startswith(sig):
                    found_formats.append(fmt)

            if len(found_formats) == 0:
                errors.append("File does not appear to be a valid image")

        except Exception as e:
            self.logger.warning(f"Error checking image exploits: {e}")


# Singleton instance for convenient access
_default_validator = None


def get_file_validator(
    security_level: FileSecurityLevel = FileSecurityLevel.MODERATE
) -> FileUploadValidator:
    """Get the default file validator instance"""
    global _default_validator
    if _default_validator is None:
        _default_validator = FileUploadValidator(security_level=security_level)
    return _default_validator


def validate_uploaded_file(
    file_path: str,
    filename: str,
    security_level: FileSecurityLevel = FileSecurityLevel.MODERATE
) -> Tuple[bool, List[str]]:
    """
    Convenience function to validate an uploaded file

    Args:
        file_path: Path to uploaded file
        filename: Original filename
        security_level: Security strictness level

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    validator = get_file_validator(security_level)
    result = validator.validate_file(file_path, filename)
    return result.is_valid, result.errors
