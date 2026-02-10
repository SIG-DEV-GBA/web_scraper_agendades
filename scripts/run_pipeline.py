#!/usr/bin/env python
"""Unified pipeline runner for all event sources.

This script runs the complete pipeline:
1. Scrape events from source
2. Filter past events (only future events)
3. LLM enrichment (categories, summary, price)
4. Image resolution (Unsplash)
5. Geocoding
6. Insert to database

Usage:
    # Single source
    python scripts/run_pipeline.py --source navarra_cultura --dry-run
    python scripts/run_pipeline.py --source navarra_cultura --no-dry-run

    # By tier
    python scripts/run_pipeline.py --tier bronze --dry-run
    python scripts/run_pipeline.py --tier gold --no-dry-run

    # By CCAA
    python scripts/run_pipeline.py --ccaa navarra --no-dry-run
    python scripts/run_pipeline.py --ccaa andalucia --dry-run

    # All sources
    python scripts/run_pipeline.py --all --dry-run

    # List available sources
    python scripts/run_pipeline.py --list

    # Options
    python scripts/run_pipeline.py --source navarra_cultura --no-llm --no-images
    python scripts/run_pipeline.py --source navarra_cultura --limit 10
"""

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adapters import ADAPTER_REGISTRY, get_adapter, list_adapters
from src.core.base_adapter import BaseAdapter
from src.core.event_model import EventBatch
from src.core.llm_enricher import get_llm_enricher, SourceTier
from src.core.image_resolver import get_image_resolver
from src.core.supabase_client import get_supabase_client
from src.logging import get_logger

logger = get_logger(__name__)

# Tier mapping for LLM model selection
TIER_MAP = {
    "gold": SourceTier.ORO,
    "silver": SourceTier.PLATA,
    "bronze": SourceTier.BRONCE,
}

# Source metadata (tier, ccaa) - this should eventually come from DB
SOURCE_METADATA = {
    # Gold tier
    "madrid_datos_abiertos": {"tier": "gold", "ccaa": "Comunidad de Madrid"},
    # Bronze tier
    "navarra_cultura": {"tier": "bronze", "ccaa": "Navarra"},
    # Add more as we migrate...
}


def get_sources_by_tier(tier: str) -> list[str]:
    """Get all source IDs for a given tier."""
    return [
        source_id
        for source_id, meta in SOURCE_METADATA.items()
        if meta.get("tier") == tier
    ]


def get_sources_by_ccaa(ccaa: str) -> list[str]:
    """Get all source IDs for a given CCAA."""
    ccaa_lower = ccaa.lower().replace("-", " ")
    ccaa_mapping = {
        "navarra": "Navarra",
        "madrid": "Comunidad de Madrid",
        "andalucia": "Andalucía",
        "galicia": "Galicia",
        "cataluna": "Cataluña",
        "catalunya": "Cataluña",
        "valencia": "Comunitat Valenciana",
        "pais vasco": "País Vasco",
        "euskadi": "País Vasco",
        "castilla y leon": "Castilla y León",
        "castilla leon": "Castilla y León",
        "aragon": "Aragón",
        "asturias": "Principado de Asturias",
        "cantabria": "Cantabria",
        "extremadura": "Extremadura",
        "murcia": "Región de Murcia",
        "canarias": "Canarias",
        "baleares": "Illes Balears",
        "la rioja": "La Rioja",
        "castilla la mancha": "Castilla-La Mancha",
    }

    ccaa_name = ccaa_mapping.get(ccaa_lower)
    if not ccaa_name:
        return []

    return [
        source_id
        for source_id, meta in SOURCE_METADATA.items()
        if meta.get("ccaa") == ccaa_name
    ]


