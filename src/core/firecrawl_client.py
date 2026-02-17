"""Firecrawl client with rate limiting and proxy support.

Firecrawl converts web pages to clean Markdown, optimized for LLMs.
Self-hosted version has no rate limits but we still need to be
gentle with target websites to avoid IP bans.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from src.core.scraper_config import (
    RateLimitConfig,
    ProxyConfig,
    HeadersConfig,
    SourceScraperConfig,
    get_source_config,
)
from src.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FirecrawlResponse:
    """Response from Firecrawl scrape."""

    success: bool
    markdown: str | None = None
    html: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def title(self) -> str | None:
        """Get page title from metadata."""
        return self.metadata.get("title")

    @property
    def description(self) -> str | None:
        """Get page description from metadata."""
        return self.metadata.get("description")


class FirecrawlClient:
    """Client for Firecrawl API with built-in rate limiting.

    Supports both cloud and self-hosted Firecrawl instances.

    Example:
        ```python
        client = FirecrawlClient("http://localhost:3002")

        # Simple scrape
        result = await client.scrape("https://example.com/events")
        print(result.markdown)

        # With source-specific config (respects rate limits)
        result = await client.scrape_with_config(
            "https://www.juntadeandalucia.es/eventos",
            source_id="andalucia_cultura"
        )
        ```
    """

    def __init__(
        self,
        base_url: str = "http://localhost:3002",
        api_key: str | None = None,
        default_rate_limit: RateLimitConfig | None = None,
    ):
        """Initialize Firecrawl client.

        Args:
            base_url: Firecrawl API URL (self-hosted or cloud)
            api_key: API key (required for cloud, optional for self-hosted)
            default_rate_limit: Default rate limiting config
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_rate_limit = default_rate_limit or RateLimitConfig()

        # Track last request time per domain
        self._last_request_time: dict[str, float] = {}

        # Track backoff level per domain (increases on 429/403)
        self._backoff_level: dict[str, int] = {}

        # HTTP client
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),  # Firecrawl can take time
                headers=headers,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL for rate limiting."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc

    async def _wait_for_rate_limit(
        self,
        domain: str,
        rate_limit: RateLimitConfig,
    ) -> None:
        """Wait appropriate time before making request."""
        backoff_level = self._backoff_level.get(domain, 0)
        delay = rate_limit.get_delay(backoff_level)

        last_time = self._last_request_time.get(domain, 0)
        elapsed = time.time() - last_time
        wait_time = max(0, delay - elapsed)

        if wait_time > 0:
            logger.debug(
                "rate_limit_wait",
                domain=domain,
                wait_seconds=round(wait_time, 2),
                backoff_level=backoff_level,
            )
            await asyncio.sleep(wait_time)

        self._last_request_time[domain] = time.time()

    def _on_success(self, domain: str) -> None:
        """Reset backoff on successful request."""
        if domain in self._backoff_level:
            self._backoff_level[domain] = max(0, self._backoff_level[domain] - 1)

    def _on_rate_limited(self, domain: str) -> None:
        """Increase backoff on rate limit."""
        current = self._backoff_level.get(domain, 0)
        self._backoff_level[domain] = min(current + 1, 5)  # Max 5 levels
        logger.warning(
            "rate_limited",
            domain=domain,
            new_backoff_level=self._backoff_level[domain],
        )

    async def scrape(
        self,
        url: str,
        rate_limit: RateLimitConfig | None = None,
        formats: list[str] | None = None,
        wait_for: str | None = None,
        timeout: int = 30000,
        only_main_content: bool = True,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        actions: list[dict[str, Any]] | None = None,
    ) -> FirecrawlResponse:
        """Scrape a URL and convert to Markdown.

        Args:
            url: URL to scrape
            rate_limit: Rate limiting config (uses default if not provided)
            formats: Output formats ["markdown", "html", "rawHtml", "links", "screenshot"]
            wait_for: CSS selector to wait for before scraping (for JS pages)
            timeout: Page load timeout in ms
            only_main_content: Remove nav, footer, etc.
            proxy: Proxy URL to use
            headers: Custom headers for the request
            actions: Browser actions to perform before scraping (Playwright)
                     Examples:
                     - {"type": "click", "selector": "button.load-more"}
                     - {"type": "wait", "milliseconds": 2000}
                     - {"type": "scroll", "direction": "down"}
                     - {"type": "write", "selector": "input#search", "text": "query"}
                     - {"type": "press", "key": "Enter"}

        Returns:
            FirecrawlResponse with markdown content
        """
        domain = self._get_domain(url)
        rate_limit = rate_limit or self.default_rate_limit

        # Wait for rate limit
        await self._wait_for_rate_limit(domain, rate_limit)

        # Build request payload
        payload: dict[str, Any] = {
            "url": url,
            "formats": formats or ["markdown"],
            "onlyMainContent": only_main_content,
            "timeout": timeout,
        }

        if wait_for:
            payload["waitFor"] = wait_for

        if headers:
            payload["headers"] = headers

        if actions:
            payload["actions"] = actions

        # Note: Firecrawl self-hosted doesn't support proxy in API
        # For proxy support, configure at Firecrawl server level

        try:
            client = await self._get_client()
            # Try /scrape first (older/self-hosted), fallback to /v1/scrape (cloud)
            scrape_url = f"{self.base_url}/scrape"
            response = await client.post(scrape_url, json=payload)

            # If /scrape returns 404, try /v1/scrape (cloud API)
            if response.status_code == 404:
                scrape_url = f"{self.base_url}/v1/scrape"
                response = await client.post(scrape_url, json=payload)

            if response.status_code == 429:
                self._on_rate_limited(domain)
                return FirecrawlResponse(
                    success=False,
                    error="Rate limited by Firecrawl",
                )

            if response.status_code == 403:
                self._on_rate_limited(domain)
                return FirecrawlResponse(
                    success=False,
                    error="Forbidden - target site may have blocked",
                )

            response.raise_for_status()
            data = response.json()

            self._on_success(domain)

            # Parse Firecrawl response - handle both old and new API formats
            # Old/self-hosted: {"content": "...", "markdown": "...", "metadata": {...}}
            # New/cloud: {"success": true, "data": {"markdown": "...", "html": "...", "metadata": {...}}}
            if data.get("success") and "data" in data:
                # New cloud API format
                result_data = data.get("data", {})
                return FirecrawlResponse(
                    success=True,
                    markdown=result_data.get("markdown"),
                    html=result_data.get("html"),
                    metadata=result_data.get("metadata", {}),
                )
            elif "content" in data or "markdown" in data:
                # Old self-hosted format - content is HTML, markdown may also be present
                return FirecrawlResponse(
                    success=True,
                    markdown=data.get("markdown") or data.get("content"),
                    html=data.get("content"),
                    metadata=data.get("metadata", {}),
                )
            else:
                return FirecrawlResponse(
                    success=False,
                    error=data.get("error", "Unknown response format"),
                )

        except httpx.TimeoutException:
            logger.warning("firecrawl_timeout", url=url)
            return FirecrawlResponse(
                success=False,
                error="Request timeout",
            )
        except httpx.HTTPStatusError as e:
            logger.error("firecrawl_http_error", url=url, status=e.response.status_code)
            return FirecrawlResponse(
                success=False,
                error=f"HTTP {e.response.status_code}",
            )
        except Exception as e:
            logger.error("firecrawl_error", url=url, error=str(e))
            return FirecrawlResponse(
                success=False,
                error=str(e),
            )

    async def scrape_with_config(
        self,
        url: str,
        source_id: str,
    ) -> FirecrawlResponse:
        """Scrape using pre-configured source settings.

        Args:
            url: URL to scrape
            source_id: Source identifier to get config from

        Returns:
            FirecrawlResponse
        """
        config = get_source_config(source_id)

        return await self.scrape(
            url=url,
            rate_limit=config.rate_limit,
            wait_for=config.firecrawl_wait_for,
            timeout=config.firecrawl_timeout,
            headers=config.headers.get_headers() if config.headers.rotate_user_agent else None,
        )

    async def scrape_batch(
        self,
        urls: list[str],
        source_id: str | None = None,
        rate_limit: RateLimitConfig | None = None,
    ) -> list[FirecrawlResponse]:
        """Scrape multiple URLs with rate limiting.

        Args:
            urls: List of URLs to scrape
            source_id: Source identifier for config
            rate_limit: Override rate limit config

        Returns:
            List of FirecrawlResponse objects
        """
        results: list[FirecrawlResponse] = []

        config = get_source_config(source_id) if source_id else None
        effective_rate_limit = rate_limit or (config.rate_limit if config else self.default_rate_limit)

        for i, url in enumerate(urls):
            logger.info(
                "scrape_batch_progress",
                current=i + 1,
                total=len(urls),
                url=url[:50],
            )

            if config:
                result = await self.scrape_with_config(url, source_id or "")
            else:
                result = await self.scrape(url, rate_limit=effective_rate_limit)

            results.append(result)

        return results

    async def health_check(self) -> bool:
        """Check if Firecrawl server is reachable."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/")
            return response.status_code == 200
        except Exception:
            return False


# Singleton instance
_client: FirecrawlClient | None = None


def get_firecrawl_client(
    base_url: str = "http://localhost:3002",
    api_key: str | None = None,
) -> FirecrawlClient:
    """Get singleton Firecrawl client instance."""
    global _client
    if _client is None:
        _client = FirecrawlClient(base_url=base_url, api_key=api_key)
    return _client


def reset_firecrawl_client() -> None:
    """Reset singleton (for testing)."""
    global _client
    _client = None
