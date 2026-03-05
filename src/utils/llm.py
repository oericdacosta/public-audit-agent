"""
LLM Factory Utilities.

Centralized LLM instance management with caching and configuration.
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from src.config import get_settings


@lru_cache(maxsize=8)
def get_llm(
    model_key: str,
    temperature: float = 0.0,
    fallback_model: str = "gpt-4o",
    timeout: int = 60,
) -> ChatOpenAI:
    """
    Get a cached LLM instance by configuration key.

    Uses LRU cache to avoid creating multiple instances of the same model.

    Args:
        model_key: Configuration key under 'agent' section (e.g., 'fiscal_model').
        temperature: Model temperature for response randomness (default: 0.0).
        fallback_model: Model to use if key not found in config.
        timeout: HTTP request timeout in seconds (default: 60). Prevents hung
            LLM calls from blocking the graph indefinitely.

    Returns:
        Configured ChatOpenAI instance.

    Example:
        llm = get_llm("fiscal_model")
        llm = get_llm("guardrail_model", temperature=0.0, timeout=30)
    """
    settings = get_settings()
    model_name = settings.get("agent", {}).get(model_key, fallback_model)
    return ChatOpenAI(model=model_name, temperature=temperature, timeout=timeout)


def clear_llm_cache() -> None:
    """Clear the LLM instance cache (useful for testing or config reload)."""
    get_llm.cache_clear()
