"""Insert Cantabria events from iCal feed with LLM enrichment."""

import asyncio
import sys
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.adapters.silver_rss_adapter import SilverRSSAdapter
from src.core.llm_enricher import LLMEnricher
from src.core.supabase_client import SupabaseClient
from src.logging import get_logger

logger = get_logger(__name__)

SOURCE_ID = "cantabria_turismo"
CCAA = "Cantabria"
PROVINCE = "Cantabria"


async def main(limit: int = 20, dry_run: bool = False):
    """Fetch, enrich and insert Cantabria events."""
    print(f"\n{'='*60}")
    print(f"CANTABRIA TURISMO (iCal) - Inserción de eventos")
    print(f"Limit: {limit}, Dry run: {dry_run}")
    print(f"{'='*60}\n")

    # Initialize components
    adapter = SilverRSSAdapter(SOURCE_ID)
    enricher = LLMEnricher()
    supabase = SupabaseClient()

    # 1. Fetch events from iCal
    print("1. Fetching events from iCal feed...")
    raw_events = await adapter.fetch_events()
    print(f"   -> Found {len(raw_events)} raw events")

    # 2. Parse events and filter past events
    print("\n2. Parsing events...")
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
    print(f"   -> Parsed {len(events)} future events (skipped {past_count} with past start_date)")

    # Apply limit
    if limit and len(events) > limit:
        events = events[:limit]
        print(f"   -> Limited to {limit} events")

    if not events:
        print("No events to process.")
        return 0

    # Show sample events
    print("\n   Sample events:")
    for e in events[:3]:
        print(f"   - {e.title[:50]}...")
        print(f"     City: {e.city}, Province: {e.province}")
        if e.description:
            print(f"     Description: {e.description[:100]}...")

    # 3. Prepare events for LLM enrichment
    print("\n3. Preparing events for LLM enrichment...")
    events_for_llm = []
    for e in events:
        events_for_llm.append({
            "id": e.external_id,
            "title": e.title,
            "description": (e.description or "")[:800],
            "@type": "",
            "audience": "",
            "price_info": e.price_info or "",
            # Location fields for contextualized image_keywords
            "city": e.city or PROVINCE,
            "province": PROVINCE,
            "comunidad_autonoma": CCAA,
            "venue_name": e.venue_name or "",
        })

    # 4. Enrich with LLM (batch_size=5 to avoid Groq truncation)
    print("\n4. Enriching with LLM (batch_size=5)...")
    enriched_data = enricher.enrich_batch(events_for_llm, batch_size=5)
    print(f"   -> Enriched {len(enriched_data)} events")

    # enriched_data is already a dict {id: enriched_event}
    enriched_map = enriched_data

    # 5. Apply enrichment to events
    print("\n5. Applying enrichment...")
    for event in events:
        enriched = enriched_map.get(event.external_id)
        if enriched:
            # EventEnrichment is a Pydantic model, access as attributes
            event.category_slugs = enriched.category_slugs or []
            if enriched.is_free is not None:
                event.is_free = enriched.is_free

    # 6. Insert into Supabase (unless dry run)
    if dry_run:
        print(f"\n6. [DRY RUN] Would insert {len(events)} events")
        for e in events[:5]:
            print(f"   - [{e.category_slugs}] {e.title[:50]}...")
            print(f"     {e.province} | {e.city} | {e.start_date}")
        return len(events)

    print("\n6. Inserting into Supabase...")
    inserted = 0
    skipped = 0
    errors = 0

    for event in events:
        try:
            result = await supabase.insert_event(event)
            if result:
                inserted += 1
                print(f"   + {event.title[:50]}...")
            else:
                errors += 1
        except Exception as e:
            err_str = str(e)
            if "duplicate key" in err_str or "already exists" in err_str.lower():
                skipped += 1
            else:
                errors += 1
                print(f"   Error: {err_str[:100]}")

    # 7. Summary
    print(f"\n{'='*60}")
    print(f"RESULTADO:")
    print(f"  - Insertados: {inserted}")
    print(f"  - Omitidos (ya existían): {skipped}")
    print(f"  - Errores: {errors}")
    print(f"{'='*60}\n")

    return inserted


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20, help="Max events to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert, just test")
    args = parser.parse_args()

    result = asyncio.run(main(limit=args.limit, dry_run=args.dry_run))
    sys.exit(0 if result > 0 else 1)
