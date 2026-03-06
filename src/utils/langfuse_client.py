"""
Langfuse Client Singleton.

Provides a shared Langfuse client for observability.
Returns None when Langfuse is not configured so the rest of the
codebase degrades gracefully without any changes.
"""

import logging
import os
from functools import lru_cache
from typing import Any, Optional

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_langfuse_client() -> Optional[Any]:
    """
    Return the Langfuse singleton client, or None if not configured.

    Reads LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY from environment.
    Host is read from config.yaml langfuse.host (default: cloud.langfuse.com).

    The result is cached — subsequent calls return the same instance.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        logger.debug("Langfuse keys not set — observability disabled")
        return None

    try:
        from langfuse import Langfuse

        from src.config import get_settings

        settings = get_settings()
        lf_cfg = settings.get("langfuse", {})
        host = lf_cfg.get("host", "https://cloud.langfuse.com")

        client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            flush_at=lf_cfg.get("flush_at", 15),
            flush_interval=lf_cfg.get("flush_interval", 0.5),
        )
        logger.info("Langfuse observability enabled — host: %s", host)
        return client

    except ImportError:
        logger.warning("langfuse package not installed — observability disabled")
        return None
    except Exception as e:
        logger.warning("Langfuse init failed: %s", e)
        return None
