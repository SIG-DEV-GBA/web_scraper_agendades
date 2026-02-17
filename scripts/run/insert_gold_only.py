"""Insert 2 events from Gold API sources only (fastest)."""

import asyncio
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, "C:\\Users\\Usuario\\Desktop\\AGENDADES_WEB_SCRAPPER")

from src.core.pipeline import run_pipeline

# Gold API sources that are fast (no Firecrawl/Playwright)
GOLD_API_SOURCES = [
    "catalunya_agenda",
    "euskadi_kulturklik",
    "castilla_leon_agenda",
    "andalucia_agenda",
    "madrid_datos_abiertos",
    "valencia_ivc",
    "zaragoza_cultura",
]


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
    """Insert 2 events from Gold API sources."""
    print("=" * 60)
    print(f"INSERCION GOLD APIs - 2 eventos por fuente")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    print(f"\nTotal fuentes Gold API: {len(GOLD_API_SOURCES)}")

    results = []
    total_inserted = 0

    for i, slug in enumerate(GOLD_API_SOURCES, 1):
        print(f"\n[{i}/{len(GOLD_API_SOURCES)}] {slug}")
        result = await insert_from_source(slug)
        results.append(result)

        if result["success"]:
            total_inserted += result["inserted"]
            cats = ", ".join(f"{k}:{v}" for k, v in result["categories"].items()) if result["categories"] else "none"
            print(f"  OK Insertados: {result['inserted']} | Categorias: {cats}")
        else:
            error_msg = result['error'][:80] if result['error'] else 'unknown'
            print(f"  X Error: {error_msg}")

    # Summary
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"Fuentes exitosas: {len(successful)}/{len(GOLD_API_SOURCES)}")
    print(f"Fuentes fallidas: {len(failed)}/{len(GOLD_API_SOURCES)}")
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
        print("\nDistribucion por categoria:")
        for cat, count in sorted(all_categories.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")

    print(f"\nFin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
