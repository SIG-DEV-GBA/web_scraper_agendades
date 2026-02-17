#!/usr/bin/env python
"""Run Bronze pipeline for non-Viralagenda sources: scrape -> LLM enrich -> geocode -> insert.

Usage:
    python scripts/run_bronze.py --source navarra_cultura --dry-run
    python scripts/run_bronze.py --source canarias_lagenda --no-dry-run --limit 10
    python scripts/run_bronze.py --all --no-dry-run
    python scripts/run_bronze.py --list
"""

import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adapters.bronze_scraper_adapter import BronzeScraperAdapter, BRONZE_SOURCES
from src.core.event_model import EventBatch
from src.core.llm_enricher import get_llm_enricher, SourceTier
from src.core.image_resolver import get_image_resolver
from src.core.supabase_client import get_supabase_client
from src.logging import get_logger

logger = get_logger(__name__)

# Non-Viralagenda Bronze sources
BRONZE_NON_VIRAL = [slug for slug in BRONZE_SOURCES if not slug.startswith("viralagenda_")]


def get_bronze_sources() -> list[str]:
    """Get list of non-Viralagenda Bronze source slugs."""
    return BRONZE_NON_VIRAL


async def run_bronze_pipeline(
    sources: list[str],
    dry_run: bool = True,
    llm_enabled: bool = True,
    images_enabled: bool = True,
    fetch_details: bool = False,
    limit: int | None = None,
) -> dict[str, dict]:
    """Run the Bronze pipeline for specified sources.

    Args:
        sources: List of source slugs to process
        dry_run: If True, don't insert to database
        llm_enabled: If True, apply LLM enrichment
        images_enabled: If True, resolve images from Unsplash
        fetch_details: If True, fetch detail pages for descriptions
        limit: Max events to process per source (for testing)

    Returns:
        Dict mapping source slug to results
    """
    results = {}
    total_events = 0
    total_inserted = 0
    total_skipped = 0
    total_failed = 0

    # Initialize clients
    supabase = get_supabase_client()
    enricher = get_llm_enricher() if llm_enabled else None
    image_resolver = get_image_resolver() if images_enabled else None

    print("=" * 70)
    print("BRONZE PIPELINE (Non-Viralagenda)")
    print("=" * 70)
    print(f"Sources: {len(sources)}")
    print(f"Dry run: {dry_run}")
    print(f"LLM enrichment: {llm_enabled}")
    print(f"Unsplash images: {images_enabled and image_resolver and image_resolver.is_enabled}")
    print(f"Fetch details: {fetch_details}")
    print(f"Limit per source: {limit or 'None'}")
    print("-" * 70)

    for source_slug in sources:
        print(f"\n[{source_slug}] Starting...")

        try:
            # 1. Scrape events
            adapter = BronzeScraperAdapter(source_slug)
            raw_events = await adapter.fetch_events(enrich=False, fetch_details=fetch_details)

            if not raw_events:
                print(f"[{source_slug}] No events found")
                results[source_slug] = {"fetched": 0, "inserted": 0, "skipped": 0, "failed": 0}
                continue

            print(f"[{source_slug}] Fetched {len(raw_events)} events")

            # Apply limit if specified
            if limit and len(raw_events) > limit:
                raw_events = raw_events[:limit]
                print(f"[{source_slug}] Limited to {limit} events for testing")

            # 2. Parse events to EventCreate
            events = []
            for raw in raw_events:
                event = adapter.parse_event(raw)
                if event:
                    events.append(event)

            print(f"[{source_slug}] Parsed {len(events)} valid events")

            # 3. Filter out past events (start_date must be >= today)
            today = date.today()
            events_before = len(events)
            events = [e for e in events if e.start_date >= today]
            filtered_out = events_before - len(events)
            if filtered_out > 0:
                print(f"[{source_slug}] Filtered out {filtered_out} past events (before {today})")
            print(f"[{source_slug}] {len(events)} future events to process")

            # 3. LLM enrichment (categorías, summary, precio)
            if llm_enabled and enricher and enricher.is_enabled and events:
                print(f"[{source_slug}] Enriching with LLM...")

                # Prepare events for LLM
                events_for_llm = []
                for i, event in enumerate(events):
                    events_for_llm.append({
                        "id": event.external_id or str(i),
                        "title": event.title,
                        "description": event.description or "",
                        "venue_name": event.venue_name,
                        "city": event.city,
                        "province": event.province,
                        "comunidad_autonoma": event.comunidad_autonoma,
                        "price_info": event.price_info,
                    })

                # Run LLM enrichment (Bronze tier for web sources)
                enrichments = enricher.enrich_batch(
                    events_for_llm,
                    batch_size=10,
                    tier=SourceTier.BRONCE,
                )

                # Apply enrichments to events and collect image keywords
                image_keywords_map = {}  # event_id -> (keywords, category)
                for event in events:
                    eid = event.external_id
                    if eid and eid in enrichments:
                        enrichment = enrichments[eid]
                        # Apply category_slugs
                        if enrichment.category_slugs:
                            event.category_slugs = enrichment.category_slugs
                        # Apply summary
                        if enrichment.summary:
                            event.summary = enrichment.summary
                        # Apply description if generated
                        if enrichment.description and not event.description:
                            event.description = enrichment.description
                        # Apply price info (only if not already set from scraping)
                        if enrichment.is_free is not None and event.is_free is None:
                            event.is_free = enrichment.is_free
                        if enrichment.price is not None and event.price is None:
                            event.price = enrichment.price
                            event.is_free = False
                        if enrichment.price_details and not event.price_info:
                            event.price_info = enrichment.price_details
                        # Store image keywords for later resolution
                        if enrichment.image_keywords:
                            category = enrichment.category_slugs[0] if enrichment.category_slugs else "default"
                            image_keywords_map[eid] = (enrichment.image_keywords, category)

                print(f"[{source_slug}] Enriched {len(enrichments)} events")

                # 3.5 Resolve images from Unsplash using LLM keywords
                if images_enabled and image_resolver and image_resolver.is_enabled and image_keywords_map:
                    print(f"[{source_slug}] Resolving images from Unsplash...")
                    images_resolved = 0
                    for event in events:
                        eid = event.external_id
                        if eid in image_keywords_map and not event.source_image_url:
                            keywords, category = image_keywords_map[eid]
                            image_data = image_resolver.resolve_image_full(keywords, category)
                            if image_data:
                                event.source_image_url = image_data.url
                                # Store attribution info
                                event.image_author = image_data.author
                                event.image_author_url = image_data.author_url
                                event.image_source_url = image_data.unsplash_url
                                images_resolved += 1
                    print(f"[{source_slug}] Resolved {images_resolved} images from Unsplash")

            # 4. Insert to database (geocoding happens automatically in save_batch)
            if not dry_run:
                from datetime import datetime
                config = BRONZE_SOURCES[source_slug]
                batch = EventBatch(
                    source_id=source_slug,
                    source_name=config.name,
                    ccaa=config.ccaa,
                    scraped_at=datetime.now().isoformat(),
                    events=events,
                    total_found=len(raw_events),
                )
                # Cross-source dedup now works with event_locations JOIN
                stats = await supabase.save_batch(batch, skip_existing=True, cross_source_dedup=True)

                results[source_slug] = {
                    "fetched": len(raw_events),
                    "parsed": len(events),
                    "inserted": stats["inserted"],
                    "skipped": stats["skipped"],
                    "merged": stats.get("merged", 0),
                    "failed": stats["failed"],
                }

                total_inserted += stats["inserted"]
                total_skipped += stats["skipped"]
                total_failed += stats["failed"]

                print(f"[{source_slug}] Inserted: {stats['inserted']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}")
            else:
                results[source_slug] = {
                    "fetched": len(raw_events),
                    "parsed": len(events),
                    "inserted": 0,
                    "skipped": 0,
                    "failed": 0,
                    "dry_run": True,
                }
                print(f"[{source_slug}] DRY RUN - would insert {len(events)} events")

            total_events += len(events)

        except Exception as e:
            logger.error("source_pipeline_error", source=source_slug, error=str(e))
            print(f"[{source_slug}] ERROR: {e}")
            results[source_slug] = {"error": str(e)}
            total_failed += 1

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total sources processed: {len(sources)}")
    print(f"Total events parsed: {total_events}")
    if not dry_run:
        print(f"Total inserted: {total_inserted}")
        print(f"Total skipped: {total_skipped}")
        print(f"Total failed: {total_failed}")
    else:
        print("(Dry run - no database changes)")
    print("=" * 70)

    return results


