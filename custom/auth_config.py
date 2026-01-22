"""
Authentication Configuration Utility
=====================================

Manages authentication settings by updating the .env file.
This is a CUSTOM addition for flexible auth method switching.

IMPORTANT: This file is custom and may need to be reapplied after upstream updates.
See custom/docs/auth-settings-customization.md for documentation.
"""

import os
import re
from pathlib import Path


def get_env_file_path() -> Path:
    """Get the path to the .env file in the autocoder root directory."""
    # This file is in custom/auth_config.py, so go up one level to root
    root_dir = Path(__file__).parent.parent
    return root_dir / ".env"


def read_env_file() -> str:
    """Read the current .env file contents."""
    env_file = get_env_file_path()
    if env_file.exists():
        return env_file.read_text()
    return ""


def update_env_variable(key: str, value: str | None) -> None:
    """
    Update or add an environment variable in the .env file.

    Args:
        key: Environment variable name (e.g., "ANTHROPIC_AUTH_TOKEN")
        value: Value to set, or None to comment out the line
    """
    env_file = get_env_file_path()
    content = read_env_file()

    # Pattern to match the variable (commented or not)
    pattern = rf'^#?\s*{re.escape(key)}\s*=.*$'

    if value is None:
        # Comment out the line
        new_line = f"# {key}="
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
        else:
            # Add commented line at the end
            if content and not content.endswith('\n'):
                content += '\n'
            content += f"\n# {key}=\n"
    else:
        # Set or update the value
        new_line = f"{key}={value}"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
        else:
            # Add new line at the end
            if content and not content.endswith('\n'):
                content += '\n'
            content += f"\n{new_line}\n"

    # Write back to file
    env_file.write_text(content)


def get_current_auth_method() -> tuple[str, bool]:
    """
    Determine the current authentication method.

    Returns:
        Tuple of (auth_method, api_key_configured)
        - auth_method: "claude_login" or "api_key"
        - api_key_configured: True if ANTHROPIC_AUTH_TOKEN is set
    """
    # Check environment variable (takes precedence)
    api_key = os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip()

    if api_key and not api_key.startswith("#"):
        return ("api_key", True)

    # Check .env file for uncommented API key
    content = read_env_file()
    pattern = r'^ANTHROPIC_AUTH_TOKEN\s*=\s*(.+)$'
    match = re.search(pattern, content, re.MULTILINE)

    if match and match.group(1).strip():
        return ("api_key", True)

    return ("claude_login", False)


def set_auth_method(method: str, api_key: str | None = None) -> None:
    """
    Set the authentication method by updating the .env file.

    Args:
        method: "claude_login" or "api_key"
        api_key: The API key value (required if method is "api_key")
    """
    if method == "api_key":
        if not api_key:
            raise ValueError("API key is required when using api_key authentication")
        # Set the API key
        update_env_variable("ANTHROPIC_AUTH_TOKEN", api_key)
    else:
        # Comment out the API key to use Claude login
        update_env_variable("ANTHROPIC_AUTH_TOKEN", None)


def get_masked_api_key() -> str | None:
    """
    Get a masked version of the API key for display purposes.

    Returns:
        Masked key like "sk-ant-***...***xyz" or None if not configured
    """
    api_key = os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip()

    if not api_key or api_key.startswith("#"):
        # Check .env file
        content = read_env_file()
        pattern = r'^ANTHROPIC_AUTH_TOKEN\s*=\s*(.+)$'
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            api_key = match.group(1).strip()

    if not api_key or len(api_key) < 10:
        return None

    # Mask the middle part, show first 7 and last 3 characters
    return f"{api_key[:7]}...{api_key[-3:]}"
