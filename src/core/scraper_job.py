"""Scraper job configuration and tracking for dashboard integration."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class JobStatus(str, Enum):
    """Status of a scraper job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScraperJobConfig:
    """Configuration for a scraper job, configurable from dashboard.

    This allows the dashboard to specify:
    - How many events to process (limit)
    - Where to start from (offset) for pagination
    - Whether to do a dry run
    - LLM and image settings
    """

    # Batch control (main dashboard controls)
    limit: int = 100  # Max events to process
    offset: int = 0   # Skip first N events (for pagination)

    # Feature toggles
    dry_run: bool = True  # Don't insert to DB
    llm_enabled: bool = True  # Use LLM for categorization
    images_enabled: bool = True  # Resolve Unsplash images

    # Processing settings
    llm_batch_size: int = 20  # Events per LLM call

    # Source filter (optional)
    source_id: Optional[str] = None  # Specific source, or None for all

    def __post_init__(self):
        """Validate configuration."""
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        if self.offset < 0:
            raise ValueError("offset must be >= 0")
        if self.llm_batch_size < 1:
            raise ValueError("llm_batch_size must be >= 1")


@dataclass
class ScraperJobResult:
    """Result of a scraper job execution."""

    # Counts
    total_fetched: int = 0
    total_processed: int = 0
    total_inserted: int = 0
    total_skipped: int = 0  # Already existed
    total_errors: int = 0

    # Category distribution
    categories: dict = field(default_factory=dict)

    # Image stats
    with_images: int = 0
    with_unsplash: int = 0

    # Errors
    error_details: list = field(default_factory=list)

    def add_category(self, category: str):
        """Track category distribution."""
        self.categories[category] = self.categories.get(category, 0) + 1

    def add_error(self, error: str, event_id: Optional[str] = None):
        """Track an error."""
        self.total_errors += 1
        self.error_details.append({
            "event_id": event_id,
            "error": error,
            "timestamp": datetime.utcnow().isoformat()
        })


@dataclass
class ScraperJob:
    """A scraper job with status tracking.

    This can be stored in the database for dashboard visibility.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_name: str = ""
    config: ScraperJobConfig = field(default_factory=ScraperJobConfig)
    status: JobStatus = JobStatus.PENDING

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Result (populated after completion)
    result: Optional[ScraperJobResult] = None
    error_message: Optional[str] = None

    def start(self):
        """Mark job as started."""
        self.status = JobStatus.RUNNING
        self.started_at = datetime.utcnow()

    def complete(self, result: ScraperJobResult):
        """Mark job as completed with result."""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.result = result

    def fail(self, error: str):
        """Mark job as failed with error."""
        self.status = JobStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error

    def cancel(self):
        """Mark job as cancelled."""
        self.status = JobStatus.CANCELLED
        self.completed_at = datetime.utcnow()

    @property
    def duration_seconds(self) -> Optional[float]:
        """Get job duration in seconds."""
        if not self.started_at:
            return None
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        """Convert to dictionary for API/DB."""
        return {
            "id": self.id,
            "source_name": self.source_name,
            "status": self.status.value,
            "config": {
                "limit": self.config.limit,
                "offset": self.config.offset,
                "dry_run": self.config.dry_run,
                "llm_enabled": self.config.llm_enabled,
                "images_enabled": self.config.images_enabled,
            },
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "result": {
                "total_fetched": self.result.total_fetched,
                "total_processed": self.result.total_processed,
                "total_inserted": self.result.total_inserted,
                "total_skipped": self.result.total_skipped,
                "total_errors": self.result.total_errors,
                "categories": self.result.categories,
                "with_images": self.result.with_images,
                "with_unsplash": self.result.with_unsplash,
            } if self.result else None,
            "error_message": self.error_message,
        }
