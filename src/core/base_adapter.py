"""Base adapter class for all event source scrapers."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
from playwright.async_api import Browser, Page, async_playwright

from src.core.event_model import EventBatch, EventCreate
from src.core.retry import RetryableHTTPError, RetryConfig, with_retry
from src.core.scraper_config import (
    SourceScraperConfig,
    get_source_config,
)
from src.core.scraper_job import ScraperJob, ScraperJobConfig, ScraperJobResult
from src.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# DATABASE ADAPTER TYPES
# Maps to scraper_sources.adapter_type column in Supabase
# ============================================================

class DBAdapterType(str, Enum):
    """Adapter type from database (scraper_sources table)."""
    API = "api"          # REST/JSON API - use httpx directly (no Firecrawl)
    JSON = "json"        # Static JSON file - use httpx directly (no Firecrawl)
    HTML = "html"        # Static HTML - use BeautifulSoup (no Firecrawl)
    FIRECRAWL = "firecrawl"  # Dynamic JS - use Firecrawl


class AdapterType(str, Enum):
    """Type of adapter based on source technology."""

    API = "api"  # REST/GraphQL API
    STATIC = "static"  # Static HTML (requests + BeautifulSoup)
    DYNAMIC = "dynamic"  # JavaScript SPA (Playwright)


@dataclass
class AdapterConfig:
    """Configuration for an adapter."""

    source_id: str
    source_name: str
    source_url: str
    ccaa: str
    ccaa_code: str
    adapter_type: AdapterType
    enabled: bool = True
    schedule: str = "0 6 * * *"  # Cron expression
    priority: int = 1
    request_timeout: int = 30
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    custom_headers: dict[str, str] = field(default_factory=dict)
    rate_limit_delay: float = 1.0  # Seconds between requests


class BaseAdapter(ABC):
    """Abstract base class for all event source adapters.

    Each CCAA/source should implement this class with specific
    parsing logic for their website/API.
    """

    # Class-level attributes to be overridden by subclasses
    source_id: str = ""
    source_name: str = ""
    source_url: str = ""
    ccaa: str = ""
    ccaa_code: str = ""
    adapter_type: AdapterType = AdapterType.STATIC

    def __init__(self, config: AdapterConfig | None = None):
        """Initialize adapter with optional config override."""
        self.config = config or self._default_config()
        self._http_client: httpx.AsyncClient | None = None
        self._browser: Browser | None = None
        self._playwright: Any = None
        self.logger = get_logger(f"adapter.{self.source_id}")

        # Load scraper config for rate limiting, headers, etc.
        self._scraper_config: SourceScraperConfig = get_source_config(self.source_id)
        self._last_request_time: float = 0
        self._backoff_level: int = 0

    def _default_config(self) -> AdapterConfig:
        """Create default config from class attributes."""
        return AdapterConfig(
            source_id=self.source_id,
            source_name=self.source_name,
            source_url=self.source_url,
            ccaa=self.ccaa,
            ccaa_code=self.ccaa_code,
            adapter_type=self.adapter_type,
        )

    # ==========================================
    # HTTP Client Management
    # ==========================================

    async def get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for API/static requests."""
        if self._http_client is None or self._http_client.is_closed:
            # Use rotating headers from scraper config
            headers = self._scraper_config.headers.get_headers()
            headers.update(self.config.custom_headers)

            # Setup proxy if configured
            proxy = self._scraper_config.proxy.get_proxy()

            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.request_timeout),
                headers=headers,
                follow_redirects=True,
                proxy=proxy,
            )
        return self._http_client

    async def close_http_client(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    # ==========================================
    # Playwright Browser Management
    # ==========================================

    async def get_browser(self) -> Browser:
        """Get or create Playwright browser for dynamic content."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        return self._browser

    async def get_page(self) -> Page:
        """Get a new browser page."""
        browser = await self.get_browser()
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="es-ES",
        )
        return await context.new_page()

    async def close_browser(self) -> None:
        """Close Playwright browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ==========================================
    # Rate Limiting
    # ==========================================

    async def _wait_for_rate_limit(self) -> None:
        """Wait appropriate time before making request (anti-ban protection)."""
        import time

        delay = self._scraper_config.rate_limit.get_delay(self._backoff_level)
        elapsed = time.time() - self._last_request_time
        wait_time = max(0, delay - elapsed)

        if wait_time > 0:
            self.logger.debug(
                "rate_limit_wait",
                wait_seconds=round(wait_time, 2),
                backoff_level=self._backoff_level,
            )
            await asyncio.sleep(wait_time)

        self._last_request_time = time.time()

    def _on_rate_limited(self) -> None:
        """Increase backoff on rate limit (429/403)."""
        self._backoff_level = min(self._backoff_level + 1, 5)
        self.logger.warning(
            "rate_limited",
            source=self.source_id,
            new_backoff_level=self._backoff_level,
        )

    def _on_request_success(self) -> None:
        """Reset backoff on successful request."""
        if self._backoff_level > 0:
            self._backoff_level = max(0, self._backoff_level - 1)

    # ==========================================
    # Request Methods with Retry
    # ==========================================

    @with_retry()
    async def fetch_url(self, url: str, respect_rate_limit: bool = True, **kwargs: Any) -> httpx.Response:
        """Fetch a URL with automatic retry logic and rate limiting.

        Args:
            url: URL to fetch
            respect_rate_limit: If True, wait for rate limit before request
            **kwargs: Additional arguments for httpx

        Returns:
            httpx.Response object

        Raises:
            RetryableHTTPError: For retryable status codes
            httpx.HTTPError: For other HTTP errors
        """
        if respect_rate_limit:
            await self._wait_for_rate_limit()

        client = await self.get_http_client()
        response = await client.get(url, **kwargs)

        # Handle rate limiting
        if response.status_code in (429, 403):
            self._on_rate_limited()
            raise RetryableHTTPError(response.status_code, response.text[:200])

        if response.status_code in self.config.retry_config.retryable_status_codes:
            raise RetryableHTTPError(response.status_code, response.text[:200])

        self._on_request_success()
        response.raise_for_status()
        return response

    @with_retry()
    async def fetch_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch JSON from URL with retry."""
        response = await self.fetch_url(url, **kwargs)
        return response.json()

    @with_retry()
    async def post_json(self, url: str, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        """POST JSON to URL with retry."""
        client = await self.get_http_client()
        response = await client.post(url, json=data, **kwargs)

        if response.status_code in self.config.retry_config.retryable_status_codes:
            raise RetryableHTTPError(response.status_code, response.text[:200])

        response.raise_for_status()
        return response.json()

    # ==========================================
    # Smart Content Fetching (API vs Firecrawl)
    # ==========================================

    async def fetch_content(
        self,
        url: str,
        db_adapter_type: str | DBAdapterType | None = None,
    ) -> str:
        """Fetch content from URL, choosing method based on adapter_type.

        This method automatically decides whether to use httpx (for APIs/JSON)
        or Firecrawl (for JS-rendered pages) based on the adapter_type.

        Args:
            url: URL to fetch
            db_adapter_type: Adapter type from scraper_sources table.
                           If None, uses self.source_id to look up from DB.

        Returns:
            Content as string (JSON for API, HTML/Markdown for others)

        Usage:
            # In your adapter's fetch_events():
            content = await self.fetch_content(self.source_url, "api")
            # or
            content = await self.fetch_content(self.source_url, DBAdapterType.FIRECRAWL)
        """
        # Normalize adapter type
        if isinstance(db_adapter_type, DBAdapterType):
            adapter_type = db_adapter_type.value
        else:
            adapter_type = db_adapter_type or "api"

        # API or JSON: use httpx directly (skip Firecrawl, save credits)
        if adapter_type in ("api", "json"):
            self.logger.info(
                "fetch_direct",
                url=url[:80],
                adapter_type=adapter_type,
                reason="skipping_firecrawl",
            )
            response = await self.fetch_url(url)
            return response.text

        # HTML: use httpx + BeautifulSoup (no JS rendering needed)
        if adapter_type == "html":
            self.logger.info(
                "fetch_html",
                url=url[:80],
                adapter_type=adapter_type,
            )
            response = await self.fetch_url(url)
            return response.text

        # FIRECRAWL: use Firecrawl for JS-rendered content
        if adapter_type == "firecrawl":
            self.logger.info(
                "fetch_firecrawl",
                url=url[:80],
                adapter_type=adapter_type,
            )
            from src.core.firecrawl_client import get_firecrawl_client
            from src.config.settings import get_settings

            settings = get_settings()
            client = get_firecrawl_client(
                base_url=settings.firecrawl_url,
                api_key=settings.firecrawl_api_key,
            )

            result = await client.scrape_with_config(url, self.source_id)

            if not result.success:
                raise RuntimeError(f"Firecrawl error: {result.error}")

            return result.markdown or result.html or ""

        # Unknown type: default to httpx
        self.logger.warning(
            "unknown_adapter_type",
            adapter_type=adapter_type,
            falling_back_to="httpx",
        )
        response = await self.fetch_url(url)
        return response.text

    # ==========================================
    # Abstract Methods (to implement per source)
    # ==========================================

    @abstractmethod
    async def fetch_events(self, enrich: bool = True) -> list[dict[str, Any]]:
        """Fetch raw event data from the source.

        Args:
            enrich: If True, run any LLM/AI enrichment. Set to False for batch
                   processing where enrichment is done separately on paginated data.

        Returns:
            List of raw event dictionaries from the source.
        """
        pass

    @abstractmethod
    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse a single raw event into EventCreate model.

        Args:
            raw_data: Raw event data from the source

        Returns:
            EventCreate model or None if parsing failed
        """
        pass

    # ==========================================
    # Main Scraping Method
    # ==========================================

    async def scrape(self) -> EventBatch:
        """Main method to scrape all events from the source.

        Returns:
            EventBatch with all scraped events and metadata
        """
        self.logger.info("Starting scrape", source=self.source_id, url=self.source_url)
        start_time = datetime.now()

        events: list[EventCreate] = []
        errors: list[str] = []
        total_found = 0

        try:
            # Fetch raw data
            raw_events = await self.fetch_events()
            total_found = len(raw_events)
            self.logger.info("Fetched raw events", count=total_found)

            # Parse each event
            for i, raw_event in enumerate(raw_events):
                try:
                    event = self.parse_event(raw_event)
                    if event:
                        # Generate external_id if not set
                        if not event.external_id:
                            event.external_id = event.generate_external_id(self.source_id)
                        events.append(event)
                except Exception as e:
                    error_msg = f"Error parsing event {i}: {e}"
                    self.logger.warning(error_msg, raw_data=str(raw_event)[:200])
                    errors.append(error_msg)

        except Exception as e:
            error_msg = f"Error fetching events: {e}"
            self.logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

        finally:
            # Cleanup
            await self.close_http_client()
            await self.close_browser()

        elapsed = (datetime.now() - start_time).total_seconds()
        self.logger.info(
            "Scrape completed",
            source=self.source_id,
            total_found=total_found,
            parsed=len(events),
            errors=len(errors),
            elapsed_seconds=elapsed,
        )

        return EventBatch(
            source_id=self.source_id,
            source_name=self.source_name,
            ccaa=self.ccaa,
            scraped_at=datetime.now().isoformat(),
            events=events,
            total_found=total_found,
            errors=errors,
        )

    # ==========================================
    # Batch Processing (Dashboard Integration)
    # ==========================================

    async def run_batch(self, config: ScraperJobConfig) -> ScraperJobResult:
        """Run a batch scrape job with configurable limits.

        This method is designed for dashboard integration, allowing:
        - Pagination via offset/limit
        - Dry run mode
        - Progress tracking

        Args:
            config: ScraperJobConfig with limit, offset, dry_run, etc.

        Returns:
            ScraperJobResult with statistics
        """
        from src.core.supabase_client import get_supabase_client

        result = ScraperJobResult()
        self.logger.info(
            "batch_start",
            source=self.source_id,
            limit=config.limit,
            offset=config.offset,
            dry_run=config.dry_run,
        )

        try:
            # Fetch all events from source (without LLM enrichment)
            # We'll enrich only the paginated subset to save API calls
            raw_events = await self.fetch_events(enrich=False)
            result.total_fetched = len(raw_events)

            # Apply offset and limit (pagination)
            paginated = raw_events[config.offset : config.offset + config.limit]
            self.logger.info(
                "batch_paginated",
                total=len(raw_events),
                offset=config.offset,
                limit=config.limit,
                processing=len(paginated),
            )

            # Enrich only the paginated events (if adapter supports it)
            if config.llm_enabled and hasattr(self, 'enrich_events'):
                self.enrich_events(paginated)

            # Parse events
            parsed_events: list[EventCreate] = []
            for raw_event in paginated:
                try:
                    event = self.parse_event(raw_event)
                    if event:
                        if not event.external_id:
                            event.external_id = event.generate_external_id(self.source_id)
                        parsed_events.append(event)
                        result.add_category(event.category_slug or "unknown")

                        # Track image stats
                        if event.source_image_url:
                            result.with_images += 1
                            if "unsplash" in (event.source_image_url or ""):
                                result.with_unsplash += 1
                except Exception as e:
                    result.add_error(str(e), raw_event.get("id"))

            result.total_processed = len(parsed_events)

            # Insert to database (unless dry_run)
            if not config.dry_run and parsed_events:
                supabase = get_supabase_client()
                for event in parsed_events:
                    try:
                        # Check if already exists
                        exists = await supabase.event_exists(event.external_id)

                        if exists:
                            result.total_skipped += 1
                        else:
                            inserted = await supabase.insert_event(event)
                            if inserted:
                                result.total_inserted += 1
                            else:
                                result.add_error("Insert failed", event.external_id)
                    except Exception as e:
                        result.add_error(str(e), event.external_id)

            self.logger.info(
                "batch_complete",
                processed=result.total_processed,
                inserted=result.total_inserted,
                skipped=result.total_skipped,
                errors=result.total_errors,
            )

        except Exception as e:
            result.add_error(f"Batch error: {e}")
            self.logger.error("batch_error", error=str(e))

        finally:
            await self.close_http_client()
            await self.close_browser()

        return result

    # ==========================================
    # Utility Methods
    # ==========================================

    async def __aenter__(self) -> "BaseAdapter":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - cleanup resources."""
        await self.close_http_client()
        await self.close_browser()
