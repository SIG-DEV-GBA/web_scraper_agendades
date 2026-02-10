#!/usr/bin/env python3
"""Test the updated Andalucía adapter."""
import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter


async def main():
    print("=" * 60)
    print("TEST ADAPTER ANDALUCÍA (Nueva API)")
    print("=" * 60)

    adapter = GoldAPIAdapter("andalucia_agenda")

    print(f"\nURL: {adapter.gold_config.url[:70]}...")
    print(f"Pagination: {adapter.gold_config.pagination_type}")
    print(f"Page size: {adapter.gold_config.page_size}")

    # Fetch events
    print("\nFetching events...")
    raw_events = await adapter.fetch_events(max_pages=2)
    print(f"Raw events: {len(raw_events)}")

    # Parse events
    print("\nParsing events...")
    parsed = []
    for raw in raw_events[:10]:
        event = adapter.parse_event(raw)
        if event:
            parsed.append(event)

    print(f"Parsed: {len(parsed)}")

    # Show samples
    print("\n" + "-" * 60)
    print("SAMPLE EVENTS:")
    for i, e in enumerate(parsed[:5], 1):
        print(f"\n{i}. {e.title[:50]}...")
        print(f"   Fecha: {e.start_date} - {e.end_date}")
        print(f"   Ciudad: {e.city}, {e.province}")
        print(f"   Precio: {e.is_free} - {e.price_info}")
        print(f"   Imagen: {e.source_image_url[:50] if e.source_image_url else 'N/A'}...")

    # Stats
    print("\n" + "-" * 60)
    print("ESTADÍSTICAS:")
    with_city = sum(1 for e in parsed if e.city)
    with_province = sum(1 for e in parsed if e.province)
    with_image = sum(1 for e in parsed if e.source_image_url)
    with_desc = sum(1 for e in parsed if e.description)

    print(f"  Con ciudad: {with_city}/{len(parsed)}")
    print(f"  Con provincia: {with_province}/{len(parsed)}")
    print(f"  Con imagen: {with_image}/{len(parsed)}")
    print(f"  Con descripción: {with_desc}/{len(parsed)}")


if __name__ == "__main__":
    asyncio.run(main())
