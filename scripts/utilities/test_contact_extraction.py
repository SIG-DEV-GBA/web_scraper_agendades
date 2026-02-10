#!/usr/bin/env python3
"""Test contact extraction from Catalunya."""
import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter


async def main():
    print("=" * 60)
    print("TEST CONTACT EXTRACTION - CATALUNYA")
    print("=" * 60)

    adapter = GoldAPIAdapter("catalunya_agenda")

    print("\nFetching events...")
    raw_events = await adapter.fetch_events(max_pages=1)
    print(f"Raw: {len(raw_events)}")

    # Parse and count contacts
    with_contact = 0
    without_contact = 0
    samples = []

    for raw in raw_events[:50]:
        event = adapter.parse_event(raw)
        if event:
            if event.contact and (event.contact.email or event.contact.phone):
                with_contact += 1
                if len(samples) < 3:
                    samples.append(event)
            else:
                without_contact += 1

    print(f"\nResultados:")
    print(f"  Con contacto: {with_contact}")
    print(f"  Sin contacto: {without_contact}")
    print(f"  % con contacto: {100*with_contact//(with_contact+without_contact)}%")

    print(f"\nEjemplos con contacto:")
    for e in samples:
        print(f"\n  {e.title[:50]}...")
        if e.contact:
            print(f"    Email: {e.contact.email}")
            print(f"    Phone: {e.contact.phone}")


if __name__ == "__main__":
    asyncio.run(main())
