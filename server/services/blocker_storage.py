"""
Secure Blocker Storage

Encrypted storage for API keys and sensitive credentials.
Uses Fernet symmetric encryption for per-project credential storage.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    from cryptography.fernet import Fernet
    FERNET_AVAILABLE = True
except ImportError:
    FERNET_AVAILABLE = False


@dataclass
class StoredCredential:
    """A stored API key or credential"""
    service: str
    key_name: str
    encrypted_value: str
    created_at: str
    last_used: Optional[str] = None


class SecureBlockerStorage:
    """
    Encrypted storage for API keys and credentials.

    Credentials are stored per-project in:
    ~/.autocoder/uat_gateway/{project_name}/credentials.enc

    Each project has its own encryption key stored in:
    ~/.autocoder/uat_gateway/{project_name}/.key
    """

    def __init__(self, project_name: str):
        if not FERNET_AVAILABLE:
            raise RuntimeError(
                "cryptography package not available. "
                "Install with: pip install cryptography"
            )

        self.project_name = project_name
        self.storage_dir = Path.home() / ".autocoder" / "uat_gateway" / project_name
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # Load or create encryption key
        self._init_encryption()

    def _init_encryption(self):
        """Initialize encryption key for this project"""
        key_path = self.storage_dir / ".key"

        if key_path.exists():
            self.key = key_path.read_bytes()
        else:
            # Generate new key
            self.key = Fernet.generate_key()
            key_path.write_bytes(self.key)
            key_path.chmod(0o600)  # Owner read/write only

        self.cipher = Fernet(self.key)
        self.credentials_file = self.storage_dir / "credentials.enc"

    def store_credential(self, service: str, key_name: str, value: str) -> None:
        """
        Store an API key encrypted.

        Args:
            service: Service name (stripe, twilio, etc.)
            key_name: Name of the key (STRIPE_SECRET_KEY, etc.)
            value: The actual key/credential value
        """
        creds = self._load_credentials()

        # Encrypt the value
        encrypted_value = self.cipher.encrypt(value.encode()).decode()

        # Store or update
        creds[f"{service}.{key_name}"] = StoredCredential(
            service=service,
            key_name=key_name,
            encrypted_value=encrypted_value,
            created_at=datetime.now().isoformat()
        )

        self._save_credentials(creds)

    def get_credential(self, service: str, key_name: str) -> Optional[str]:
        """
        Retrieve and decrypt an API key.

        Args:
            service: Service name
            key_name: Name of the key

        Returns:
            The decrypted credential value, or None if not found
        """
        creds = self._load_credentials()
        key = f"{service}.{key_name}"

        if key not in creds:
            return None

        cred = creds[key]
        decrypted = self.cipher.decrypt(cred.encrypted_value.encode()).decode()

        # Update last_used time
        cred.last_used = datetime.now().isoformat()
        self._save_credentials(creds)

        return decrypted

    def list_credentials(self) -> List[Dict]:
        """
        List all stored credentials (without exposing values).

        Returns:
            List of credential metadata
        """
        creds = self._load_credentials()

        return [
            {
                "service": cred.service,
                "key_name": cred.key_name,
                "created_at": cred.created_at,
                "last_used": cred.last_used
            }
            for cred in creds.values()
        ]

    def delete_credential(self, service: str, key_name: str) -> bool:
        """
        Delete a stored credential.

        Args:
            service: Service name
            key_name: Name of the key

        Returns:
            True if deleted, False if not found
        """
        creds = self._load_credentials()
        key = f"{service}.{key_name}"

        if key not in creds:
            return False

        del creds[key]
        self._save_credentials(creds)
        return True

    def inject_into_env(self, project_path: str, additional_vars: Dict[str, str] = None) -> Path:
        """
        Inject stored credentials into a test environment file.

        Creates or updates .env.test with stored credentials.

        Args:
            project_path: Path to the project directory
            additional_vars: Additional environment variables to include

        Returns:
            Path to the created/updated .env.test file
        """
        project_path = Path(project_path)
        env_file = project_path / ".env.test"

        # Load existing .env.test if it exists
        env_vars = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    key, val = line.split("=", 1)
                    env_vars[key.strip()] = val.strip()

        # Add all stored credentials
        creds = self._load_credentials()
        for cred in creds.values():
            # Decrypt and add to env
            value = self.cipher.decrypt(cred.encrypted_value.encode()).decode()
            env_vars[cred.key_name] = value

        # Add any additional variables
        if additional_vars:
            env_vars.update(additional_vars)

        # Write .env.test file
        with open(env_file, 'w') as f:
            f.write("# Auto-generated by UAT AutoCoder\n")
            f.write(f"# Generated: {datetime.now().isoformat()}\n")
            f.write("# DO NOT commit this file to version control\n")
            f.write("\n")
            for key, val in env_vars.items():
                f.write(f"{key}={val}\n")

        # Set restrictive permissions
        env_file.chmod(0o600)

        return env_file

    def _load_credentials(self) -> Dict[str, StoredCredential]:
        """Load credentials from storage"""
        if not self.credentials_file.exists():
            return {}

        try:
            with open(self.credentials_file, 'r') as f:
                data = json.load(f)

            # Convert dict back to StoredCredential objects
            return {
                key: StoredCredential(**value)
                for key, value in data.items()
            }
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save_credentials(self, creds: Dict[str, StoredCredential]) -> None:
        """Save credentials to storage"""
        # Convert to dict for JSON serialization
        data = {
            key: {
                "service": cred.service,
                "key_name": cred.key_name,
                "encrypted_value": cred.encrypted_value,
                "created_at": cred.created_at,
                "last_used": cred.last_used
            }
            for key, cred in creds.items()
        }

        with open(self.credentials_file, 'w') as f:
            json.dump(data, f, indent=2)

        # Set restrictive permissions
        self.credentials_file.chmod(0o600)


# Convenience function to get storage for a project
def get_storage(project_name: str) -> SecureBlockerStorage:
    """Get SecureBlockerStorage instance for a project"""
    return SecureBlockerStorage(project_name)
