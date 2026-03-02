"""Backward-compatible re-export.  Use ``src.core.db`` instead."""

from src.core.db import SupabaseClient, get_supabase_client  # noqa: F401

# Re-export constants and helpers that may be imported from here
from src.core.db.relations import (  # noqa: F401
    CCAA_CALENDARS,
    CCAA_OFFICIAL_NAMES,
    normalize_ccaa,
)
from src.core.db.event_builder import PUBLIC_CALENDAR_ID  # noqa: F401
from src.core.db.audit import SCRAPER_BOT_USER_ID  # noqa: F401
