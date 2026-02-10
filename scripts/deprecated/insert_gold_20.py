#!/usr/bin/env python
"""Insert 20 events from each Gold source for testing."""

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ["LLM_ENABLED"] = "true"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.adapters import get_adapter
from src.core.llm_enricher import SourceTier, get_llm_enricher
from src.core.supabase_client import get_supabase_client

LIMIT = 20
SOURCES = [
    "euskadi_kulturklik",
    "castilla_leon_agenda",
    "andalucia_agenda",
    "madrid_datos_abiertos",
    "catalunya_agenda",
]


async def main():
    db = get_supabase_client()
    enricher = get_llm_enricher()

    total_inserted = 0

    for slug in SOURCES:
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  {slug} (limit={LIMIT})")
        print(sep)

        adapter_class = get_adapter(slug)
        adapter = adapter_class()

        # Fetch (max_pages=1 to limit volume)
        raw = await adapter.fetch_events(max_pages=1)
        print(f"  Fetched: {len(raw)} raw events")

        # Parse first N
        events = []
        for r in raw[:LIMIT]:
            e = adapter.parse_event(r)
            if e:
                if not e.external_id:
                    e.external_id = e.generate_external_id(slug)
                events.append(e)

        print(f"  Parsed: {len(events)} events")

        # LLM enrich
        if enricher.is_enabled and events:
            try:
                events_for_llm = [
                    {
                        "id": e.external_id,
                        "title": e.title,
                        "description": (e.description or "")[:300],
                        "@type": e.category_name or "",
                        "audience": "",
                        "price_info": e.price_info or "",
                    }
                    for e in events
                ]

                enrichments = enricher.enrich_batch(
                    events_for_llm, batch_size=10, tier=SourceTier.ORO
                )

                for event in events:
                    enr = enrichments.get(event.external_id)
                    if enr:
                        event.category_slugs = enr.category_slugs
                        if enr.summary:
                            event.summary = enr.summary
                        if enr.price is not None:
                            event.price = enr.price
                        if enr.price_details:
                            event.price_info = enr.price_details
                        else:
                            event.price_info = None  # No generic text

                    # If no price_info but we have official URL, put it in price_info
                    if not event.price_info and event.registration_url:
                        event.price_info = event.registration_url

                print(f"  Enriched: {len(enrichments)} events")
            except Exception as ex:
                print(f"  LLM error (continuing without): {str(ex)[:100]}")

        # Insert
        inserted = 0
        skipped = 0
        errors = 0
        for event in events:
            try:
                exists = await db.event_exists(event.external_id)
                if exists:
                    skipped += 1
                    continue
                result = await db.insert_event(event)
                if result:
                    inserted += 1
                else:
                    errors += 1
            except Exception as ex:
                errors += 1
                print(f"    Error: {str(ex)[:80]}")

        total_inserted += inserted
        print(f"  Inserted: {inserted}, Skipped: {skipped}, Errors: {errors}")

        # Sample output
        print(f"  Sample:")
        for e in events[:3]:
            t = e.start_time.strftime("%H:%M") if e.start_time else "--:--"
            cats = ",".join(e.category_slugs[:2]) if e.category_slugs else "N/A"
            print(f"    {t} | {e.title[:45]:45s} | {cats}")

    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  TOTAL INSERTED: {total_inserted}")
    print(sep)


if __name__ == "__main__":
    asyncio.run(main())
