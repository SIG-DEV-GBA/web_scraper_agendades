#!/usr/bin/env python
"""Test all sources with a small limit to verify they work.

Usage:
    python scripts/test_all_sources.py --dry-run
    python scripts/test_all_sources.py --no-dry-run --limit 3
    python scripts/test_all_sources.py --tier gold --no-dry-run
"""

import argparse
import asyncio
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adapters import list_adapters, get_adapter
from src.core.event_model import EventBatch
from src.core.llm_enricher import get_llm_enricher, SourceTier
from src.core.image_resolver import get_image_resolver
from src.core.supabase_client import get_supabase_client
from src.logging import get_logger

logger = get_logger(__name__)

# Classify adapters by tier
GOLD_SOURCES = [
    "madrid_datos_abiertos",
    "catalunya_agenda",
    "euskadi_kulturklik",
    "castilla_leon_agenda",
    "andalucia_agenda",
    "zaragoza_cultura",
]

SILVER_SOURCES = [
    "galicia_cultura",
    "huesca_radar",
]

BRONZE_SOURCES = [
    "navarra_cultura",
    "clm_agenda",
    "asturias_turismo",
    "larioja_agenda",
    "badajoz_agenda",
]

# Viralagenda sources (sample - one per CCAA)
VIRALAGENDA_SAMPLE = [
    "viralagenda_sevilla",      # Andalucia
    "viralagenda_valladolid",   # CyL
    "viralagenda_pontevedra",   # Galicia
    "viralagenda_caceres",      # Extremadura
    "viralagenda_murcia",       # Murcia
]


def get_tier(source_id: str) -> SourceTier:
    """Determine the tier for a source."""
    if source_id in GOLD_SOURCES:
        return SourceTier.ORO
    elif source_id in SILVER_SOURCES:
        return SourceTier.PLATA
    else:
        return SourceTier.BRONCE


async def test_source(
    source_id: str,
    dry_run: bool = True,
    limit: int = 3,
    llm_enabled: bool = True,
    images_enabled: bool = True,
) -> dict:
    """Test a single source and return results."""
    result = {
        "source_id": source_id,
        "status": "unknown",
        "fetched": 0,
        "parsed": 0,
        "inserted": 0,
        "skipped": 0,
        "failed": 0,
        "error": None,
    }

    try:
        # Get adapter
        adapter_class = get_adapter(source_id)
        if not adapter_class:
            result["status"] = "no_adapter"
            result["error"] = "Adapter not found"
            return result

        adapter = adapter_class()

        # Fetch events (some adapters have enrich param, some don't)
        try:
            raw_events = await adapter.fetch_events(enrich=False)
        except TypeError:
            raw_events = await adapter.fetch_events()
        result["fetched"] = len(raw_events)

        if not raw_events:
            result["status"] = "no_events"
            return result

        # Limit events
        if limit and len(raw_events) > limit:
            raw_events = raw_events[:limit]

        # Parse events
        events = []
        for raw in raw_events:
            event = adapter.parse_event(raw)
            if event:
                events.append(event)

        result["parsed"] = len(events)

        if not events:
            result["status"] = "parse_failed"
            return result

        # Filter out past events (only keep events from today onwards)
        today = date.today()
        events_before = len(events)
        events = [e for e in events if e.start_date and e.start_date >= today]
        filtered_out = events_before - len(events)
        if filtered_out > 0:
            logger.info("filtered_past_events", source=source_id, filtered=filtered_out, remaining=len(events))

        if not events:
            result["status"] = "no_future_events"
            return result

        # LLM enrichment (optional)
        if llm_enabled:
            enricher = get_llm_enricher()
            if enricher and enricher.is_enabled:
                tier = get_tier(source_id)
                events_for_llm = [
                    {
                        "id": e.external_id or str(i),
                        "title": e.title,
                        "description": e.description or "",
                        "venue_name": e.venue_name,
                        "city": e.city,
                        "province": e.province,
                        "price_info": e.price_info,
                    }
                    for i, e in enumerate(events)
                ]

                enrichments = enricher.enrich_batch(events_for_llm, batch_size=5, tier=tier)

                # Collect image keywords for Unsplash resolution
                image_keywords_map = {}  # event_id -> (keywords, category)

                for event in events:
                    eid = event.external_id
                    if eid and eid in enrichments:
                        enr = enrichments[eid]
                        if enr.category_slugs:
                            event.category_slugs = enr.category_slugs
                        if enr.summary:
                            event.summary = enr.summary
                        if enr.is_free is not None and event.is_free is None:
                            event.is_free = enr.is_free
                        # Store image keywords for later resolution
                        if enr.image_keywords:
                            category = enr.category_slugs[0] if enr.category_slugs else "default"
                            image_keywords_map[eid] = (enr.image_keywords, category)
                            logger.debug("image_keywords_collected", event_id=eid[:50], keywords=enr.image_keywords)

                logger.info("image_keywords_map_size", source=source_id, count=len(image_keywords_map))

                # Resolve images from Unsplash using LLM keywords
                if images_enabled and image_keywords_map:
                    image_resolver = get_image_resolver()
                    if image_resolver and image_resolver.is_enabled:
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
                        if images_resolved > 0:
                            logger.info("unsplash_images_resolved", source=source_id, count=images_resolved)
                    else:
                        logger.warning("unsplash_disabled", source=source_id)
                elif image_keywords_map:
                    logger.info("unsplash_skipped", source=source_id, reason="images_enabled=False")

        # Insert to database
        if not dry_run:
            supabase = get_supabase_client()
            batch = EventBatch(
                source_id=source_id,
                source_name=adapter.source_name,
                ccaa=adapter.ccaa,
                scraped_at=datetime.now().isoformat(),
                events=events,
                total_found=result["fetched"],
            )
            # Cross-source dedup now works with event_locations JOIN
            stats = await supabase.save_batch(batch, skip_existing=True, cross_source_dedup=True)
            result["inserted"] = stats["inserted"]
            result["skipped"] = stats["skipped"]
            result["failed"] = stats["failed"]
            result["status"] = "ok"
        else:
            result["status"] = "dry_run"
            result["inserted"] = len(events)

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        logger.error("test_source_error", source=source_id, error=str(e))

    return result


