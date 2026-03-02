"""Event CRUD and batch operations against Supabase."""

from datetime import datetime
from typing import Any

from supabase import Client

from src.core.embeddings import get_embeddings_client
from src.core.event_model import EventBatch, EventCreate
from src.logging import get_logger

from src.core.db.audit import log_audit
from src.core.db.event_builder import get_filled_fields, prepare_event_data
from src.core.db import relations

logger = get_logger(__name__)


async def insert_event(
    client: Client,
    event: EventCreate,
    source_uuid: str | None,
    resolve_category_id,
    generate_embedding: bool = True,
) -> dict[str, Any] | None:
    """Insert a single event with all related data.

    Creates:
    1. Event record (events table)
    2. Embedding (via UPDATE - Supabase triggers block INSERT)
    3. Location (event_locations table)
    4. Calendar links (event_calendars junction table)
    5. Category links (event_categories junction table) - N:M
    6. Organizer (event_organizers table)

    Args:
        client: Supabase client instance
        event: Event to insert
        source_uuid: Resolved UUID from scraper_sources table
        resolve_category_id: Async callable to resolve category slug -> UUID
        generate_embedding: Whether to generate embedding (default: True)

    Returns:
        Inserted event data or None on failure
    """
    try:
        data = prepare_event_data(event, source_uuid=source_uuid)

        # Insert event first (without embedding - Supabase triggers reset it)
        response = client.table("events").insert(data).execute()

        if not response.data:
            return None

        inserted_event = response.data[0]
        event_id = inserted_event["id"]

        # Generate and UPDATE embedding separately (triggers don't block UPDATE)
        if generate_embedding:
            embeddings_client = get_embeddings_client()
            embedding = embeddings_client.generate_for_event(
                title=event.title,
                description=event.description,
            )
            if embedding:
                client.table("events").update({
                    "embedding": embedding,
                    "embedding_pending": False,
                }).eq("id", event_id).execute()
            else:
                logger.warning("embedding_failed", title=event.title[:50])

        # Save location data
        await relations.save_location(client, event_id, event)

        # Link to calendars
        calendar_ids = relations.get_calendar_ids_for_event(event)
        await relations.link_event_to_calendars(client, event_id, calendar_ids)

        # Link to categories (N:M) - supports multiple categories
        if event.category_slugs:
            category_ids = []
            for slug in event.category_slugs:
                cat_id = await resolve_category_id(slug)
                if cat_id:
                    category_ids.append(cat_id)
            if category_ids:
                await relations.link_event_to_categories(client, event_id, category_ids)

        # Save organizer
        if event.organizer:
            await relations.save_organizer(client, event_id, event)

        # Save registration info (if has URL, requires_registration, or registration_info)
        if event.registration_url or event.requires_registration or event.registration_info:
            await relations.save_registration(client, event_id, event)

        # Save accessibility info
        if event.accessibility:
            await relations.save_accessibility(client, event_id, event)

        # Save contact info
        if event.contact:
            await relations.save_contact(client, event_id, event)

        # Save online event info (YouTube, Zoom, etc.)
        if event.online_url:
            await relations.save_online(client, event_id, event)

        # Audit log
        log_audit(
            client,
            action="create",
            entity_type="event",
            entity_id=event_id,
            entity_name=event.title,
            details={"source": event.source_id, "external_id": event.external_id},
        )

        return inserted_event

    except Exception as e:
        logger.error("Failed to insert event", error=str(e), title=event.title)
        return None


async def upsert_event(
    client: Client,
    event: EventCreate,
    source_uuid: str | None,
) -> dict[str, Any] | None:
    """Upsert event (insert or update based on external_id)."""
    try:
        data = prepare_event_data(event, source_uuid=source_uuid)
        data["updated_at"] = datetime.now().isoformat()

        response = (
            client.table("events")
            .upsert(data, on_conflict="external_id")
            .execute()
        )

        if response.data:
            log_audit(
                client,
                action="upsert",
                entity_type="event",
                entity_id=response.data[0].get("id"),
                entity_name=event.title,
                details={"source": event.source_id, "external_id": event.external_id},
            )

        return response.data[0] if response.data else None

    except Exception as e:
        logger.error("Failed to upsert event", error=str(e), title=event.title)
        return None


