"""Supabase client facade -- delegates to specialised sub-modules.

This is the public entry-point.  All other code should import
``SupabaseClient`` and ``get_supabase_client`` from here (or from
``src.core.db`` which re-exports them).
"""

from typing import Any

from supabase import Client, create_client

from src.config import get_settings
from src.core.event_model import EventBatch, EventCreate
from src.logging import get_logger

# Sub-modules
from src.core.db.audit import compute_content_hash, log_audit
from src.core.db.event_builder import prepare_event_data, get_filled_fields
from src.core.db import event_store
from src.core.db import relations
from src.core.db.relations import normalize_ccaa, CCAA_CALENDARS, CCAA_OFFICIAL_NAMES


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
    # Resolve helpers (cache-backed)
    # ==========================================

    async def resolve_category_id(self, category_slug: str | None) -> str | None:
        """Resolve category slug to UUID."""
        if not category_slug:
            return None

        categories = await self._ensure_categories_loaded()
        slug_lower = category_slug.lower().strip()

        if slug_lower in categories:
            return categories[slug_lower]

        self.logger.warning("Category not found", category_slug=category_slug)
        return None

    async def resolve_source_id(self, source_slug: str | None) -> str | None:
        """Resolve source slug to UUID from scraper_sources table."""
        if not source_slug:
            return None

        sources = await self._ensure_sources_loaded()

        if source_slug in sources:
            return sources[source_slug]

        self.logger.warning("Source not found in scraper_sources", source_slug=source_slug)
        return None

    # ==========================================
    # Audit / hashing  (static, delegated)
    # ==========================================

    @staticmethod
    def _compute_content_hash(data: dict[str, Any]) -> str:
        return compute_content_hash(data)

    def _log_audit(
        self,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        entity_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        log_audit(self._client, action, entity_type, entity_id, entity_name, details)

    # ==========================================
    # Event data preparation  (delegated)
    # ==========================================

    def _prepare_event_data(self, event: EventCreate, source_uuid: str | None = None) -> dict[str, Any]:
        return prepare_event_data(event, source_uuid=source_uuid)

    def _get_filled_fields(self, event: EventCreate) -> list[str]:
        return get_filled_fields(event)

    # ==========================================
    # Relations  (delegated)
    # ==========================================

    async def _save_location(self, event_id: str, event: EventCreate) -> bool:
        return await relations.save_location(self._client, event_id, event)

    async def _save_organizer(self, event_id: str, event: EventCreate) -> bool:
        return await relations.save_organizer(self._client, event_id, event)

    async def _save_registration(self, event_id: str, event: EventCreate) -> bool:
        return await relations.save_registration(self._client, event_id, event)

    async def _save_accessibility(self, event_id: str, event: EventCreate) -> bool:
        return await relations.save_accessibility(self._client, event_id, event)

    async def _save_contact(self, event_id: str, event: EventCreate) -> bool:
        return await relations.save_contact(self._client, event_id, event)

    async def _save_online(self, event_id: str, event: EventCreate) -> bool:
        return await relations.save_online(self._client, event_id, event)

    def _get_calendar_ids_for_event(self, event: EventCreate) -> list[str]:
        return relations.get_calendar_ids_for_event(event)

    async def _link_event_to_calendars(self, event_id: str, calendar_ids: list[str]) -> bool:
        return await relations.link_event_to_calendars(self._client, event_id, calendar_ids)

    async def _link_event_to_categories(self, event_id: str, category_ids: list[str]) -> bool:
        return await relations.link_event_to_categories(self._client, event_id, category_ids)

    # ==========================================
    # Event CRUD  (delegated)
    # ==========================================

    async def insert_event(self, event: EventCreate, generate_embedding: bool = True) -> dict[str, Any] | None:
        """Insert a single event with all related data."""
        source_uuid = await self.resolve_source_id(event.source_id)
        return await event_store.insert_event(
            self._client, event, source_uuid,
            resolve_category_id=self.resolve_category_id,
            generate_embedding=generate_embedding,
        )

    async def upsert_event(self, event: EventCreate) -> dict[str, Any] | None:
        """Upsert event (insert or update based on external_id)."""
        source_uuid = await self.resolve_source_id(event.source_id)
        return await event_store.upsert_event(self._client, event, source_uuid)

    async def event_exists(self, external_id: str) -> bool:
        return await event_store.event_exists(self._client, external_id)

    async def get_existing_external_ids(self, external_ids: list[str]) -> set[str]:
        return await event_store.get_existing_external_ids(self._client, external_ids)

    async def get_existing_content_hashes(self, external_ids: list[str]) -> dict[str, str]:
        return await event_store.get_existing_content_hashes(self._client, external_ids)

    async def _get_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        return await event_store.get_event_by_id(self._client, event_id)

    async def _update_event_fields(
        self,
        event_id: str,
        merged_data: dict[str, Any],
        fields_to_update: list[str],
    ) -> dict[str, Any] | None:
        return await event_store.update_event_fields(
            self._client, event_id, merged_data, fields_to_update,
        )

    # ==========================================
    # Batch Operations  (delegated)
    # ==========================================

    async def save_batch(
        self,
        batch: EventBatch,
        skip_existing: bool = True,
        cross_source_dedup: bool = True,
    ) -> dict[str, int]:
        """Save a batch of events to Supabase."""
        # Pre-load caches for faster processing
        await self._ensure_categories_loaded()
        await self._ensure_sources_loaded()

        return await event_store.save_batch(
            self._client,
            batch,
            resolve_source_id=self.resolve_source_id,
            resolve_category_id=self.resolve_category_id,
            skip_existing=skip_existing,
            cross_source_dedup=cross_source_dedup,
        )

    # ==========================================
    # Query Operations  (delegated)
    # ==========================================

    async def get_events_by_source(self, source_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return await event_store.get_events_by_source(self._client, source_id, limit)

    async def get_upcoming_events(self, ccaa: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return await event_store.get_upcoming_events(self._client, ccaa, limit)


# Singleton instance
_client: SupabaseClient | None = None


def get_supabase_client() -> SupabaseClient:
    """Get or create Supabase client singleton."""
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client