async def run_tests(
    sources: list[str],
    dry_run: bool = True,
    limit: int = 3,
    llm_enabled: bool = True,
    images_enabled: bool = True,
) -> list[dict]:
    """Run tests for multiple sources."""
    results = []

    print("=" * 80)
    print("TESTING ALL SOURCES")
    print("=" * 80)
    print(f"Sources to test: {len(sources)}")
    print(f"Dry run: {dry_run}")
    print(f"Limit per source: {limit}")
    print(f"LLM enrichment: {llm_enabled}")
    print(f"Unsplash images: {images_enabled}")
    print("-" * 80)

    for i, source_id in enumerate(sources, 1):
        print(f"\n[{i}/{len(sources)}] Testing {source_id}...")
        result = await test_source(source_id, dry_run, limit, llm_enabled, images_enabled)
        results.append(result)

        status_icon = {
            "ok": "[OK]",
            "dry_run": "[DRY]",
            "no_adapter": "[NO ADAPTER]",
            "no_events": "[NO EVENTS]",
            "no_future_events": "[PAST ONLY]",
            "parse_failed": "[PARSE FAIL]",
            "error": "[ERROR]",
        }.get(result["status"], "[?]")

        print(f"  {status_icon} Fetched: {result['fetched']}, Parsed: {result['parsed']}, Inserted: {result['inserted']}")
        if result["error"]:
            print(f"  Error: {result['error'][:100]}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    ok_count = sum(1 for r in results if r["status"] in ("ok", "dry_run"))
    error_count = sum(1 for r in results if r["status"] == "error")
    no_events = sum(1 for r in results if r["status"] == "no_events")

    print(f"Total sources tested: {len(results)}")
    print(f"Successful: {ok_count}")
    print(f"Errors: {error_count}")
    print(f"No events: {no_events}")
    print(f"Total events fetched: {sum(r['fetched'] for r in results)}")
    print(f"Total events parsed: {sum(r['parsed'] for r in results)}")
    print(f"Total events inserted: {sum(r['inserted'] for r in results)}")

    # Show errors
    errors = [r for r in results if r["status"] == "error"]
    if errors:
        print("\nERRORS:")
        for r in errors:
            print(f"  - {r['source_id']}: {r['error'][:80]}")

    print("=" * 80)

    return results


def main():
    parser = argparse.ArgumentParser(description="Test all event sources")
    parser.add_argument(
        "--tier", "-t",
        choices=["gold", "silver", "bronze", "viralagenda", "all"],
        default="all",
        help="Which tier of sources to test",
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
        "--limit", "-l",
        type=int,
        default=3,
        help="Limit events per source (default: 3)",
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
        "--source", "-s",
        help="Test a specific source ID",
    )

    args = parser.parse_args()

    # Determine sources to test
    if args.source:
        sources = [args.source]
    elif args.tier == "gold":
        sources = GOLD_SOURCES
    elif args.tier == "silver":
        sources = SILVER_SOURCES
    elif args.tier == "bronze":
        sources = BRONZE_SOURCES
    elif args.tier == "viralagenda":
        sources = VIRALAGENDA_SAMPLE
    else:
        sources = GOLD_SOURCES + SILVER_SOURCES + BRONZE_SOURCES

    dry_run = not args.no_dry_run

    asyncio.run(run_tests(
        sources=sources,
        dry_run=dry_run,
        limit=args.limit,
        llm_enabled=not args.no_llm,
        images_enabled=not args.no_images,
    ))


if __name__ == "__main__":
    main()
