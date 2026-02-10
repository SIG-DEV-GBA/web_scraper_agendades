"""Event deduplication utilities."""

import hashlib
import re
from difflib import SequenceMatcher

from src.core.event_model import EventCreate
from src.logging import get_logger

logger = get_logger(__name__)


def normalize_text(text: str) -> str:
    """Normalize text for comparison.

    - Lowercase
    - Remove extra whitespace
    - Remove punctuation
    - Remove common words
    """
    if not text:
        return ""

    text = text.lower()
    # Remove punctuation
    text = re.sub(r"[^\w\s]", " ", text)
    # Normalize whitespace
    text = " ".join(text.split())

    return text


def generate_event_hash(event: EventCreate, include_time: bool = False) -> str:
    """Generate a unique hash for an event.

    The hash is based on:
    - Normalized title
    - Start date
    - Optionally: start time
    - Optionally: venue name

    Args:
        event: Event to hash
        include_time: Include start_time in hash

    Returns:
        SHA256 hash string (32 chars)
    """
    components = [
        normalize_text(event.title),
        event.start_date.isoformat(),
    ]

    if include_time and event.start_time:
        components.append(event.start_time.isoformat())

    if event.venue_name:
        components.append(normalize_text(event.venue_name))

    key = "|".join(components)
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def generate_external_id(source_id: str, event: EventCreate) -> str:
    """Generate external_id for deduplication across scrape runs.

    Format: {source_id}:{hash}

    Args:
        source_id: Adapter source ID
        event: Event to generate ID for

    Returns:
        External ID string
    """
    event_hash = generate_event_hash(event, include_time=True)
    return f"{source_id}:{event_hash}"


def title_similarity(title1: str, title2: str) -> float:
    """Calculate similarity ratio between two titles.

    Uses SequenceMatcher for fuzzy matching.

    Args:
        title1: First title
        title2: Second title

    Returns:
        Similarity ratio (0.0 to 1.0)
    """
    norm1 = normalize_text(title1)
    norm2 = normalize_text(title2)

    if not norm1 or not norm2:
        return 0.0

    return SequenceMatcher(None, norm1, norm2).ratio()


def is_duplicate(
    event: EventCreate,
    existing_events: list[EventCreate],
    title_threshold: float = 0.85,
    check_venue: bool = True,
) -> bool:
    """Check if an event is a duplicate of any existing event.

    Duplicate criteria:
    1. Same start_date AND
    2. Title similarity > threshold AND
    3. (Optional) Same venue

    Args:
        event: Event to check
        existing_events: List of existing events
        title_threshold: Minimum title similarity (0.0-1.0)
        check_venue: Also check venue match

    Returns:
        True if event is a duplicate
    """
    for existing in existing_events:
        # Must have same start date
        if event.start_date != existing.start_date:
            continue

        # Check title similarity
        similarity = title_similarity(event.title, existing.title)
        if similarity < title_threshold:
            continue

        # Optionally check venue
        if check_venue and event.venue_name and existing.venue_name:
            venue_similarity = title_similarity(event.venue_name, existing.venue_name)
            if venue_similarity < 0.7:
                continue

        logger.debug(
            "Duplicate found",
            new_title=event.title,
            existing_title=existing.title,
            similarity=similarity,
        )
        return True

    return False


def find_duplicate_index(
    event: EventCreate,
    existing_events: list[EventCreate],
    title_threshold: float = 0.85,
) -> int | None:
    """Find the index of a duplicate event in the list.

    Returns:
        Index of duplicate event, or None if no duplicate found
    """
    for i, existing in enumerate(existing_events):
        if event.start_date != existing.start_date:
            continue

        similarity = title_similarity(event.title, existing.title)
        if similarity < title_threshold:
            continue

        if event.venue_name and existing.venue_name:
            venue_similarity = title_similarity(event.venue_name, existing.venue_name)
            if venue_similarity < 0.7:
                continue

        return i

    return None


def deduplicate_batch(
    events: list[EventCreate],
    title_threshold: float = 0.85,
    merge_categories: bool = True,
) -> tuple[list[EventCreate], list[EventCreate]]:
    """Remove duplicates from a batch of events.

    Keeps the first occurrence of each unique event.
    If merge_categories=True, merges category_slugs from duplicates.

    Args:
        events: List of events to deduplicate
        title_threshold: Minimum title similarity for duplicate detection
        merge_categories: Whether to merge categories from duplicates

    Returns:
        Tuple of (unique_events, duplicate_events)
    """
    unique: list[EventCreate] = []
    duplicates: list[EventCreate] = []

    for event in events:
        dup_idx = find_duplicate_index(event, unique, title_threshold)

        if dup_idx is not None:
            duplicates.append(event)

            # Merge categories if enabled
            if merge_categories and event.category_slugs:
                existing = unique[dup_idx]
                existing_cats = set(existing.category_slugs or [])
                new_cats = set(event.category_slugs or [])
                merged = existing_cats | new_cats

                if merged != existing_cats:
                    unique[dup_idx].category_slugs = list(merged)
                    logger.debug(
                        "Merged categories",
                        title=existing.title[:50],
                        original=list(existing_cats),
                        merged=list(merged),
                    )
        else:
            unique.append(event)

    if duplicates:
        logger.info(
            "Deduplicated batch",
            original=len(events),
            unique=len(unique),
            duplicates=len(duplicates),
        )

    return unique, duplicates


class DeduplicationCache:
    """In-memory cache for tracking seen events during a scrape session."""

    def __init__(self) -> None:
        self._seen_hashes: set[str] = set()
        self._seen_external_ids: set[str] = set()

    def has_seen_hash(self, event_hash: str) -> bool:
        """Check if a hash has been seen."""
        return event_hash in self._seen_hashes

    def add_hash(self, event_hash: str) -> None:
        """Add a hash to the seen set."""
        self._seen_hashes.add(event_hash)

    def has_seen_external_id(self, external_id: str) -> bool:
        """Check if an external_id has been seen."""
        return external_id in self._seen_external_ids

    def add_external_id(self, external_id: str) -> None:
        """Add an external_id to the seen set."""
        self._seen_external_ids.add(external_id)

    def check_and_add(self, event: EventCreate, source_id: str) -> bool:
        """Check if event is new and add to cache if so.

        Args:
            event: Event to check
            source_id: Source adapter ID

        Returns:
            True if event is new (not seen before)
        """
        event_hash = generate_event_hash(event)

        if self.has_seen_hash(event_hash):
            return False

        external_id = event.external_id or generate_external_id(source_id, event)
        if self.has_seen_external_id(external_id):
            return False

        self.add_hash(event_hash)
        self.add_external_id(external_id)
        return True

    def clear(self) -> None:
        """Clear all cached data."""
        self._seen_hashes.clear()
        self._seen_external_ids.clear()

    @property
    def count(self) -> int:
        """Number of unique events seen."""
        return len(self._seen_hashes)
