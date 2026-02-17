"""Insert 2 events from Bronze sources that use direct HTTP (no Firecrawl)."""

import asyncio
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, "C:\\Users\\Usuario\\Desktop\\AGENDADES_WEB_SCRAPPER")

from src.core.pipeline import run_pipeline

# Bronze sources that use direct HTTP (fast)
BRONZE_FAST_SOURCES = [
    "clm_agenda",  # Castilla-La Mancha - HTTP directo
    "canarias_grancanaria",  # Gran Canaria - HTTP directo
    "navarra_cultura",  # Navarra oficial - HTTP directo
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
    """Insert 2 events from Bronze fast sources."""
    print("=" * 60)
    print(f"INSERCION BRONZE FAST (HTTP directo) - 2 eventos por fuente")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    print(f"\nTotal fuentes: {len(BRONZE_FAST_SOURCES)}")

    results = []
    total_inserted = 0

    for i, slug in enumerate(BRONZE_FAST_SOURCES, 1):
        print(f"\n[{i}/{len(BRONZE_FAST_SOURCES)}] {slug}")
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

    print(f"Fuentes exitosas: {len(successful)}/{len(BRONZE_FAST_SOURCES)}")
    print(f"Total eventos insertados: {total_inserted}")

    print(f"\nFin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
