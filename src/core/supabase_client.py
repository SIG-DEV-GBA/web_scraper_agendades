"""Supabase client for event storage operations."""

from datetime import datetime
from typing import Any

from supabase import Client, create_client

from src.config import get_settings
from src.core.event_model import EventBatch, EventCreate
from src.core.embeddings import get_embeddings_client
from src.core.geocoder import get_geocoder
from src.logging import get_logger

logger = get_logger(__name__)

# Calendar IDs - Events are linked to multiple calendars hierarchically
PUBLIC_CALENDAR_ID = "00000000-0000-0000-0000-000000000001"

# CCAA Calendar mapping (comunidad_autonoma name -> calendar_id)
# Includes official names and common aliases
CCAA_CALENDARS = {
    "andalucía": "c0ecdd57-3afe-419a-8164-b58b3fa49af6",
    "aragón": "eebc93e1-e2a3-466f-9d19-681a9a12d379",
    "asturias": "204d4609-2513-4c78-aa7d-1d57df965cf9",
    "principado de asturias": "204d4609-2513-4c78-aa7d-1d57df965cf9",
    "islas baleares": "f77b0b73-c9e8-42e7-a5de-f3b075000bb3",
    "illes balears": "f77b0b73-c9e8-42e7-a5de-f3b075000bb3",
    "canarias": "0b5d5367-9e55-4189-a413-07ab0d26382b",
    "cantabria": "50a6e772-a004-4fd4-8589-e0f2f24a3df1",
    "castilla-la mancha": "99a0629d-caf3-49ea-9c1a-42865a28efed",
    "castilla y león": "139f9549-4c80-4278-9e41-07f4814719e0",
    "cataluña": "ca25eb5e-0012-4fae-af61-505a27aa604b",
    "catalunya": "ca25eb5e-0012-4fae-af61-505a27aa604b",
    "comunidad de madrid": "75235734-4fca-4299-8663-4ff894ecb156",
    "madrid": "75235734-4fca-4299-8663-4ff894ecb156",
    "comunidad valenciana": "175e520f-3145-4fc6-90ad-942c8674e7ae",
    "valencia": "175e520f-3145-4fc6-90ad-942c8674e7ae",
    "extremadura": "abeaf767-1b22-4db4-889e-6cf61735b51d",
    "galicia": "588d002f-8ae6-4a0e-8cef-6bbaedfe44d3",
    "región de murcia": "262ec6bf-a98e-4665-b6b2-500c24db8d83",
    "murcia": "262ec6bf-a98e-4665-b6b2-500c24db8d83",
    "navarra": "cd79db72-096a-44fa-9331-53f8eb7456a5",
    "comunidad foral de navarra": "cd79db72-096a-44fa-9331-53f8eb7456a5",
    "país vasco": "019ee009-51e5-436c-8f20-b65262b3c6c9",
    "euskadi": "019ee009-51e5-436c-8f20-b65262b3c6c9",
    "la rioja": "e069b836-c437-4ea4-9cf9-fc9222985889",
    "ceuta": "4e337434-dddb-4dc4-b049-0ab46f751f3c",
    "melilla": "3ac0c74b-5b2b-4854-81fb-79f43c75c980",
}


