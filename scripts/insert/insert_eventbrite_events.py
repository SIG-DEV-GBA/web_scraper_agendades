"""Insert events from Eventbrite for all Spanish regions.

Fetches events using Firecrawl to render JS and extracts JSON-LD structured data.
Covers all 17 autonomous communities with 52 city-based sources.
"""

import asyncio
import sys
from datetime import date
from pathlib import Path
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src.adapters.eventbrite_adapter import EventbriteAdapter, EVENTBRITE_SOURCES
from src.core.llm_enricher import LLMEnricher
from src.core.supabase_client import SupabaseClient
from src.logging import get_logger

logger = get_logger(__name__)

# Group sources by CCAA for organized processing
SOURCES_BY_CCAA: dict[str, list[str]] = defaultdict(list)
for slug, config in EVENTBRITE_SOURCES.items():
    SOURCES_BY_CCAA[config.ccaa].append(slug)


async def process_source(
    source_id: str,
    enricher: LLMEnricher,
    supabase: SupabaseClient,
    limit: int = 30,
    dry_run: bool = False
) -> dict:
    """Process a single Eventbrite source.

    Returns dict with stats: {fetched, parsed, inserted, skipped, errors}
    """
    stats = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}

    config = EVENTBRITE_SOURCES.get(source_id)
    if not config:
        print(f"Unknown source: {source_id}")
        return stats

    print(f"\n--- {config.name} ({source_id}) ---")

    # Initialize adapter
    adapter = EventbriteAdapter(source_id)

    # 1. Fetch events from Eventbrite
    raw_events = await adapter.fetch_events()
    stats["fetched"] = len(raw_events)
    print(f"   Fetched: {len(raw_events)} raw events")

    if not raw_events:
        return stats

    # 2. Parse events and filter past events
    today = date.today()
    events = []
    past_count = 0

    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event:
            # Filter out events with start_date before today
            if event.start_date and event.start_date < today:
                past_count += 1
                continue
            events.append(event)

    stats["parsed"] = len(events)
    print(f"   Parsed: {len(events)} future events (skipped {past_count} past)")

    # Apply limit
    if limit and len(events) > limit:
        events = events[:limit]
        print(f"   Limited to {limit} events")

    if not events:
        return stats

    # 3. Prepare events for LLM enrichment
    events_for_llm = []
    for e in events:
        events_for_llm.append({
            "id": e.external_id,
            "title": e.title,
            "description": (e.description or "")[:800],
            "@type": "",
            "audience": "",
            "price_info": e.price_info or "",
            "city": e.city or config.city,
            "province": config.province,
            "comunidad_autonoma": config.ccaa,
            "venue_name": e.venue_name or "",
        })

    # 4. Enrich with LLM
    print(f"   Enriching {len(events_for_llm)} events...")
    enriched_data = enricher.enrich_batch(events_for_llm, batch_size=5)
    enriched_map = enriched_data

    # 5. Apply enrichment to events
    for event in events:
        enriched = enriched_map.get(event.external_id)
        if enriched:
            event.category_slugs = enriched.category_slugs or []
            if enriched.is_free is not None:
                event.is_free = enriched.is_free

    # 6. Insert into Supabase (unless dry run)
    if dry_run:
        print(f"   [DRY RUN] Would insert {len(events)} events")
        for e in events[:5]:
            print(f"      - [{e.category_slugs}] {e.title[:50]}...")
        return stats

    for event in events:
        try:
            result = await supabase.insert_event(event)
            if result:
                stats["inserted"] += 1
            else:
                stats["errors"] += 1
        except Exception as e:
            err_str = str(e)
            if "duplicate key" in err_str or "already exists" in err_str.lower():
                stats["skipped"] += 1
            else:
                stats["errors"] += 1
                print(f"   Error: {err_str[:80]}")

    print(f"   Inserted: {stats['inserted']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")
    return stats


