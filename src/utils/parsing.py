def clean_markdown_code(content: str) -> str:
    """
    Strips markdown code block formatting (```python ... ```) from a string.
    Useful for cleaning LLM outputs before execution.
    """
    content = content.strip()
    if content.startswith("```python"):
        content = content[9:]
    elif content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    return content.strip()
