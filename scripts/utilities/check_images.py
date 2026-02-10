#!/usr/bin/env python3
"""Check image fields in CyL API."""
import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter


async def check():
    adapter = GoldAPIAdapter("castilla_leon_agenda")
    raw_events = await adapter.fetch_events(max_pages=1)

    print("IMÁGENES SELECCIONADAS (después del fix):")
    print("=" * 100)

    ampliada_count = 0
    normal_count = 0

    for raw in raw_events[:15]:
        event = adapter.parse_event(raw)
        if not event:
            continue

        has_ampliada = raw.get("imagen_evento_ampliada") is not None
        if has_ampliada:
            ampliada_count += 1
            tag = "AMPLIADA"
        else:
            normal_count += 1
            tag = "normal"

        print(f"\n[{tag:8}] {event.title[:50]}")
        print(f"           URL: {event.source_image_url[:70] if event.source_image_url else 'N/A'}...")

    print(f"\n\nRESUMEN: {ampliada_count} con imagen ampliada, {normal_count} con imagen normal")


if __name__ == "__main__":
    asyncio.run(check())
