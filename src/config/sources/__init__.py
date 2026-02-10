"""Centralized source configuration registry.

Provides a unified registry for all event sources across tiers (Gold, Silver, Bronze, Eventbrite).
Sources are registered at import time and can be queried by slug, tier, or CCAA.

Usage:
    from src.config.sources import SourceRegistry, SourceTier

    # Get a specific source
    source = SourceRegistry.get("eventbrite_madrid")

    # Get all sources for a tier
    gold_sources = SourceRegistry.get_by_tier(SourceTier.GOLD)

    # Get all sources for a CCAA
    madrid_sources = SourceRegistry.get_by_ccaa("Comunidad de Madrid")
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceTier(str, Enum):
    """Quality tier of data source - determines which LLM model to use."""

    GOLD = "gold"  # Clean JSON APIs - use gpt-oss-120b (fast, structured)
    SILVER = "silver"  # Semi-structured RSS/HTML - use llama-3.3-70b (balanced)
    BRONZE = "bronze"  # Web scraping - use kimi-k2 (deep reasoning)
    EVENTBRITE = "eventbrite"  # Eventbrite (Firecrawl + JSON-LD)


class PaginationType(str, Enum):
    """Pagination strategy for APIs."""

    NONE = "none"
    OFFSET_LIMIT = "offset_limit"
    PAGE = "page"
    SOCRATA = "socrata"


@dataclass
class BaseSourceConfig:
    """Base configuration for all source types."""

    slug: str
    name: str
    ccaa: str
    ccaa_code: str
    tier: SourceTier
    is_active: bool = True

    def __hash__(self) -> int:
        return hash(self.slug)


@dataclass
class GoldSourceConfig(BaseSourceConfig):
    """Configuration for Gold-level API sources."""

    url: str = ""
    pagination_type: PaginationType = PaginationType.NONE
    page_size: int = 100
    offset_param: str = "offset"
    limit_param: str = "limit"
    page_param: str = "_page"
    items_path: str = ""
    total_count_path: str = ""
    total_pages_path: str = ""
    field_mappings: dict[str, str] = field(default_factory=dict)
    default_province: str | None = None
    date_format: str = "%Y-%m-%d"
    datetime_format: str = "%Y-%m-%dT%H:%M:%SZ"
    free_value: str | None = "Gratuito"
    free_field: str | None = None
    image_url_prefix: str = ""

    def __post_init__(self):
        if not hasattr(self, 'tier') or self.tier is None:
            object.__setattr__(self, 'tier', SourceTier.GOLD)


@dataclass
class SilverSourceConfig(BaseSourceConfig):
    """Configuration for Silver-level RSS/HTML sources."""

    url: str = ""
    feed_type: str = "rss"  # rss, atom, ical
    event_selector: str = ""
    detail_url_selector: str = ""
    requires_detail_fetch: bool = False
    field_selectors: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not hasattr(self, 'tier') or self.tier is None:
            object.__setattr__(self, 'tier', SourceTier.SILVER)


@dataclass
class BronzeSourceConfig(BaseSourceConfig):
    """Configuration for Bronze-level web scraping sources."""

    listing_url: str = ""  # URL for event listings page
    province: str = ""
    city: str = ""
    uses_firecrawl: bool = True
    firecrawl_wait: int = 5000
    event_card_selector: str = ""
    title_selector: str = ""
    date_selector: str = ""
    link_selector: str = ""
    image_selector: str = ""
    requires_detail_fetch: bool = True
    max_pages: int = 3

    def __post_init__(self):
        if not hasattr(self, 'tier') or self.tier is None:
            object.__setattr__(self, 'tier', SourceTier.BRONZE)


@dataclass
class EventbriteSourceConfig(BaseSourceConfig):
    """Configuration for Eventbrite sources."""

    search_url: str = ""
    province: str = ""
    city: str = ""
    firecrawl_url: str = "https://firecrawl.si-erp.cloud/scrape"
    firecrawl_wait: int = 10000

    def __post_init__(self):
        if not hasattr(self, 'tier') or self.tier is None:
            object.__setattr__(self, 'tier', SourceTier.EVENTBRITE)


# Type alias for any source config
AnySourceConfig = GoldSourceConfig | SilverSourceConfig | BronzeSourceConfig | EventbriteSourceConfig


class SourceRegistry:
    """Central registry for all event sources.

    Sources are registered at module import time from the config modules.
    Provides lookup by slug, tier, and CCAA.
    """

    _sources: dict[str, AnySourceConfig] = {}
    _initialized: bool = False

    @classmethod
    def register(cls, config: AnySourceConfig) -> None:
        """Register a source configuration.

        Args:
            config: Source configuration to register
        """
        cls._sources[config.slug] = config

    @classmethod
    def register_many(cls, configs: list[AnySourceConfig]) -> None:
        """Register multiple source configurations.

        Args:
            configs: List of configurations to register
        """
        for config in configs:
            cls.register(config)

    @classmethod
    def get(cls, slug: str) -> AnySourceConfig | None:
        """Get a source configuration by slug.

        Args:
            slug: Source identifier

        Returns:
            Source configuration or None
        """
        cls._ensure_initialized()
        return cls._sources.get(slug)

    @classmethod
    def get_by_tier(cls, tier: SourceTier) -> list[AnySourceConfig]:
        """Get all sources for a tier.

        Args:
            tier: Source tier

        Returns:
            List of matching source configurations
        """
        cls._ensure_initialized()
        return [s for s in cls._sources.values() if s.tier == tier and s.is_active]

    @classmethod
    def get_by_ccaa(cls, ccaa: str) -> list[AnySourceConfig]:
        """Get all sources for a CCAA.

        Args:
            ccaa: CCAA name

        Returns:
            List of matching source configurations
        """
        cls._ensure_initialized()
        ccaa_lower = ccaa.lower()
        return [
            s for s in cls._sources.values()
            if s.ccaa.lower() == ccaa_lower and s.is_active
        ]

    @classmethod
    def get_active(cls) -> list[AnySourceConfig]:
        """Get all active sources.

        Returns:
            List of active source configurations
        """
        cls._ensure_initialized()
        return [s for s in cls._sources.values() if s.is_active]

    @classmethod
    def all(cls) -> list[AnySourceConfig]:
        """Get all registered sources.

        Returns:
            List of all source configurations
        """
        cls._ensure_initialized()
        return list(cls._sources.values())

    @classmethod
    def slugs(cls) -> list[str]:
        """Get all registered source slugs.

        Returns:
            List of source slugs
        """
        cls._ensure_initialized()
        return list(cls._sources.keys())

    @classmethod
    def count(cls) -> int:
        """Get total number of registered sources.

        Returns:
            Number of sources
        """
        cls._ensure_initialized()
        return len(cls._sources)

    @classmethod
    def count_by_tier(cls) -> dict[SourceTier, int]:
        """Get source counts by tier.

        Returns:
            Dict mapping tier to count
        """
        cls._ensure_initialized()
        counts = {tier: 0 for tier in SourceTier}
        for source in cls._sources.values():
            if source.is_active:
                counts[source.tier] += 1
        return counts

    @classmethod
    def count_by_ccaa(cls) -> dict[str, int]:
        """Get source counts by CCAA.

        Returns:
            Dict mapping CCAA to count
        """
        cls._ensure_initialized()
        counts: dict[str, int] = {}
        for source in cls._sources.values():
            if source.is_active:
                counts[source.ccaa] = counts.get(source.ccaa, 0) + 1
        return counts

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Ensure all source modules are imported."""
        if cls._initialized:
            return

        # Import all source modules to trigger registration
        # These imports have side effects - they register sources
        from src.config.sources import bronze_sources  # noqa: F401
        from src.config.sources import eventbrite_sources  # noqa: F401
        from src.config.sources import gold_sources  # noqa: F401

        cls._initialized = True

    @classmethod
    def clear(cls) -> None:
        """Clear all registered sources (for testing)."""
        cls._sources.clear()
        cls._initialized = False


# Export main classes
__all__ = [
    "SourceTier",
    "PaginationType",
    "BaseSourceConfig",
    "GoldSourceConfig",
    "SilverSourceConfig",
    "BronzeSourceConfig",
    "EventbriteSourceConfig",
    "AnySourceConfig",
    "SourceRegistry",
]
