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
CCAA_CALENDARS = {
    "andalucía": "c0ecdd57-3afe-419a-8164-b58b3fa49af6",
    "aragón": "eebc93e1-e2a3-466f-9d19-681a9a12d379",
    "asturias": "204d4609-2513-4c78-aa7d-1d57df965cf9",
    "islas baleares": "f77b0b73-c9e8-42e7-a5de-f3b075000bb3",
    "canarias": "0b5d5367-9e55-4189-a413-07ab0d26382b",
    "cantabria": "50a6e772-a004-4fd4-8589-e0f2f24a3df1",
    "castilla-la mancha": "99a0629d-caf3-49ea-9c1a-42865a28efed",
    "castilla y león": "139f9549-4c80-4278-9e41-07f4814719e0",
    "cataluña": "ca25eb5e-0012-4fae-af61-505a27aa604b",
    "comunidad de madrid": "75235734-4fca-4299-8663-4ff894ecb156",
    "madrid": "75235734-4fca-4299-8663-4ff894ecb156",
    "comunidad valenciana": "175e520f-3145-4fc6-90ad-942c8674e7ae",
    "valencia": "175e520f-3145-4fc6-90ad-942c8674e7ae",
    "extremadura": "abeaf767-1b22-4db4-889e-6cf61735b51d",
    "galicia": "588d002f-8ae6-4a0e-8cef-6bbaedfe44d3",
    "región de murcia": "262ec6bf-a98e-4665-b6b2-500c24db8d83",
    "murcia": "262ec6bf-a98e-4665-b6b2-500c24db8d83",
    "navarra": "cd79db72-096a-44fa-9331-53f8eb7456a5",
    "país vasco": "019ee009-51e5-436c-8f20-b65262b3c6c9",
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

            # Use detected CCAA if it differs from source (fixes cross-region events)
            final_ccaa = event.comunidad_autonoma
            if detected_ccaa and detected_ccaa != event.comunidad_autonoma:
                self.logger.info(
                    "ccaa_corrected",
                    event_id=event_id,
                    city=event.city,
                    source_ccaa=event.comunidad_autonoma,
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
        """Save registration info to event_registration table."""
        if not event.registration_url:
            return True

        try:
            data = {
                "event_id": event_id,
                "registration_url": event.registration_url,
                "requires_registration": True,
            }
            self._client.table("event_registration").insert(data).execute()
            return True
        except Exception as e:
            self.logger.warning("Failed to save registration", event_id=event_id, error=str(e))
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
            # Model-only fields not in DB
            "online_url",
            "accessibility_info",
            "excluded_days",
            # source_id is removed because model contains slug, but DB needs UUID
            # The resolved UUID is set separately via source_uuid parameter
            "source_id",
            # Image attribution - not in events table yet
            "image_author",
            "image_author_url",
            "image_source_url",
            # source_image_url is for pending approval workflow
            # For scraper imports, we copy directly to image_url
            "source_image_url",
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

            # Save registration info
            if event.registration_url:
                await self._save_registration(event_id, event)

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
    ) -> dict[str, int]:
        """Save a batch of events to Supabase.

        Args:
            batch: EventBatch to save
            skip_existing: Skip events that already exist (by external_id)

        Returns:
            Dict with counts: inserted, updated, skipped, failed
        """
        stats = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}

        if not batch.events:
            self.logger.info("Empty batch, nothing to save")
            return stats

        # Pre-load caches for faster processing
        await self._ensure_categories_loaded()
        await self._ensure_sources_loaded()

        # Always get existing external_ids to know which to update vs insert
        all_ids = [e.external_id for e in batch.events if e.external_id]
        existing_ids = await self.get_existing_external_ids(all_ids) if all_ids else set()

        for event in batch.events:
            # Skip existing if configured
            if skip_existing and event.external_id in existing_ids:
                stats["skipped"] += 1
                continue

            # Insert or upsert
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
                else:
                    stats["failed"] += 1

        self.logger.info("Batch save completed", source=batch.source_id, **stats)
        return stats

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
