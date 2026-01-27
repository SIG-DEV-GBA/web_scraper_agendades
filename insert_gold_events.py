#!/usr/bin/env python
"""Insert events from all Gold-level sources into Supabase.

Usage:
    python insert_gold_events.py                    # Insert 20 per source
    python insert_gold_events.py --limit 10         # Insert 10 per source
    python insert_gold_events.py --source madrid    # Only Madrid
    python insert_gold_events.py --dry-run          # Test without inserting
"""

import argparse
import asyncio
import os
import sys
from datetime import date

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["LLM_ENABLED"] = "true"

from datetime import datetime

from src.adapters import get_adapter
from src.adapters.gold_api_adapter import GOLD_SOURCES, SourceTier
from src.core.event_model import EventBatch
from src.core.llm_enricher import SourceTier as EnricherTier, get_llm_enricher
from src.core.supabase_client import get_supabase_client
from src.logging.logger import get_logger

logger = get_logger(__name__)

# Colors for terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def process_source(
    source_slug: str,
    limit: int = 20,
    dry_run: bool = False,
    upsert: bool = False,
) -> dict:
    """Process and insert events from a single source.

    Returns:
        dict with stats
    """
    print(f"\n{'='*60}")
    print(f"{BOLD}{source_slug.upper()}{RESET}")
    print(f"{'='*60}")

    config = GOLD_SOURCES.get(source_slug)
    if not config:
        print(f"  {RED}ERROR: Source not found{RESET}")
        return {"source": source_slug, "error": "Source not found"}

    print(f"  CCAA: {config.ccaa}")
    print(f"  Tier: {config.tier.value.upper()}")

    # Get adapter
    adapter_class = get_adapter(source_slug)
    if not adapter_class:
        print(f"  {RED}ERROR: Adapter not registered{RESET}")
        return {"source": source_slug, "error": "Adapter not registered"}

    adapter = adapter_class()

    # Fetch events
    print(f"  Fetching events...")
    try:
        raw_events = await adapter.fetch_events(max_pages=3)
        print(f"  Raw events: {len(raw_events)}")
    except Exception as e:
        print(f"  {RED}FETCH ERROR: {e}{RESET}")
        return {"source": source_slug, "error": f"Fetch error: {e}"}

    # Parse events - only include future events (>= today)
    today = date.today()
    events = []
    skipped_past = 0

    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event:
            if event.start_date:
                # Parse event date and filter
                try:
                    event_date = datetime.fromisoformat(str(event.start_date).replace('Z', '')).date()
                    if event_date >= today:
                        events.append(event)
                    else:
                        skipped_past += 1
                except (ValueError, TypeError):
                    # If date parsing fails, include the event anyway
                    events.append(event)

    print(f"  Parsed events: {len(events)} (skipped {skipped_past} past events)")

    if not events:
        print(f"  {YELLOW}WARNING: No events parsed{RESET}")
        return {"source": source_slug, "parsed": 0, "inserted": 0}

    # Take only the limit
    events = events[:limit]
    print(f"  Events to process: {len(events)}")

    # LLM Enrichment
    print(f"  Running LLM enrichment...")
    enricher = get_llm_enricher()

    events_for_llm = []
    for e in events:
        events_for_llm.append({
            "id": e.external_id,
            "title": e.title,
            "description": e.description,
            "@type": e.category_name or "",
            "audience": "",
            "price_info": e.price_info or "",  # For LLM to extract numeric price
        })

    # Map source tier to enricher tier
    tier_map = {
        SourceTier.ORO: EnricherTier.ORO,
        SourceTier.PLATA: EnricherTier.PLATA,
        SourceTier.BRONCE: EnricherTier.BRONCE,
    }
    enricher_tier = tier_map.get(config.tier, EnricherTier.ORO)

    enrichments = enricher.enrich_batch(events_for_llm, batch_size=10, tier=enricher_tier)
    print(f"  Enriched: {len(enrichments)} events")

    # Apply enrichments to events
    for event in events:
        enrichment = enrichments.get(event.external_id)
        if enrichment:
            event.category_slugs = enrichment.category_slugs
            if enrichment.summary:
                event.summary = enrichment.summary
            # Apply price from LLM (extracts numeric value from price_info)
            if enrichment.price is not None:
                event.price = enrichment.price
                event.is_free = False  # If has price, not free
            elif event.price_info and not event.price:
                # Mark as free if no price extracted but has price_info mentioning "gratis/gratuito"
                price_lower = event.price_info.lower()
                if any(word in price_lower for word in ["gratis", "gratuito", "gratuït", "libre", "lliure"]):
                    event.is_free = True

            # price_info should ONLY contain additional details (discounts, etc.)
            # NOT duplicate the main price - clear original and use only LLM details
            if enrichment.price_details:
                # Clean up "Gratis" type values - they belong in is_free, not price_info
                details = enrichment.price_details.strip()
                if details.lower() in ["gratis", "gratuito", "gratuït", "libre", "entrada libre"]:
                    event.price_info = None
                    event.is_free = True
                else:
                    event.price_info = details if details else None
            elif enrichment.price is not None:
                # If LLM extracted price but no details, clear price_info (avoid duplication)
                event.price_info = None
            else:
                # No price extracted - check if original price_info indicates free
                if event.price_info:
                    price_lower = event.price_info.lower()
                    if any(word in price_lower for word in ["gratis", "gratuito", "gratuït", "libre", "lliure"]):
                        event.is_free = True
                        event.price_info = None  # Don't duplicate "Gratis" text

    # Count categories (use first/primary category)
    category_counts = {}
    for e in events:
        cat = e.category_slugs[0] if e.category_slugs else "N/A"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    print(f"  Categories: {category_counts}")

    if dry_run:
        print(f"\n  {YELLOW}DRY RUN - Not inserting to database{RESET}")
        print(f"  Would insert {len(events)} events")

        # Show sample
        print(f"\n  {BOLD}Sample events:{RESET}")
        for i, e in enumerate(events[:5]):
            cat = e.category_slugs[0] if e.category_slugs else "N/A"
            print(f"    {i+1}. [{cat}] {e.title[:50]}")
            print(f"       {e.comunidad_autonoma} | {e.city or '?'} | {e.start_date}")

        return {
            "source": source_slug,
            "ccaa": config.ccaa,
            "parsed": len(events),
            "inserted": 0,
            "dry_run": True,
            "categories": category_counts,
        }

    # Insert to Supabase
    print(f"\n  {CYAN}Inserting to Supabase...{RESET}")
    client = get_supabase_client()

    batch = EventBatch(
        source_id=source_slug,
        source_name=config.name,
        ccaa=config.ccaa,
        scraped_at=datetime.now().isoformat(),
        events=events,
        total_found=len(raw_events),
    )

    stats = await client.save_batch(batch, skip_existing=not upsert)

    print(f"  {GREEN}Inserted: {stats['inserted']}{RESET}")
    print(f"  Skipped (existing): {stats['skipped']}")
    print(f"  Failed: {stats['failed']}")

    return {
        "source": source_slug,
        "ccaa": config.ccaa,
        "parsed": len(events),
        "inserted": stats["inserted"],
        "skipped": stats["skipped"],
        "failed": stats["failed"],
        "categories": category_counts,
    }