async def event_exists(client: Client, external_id: str) -> bool:
    """Check if an event with the given external_id exists."""
    response = (
        client.table("events")
        .select("id")
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )
    return len(response.data) > 0


async def get_existing_external_ids(client: Client, external_ids: list[str]) -> set[str]:
    """Get set of external_ids that already exist in database."""
    if not external_ids:
        return set()

    response = (
        client.table("events")
        .select("external_id")
        .in_("external_id", external_ids)
        .execute()
    )
    return {row["external_id"] for row in response.data}


async def get_existing_content_hashes(client: Client, external_ids: list[str]) -> dict[str, str]:
    """Get map of external_id -> content_hash for existing events."""
    if not external_ids:
        return {}

    response = (
        client.table("events")
        .select("external_id,content_hash")
        .in_("external_id", external_ids)
        .execute()
    )
    return {
        row["external_id"]: row.get("content_hash", "")
        for row in response.data
        if row.get("content_hash")
    }


async def get_event_by_id(client: Client, event_id: str) -> dict[str, Any] | None:
    """Get event by UUID."""
    try:
        response = (
            client.table("events")
            .select("*")
            .eq("id", event_id)
            .single()
            .execute()
        )
        return response.data
    except Exception as e:
        logger.error("Failed to get event", event_id=event_id, error=str(e))
        return None


async def update_event_fields(
    client: Client,
    event_id: str,
    merged_data: dict[str, Any],
    fields_to_update: list[str],
) -> dict[str, Any] | None:
    """Update specific fields of an event."""
    if not fields_to_update:
        return None

    try:
        # Only update the fields that changed
        update_data = {k: merged_data[k] for k in fields_to_update if k in merged_data}
        update_data["updated_at"] = "now()"

        # Serialize time/date objects to strings for JSON compatibility
        from datetime import date, time
        for key, val in update_data.items():
            if isinstance(val, time):
                update_data[key] = val.isoformat()
            elif isinstance(val, date):
                update_data[key] = val.isoformat()

        response = (
            client.table("events")
            .update(update_data)
            .eq("id", event_id)
            .execute()
        )

        if response.data:
            log_audit(
                client,
                action="update",
                entity_type="event",
                entity_id=event_id,
                entity_name=response.data[0].get("title", ""),
                details={"fields_updated": fields_to_update},
            )

        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(
            "Failed to update event fields",
            event_id=event_id,
            fields=fields_to_update,
            error=str(e),
        )
        return None


