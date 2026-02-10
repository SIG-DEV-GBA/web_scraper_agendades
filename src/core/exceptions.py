"""Unified exception hierarchy for the Agendades scraper.

Exception categories:
- Configuration errors (missing config, invalid settings)
- Fetch errors (HTTP, timeout, rate limiting)
- Parse errors (invalid data, missing fields)
- Enrichment errors (LLM failures)
- Storage errors (Supabase failures)
"""


class AgendadesError(Exception):
    """Base exception for all Agendades errors."""

    def __init__(self, message: str, source: str | None = None, details: dict | None = None):
        self.source = source
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        msg = super().__str__()
        if self.source:
            msg = f"[{self.source}] {msg}"
        return msg


# ============================================================
# CONFIGURATION ERRORS
# ============================================================


class ConfigurationError(AgendadesError):
    """Base class for configuration-related errors."""
    pass


class SourceNotFoundError(ConfigurationError):
    """Raised when a source slug is not found in the registry."""

    def __init__(self, slug: str, available: list[str] | None = None):
        self.slug = slug
        self.available = available
        msg = f"Unknown source: {slug}"
        if available:
            msg += f". Available: {', '.join(available[:5])}..."
        super().__init__(msg, source=slug)


class AdapterNotFoundError(ConfigurationError):
    """Raised when no adapter is registered for a source."""

    def __init__(self, slug: str):
        super().__init__(f"No adapter registered for source", source=slug)


class InvalidConfigError(ConfigurationError):
    """Raised when configuration values are invalid."""

    def __init__(self, message: str, field: str | None = None):
        self.field = field
        details = {"field": field} if field else {}
        super().__init__(message, details=details)


# ============================================================
# FETCH ERRORS
# ============================================================


class FetchError(AgendadesError):
    """Base class for data fetching errors."""
    pass


class HTTPError(FetchError):
    """Raised for HTTP-related failures."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        url: str | None = None,
        source: str | None = None,
    ):
        self.status_code = status_code
        self.url = url
        details = {}
        if status_code:
            details["status_code"] = status_code
        if url:
            details["url"] = url
        super().__init__(message, source=source, details=details)


class TimeoutError(FetchError):
    """Raised when a request times out."""

    def __init__(self, url: str, timeout: float, source: str | None = None):
        self.url = url
        self.timeout = timeout
        super().__init__(
            f"Request timed out after {timeout}s",
            source=source,
            details={"url": url, "timeout": timeout},
        )


class RateLimitError(FetchError):
    """Raised when rate limited by the source."""

    def __init__(
        self,
        source: str,
        retry_after: int | None = None,
        url: str | None = None,
    ):
        self.retry_after = retry_after
        msg = "Rate limited by source"
        if retry_after:
            msg += f", retry after {retry_after}s"
        super().__init__(
            msg,
            source=source,
            details={"retry_after": retry_after, "url": url},
        )


class FirecrawlError(FetchError):
    """Raised for Firecrawl-specific errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        source: str | None = None,
    ):
        self.status_code = status_code
        super().__init__(message, source=source, details={"status_code": status_code})


# ============================================================
# PARSE ERRORS
# ============================================================


class ParseError(AgendadesError):
    """Base class for data parsing errors."""
    pass


class MissingFieldError(ParseError):
    """Raised when a required field is missing."""

    def __init__(self, field: str, event_id: str | None = None, source: str | None = None):
        self.field = field
        self.event_id = event_id
        msg = f"Missing required field: {field}"
        if event_id:
            msg += f" (event: {event_id})"
        super().__init__(msg, source=source, details={"field": field, "event_id": event_id})


class InvalidDateError(ParseError):
    """Raised when a date cannot be parsed."""

    def __init__(self, value: str, expected_format: str | None = None, source: str | None = None):
        self.value = value
        self.expected_format = expected_format
        msg = f"Invalid date: {value}"
        if expected_format:
            msg += f" (expected format: {expected_format})"
        super().__init__(msg, source=source, details={"value": value, "format": expected_format})


class JSONParseError(ParseError):
    """Raised when JSON parsing fails."""

    def __init__(self, message: str, raw_data: str | None = None, source: str | None = None):
        self.raw_data = raw_data[:200] if raw_data else None
        super().__init__(message, source=source, details={"raw_data_preview": self.raw_data})


# ============================================================
# ENRICHMENT ERRORS
# ============================================================


class EnrichmentError(AgendadesError):
    """Base class for LLM enrichment errors."""
    pass


class LLMError(EnrichmentError):
    """Raised for LLM API failures."""

    def __init__(
        self,
        message: str,
        model: str | None = None,
        provider: str | None = None,
        source: str | None = None,
    ):
        self.model = model
        self.provider = provider
        super().__init__(
            message,
            source=source,
            details={"model": model, "provider": provider},
        )


class LLMResponseTruncatedError(LLMError):
    """Raised when LLM response is truncated (incomplete JSON)."""

    def __init__(self, batch_size: int, source: str | None = None):
        super().__init__(
            f"LLM response truncated. Try reducing batch_size from {batch_size}",
            source=source,
        )


class LLMQuotaExceededError(LLMError):
    """Raised when LLM API quota is exceeded."""

    def __init__(self, provider: str, source: str | None = None):
        super().__init__(f"API quota exceeded for {provider}", provider=provider, source=source)


# ============================================================
# STORAGE ERRORS
# ============================================================


class StorageError(AgendadesError):
    """Base class for storage-related errors."""
    pass


class SupabaseError(StorageError):
    """Raised for Supabase-specific errors."""

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        table: str | None = None,
        source: str | None = None,
    ):
        self.operation = operation
        self.table = table
        super().__init__(
            message,
            source=source,
            details={"operation": operation, "table": table},
        )


class DuplicateEventError(StorageError):
    """Raised when trying to insert a duplicate event."""

    def __init__(self, event_id: str, source: str | None = None):
        self.event_id = event_id
        super().__init__(
            f"Event already exists: {event_id}",
            source=source,
            details={"event_id": event_id},
        )


class BatchInsertError(StorageError):
    """Raised when a batch insert partially fails."""

    def __init__(
        self,
        total: int,
        inserted: int,
        failed: int,
        errors: list[str] | None = None,
        source: str | None = None,
    ):
        self.total = total
        self.inserted = inserted
        self.failed = failed
        self.errors = errors or []
        super().__init__(
            f"Batch insert partially failed: {inserted}/{total} inserted, {failed} failed",
            source=source,
            details={"total": total, "inserted": inserted, "failed": failed},
        )
