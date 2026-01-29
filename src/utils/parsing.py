"""
Code parsing utilities.

Functions for cleaning and extracting code from LLM outputs.
"""

import re
from typing import Optional


def clean_markdown_code(content: str, language: Optional[str] = None) -> str:
    """
    Extract code from markdown code blocks.
    
    Handles various formats:
    - ```python\\ncode```
    - ```\\ncode```
    - ``` python\\ncode``` (with space)
    - Plain code without blocks
    
    Args:
        content: Raw LLM output potentially containing code blocks.
        language: Optional language to prioritize (e.g., 'python', 'sql').
    
    Returns:
        Extracted code without markdown formatting.
    """
    content = content.strip()
    
    # Pattern to match code blocks with optional language specifier
    pattern = r"```(?:\s*(\w+))?\s*\n?([\s\S]*?)```"
    matches = re.findall(pattern, content)
    
    if matches:
        if language:
            # Prioritize blocks matching the requested language
            for lang, code in matches:
                if lang and lang.lower() == language.lower():
                    return code.strip()
        # Return the first code block found
        return matches[0][1].strip()
    
    # No code blocks found, return content as-is
    return content
