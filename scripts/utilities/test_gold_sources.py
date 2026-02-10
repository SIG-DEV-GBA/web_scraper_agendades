#!/usr/bin/env python
"""Test script to validate Gold-level adapters and LLM classification.

Tests 20 events from each of the 5 CCAA sources to evaluate:
1. Data quality (title, description, dates, location)
2. LLM category classification accuracy
3. Image keywords relevance

Usage:
    python test_gold_sources.py
    python test_gold_sources.py --source madrid
    python test_gold_sources.py --limit 10
"""

import argparse
import asyncio
import os
import sys
from datetime import date

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["LLM_ENABLED"] = "true"

from src.adapters import get_adapter, list_adapters
from src.adapters.gold_api_adapter import GOLD_SOURCES
from src.core.llm_enricher import get_llm_enricher
from src.logging.logger import get_logger

logger = get_logger(__name__)


# Category color coding for terminal
CATEGORY_COLORS = {
    "cultural": "\033[95m",      # Magenta
    "social": "\033[92m",        # Green
    "economica": "\033[93m",     # Yellow
    "politica": "\033[91m",      # Red
    "sanitaria": "\033[96m",     # Cyan
    "tecnologia": "\033[94m",    # Blue
}
RESET = "\033[0m"
BOLD = "\033[1m"


def colored_category(cat: str) -> str:
    """Return colored category string."""
    color = CATEGORY_COLORS.get(cat, "")
    return f"{color}{cat.upper()}{RESET}"


async def test_source(source_slug: str, limit: int = 20) -> dict:
    """Test a single source adapter.

    Returns:
        dict with test results
    """
    print(f"\n{'='*70}")
    print(f"{BOLD}Testing: {source_slug}{RESET}")
    print(f"{'='*70}")

    config = GOLD_SOURCES.get(source_slug)
    if not config:
        print(f"  ERROR: Source {source_slug} not found")
        return {"source": source_slug, "error": "Source not found"}

    print(f"  CCAA: {config.ccaa}")
    print(f"  URL: {config.url[:70]}...")
    print(f"  Pagination: {config.pagination_type.value}")

    # Get adapter
    adapter_class = get_adapter(source_slug)
    if not adapter_class:
        print(f"  ERROR: Adapter not registered")
        return {"source": source_slug, "error": "Adapter not registered"}

    adapter = adapter_class()

    # Fetch events
    print(f"\n  Fetching events (max {limit})...")
    try:
        raw_events = await adapter.fetch_events(max_pages=2)
        print(f"  Total raw events: {len(raw_events)}")
    except Exception as e:
        print(f"  FETCH ERROR: {e}")
        return {"source": source_slug, "error": f"Fetch error: {e}"}

    # Parse events (limit to N)
    events = []
    for raw in raw_events[:limit]:
        event = adapter.parse_event(raw)
        if event:
            events.append(event)

    print(f"  Parsed events: {len(events)}")

    if not events:
        print(f"  WARNING: No events parsed!")
        return {"source": source_slug, "events": 0, "error": "No events parsed"}

    # Data quality check
    print(f"\n  {BOLD}DATA QUALITY CHECK:{RESET}")
    with_description = sum(1 for e in events if e.description)
    with_venue = sum(1 for e in events if e.venue_name)
    with_city = sum(1 for e in events if e.city)
    with_coords = sum(1 for e in events if e.latitude and e.longitude)
    with_image = sum(1 for e in events if e.source_image_url)
    future_dates = sum(1 for e in events if e.start_date and e.start_date >= date.today())

    print(f"  - With description: {with_description}/{len(events)} ({100*with_description//len(events)}%)")
    print(f"  - With venue:       {with_venue}/{len(events)} ({100*with_venue//len(events)}%)")
    print(f"  - With city:        {with_city}/{len(events)} ({100*with_city//len(events)}%)")
    print(f"  - With coords:      {with_coords}/{len(events)} ({100*with_coords//len(events)}%)")
    print(f"  - With image:       {with_image}/{len(events)} ({100*with_image//len(events)}%)")
    print(f"  - Future dates:     {future_dates}/{len(events)} ({100*future_dates//len(events)}%)")

    # LLM Enrichment
    print(f"\n  {BOLD}LLM ENRICHMENT:{RESET}")
    enricher = get_llm_enricher()

    # Prepare events for enricher
    events_for_llm = []
    for e in events:
        events_for_llm.append({
            "id": e.external_id,
            "title": e.title,
            "description": e.description,
            "@type": e.category_name or "",
            "audience": "",
        })

    # Use smaller batch_size to avoid JSON truncation with long descriptions
    enrichments = enricher.enrich_batch(events_for_llm, batch_size=10)

    # Show results
    print(f"  Enriched: {len(enrichments)} events")

    category_counts = {}
    results = []

    print(f"\n  {BOLD}SAMPLE EVENTS WITH CLASSIFICATION:{RESET}")
    print("-" * 70)

    for i, event in enumerate(events[:20]):
        enrichment = enrichments.get(event.external_id)
        # Now using category_slugs (list) instead of category_slug (single)
        cats = enrichment.category_slugs if enrichment else []
        cat = cats[0] if cats else "N/A"
        cat_display = ", ".join(cats) if cats else "N/A"
        summary = (enrichment.summary[:60] + "...") if enrichment and enrichment.summary else "N/A"
        img_kw = ", ".join(enrichment.image_keywords) if enrichment else "N/A"
        price = f"{enrichment.price}EUR" if enrichment and enrichment.price else "free"

        # Count primary category
        category_counts[cat] = category_counts.get(cat, 0) + 1

        # Truncate title for display
        title = event.title[:55] + "..." if len(event.title) > 55 else event.title
        city = event.city or "?"
        date_str = event.start_date.strftime("%d/%m") if event.start_date else "?"
        has_desc = "+" if event.description else "-"

        print(f"  {i+1:2}. [{colored_category(cat):20}] {title}")
        print(f"      {city} | {date_str} | desc:{has_desc} | cats: {cat_display} | {price}")
        if enrichment and enrichment.summary:
            print(f"      Summary: {summary}")
        print(f"      Img: {img_kw}")
        print()

        results.append({
            "title": event.title,
            "categories": cats,
            "summary": enrichment.summary if enrichment else None,
            "image_keywords": enrichment.image_keywords if enrichment else [],
            "price": enrichment.price if enrichment else None,
            "city": event.city,
            "has_description": bool(event.description),
        })

    print("-" * 70)
    print(f"  {BOLD}CATEGORY DISTRIBUTION:{RESET}")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        bar = "*" * count
        print(f"    {colored_category(cat):20} {bar} ({count})")

    return {
        "source": source_slug,
        "ccaa": config.ccaa,
        "total_raw": len(raw_events),
        "total_parsed": len(events),
        "data_quality": {
            "with_description": with_description,
            "with_venue": with_venue,
            "with_city": with_city,
            "with_coords": with_coords,
            "with_image": with_image,
            "future_dates": future_dates,
        },
        "categories": category_counts,
        "events": results,
    }


