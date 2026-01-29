"""
Configuration Management.

Loads and provides access to application configuration from config.yaml.
"""

import logging
from pathlib import Path
from typing import Any, cast

import yaml

from src.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

_config: dict[str, Any] = {}


def load_config() -> dict[str, Any]:
    """
    Load the YAML configuration file from the project root.

    Returns:
        Configuration dictionary.

    Raises:
        ConfigurationError: If the config file is not found or invalid.
    """
    if not CONFIG_PATH.exists():
        raise ConfigurationError(
            "Configuration file not found", details=str(CONFIG_PATH)
        )

    try:
        content = CONFIG_PATH.read_text(encoding="utf-8")
        return cast(dict[str, Any], yaml.safe_load(content))
    except yaml.YAMLError as e:
        raise ConfigurationError("Invalid YAML configuration", details=str(e)) from e


def _initialize_config() -> None:
    """Initialize the global configuration on module load."""
    global _config
    try:
        _config = load_config()
    except ConfigurationError as e:
        logger.warning("Could not load config.yaml: %s", e)
        _config = {}


def get_settings() -> dict[str, Any]:
    """
    Get the current application settings.

    Returns:
        Configuration dictionary (may be empty if config failed to load).
    """
    return _config


def reload_config() -> dict[str, Any]:
    """
    Reload configuration from disk.

    Returns:
        Updated configuration dictionary.
    """
    global _config
    _config = load_config()
    return _config


# Initialize on module import
_initialize_config()
