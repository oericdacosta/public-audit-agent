"""
TCE API Client.

HTTP client for fetching data from the TCE (Tribunal de Contas) APIs.
"""

import logging
import time
from typing import Any, Optional, cast

import requests

from src.config import get_settings

logger = logging.getLogger(__name__)


class TCEClient:
    """
    HTTP client for TCE public data APIs.

    Provides retry logic and timeout handling for API requests.
    """

    def __init__(self) -> None:
        """Initialize the TCE client with configured URLs."""
        settings = get_settings()
        tce_config = settings.get("tce", {})
        self.BASE_URL = tce_config.get("base_url")
        self.SIM_BASE_URL = tce_config.get("sim_base_url")

    def fetch_json(
        self, url: str, params: dict[str, Any], timeout: int = 20, retries: int = 3
    ) -> Optional[dict[str, Any]]:
        """
        Fetch JSON data from a URL with retry logic.

        Args:
            url: API endpoint URL.
            params: Query parameters.
            timeout: Request timeout in seconds.
            retries: Number of retry attempts.

        Returns:
            Parsed JSON response or None if all attempts fail.
        """
        for attempt in range(retries):
            try:
                response = requests.get(url, params=params, timeout=timeout)

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return cast(dict[str, Any], response.json())

            except requests.exceptions.RequestException as e:
                logger.warning(
                    "Request failed (attempt %d/%d): %s", attempt + 1, retries, e
                )
                time.sleep(1 * (attempt + 1))

        logger.error("Failed to fetch %s after %d attempts.", url, retries)
        return None
