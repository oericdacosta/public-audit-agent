"""
TCE API Client.

HTTP client for fetching data from the TCE (Tribunal de Contas) APIs.
Includes rate limiting and circuit breaker for resilience.
"""

import logging
import time
from typing import Any, Optional, cast

import pybreaker
import requests
from ratelimit import limits, sleep_and_retry

from src.config import get_settings

logger = logging.getLogger(__name__)

# Rate limit: 10 requests per second
RATE_LIMIT_CALLS = 10
RATE_LIMIT_PERIOD = 1  # seconds

# Circuit breaker: open after 5 failures, reset after 60 seconds
CIRCUIT_FAIL_MAX = 5
CIRCUIT_RESET_TIMEOUT = 60


class TCEClient:
    """
    HTTP client for TCE public data APIs.

    Provides retry logic, timeout handling, rate limiting,
    and circuit breaker for API requests.
    """

    # Default HTTP headers for API requests
    DEFAULT_HEADERS = {
        "User-Agent": "CivicAudit-ETL/1.0 (Public Audit Agent)",
        "Accept": "application/json",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    # Circuit breaker shared across all instances
    _circuit_breaker = pybreaker.CircuitBreaker(
        fail_max=CIRCUIT_FAIL_MAX,
        reset_timeout=CIRCUIT_RESET_TIMEOUT,
        name="TCEAPIBreaker",
    )

    def __init__(self) -> None:
        """Initialize the TCE client with configured URLs."""
        settings = get_settings()
        tce_config = settings.get("tce", {})
        self.BASE_URL = tce_config.get("base_url")
        self.SIM_BASE_URL = tce_config.get("sim_base_url")

    @sleep_and_retry
    @limits(calls=RATE_LIMIT_CALLS, period=RATE_LIMIT_PERIOD)
    def _rate_limited_request(
        self, url: str, params: dict[str, Any], timeout: int
    ) -> requests.Response:
        """
        Execute a rate-limited HTTP GET request.

        Args:
            url: API endpoint URL.
            params: Query parameters.
            timeout: Request timeout in seconds.

        Returns:
            Response object from requests library.
        """
        return requests.get(
            url,
            params=params,
            timeout=timeout,
            headers=self.DEFAULT_HEADERS,
        )

    def fetch_json(
        self, url: str, params: dict[str, Any], timeout: int = 20, retries: int = 3
    ) -> Optional[dict[str, Any]]:
        """
        Fetch JSON data from a URL with retry logic and resilience.

        Uses rate limiting to avoid overwhelming the API and circuit breaker
        to fail fast when the API is unavailable.

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
                response = self._circuit_breaker.call(
                    self._rate_limited_request, url, params, timeout
                )

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return cast(dict[str, Any], response.json())

            except pybreaker.CircuitBreakerError:
                logger.error("Circuit breaker is open. Skipping request to %s", url)
                return None

            except requests.exceptions.RequestException as e:
                logger.warning(
                    "Request failed (attempt %d/%d): %s", attempt + 1, retries, e
                )
                # Exponential backoff
                time.sleep(1 * (attempt + 1))

        logger.error("Failed to fetch %s after %d attempts.", url, retries)
        return None
