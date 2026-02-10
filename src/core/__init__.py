"""Core modules for the scraper."""

from src.core.base_adapter import BaseAdapter, DBAdapterType
from src.core.event_model import Event, EventCreate
from src.core.exceptions import (
    AgendadesError,
    ConfigurationError,
    EnrichmentError,
    FetchError,
    ParseError,
    SourceNotFoundError,
    StorageError,
)
from src.core.firecrawl_client import FirecrawlClient, get_firecrawl_client
from src.core.image_provider import ImageProvider, get_image_provider
from src.core.pipeline import InsertionPipeline, PipelineConfig, PipelineResult
from src.core.retry import RetryConfig, with_retry
from src.core.scraper_config import SourceScraperConfig, get_source_config

__all__ = [
    # Base classes
    "BaseAdapter",
    "DBAdapterType",
    # Event models
    "Event",
    "EventCreate",
    # Pipeline
    "InsertionPipeline",
    "PipelineConfig",
    "PipelineResult",
    # Exceptions
    "AgendadesError",
    "ConfigurationError",
    "FetchError",
    "ParseError",
    "EnrichmentError",
    "StorageError",
    "SourceNotFoundError",
    # Retry
    "with_retry",
    "RetryConfig",
    # Clients
    "FirecrawlClient",
    "get_firecrawl_client",
    "ImageProvider",
    "get_image_provider",
    # Config
    "SourceScraperConfig",
    "get_source_config",
]