def main():
    parser = argparse.ArgumentParser(description="Run Bronze scraping pipeline (non-Viralagenda)")
    parser.add_argument(
        "--source", "-s",
        help="Source slug to process (e.g., navarra_cultura, canarias_lagenda)",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Process all Bronze sources (excluding Viralagenda)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Don't insert to database (default: True)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Actually insert to database",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM enrichment",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Disable Unsplash image resolution",
    )
    parser.add_argument(
        "--fetch-details",
        action="store_true",
        help="Fetch detail pages for descriptions (slower but more complete)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of events to process per source (for testing)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available Bronze sources",
    )

    args = parser.parse_args()

    # List sources
    if args.list:
        print("Available Bronze sources (non-Viralagenda):")
        for slug in sorted(BRONZE_NON_VIRAL):
            config = BRONZE_SOURCES[slug]
            print(f"  {slug}: {config.ccaa} / {config.province or 'N/A'}")
        return

    # Determine sources to process
    sources = []

    if args.all:
        sources = BRONZE_NON_VIRAL
    elif args.source:
        if args.source in BRONZE_NON_VIRAL:
            sources = [args.source]
        elif args.source in BRONZE_SOURCES:
            print(f"'{args.source}' is a Viralagenda source. Use run_viralagenda.py instead.")
            return
        else:
            print(f"Unknown source: {args.source}")
            print(f"Available: {', '.join(sorted(BRONZE_NON_VIRAL))}")
            return
    else:
        parser.print_help()
        return

    # Handle dry_run logic
    dry_run = not args.no_dry_run

    # Run pipeline
    asyncio.run(run_bronze_pipeline(
        sources=sources,
        dry_run=dry_run,
        llm_enabled=not args.no_llm,
        images_enabled=not args.no_images,
        fetch_details=args.fetch_details,
        limit=args.limit,
    ))


if __name__ == "__main__":
    main()
