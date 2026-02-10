#!/usr/bin/env python3
"""Test Plata (Silver) level quality - Galicia RSS with LLM enrichment.

Analyzes:
1. Raw RSS field coverage
2. LLM enrichment quality (categories, price, summary)
3. Final EventCreate completeness
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
from src.logging.logger import get_logger

# Fix encoding for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

logger = get_logger(__name__)

# Galicia province mapping
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
        "@type": "",
        "audience": "",
        "price_info": "",
    }


def analyze_raw_coverage(events_raw: list[dict]) -> dict:
    """Analyze raw RSS field coverage."""
    fields = ["title", "description", "venue_name", "city", "province",
              "start_date", "start_time", "image_url", "external_url"]

    coverage = {}
    for field in fields:
        filled = sum(1 for e in events_raw if e.get(field))
        coverage[field] = (filled, len(events_raw), filled / len(events_raw) * 100)

    return coverage


def analyze_enrichment_quality(enrichments: dict) -> dict:
    """Analyze LLM enrichment quality."""
    total = len(enrichments)
    if total == 0:
        return {}

    stats = {
        "has_summary": 0,
        "has_categories": 0,
        "category_count_avg": 0,
        "is_free_true": 0,
        "is_free_false": 0,
        "is_free_none": 0,
        "has_price": 0,
        "has_price_details": 0,
    }

    category_counts = []

    for ext_id, enrichment in enrichments.items():
        if enrichment.summary:
            stats["has_summary"] += 1
        if enrichment.category_slugs:
            stats["has_categories"] += 1
            category_counts.append(len(enrichment.category_slugs))
        if enrichment.is_free is True:
            stats["is_free_true"] += 1
        elif enrichment.is_free is False:
            stats["is_free_false"] += 1
        else:
            stats["is_free_none"] += 1
        if enrichment.price:
            stats["has_price"] += 1
        if enrichment.price_details:
            stats["has_price_details"] += 1

    if category_counts:
        stats["category_count_avg"] = sum(category_counts) / len(category_counts)

    return stats


def analyze_final_model(events: list[EventCreate]) -> dict:
    """Analyze final EventCreate model completeness."""
    required_for_ui = [
        "title", "description", "summary", "start_date", "start_time",
        "venue_name", "city", "province", "comunidad_autonoma",
        "source_image_url", "external_url", "category_slugs",
        "is_free", "price_info"
    ]

    coverage = {}
    for field in required_for_ui:
        filled = 0
        for e in events:
            val = getattr(e, field, None)
            if val is not None and val != [] and val != "":
                filled += 1
        coverage[field] = (filled, len(events), filled / len(events) * 100)

    return coverage


async def main(limit: int = 20):
    """Main analysis pipeline."""
    settings = get_settings()

    print("=" * 70)
    print("PLATA LEVEL QUALITY ANALYSIS - GALICIA RSS + LLM")
    print("=" * 70)
    print(f"\nConfig:")
    print(f"  LLM Enabled: {settings.llm_enabled}")
    print(f"  LLM Provider: {settings.llm_provider}")
    print(f"  Limit: {limit} eventos")

    # 1. Fetch RSS
    print(f"\n{'='*70}")
    print("1. RAW RSS FIELD COVERAGE")
    print("=" * 70)

    feed = feedparser.parse("https://www.cultura.gal/es/rssaxenda")
    print(f"  Total entries in RSS: {len(feed.entries)}")

    events_raw = [parse_rss_entry(e) for e in feed.entries[:limit]]
    print(f"  Parsed: {len(events_raw)} events")

    raw_coverage = analyze_raw_coverage(events_raw)
    print(f"\n  Field Coverage (from RSS parsing):")
    for field, (filled, total, pct) in raw_coverage.items():
        status = "OK" if pct == 100 else "PARTIAL" if pct > 50 else "LOW"
        print(f"    {field:15} {filled:3}/{total} ({pct:5.1f}%) [{status}]")

    # 2. LLM Enrichment
    print(f"\n{'='*70}")
    print("2. LLM ENRICHMENT QUALITY")
    print("=" * 70)

    enricher = get_llm_enricher()

    if not enricher.is_enabled:
        print("  ERROR: LLM not enabled. Set LLM_ENABLED=true in .env")
        return

    events_for_llm = [
        {
            "id": e["external_id"],
            "title": e["title"],
            "description": e["description"][:800],
            "@type": e.get("@type", ""),
            "audience": e.get("audience", ""),
            "price_info": e.get("price_info", ""),
        }
        for e in events_raw
    ]

    print(f"  Enriching {len(events_for_llm)} events with LLM...")
    enrichments = enricher.enrich_batch(
        events_for_llm,
        batch_size=10,
        tier=SourceTier.PLATA,
    )
    print(f"  Enriched: {len(enrichments)} events")

    enrichment_stats = analyze_enrichment_quality(enrichments)
    total = len(enrichments)

    print(f"\n  Enrichment Results:")
    print(f"    Has summary:        {enrichment_stats['has_summary']:3}/{total} ({enrichment_stats['has_summary']/total*100:5.1f}%)")
    print(f"    Has categories:     {enrichment_stats['has_categories']:3}/{total} ({enrichment_stats['has_categories']/total*100:5.1f}%)")
    print(f"    Avg categories/evt: {enrichment_stats['category_count_avg']:.1f}")
    print(f"    Price detection:")
    print(f"      is_free=True:     {enrichment_stats['is_free_true']:3}/{total} ({enrichment_stats['is_free_true']/total*100:5.1f}%)")
    print(f"      is_free=False:    {enrichment_stats['is_free_false']:3}/{total} ({enrichment_stats['is_free_false']/total*100:5.1f}%)")
    print(f"      is_free=None:     {enrichment_stats['is_free_none']:3}/{total} ({enrichment_stats['is_free_none']/total*100:5.1f}%)")
    print(f"    Has price value:    {enrichment_stats['has_price']:3}/{total} ({enrichment_stats['has_price']/total*100:5.1f}%)")
    print(f"    Has price details:  {enrichment_stats['has_price_details']:3}/{total} ({enrichment_stats['has_price_details']/total*100:5.1f}%)")

    # 3. Final Model Completeness
    print(f"\n{'='*70}")
    print("3. FINAL MODEL COMPLETENESS (EventCreate)")
    print("=" * 70)

    events_final = []
    for raw in events_raw:
        enrichment = enrichments.get(raw["external_id"])

        # Determine price info - always provide descriptive text
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
                elif price:
                    price_info = f"{price:.2f}€"
                else:
                    price_info = "Consultar precio en web del organizador"
            else:
                # Unknown
                price_info = "Consultar en web del organizador"
        else:
            is_free = None
            price = None
            price_info = "Consultar en web del organizador"

        event = EventCreate(
            title=raw["title"],
            description=raw["description"],
            start_date=raw["start_date"],
            start_time=raw["start_time"],
            location_type=LocationType.PHYSICAL,
            venue_name=raw["venue_name"],
            city=raw["city"],
            province=raw["province"],
            comunidad_autonoma="Galicia",
            source_id="galicia_cultura",
            external_url=raw["external_url"],
            external_id=raw["external_id"],
            source_image_url=raw["image_url"],
            summary=enrichment.summary if enrichment else None,
            category_slugs=enrichment.category_slugs if enrichment else [],
            is_free=is_free,
            price=price,
            price_info=price_info,
        )
        events_final.append(event)

    final_coverage = analyze_final_model(events_final)
    print(f"\n  UI-Required Fields Coverage:")
    for field, (filled, total, pct) in final_coverage.items():
        status = "OK" if pct >= 90 else "GOOD" if pct >= 70 else "PARTIAL" if pct > 50 else "LOW"
        print(f"    {field:20} {filled:3}/{total} ({pct:5.1f}%) [{status}]")

    # 4. Sample Events
    print(f"\n{'='*70}")
    print("4. SAMPLE EVENTS (first 3)")
    print("=" * 70)

    for i, event in enumerate(events_final[:3], 1):
        print(f"\n  [{i}] {event.title[:60]}...")
        print(f"      Date: {event.start_date} {event.start_time or 'N/A'}")
        print(f"      Location: {event.venue_name}, {event.city} ({event.province})")
        print(f"      Categories: {event.category_slugs}")
        print(f"      Price: is_free={event.is_free}, info={event.price_info}")
        print(f"      Summary: {event.summary[:100] if event.summary else 'N/A'}...")

    # 5. Summary
    print(f"\n{'='*70}")
    print("5. RESUMEN NIVEL PLATA")
    print("=" * 70)

    # Calculate overall score
    total_fields = len(final_coverage)
    avg_coverage = sum(pct for _, _, pct in final_coverage.values()) / total_fields

    print(f"\n  Overall Field Coverage: {avg_coverage:.1f}%")
    print(f"\n  Missing from RSS (filled by LLM):")
    print(f"    - summary:        LLM generates short description")
    print(f"    - category_slugs: LLM classifies into our categories")
    print(f"    - is_free/price:  LLM detects from description")
    print(f"\n  Missing entirely (not in source):")
    print(f"    - organizer:      Not in RSS")
    print(f"    - accessibility:  Not in RSS")
    print(f"    - coordinates:    Would need geocoding")
    print(f"    - age_range:      LLM could infer but not mapped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze Plata level quality")
    parser.add_argument("--limit", type=int, default=20, help="Number of events to process")
    args = parser.parse_args()

    asyncio.run(main(limit=args.limit))
