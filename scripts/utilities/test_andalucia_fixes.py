#!/usr/bin/env python3
"""Test Andalucía fixes: gratuito detection and deduplication."""
import asyncio
import sys
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter


async def main():
    print("=" * 60)
    print("TEST ANDALUCÍA - Verificar gratuito y duplicados")
    print("=" * 60)

    adapter = GoldAPIAdapter("andalucia_agenda")

    # Fetch events
    print("\nFetching events...")
    raw_events = await adapter.fetch_events(max_pages=3)
    print(f"Raw events: {len(raw_events)}")

    # Parse events and track duplicates
    parsed = []
    external_ids = []

    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event:
            parsed.append(event)
            external_ids.append(event.external_id)

    print(f"Parsed: {len(parsed)}")

    # Check for duplicate external_ids
    id_counts = Counter(external_ids)
    duplicates = {k: v for k, v in id_counts.items() if v > 1}
    if duplicates:
        print(f"\n⚠️ DUPLICADOS detectados por external_id:")
        for ext_id, count in list(duplicates.items())[:5]:
            print(f"  {ext_id}: {count}x")
    else:
        print("\n✓ No hay duplicados por external_id")

    # Check gratuito detection
    print("\n" + "-" * 60)
    print("ANÁLISIS DE GRATUITO:")

    free_count = sum(1 for e in parsed if e.is_free is True)
    paid_count = sum(1 for e in parsed if e.is_free is False)
    unknown_count = sum(1 for e in parsed if e.is_free is None)

    print(f"  Gratuitos: {free_count}")
    print(f"  De pago: {paid_count}")
    print(f"  Desconocido: {unknown_count}")

    # Show samples of each
    print("\n" + "-" * 60)
    print("EJEMPLOS GRATUITOS (detectados):")
    for e in parsed[:20]:
        if e.is_free is True:
            print(f"  ✓ {e.title[:50]}... ({e.city})")
            break

    print("\nEJEMPLOS PAGO (detectados):")
    for e in parsed[:20]:
        if e.is_free is False:
            print(f"  $ {e.title[:50]}... - {e.price_info}")
            break

    # Look specifically for "Humedales" events
    print("\n" + "-" * 60)
    print("EVENTOS 'HUMEDALES' (verificar gratuito):")
    for e in parsed:
        if "humedales" in e.title.lower():
            status = "GRATIS" if e.is_free else "PAGO" if e.is_free is False else "?"
            print(f"  [{status}] {e.title[:45]}... | {e.city} | {e.start_date}")

    # Check if public institution detection is working
    print("\n" + "-" * 60)
    print("VERIFICACIÓN ORGANISMO PÚBLICO:")

    # Show raw data for a Humedales event to check organizer
    for raw in raw_events[:50]:
        preprocessed = adapter._preprocess_andalucia(raw)
        if preprocessed and "humedales" in preprocessed.get("title", "").lower():
            print(f"\n  Título: {preprocessed.get('title', '')[:50]}...")
            print(f"  Organizadores: {preprocessed.get('organizer_names', [])}")
            print(f"  external_id: {preprocessed.get('external_id', '')}")
            break


if __name__ == "__main__":
    asyncio.run(main())
