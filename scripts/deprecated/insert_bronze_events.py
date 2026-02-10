#!/usr/bin/env python
"""Insert events from Bronze-level sources into Supabase.

Usage:
    python insert_bronze_events.py                    # Insert 20 per source
    python insert_bronze_events.py --limit 10         # Insert 10 per source
    python insert_bronze_events.py --source clm_agenda # Only CLM
    python insert_bronze_events.py --dry-run          # Test without inserting
"""

import argparse
import asyncio
import os
import sys
from datetime import date, datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["LLM_ENABLED"] = "true"

from src.adapters.bronze_scraper_adapter import BronzeScraperAdapter, BRONZE_SOURCES
from src.core.event_model import EventBatch
from src.core.image_provider import get_image_provider
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
    fetch_details: bool = True,
) -> dict:
    """Process and insert events from a single Bronze source.

    Returns:
        dict with stats
    """
    print(f"\n{'='*60}")
    print(f"{BOLD}{source_slug.upper()}{RESET}")
    print(f"{'='*60}")

    config = BRONZE_SOURCES.get(source_slug)
    if not config:
        print(f"  {RED}ERROR: Source not found{RESET}")
        return {"source": source_slug, "error": "Source not found"}

    print(f"  CCAA: {config.ccaa}")
    print(f"  URL: {config.listing_url}")
    print(f"  Tier: BRONZE")

    # Create adapter
    try:
        adapter = BronzeScraperAdapter(source_slug)
    except Exception as e:
        print(f"  {RED}ERROR: Failed to create adapter: {e}{RESET}")
        return {"source": source_slug, "error": f"Adapter error: {e}"}

    # Fetch events
    print(f"  Fetching events (fetch_details={fetch_details})...")
    try:
        raw_events = await adapter.fetch_events(enrich=False, fetch_details=fetch_details)
        print(f"  Raw events: {len(raw_events)}")
    except Exception as e:
        print(f"  {RED}FETCH ERROR: {e}{RESET}")
        return {"source": source_slug, "error": f"Fetch error: {e}"}

    # Parse events - only include future/ongoing events
    # An event is valid if end_date >= today OR start_date >= today (if no end_date)
    today = date.today()
    events = []
    skipped_past = 0

    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event:
            try:
                # Determine the relevant date (end_date for ongoing, start_date for future)
                end_dt = event.end_date
                start_dt = event.start_date

                # Convert to date objects if needed
                if end_dt and not isinstance(end_dt, date):
                    end_dt = datetime.fromisoformat(str(end_dt).replace('Z', '')).date()
                if start_dt and not isinstance(start_dt, date):
                    start_dt = datetime.fromisoformat(str(start_dt).replace('Z', '')).date()

                # Event is valid if:
                # - end_date >= today (ongoing event), OR
                # - start_date >= today (future event, no end_date)
                is_valid = False
                if end_dt and end_dt >= today:
                    is_valid = True
                elif start_dt and start_dt >= today:
                    is_valid = True

                if is_valid:
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
            "description": e.description or "",
            "@type": e.category_name or "",
            "audience": "",
            "price_info": e.price_info or "",
        })

    # Bronze tier
    enrichments = enricher.enrich_batch(events_for_llm, batch_size=10, tier=EnricherTier.BRONCE)
    print(f"  Enriched: {len(enrichments)} events")

    # Apply enrichments to events
    for event in events:
        enrichment = enrichments.get(event.external_id)
        if enrichment:
            event.category_slugs = enrichment.category_slugs
            if enrichment.summary:
                event.summary = enrichment.summary

            # Apply is_free from LLM (PRIORITY 1)
            if enrichment.is_free is not None:
                event.is_free = enrichment.is_free

            # Apply price from LLM
            if enrichment.price is not None:
                event.price = enrichment.price
                event.is_free = False  # Explicit price = paid
            elif event.price_info and not event.price:
                price_lower = event.price_info.lower()
                if any(word in price_lower for word in ["gratis", "gratuito", "libre"]):
                    event.is_free = True

            # Handle price_info
            if enrichment.price_details:
                details = enrichment.price_details.strip()
                if details.lower() in ["gratis", "gratuito", "libre", "entrada libre"]:
                    event.price_info = None
                    event.is_free = True
                else:
                    event.price_info = details if details else None
            elif enrichment.price is not None:
                event.price_info = None

        # FALLBACK: Rule-based is_free inference for public venues (if still None)
        if event.is_free is None and event.venue_name:
            venue_lower = event.venue_name.lower()
            free_venue_keywords = [
                "biblioteca", "museo", "archivo", "casa de cultura",
                "centro cultural", "centro cívico", "sala de exposiciones",
            ]
            if any(kw in venue_lower for kw in free_venue_keywords):
                event.is_free = True

    # Fetch images for events without source_image_url
    image_provider = get_image_provider()
    images_found = 0
    if image_provider.unsplash:
        print(f"  Fetching images for events without source image...")
        for event in events:
            if not event.source_image_url:
                enrichment = enrichments.get(event.external_id)
                if enrichment and enrichment.image_keywords:
                    image_url = image_provider.get_image(
                        keywords=enrichment.image_keywords,
                        category=enrichment.category_slugs[0] if enrichment.category_slugs else "default",
                    )
                    if image_url:
                        event.source_image_url = image_url
                        images_found += 1
        print(f"  Images found: {images_found}")

    # Count by province
    province_counts = {}
    for e in events:
        prov = e.province or "N/A"
        province_counts[prov] = province_counts.get(prov, 0) + 1

    print(f"  Provinces: {province_counts}")

    # Count categories
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
        for i, e in enumerate(events[:8]):
            cat = e.category_slugs[0] if e.category_slugs else "N/A"
            print(f"    {i+1}. [{cat}] {e.title[:50]}")
            print(f"       {e.province} | {e.city or '?'} | {e.start_date} - {e.end_date}")
            if e.venue_name:
                print(f"       Venue: {e.venue_name[:50]}")
            if e.summary:
                print(f"       Summary: {e.summary[:60]}...")

        return {
            "source": source_slug,
            "ccaa": config.ccaa,
            "parsed": len(events),
            "inserted": 0,
            "dry_run": True,
            "provinces": province_counts,
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
        "provinces": province_counts,
        "categories": category_counts,
    }


