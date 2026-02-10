"""Insert Extremadura events from turismoextremadura.com (covers Cáceres and Badajoz)."""

import asyncio
import re
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

SOURCE_ID = "extremadura_turismo"
CCAA = "Extremadura"


def detect_province(text: str) -> str:
    """Detect province from location text."""
    if not text:
        return "Cáceres"  # Default
    text_lower = text.lower()
    if "badajoz" in text_lower:
        return "Badajoz"
    if "cáceres" in text_lower or "caceres" in text_lower:
        return "Cáceres"
    # Known Cáceres province cities
    caceres_cities = ["plasencia", "trujillo", "coria", "navalmoral", "mérida", "jaraíz"]
    for city in caceres_cities:
        if city in text_lower:
            return "Cáceres"
    return "Cáceres"


def extract_city(text: str) -> str:
    """Extract city name from location text like 'Plasencia, Cáceres (Extremadura)'."""
    if not text:
        return ""
    # Remove province and region suffixes
    text = re.sub(r",?\s*(Cáceres|Badajoz)\s*(\(Extremadura\))?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\(Extremadura\)", "", text, flags=re.IGNORECASE)
    return text.strip().strip(",").strip()


async def main(limit: int = 30, dry_run: bool = False, province_filter: str = None):
    """Fetch, enrich and insert Extremadura events.

    Args:
        limit: Max events to process
        dry_run: If True, don't insert into DB
        province_filter: If set ("Cáceres" or "Badajoz"), only process events from that province
    """
    print(f"\n{'='*60}")
    print(f"EXTREMADURA TURISMO - Insercion de eventos")
    print(f"Limit: {limit}, Dry run: {dry_run}")
    if province_filter:
        print(f"Province filter: {province_filter}")
    print(f"{'='*60}\n")

    # Initialize components
    adapter = BronzeScraperAdapter(SOURCE_ID)
    enricher = LLMEnricher()
    supabase = SupabaseClient()

    # 1. Fetch events from listing pages
    print("1. Fetching events from turismoextremadura.com...")
    raw_events = await adapter.fetch_events(fetch_details=True)
    print(f"   -> Found {len(raw_events)} raw events")

    if not raw_events:
        print("No events found.")
        return 0

    # 2. Parse events and filter
    print("\n2. Parsing events...")
    today = date.today()
    events = []
    past_count = 0
    filtered_count = 0

    for raw in raw_events:
        # Extract location info for province detection
        full_text = raw.get("raw_date", "") or ""
        loc_match = re.search(r"Localizaci[oó]n:\s*([^|]+)", full_text)
        if loc_match:
            raw["locality"] = loc_match.group(1).strip()

        event = adapter.parse_event(raw)
        if event:
            # Detect province from locality
            province = detect_province(event.city or raw.get("locality", ""))
            event.province = province

            # Extract clean city name
            city = extract_city(raw.get("locality", ""))
            if city:
                event.city = city

            # Filter by province if specified
            if province_filter and event.province != province_filter:
                filtered_count += 1
                continue

            # Filter out events with start_date before today
            if event.start_date and event.start_date < today:
                past_count += 1
                continue

            events.append(event)

    print(f"   -> Parsed {len(events)} future events")
    print(f"   -> Skipped {past_count} past events, {filtered_count} filtered by province")

    # Apply limit
    if limit and len(events) > limit:
        events = events[:limit]
        print(f"   -> Limited to {limit} events")

    if not events:
        print("No events to process.")
        return 0

    # Show sample events
    print("\n   Sample events:")
    for e in events[:5]:
        title_display = e.title[:45] if e.title else "Sin titulo"
        print(f"   - {title_display}...")
        print(f"     City: {e.city}, Province: {e.province}")
        print(f"     Date: {e.start_date} - {e.end_date}")

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
            "city": e.city or "",
            "province": e.province,
            "comunidad_autonoma": CCAA,
            "venue_name": e.venue_name or "",
        })

    # 4. Enrich with LLM
    print("\n4. Enriching with LLM (batch_size=5)...")
    enriched_data = enricher.enrich_batch(events_for_llm, batch_size=5)
    print(f"   -> Enriched {len(enriched_data)} events")

    enriched_map = enriched_data

    # 5. Apply enrichment to events
    print("\n5. Applying enrichment...")
    for event in events:
        enriched = enriched_map.get(event.external_id)
        if enriched:
            event.category_slugs = enriched.category_slugs or []
            if enriched.is_free is not None:
                event.is_free = enriched.is_free

    # 6. Insert into Supabase (unless dry run)
    if dry_run:
        print(f"\n6. [DRY RUN] Would insert {len(events)} events")
        for e in events[:8]:
            print(f"   - [{e.category_slugs}] {e.title[:45]}...")
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
                print(f"   + {event.title[:45]}...")
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
    print(f"  - Omitidos (ya existian): {skipped}")
    print(f"  - Errores: {errors}")
    print(f"{'='*60}\n")

    return inserted


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30, help="Max events to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert, just test")
    parser.add_argument("--province", type=str, choices=["Cáceres", "Badajoz"],
                        help="Only process events from this province")
    args = parser.parse_args()

    result = asyncio.run(main(limit=args.limit, dry_run=args.dry_run, province_filter=args.province))
    sys.exit(0 if result > 0 else 1)
