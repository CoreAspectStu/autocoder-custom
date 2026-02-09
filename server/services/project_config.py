"""
Project Configuration Service
=============================

Handles project type detection and dev command configuration.
Detects project types by scanning for configuration files and provides
default or custom dev commands for each project.

Configuration is stored in {project_dir}/.autoforge/config.json.
"""

import json
import logging
from pathlib import Path
from typing import TypedDict

# Python 3.11+ has tomllib in the standard library
try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# =============================================================================
# Path Validation
# =============================================================================


def _validate_project_dir(project_dir: Path) -> Path:
    """
    Validate and resolve the project directory.

    Args:
        project_dir: Path to the project directory.

    Returns:
        Resolved Path object.

    Raises:
        ValueError: If project_dir is not a valid directory.
    """
    resolved = Path(project_dir).resolve()

    if not resolved.exists():
        raise ValueError(f"Project directory does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"Path is not a directory: {resolved}")

    return resolved

# =============================================================================
# Type Definitions
# =============================================================================


class ProjectConfig(TypedDict):
    """Full project configuration response."""
    detected_type: str | None
    detected_command: str | None
    custom_command: str | None
    effective_command: str | None
    assigned_port: int | None


# =============================================================================
# Project Type Definitions
# =============================================================================

# Port range for remote dev servers (SSH tunnel friendly)
DEVSERVER_PORT_MIN = 4000
DEVSERVER_PORT_MAX = 4099

# Mapping of project types to their default dev command templates
# {port} placeholder will be replaced with assigned port
PROJECT_TYPE_COMMANDS: dict[str, str] = {
    "nodejs-vite": "npm run dev -- --port {port}",
    "nodejs-cra": "PORT={port} npm start",
    "python-poetry": "poetry run python -m uvicorn main:app --reload --port {port}",
    "python-django": "python manage.py runserver {port}",
    "python-fastapi": "python -m uvicorn main:app --reload --port {port}",
    "rust": "cargo run",  # Port depends on app implementation
    "go": "go run .",      # Port depends on app implementation
}


# =============================================================================
# Configuration File Handling
# =============================================================================


def _get_config_path(project_dir: Path) -> Path:
    """
    Get the path to the project config file.

    Checks the new .autoforge/ location first, falls back to .autocoder/
    for backward compatibility.

    Args:
        project_dir: Path to the project directory.

    Returns:
        Path to the config.json file in the appropriate directory.
    """
    new_path = project_dir / ".autoforge" / "config.json"
    if new_path.exists():
        return new_path
    old_path = project_dir / ".autocoder" / "config.json"
    if old_path.exists():
        return old_path
    return new_path


def _load_config(project_dir: Path) -> dict:
    """
    Load the project configuration from disk.

    Args:
        project_dir: Path to the project directory.

    Returns:
        Configuration dictionary, or empty dict if file doesn't exist or is invalid.
    """
    config_path = _get_config_path(project_dir)

    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        if not isinstance(config, dict):
            logger.warning(
                "Invalid config format in %s: expected dict, got %s",
                config_path, type(config).__name__
            )
            return {}

        return config

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse config at %s: %s", config_path, e)
        return {}
    except OSError as e:
        logger.warning("Failed to read config at %s: %s", config_path, e)
        return {}


def _save_config(project_dir: Path, config: dict) -> None:
    """
    Save the project configuration to disk.

    Creates the .autoforge directory if it doesn't exist.

    Args:
        project_dir: Path to the project directory.
        config: Configuration dictionary to save.

    Raises:
        OSError: If the file cannot be written.
    """
    config_path = _get_config_path(project_dir)

    # Ensure the .autoforge directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        logger.debug("Saved config to %s", config_path)
    except OSError as e:
        logger.error("Failed to save config to %s: %s", config_path, e)
        raise


# =============================================================================
# Project Type Detection
# =============================================================================


def _parse_package_json(project_dir: Path) -> dict | None:
    """
    Parse package.json if it exists.

    Args:
        project_dir: Path to the project directory.

    Returns:
        Parsed package.json as dict, or None if not found or invalid.
    """
    package_json_path = project_dir / "package.json"

    if not package_json_path.exists():
        return None

    try:
        with open(package_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return None
    except (json.JSONDecodeError, OSError) as e:
        logger.debug("Failed to parse package.json in %s: %s", project_dir, e)
        return None


def _is_poetry_project(project_dir: Path) -> bool:
    """
    Check if pyproject.toml indicates a Poetry project.

    Parses pyproject.toml to look for [tool.poetry] section.
    Falls back to simple file existence check if tomllib is not available.

    Args:
        project_dir: Path to the project directory.

    Returns:
        True if pyproject.toml exists and contains Poetry configuration.
    """
    pyproject_path = project_dir / "pyproject.toml"
    if not pyproject_path.exists():
        return False

    # If tomllib is available (Python 3.11+), parse and check for [tool.poetry]
    if tomllib is not None:
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            return "poetry" in data.get("tool", {})
        except Exception:
            # If parsing fails, fall back to False
            return False

    # Fallback for older Python: simple file existence check
    # This is less accurate but provides backward compatibility
    return True


def detect_project_type(project_dir: Path) -> str | None:
    """
    Detect the project type by scanning for configuration files.

    Detection priority (first match wins):
    1. package.json with scripts.dev -> nodejs-vite
    2. package.json with scripts.start -> nodejs-cra
    3. pyproject.toml with [tool.poetry] -> python-poetry
    4. manage.py -> python-django
    5. requirements.txt + (main.py or app.py) -> python-fastapi
    6. Cargo.toml -> rust
    7. go.mod -> go

    Args:
        project_dir: Path to the project directory.

    Returns:
        Project type string (e.g., "nodejs-vite", "python-django"),
        or None if no known project type is detected.
    """
    project_dir = Path(project_dir).resolve()

    if not project_dir.exists() or not project_dir.is_dir():
        logger.debug("Project directory does not exist: %s", project_dir)
        return None

    # Check for Node.js projects (package.json)
    package_json = _parse_package_json(project_dir)
    if package_json is not None:
        scripts = package_json.get("scripts", {})
        if isinstance(scripts, dict):
            # Check for 'dev' script first (typical for Vite, Next.js, etc.)
            if "dev" in scripts:
                logger.debug("Detected nodejs-vite project in %s", project_dir)
                return "nodejs-vite"
            # Fall back to 'start' script (typical for CRA)
            if "start" in scripts:
                logger.debug("Detected nodejs-cra project in %s", project_dir)
                return "nodejs-cra"

    # Check for Python Poetry project (must have [tool.poetry] in pyproject.toml)
    if _is_poetry_project(project_dir):
        logger.debug("Detected python-poetry project in %s", project_dir)
        return "python-poetry"

    # Check for Django project
    if (project_dir / "manage.py").exists():
        logger.debug("Detected python-django project in %s", project_dir)
        return "python-django"

    # Check for Python FastAPI project (requirements.txt + main.py or app.py)
    if (project_dir / "requirements.txt").exists():
        has_main = (project_dir / "main.py").exists()
        has_app = (project_dir / "app.py").exists()
        if has_main or has_app:
            logger.debug("Detected python-fastapi project in %s", project_dir)
            return "python-fastapi"

    # Check for Rust project
    if (project_dir / "Cargo.toml").exists():
        logger.debug("Detected rust project in %s", project_dir)
        return "rust"

    # Check for Go project
    if (project_dir / "go.mod").exists():
        logger.debug("Detected go project in %s", project_dir)
        return "go"

    logger.debug("No known project type detected in %s", project_dir)
    return None


# =============================================================================
# Port Assignment Functions
# =============================================================================


def get_all_assigned_ports() -> set[int]:
    """
    Scan all .autocoder/config.json files to find assigned ports.

    This helps prevent port conflicts when assigning new ports.

    Returns:
        Set of all currently assigned ports across all projects.
    """
    import sys
    from pathlib import Path

    # Add root to path for registry import
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    try:
        from registry import list_registered_projects

        assigned_ports = set()
        projects = list_registered_projects()

        for name, info in projects.items():
            project_path = Path(info.get("path", ""))
            if not project_path.exists():
                continue

            config = _load_config(project_path)
            port = config.get("assigned_port")
            if isinstance(port, int) and DEVSERVER_PORT_MIN <= port <= DEVSERVER_PORT_MAX:
                assigned_ports.add(port)

        return assigned_ports
    except Exception as e:
        logger.warning("Failed to get assigned ports: %s", e)
        return set()


def get_next_available_port(exclude_ports: set[int] | None = None) -> int:
    """
    Find the next available port in the DEVSERVER_PORT range.

    Args:
        exclude_ports: Optional set of ports to exclude from selection.

    Returns:
        Next available port number in range 4000-4099.

    Raises:
        RuntimeError: If no ports are available in the range.
    """
    if exclude_ports is None:
        exclude_ports = set()

    # Combine with all currently assigned ports
    assigned = get_all_assigned_ports()
    exclude_ports = exclude_ports | assigned

    for port in range(DEVSERVER_PORT_MIN, DEVSERVER_PORT_MAX + 1):
        if port not in exclude_ports:
            return port

    raise RuntimeError(f"No available ports in range {DEVSERVER_PORT_MIN}-{DEVSERVER_PORT_MAX}")


def get_assigned_port(project_dir: Path) -> int:
    """
    Get or assign a port for this project.

    If the project already has an assigned port in config, return it.
    Otherwise, assign the next available port and save it to config.

    Args:
        project_dir: Path to the project directory.

    Returns:
        The assigned port number for this project.

    Raises:
        RuntimeError: If no ports are available.
    """
    project_dir = Path(project_dir).resolve()

    # Check if port is already assigned
    config = _load_config(project_dir)
    existing_port = config.get("assigned_port")

    if isinstance(existing_port, int) and DEVSERVER_PORT_MIN <= existing_port <= DEVSERVER_PORT_MAX:
        logger.debug("Using existing port %d for %s", existing_port, project_dir.name)
        return existing_port

    # Assign new port
    new_port = get_next_available_port()
    config["assigned_port"] = new_port

    try:
        _save_config(project_dir, config)
        logger.info("Assigned port %d to project %s", new_port, project_dir.name)
    except OSError as e:
        logger.error("Failed to save port assignment for %s: %s", project_dir.name, e)
        # Still return the port even if save failed

    return new_port


def set_assigned_port(project_dir: Path, port: int) -> None:
    """
    Set the assigned port for a project.

    Args:
        project_dir: Path to the project directory.
        port: The port number to assign (must be in range 4000-4099).

    Raises:
        ValueError: If port is not in valid range or is already assigned to another project.
        OSError: If the configuration file cannot be written.
    """
    project_dir = Path(project_dir).resolve()

    # Validate port range
    if not isinstance(port, int) or not (DEVSERVER_PORT_MIN <= port <= DEVSERVER_PORT_MAX):
        raise ValueError(
            f"Port must be between {DEVSERVER_PORT_MIN} and {DEVSERVER_PORT_MAX}, got {port}"
        )

    # Check if port is already assigned to a different project
    config = _load_config(project_dir)
    current_port = config.get("assigned_port")

    # If changing to a different port, check for conflicts
    if current_port != port:
        assigned_ports = get_all_assigned_ports()
        if port in assigned_ports:
            raise ValueError(
                f"Port {port} is already assigned to another project"
            )

    # Update and save config
    config["assigned_port"] = port
    _save_config(project_dir, config)
    logger.info("Set port %d for project %s", port, project_dir.name)


# =============================================================================
# Dev Command Functions
# =============================================================================


def get_default_dev_command(project_dir: Path) -> str | None:
    """
    Get the auto-detected dev command for a project with assigned port.

    This returns the default command based on detected project type,
    with {port} placeholder replaced with the project's assigned port.

    Args:
        project_dir: Path to the project directory.

    Returns:
        Default dev command string for the detected project type with port,
        or None if no project type is detected.
    """
    project_type = detect_project_type(project_dir)

    if project_type is None:
        return None

    command_template = PROJECT_TYPE_COMMANDS.get(project_type)
    if not command_template:
        return None

    # If command has {port} placeholder, replace it with assigned port
    if "{port}" in command_template:
        try:
            assigned_port = get_assigned_port(project_dir)
            return command_template.format(port=assigned_port)
        except RuntimeError as e:
            logger.error("Failed to assign port for %s: %s", project_dir, e)
            # Return command without port replacement
            return command_template

    return command_template


def get_dev_command(project_dir: Path) -> str | None:
    """
    Get the effective dev command for a project.

    Returns the custom command if one is configured,
    otherwise returns the auto-detected default command.

    Args:
        project_dir: Path to the project directory.

    Returns:
        The effective dev command (custom if set, else detected),
        or None if neither is available.
    """
    project_dir = Path(project_dir).resolve()

    # Check for custom command first
    config = _load_config(project_dir)
    custom_command = config.get("dev_command")

    if custom_command and isinstance(custom_command, str):
        # Type is narrowed to str by isinstance check
        result: str = custom_command
        return result

    # Fall back to auto-detected command
    return get_default_dev_command(project_dir)


def set_dev_command(project_dir: Path, command: str) -> None:
    """
    Save a custom dev command for a project.

    Args:
        project_dir: Path to the project directory.
        command: The custom dev command to save.

    Raises:
        ValueError: If command is empty or not a string, or if project_dir is invalid.
        OSError: If the config file cannot be written.
    """
    if not command or not isinstance(command, str):
        raise ValueError("Command must be a non-empty string")

    project_dir = _validate_project_dir(project_dir)

    # Load existing config and update
    config = _load_config(project_dir)
    config["dev_command"] = command

    _save_config(project_dir, config)
    logger.info("Set custom dev command for %s: %s", project_dir.name, command)


def clear_dev_command(project_dir: Path) -> None:
    """
    Remove the custom dev command, reverting to auto-detection.

    If no config file exists or no custom command is set,
    this function does nothing (no error is raised).

    Args:
        project_dir: Path to the project directory.

    Raises:
        ValueError: If project_dir is not a valid directory.
    """
    project_dir = _validate_project_dir(project_dir)
    config_path = _get_config_path(project_dir)

    if not config_path.exists():
        return

    config = _load_config(project_dir)

    if "dev_command" not in config:
        return

    del config["dev_command"]

    # If config is now empty, delete the file
    if not config:
        try:
            config_path.unlink(missing_ok=True)
            logger.info("Removed empty config file for %s", project_dir.name)

            # Also remove .autoforge directory if empty
            autoforge_dir = config_path.parent
            if autoforge_dir.exists() and not any(autoforge_dir.iterdir()):
                autoforge_dir.rmdir()
                logger.debug("Removed empty .autoforge directory for %s", project_dir.name)
        except OSError as e:
            logger.warning("Failed to clean up config for %s: %s", project_dir.name, e)
    else:
        _save_config(project_dir, config)

    logger.info("Cleared custom dev command for %s", project_dir.name)


def get_project_config(project_dir: Path) -> ProjectConfig:
    """
    Get the full project configuration including detection results.

    This provides all relevant configuration information in a single call,
    useful for displaying in a UI or debugging.

    Args:
        project_dir: Path to the project directory.

    Returns:
        ProjectConfig dict with:
        - detected_type: The auto-detected project type (or None)
        - detected_command: The default command for detected type (or None)
        - custom_command: The user-configured custom command (or None)
        - effective_command: The command that would actually be used (or None)
        - assigned_port: The assigned port for this project (or None)

    Raises:
        ValueError: If project_dir is not a valid directory.
    """
    project_dir = _validate_project_dir(project_dir)

    # Detect project type and get default command (with port)
    detected_type = detect_project_type(project_dir)
    detected_command = get_default_dev_command(project_dir) if detected_type else None

    # Load custom command and assigned port from config
    config = _load_config(project_dir)
    custom_command = config.get("dev_command")
    assigned_port = config.get("assigned_port")

    # Validate custom_command is a string
    if not isinstance(custom_command, str):
        custom_command = None

    # Validate assigned_port is an int in valid range
    if not isinstance(assigned_port, int) or not (DEVSERVER_PORT_MIN <= assigned_port <= DEVSERVER_PORT_MAX):
        assigned_port = None

    # Determine effective command
    effective_command = custom_command if custom_command else detected_command

    return ProjectConfig(
        detected_type=detected_type,
        detected_command=detected_command,
        custom_command=custom_command,
        effective_command=effective_command,
        assigned_port=assigned_port,
    )