async def main():
    parser = argparse.ArgumentParser(description="Test Gold-level adapters")
    parser.add_argument(
        "--source", "-s",
        help="Test only this source (default: all)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Events per source (default: 20)",
    )

    args = parser.parse_args()

    # Available sources
    sources = list(GOLD_SOURCES.keys())

    if args.source:
        if args.source not in sources:
            print(f"ERROR: Unknown source '{args.source}'")
            print(f"Available: {', '.join(sources)}")
            sys.exit(1)
        sources = [args.source]

    print(f"\n{'#'*70}")
    print(f"# GOLD SOURCES TEST - {len(sources)} sources, {args.limit} events each")
    print(f"{'#'*70}")
    print(f"\nSources to test: {', '.join(sources)}")

    all_results = []

    for source in sources:
        try:
            result = await test_source(source, limit=args.limit)
            all_results.append(result)
        except Exception as e:
            print(f"\n  FATAL ERROR testing {source}: {e}")
            all_results.append({"source": source, "error": str(e)})

    # Final summary
    print(f"\n{'#'*70}")
    print(f"# FINAL SUMMARY")
    print(f"{'#'*70}")

    total_events = 0
    total_categories = {}

    for result in all_results:
        if "error" not in result or result.get("total_parsed", 0) > 0:
            source = result["source"]
            parsed = result.get("total_parsed", 0)
            total_events += parsed

            dq = result.get("data_quality", {})
            desc_pct = 100 * dq.get("with_description", 0) // max(1, parsed)

            cats = result.get("categories", {})
            for c, n in cats.items():
                total_categories[c] = total_categories.get(c, 0) + n

            top_cat = max(cats.items(), key=lambda x: x[1])[0] if cats else "N/A"

            print(f"\n{source}:")
            print(f"  Events: {parsed}, Desc: {desc_pct}%, Top cat: {colored_category(top_cat)}")

    print(f"\n{BOLD}TOTAL ACROSS ALL SOURCES:{RESET}")
    print(f"  Events tested: {total_events}")
    print(f"\n  Category distribution:")
    for cat, count in sorted(total_categories.items(), key=lambda x: -x[1]):
        pct = 100 * count // max(1, total_events)
        bar = "*" * (count // 2)
        print(f"    {colored_category(cat):20} {bar} ({count}, {pct}%)")


if __name__ == "__main__":
    asyncio.run(main())
