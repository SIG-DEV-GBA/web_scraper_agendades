"""Insert Huesca events from RADAR RSS feed with LLM enrichment."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.adapters.silver_rss_adapter import SilverRSSAdapter
from src.core.llm_enricher import LLMEnricher
from src.core.supabase_client import SupabaseClient
from src.logging import get_logger

logger = get_logger(__name__)

SOURCE_ID = "huesca_radar"
CCAA = "Aragón"
PROVINCE = "Huesca"


async def main():
    """Fetch, enrich and insert Huesca events."""
    print(f"\n{'='*60}")
    print(f"HUESCA RADAR - Inserción de eventos")
    print(f"{'='*60}\n")

    # Initialize components
    adapter = SilverRSSAdapter(SOURCE_ID)
    enricher = LLMEnricher()
    supabase = SupabaseClient()

    # 1. Fetch events from RSS
    print("1. Fetching events from RSS...")
    raw_events = await adapter.fetch_events()
    print(f"   -> Found {len(raw_events)} raw events")

    # 2. Parse events
    print("\n2. Parsing events...")
    events = []
    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event:
            events.append(event)
    print(f"   -> Parsed {len(events)} valid events")

    # Show sample of registration detection
    print("\n   Registration detection:")
    for e in events[:3]:
        if e.requires_registration:
            print(f"   - {e.title[:50]}...")
            print(f"     requires_registration: {e.requires_registration}")
            if e.registration_info:
                print(f"     registration_info: {e.registration_info}")

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
            if enriched.image_keywords and not event.source_image_url:
                # Store image_keywords for Unsplash fallback (handled by supabase_client)
                pass  # image_keywords are used when inserting

    # 6. Insert into Supabase
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
    result = asyncio.run(main())
    sys.exit(0 if result > 0 else 1)
