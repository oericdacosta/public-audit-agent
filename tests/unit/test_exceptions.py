"""
Unit tests for the exceptions module.
"""

import pytest

from src.exceptions import (
    AgentError,
    CivicAuditError,
    ConfigurationError,
    DatabaseError,
    SandboxError,
    ValidationError,
)


class TestCivicAuditError:
    """Tests for the base CivicAuditError class."""

    def test_creates_error_with_message_only(self) -> None:
        """Should create error with just a message."""
        error = CivicAuditError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.details is None

    def test_creates_error_with_message_and_details(self) -> None:
        """Should create error with message and details."""
        error = CivicAuditError("Error occurred", details="More info here")
        assert str(error) == "Error occurred: More info here"
        assert error.message == "Error occurred"
        assert error.details == "More info here"

    def test_is_exception_subclass(self) -> None:
        """Should be a proper Exception subclass."""
        error = CivicAuditError("Test")
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        """Should work with try/except."""
        with pytest.raises(CivicAuditError) as exc_info:
            raise CivicAuditError("Test error", details="context")
        assert "Test error" in str(exc_info.value)


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from CivicAuditError."""
        error = ConfigurationError("Config missing")
        assert isinstance(error, CivicAuditError)

    def test_can_be_caught_as_base(self) -> None:
        """Should be catchable as CivicAuditError."""
        with pytest.raises(CivicAuditError):
            raise ConfigurationError("Missing key", details="API_KEY")


class TestDatabaseError:
    """Tests for DatabaseError."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from CivicAuditError."""
        error = DatabaseError("Connection failed")
        assert isinstance(error, CivicAuditError)


class TestSandboxError:
    """Tests for SandboxError."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from CivicAuditError."""
        error = SandboxError("Docker not running")
        assert isinstance(error, CivicAuditError)


class TestValidationError:
    """Tests for ValidationError."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from CivicAuditError."""
        error = ValidationError("Invalid input")
        assert isinstance(error, CivicAuditError)


class TestAgentError:
    """Tests for AgentError."""

    def test_inherits_from_base(self) -> None:
        """Should inherit from CivicAuditError."""
        error = AgentError("LLM call failed")
        assert isinstance(error, CivicAuditError)

    def test_has_details(self) -> None:
        """Should support details."""
        error = AgentError("Workflow failed", details="Max retries exceeded")
        assert error.details == "Max retries exceeded"
