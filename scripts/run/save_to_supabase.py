#!/usr/bin/env python3
"""Script to scrape Madrid events and save them to Supabase.

Usage:
    # Dry run (no save)
    python scripts/save_to_supabase.py --dry-run

    # Save to Supabase
    python scripts/save_to_supabase.py

    # Limit events
    python scripts/save_to_supabase.py --limit 50
"""

import asyncio
import sys
from pathlib import Path

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.adapters import get_adapter
from src.config.settings import get_settings
from src.core.supabase_client import get_supabase_client
from src.logging.logger import get_logger

logger = get_logger(__name__)


async def save_events_to_supabase(
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Scrape Madrid events and save to Supabase.

    Args:
        limit: Max events to save (None = all)
        dry_run: If True, don't save to database

    Returns:
        Stats dict
    """
    settings = get_settings()

    print("\n" + "=" * 60)
    print("💾 SAVE EVENTS TO SUPABASE")
    print("=" * 60)
    print(f"\n📋 Configuration:")
    print(f"   - Dry Run: {dry_run}")
    print(f"   - Limit: {limit or 'all'}")
    print(f"   - LLM Enabled: {settings.llm_enabled}")

    # Get Madrid adapter
    adapter_class = get_adapter("madrid_datos_abiertos")
    if not adapter_class:
        print("❌ Adapter not found!")
        return {}

    # Scrape events
    print("\n🔄 Scraping events from Madrid API...")
    async with adapter_class() as adapter:
        batch = await adapter.scrape()

    print(f"   Found: {batch.total_found} events")
    print(f"   Parsed: {batch.success_count} events")

    if batch.error_count > 0:
        print(f"   Errors: {batch.error_count}")

    # Limit if specified
    if limit and limit < len(batch.events):
        batch.events = batch.events[:limit]
        print(f"   Limited to: {len(batch.events)} events")

    if dry_run:
        print("\n🔸 DRY RUN - Not saving to database")
        print(f"   Would save {len(batch.events)} events")

        # Show sample
        print("\n📋 Sample events that would be saved:")
        for event in batch.events[:5]:
            print(f"   - {event.title[:50]}... ({event.start_date})")

        return {"would_save": len(batch.events)}

    # Save to Supabase
    print("\n💾 Saving to Supabase...")
    supabase = get_supabase_client()
    stats = await supabase.save_batch(batch, skip_existing=True)

    print("\n" + "-" * 60)
    print("📊 RESULTS")
    print("-" * 60)
    print(f"   Inserted: {stats['inserted']}")
    print(f"   Updated: {stats['updated']}")
    print(f"   Skipped (existing): {stats['skipped']}")
    print(f"   Failed: {stats['failed']}")

    print("\n" + "=" * 60)
    print("✅ COMPLETED")
    print("=" * 60 + "\n")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Save Madrid events to Supabase")
    parser.add_argument("--limit", type=int, help="Max events to save")
    parser.add_argument("--dry-run", action="store_true", help="Don't save to database")

    args = parser.parse_args()

    asyncio.run(save_events_to_supabase(
        limit=args.limit,
        dry_run=args.dry_run,
    ))