class SupabaseClient:
    """Client for interacting with Supabase events table."""

    def __init__(self) -> None:
        """Initialize Supabase client."""
        settings = get_settings()
        self._client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        self.logger = get_logger("supabase_client")

        # Caches loaded dynamically
        self._categories_cache: dict[str, str] | None = None  # slug -> id
        self._sources_cache: dict[str, str] | None = None  # slug -> uuid

    @property
    def client(self) -> Client:
        """Get the Supabase client instance."""
        return self._client

    # ==========================================
    # Dynamic Cache Loading
    # ==========================================

    async def _ensure_categories_loaded(self) -> dict[str, str]:
        """Load categories from DB if not cached."""
        if self._categories_cache is None:
            response = self._client.table("categories").select("id, slug").execute()
            self._categories_cache = {cat["slug"].lower(): cat["id"] for cat in response.data}
            self.logger.info("Loaded categories", count=len(self._categories_cache))
        return self._categories_cache

    async def _ensure_sources_loaded(self) -> dict[str, str]:
        """Load scraper sources from DB if not cached."""
        if self._sources_cache is None:
            response = self._client.table("scraper_sources").select("id, slug").execute()
            self._sources_cache = {src["slug"]: src["id"] for src in response.data}
            self.logger.info("Loaded scraper sources", count=len(self._sources_cache))
        return self._sources_cache

    def reload_caches(self) -> None:
        """Force reload of caches."""
        self._categories_cache = None
        self._sources_cache = None

    # ==========================================
    # Category Operations
    # ==========================================

    async def resolve_category_id(self, category_slug: str | None) -> str | None:
        """Resolve category slug to UUID.

        Args:
            category_slug: DB category slug (e.g., "cultural", "social")

        Returns:
            Category UUID or None if not found
        """
        if not category_slug:
            return None

        categories = await self._ensure_categories_loaded()
        slug_lower = category_slug.lower().strip()

        if slug_lower in categories:
            return categories[slug_lower]

        self.logger.warning("Category not found", category_slug=category_slug)
        return None

    async def resolve_source_id(self, source_slug: str | None) -> str | None:
        """Resolve source slug to UUID from scraper_sources table.

        Args:
            source_slug: Source slug (e.g., "madrid_datos_abiertos", "euskadi_kulturklik")

        Returns:
            Source UUID or None if not found
        """
        if not source_slug:
            return None

        sources = await self._ensure_sources_loaded()

        if source_slug in sources:
            return sources[source_slug]

        self.logger.warning("Source not found in scraper_sources", source_slug=source_slug)
        return None

    # ==========================================
    # Location Operations
    # ==========================================

    async def _save_location(self, event_id: str, event: EventCreate) -> bool:
        """Save location to event_locations table.

        Fields in event_locations:
        - name, address, city, municipio, province, comunidad_autonoma,
        - country, postal_code, latitude, longitude, details, map_url

        Automatically geocodes if coordinates are missing but address/city available.
        """
        # Check if we have any location data
        has_location = any([
            event.venue_name,
            event.address,
            event.city,
            event.latitude,
            event.longitude,
        ])

        if not has_location:
            return True

        try:
            # Get coordinates from event or geocode if missing
            latitude = event.latitude
            longitude = event.longitude

            # Geocode if we have address/city but no coordinates
            # Also resolves the correct CCAA for the city
            detected_ccaa = None
            if latitude is None or longitude is None:
                has_geocodable = any([event.venue_name, event.address, event.city])
                if has_geocodable:
                    geocoder = get_geocoder()
                    result = await geocoder.geocode(
                        venue_name=event.venue_name,
                        address=event.address,
                        city=event.city,
                        province=event.province,
                        postal_code=event.postal_code,
                        comunidad_autonoma=event.comunidad_autonoma,
                    )
                    if result:
                        latitude = result.latitude
                        longitude = result.longitude
                        detected_ccaa = result.detected_ccaa
                        self.logger.debug(
                            "geocoded_location",
                            event_id=event_id,
                            lat=latitude,
                            lon=longitude,
                            confidence=result.confidence,
                            detected_ccaa=detected_ccaa,
                        )

            # CCAA resolution: trust source over geocoder detection
            # The source already knows the correct CCAA (e.g., canarias_lagenda = Canarias)
            # Geocoder can fail with ambiguous cities (Santa Cruz exists in Andalucía AND Canarias)
            final_ccaa = event.comunidad_autonoma
            if detected_ccaa and detected_ccaa != event.comunidad_autonoma:
                if event.comunidad_autonoma:
                    # Source has CCAA - trust it, just log the mismatch for debugging
                    self.logger.debug(
                        "ccaa_mismatch_ignored",
                        event_id=event_id,
                        city=event.city,
                        source_ccaa=event.comunidad_autonoma,
                        detected_ccaa=detected_ccaa,
                        reason="trusting source CCAA over geocoder detection",
                    )
                    # Keep final_ccaa = event.comunidad_autonoma (source wins)
                else:
                    # Source has no CCAA - use detected
                    self.logger.info(
                        "ccaa_filled_from_geocoder",
                        event_id=event_id,
                        city=event.city,
                        detected_ccaa=detected_ccaa,
                    )
                    final_ccaa = detected_ccaa

            data = {
                "event_id": event_id,
                "name": event.venue_name or "",
                "address": event.address or "",
                "city": event.city or "",
                "municipio": event.district or event.city or "",
                "province": event.province or "",
                "comunidad_autonoma": final_ccaa,
                "country": event.country or "España",
                "postal_code": event.postal_code or "",
            }

            # Add coordinates if available (from event or geocoding)
            if latitude is not None:
                data["latitude"] = latitude
            if longitude is not None:
                data["longitude"] = longitude

            # Add details if available (parking, access info, meeting point, etc.)
            if event.location_details:
                data["details"] = event.location_details

            self._client.table("event_locations").insert(data).execute()
            return True
        except Exception as e:
            self.logger.warning("Failed to save location", event_id=event_id, error=str(e))
            return False

    # ==========================================
    # Organizer Operations
    # ==========================================

    async def _save_organizer(self, event_id: str, event: EventCreate) -> bool:
        """Save organizer to event_organizers table."""
        organizer = event.organizer
        if not organizer:
            return True

        try:
            data = {
                "event_id": event_id,
                "name": organizer.name,
                "type": organizer.type.value if hasattr(organizer.type, "value") else organizer.type,
                "url": organizer.url,
                "logo_url": organizer.logo_url,
            }
            self._client.table("event_organizers").insert(data).execute()
            return True
        except Exception as e:
            self.logger.warning("Failed to save organizer", event_id=event_id, error=str(e))
            return False

    # ==========================================
    # Registration Operations
    # ==========================================

    async def _save_registration(self, event_id: str, event: EventCreate) -> bool:
        """Save registration info to event_registration table.

        Saves if:
        - event has registration_url, OR
        - event.requires_registration is True (e.g., registration via phone/email)
        - event has registration_info (instructions for how to register)
        """
        # Only save if we have registration data
        has_registration_data = any([
            event.registration_url,
            event.requires_registration,
            event.registration_info,
        ])
        if not has_registration_data:
            return True

        try:
            data = {
                "event_id": event_id,
                "requires_registration": event.requires_registration or bool(event.registration_url),
            }
            if event.registration_url:
                data["registration_url"] = event.registration_url
            if event.registration_info:
                data["registration_info"] = event.registration_info
            self._client.table("event_registration").insert(data).execute()
            return True
        except Exception as e:
            self.logger.warning("Failed to save registration", event_id=event_id, error=str(e))
            return False

    async def _save_accessibility(self, event_id: str, event: EventCreate) -> bool:
        """Save accessibility info to event_accessibility table."""
        if not event.accessibility:
            return True

        try:
            data = {
                "event_id": event_id,
                "wheelchair_accessible": event.accessibility.wheelchair_accessible,
                "sign_language": event.accessibility.sign_language,
                "hearing_loop": event.accessibility.hearing_loop,
                "braille_materials": event.accessibility.braille_materials,
                "other_facilities": event.accessibility.other_facilities,
                "notes": event.accessibility.notes,
            }
            self._client.table("event_accessibility").insert(data).execute()
            return True
        except Exception as e:
            self.logger.warning("Failed to save accessibility", event_id=event_id, error=str(e))
            return False

    async def _save_contact(self, event_id: str, event: EventCreate) -> bool:
        """Save contact info to event_contact table."""
        if not event.contact:
            return True

        # Only save if at least one field has data
        if not any([event.contact.name, event.contact.email, event.contact.phone, event.contact.info]):
            return True

        try:
            data = {
                "event_id": event_id,
                "name": event.contact.name,
                "email": event.contact.email,
                "phone": event.contact.phone,
                "info": event.contact.info,
            }
            # Remove None values
            data = {k: v for k, v in data.items() if v is not None}
            self._client.table("event_contact").insert(data).execute()
            return True
        except Exception as e:
            self.logger.warning("Failed to save contact", event_id=event_id, error=str(e))
            return False

    # ==========================================
    # Calendar Operations
    # ==========================================

    def _get_calendar_ids_for_event(self, event: EventCreate) -> list[str]:
        """Get list of calendar IDs for an event based on its location."""
        calendar_ids = [PUBLIC_CALENDAR_ID]

        if event.comunidad_autonoma:
            ccaa_lower = event.comunidad_autonoma.lower().strip()
            if ccaa_lower in CCAA_CALENDARS:
                calendar_ids.append(CCAA_CALENDARS[ccaa_lower])

        return calendar_ids

    async def _link_event_to_calendars(self, event_id: str, calendar_ids: list[str]) -> bool:
        """Link event to calendars via event_calendars junction table."""
        try:
            records = [{"event_id": event_id, "calendar_id": cid} for cid in calendar_ids]
            self._client.table("event_calendars").insert(records).execute()
            return True
        except Exception as e:
            self.logger.warning("Failed to link calendars", event_id=event_id, error=str(e))
            return False

    async def _link_event_to_categories(self, event_id: str, category_ids: list[str]) -> bool:
        """Link event to categories via event_categories junction table (N:M)."""
        if not category_ids:
            return True

        try:
            # Remove duplicates
            unique_ids = list(dict.fromkeys(category_ids))
            records = [{"event_id": event_id, "category_id": cid} for cid in unique_ids]
            self._client.table("event_categories").insert(records).execute()
            return True
        except Exception as e:
            self.logger.warning("Failed to link categories", event_id=event_id, error=str(e))
            return False

    # ==========================================
    # Event Data Preparation
    # ==========================================

    def _prepare_event_data(self, event: EventCreate, source_uuid: str | None = None) -> dict[str, Any]:
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

        # Map LocationType enum to Supabase modality values (Spanish)
        modality_mapping = {
            "physical": "presencial",
            "online": "online",
            "hybrid": "hibrido",
        }

        if "location_type" in data:
            val = data["location_type"]
            raw_value = val.value if hasattr(val, "value") else val
            data["modality"] = modality_mapping.get(raw_value, "presencial")
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

        return data

    # ==========================================
    # Event CRUD Operations
    # ==========================================

    async def insert_event(self, event: EventCreate, generate_embedding: bool = True) -> dict[str, Any] | None:
        """Insert a single event with all related data.

        Creates:
        1. Event record (events table)
        2. Embedding (via UPDATE - Supabase triggers block INSERT)
        3. Location (event_locations table)
        4. Calendar links (event_calendars junction table)
        5. Category links (event_categories junction table) - N:M
        6. Organizer (event_organizers table)

        Args:
            event: Event to insert
            generate_embedding: Whether to generate embedding (default: True)

        Returns:
            Inserted event data or None on failure
        """
        try:
            # Resolve source_id slug to UUID
            source_uuid = await self.resolve_source_id(event.source_id)
            data = self._prepare_event_data(event, source_uuid=source_uuid)

            # Insert event first (without embedding - Supabase triggers reset it)
            response = self._client.table("events").insert(data).execute()

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
                    self._client.table("events").update({
                        "embedding": embedding,
                        "embedding_pending": False,
                    }).eq("id", event_id).execute()
                else:
                    self.logger.warning("embedding_failed", title=event.title[:50])

            # Save location data
            await self._save_location(event_id, event)

            # Link to calendars
            calendar_ids = self._get_calendar_ids_for_event(event)
            await self._link_event_to_calendars(event_id, calendar_ids)

            # Link to categories (N:M) - supports multiple categories
            if event.category_slugs:
                category_ids = []
                for slug in event.category_slugs:
                    cat_id = await self.resolve_category_id(slug)
                    if cat_id:
                        category_ids.append(cat_id)
                if category_ids:
                    await self._link_event_to_categories(event_id, category_ids)

            # Save organizer
            if event.organizer:
                await self._save_organizer(event_id, event)

            # Save registration info (if has URL, requires_registration, or registration_info)
            if event.registration_url or event.requires_registration or event.registration_info:
                await self._save_registration(event_id, event)

            # Save accessibility info
            if event.accessibility:
                await self._save_accessibility(event_id, event)

            # Save contact info
            if event.contact:
                await self._save_contact(event_id, event)

            return inserted_event

        except Exception as e:
            self.logger.error("Failed to insert event", error=str(e), title=event.title)
            return None

    async def upsert_event(self, event: EventCreate) -> dict[str, Any] | None:
        """Upsert event (insert or update based on external_id)."""
        try:
            # Resolve source_id slug to UUID
            source_uuid = await self.resolve_source_id(event.source_id)
            data = self._prepare_event_data(event, source_uuid=source_uuid)
            data["updated_at"] = datetime.now().isoformat()

            response = (
                self._client.table("events")
                .upsert(data, on_conflict="external_id")
                .execute()
            )
            return response.data[0] if response.data else None

        except Exception as e:
            self.logger.error("Failed to upsert event", error=str(e), title=event.title)
            return None

    async def event_exists(self, external_id: str) -> bool:
        """Check if an event with the given external_id exists."""
        response = (
            self._client.table("events")
            .select("id")
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        return len(response.data) > 0

    async def get_existing_external_ids(self, external_ids: list[str]) -> set[str]:
        """Get set of external_ids that already exist in database."""
        if not external_ids:
            return set()

        response = (
            self._client.table("events")
            .select("external_id")
            .in_("external_id", external_ids)
            .execute()
        )
        return {row["external_id"] for row in response.data}

    # ==========================================
    # Batch Operations
    # ==========================================

    async def save_batch(
        self,
        batch: EventBatch,
        skip_existing: bool = True,
        cross_source_dedup: bool = True,
    ) -> dict[str, int]:
        """Save a batch of events to Supabase.

        Args:
            batch: EventBatch to save
            skip_existing: Skip events that already exist (by external_id)
            cross_source_dedup: Enable cross-source deduplication (merge duplicates from other sources)

        Returns:
            Dict with counts: inserted, updated, skipped, merged, failed
        """
        stats = {"inserted": 0, "updated": 0, "skipped": 0, "merged": 0, "failed": 0}

        if not batch.events:
            self.logger.info("Empty batch, nothing to save")
            return stats

        # Pre-load caches for faster processing
        await self._ensure_categories_loaded()
        await self._ensure_sources_loaded()

        # Always get existing external_ids to know which to update vs insert
        all_ids = [e.external_id for e in batch.events if e.external_id]
        existing_ids = await self.get_existing_external_ids(all_ids) if all_ids else set()

        # Initialize cross-source deduplicator if enabled
        deduplicator = None
        if cross_source_dedup:
            from src.utils.cross_source_dedup import CrossSourceDeduplicator
            deduplicator = CrossSourceDeduplicator(self)

        for event in batch.events:
            # Skip existing from same source if configured
            if skip_existing and event.external_id in existing_ids:
                stats["skipped"] += 1
                continue

            # Cross-source deduplication check
            if deduplicator and event.external_id not in existing_ids:
                dedup_result = await deduplicator.process_event(event)

                if dedup_result.action == "merge":
                    # Found duplicate from another source - merge and update
                    from src.utils.cross_source_dedup import merge_events, calculate_quality_score

                    # Get existing event to merge
                    existing_event = await self._get_event_by_id(dedup_result.existing_id)
                    if existing_event:
                        merged_data, fields_updated = merge_events(existing_event, event)

                        # Update the existing event with merged data
                        result = await self._update_event_fields(
                            dedup_result.existing_id,
                            merged_data,
                            fields_updated,
                        )

                        if result:
                            stats["merged"] += 1

                            # Record this source's contribution
                            source_uuid = await self.resolve_source_id(event.source_id)
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
                result = await self.upsert_event(event)
                if result:
                    stats["updated"] += 1
                else:
                    stats["failed"] += 1
            else:
                result = await self.insert_event(event)
                if result:
                    stats["inserted"] += 1

                    # Record primary source contribution
                    if deduplicator and result.get("id"):
                        from src.utils.cross_source_dedup import calculate_quality_score
                        source_uuid = await self.resolve_source_id(event.source_id)
                        if source_uuid:
                            deduplicator.record_contribution(
                                event_id=result["id"],
                                source_id=source_uuid,
                                external_id=event.external_id,
                                external_url=event.external_url,
                                fields_contributed=self._get_filled_fields(event),
                                quality_score=calculate_quality_score(event),
                                is_primary=True,
                            )
                else:
                    stats["failed"] += 1

        # Clear deduplicator cache
        if deduplicator:
            deduplicator.clear_cache()

        self.logger.info("Batch save completed", source=batch.source_id, **stats)
        return stats

    def _get_filled_fields(self, event: EventCreate) -> list[str]:
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

    async def _get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        """Get event by UUID."""
        try:
            response = (
                self._client.table("events")
                .select("*")
                .eq("id", event_id)
                .single()
                .execute()
            )
            return response.data
        except Exception as e:
            self.logger.error("Failed to get event", event_id=event_id, error=str(e))
            return None

    async def _update_event_fields(
        self,
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

            response = (
                self._client.table("events")
                .update(update_data)
                .eq("id", event_id)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            self.logger.error(
                "Failed to update event fields",
                event_id=event_id,
                fields=fields_to_update,
                error=str(e),
            )
            return None

    # ==========================================
    # Query Operations
    # ==========================================

    async def get_events_by_source(
        self,
        source_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get events from a specific source."""
        response = (
            self._client.table("events")
            .select("*")
            .eq("source", source_id)
            .order("start_date", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data

    async def get_upcoming_events(
        self,
        ccaa: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get upcoming events, optionally filtered by CCAA."""
        query = (
            self._client.table("events")
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


# Singleton instance
_client: SupabaseClient | None = None


def get_supabase_client() -> SupabaseClient:
    """Get or create Supabase client singleton."""
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client