async def save_batch(
    client: Client,
    batch: EventBatch,
    resolve_source_id,
    resolve_category_id,
    skip_existing: bool = True,
    cross_source_dedup: bool = True,
) -> dict[str, int]:
    """Save a batch of events to Supabase.

    Args:
        client: Supabase client instance
        batch: EventBatch to save
        resolve_source_id: Async callable to resolve source slug -> UUID
        resolve_category_id: Async callable to resolve category slug -> UUID
        skip_existing: Skip events that already exist (by external_id)
        cross_source_dedup: Enable cross-source deduplication

    Returns:
        Dict with counts: inserted, updated, skipped, merged, failed
    """
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "merged": 0, "failed": 0}

    if not batch.events:
        logger.info("Empty batch, nothing to save")
        return stats

    # Always get existing external_ids to know which to update vs insert
    all_ids = [e.external_id for e in batch.events if e.external_id]
    existing_ids = await get_existing_external_ids(client, all_ids) if all_ids else set()

    # Get content hashes for existing events (for change detection)
    existing_hashes = await get_existing_content_hashes(client, all_ids) if all_ids else {}

    # Initialize cross-source deduplicator if enabled
    # NOTE: deduplicator needs a SupabaseClient facade reference, not a raw Client.
    # We import lazily and pass the raw client wrapped in a minimal interface.
    deduplicator = None
    if cross_source_dedup:
        from src.utils.cross_source_dedup import CrossSourceDeduplicator
        # CrossSourceDeduplicator expects an object with .client attribute
        # We create a tiny wrapper for backward compat
        deduplicator = CrossSourceDeduplicator(_ClientWrapper(client))

    for event in batch.events:
        source_uuid = await resolve_source_id(event.source_id)

        # Skip existing from same source if configured
        if skip_existing and event.external_id in existing_ids:
            # Check content_hash: if content unchanged, truly skip
            if event.external_id in existing_hashes:
                new_data = prepare_event_data(event, source_uuid=source_uuid)
                new_hash = new_data.get("content_hash", "")
                old_hash = existing_hashes.get(event.external_id, "")
                if new_hash and old_hash and new_hash != old_hash:
                    # Content changed -- upsert instead of skip
                    result = await upsert_event(client, event, source_uuid)
                    if result:
                        stats["updated"] += 1
                    else:
                        stats["failed"] += 1
                    continue
            stats["skipped"] += 1
            continue

        # Cross-source deduplication check
        if deduplicator and event.external_id not in existing_ids:
            dedup_result = await deduplicator.process_event(event)

            if dedup_result.action == "merge":
                # Found duplicate from another source - merge and update
                from src.utils.cross_source_dedup import merge_events, calculate_quality_score

                # Get existing event to merge
                existing_event = await get_event_by_id(client, dedup_result.existing_id)
                if existing_event:
                    merged_data, fields_updated = merge_events(existing_event, event)

                    # Update the existing event with merged data
                    result = await update_event_fields(
                        client,
                        dedup_result.existing_id,
                        merged_data,
                        fields_updated,
                    )

                    if result:
                        stats["merged"] += 1

                        # Record this source's contribution
                        if source_uuid:
                            deduplicator.record_contribution(
                                event_id=dedup_result.existing_id,
                                source_id=source_uuid,
                                external_id=event.external_id,
                                external_url=event.external_url,
                                fields_contributed=fields_updated,
                                quality_score=calculate_quality_score(event),
                                is_primary=False,
                            )
                    else:
                        stats["failed"] += 1
                    continue

            elif dedup_result.action == "skip":
                # Duplicate found but no improvement - skip
                stats["skipped"] += 1
                continue

        # Insert or upsert (same source)
        if event.external_id in existing_ids:
            result = await upsert_event(client, event, source_uuid)
            if result:
                stats["updated"] += 1
            else:
                stats["failed"] += 1
        else:
            result = await insert_event(
                client, event, source_uuid, resolve_category_id,
            )
            if result:
                stats["inserted"] += 1

                # Record primary source contribution
                if deduplicator and result.get("id"):
                    from src.utils.cross_source_dedup import calculate_quality_score
                    if source_uuid:
                        deduplicator.record_contribution(
                            event_id=result["id"],
                            source_id=source_uuid,
                            external_id=event.external_id,
                            external_url=event.external_url,
                            fields_contributed=get_filled_fields(event),
                            quality_score=calculate_quality_score(event),
                            is_primary=True,
                        )
            else:
                stats["failed"] += 1

    # Clear deduplicator cache
    if deduplicator:
        deduplicator.clear_cache()

    logger.info("Batch save completed", source=batch.source_id, **stats)
    return stats


async def get_events_by_source(
    client: Client,
    source_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get events from a specific source."""
    response = (
        client.table("events")
        .select("*")
        .eq("source", source_id)
        .order("start_date", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data


async def get_upcoming_events(
    client: Client,
    ccaa: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get upcoming events, optionally filtered by CCAA."""
    query = (
        client.table("events")
        .select("*")
        .gte("start_date", datetime.now().date().isoformat())
        .eq("is_published", True)
        .order("start_date")
        .limit(limit)
    )

    if ccaa:
        query = query.eq("comunidad_autonoma", ccaa)

    response = query.execute()
    return response.data


class _ClientWrapper:
    """Minimal wrapper so CrossSourceDeduplicator can access ._client.

    CrossSourceDeduplicator accesses `self.client._client` to reach
    the raw Supabase Client, so we expose _client directly.
    """

    def __init__(self, raw_client: Client) -> None:
        self._client = raw_client
