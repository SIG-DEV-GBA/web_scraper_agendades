"""Insert 2 events from each Viralagenda source."""

import asyncio
import sys
from datetime import datetime

sys.path.insert(0, r"C:\Users\Usuario\Desktop\AGENDADES_WEB_SCRAPPER")

from src.config.sources import SourceRegistry
from src.core.pipeline import run_pipeline

# Load all sources
import src.config.sources.bronze_sources  # noqa


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
    """Insert 2 events from Viralagenda sources."""
    print("=" * 60)
    print(f"INSERCION VIRALAGENDA - 2 eventos por fuente")
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Get all viralagenda sources
    all_slugs = [s for s in SourceRegistry._sources.keys() if s.startswith("viralagenda_")]
    print(f"\nTotal fuentes Viralagenda: {len(all_slugs)}")

    results = []
    total_inserted = 0

    for i, slug in enumerate(all_slugs, 1):
        source = SourceRegistry._sources[slug]
        ccaa = getattr(source, 'ccaa', 'unknown')
        print(f"\n[{i}/{len(all_slugs)}] {slug} ({ccaa})")

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
    print("RESUMEN VIRALAGENDA")
    print("=" * 60)

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"Fuentes exitosas: {len(successful)}/{len(all_slugs)}")
    print(f"Fuentes fallidas: {len(failed)}/{len(all_slugs)}")
    print(f"Total eventos insertados: {total_inserted}")

    if failed:
        print("\nFuentes con errores:")
        for r in failed[:10]:
            print(f"  - {r['slug']}: {r['error'][:50] if r['error'] else 'unknown'}")

    print(f"\nFin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
