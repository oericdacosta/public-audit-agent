"""
Unit tests for the utils/llm module.
"""

from unittest.mock import MagicMock, patch

from src.utils.llm import clear_llm_cache, get_llm


class TestGetLlm:
    """Tests for get_llm function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_llm_cache()

    @patch("src.utils.llm.get_settings")
    @patch("src.utils.llm.ChatOpenAI")
    def test_creates_openai_model(
        self, mock_openai: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Should create a ChatOpenAI model."""
        mock_settings.return_value = {"agent": {"fiscal_model": "gpt-4o"}}
        mock_openai.return_value = MagicMock()

        get_llm("fiscal_model")
        mock_openai.assert_called_once()

    @patch("src.utils.llm.get_settings")
    @patch("src.utils.llm.ChatOpenAI")
    def test_uses_fallback_model(
        self, mock_openai: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Should use fallback model when key not found."""
        mock_settings.return_value = {"agent": {}}
        mock_openai.return_value = MagicMock()

        get_llm("nonexistent_model", fallback_model="gpt-3.5-turbo")
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["model"] == "gpt-3.5-turbo"

    @patch("src.utils.llm.get_settings")
    @patch("src.utils.llm.ChatOpenAI")
    def test_passes_temperature(
        self, mock_openai: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Should pass temperature to the constructor."""
        mock_settings.return_value = {"agent": {}}
        mock_openai.return_value = MagicMock()

        get_llm("test_model", temperature=0.7)
        call_kwargs = mock_openai.call_args[1]
        assert call_kwargs["temperature"] == 0.7


class TestClearLlmCache:
    """Tests for clear_llm_cache function."""

    def test_clears_cache_without_error(self) -> None:
        """Should clear cache without raising an error."""
        # Just test it runs without error
        clear_llm_cache()
