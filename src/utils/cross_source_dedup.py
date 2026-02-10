"""Cross-source deduplication for events from multiple sources.

This module handles deduplication of events that come from different sources
(e.g., viralagenda_valladolid + eventbrite_valladolid + castilla_leon_agenda)
and merges them to keep the most complete data.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from src.core.event_model import EventCreate
from src.logging import get_logger
from src.utils.deduplication import normalize_text, title_similarity

logger = get_logger(__name__)


# Quality scoring weights for each field
QUALITY_WEIGHTS = {
    "description": 10,  # >50 chars
    "image_url": 8,
    "end_date": 5,
    "start_time": 3,
    "end_time": 3,
    "price_info": 5,
    "coordinates": 7,  # latitude + longitude
    "organizer_name": 4,
    "category_id": 3,
    "external_url": 2,
}

# Fields that can be merged from a new event into an existing one
MERGEABLE_FIELDS = [
    "description",
    "summary",
    "image_url",
    "source_image_url",
    "end_date",
    "start_time",
    "end_time",
    "price_info",
    "is_free",
    "latitude",
    "longitude",
    "organizer_name",
    "venue_name",
    "address",
    "external_url",
    "category_id",
    "category_slugs",
    "district",
    "postal_code",
]


def normalize_city(city: str | None) -> str:
    """Normalize city name for comparison.

    - Lowercase
    - Remove accents
    - Remove comarca/region suffixes ("y Comarca", "y Campiña", etc.)
    - Normalize whitespace
    """
    if not city:
        return ""

    city = city.lower().strip()

    # Remove comarca/region suffixes (Viralagenda uses these)
    # Examples: "Valladolid y Campiña del Pisuerga", "León y Comarca"
    comarca_patterns = [
        r"\s+y\s+comarca.*$",
        r"\s+y\s+campiña.*$",
        r"\s+y\s+alfoz.*$",
        r"\s+y\s+área\s+metropolitana.*$",
        r"\s+y\s+entorno.*$",
        r"\s+metropolitano.*$",
    ]
    for pattern in comarca_patterns:
        city = re.sub(pattern, "", city, flags=re.IGNORECASE)

    # Remove accents
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "à": "a", "è": "e", "ì": "i", "ò": "o", "ù": "u",
        "ñ": "n", "ü": "u",
    }
    for old, new in replacements.items():
        city = city.replace(old, new)

    # Normalize whitespace
    city = " ".join(city.split())

    return city


def calculate_quality_score(event: EventCreate | dict[str, Any]) -> int:
    """Calculate quality score for an event based on filled fields.

    Args:
        event: EventCreate or dict with event data

    Returns:
        Quality score (0-50)
    """
    score = 0

    def get_val(field: str) -> Any:
        if isinstance(event, dict):
            return event.get(field)
        return getattr(event, field, None)

    # Description (>50 chars)
    desc = get_val("description")
    if desc and len(str(desc)) > 50:
        score += QUALITY_WEIGHTS["description"]

    # Image
    if get_val("image_url") or get_val("source_image_url"):
        score += QUALITY_WEIGHTS["image_url"]

    # End date
    if get_val("end_date"):
        score += QUALITY_WEIGHTS["end_date"]

    # Times
    if get_val("start_time"):
        score += QUALITY_WEIGHTS["start_time"]
    if get_val("end_time"):
        score += QUALITY_WEIGHTS["end_time"]

    # Price info
    if get_val("price_info"):
        score += QUALITY_WEIGHTS["price_info"]

    # Coordinates
    if get_val("latitude") and get_val("longitude"):
        score += QUALITY_WEIGHTS["coordinates"]

    # Organizer
    if get_val("organizer_name"):
        score += QUALITY_WEIGHTS["organizer_name"]

    # Category
    if get_val("category_id") or get_val("category_slugs"):
        score += QUALITY_WEIGHTS["category_id"]

    # External URL
    if get_val("external_url"):
        score += QUALITY_WEIGHTS["external_url"]

    return score


def is_cross_source_duplicate(
    event: EventCreate,
    candidate: dict[str, Any],
    title_threshold: float = 0.85,
    venue_threshold: float = 0.7,
) -> bool:
    """Check if event is a duplicate of a candidate from the database.

    Criteria:
    1. Same start_date (exact)
    2. Title similarity >= threshold
    3. Same city OR same venue (if available)

    Args:
        event: New event to check
        candidate: Existing event from DB
        title_threshold: Minimum title similarity
        venue_threshold: Minimum venue similarity

    Returns:
        True if they are duplicates
    """
    # Must have same start date
    candidate_date = candidate.get("start_date")
    if isinstance(candidate_date, str):
        candidate_date = date.fromisoformat(candidate_date)

    if event.start_date != candidate_date:
        return False

    # Check title similarity
    similarity = title_similarity(event.title, candidate.get("title", ""))
    if similarity < title_threshold:
        return False

    # Check city OR venue match
    event_city = normalize_city(event.city)
    candidate_city = normalize_city(candidate.get("city"))

    if event_city and candidate_city and event_city == candidate_city:
        return True

    # Fallback to venue check
    if event.venue_name and candidate.get("venue_name"):
        venue_sim = title_similarity(event.venue_name, candidate.get("venue_name", ""))
        if venue_sim >= venue_threshold:
            return True

    # If no city/venue to compare, rely on title similarity alone if very high
    if similarity >= 0.95:
        return True

    return False


def merge_events(
    existing: dict[str, Any],
    new: EventCreate,
) -> tuple[dict[str, Any], list[str]]:
    """Merge new event data into existing event.

    Strategy:
    - Keep existing values if present
    - Fill empty fields with new event's values
    - For description: keep the longer one

    Args:
        existing: Existing event from DB
        new: New event with potentially better data

    Returns:
        Tuple of (merged event dict, list of fields that were updated)
    """
    merged = existing.copy()
    fields_updated = []

    for field in MERGEABLE_FIELDS:
        existing_val = merged.get(field)
        new_val = getattr(new, field, None)

        # Skip if new value is empty
        if new_val is None or new_val == "" or new_val == []:
            continue

        # Fill empty fields
        if not existing_val:
            merged[field] = new_val
            fields_updated.append(field)
            continue

        # Special case: description - prefer longer
        if field == "description":
            existing_len = len(str(existing_val)) if existing_val else 0
            new_len = len(str(new_val)) if new_val else 0
            if new_len > existing_len + 50:  # Only if significantly longer
                merged[field] = new_val
                fields_updated.append(field)

        # Special case: category_slugs - merge lists
        if field == "category_slugs" and new_val:
            existing_cats = set(existing_val or [])
            new_cats = set(new_val or [])
            merged_cats = existing_cats | new_cats
            if merged_cats != existing_cats:
                merged[field] = list(merged_cats)
                fields_updated.append(field)

    if fields_updated:
        logger.debug(
            "Merged event fields",
            title=existing.get("title", "")[:50],
            fields=fields_updated,
        )

    return merged, fields_updated


def should_update_event(
    existing: dict[str, Any],
    new: EventCreate,
    min_improvement: int = 5,
) -> bool:
    """Decide if merging the new event would improve the existing one.

    Args:
        existing: Existing event from DB
        new: New event to potentially merge
        min_improvement: Minimum score improvement to justify update

    Returns:
        True if update would add value
    """
    existing_score = calculate_quality_score(existing)
    new_score = calculate_quality_score(new)

    # Check if merge would add new fields
    _, fields_updated = merge_events(existing, new)

    if not fields_updated:
        return False

    # Estimate improvement
    improvement = 0
    for field in fields_updated:
        if field in QUALITY_WEIGHTS:
            improvement += QUALITY_WEIGHTS[field]
        elif field == "description":
            improvement += QUALITY_WEIGHTS["description"]

    logger.debug(
        "Update evaluation",
        title=existing.get("title", "")[:40],
        existing_score=existing_score,
        new_score=new_score,
        fields_to_add=fields_updated,
        improvement=improvement,
    )

    return improvement >= min_improvement


@dataclass
class DeduplicationResult:
    """Result of cross-source deduplication."""

    action: str  # "insert", "merge", "skip"
    event_id: str | None = None  # UUID of affected event
    existing_id: str | None = None  # UUID of existing duplicate
    fields_merged: list[str] | None = None
    quality_before: int = 0
    quality_after: int = 0


class CrossSourceDeduplicator:
    """Cross-source deduplication handler.

    Finds duplicates across different sources and merges them
    to keep the most complete data.
    """

    def __init__(self, supabase_client: Any):
        """Initialize with Supabase client.

        Args:
            supabase_client: SupabaseClient instance for DB queries
        """
        self.client = supabase_client
        self._candidate_cache: dict[str, list[dict]] = {}

    async def find_candidates(
        self,
        start_date: date,
        city: str | None,
        exclude_source: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find potential duplicate candidates from DB.

        Args:
            start_date: Event start date
            city: Event city (normalized)
            exclude_source: Source ID to exclude from results

        Returns:
            List of candidate events from DB (with location data flattened)
        """
        # Cache key
        cache_key = f"{start_date.isoformat()}:{normalize_city(city)}"

        if cache_key in self._candidate_cache:
            candidates = self._candidate_cache[cache_key]
        else:
            # Query DB for candidates with JOIN to event_locations
            # Using PostgREST embedded resources syntax
            query = (
                self.client._client.table("events")
                .select("*, event_locations(city, province, name, address)")
                .eq("start_date", start_date.isoformat())
            )

            response = query.limit(50).execute()
            raw_candidates = response.data if response.data else []

            # Flatten location data into each event dict for easier access
            candidates = []
            for event in raw_candidates:
                location = event.pop("event_locations", None)
                if location:
                    # Flatten location fields with prefix to avoid conflicts
                    event["city"] = location.get("city")
                    event["province"] = location.get("province")
                    event["venue_name"] = location.get("name") or event.get("venue_name")
                    event["address"] = location.get("address") or event.get("address")
                candidates.append(event)

            # Filter by city if specified (now that we have the data)
            if city:
                normalized_city = normalize_city(city)
                candidates = [
                    c for c in candidates
                    if normalized_city in normalize_city(c.get("city") or "")
                ]

            # Cache for this session
            self._candidate_cache[cache_key] = candidates

        # Filter out same source if specified
        if exclude_source:
            candidates = [
                c for c in candidates
                if c.get("source") != exclude_source
            ]

        return candidates

    async def find_duplicate(
        self,
        event: EventCreate,
        title_threshold: float = 0.85,
    ) -> dict[str, Any] | None:
        """Find a duplicate event in the database.

        Args:
            event: Event to check
            title_threshold: Minimum title similarity

        Returns:
            Duplicate event dict if found, None otherwise
        """
        candidates = await self.find_candidates(
            start_date=event.start_date,
            city=event.city,
            exclude_source=event.source_id,
        )

        for candidate in candidates:
            if is_cross_source_duplicate(event, candidate, title_threshold):
                logger.debug(
                    "Cross-source duplicate found",
                    new_title=event.title[:50],
                    existing_title=candidate.get("title", "")[:50],
                    existing_source=candidate.get("source"),
                )
                return candidate

        return None

    async def process_event(
        self,
        event: EventCreate,
        title_threshold: float = 0.85,
    ) -> DeduplicationResult:
        """Process an event for cross-source deduplication.

        Args:
            event: Event to process
            title_threshold: Minimum title similarity for duplicate detection

        Returns:
            DeduplicationResult with action taken
        """
        # Find duplicate
        existing = await self.find_duplicate(event, title_threshold)

        if not existing:
            # No duplicate - will be inserted normally
            return DeduplicationResult(action="insert")

        existing_id = existing.get("id")
        existing_score = calculate_quality_score(existing)

        # Check if update would improve the event
        if should_update_event(existing, event):
            merged, fields = merge_events(existing, event)
            merged_score = calculate_quality_score(merged)

            return DeduplicationResult(
                action="merge",
                existing_id=existing_id,
                fields_merged=fields,
                quality_before=existing_score,
                quality_after=merged_score,
            )

        # Duplicate but no improvement - skip
        return DeduplicationResult(
            action="skip",
            existing_id=existing_id,
            quality_before=existing_score,
        )

    async def record_contribution(
        self,
        event_id: str,
        source_id: str,
        external_id: str | None,
        external_url: str | None,
        fields_contributed: list[str],
        quality_score: int,
        is_primary: bool = False,
    ) -> None:
        """Record a source's contribution to an event.

        Args:
            event_id: UUID of the event
            source_id: UUID of the source
            external_id: Original ID from source
            external_url: Original URL from source
            fields_contributed: List of fields this source provided
            quality_score: Quality score of this contribution
            is_primary: Whether this is the primary (first) source
        """
        try:
            await self.client._client.table("event_source_contributions").upsert(
                {
                    "event_id": event_id,
                    "source_id": source_id,
                    "external_id": external_id,
                    "external_url": external_url,
                    "fields_contributed": fields_contributed,
                    "quality_score": quality_score,
                    "is_primary": is_primary,
                },
                on_conflict="event_id,source_id",
            ).execute()
        except Exception as e:
            logger.warning(
                "Failed to record contribution",
                event_id=event_id,
                source_id=source_id,
                error=str(e),
            )

    def clear_cache(self) -> None:
        """Clear the candidate cache."""
        self._candidate_cache.clear()
