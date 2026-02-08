"""
TCE API Client - Optimized.

HTTP client for fetching data from the TCE (Tribunal de Contas) APIs.
Uses session pooling for connection reuse, rate limiting and circuit breaker.
"""

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Any, Awaitable, Callable, Optional, cast

import aiohttp
import pybreaker
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import get_settings
from src.etl.endpoints import APIBase, Endpoint

logger = logging.getLogger(__name__)

# Rate limit: 200 requests per second (API allows up to 500)
# Rate limit: 5 requests concurrent (SAFE mode to prevent WAF blocks)
RATE_LIMIT_CALLS = 5
RATE_LIMIT_PERIOD = 1.0  # seconds

# Circuit breaker: open after 20 failures, reset after 30 seconds
CIRCUIT_FAIL_MAX = 20
CIRCUIT_RESET_TIMEOUT = 30


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
    _request_times: deque[float] = deque()

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

        # Configure connection pooling (sized for safety)
        adapter = HTTPAdapter(
            pool_connections=5,
            pool_maxsize=20,
            max_retries=retry_strategy,
        )

        session.mount("https://", adapter)
        session.mount("http://", adapter)

        logger.info("TCEClient session initialized with rate limiting")
        return session

    def _wait_for_rate_limit(self) -> None:
        """
        Enforce rate limiting: max RATE_LIMIT_CALLS per RATE_LIMIT_PERIOD.
        Thread-safe implementation that does NOT sleep while holding the lock.
        """
        while True:
            sleep_time = 0.0
            with self._rate_lock:
                now = time.time()
                # Remove requests older than the rate limit period
                while (
                    self._request_times
                    and now - self._request_times[0] >= RATE_LIMIT_PERIOD
                ):
                    self._request_times.popleft()

                if len(self._request_times) < RATE_LIMIT_CALLS:
                    # Slot available: register and proceed
                    self._request_times.append(now)
                    return
                else:
                    # Calculate sleep time and release lock before sleeping
                    sleep_time = (
                        RATE_LIMIT_PERIOD - (now - self._request_times[0]) + 0.01
                    )

            # Sleep OUTSIDE the lock so other threads aren't blocked
            if sleep_time > 0:
                time.sleep(sleep_time)

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


class AsyncCircuitBreaker:
    """Simple Async Circuit Breaker."""

    def __init__(self, fail_max: int = 5, reset_timeout: int = 60) -> None:
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.state = "closed"  # closed, open, half-open
        self.last_failure_time = 0

    async def call(
        self, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute async function with circuit breaker logic."""
        if self.state == "open":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "half-open"
            else:
                raise pybreaker.CircuitBreakerError("Circuit is open")

        try:
            result = await func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failure_count = 0
            return result
        except Exception:
            self.failure_count += 1
            self.last_failure_time = int(time.time())
            if self.failure_count >= self.fail_max:
                self.state = "open"
            raise


class AsyncTCEClient:
    """
    Async HTTP client for TCE public data APIs using aiohttp.

    Optimized for high concurrency with:
    - asyncio.Semaphore for rate limiting
    - aiohttp.TCPConnector for connection pooling
    - Single session for entire lifecycle
    """

    def __init__(self, rate_limit: int = RATE_LIMIT_CALLS) -> None:
        """
        Initialize Async Client.
        Args:
            rate_limit: Max concurrent requests allowed.
                        Note: This acts as a semaphore, not strict rate/sec,
                        but effectively limits load.
        """
        settings = get_settings()
        tce_config = settings.get("tce", {})
        self.BASE_URL = tce_config.get("base_url", "")
        self.SIM_BASE_URL = tce_config.get("sim_base_url", "")

        # Concurrency control
        self.semaphore = asyncio.Semaphore(rate_limit)

        # Session state
        self._session: Optional[aiohttp.ClientSession] = None

        # Circuit breaker (Simple async implementation)
        self._circuit_breaker = AsyncCircuitBreaker(
            fail_max=CIRCUIT_FAIL_MAX,
            reset_timeout=CIRCUIT_RESET_TIMEOUT,
        )

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create the shared aiohttp session."""
        if self._session is None or self._session.closed:
            # No limit on pool size (governed by semaphore)
            # ttl_dns_cache=300 to reduce DNS lookups
            connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=60, sock_connect=10)

            self._session = aiohttp.ClientSession(
                connector=connector, headers=TCEClient.DEFAULT_HEADERS, timeout=timeout
            )
            logger.info("AsyncTCEClient session initialized")
        return self._session

    async def close(self) -> None:
        """Close the async session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("AsyncTCEClient session closed")

    def build_url(self, endpoint: Endpoint) -> str:
        """Build full URL for endpoint."""
        if endpoint.base == APIBase.SIM:
            base = self.SIM_BASE_URL
        else:
            base = self.BASE_URL
        return f"{base.rstrip('/')}{endpoint.path}"

    async def _make_request(
        self, session: aiohttp.ClientSession, url: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute request with semaphore and error handling."""
        async with self.semaphore:
            async with session.get(url, params=params) as response:
                if response.status == 404:
                    return {}

                response.raise_for_status()
                return cast(dict[str, Any], await response.json())

    async def fetch_json(
        self, url: str, params: dict[str, Any], retries: int = 3
    ) -> Optional[dict[str, Any]]:
        """
        Fetch JSON data asynchronously with retries and circuit breaker.
        """
        session = await self.get_session()

        for attempt in range(retries + 1):
            try:
                return cast(
                    dict[str, Any] | None,
                    await self._circuit_breaker.call(
                        self._make_request, session, url, params
                    ),
                )

            except pybreaker.CircuitBreakerError:
                logger.warning("Circuit breaker open. Skipping %s", url)
                return None

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == retries:
                    logger.error(
                        "Failed to fetch %s after %d retries: %s", url, retries, e
                    )
                    return None

                # Exponential backoff: 1s, 2s, 4s...
                delay = 1 * (2**attempt)
                await asyncio.sleep(delay)

        return None

    async def fetch(
        self, endpoint: Endpoint, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Syntactic sugar for fetching a specific endpoint."""
        url = self.build_url(endpoint)
        return await self.fetch_json(url, params)
