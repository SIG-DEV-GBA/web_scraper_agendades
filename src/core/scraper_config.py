"""Scraper configuration for anti-ban protection and rate limiting.

This module provides:
- Per-source delay configuration
- Proxy rotation support
- Realistic headers rotation
- Backoff strategies for rate limiting
"""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AggressivenessLevel(str, Enum):
    """How aggressive the scraping should be."""

    GENTLE = "gentle"      # 3-6 seconds between requests
    MODERATE = "moderate"  # 1-3 seconds between requests
    AGGRESSIVE = "aggressive"  # 0.5-1.5 seconds (use with caution)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    # Base delay between requests (seconds)
    base_delay: float = 2.0

    # Random jitter to add (0 to jitter_max seconds)
    jitter_max: float = 2.0

    # Multiplier when rate limited (429/403)
    backoff_multiplier: float = 2.0

    # Maximum delay after backoffs
    max_delay: float = 60.0

    # Maximum requests per minute (0 = unlimited)
    max_requests_per_minute: int = 0

    def get_delay(self, current_backoff_level: int = 0) -> float:
        """Calculate delay with jitter and backoff.

        Args:
            current_backoff_level: Number of consecutive rate limits hit

        Returns:
            Delay in seconds
        """
        base = self.base_delay * (self.backoff_multiplier ** current_backoff_level)
        base = min(base, self.max_delay)
        jitter = random.uniform(0, self.jitter_max)
        return base + jitter


@dataclass
class ProxyConfig:
    """Proxy configuration for IP rotation."""

    enabled: bool = False

    # List of proxy URLs (http://user:pass@host:port)
    proxies: list[str] = field(default_factory=list)

    # Rotate proxy every N requests (0 = every request)
    rotate_every: int = 10

    # Current proxy index
    _current_index: int = 0
    _request_count: int = 0

    def get_proxy(self) -> str | None:
        """Get next proxy URL, rotating if needed."""
        if not self.enabled or not self.proxies:
            return None

        self._request_count += 1

        if self.rotate_every > 0 and self._request_count >= self.rotate_every:
            self._current_index = (self._current_index + 1) % len(self.proxies)
            self._request_count = 0

        return self.proxies[self._current_index]

    def mark_proxy_failed(self) -> None:
        """Mark current proxy as failed and rotate to next."""
        if self.proxies:
            self._current_index = (self._current_index + 1) % len(self.proxies)
            self._request_count = 0


# Realistic User-Agent strings (Chrome, Firefox, Safari on Windows/Mac)
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Firefox on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


@dataclass
class HeadersConfig:
    """HTTP headers configuration with rotation."""

    # Rotate User-Agent
    rotate_user_agent: bool = True

    # Custom User-Agent (if not rotating)
    custom_user_agent: str | None = None

    # Additional headers to include
    extra_headers: dict[str, str] = field(default_factory=dict)

    def get_headers(self) -> dict[str, str]:
        """Get headers with optional User-Agent rotation."""
        if self.rotate_user_agent:
            user_agent = random.choice(USER_AGENTS)
        else:
            user_agent = self.custom_user_agent or USER_AGENTS[0]

        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            **self.extra_headers,
        }

        return headers


@dataclass
class SourceScraperConfig:
    """Complete scraper configuration for a specific source."""

    source_id: str
    source_name: str
    base_url: str

    # Rate limiting
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)

    # Proxy settings
    proxy: ProxyConfig = field(default_factory=ProxyConfig)

    # Headers
    headers: HeadersConfig = field(default_factory=HeadersConfig)

    # Firecrawl settings
    use_firecrawl: bool = False
    firecrawl_wait_for: str | None = None  # CSS selector to wait for
    firecrawl_timeout: int = 30000  # ms

    # Request settings
    request_timeout: int = 30  # seconds
    max_retries: int = 3

    # Content cleaning
    clean_html_to_markdown: bool = True

    @classmethod
    def gentle(cls, source_id: str, source_name: str, base_url: str) -> "SourceScraperConfig":
        """Create a gentle configuration (for strict sites)."""
        return cls(
            source_id=source_id,
            source_name=source_name,
            base_url=base_url,
            rate_limit=RateLimitConfig(base_delay=3.0, jitter_max=3.0),
        )

    @classmethod
    def moderate(cls, source_id: str, source_name: str, base_url: str) -> "SourceScraperConfig":
        """Create a moderate configuration (default)."""
        return cls(
            source_id=source_id,
            source_name=source_name,
            base_url=base_url,
            rate_limit=RateLimitConfig(base_delay=1.5, jitter_max=2.0),
        )

    @classmethod
    def api_friendly(cls, source_id: str, source_name: str, base_url: str) -> "SourceScraperConfig":
        """Create config for official APIs (less restrictive)."""
        return cls(
            source_id=source_id,
            source_name=source_name,
            base_url=base_url,
            rate_limit=RateLimitConfig(base_delay=0.5, jitter_max=0.5),
            headers=HeadersConfig(
                rotate_user_agent=False,
                custom_user_agent="AgendadesScraper/1.0 (+https://agendades.es)",
            ),
        )


# Pre-configured sources (to be expanded)
SOURCES_CONFIG: dict[str, SourceScraperConfig] = {
    # Madrid - Official API, can be faster
    "madrid_datos_abiertos": SourceScraperConfig.api_friendly(
        source_id="madrid_datos_abiertos",
        source_name="Madrid Datos Abiertos",
        base_url="https://datos.madrid.es",
    ),

    # Template for future sources - HTML scraping needs to be gentler
    "barcelona_agenda": SourceScraperConfig.gentle(
        source_id="barcelona_agenda",
        source_name="Agenda Barcelona",
        base_url="https://www.barcelona.cat",
    ),

    "valencia_agenda": SourceScraperConfig.gentle(
        source_id="valencia_agenda",
        source_name="Agenda Valencia",
        base_url="https://www.valencia.es",
    ),

    "andalucia_cultura": SourceScraperConfig.moderate(
        source_id="andalucia_cultura",
        source_name="Agenda Cultural Andalucía",
        base_url="https://www.juntadeandalucia.es",
    ),
}


def get_source_config(source_id: str) -> SourceScraperConfig:
    """Get configuration for a source, or create default if not found."""
    if source_id in SOURCES_CONFIG:
        return SOURCES_CONFIG[source_id]

    # Default moderate config
    return SourceScraperConfig.moderate(
        source_id=source_id,
        source_name=source_id,
        base_url="",
    )


def register_source_config(config: SourceScraperConfig) -> None:
    """Register a new source configuration."""
    SOURCES_CONFIG[config.source_id] = config
