#!/usr/bin/env python3
"""Test inserting 5 events per province from Castilla y León."""
import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter
from src.core.llm_enricher import get_llm_enricher, SourceTier
from src.core.supabase_client import SupabaseClient

EVENTS_PER_PROVINCE = 5


async def test_cyl():
    print("=" * 60)
    print(f"TEST CASTILLA Y LEÓN - {EVENTS_PER_PROVINCE} eventos por provincia")
    print("=" * 60)

    adapter = GoldAPIAdapter("castilla_leon_agenda")
    db = SupabaseClient()
    enricher = get_llm_enricher()

    # Fetch events
    print("\nFetching events...")
    raw_events = await adapter.fetch_events(max_pages=10)
    print(f"Total raw: {len(raw_events)}")

    # Separate paid and free events
    paid_events = [e for e in raw_events if e.get("precio") and "€" in str(e.get("precio", ""))]
    print(f"Eventos de pago encontrados: {len(paid_events)}")

    # Group by province, prioritizing 1 paid event per province if available
    by_province = {}
    paid_by_province = {}

    # First pass: collect paid events by province
    for raw in paid_events:
        prov = raw.get("nombre_provincia", "Unknown")
        if prov not in paid_by_province:
            paid_by_province[prov] = raw

    # Second pass: build final selection
    for raw in raw_events:
        prov = raw.get("nombre_provincia", "Unknown")
        if prov not in by_province:
            by_province[prov] = []
            # Add paid event first if available
            if prov in paid_by_province:
                by_province[prov].append(paid_by_province[prov])

        if len(by_province[prov]) < EVENTS_PER_PROVINCE:
            # Avoid duplicates
            if raw not in by_province[prov]:
                by_province[prov].append(raw)

    print(f"\nProvincias: {list(by_province.keys())}")

    # Parse selected events
    selected = []
    for prov, raws in by_province.items():
        for raw in raws:
            event = adapter.parse_event(raw)
            if event:
                selected.append(event)

    print(f"Parsed: {len(selected)} eventos")

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
    free_count = 0
    paid_count = 0

    for event in selected:
        prov = event.province or "Unknown"
        if prov not in by_prov_result:
            by_prov_result[prov] = {"ok": 0, "fail": 0, "free": 0, "paid": 0}
        try:
            result = await db.insert_event(event, generate_embedding=False)
            if result:
                inserted += 1
                by_prov_result[prov]["ok"] += 1

                # Track free vs paid
                price_tag = "GRATIS" if event.is_free else f"PAGO ({event.price_info[:20]})" if event.price_info else "?"
                if event.is_free:
                    free_count += 1
                    by_prov_result[prov]["free"] += 1
                else:
                    paid_count += 1
                    by_prov_result[prov]["paid"] += 1

                print(f"  ✓ [{price_tag:25}] {event.title[:40]}... ({prov})")
        except Exception as e:
            by_prov_result[prov]["fail"] += 1
            print(f"  ✗ {event.title[:45]}... - {str(e)[:40]}")

    # Summary
    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)
    for prov, res in sorted(by_prov_result.items()):
        status = "✓" if res["fail"] == 0 else "⚠"
        free_paid = f"(gratis: {res['free']}, pago: {res['paid']})"
        print(f"  {prov}: {res['ok']}/{EVENTS_PER_PROVINCE} {status} {free_paid}")

    print(f"\nTotal insertados: {inserted}/{len(selected)}")
    print(f"  - Gratuitos: {free_count}")
    print(f"  - De pago: {paid_count}")


if __name__ == "__main__":
    asyncio.run(test_cyl())
