#!/usr/bin/env python3
"""Insert 20 enriched events from Galicia RSS into Supabase.

This script demonstrates the full pipeline:
1. Fetch events from RSS
2. Enrich with LLM (categories, summary, price, age_range)
3. Geocode locations
4. Insert into Supabase with all fields populated
"""

import asyncio
import html as html_lib
import re
import sys
from datetime import date, time

import feedparser

from src.config.settings import get_settings
from src.core.event_model import EventCreate, LocationType
from src.core.llm_enricher import SourceTier, get_llm_enricher
from src.core.supabase_client import get_supabase_client
from src.logging.logger import get_logger

# Fix encoding for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logger = get_logger(__name__)

# Galicia province mapping for cities
GALICIA_CITY_PROVINCE: dict[str, str] = {
    "a coruña": "A Coruña",
    "coruña": "A Coruña",
    "ferrol": "A Coruña",
    "santiago de compostela": "A Coruña",
    "santiago": "A Coruña",
    "carballo": "A Coruña",
    "betanzos": "A Coruña",
    "arteixo": "A Coruña",
    "narón": "A Coruña",
    "naron": "A Coruña",
    "lugo": "Lugo",
    "monforte de lemos": "Lugo",
    "viveiro": "Lugo",
    "sarria": "Lugo",
    "vilalba": "Lugo",
    "ourense": "Ourense",
    "orense": "Ourense",
    "verín": "Ourense",
    "celanova": "Ourense",
    "pontevedra": "Pontevedra",
    "vigo": "Pontevedra",
    "vilagarcía de arousa": "Pontevedra",
    "cangas": "Pontevedra",
    "marín": "Pontevedra",
    "redondela": "Pontevedra",
    "tui": "Pontevedra",
    "bueu": "Pontevedra",
    "lalín": "Pontevedra",
}


def parse_rss_entry(entry: dict) -> dict:
    """Parse a single RSS entry into event data."""
    title = html_lib.unescape(entry.get("title", "")).strip()
    summary_html = entry.get("summary", "")
    pp = entry.get("published_parsed")

    # Description from <p> tags
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", summary_html, re.DOTALL)
    description = "\n\n".join(
        html_lib.unescape(re.sub(r"<[^>]+>", "", p).strip())
        for p in paragraphs
        if p.strip()
    )

    # Image URL
    img_match = re.search(r'<img[^>]+src="([^"]+)"', summary_html)
    image_url = img_match.group(1) if img_match else None

    # Location: "Venue - City - Province"
    loc_match = re.search(
        r'<div\s+class="info">\s*\n?\s*.+?<br\s*/?>\s*\n?\s*(.+?)<br',
        summary_html,
        re.DOTALL,
    )
    venue, city, province = None, None, None
    if loc_match:
        location_text = re.sub(r"<[^>]+>", "", loc_match.group(1)).strip()
        parts = [p.strip() for p in location_text.split(" - ")]
        venue = parts[0] if len(parts) >= 1 else None
        city = parts[1] if len(parts) >= 2 else None
        province = parts[2] if len(parts) >= 3 else None

    # Resolve province from city if not explicit
    if not province and city:
        province = GALICIA_CITY_PROVINCE.get(city.lower())

    # Dates
    start_date = date(pp.tm_year, pp.tm_mon, pp.tm_mday) if pp else date.today()
    start_time_val = (
        time(pp.tm_hour, pp.tm_min)
        if pp and (pp.tm_hour > 0 or pp.tm_min > 0)
        else None
    )

    return {
        "id": str(entry.get("id", "")),
        "title": title,
        "description": description,
        "start_date": start_date,
        "start_time": start_time_val,
        "venue_name": venue,
        "city": city,
        "province": province,
        "image_url": image_url,
        "external_url": entry.get("link", ""),
        "external_id": f"galicia_cultura_{entry.get('id', '')}",
        # For LLM
        "@type": "",
        "audience": "",
        "price_info": "",
    }


