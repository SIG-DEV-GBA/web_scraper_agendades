#!/usr/bin/env python
"""Debug CyL enrichment issue."""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.adapters import get_adapter
from src.core.llm_enricher import get_llm_enricher, SourceTier, EventEnrichment


async def main():
    adapter_class = get_adapter('castilla_leon_agenda')
    adapter = adapter_class()

    raw = await adapter.fetch_events(max_pages=1)
    events = []
    for r in raw[:10]:
        e = adapter.parse_event(r)
        if e:
            events.append(e)

    print(f"Parsed {len(events)} events")

    # Prepare for LLM
    events_for_llm = []
    for e in events:
        events_for_llm.append({
            'id': e.external_id,
            'title': e.title,
            'description': (e.description or '')[:500],
            '@type': e.category_name or '',
            'audience': '',
            'price_info': e.price_info or '',
        })

    print(f"\nSending {len(events_for_llm)} to LLM...")
    print("\nEvent IDs being sent:")
    for e in events_for_llm:
        print(f"  - {e['id']}")

    enricher = get_llm_enricher()
    results = enricher.enrich_batch(events_for_llm, batch_size=10, tier=SourceTier.ORO)

    print(f"\n\nResults: {len(results)} enriched")
    print("\nMatching:")
    for e in events_for_llm:
        eid = e['id']
        if eid in results:
            r = results[eid]
            print(f"  OK: {eid[:40]} -> {r.category_slugs}")
        else:
            print(f"  MISSING: {eid[:40]}")


if __name__ == "__main__":
    asyncio.run(main())
