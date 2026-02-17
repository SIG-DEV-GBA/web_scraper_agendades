#!/usr/bin/env python3
"""Test script for Madrid Datos Abiertos adapter.

Usage:
    # Without LLM (fast test)
    python scripts/test_madrid_adapter.py

    # With LLM enrichment
    LLM_ENABLED=true python scripts/test_madrid_adapter.py

    # Dry run (no Supabase write)
    DRY_RUN=true python scripts/test_madrid_adapter.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.adapters import get_adapter, list_adapters
from src.config.settings import get_settings
from src.logging.logger import get_logger

logger = get_logger(__name__)


async def test_madrid_adapter() -> None:
    """Test the Madrid Datos Abiertos adapter."""
    settings = get_settings()

    print("\n" + "=" * 60)
    print("🏛️  TEST: Madrid Datos Abiertos Adapter")
    print("=" * 60)

    # Show settings
    print(f"\n📋 Configuration:")
    print(f"   - LLM Enabled: {settings.llm_enabled}")
    print(f"   - Groq Model: {settings.groq_model}")
    print(f"   - Dry Run: {settings.dry_run}")
    print(f"   - Environment: {settings.environment}")

    # List registered adapters
    print(f"\n📦 Registered adapters: {list_adapters()}")

    # Get Madrid adapter
    adapter_class = get_adapter("madrid_datos_abiertos")
    if not adapter_class:
        print("❌ Adapter 'madrid_datos_abiertos' not found!")
        return

    print(f"\n✅ Adapter found: {adapter_class.source_name}")

    # Run scrape
    print("\n🔄 Starting scrape...")
    async with adapter_class() as adapter:
        batch = await adapter.scrape()

    # Results
    print("\n" + "-" * 60)
    print("📊 RESULTS")
    print("-" * 60)
    print(f"   Source: {batch.source_name}")
    print(f"   CCAA: {batch.ccaa}")
    print(f"   Scraped at: {batch.scraped_at}")
    print(f"   Total found: {batch.total_found}")
    print(f"   Successfully parsed: {batch.success_count}")
    print(f"   Errors: {batch.error_count}")

    if batch.errors:
        print(f"\n⚠️  First 3 errors:")
        for err in batch.errors[:3]:
            print(f"      - {err[:100]}...")

    # Show sample events
    print("\n" + "-" * 60)
    print("🎭 SAMPLE EVENTS (first 5)")
    print("-" * 60)

    for i, event in enumerate(batch.events[:5], 1):
        print(f"\n  [{i}] {event.title[:60]}...")
        print(f"      📅 {event.start_date} - {event.end_date or 'N/A'}")
        print(f"      📍 {event.venue_name or 'N/A'}")
        print(f"      🏷️  Category: {event.category_name}")
        print(f"      💰 Free: {event.is_free}")
        print(f"      🔖 Tags: {', '.join(event.tags[:5])}")
        if event.description:
            print(f"      📝 {event.description[:100]}...")

    # Category distribution
    print("\n" + "-" * 60)
    print("📈 CATEGORY DISTRIBUTION")
    print("-" * 60)

    categories: dict[str, int] = {}
    for event in batch.events:
        cat = event.category_name or "sin categoría"
        categories[cat] = categories.get(cat, 0) + 1

    for cat, count in sorted(categories.items(), key=lambda x: -x[1])[:10]:
        bar = "█" * min(count // 5, 30)
        print(f"   {cat:20} {count:4} {bar}")

    # Export sample to JSON
    if settings.dry_run:
        output_file = Path("output/madrid_sample.json")
        output_file.parent.mkdir(exist_ok=True)

        sample_data = {
            "source": batch.source_id,
            "scraped_at": batch.scraped_at,
            "total": batch.total_found,
            "parsed": batch.success_count,
            "events": [e.model_dump(mode="json") for e in batch.events[:20]],
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, ensure_ascii=False, indent=2, default=str)

        print(f"\n💾 Sample exported to: {output_file}")

    print("\n" + "=" * 60)
    print("✅ TEST COMPLETED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(test_madrid_adapter())
