"""Test script for Valencia IVC adapter."""

import asyncio
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

from src.logging import setup_logging, get_logger
from src.adapters.gold_api_adapter import GoldAPIAdapter, GOLD_SOURCES

logger = get_logger(__name__)


async def test_valencia():
    """Test Valencia IVC adapter."""
    setup_logging(level="INFO")

    print("\n" + "="*60)
    print("Testing Valencia IVC Adapter")
    print("="*60)

    # Check config exists
    if "valencia_ivc" not in GOLD_SOURCES:
        print("[ERROR] valencia_ivc not in GOLD_SOURCES!")
        return

    config = GOLD_SOURCES["valencia_ivc"]
    print(f"\nSource: {config.name}")
    print(f"URL: {config.url[:80]}...")
    print(f"CCAA: {config.ccaa}")
    print(f"Date format: {config.date_format}")

    # Create adapter and fetch events
    adapter = GoldAPIAdapter("valencia_ivc")

    async with adapter:
        print("\nFetching events...")
        raw_events = await adapter.fetch_events(max_pages=1)
        print(f"Raw events fetched: {len(raw_events)}")

        if not raw_events:
            print("[ERROR] No events fetched!")
            return

        # Show sample raw event
        print("\n--- Sample Raw Event ---")
        sample = raw_events[0]
        for key, value in sample.items():
            print(f"  {key}: {value}")

        # Parse events
        print("\n--- Parsing Events ---")
        parsed = []
        today = date.today()

        for raw in raw_events[:20]:  # Test first 20
            event = adapter.parse_event(raw)
            if event:
                parsed.append(event)

        print(f"Parsed: {len(parsed)} events")

        # Filter future events
        future = [e for e in parsed if e.start_date >= today]
        print(f"Future events: {len(future)}")

        # Show parsed samples
        print("\n--- Parsed Event Samples ---")
        for event in parsed[:5]:
            print(f"\n[EVENT] {event.title[:60]}...")
            print(f"  Date: {event.start_date}")
            print(f"  City: {event.city}, {event.province}")
            print(f"  Venue: {event.venue_name}")
            print(f"  Price: {event.price_info}")
            print(f"  Category: {event.category_name}")
            print(f"  Coords: {event.latitude}, {event.longitude}")
            print(f"  Future: {'Yes' if event.start_date >= today else 'No (past)'}")

    print("\n" + "="*60)
    print("Test completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_valencia())