async def run_pipeline(
    sources: list[str],
    dry_run: bool = True,
    llm_enabled: bool = True,
    images_enabled: bool = True,
    fetch_details: bool = True,
    limit: int | None = None,
) -> dict[str, dict]:
    """Run the unified pipeline for specified sources.

    Args:
        sources: List of source IDs to process
        dry_run: If True, don't insert to database
        llm_enabled: If True, apply LLM enrichment
        images_enabled: If True, resolve images from Unsplash
        fetch_details: If True, fetch detail pages
        limit: Max events per source (for testing)

    Returns:
        Dict mapping source_id to results
    """
    results = {}
    total_events = 0
    total_inserted = 0
    total_skipped = 0
    total_failed = 0

    # Initialize shared clients
    supabase = get_supabase_client()
    enricher = get_llm_enricher() if llm_enabled else None
    image_resolver = get_image_resolver() if images_enabled else None

    print("=" * 70)
    print("EVENT PIPELINE")
    print("=" * 70)
    print(f"Sources: {len(sources)}")
    print(f"Dry run: {dry_run}")
    print(f"LLM enrichment: {llm_enabled}")
    print(f"Unsplash images: {images_enabled and image_resolver and image_resolver.is_enabled}")
    print(f"Fetch details: {fetch_details}")
    print(f"Limit per source: {limit or 'None'}")
    print("-" * 70)

    for source_id in sources:
        print(f"\n[{source_id}] Starting...")

        try:
            # Get adapter class from registry
            adapter_class = get_adapter(source_id)
            if not adapter_class:
                print(f"[{source_id}] ERROR: Adapter not found in registry")
                results[source_id] = {"error": "Adapter not found"}
                continue

            # Instantiate adapter
            adapter: BaseAdapter = adapter_class()

            # Get tier for LLM model selection
            tier = SOURCE_METADATA.get(source_id, {}).get("tier", "bronze")
            source_tier = TIER_MAP.get(tier, SourceTier.BRONCE)

            # 1. Fetch events
            raw_events = await adapter.fetch_events(enrich=False, fetch_details=fetch_details)

            if not raw_events:
                print(f"[{source_id}] No events found")
                results[source_id] = {"fetched": 0, "inserted": 0, "skipped": 0, "failed": 0}
                continue

            print(f"[{source_id}] Fetched {len(raw_events)} events")

            # Apply limit if specified
            if limit and len(raw_events) > limit:
                raw_events = raw_events[:limit]
                print(f"[{source_id}] Limited to {limit} events for testing")

            # 2. Parse events
            events = []
            for raw in raw_events:
                event = adapter.parse_event(raw)
                if event:
                    events.append(event)

            print(f"[{source_id}] Parsed {len(events)} valid events")

            # 3. Filter past events (keep events that haven't ended yet)
            today = date.today()
            events_before = len(events)
            # Event is valid if end_date >= today (still ongoing) or start_date >= today (upcoming)
            events = [e for e in events if (e.end_date and e.end_date >= today) or e.start_date >= today]
            filtered_out = events_before - len(events)
            if filtered_out > 0:
                print(f"[{source_id}] Filtered out {filtered_out} past events (ended before {today})")
            print(f"[{source_id}] {len(events)} active/future events to process")

            if not events:
                results[source_id] = {"fetched": len(raw_events), "parsed": 0, "inserted": 0}
                continue

            # 4. LLM enrichment
            if llm_enabled and enricher and enricher.is_enabled and events:
                print(f"[{source_id}] Enriching with LLM ({tier} tier)...")

                events_for_llm = [
                    {
                        "id": event.external_id or str(i),
                        "title": event.title,
                        "description": event.description or "",
                        "venue_name": event.venue_name,
                        "city": event.city,
                        "province": event.province,
                        "comunidad_autonoma": event.comunidad_autonoma,
                        "price_info": event.price_info,
                    }
                    for i, event in enumerate(events)
                ]

                enrichments = enricher.enrich_batch(
                    events_for_llm,
                    batch_size=10,
                    tier=source_tier,
                )

                # Apply enrichments
                image_keywords_map = {}
                for event in events:
                    eid = event.external_id
                    if eid and eid in enrichments:
                        enrichment = enrichments[eid]
                        if enrichment.category_slugs:
                            event.category_slugs = enrichment.category_slugs
                        if enrichment.summary:
                            event.summary = enrichment.summary
                        if enrichment.description and not event.description:
                            event.description = enrichment.description
                        if enrichment.is_free is not None and event.is_free is None:
                            event.is_free = enrichment.is_free
                        if enrichment.price is not None and event.price is None:
                            event.price = enrichment.price
                            event.is_free = False
                        if enrichment.price_details and not event.price_info:
                            event.price_info = enrichment.price_details
                        if enrichment.image_keywords:
                            category = enrichment.category_slugs[0] if enrichment.category_slugs else "default"
                            image_keywords_map[eid] = (enrichment.image_keywords, category)

                print(f"[{source_id}] Enriched {len(enrichments)} events")

                # 5. Resolve images
                if images_enabled and image_resolver and image_resolver.is_enabled and image_keywords_map:
                    print(f"[{source_id}] Resolving images from Unsplash...")
                    images_resolved = 0
                    for event in events:
                        eid = event.external_id
                        if eid in image_keywords_map and not event.source_image_url:
                            keywords, category = image_keywords_map[eid]
                            image_data = image_resolver.resolve_image_full(keywords, category)
                            if image_data:
                                event.source_image_url = image_data.url
                                event.image_author = image_data.author
                                event.image_author_url = image_data.author_url
                                event.image_source_url = image_data.unsplash_url
                                images_resolved += 1
                    print(f"[{source_id}] Resolved {images_resolved} images from Unsplash")

            # 6. Insert to database
            if not dry_run:
                from datetime import datetime
                batch = EventBatch(
                    source_id=source_id,
                    source_name=adapter.source_name,
                    ccaa=adapter.ccaa,
                    scraped_at=datetime.now().isoformat(),
                    events=events,
                    total_found=len(raw_events),
                )
                stats = await supabase.save_batch(batch, skip_existing=True, cross_source_dedup=True)

                results[source_id] = {
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

                print(f"[{source_id}] Inserted: {stats['inserted']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}")
            else:
                results[source_id] = {
                    "fetched": len(raw_events),
                    "parsed": len(events),
                    "inserted": 0,
                    "skipped": 0,
                    "failed": 0,
                    "dry_run": True,
                }
                print(f"[{source_id}] DRY RUN - would insert {len(events)} events")

            total_events += len(events)

        except Exception as e:
            logger.error("pipeline_error", source=source_id, error=str(e))
            print(f"[{source_id}] ERROR: {e}")
            results[source_id] = {"error": str(e)}
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
    parser = argparse.ArgumentParser(
        description="Unified event pipeline runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_pipeline.py --source navarra_cultura --dry-run
  python scripts/run_pipeline.py --tier bronze --no-dry-run
  python scripts/run_pipeline.py --ccaa navarra --no-dry-run --limit 10
  python scripts/run_pipeline.py --list
        """
    )

    # Source selection (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--source", "-s",
        help="Single source ID to process",
    )
    source_group.add_argument(
        "--tier", "-t",
        choices=["gold", "silver", "bronze"],
        help="Process all sources of a tier",
    )
    source_group.add_argument(
        "--ccaa", "-c",
        help="Process all sources of a CCAA",
    )
    source_group.add_argument(
        "--all", "-a",
        action="store_true",
        help="Process all sources",
    )
    source_group.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available sources",
    )

    # Pipeline options
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
        "--no-details",
        action="store_true",
        help="Skip fetching detail pages",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit events per source (for testing)",
    )

    args = parser.parse_args()

    # Handle --list
    if args.list:
        print("Available sources:\n")
        print(f"{'Source ID':<30} {'Tier':<10} {'CCAA':<25}")
        print("-" * 65)
        for source_id in sorted(SOURCE_METADATA.keys()):
            meta = SOURCE_METADATA[source_id]
            print(f"{source_id:<30} {meta.get('tier', 'unknown'):<10} {meta.get('ccaa', 'unknown'):<25}")
        print(f"\nRegistered adapters: {list_adapters()}")
        return

    # Determine sources to process
    sources = []

    if args.source:
        sources = [args.source]
    elif args.tier:
        sources = get_sources_by_tier(args.tier)
        if not sources:
            print(f"No sources found for tier: {args.tier}")
            return
    elif args.ccaa:
        sources = get_sources_by_ccaa(args.ccaa)
        if not sources:
            print(f"No sources found for CCAA: {args.ccaa}")
            return
    elif args.all:
        sources = list(SOURCE_METADATA.keys())
    else:
        parser.print_help()
        return

    # Validate sources exist in registry
    available = list_adapters()
    valid_sources = []
    for s in sources:
        if s in available:
            valid_sources.append(s)
        else:
            print(f"Warning: Source '{s}' not found in adapter registry, skipping")

    if not valid_sources:
        print("No valid sources to process")
        return

    # Run pipeline
    dry_run = not args.no_dry_run

    asyncio.run(run_pipeline(
        sources=valid_sources,
        dry_run=dry_run,
        llm_enabled=not args.no_llm,
        images_enabled=not args.no_images,
        fetch_details=not args.no_details,
        limit=args.limit,
    ))


if __name__ == "__main__":
    main()