async def main(limit: int = 20):
    """Main pipeline: fetch, enrich, insert."""
    settings = get_settings()

    print("=" * 60)
    print("GALICIA RSS -> LLM ENRICHMENT -> SUPABASE")
    print("=" * 60)
    print(f"\nConfig:")
    print(f"  LLM Enabled: {settings.llm_enabled}")
    print(f"  LLM Provider: {settings.llm_provider}")
    print(f"  Limit: {limit} eventos")

    # 1. Fetch RSS
    print(f"\n[1/4] Fetching RSS from cultura.gal...")
    feed = feedparser.parse("https://www.cultura.gal/es/rssaxenda")
    print(f"  Found {len(feed.entries)} entries in RSS")

    # Parse entries
    events_raw = [parse_rss_entry(e) for e in feed.entries[:limit]]
    print(f"  Parsed {len(events_raw)} events")

    # 2. Enrich with LLM
    print(f"\n[2/4] Enriching with LLM (batch)...")
    enricher = get_llm_enricher()

    if not enricher.is_enabled:
        print("  ERROR: LLM not enabled. Set LLM_ENABLED=true in .env")
        return

    # Prepare events for LLM
    events_for_llm = [
        {
            "id": e["external_id"],
            "title": e["title"],
            "description": e["description"][:800],  # Truncate for LLM
            "@type": e.get("@type", ""),
            "audience": e.get("audience", ""),
            "price_info": e.get("price_info", ""),
        }
        for e in events_raw
    ]

    enrichments = enricher.enrich_batch(
        events_for_llm,
        batch_size=10,  # Process 10 at a time
        tier=SourceTier.PLATA,
    )
    print(f"  Enriched {len(enrichments)} events")

    # 3. Create EventCreate objects
    print(f"\n[3/4] Creating EventCreate objects...")
    events_to_insert = []

    for raw in events_raw:
        enrichment = enrichments.get(raw["external_id"])

        # Determine price info - always provide descriptive text for UI
        # is_free=True: Gratis confirmado -> "Entrada gratuita"
        # is_free=False: De pago -> price_details o None
        # is_free=None: No especificado -> None (frontend handles display)
        if enrichment:
            is_free = enrichment.is_free
            price = enrichment.price

            if is_free is True:
                # Free event
                price_info = enrichment.price_details if enrichment.price_details else "Entrada gratuita"
            elif is_free is False:
                # Paid event
                if enrichment.price_details:
                    price_info = enrichment.price_details
                else:
                    # No details - let frontend handle
                    price_info = None
            else:
                # Unknown - no generic text
                price_info = None
        else:
            is_free = None
            price = None
            price_info = None

        event = EventCreate(
            # Basic fields from RSS
            title=raw["title"],
            description=raw["description"],
            start_date=raw["start_date"],
            start_time=raw["start_time"],
            # Location
            location_type=LocationType.PHYSICAL,
            venue_name=raw["venue_name"],
            city=raw["city"],
            province=raw["province"],
            comunidad_autonoma="Galicia",
            # Source
            source_id="galicia_cultura",
            external_url=raw["external_url"],
            external_id=raw["external_id"],
            source_image_url=raw["image_url"],
            # From LLM enrichment
            summary=enrichment.summary if enrichment else None,
            category_slugs=enrichment.category_slugs if enrichment else [],
            is_free=is_free,
            price=price,
            price_info=price_info,
        )
        events_to_insert.append(event)

    print(f"  Created {len(events_to_insert)} EventCreate objects")

    # 4. Insert into Supabase
    print(f"\n[4/4] Inserting into Supabase...")
    client = get_supabase_client()

    inserted = 0
    failed = 0
    skipped = 0

    for i, event in enumerate(events_to_insert, 1):
        # Check if already exists
        exists = await client.event_exists(event.external_id)
        if exists:
            print(f"  [{i}/{len(events_to_insert)}] SKIP (exists): {event.title[:40]}...")
            skipped += 1
            continue

        result = await client.insert_event(event, generate_embedding=True)
        if result:
            print(f"  [{i}/{len(events_to_insert)}] OK: {event.title[:40]}...")
            inserted += 1
        else:
            print(f"  [{i}/{len(events_to_insert)}] FAIL: {event.title[:40]}...")
            failed += 1

    # Summary
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"  Total procesados: {len(events_to_insert)}")
    print(f"  Insertados: {inserted}")
    print(f"  Skipped (existentes): {skipped}")
    print(f"  Fallidos: {failed}")
    print(f"\n  Campos rellenados por LLM:")
    print(f"    - category_slugs")
    print(f"    - summary")
    print(f"    - is_free / price")
    print(f"    - age_range (en enrichment)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Insert Galicia events into Supabase")
    parser.add_argument("--limit", type=int, default=20, help="Number of events to process")
    args = parser.parse_args()

    asyncio.run(main(limit=args.limit))
