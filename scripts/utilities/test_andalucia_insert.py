#!/usr/bin/env python3
"""Test inserting Andalucía events - 2 per province."""
import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter
from src.core.llm_enricher import get_llm_enricher, SourceTier
from src.core.supabase_client import SupabaseClient

EVENTS_PER_PROVINCE = 2
ANDALUCIA_PROVINCES = [
    "Almería", "Cádiz", "Córdoba", "Granada",
    "Huelva", "Jaén", "Málaga", "Sevilla"
]


async def main():
    print("=" * 60)
    print(f"TEST ANDALUCÍA - {EVENTS_PER_PROVINCE} eventos por provincia")
    print("=" * 60)

    adapter = GoldAPIAdapter("andalucia_agenda")
    db = SupabaseClient()
    enricher = get_llm_enricher()

    # Fetch events (get enough to cover all provinces)
    print("\nFetching events...")
    raw_events = await adapter.fetch_events(max_pages=10)
    print(f"Raw: {len(raw_events)}")

    # Parse all events
    parsed = []
    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event:
            parsed.append(event)
    print(f"Parsed: {len(parsed)}")

    # Group by province
    by_province = {}
    for event in parsed:
        prov = event.province or "Unknown"
        if prov not in by_province:
            by_province[prov] = []
        if len(by_province[prov]) < EVENTS_PER_PROVINCE:
            by_province[prov].append(event)

    # Flatten selected events
    selected = []
    for prov, events in by_province.items():
        selected.extend(events)

    print(f"Selected: {len(selected)} ({len(by_province)} provinces)")

    # Enrich with LLM
    print("\nEnriching with LLM...")
    events_for_llm = [
        {
            "id": e.external_id,
            "title": e.title,
            "description": e.description or "",
            "@type": e.category_name or "",
            "audience": "",
            "price_info": e.price_info or "",
        }
        for e in selected
    ]

    enrichments = enricher.enrich_batch(events_for_llm, batch_size=10, tier=SourceTier.ORO)
    print(f"Enriched: {len(enrichments)}")

    # Apply enrichments
    for event in selected:
        enr = enrichments.get(event.external_id)
        if enr:
            event.category_slugs = enr.category_slugs or []
            if enr.summary:
                event.summary = enr.summary
            if enr.price is not None:
                event.price = enr.price
            if enr.is_free is not None:
                event.is_free = enr.is_free

    # Insert events
    print("\nInserting events...")
    inserted = 0
    by_prov_result = {}

    for event in selected:
        prov = event.province or "Unknown"
        if prov not in by_prov_result:
            by_prov_result[prov] = {"ok": 0, "fail": 0}

        try:
            result = await db.insert_event(event, generate_embedding=False)
            if result:
                inserted += 1
                by_prov_result[prov]["ok"] += 1
                free_tag = "GRATIS" if event.is_free else "PAGO" if event.is_free is False else "?"
                print(f"  ✓ [{free_tag:6}] {event.title[:40]}... ({prov})")
        except Exception as e:
            by_prov_result[prov]["fail"] += 1
            print(f"  ✗ {event.title[:40]}... - {str(e)[:30]}")

    # Summary
    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)

    for prov in ANDALUCIA_PROVINCES:
        res = by_prov_result.get(prov, {"ok": 0, "fail": 0})
        status = "✓" if res["ok"] > 0 else "✗"
        print(f"  {prov}: {res['ok']}/{EVENTS_PER_PROVINCE} {status}")

    print(f"\nTotal insertados: {inserted}/{len(selected)}")


if __name__ == "__main__":
    asyncio.run(main())
