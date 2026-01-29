# Prompt Loading Utilities
"""
Shared utility functions for loading prompt files.
Centralizes prompt loading logic to avoid duplication across agents.
"""

from pathlib import Path

# Cache for loaded prompts to avoid repeated file I/O
_prompt_cache: dict[str, str] = {}


def load_prompt(filename: str, use_cache: bool = True) -> str:
    """
    Load a prompt file from the prompts directory.

    Args:
        filename: Name of the prompt file (e.g., 'planner.md')
        use_cache: Whether to cache the loaded prompt (default: True)

    Returns:
        The contents of the prompt file as a string.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist.
    """
    if use_cache and filename in _prompt_cache:
        return _prompt_cache[filename]

    prompts_dir = Path(__file__).parent.parent / "prompts"
    path = prompts_dir / filename

    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    content = path.read_text(encoding="utf-8")

    if use_cache:
        _prompt_cache[filename] = content

    return content


def load_prompt_components(*components: str) -> str:
    """
    Load and concatenate multiple prompt component files.

    Args:
        *components: Variable number of component filenames
                     (e.g., 'identity.md', 'rules.md')

    Returns:
        Concatenated contents of all component files.
    """
    prompts_dir = Path(__file__).parent.parent / "prompts" / "components"
    parts: list[str] = []

    for comp in components:
        cache_key = f"components/{comp}"
        if cache_key in _prompt_cache:
            parts.append(_prompt_cache[cache_key])
            continue

        path = prompts_dir / comp
        if path.exists():
            content = path.read_text(encoding="utf-8")
            _prompt_cache[cache_key] = content
            parts.append(content)

    return "\n\n".join(parts)


def clear_prompt_cache() -> None:
    """Clear the prompt cache (useful for testing or hot-reloading)."""
    _prompt_cache.clear()
