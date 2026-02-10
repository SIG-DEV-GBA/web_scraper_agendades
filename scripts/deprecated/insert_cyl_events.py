"""Insert Castilla y León events from viralagenda.com (all 9 provinces)."""

import asyncio
import sys
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src.adapters.bronze_scraper_adapter import BronzeScraperAdapter
from src.core.llm_enricher import LLMEnricher
from src.core.supabase_client import SupabaseClient
from src.logging import get_logger

logger = get_logger(__name__)

CCAA = "Castilla y León"

# All CyL viralagenda sources
CYL_SOURCES = [
    ("viralagenda_avila", "Ávila"),
    ("viralagenda_burgos", "Burgos"),
    ("viralagenda_leon", "León"),
    ("viralagenda_palencia", "Palencia"),
    ("viralagenda_salamanca", "Salamanca"),
    ("viralagenda_segovia", "Segovia"),
    ("viralagenda_soria", "Soria"),
    ("viralagenda_valladolid", "Valladolid"),
    ("viralagenda_zamora", "Zamora"),
]


async def process_province(
    source_id: str,
    province: str,
    enricher: LLMEnricher,
    supabase: SupabaseClient,
    limit: int = 30,
    dry_run: bool = False
) -> dict:
    """Process a single province source.

    Returns dict with stats: {fetched, parsed, inserted, skipped, errors}
    """
    stats = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}

    print(f"\n--- {province} ({source_id}) ---")

    # Initialize adapter
    adapter = BronzeScraperAdapter(source_id)

    # 1. Fetch events from listing page
    raw_events = await adapter.fetch_events(fetch_details=True)
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
            "city": e.city or province,
            "province": province,
            "comunidad_autonoma": CCAA,
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
        for e in events[:3]:
            print(f"      - [{e.category_slugs}] {e.title[:40]}...")
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
    provinces: list[str] | None = None
):
    """Fetch, enrich and insert CyL events from all viralagenda sources.

    Args:
        limit: Max events to process per province
        dry_run: If True, don't insert into DB
        provinces: List of province names to process (None = all)
    """
    print(f"\n{'='*60}")
    print(f"CASTILLA Y LEÓN VIRALAGENDA - Inserción de eventos")
    print(f"Limit per province: {limit}, Dry run: {dry_run}")
    if provinces:
        print(f"Provinces: {', '.join(provinces)}")
    print(f"{'='*60}")

    # Initialize shared components
    enricher = LLMEnricher()
    supabase = SupabaseClient()

    # Filter sources by province if specified
    sources_to_process = CYL_SOURCES
    if provinces:
        provinces_lower = [p.lower() for p in provinces]
        sources_to_process = [
            (sid, prov) for sid, prov in CYL_SOURCES
            if prov.lower() in provinces_lower
        ]

    # Process each province
    total_stats = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}

    for source_id, province in sources_to_process:
        stats = await process_province(
            source_id, province, enricher, supabase,
            limit=limit, dry_run=dry_run
        )
        for key in total_stats:
            total_stats[key] += stats[key]

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTADO TOTAL CASTILLA Y LEÓN:")
    print(f"  - Provincias procesadas: {len(sources_to_process)}")
    print(f"  - Eventos encontrados: {total_stats['fetched']}")
    print(f"  - Eventos parseados: {total_stats['parsed']}")
    print(f"  - Insertados: {total_stats['inserted']}")
    print(f"  - Omitidos (ya existían): {total_stats['skipped']}")
    print(f"  - Errores: {total_stats['errors']}")
    print(f"{'='*60}\n")

    return total_stats['inserted']


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30, help="Max events per province")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert, just test")
    parser.add_argument("--province", type=str, action="append",
                        help="Only process specific province(s). Can be used multiple times.")
    args = parser.parse_args()

    result = asyncio.run(main(limit=args.limit, dry_run=args.dry_run, provinces=args.province))
    sys.exit(0 if result > 0 else 1)
