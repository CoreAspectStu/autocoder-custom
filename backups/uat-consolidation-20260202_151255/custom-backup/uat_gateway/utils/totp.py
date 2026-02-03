"""
Two-Factor Authentication (2FA) / TOTP Utilities

This module provides Time-based One-Time Password (TOTP) functionality
for implementing two-factor authentication using the RFC 6238 standard.

Compatible with Google Authenticator, Authy, and other TOTP apps.
"""

import base64
import hashlib
import hmac
import os
import secrets
from typing import List, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

# Try to import qrcode, but make it optional
try:
    import qrcode
    import io
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("qrcode library not installed. QR code generation will be disabled.")

logger = logging.getLogger(__name__)


@dataclass
class TOTPSetup:
    """Contains data for setting up TOTP"""
    secret: str
    qr_code_url: str
    backup_codes: List[str]
    issuer: str
    qr_code_image: Optional[bytes] = None  # PNG bytes or None if not available


class TOTPAuthenticator:
    """
    TOTP (Time-based One-Time Password) authenticator

    Implements RFC 6238 TOTP algorithm compatible with Google Authenticator,
    Authy, Microsoft Authenticator, and other 2FA apps.
    """

    # TOTP configuration
    DIGITS = 6  # Number of digits in code (usually 6)
    PERIOD = 30  # Time period in seconds (usually 30)
    ISSUER = "UAT Gateway"  # App name shown in authenticator app

    def __init__(self, digits: int = DIGITS, period: int = PERIOD, issuer: str = ISSUER):
        """
        Initialize TOTP authenticator

        Args:
            digits: Number of digits in OTP code (default: 6)
            period: Time step in seconds (default: 30)
            issuer: Issuer name for authenticator app (default: "UAT Gateway")
        """
        self.digits = digits
        self.period = period
        self.issuer = issuer

    def generate_secret(self) -> str:
        """
        Generate a new random TOTP secret

        Returns:
            Base32-encoded secret key (typically 160 bits)
        """
        # Generate 20 random bytes (160 bits)
        secret_bytes = secrets.token_bytes(20)

        # Encode as base32 (easy for humans to type)
        secret_b32 = base64.b32encode(secret_bytes).decode('utf-8')

        logger.info(f"Generated new TOTP secret: {secret_b32[:10]}...")

        return secret_b32

    def generate_backup_codes(self, count: int = 10) -> List[str]:
        """
        Generate backup codes for recovery when 2FA device unavailable

        Args:
            count: Number of backup codes to generate (default: 10)

        Returns:
            List of backup code strings
        """
        codes = []

        for _ in range(count):
            # Generate 8-byte random code
            code_bytes = secrets.token_bytes(8)

            # Encode as hex and format nicely (XXXX-XXXX-XXXX-XXXX)
            code_hex = code_bytes.hex().upper()
            formatted_code = '-'.join([code_hex[i:i+4] for i in range(0, len(code_hex), 4)])

            codes.append(formatted_code)

        logger.info(f"Generated {count} backup codes")

        return codes

    def get_provisioning_uri(self, username: str, secret: str) -> str:
        """
        Generate the provisioning URI for QR code

        This URI is used by authenticator apps to scan and add the TOTP secret.

        Format: otpauth://totp/ISSUER:USERNAME?secret=SECRET&issuer=ISSUER&digits=DIGITS&period=PERIOD

        Args:
            username: Username/identifier
            secret: Base32-encoded TOTP secret

        Returns:
            otpauth:// URI string
        """
        uri = (
            f"otpauth://totp/{self.issuer}:{username}?"
            f"secret={secret}&"
            f"issuer={self.issuer}&"
            f"digits={self.digits}&"
            f"period={self.period}"
        )

        logger.debug(f"Generated provisioning URI for user '{username}'")

        return uri

    def generate_qr_code(self, provisioning_uri: str) -> Optional[bytes]:
        """
        Generate QR code image from provisioning URI

        Args:
            provisioning_uri: otpauth:// URI string

        Returns:
            QR code image as PNG bytes, or None if qrcode not available
        """
        if not QRCODE_AVAILABLE:
            logger.warning("QR code generation requested but qrcode library not available")
            return None

        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )

        qr.add_data(provisioning_uri)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to PNG bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        logger.debug("Generated QR code for provisioning URI")

        return img_bytes.read()

    def generate_totp(self, secret: str, timestamp: Optional[datetime] = None) -> str:
        """
        Generate TOTP code for given secret at given time

        Implements RFC 6238 algorithm:
        1. Calculate time step counter: floor(timestamp / period)
        2. HMAC-SHA1(secret, counter)
        3. Dynamic truncation
        4. Modulo 10^digits

        Args:
            secret: Base32-encoded TOTP secret
            timestamp: Time to generate code for (default: now)

        Returns:
            TOTP code as string
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # Decode base32 secret
        try:
            secret_bytes = base64.b32decode(secret, casefold=True)
        except Exception as e:
            logger.error(f"Failed to decode TOTP secret: {e}")
            raise ValueError("Invalid TOTP secret")

        # Calculate time step counter
        time_counter = int(timestamp.timestamp() // self.period)

        # Convert counter to bytes (8 bytes, big-endian)
        counter_bytes = time_counter.to_bytes(8, byteorder='big')

        # HMAC-SHA1(secret, counter)
        hmac_hash = hmac.new(secret_bytes, counter_bytes, hashlib.sha1).digest()

        # Dynamic truncation
        offset = hmac_hash[-1] & 0x0f
        code_bytes = hmac_hash[offset:offset + 4]

        # Remove sign bit
        code_int = int.from_bytes(code_bytes, byteorder='big') & 0x7fffffff

        # Extract digits
        totp_code = str(code_int % (10 ** self.digits)).zfill(self.digits)

        logger.debug(f"Generated TOTP code: {totp_code}")

        return totp_code

    def verify_totp(
        self,
        secret: str,
        code: str,
        timestamp: Optional[datetime] = None,
        window: int = 1
    ) -> bool:
        """
        Verify TOTP code against secret

        Allows for time drift by checking adjacent time windows.

        Args:
            secret: Base32-encoded TOTP secret
            code: TOTP code to verify
            timestamp: Time to verify at (default: now)
            window: Number of time windows to check (default: 1, meaning ±30 seconds)

        Returns:
            True if code is valid, False otherwise
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        # Normalize code
        code = code.strip().zfill(self.digits)

        # Check current time window and adjacent windows
        for i in range(-window, window + 1):
            # Calculate time for this window
            window_time = timestamp + timedelta(seconds=i * self.period)

            # Generate expected code
            expected_code = self.generate_totp(secret, window_time)

            # Compare
            if code == expected_code:
                logger.info(f"TOTP code verified successfully (window: {i})")
                return True

        logger.warning(f"TOTP code verification failed")

        return False

    def verify_backup_code(self, provided_code: str, stored_codes: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Verify a backup code

        Backup codes are single-use, so if valid, it should be removed from the list.

        Args:
            provided_code: Code provided by user
            stored_codes: List of valid backup codes

        Returns:
            Tuple of (is_valid, used_code) where used_code is the code if valid, None otherwise
        """
        # Normalize provided code
        provided_code = provided_code.strip().replace(' ', '').replace('-', '').upper()

        for stored_code in stored_codes:
            # Normalize stored code
            normalized_stored = stored_code.replace('-', '').upper()

            if provided_code == normalized_stored:
                logger.info("Backup code verified successfully")
                return True, stored_code

        logger.warning("Backup code verification failed")

        return False, None

    def setup_totp(self, username: str) -> TOTPSetup:
        """
        Generate complete TOTP setup data

        This creates everything needed for a user to set up 2FA:
        - Secret key
        - QR code (for scanning with authenticator app)
        - Backup codes (for recovery)

        Args:
            username: Username to set up 2FA for

        Returns:
            TOTPSetup object with secret, QR code, and backup codes
        """
        # Generate secret
        secret = self.generate_secret()

        # Generate backup codes
        backup_codes = self.generate_backup_codes(count=10)

        # Generate provisioning URI
        provisioning_uri = self.get_provisioning_uri(username, secret)

        # Generate QR code image (if qrcode available)
        qr_code_image = self.generate_qr_code(provisioning_uri)

        logger.info(f"Generated TOTP setup data for user '{username}'")

        return TOTPSetup(
            secret=secret,
            qr_code_url=provisioning_uri,
            backup_codes=backup_codes,
            issuer=self.issuer,
            qr_code_image=qr_code_image
        )


# Singleton instance
_totp_authenticator: Optional[TOTPAuthenticator] = None


def get_totp_authenticator() -> TOTPAuthenticator:
    """
    Get the global TOTP authenticator instance

    Returns:
        TOTPAuthenticator instance
    """
    global _totp_authenticator

    if _totp_authenticator is None:
        _totp_authenticator = TOTPAuthenticator()

    return _totp_authenticator


def generate_test_code(secret: str, timestamp: Optional[datetime] = None) -> str:
    """
    Helper function to generate a valid TOTP code for testing

    Args:
        secret: TOTP secret
        timestamp: Time to generate code for (default: now)

    Returns:
        Valid TOTP code
    """
    authenticator = get_totp_authenticator()
    return authenticator.generate_totp(secret, timestamp)
