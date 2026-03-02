"""Event data preparation for database insertion."""

import os
from datetime import datetime
from typing import Any

from src.core.event_model import EventCreate

from src.core.db.audit import SCRAPER_BOT_USER_ID, compute_content_hash

# Calendar IDs - Events are linked to multiple calendars hierarchically
PUBLIC_CALENDAR_ID = os.getenv(
    "PUBLIC_CALENDAR_ID", "00000000-0000-0000-0000-000000000001"
)


def prepare_event_data(event: EventCreate, source_uuid: str | None = None) -> dict[str, Any]:
    """Prepare event data for database insertion.

    Args:
        event: Event to prepare
        source_uuid: Resolved UUID from scraper_sources table (optional)
    """
    data = event.model_dump(exclude_none=True, mode="json")

    # Explicitly include is_free even when None (DB interprets None as "unknown")
    # This prevents DB default (True) from being applied incorrectly
    data["is_free"] = event.is_free

    # Always set calendar_id to public calendar (required field)
    data["calendar_id"] = PUBLIC_CALENDAR_ID

    # Map LocationType enum to Supabase modality field
    # LocationType values are already Spanish: presencial, online, hibrido
    if "location_type" in data:
        val = data["location_type"]
        # Get the enum value (already in Spanish) or use as-is if string
        raw_value = val.value if hasattr(val, "value") else val
        # Validate it's a valid modality, default to presencial
        valid_modalities = {"presencial", "online", "hibrido"}
        data["modality"] = raw_value if raw_value in valid_modalities else "presencial"
        del data["location_type"]

    # Copy source_image_url to image_url (for scraper imports, skip approval workflow)
    if not data.get("image_url") and data.get("source_image_url"):
        data["image_url"] = data["source_image_url"]

    # Remove fields not in events table schema
    # These are either stored in other tables or not needed
    fields_to_remove = [
        # Stored in event_locations table
        "venue_name",
        "address",
        "district",
        "city",
        "postal_code",
        "latitude",
        "longitude",
        "province",
        "comunidad_autonoma",
        "country",
        # Stored in event_organizers table
        "organizer",
        "organizer_name",
        "organizer_type",
        # Stored in event_categories table (N:M) - no longer a column
        "category_id",
        "category_name",
        "category_slug",
        "category_slugs",
        # Stored in event_registration table
        "registration_url",
        "requires_registration",
        "registration_info",
        # Stored in event_locations table (details field)
        "location_details",
        # Model-only fields not in DB
        "online_url",
        "accessibility",  # Stored in event_accessibility table
        "accessibility_info",  # Legacy text field
        "contact",  # Stored in event_contact table
        "excluded_days",
        # source_id is removed because model contains slug, but DB needs UUID
        # The resolved UUID is set separately via source_uuid parameter
        "source_id",
        # Image attribution - not in events table yet
        "image_author",
        "image_author_url",
        "image_source_url",
        # Note: source_image_url IS in the events table schema (kept for storage)
        # Other fields not in schema
        "all_day",
    ]
    for field in fields_to_remove:
        data.pop(field, None)

    # Set source_id to resolved UUID AFTER removing fields
    # (model has slug, DB needs UUID)
    if source_uuid:
        data["source_id"] = source_uuid

    # Set bot user for audit trail
    data["created_by"] = SCRAPER_BOT_USER_ID

    # Set content_hash for change detection
    data["content_hash"] = compute_content_hash(data)

    # Set published_at on insert (scraper events are published immediately)
    if "published_at" not in data or not data.get("published_at"):
        data["published_at"] = datetime.now().isoformat()

    return data


def get_filled_fields(event: EventCreate) -> list[str]:
    """Get list of fields that have values in the event."""
    filled = []
    check_fields = [
        "description", "summary", "image_url", "source_image_url",
        "end_date", "start_time", "end_time", "price_info",
        "latitude", "longitude", "organizer_name", "venue_name",
        "address", "external_url", "category_id",
    ]
    for field in check_fields:
        val = getattr(event, field, None)
        if val is not None and val != "" and val != []:
            filled.append(field)
    return filled