async def main():
    parser = argparse.ArgumentParser(description="Insert Bronze-level events to Supabase")
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
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="Skip fetching detail pages (faster but less info)",
    )

    args = parser.parse_args()

    sources = list(BRONZE_SOURCES.keys())

    if args.source:
        if args.source not in sources:
            print(f"{RED}ERROR: Unknown source '{args.source}'{RESET}")
            print(f"Available: {', '.join(sources)}")
            sys.exit(1)
        sources = [args.source]

    print(f"\n{'#'*60}")
    print(f"# BRONZE EVENTS INSERTION")
    print(f"# Sources: {len(sources)}, Limit: {args.limit}/source")
    print(f"# Dry run: {args.dry_run}, Upsert: {args.upsert}")
    print(f"# Fetch details: {not args.no_details}")
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
                fetch_details=not args.no_details,
            )
            all_results.append(result)
            total_parsed += result.get("parsed", 0)
            total_inserted += result.get("inserted", 0)
        except Exception as e:
            print(f"\n  {RED}FATAL ERROR: {e}{RESET}")
            import traceback
            traceback.print_exc()
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
            if result.get("provinces"):
                print(f"  Provinces: {result['provinces']}")

    print(f"\n{BOLD}TOTALS:{RESET}")
    print(f"  Events parsed: {total_parsed}")
    print(f"  Events inserted: {total_inserted}")

    if args.dry_run:
        print(f"\n{YELLOW}This was a dry run. Use without --dry-run to insert.{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
