"""
Tests for configuration module.

Tests the settings loading and caching behavior.
"""

import pytest
from unittest.mock import patch, mock_open
import yaml


class TestGetSettings:
    """Test suite for get_settings function."""

    def test_loads_config_from_file(self):
        """Should load configuration from config.yaml file."""
        from src.config import get_settings

        # Just verify that settings can be loaded
        settings = get_settings()
        assert isinstance(settings, dict)
        assert len(settings) > 0

    def test_caches_settings(self):
        """Should cache settings after first load."""
        from src.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        # Should be the same object (cached)
        assert settings1 is settings2

    def test_contains_required_keys(self):
        """Should contain all required configuration keys."""
        from src.config import get_settings

        settings = get_settings()

        # Check required sections
        assert "agent" in settings
        assert "database" in settings
        assert "sandbox" in settings

        # Check required agent keys
        assert "analyst_model" in settings["agent"]
        assert "max_retries" in settings["agent"]
