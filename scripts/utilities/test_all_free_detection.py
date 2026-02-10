#!/usr/bin/env python3
"""Test universal free detection across all Gold sources."""
import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter, GOLD_SOURCES


async def test_source(source_id: str, max_events: int = 20):
    """Test free detection for a single source."""
    print(f"\n{'='*60}")
    print(f"SOURCE: {source_id}")
    print("=" * 60)

    try:
        adapter = GoldAPIAdapter(source_id)
        raw_events = await adapter.fetch_events(max_pages=1)
        print(f"Raw: {len(raw_events)}")

        parsed = []
        for raw in raw_events[:max_events]:
            event = adapter.parse_event(raw)
            if event:
                parsed.append(event)

        if not parsed:
            print("  No events parsed")
            return

        free = sum(1 for e in parsed if e.is_free is True)
        paid = sum(1 for e in parsed if e.is_free is False)
        unknown = sum(1 for e in parsed if e.is_free is None)

        print(f"\nResultados ({len(parsed)} eventos):")
        print(f"  Gratuitos: {free} ({100*free//len(parsed)}%)")
        print(f"  De pago: {paid} ({100*paid//len(parsed)}%)")
        print(f"  Desconocido: {unknown} ({100*unknown//len(parsed)}%)")

        # Show samples
        if unknown > 0:
            print("\n⚠️ Eventos con precio desconocido:")
            for e in parsed:
                if e.is_free is None:
                    print(f"  ? {e.title[:40]}... | price_info: {e.price_info}")
                    break

        if paid > 0:
            print("\nEventos de pago:")
            shown = 0
            for e in parsed:
                if e.is_free is False and shown < 2:
                    print(f"  $ {e.title[:40]}... | {e.price_info}")
                    shown += 1

    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {str(e)[:50]}")


async def main():
    print("=" * 60)
    print("TEST DETECCIÓN GRATUITO - TODAS LAS FUENTES GOLD")
    print("=" * 60)

    # Test all sources
    for source_id in GOLD_SOURCES.keys():
        await test_source(source_id)

    print("\n" + "=" * 60)
    print("FIN TEST")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
