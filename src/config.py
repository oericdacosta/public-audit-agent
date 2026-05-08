"""
Configuration Management.

Loads and provides access to application configuration from config.yaml.
"""

import logging
from pathlib import Path
from typing import Any, Optional, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.exceptions import ConfigurationError

# ---------------------------------------------------------------------------
# Typed configuration models — validated at startup, no behavior change for
# existing call sites (get_settings() still returns dict[str, Any]).
# ---------------------------------------------------------------------------


class _TCESettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    base_url: str
    sim_base_url: str = ""
    rate_limit: int = Field(default=5, ge=1)
    circuit_fail_max: int = Field(default=20, ge=1)
    circuit_reset_timeout: int = Field(default=30, ge=1)


class _AgentSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    analyst_model: str = "gpt-4o"
    critic_model: str = "gpt-4o-mini"
    fiscal_model: str = "gpt-4o"
    planner_model: str = "gpt-4o"
    guardrail_model: str = "gpt-4o-mini"
    editor_model: str = "gpt-4o-mini"
    max_retries: int = Field(default=3, ge=1, le=10)
    recursion_limit: int = Field(default=30, ge=5)


class _DatabaseSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str = "data/civic_audit.duckdb"
    query_timeout: int = Field(default=30, ge=5, le=300)


class _SandboxSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    image: str = "python:3.12-slim"
    timeout: int = Field(default=30, ge=5, le=120)
    memory_limit: str = "512m"


class _LangfuseSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    host: str = "https://cloud.langfuse.com"
    flush_at: int = Field(default=15, ge=1)
    flush_interval: float = Field(default=0.5, gt=0)


class _AppSettings(BaseModel):
    """Top-level configuration model. Validates config.yaml at startup."""

    model_config = ConfigDict(extra="ignore")
    tce: Optional[_TCESettings] = None
    agent: _AgentSettings = Field(default_factory=_AgentSettings)
    database: _DatabaseSettings = Field(default_factory=_DatabaseSettings)
    sandbox: _SandboxSettings = Field(default_factory=_SandboxSettings)
    langfuse: _LangfuseSettings = Field(default_factory=_LangfuseSettings)


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
        raw = cast(dict[str, Any], yaml.safe_load(content))
    except yaml.YAMLError as e:
        raise ConfigurationError("Invalid YAML configuration", details=str(e)) from e

    # Validate types at load time — fails early with a clear message.
    # get_settings() still returns dict[str, Any] for backward compatibility.
    try:
        _AppSettings.model_validate(raw)
    except Exception as e:
        raise ConfigurationError(
            "Configuration validation failed", details=str(e)
        ) from e

    return raw


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
