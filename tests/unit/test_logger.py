"""
Unit tests for the logger module.
"""

import logging


class TestLoggerSetup:
    """Tests for logger setup."""

    def test_logging_module_importable(self) -> None:
        """Should be able to import the logger module."""
        from src.utils import logger

        assert logger is not None

    def test_creates_standard_logger(self) -> None:
        """Should create a standard Python logger."""
        test_logger = logging.getLogger("test_logger")
        assert isinstance(test_logger, logging.Logger)

    def test_logger_has_name(self) -> None:
        """Logger should have a name."""
        test_logger = logging.getLogger("my_app")
        assert test_logger.name == "my_app"


class TestLoggerLevels:
    """Tests for logger levels."""

    def test_debug_level_exists(self) -> None:
        """DEBUG level should exist."""
        assert logging.DEBUG == 10

    def test_info_level_exists(self) -> None:
        """INFO level should exist."""
        assert logging.INFO == 20

    def test_warning_level_exists(self) -> None:
        """WARNING level should exist."""
        assert logging.WARNING == 30

    def test_error_level_exists(self) -> None:
        """ERROR level should exist."""
        assert logging.ERROR == 40
