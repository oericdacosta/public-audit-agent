"""
TCE API Client - Optimized.

HTTP client for fetching data from the TCE (Tribunal de Contas) APIs.
Uses session pooling for connection reuse, rate limiting and circuit breaker.
"""

import logging
import threading
import time
from typing import Any, Optional, cast

import pybreaker
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import get_settings
from src.etl.endpoints import APIBase, Endpoint

logger = logging.getLogger(__name__)

# Rate limit: 10 requests per second (prevents IP blocking)
RATE_LIMIT_CALLS = 10
RATE_LIMIT_PERIOD = 1.0  # seconds

# Circuit breaker: open after 5 failures, reset after 60 seconds
CIRCUIT_FAIL_MAX = 5
CIRCUIT_RESET_TIMEOUT = 60


class TCEClient:
    """
    HTTP client for TCE public data APIs.

    Uses session pooling for connection reuse, rate limiting,
    retry logic with backoff, and circuit breaker for API requests.
    """

    # Default HTTP headers for API requests
    DEFAULT_HEADERS = {
        "User-Agent": "CivicAudit-ETL/1.0 (Public Audit Agent)",
        "Accept": "application/json",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }

    # Circuit breaker shared across all instances
    _circuit_breaker = pybreaker.CircuitBreaker(
        fail_max=CIRCUIT_FAIL_MAX,
        reset_timeout=CIRCUIT_RESET_TIMEOUT,
        name="TCEAPIBreaker",
    )

    # Shared session for connection pooling
    _session: Optional[requests.Session] = None

    # Rate limiter state (thread-safe)
    _rate_lock = threading.Lock()
    _request_times: list[float] = []

    def __init__(self) -> None:
        """Initialize the TCE client with configured URLs and session."""
        settings = get_settings()
        tce_config = settings.get("tce", {})
        self.BASE_URL = tce_config.get("base_url", "")
        self.SIM_BASE_URL = tce_config.get("sim_base_url", "")

        # Initialize shared session with connection pooling
        if TCEClient._session is None:
            TCEClient._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """
        Create a session with connection pooling and retry strategy.

        Returns:
            Configured requests Session.
        """
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1.0,  # Wait 1s, 2s, 4s between retries
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        # Configure connection pooling (conservative settings)
        adapter = HTTPAdapter(
            pool_connections=5,  # Reduced from 20
            pool_maxsize=10,  # Reduced from 50
            max_retries=retry_strategy,
        )

        session.mount("https://", adapter)
        session.mount("http://", adapter)

        logger.info("TCEClient session initialized with rate limiting")
        return session

    def _wait_for_rate_limit(self) -> None:
        """
        Enforce rate limiting: max RATE_LIMIT_CALLS per RATE_LIMIT_PERIOD.
        Thread-safe implementation.
        """
        with self._rate_lock:
            now = time.time()
            # Remove requests older than the rate limit period
            self._request_times = [
                t for t in self._request_times if now - t < RATE_LIMIT_PERIOD
            ]

            if len(self._request_times) >= RATE_LIMIT_CALLS:
                # Wait until oldest request expires
                sleep_time = RATE_LIMIT_PERIOD - (now - self._request_times[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    self._request_times = self._request_times[1:]

            self._request_times.append(time.time())

    def build_url(self, endpoint: Endpoint) -> str:
        """
        Build the full URL for a given endpoint.

        Args:
            endpoint: The API endpoint enum.

        Returns:
            Full URL string.
        """
        if endpoint.base == APIBase.SIM:
            base = self.SIM_BASE_URL
        else:
            base = self.BASE_URL

        return f"{base.rstrip('/')}{endpoint.path}"

    def _make_request(
        self, url: str, params: dict[str, Any], timeout: int
    ) -> requests.Response:
        """
        Execute HTTP GET request using the shared session with rate limiting.

        Args:
            url: API endpoint URL.
            params: Query parameters.
            timeout: Request timeout in seconds.

        Returns:
            Response object from requests library.
        """
        # Enforce rate limit before making request
        self._wait_for_rate_limit()

        assert TCEClient._session is not None
        return TCEClient._session.get(url, params=params, timeout=timeout)

    def fetch_json(
        self, url: str, params: dict[str, Any], timeout: int = 30, retries: int = 3
    ) -> Optional[dict[str, Any]]:
        """
        Fetch JSON data from a URL with retry logic and resilience.

        Uses connection pooling and circuit breaker for performance and reliability.

        Args:
            url: API endpoint URL.
            params: Query parameters.
            timeout: Request timeout in seconds.
            retries: Number of retry attempts (handled by HTTPAdapter).

        Returns:
            Parsed JSON response or None if all attempts fail.
        """
        try:
            response = self._circuit_breaker.call(
                self._make_request, url, params, timeout
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return cast(dict[str, Any], response.json())

        except pybreaker.CircuitBreakerError:
            logger.error("Circuit breaker is open. Skipping request to %s", url)
            return None

        except requests.exceptions.RequestException as e:
            logger.warning("Request failed for %s: %s", url, e)
            return None

    def fetch(
        self, endpoint: Endpoint, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """
        Syntactic sugar for fetching a specific endpoint.

        Args:
            endpoint: The API endpoint definition.
            params: Query parameters.

        Returns:
            Parsed JSON or None.
        """
        url = self.build_url(endpoint)
        return self.fetch_json(url, params)

    @classmethod
    def close_session(cls) -> None:
        """Close the shared session. Call at end of ETL process."""
        if cls._session is not None:
            cls._session.close()
            cls._session = None
            logger.info("TCEClient session closed")
