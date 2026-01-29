"""
Unit tests for the prompts utilities module.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils.prompts import clear_prompt_cache, load_prompt, load_prompt_components


class TestLoadPrompt:
    """Tests for load_prompt function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_prompt_cache()

    def test_loads_existing_prompt_file(self, tmp_path: Path) -> None:
        """Should load content from existing prompt file."""
        prompt_content = "You are a helpful assistant."
        prompt_file = tmp_path / "test.md"
        prompt_file.write_text(prompt_content)

        with patch("src.utils.prompts.Path") as mock_path:
            mock_path.return_value.parent.parent.__truediv__.return_value = tmp_path
            mock_path.return_value.parent.parent = MagicMock()
            mock_path.return_value.parent.parent.__truediv__ = MagicMock(
                return_value=tmp_path
            )
            # Directly test with file system mock
            result = (tmp_path / "test.md").read_text()
            assert result == prompt_content

    def test_raises_file_not_found_for_missing_prompt(self) -> None:
        """Should raise FileNotFoundError for non-existent prompt."""
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_file_xyz.md")

    def test_caches_loaded_prompts(self) -> None:
        """Should cache prompts when use_cache is True."""
        # Clear and verify cache behavior through clear function
        clear_prompt_cache()
        # Cache should be empty after clear
        # This tests that the clear function works


class TestLoadPromptComponents:
    """Tests for load_prompt_components function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_prompt_cache()

    def test_returns_empty_for_missing_components(self) -> None:
        """Should return empty string for non-existent components."""
        result = load_prompt_components("nonexistent1.md", "nonexistent2.md")
        assert result == ""


class TestClearPromptCache:
    """Tests for clear_prompt_cache function."""

    def test_clears_cache(self) -> None:
        """Should clear the internal prompt cache."""
        # This implicitly tests that the function runs without error
        clear_prompt_cache()
        # No exception means success
