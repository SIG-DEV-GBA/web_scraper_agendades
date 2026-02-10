#!/usr/bin/env python3
"""Test category classification distribution."""
import sys
import asyncio
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.bronze_scraper_adapter import BronzeScraperAdapter
from src.core.llm_enricher import LLMEnricher, SourceTier

async def main():
    print("Fetching events...")
    adapter = BronzeScraperAdapter("canarias_lagenda")
    events_raw = await adapter.fetch_events(enrich=False, fetch_details=True)

    # Limit to 30 for testing
    events_raw = events_raw[:30]
    print(f"Processing {len(events_raw)} events...\n")

    # Prepare for LLM
    events_for_llm = [
        {
            "id": e["external_id"],
            "title": e["title"],
            "description": e.get("description", "")[:500],
            "@type": e.get("category_raw", ""),
            "audience": "",
            "price_info": e.get("price_raw", ""),
        }
        for e in events_raw
    ]

    # Enrich
    enricher = LLMEnricher()
    enrichments = enricher.enrich_batch(events_for_llm, batch_size=15, tier=SourceTier.BRONCE)

    # Analyze
    category_counter = Counter()
    primary_counter = Counter()

    print("=" * 80)
    print("CLASIFICACIÓN DE EVENTOS:")
    print("=" * 80)

    for i, raw in enumerate(events_raw):
        enrichment = enrichments.get(raw["external_id"])
        if enrichment:
            cats = enrichment.category_slugs
            for cat in cats:
                category_counter[cat] += 1
            if cats:
                primary_counter[cats[0]] += 1

            title = raw["title"][:45]
            cats_str = ", ".join(cats) if cats else "N/A"
            print(f"[{i+1:2}] {title:45} → {cats_str}")

    print("\n" + "=" * 80)
    print("DISTRIBUCIÓN (categoría principal):")
    print("=" * 80)
    for cat, count in primary_counter.most_common():
        pct = count / len(events_raw) * 100
        bar = "█" * int(pct / 5)
        print(f"  {cat:12} {count:3} ({pct:5.1f}%) {bar}")

    print("\n" + "=" * 80)
    print("DISTRIBUCIÓN (todas las categorías):")
    print("=" * 80)
    for cat, count in category_counter.most_common():
        print(f"  {cat:12} {count:3}")

if __name__ == "__main__":
    asyncio.run(main())
