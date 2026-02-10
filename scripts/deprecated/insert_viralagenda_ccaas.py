"""Insert events from viralagenda.com for multiple CCAAs without Gold sources.

Covers: Galicia, Asturias, Canarias, Cantabria, Castilla-La Mancha, Murcia, Navarra
"""

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

# All viralagenda sources by CCAA
CCAA_SOURCES = {
    "Galicia": [
        ("viralagenda_a_coruna", "A Coruña"),
        ("viralagenda_lugo", "Lugo"),
        ("viralagenda_ourense", "Ourense"),
        ("viralagenda_pontevedra", "Pontevedra"),
    ],
    "Asturias": [
        ("viralagenda_asturias", "Asturias"),
    ],
    "Canarias": [
        ("viralagenda_las_palmas", "Las Palmas"),
        ("viralagenda_santa_cruz_tenerife", "Santa Cruz de Tenerife"),
    ],
    "Cantabria": [
        ("viralagenda_cantabria", "Cantabria"),
    ],
    "Castilla-La Mancha": [
        ("viralagenda_albacete", "Albacete"),
        ("viralagenda_ciudad_real", "Ciudad Real"),
        ("viralagenda_cuenca", "Cuenca"),
        ("viralagenda_guadalajara", "Guadalajara"),
        ("viralagenda_toledo", "Toledo"),
    ],
    "Murcia": [
        ("viralagenda_murcia", "Murcia"),
    ],
    "Navarra": [
        ("viralagenda_navarra", "Navarra"),
    ],
}


async def process_province(
    source_id: str,
    province: str,
    ccaa: str,
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
            "comunidad_autonoma": ccaa,
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


async def process_ccaa(
    ccaa_name: str,
    enricher: LLMEnricher,
    supabase: SupabaseClient,
    limit: int = 30,
    dry_run: bool = False
) -> dict:
    """Process all provinces in a CCAA."""
    sources = CCAA_SOURCES.get(ccaa_name, [])
    if not sources:
        print(f"Unknown CCAA: {ccaa_name}")
        return {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}

    print(f"\n{'='*60}")
    print(f"{ccaa_name.upper()} - Viralagenda")
    print(f"{'='*60}")

    total_stats = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}

    for source_id, province in sources:
        stats = await process_province(
            source_id, province, ccaa_name, enricher, supabase,
            limit=limit, dry_run=dry_run
        )
        for key in total_stats:
            total_stats[key] += stats[key]

    print(f"\n  {ccaa_name} Total: {total_stats['inserted']} inserted, {total_stats['skipped']} skipped")
    return total_stats


async def main(
    limit: int = 30,
    dry_run: bool = False,
    ccaas: list[str] | None = None
):
    """Fetch, enrich and insert events from all viralagenda CCAA sources.

    Args:
        limit: Max events to process per province
        dry_run: If True, don't insert into DB
        ccaas: List of CCAA names to process (None = all)
    """
    print(f"\n{'='*60}")
    print(f"VIRALAGENDA - Inserción de eventos (7 CCAAs)")
    print(f"Limit per province: {limit}, Dry run: {dry_run}")
    print(f"{'='*60}")

    # Initialize shared components
    enricher = LLMEnricher()
    supabase = SupabaseClient()

    # Determine which CCAAs to process
    ccaas_to_process = list(CCAA_SOURCES.keys())
    if ccaas:
        ccaas_lower = [c.lower() for c in ccaas]
        ccaas_to_process = [
            c for c in CCAA_SOURCES.keys()
            if c.lower() in ccaas_lower
        ]

    # Process each CCAA
    grand_total = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "errors": 0}
    ccaa_results = {}

    for ccaa_name in ccaas_to_process:
        stats = await process_ccaa(
            ccaa_name, enricher, supabase,
            limit=limit, dry_run=dry_run
        )
        ccaa_results[ccaa_name] = stats
        for key in grand_total:
            grand_total[key] += stats[key]

    # Final summary
    print(f"\n{'='*60}")
    print(f"RESULTADO TOTAL:")
    print(f"{'='*60}")
    for ccaa_name, stats in ccaa_results.items():
        num_provinces = len(CCAA_SOURCES[ccaa_name])
        print(f"  {ccaa_name} ({num_provinces} prov): {stats['inserted']} inserted")
    print(f"{'='*60}")
    print(f"  TOTAL: {grand_total['inserted']} eventos insertados")
    print(f"  (Omitidos: {grand_total['skipped']}, Errores: {grand_total['errors']})")
    print(f"{'='*60}\n")

    return grand_total['inserted']


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30, help="Max events per province")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert, just test")
    parser.add_argument("--ccaa", type=str, action="append",
                        help="Only process specific CCAA(s). Options: Galicia, Asturias, Canarias, Cantabria, Castilla-La Mancha, Murcia, Navarra")
    args = parser.parse_args()

    result = asyncio.run(main(limit=args.limit, dry_run=args.dry_run, ccaas=args.ccaa))
    sys.exit(0 if result > 0 else 1)
