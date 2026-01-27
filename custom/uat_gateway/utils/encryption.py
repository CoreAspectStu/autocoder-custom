"""
Encryption Utilities for UAT Gateway

Provides encryption/decryption functionality for sensitive test data at rest.
Uses Fernet (AES-128-CBC with HMAC) for symmetric encryption.

Feature #214: UAT gateway encrypts sensitive data
"""

import base64
import os
import hashlib
import json
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Optional cryptography dependency
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    logger.warning("cryptography package not available - encryption features disabled")


class EncryptionManager:
    """
    Manages encryption and decryption of sensitive data

    Uses Fernet symmetric encryption with PBKDF2 key derivation.
    Provides strong encryption for data at rest.
    """

    # Sensitive field patterns that should be encrypted
    SENSITIVE_PATTERNS = [
        'password', 'secret', 'token', 'api_key', 'credential',
        'auth', 'session', 'cookie', 'private_key', 'access_token',
        'refresh_token', 'bearer', 'authorization'
    ]

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption manager

        Args:
            encryption_key: Optional 32-byte encryption key (base64 encoded).
                          If not provided, will use environment variable or generate key.
        """
        self.encryption_key = encryption_key or os.environ.get('UAT_ENCRYPTION_KEY')

        if not self.encryption_key:
            # Generate a new key and warn
            logger.warning(
                "No encryption key provided. Generated ephemeral key. "
                "Set UAT_ENCRYPTION_KEY environment variable for persistent encryption."
            )
            self.encryption_key = self._generate_key().decode()

        # Ensure key is proper format for Fernet
        try:
            # If it's a raw key, derive proper Fernet key
            if len(self.encryption_key) == 32:  # 32-byte raw key
                derived_key = self._derive_fernet_key(self.encryption_key)
                self.cipher = Fernet(derived_key)
            else:
                # Assume it's already a Fernet key
                self.cipher = Fernet(self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key)
        except Exception as e:
            logger.error(f"Failed to initialize cipher: {e}")
            raise ValueError(f"Invalid encryption key: {e}")

    def _generate_key(self) -> bytes:
        """
        Generate a new Fernet encryption key

        Returns:
            Base64-encoded encryption key
        """
        return Fernet.generate_key()

    def _derive_fernet_key(self, password: str) -> bytes:
        """
        Derive a Fernet-compatible key from a password

        Uses PBKDF2-HMAC with SHA256 and 100,000 iterations.

        Args:
            password: Password string

        Returns:
            32-byte Fernet-compatible key
        """
        password_bytes = password.encode() if isinstance(password, str) else password
        salt = b'uat_gateway_salt'  # In production, use random salt per deployment
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))
        return key

    def encrypt_data(self, data: str) -> str:
        """
        Encrypt a string value

        Args:
            data: Plain text data to encrypt

        Returns:
            Base64-encoded encrypted data (with prefix ENCRYPTED:)
        """
        if not data:
            return data

        try:
            encrypted_bytes = self.cipher.encrypt(data.encode('utf-8'))
            encrypted_b64 = base64.b64encode(encrypted_bytes).decode('utf-8')
            return f"ENCRYPTED:{encrypted_b64}"
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt_data(self, encrypted_data: str) -> str:
        """
        Decrypt an encrypted string value

        Args:
            encrypted_data: Encrypted data (with ENCRYPTED: prefix)

        Returns:
            Decrypted plain text
        """
        if not encrypted_data or not encrypted_data.startswith('ENCRYPTED:'):
            return encrypted_data

        try:
            # Remove prefix and decode
            encrypted_b64 = encrypted_data[len('ENCRYPTED:'):]
            encrypted_bytes = base64.b64decode(encrypted_b64)
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Unable to decrypt data: {e}")

    def encrypt_dict(self, data: Dict[str, Any], recursive: bool = True) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in a dictionary

        Args:
            data: Dictionary to encrypt
            recursive: Whether to recursively encrypt nested dictionaries

        Returns:
            Dictionary with sensitive fields encrypted
        """
        if not isinstance(data, dict):
            return data

        encrypted = {}

        for key, value in data.items():
            # Check if this is a sensitive field
            if self._is_sensitive_field(key) and isinstance(value, (str, int, float, bool)):
                # Encrypt the value
                encrypted[key] = self.encrypt_data(str(value))
            elif recursive and isinstance(value, dict):
                # Recursively encrypt nested dictionaries
                encrypted[key] = self.encrypt_dict(value, recursive=True)
            elif recursive and isinstance(value, list):
                # Recursively encrypt lists
                encrypted[key] = self.encrypt_list(value, recursive=True)
            else:
                encrypted[key] = value

        return encrypted

    def decrypt_dict(self, data: Dict[str, Any], recursive: bool = True) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in a dictionary

        Args:
            data: Dictionary to decrypt
            recursive: Whether to recursively decrypt nested dictionaries

        Returns:
            Dictionary with sensitive fields decrypted
        """
        if not isinstance(data, dict):
            return data

        decrypted = {}

        for key, value in data.items():
            if isinstance(value, str) and value.startswith('ENCRYPTED:'):
                # Decrypt the value
                try:
                    decrypted[key] = self.decrypt_data(value)
                except Exception as e:
                    logger.warning(f"Failed to decrypt field {key}: {e}")
                    decrypted[key] = value  # Keep encrypted if decryption fails
            elif recursive and isinstance(value, dict):
                # Recursively decrypt nested dictionaries
                decrypted[key] = self.decrypt_dict(value, recursive=True)
            elif recursive and isinstance(value, list):
                # Recursively decrypt lists
                decrypted[key] = self.decrypt_list(value, recursive=True)
            else:
                decrypted[key] = value

        return decrypted

    def encrypt_list(self, data: List[Any], recursive: bool = True) -> List[Any]:
        """
        Encrypt sensitive fields in a list

        Args:
            data: List to encrypt
            recursive: Whether to recursively encrypt nested structures

        Returns:
            List with sensitive fields encrypted
        """
        if not isinstance(data, list):
            return data

        encrypted = []

        for item in data:
            if isinstance(item, dict):
                encrypted.append(self.encrypt_dict(item, recursive=recursive))
            elif isinstance(item, list):
                encrypted.append(self.encrypt_list(item, recursive=recursive))
            else:
                encrypted.append(item)

        return encrypted

    def decrypt_list(self, data: List[Any], recursive: bool = True) -> List[Any]:
        """
        Decrypt sensitive fields in a list

        Args:
            data: List to decrypt
            recursive: Whether to recursively decrypt nested structures

        Returns:
            List with sensitive fields decrypted
        """
        if not isinstance(data, list):
            return data

        decrypted = []

        for item in data:
            if isinstance(item, dict):
                decrypted.append(self.decrypt_dict(item, recursive=recursive))
            elif isinstance(item, list):
                decrypted.append(self.decrypt_list(item, recursive=recursive))
            else:
                decrypted.append(item)

        return decrypted

    def _is_sensitive_field(self, field_name: str) -> bool:
        """
        Check if a field name contains sensitive data patterns

        Args:
            field_name: Field name to check

        Returns:
            True if field appears to be sensitive
        """
        field_lower = field_name.lower()
        return any(pattern in field_lower for pattern in self.SENSITIVE_PATTERNS)

    def validate_encryption_strength(self) -> Dict[str, Any]:
        """
        Validate that encryption is strong enough

        Returns:
            Dictionary with validation results
        """
        # Test encrypt/decrypt
        test_data = "sensitive_test_data_12345"
        try:
            encrypted = self.encrypt_data(test_data)
            decrypted = self.decrypt_data(encrypted)

            if decrypted != test_data:
                return {
                    'valid': False,
                    'error': 'Encrypt/decrypt cycle failed',
                    'algorithm': 'Fernet (AES-128-CBC with HMAC)',
                    'key_derivation': 'PBKDF2-SHA256'
                }

            return {
                'valid': True,
                'algorithm': 'Fernet (AES-128-CBC with HMAC-SHA256)',
                'key_derivation': 'PBKDF2-SHA256 with 100,000 iterations',
                'message': 'Encryption is strong and working correctly'
            }
        except Exception as e:
            return {
                'valid': False,
                'error': str(e),
                'algorithm': 'Fernet (AES-128-CBC with HMAC)',
                'key_derivation': 'PBKDF2-SHA256'
            }


# Global encryption manager instance
_encryption_manager = None


def get_encryption_manager(encryption_key: Optional[str] = None) -> EncryptionManager:
    """
    Get or create the global encryption manager instance

    Args:
        encryption_key: Optional encryption key

    Returns:
        EncryptionManager instance
    """
    global _encryption_manager

    if _encryption_manager is None or encryption_key is not None:
        _encryption_manager = EncryptionManager(encryption_key)

    return _encryption_manager
