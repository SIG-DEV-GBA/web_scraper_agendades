"""Insert 2 events from each registered source."""

import asyncio
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, "C:\\Users\\Usuario\\Desktop\\AGENDADES_WEB_SCRAPPER")

from src.config.sources import SourceRegistry
from src.config.sources.gold_sources import GOLD_SOURCES
import src.config.sources.bronze_sources
from src.core.pipeline import run_pipeline


async def insert_from_source(slug: str) -> dict:
    """Insert 2 events from a single source."""
    try:
        result = await run_pipeline(
            source_slug=slug,
            limit=2,
            dry_run=False,
        )
        return {
            "slug": slug,
            "success": result.success,
            "inserted": result.inserted_count,
            "categories": result.categories,
            "error": result.error,
        }
    except Exception as e:
        return {
            "slug": slug,
            "success": False,
            "inserted": 0,
            "categories": {},
            "error": str(e),
        }


async def main():
    """Insert 2 events from each source."""
    print("=" * 60)
    print(f"INSERCIÓN MASIVA - 2 eventos por fuente")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Fuentes lentas que usan Playwright - procesar al final
    SLOW_SOURCES = {"visitnavarra", "larioja_agenda", "pamplona"}

    # Get all source slugs - ordenar: rápidas primero, lentas al final
    all_slugs_set = set(SourceRegistry._sources.keys())
    fast_slugs = [s for s in all_slugs_set if s not in SLOW_SOURCES]
    slow_slugs = [s for s in all_slugs_set if s in SLOW_SOURCES]
    all_slugs = fast_slugs + slow_slugs
    print(f"\nTotal fuentes: {len(all_slugs)}")

    results = []
    total_inserted = 0

    for i, slug in enumerate(all_slugs, 1):
        source = SourceRegistry._sources[slug]
        tier = getattr(source, 'tier', 'unknown')
        tier_val = tier.value if hasattr(tier, 'value') else str(tier)
        ccaa = getattr(source, 'ccaa', 'unknown')

        print(f"\n[{i}/{len(all_slugs)}] {slug} ({tier_val} - {ccaa})")

        result = await insert_from_source(slug)
        results.append(result)

        if result["success"]:
            total_inserted += result["inserted"]
            cats = ", ".join(f"{k}:{v}" for k, v in result["categories"].items()) if result["categories"] else "none"
            print(f"  ✓ Insertados: {result['inserted']} | Categorías: {cats}")
        else:
            print(f"  ✗ Error: {result['error'][:80] if result['error'] else 'unknown'}")

    # Summary
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"Fuentes exitosas: {len(successful)}/{len(all_slugs)}")
    print(f"Fuentes fallidas: {len(failed)}/{len(all_slugs)}")
    print(f"Total eventos insertados: {total_inserted}")

    if failed:
        print("\nFuentes con errores:")
        for r in failed:
            print(f"  - {r['slug']}: {r['error'][:60] if r['error'] else 'unknown'}")

    # Category distribution
    all_categories = {}
    for r in results:
        for cat, count in r.get("categories", {}).items():
            all_categories[cat] = all_categories.get(cat, 0) + count

    if all_categories:
        print("\nDistribución por categoría:")
        for cat, count in sorted(all_categories.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")

    print(f"\nFin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
