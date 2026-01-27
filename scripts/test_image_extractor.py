#!/usr/bin/env python3
"""Test script for image extraction from Madrid events."""

import asyncio
import sys
from pathlib import Path

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.adapters import get_adapter
from src.utils.image_extractor import extract_images_batch


async def test_image_extraction() -> None:
    """Test image extraction from Madrid events."""
    print("\n" + "=" * 60)
    print("🖼️  TEST: Image Extraction from Madrid Events")
    print("=" * 60)

    # First, get some events
    print("\n📥 Fetching events from Madrid API...")
    adapter_class = get_adapter("madrid_datos_abiertos")
    if not adapter_class:
        print("❌ Adapter not found!")
        return

    async with adapter_class() as adapter:
        batch = await adapter.scrape()

    print(f"   Found {len(batch.events)} events")

    # Prepare events for image extraction
    events_data = []
    for event in batch.events[:10]:  # Test with 10 events
        events_data.append({
            "external_id": event.external_id,
            "title": event.title,
            "source_url": event.source_url,
        })

    # Extract images
    print(f"\n🔍 Extracting images for {len(events_data)} events...")
    print("   (This may take a few seconds due to rate limiting)\n")

    images = await extract_images_batch(
        events_data,
        url_field="source_url",
        id_field="external_id",
        batch_size=10,
        delay=0.5,
    )

    # Results
    print("\n" + "-" * 60)
    print("📊 RESULTS")
    print("-" * 60)
    print(f"   Events processed: {len(events_data)}")
    print(f"   Images found: {len(images)}")
    print(f"   Success rate: {len(images) / len(events_data) * 100:.1f}%")

    print("\n🖼️  IMAGES FOUND:")
    for event in events_data:
        event_id = event["external_id"]
        title = event["title"][:40]
        if event_id in images:
            img_url = images[event_id]
            print(f"\n   ✅ {title}...")
            print(f"      {img_url}")
        else:
            print(f"\n   ❌ {title}... (no image)")

    print("\n" + "=" * 60)
    print("✅ TEST COMPLETED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_image_extraction())
