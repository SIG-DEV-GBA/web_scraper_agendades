#!/usr/bin/env python
"""Test insertion for all Gold and Silver sources.

Inserts at least 5 events per province across all available sources.
"""

import asyncio
import os
import sys
from collections import defaultdict
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["LLM_ENABLED"] = "true"

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter, GOLD_SOURCES
from src.adapters.silver_rss_adapter import SilverRSSAdapter, SILVER_RSS_SOURCES
from src.core.event_model import EventBatch
from src.core.llm_enricher import SourceTier, get_llm_enricher
from src.core.supabase_client import get_supabase_client
from src.logging.logger import get_logger

logger = get_logger(__name__)

# Target events per province
MIN_PER_PROVINCE = 5


async def process_gold_source(source_slug: str, limit: int = 50) -> dict:
    """Process a Gold source and return events grouped by province."""
    print(f"\n{'='*60}")
    print(f"GOLD: {source_slug.upper()}")
    print("=" * 60)

    config = GOLD_SOURCES[source_slug]
    adapter = GoldAPIAdapter(source_slug)

    raw_events = await adapter.fetch_events(max_pages=3)
    print(f"  Raw: {len(raw_events)}")

    today = date.today()
    events_by_province = defaultdict(list)

    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event and event.start_date:
            try:
                event_date = datetime.fromisoformat(str(event.start_date).replace("Z", "")).date()
                if event_date >= today:
                    province = event.province or "Sin provincia"
                    if len(events_by_province[province]) < MIN_PER_PROVINCE:
                        events_by_province[province].append(event)
            except (ValueError, TypeError):
                pass

    # Collect all events
    all_events = []
    for province, events in events_by_province.items():
        print(f"  {province}: {len(events)} eventos")
        all_events.extend(events)

    return {
        "source": source_slug,
        "ccaa": config.ccaa,
        "events": all_events,
        "by_province": dict(events_by_province),
    }


async def process_silver_source(source_slug: str) -> dict:
    """Process a Silver RSS source and return events grouped by province."""
    print(f"\n{'='*60}")
    print(f"SILVER: {source_slug.upper()}")
    print("=" * 60)

    config = SILVER_RSS_SOURCES[source_slug]
    adapter = SilverRSSAdapter(source_slug)

    raw_events = await adapter.fetch_events()
    print(f"  Raw: {len(raw_events)}")

    today = date.today()
    events_by_province = defaultdict(list)

    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event and event.start_date:
            try:
                event_date = event.start_date
                if isinstance(event_date, str):
                    event_date = datetime.fromisoformat(event_date.replace("Z", "")).date()
                if event_date >= today:
                    province = event.province or "Sin provincia"
                    if len(events_by_province[province]) < MIN_PER_PROVINCE:
                        events_by_province[province].append(event)
            except (ValueError, TypeError):
                pass

    all_events = []
    for province, events in events_by_province.items():
        print(f"  {province}: {len(events)} eventos")
        all_events.extend(events)

    return {
        "source": source_slug,
        "ccaa": config.ccaa,
        "events": all_events,
        "by_province": dict(events_by_province),
    }


async def enrich_and_insert(results: list[dict], dry_run: bool = False) -> dict:
    """Enrich all events with LLM and insert to Supabase."""
    print(f"\n{'#'*60}")
    print("ENRICHMENT & INSERTION")
    print("#" * 60)

    enricher = get_llm_enricher()
    client = get_supabase_client()

    total_inserted = 0
    total_skipped = 0
    total_failed = 0
    province_counts = defaultdict(int)

    for result in results:
        source = result["source"]
        ccaa = result["ccaa"]
        events = result["events"]

        if not events:
            print(f"\n{source}: Sin eventos")
            continue

        print(f"\n{source}: {len(events)} eventos")

        # Prepare for LLM
        events_for_llm = []
        for e in events:
            events_for_llm.append({
                "id": e.external_id,
                "title": e.title,
                "description": e.description or "",
                "@type": e.category_name or "",
                "audience": "",
                "price_info": e.price_info or "",
            })

        # Enrich
        enrichments = enricher.enrich_batch(events_for_llm, batch_size=10, tier=SourceTier.ORO)
        print(f"  Enriched: {len(enrichments)}")

        # Apply enrichments
        for event in events:
            enrichment = enrichments.get(event.external_id)
            if enrichment:
                event.category_slugs = enrichment.category_slugs
                if enrichment.summary:
                    event.summary = enrichment.summary
                if enrichment.price is not None:
                    event.price = enrichment.price
                    event.is_free = False
                if enrichment.price_details:
                    details = enrichment.price_details.strip()
                    if details.lower() in ["gratis", "gratuito", "entrada libre"]:
                        event.price_info = None
                        event.is_free = True
                    else:
                        event.price_info = details if details else None
                elif enrichment.price is not None:
                    event.price_info = None

        if dry_run:
            print(f"  [DRY RUN] Would insert {len(events)} events")
            for province, pevents in result["by_province"].items():
                province_counts[f"{ccaa} - {province}"] += len(pevents)
            continue

        # Get source config name
        source_name = GOLD_SOURCES.get(source, SILVER_RSS_SOURCES.get(source)).name

        # Insert
        batch = EventBatch(
            source_id=source,
            source_name=source_name,
            ccaa=ccaa,
            scraped_at=datetime.now().isoformat(),
            events=events,
            total_found=len(events),
        )

        stats = await client.save_batch(batch, skip_existing=True)
        total_inserted += stats["inserted"]
        total_skipped += stats["skipped"]
        total_failed += stats["failed"]

        print(f"  Inserted: {stats['inserted']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}")

        for province, pevents in result["by_province"].items():
            province_counts[f"{ccaa} - {province}"] += len(pevents)

    return {
        "inserted": total_inserted,
        "skipped": total_skipped,
        "failed": total_failed,
        "by_province": dict(province_counts),
    }


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Don't insert to database")
    args = parser.parse_args()

    print("#" * 60)
    print("# TEST INSERTION: ALL GOLD + SILVER SOURCES")
    print(f"# Target: {MIN_PER_PROVINCE} events per province")
    print(f"# Dry run: {args.dry_run}")
    print("#" * 60)

    results = []

    # Process Gold sources
    for source_slug in GOLD_SOURCES.keys():
        try:
            result = await process_gold_source(source_slug)
            results.append(result)
        except Exception as e:
            print(f"  ERROR: {e}")

    # Process Silver sources
    for source_slug in SILVER_RSS_SOURCES.keys():
        try:
            result = await process_silver_source(source_slug)
            results.append(result)
        except Exception as e:
            print(f"  ERROR: {e}")

    # Enrich and insert
    stats = await enrich_and_insert(results, dry_run=args.dry_run)

    # Final summary
    print(f"\n{'#'*60}")
    print("FINAL SUMMARY")
    print("#" * 60)

    print(f"\nTotal inserted: {stats['inserted']}")
    print(f"Total skipped: {stats['skipped']}")
    print(f"Total failed: {stats['failed']}")

    print(f"\nEvents by province:")
    for province, count in sorted(stats["by_province"].items()):
        status = "OK" if count >= MIN_PER_PROVINCE else "LOW"
        print(f"  [{status}] {province}: {count}")

    total_provinces = len(stats["by_province"])
    print(f"\nTotal provinces covered: {total_provinces}")


if __name__ == "__main__":
    asyncio.run(main())