async def main():
    parser = argparse.ArgumentParser(description="Insert Gold-level events to Supabase")
    parser.add_argument(
        "--source", "-s",
        help="Process only this source (default: all)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Events per source (default: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test without inserting to database",
    )
    parser.add_argument(
        "--upsert",
        action="store_true",
        help="Update existing events instead of skipping them",
    )

    args = parser.parse_args()

    sources = list(GOLD_SOURCES.keys())

    if args.source:
        if args.source not in sources:
            print(f"{RED}ERROR: Unknown source '{args.source}'{RESET}")
            print(f"Available: {', '.join(sources)}")
            sys.exit(1)
        sources = [args.source]

    print(f"\n{'#'*60}")
    print(f"# GOLD EVENTS INSERTION")
    print(f"# Sources: {len(sources)}, Limit: {args.limit}/source")
    print(f"# Dry run: {args.dry_run}, Upsert: {args.upsert}")
    print(f"{'#'*60}")

    all_results = []
    total_inserted = 0
    total_parsed = 0

    for source in sources:
        try:
            result = await process_source(
                source,
                limit=args.limit,
                dry_run=args.dry_run,
                upsert=args.upsert,
            )
            all_results.append(result)
            total_parsed += result.get("parsed", 0)
            total_inserted += result.get("inserted", 0)
        except Exception as e:
            print(f"\n  {RED}FATAL ERROR: {e}{RESET}")
            all_results.append({"source": source, "error": str(e)})

    # Final summary
    print(f"\n{'#'*60}")
    print(f"# {BOLD}FINAL SUMMARY{RESET}")
    print(f"{'#'*60}")

    for result in all_results:
        source = result["source"]
        if "error" in result:
            print(f"\n{source}: {RED}ERROR - {result['error']}{RESET}")
        else:
            inserted = result.get("inserted", 0)
            parsed = result.get("parsed", 0)
            skipped = result.get("skipped", 0)
            status = f"{GREEN}OK{RESET}" if inserted > 0 or result.get("dry_run") else f"{YELLOW}SKIP{RESET}"
            print(f"\n{source}: {status}")
            print(f"  Parsed: {parsed}, Inserted: {inserted}, Skipped: {skipped}")

    print(f"\n{BOLD}TOTALS:{RESET}")
    print(f"  Events parsed: {total_parsed}")
    print(f"  Events inserted: {total_inserted}")

    if args.dry_run:
        print(f"\n{YELLOW}This was a dry run. Use without --dry-run to insert.{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
