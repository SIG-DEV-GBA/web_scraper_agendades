"""Core modules for the scraper."""

from src.core.base_adapter import BaseAdapter, DBAdapterType
from src.core.event_model import Event, EventCreate
from src.core.firecrawl_client import FirecrawlClient, get_firecrawl_client
from src.core.image_provider import ImageProvider, get_image_provider
from src.core.retry import RetryConfig, with_retry
from src.core.scraper_config import SourceScraperConfig, get_source_config

__all__ = [
    "BaseAdapter",
    "DBAdapterType",
    "Event",
    "EventCreate",
    "with_retry",
    "RetryConfig",
    "FirecrawlClient",
    "get_firecrawl_client",
    "ImageProvider",
    "get_image_provider",
    "SourceScraperConfig",
    "get_source_config",
]
