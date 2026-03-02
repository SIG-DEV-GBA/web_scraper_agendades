"""Audit logging and content hashing for event change detection."""

import hashlib
import os
from typing import Any

from supabase import Client

from src.logging import get_logger

logger = get_logger(__name__)

# Bot user for audit trail (auth.users)
SCRAPER_BOT_USER_ID = os.getenv(
    "SCRAPER_BOT_USER_ID", "f1637f49-d45b-49ee-a493-1e69daceaa9b"
)


def compute_content_hash(data: dict[str, Any]) -> str:
    """Compute a hash of event content fields for change detection.

    Uses title + description + start_date + start_time + end_date + end_time
    to detect meaningful content changes between scrapes.
    """
    parts = [
        str(data.get("title", "")),
        str(data.get("description", ""))[:500],
        str(data.get("start_date", "")),
        str(data.get("start_time", "")),
        str(data.get("end_date", "")),
        str(data.get("end_time", "")),
        str(data.get("modality", "")),
        str(data.get("price", "")),
        str(data.get("external_url", "")),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def log_audit(
    client: Client,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    entity_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Write an entry to audit_logs for the scraper bot."""
    try:
        client.table("audit_logs").insert({
            "user_id": SCRAPER_BOT_USER_ID,
            "user_email": "scraper-bot@solidaridadintergeneracional.es",
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_name": (entity_name or "")[:200],
            "details": details,
        }).execute()
    except Exception as e:
        logger.warning("audit_log_failed", error=str(e))
