#!/usr/bin/env python3
"""Check Madrid district field structure."""
import asyncio
import sys
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter, get_nested_value


async def main():
    print("=" * 60)
    print("MADRID - DISTRICT FIELD ANALYSIS")
    print("=" * 60)

    adapter = GoldAPIAdapter("madrid_datos_abiertos")
    raw_events = await adapter.fetch_events(max_pages=1)

    print(f"\nRaw events: {len(raw_events)}")

    # Check district structure in first 5 events
    for i, raw in enumerate(raw_events[:5]):
        print(f"\n--- Event {i+1} ---")
        print(f"Title: {raw.get('title', '?')[:50]}")

        # Check address structure
        address = raw.get("address", {})
        print(f"address keys: {list(address.keys()) if isinstance(address, dict) else type(address)}")

        if isinstance(address, dict):
            district = address.get("district", {})
            print(f"  district: {district}")

            area = address.get("area", {})
            if isinstance(area, dict):
                print(f"  area.locality: {area.get('locality')}")

        # Check event-location (has district in name sometimes)
        event_loc = raw.get("event-location", "")
        print(f"event-location: {event_loc}")


if __name__ == "__main__":
    asyncio.run(main())
