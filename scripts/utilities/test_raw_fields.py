#!/usr/bin/env python3
"""Show raw API fields available for each source."""
import asyncio
import sys
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter, GOLD_SOURCES


async def show_raw_fields(source_id: str):
    """Show all raw fields from first event."""
    print(f"\n{'='*70}")
    print(f"RAW FIELDS: {source_id}")
    print("=" * 70)

    try:
        adapter = GoldAPIAdapter(source_id)
        raw_events = await adapter.fetch_events(max_pages=1)

        if not raw_events:
            print("  No events")
            return

        first = raw_events[0]

        # For Andalucía, also show preprocessed
        if source_id == "andalucia_agenda":
            print("\n  (Showing preprocessed data)")
            first = adapter._preprocess_andalucia(first)

        if not isinstance(first, dict):
            print(f"  Type: {type(first)}")
            return

        print(f"\n  Total fields: {len(first)}")
        print("\n  Fields with values:")

        for key in sorted(first.keys()):
            val = first[key]
            if val is None or val == "" or val == []:
                continue

            # Truncate long values
            if isinstance(val, str):
                preview = val[:60] + "..." if len(val) > 60 else val
            elif isinstance(val, list):
                preview = f"[{len(val)} items]"
                if val and isinstance(val[0], dict):
                    preview += f" keys: {list(val[0].keys())[:5]}"
            elif isinstance(val, dict):
                preview = f"{{keys: {list(val.keys())[:5]}}}"
            else:
                preview = str(val)[:60]

            print(f"    {key}: {preview}")

    except Exception as e:
        print(f"  ERROR: {e}")


async def main():
    print("=" * 70)
    print("RAW API FIELDS - IDENTIFICAR CAMPOS NO EXTRAÍDOS")
    print("=" * 70)

    for source_id in GOLD_SOURCES.keys():
        await show_raw_fields(source_id)


if __name__ == "__main__":
    asyncio.run(main())
