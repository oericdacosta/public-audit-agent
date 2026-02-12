"""
TCE API Client - Optimized.

HTTP client for fetching data from the TCE (Tribunal de Contas) APIs.
Uses session pooling for connection reuse, rate limiting and circuit breaker.
"""

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Optional, cast

import aiohttp
import pybreaker

from src.config import get_settings
from src.etl.endpoints import APIBase, Endpoint

logger = logging.getLogger(__name__)


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

    # Default HTTP headers for API requests
    DEFAULT_HEADERS = {
        "User-Agent": "CivicAudit-ETL/1.0 (Public Audit Agent)",
        "Accept": "application/json",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    }

    def __init__(self, rate_limit: Optional[int] = None) -> None:
        """
        Initialize Async Client.
        Args:
            rate_limit: Max concurrent requests. If None, uses config.
        """
        settings = get_settings()
        tce_config = settings.get("tce", {})
        self.BASE_URL = tce_config.get("base_url", "")
        self.SIM_BASE_URL = tce_config.get("sim_base_url", "")

        # Rate Limit Logic
        # Priority: Explicit Arg > Config (Mandatory via KeyError)
        config_limit = tce_config["rate_limit"]
        final_limit = rate_limit if rate_limit is not None else config_limit

        self.semaphore = asyncio.Semaphore(final_limit)
        logger.debug(f"AsyncTCEClient initialized with rate_limit={final_limit}")

        # Session state
        self._session: Optional[aiohttp.ClientSession] = None

        # Circuit breaker Configuration (Mandatory from config)
        fail_max = tce_config["circuit_fail_max"]
        reset_timeout = tce_config["circuit_reset_timeout"]

        self._circuit_breaker = AsyncCircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
        )

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create the shared aiohttp session."""
        if self._session is None or self._session.closed:
            # No limit on pool size (governed by semaphore)
            # ttl_dns_cache=300 to reduce DNS lookups
            connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=60, sock_connect=10)

            self._session = aiohttp.ClientSession(
                connector=connector, headers=self.DEFAULT_HEADERS, timeout=timeout
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
