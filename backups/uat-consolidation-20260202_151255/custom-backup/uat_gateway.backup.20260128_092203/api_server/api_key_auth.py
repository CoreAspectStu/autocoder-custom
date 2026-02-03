"""
API Key Authentication for UAT Gateway API

Implements API key-based authentication for API endpoints.
Supports key generation, validation, and revocation.
"""

import os
import secrets
import hashlib
import hmac
from datetime import datetime
from typing import Optional, Dict, List, Set
from dataclasses import dataclass, field
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class APIKey:
    """API Key data structure"""
    key_id: str
    name: str
    hashed_key: str
    created_at: datetime
    last_used: Optional[datetime] = None
    is_active: bool = True
    scopes: List[str] = field(default_factory=list)

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert to dictionary (excluding sensitive data by default)"""
        data = {
            "key_id": self.key_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "is_active": self.is_active,
            "scopes": self.scopes
        }
        if include_sensitive:
            data["hashed_key"] = self.hashed_key
        return data


@dataclass
class APIKeyConfig:
    """Configuration for API key authentication"""
    enable_api_key_auth: bool = True
    key_prefix: str = "uatk_"  # UAT Gateway Key prefix
    key_length: int = 32  # Length of random portion
    storage_file: str = "api_keys.json"


class APIKeyAuthenticator:
    """
    API Key-based authentication for API endpoints

    Features:
    - Secure API key generation with prefix
    - Key hashing for storage (never store plaintext keys)
    - Key validation and authentication
    - Key revocation/deactivation
    - File-based persistence (can be extended to database)
    """

    def __init__(
        self,
        enable_api_key_auth: bool = True,
        key_prefix: str = "uatk_",
        storage_file: Optional[str] = None
    ):
        """
        Initialize API key authenticator

        Args:
            enable_api_key_auth: Whether to enable API key auth
            key_prefix: Prefix for generated keys (e.g., "uatk_")
            storage_file: File to store API keys (default: api_keys.json in project root)
        """
        self.config = APIKeyConfig(
            enable_api_key_auth=enable_api_key_auth,
            key_prefix=key_prefix,
            storage_file=storage_file or os.path.join(os.getcwd(), "api_keys.json")
        )

        # In-memory storage for API keys
        # Format: {key_id: APIKey}
        self._api_keys: Dict[str, APIKey] = {}

        # Reverse lookup: hashed_key -> key_id
        self._key_hash_lookup: Dict[str, str] = {}

        # Load existing keys from storage
        self._load_keys()

        logger.info(f"API key authenticator initialized (loaded {len(self._api_keys)} keys)")

    def _hash_key(self, key: str) -> str:
        """
        Hash an API key for storage

        Uses HMAC-SHA256 for secure one-way hashing

        Args:
            key: Plain text API key

        Returns:
            Hashed key
        """
        # Use a pepper (server-side secret) for additional security
        # In production, this should come from environment variable
        pepper = os.getenv("API_KEY_PEPPER", "default-pepper-change-in-production")

        # HMAC-SHA256 for key hashing
        hashed = hmac.new(
            pepper.encode(),
            key.encode(),
            hashlib.sha256
        ).hexdigest()

        return hashed

    def _generate_key_id(self) -> str:
        """Generate a unique key ID"""
        return secrets.token_hex(16)

    def _load_keys(self):
        """Load API keys from storage file"""
        try:
            if os.path.exists(self.config.storage_file):
                with open(self.config.storage_file, 'r') as f:
                    data = json.load(f)

                for key_data in data.get("api_keys", []):
                    api_key = APIKey(
                        key_id=key_data["key_id"],
                        name=key_data["name"],
                        hashed_key=key_data["hashed_key"],
                        created_at=datetime.fromisoformat(key_data["created_at"]),
                        last_used=datetime.fromisoformat(key_data["last_used"]) if key_data.get("last_used") else None,
                        is_active=key_data.get("is_active", True),
                        scopes=key_data.get("scopes", [])
                    )
                    self._api_keys[api_key.key_id] = api_key
                    self._key_hash_lookup[api_key.hashed_key] = api_key.key_id

                logger.info(f"Loaded {len(self._api_keys)} API keys from storage")
        except Exception as e:
            logger.error(f"Error loading API keys from storage: {e}")
            # Continue with empty storage

    def _save_keys(self):
        """Save API keys to storage file"""
        try:
            data = {
                "api_keys": [
                    api_key.to_dict(include_sensitive=True)
                    for api_key in self._api_keys.values()
                ],
                "updated_at": datetime.now().isoformat()
            }

            with open(self.config.storage_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self._api_keys)} API keys to storage")
        except Exception as e:
            logger.error(f"Error saving API keys to storage: {e}")

    def generate_api_key(
        self,
        name: str,
        scopes: Optional[List[str]] = None
    ) -> str:
        """
        Generate a new API key

        Args:
            name: Descriptive name for the key (e.g., "Production API", "Testing Script")
            scopes: List of scopes/permissions (optional, default: full access)

        Returns:
            The generated API key (format: prefix + random string)
            NOTE: This is the only time the full key is returned - store it securely!
        """
        # Generate random portion
        random_part = secrets.token_urlsafe(self.config.key_length)

        # Combine with prefix
        full_key = f"{self.config.key_prefix}{random_part}"

        # Hash the key for storage
        hashed_key = self._hash_key(full_key)

        # Create API key record
        key_id = self._generate_key_id()
        api_key = APIKey(
            key_id=key_id,
            name=name,
            hashed_key=hashed_key,
            created_at=datetime.now(),
            scopes=scopes or ["read", "write", "admin"]
        )

        # Store in memory
        self._api_keys[key_id] = api_key
        self._key_hash_lookup[hashed_key] = key_id

        # Persist to storage
        self._save_keys()

        logger.info(f"Generated new API key '{name}' (ID: {key_id})")

        # Return the full key (only time it's visible!)
        return full_key

    def validate_api_key(self, key: str, update_last_used: bool = True) -> Optional[APIKey]:
        """
        Validate an API key

        Args:
            key: API key to validate
            update_last_used: Whether to update last_used timestamp

        Returns:
            APIKey object if valid, None otherwise
        """
        if not self.config.enable_api_key_auth:
            logger.debug("API key authentication disabled")
            return None

        # Hash the provided key
        hashed_key = self._hash_key(key)

        # Look up the key
        key_id = self._key_hash_lookup.get(hashed_key)
        if not key_id:
            logger.warning(f"Invalid API key provided (hash not found)")
            return None

        # Get the API key record
        api_key = self._api_keys.get(key_id)
        if not api_key:
            logger.warning(f"API key record not found for ID: {key_id}")
            return None

        # Check if key is active
        if not api_key.is_active:
            logger.warning(f"API key '{api_key.name}' is inactive (ID: {key_id})")
            return None

        # Update last used timestamp
        if update_last_used:
            api_key.last_used = datetime.now()
            self._save_keys()

        logger.debug(f"API key validated successfully: '{api_key.name}' (ID: {key_id})")
        return api_key

    def revoke_api_key(self, key_id: str) -> bool:
        """
        Revoke (deactivate) an API key

        Args:
            key_id: ID of the key to revoke

        Returns:
            True if revoked successfully, False otherwise
        """
        api_key = self._api_keys.get(key_id)
        if not api_key:
            logger.warning(f"Cannot revoke non-existent key: {key_id}")
            return False

        api_key.is_active = False
        self._save_keys()

        logger.info(f"Revoked API key '{api_key.name}' (ID: {key_id})")
        return True

    def delete_api_key(self, key_id: str) -> bool:
        """
        Permanently delete an API key

        Args:
            key_id: ID of the key to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        api_key = self._api_keys.get(key_id)
        if not api_key:
            logger.warning(f"Cannot delete non-existent key: {key_id}")
            return False

        # Remove from lookup
        self._key_hash_lookup.pop(api_key.hashed_key, None)

        # Remove from storage
        del self._api_keys[key_id]

        # Persist
        self._save_keys()

        logger.info(f"Deleted API key '{api_key.name}' (ID: {key_id})")
        return True

    def list_api_keys(self, include_inactive: bool = False) -> List[Dict[str, any]]:
        """
        List all API keys

        Args:
            include_inactive: Whether to include inactive keys

        Returns:
            List of API key dictionaries (without sensitive data)
        """
        keys = []
        for api_key in self._api_keys.values():
            if include_inactive or api_key.is_active:
                keys.append(api_key.to_dict(include_sensitive=False))

        return keys

    def get_api_key(self, key_id: str) -> Optional[Dict[str, any]]:
        """
        Get details of a specific API key

        Args:
            key_id: ID of the key

        Returns:
            API key dictionary (without sensitive data), or None
        """
        api_key = self._api_keys.get(key_id)
        if not api_key:
            return None

        return api_key.to_dict(include_sensitive=False)


def create_api_key_authenticator() -> APIKeyAuthenticator:
    """
    Create an API key authenticator with default configuration

    Returns:
        APIKeyAuthenticator instance
    """
    return APIKeyAuthenticator()
