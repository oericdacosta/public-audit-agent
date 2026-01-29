"""
Unit tests for the parsing utilities module.
"""

from src.utils.parsing import clean_markdown_code


class TestCleanMarkdownCode:
    """Tests for clean_markdown_code function."""

    def test_extracts_python_code_block(self) -> None:
        """Should extract code from a python code block."""
        content = """Here is some code:
```python
def hello():
    return "world"
```
"""
        result = clean_markdown_code(content)
        assert result == 'def hello():\n    return "world"'

    def test_extracts_code_block_without_language(self) -> None:
        """Should extract code from a code block without language specifier."""
        content = """```
SELECT * FROM table
```"""
        result = clean_markdown_code(content)
        assert "FROM table" in result

    def test_returns_plain_content_without_code_blocks(self) -> None:
        """Should return content as-is when no code blocks found."""
        content = "Just some plain text"
        result = clean_markdown_code(content)
        assert result == "Just some plain text"

    def test_prioritizes_matching_language(self) -> None:
        """Should prioritize the code block with matching language."""
        content = """```python
python_code
```

```sql
SELECT * FROM t
```
"""
        result = clean_markdown_code(content, language="sql")
        assert result == "SELECT * FROM t"

    def test_returns_first_block_when_language_not_found(self) -> None:
        """Should return first block when specified language not found."""
        content = """```python
def foo():
    pass
```"""
        result = clean_markdown_code(content, language="javascript")
        assert "def foo():" in result

    def test_handles_empty_content(self) -> None:
        """Should handle empty content."""
        result = clean_markdown_code("")
        assert result == ""

    def test_handles_content_with_only_whitespace(self) -> None:
        """Should handle whitespace-only content."""
        result = clean_markdown_code("   \n   ")
        assert result == ""
