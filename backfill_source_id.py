#!/usr/bin/env python
"""Backfill source_id UUID for existing events.

Usage:
    python backfill_source_id.py              # Update all events
    python backfill_source_id.py --dry-run    # Test without updating
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.supabase_client import get_supabase_client
from src.logging.logger import get_logger

logger = get_logger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Backfill source_id UUID")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test without updating database",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("BACKFILL SOURCE_ID UUID")
    print("=" * 60)

    client = get_supabase_client()

    # Load scraper sources
    sources = await client._ensure_sources_loaded()
    print(f"\nLoaded {len(sources)} scraper sources:")
    for slug, uuid in sources.items():
        print(f"  {slug}: {uuid}")

    # Get all events with null source_id
    result = client.client.table("events").select(
        "id, external_id, source_id"
    ).is_("source_id", "null").execute()

    events = result.data
    print(f"\nEvents with NULL source_id: {len(events)}")

    if not events:
        print("\nAll events already have source_id!")
        return

    # Update each event
    updated = 0
    skipped = 0

    for event in events:
        event_id = event["id"]
        external_id = event["external_id"] or ""

        # Extract source slug from external_id (e.g., "madrid_datos_abiertos_123" -> "madrid_datos_abiertos")
        source_slug = None
        for slug in sources.keys():
            if external_id.startswith(slug):
                source_slug = slug
                break

        if not source_slug:
            print(f"  SKIP: {external_id} - no matching source")
            skipped += 1
            continue

        source_uuid = sources[source_slug]

        if args.dry_run:
            print(f"  DRY RUN: {external_id} -> {source_uuid}")
            updated += 1
            continue

        try:
            client.client.table("events").update({
                "source_id": source_uuid
            }).eq("id", event_id).execute()
            print(f"  OK: {external_id}")
            updated += 1
        except Exception as e:
            print(f"  ERROR: {external_id} - {e}")
            skipped += 1

    print("\n" + "=" * 60)
    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