async def main(
    limit: int = 30,
    dry_run: bool = False,
    sources: list[str] | None = None,
    ccaas: list[str] | None = None
):
    """Fetch, enrich and insert events from Eventbrite sources.

    Args:
        limit: Max events to process per source
        dry_run: If True, don't insert into DB
        sources: List of source slugs to process (None = all)
        ccaas: List of CCAA names to process (None = all)
    """
    print(f"\n{'='*60}")
    print(f"EVENTBRITE - Inserción de eventos (52 fuentes)")
    print(f"Limit per source: {limit}, Dry run: {dry_run}")
    print(f"{'='*60}")

    # Initialize shared components
    enricher = LLMEnricher()
    supabase = SupabaseClient()

    # Determine which sources to process
    sources_to_process = list(EVENTBRITE_SOURCES.keys())

    # Filter by CCAA if specified
    if ccaas:
        ccaas_lower = [c.lower() for c in ccaas]
        sources_to_process = [
            s for s in sources_to_process
            if EVENTBRITE_SOURCES[s].ccaa.lower() in ccaas_lower
        ]

    # Filter by specific sources if specified
    if sources:
        sources_lower = [s.lower() for s in sources]
        sources_to_process = [
            s for s in sources_to_process
            if s.lower() in sources_lower
        ]

    print(f"Processing {len(sources_to_process)} sources")

    # Process each source and group results by CCAA
    total_stats = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}
    ccaa_results: dict[str, dict] = defaultdict(lambda: {"inserted": 0, "skipped": 0, "errors": 0, "sources": []})

    for source_id in sources_to_process:
        stats = await process_source(
            source_id, enricher, supabase,
            limit=limit, dry_run=dry_run
        )

        config = EVENTBRITE_SOURCES[source_id]
        ccaa = config.ccaa

        ccaa_results[ccaa]["inserted"] += stats["inserted"]
        ccaa_results[ccaa]["skipped"] += stats["skipped"]
        ccaa_results[ccaa]["errors"] += stats["errors"]
        ccaa_results[ccaa]["sources"].append((config.city, stats["inserted"]))

        for key in total_stats:
            total_stats[key] += stats[key]

    # Final summary grouped by CCAA
    print(f"\n{'='*60}")
    print(f"RESULTADO TOTAL EVENTBRITE:")
    print(f"{'='*60}")

    for ccaa in sorted(ccaa_results.keys()):
        data = ccaa_results[ccaa]
        cities = ", ".join([f"{city}:{n}" for city, n in data["sources"] if n > 0])
        print(f"  {ccaa}: {data['inserted']} inserted")
        if cities:
            print(f"    ({cities})")

    print(f"{'='*60}")
    print(f"  TOTAL: {total_stats['inserted']} eventos insertados")
    print(f"  (Omitidos: {total_stats['skipped']}, Errores: {total_stats['errors']})")
    print(f"{'='*60}\n")

    return total_stats['inserted']


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Insert events from Eventbrite (52 sources across all Spanish regions)"
    )
    parser.add_argument("--limit", type=int, default=30, help="Max events per source")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert, just test")
    parser.add_argument("--source", type=str, action="append",
                        help="Only process specific source(s)")
    parser.add_argument("--ccaa", type=str, action="append",
                        help="Only process specific CCAA(s). Options: " +
                        ", ".join(sorted(SOURCES_BY_CCAA.keys())))
    parser.add_argument("--list", action="store_true", dest="list_sources",
                        help="List all available sources and exit")
    args = parser.parse_args()

    if args.list_sources:
        print("\nEventbrite sources by CCAA:")
        print("="*50)
        for ccaa in sorted(SOURCES_BY_CCAA.keys()):
            sources = SOURCES_BY_CCAA[ccaa]
            print(f"\n{ccaa} ({len(sources)} sources):")
            for s in sources:
                config = EVENTBRITE_SOURCES[s]
                print(f"  - {s}: {config.city}")
        print(f"\nTotal: {len(EVENTBRITE_SOURCES)} sources")
        sys.exit(0)

    result = asyncio.run(main(
        limit=args.limit,
        dry_run=args.dry_run,
        sources=args.source,
        ccaas=args.ccaa
    ))
    sys.exit(0 if result > 0 else 1)
