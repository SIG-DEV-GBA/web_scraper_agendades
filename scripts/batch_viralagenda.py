"""Batch script to run all valid Viralagenda sources.

Only includes CCAA that actually exist in Viralagenda:
- Andalucía (8 provinces)
- Castilla y León (9 provinces)
- Extremadura (2 provinces)
- Galicia (4 provinces)

Total: 23 sources

Usage:
    python scripts/batch_viralagenda.py [--limit 40] [--dry-run] [--skip-existing]
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import run_pipeline
from src.core.supabase_client import get_supabase_client
from src.logging import get_logger

logger = get_logger(__name__)

# Valid Viralagenda sources (only CCAA that exist)
VALID_SOURCES = [
    # Andalucía (8)
    "viralagenda_almeria",
    "viralagenda_cadiz",
    "viralagenda_cordoba",
    "viralagenda_granada",
    "viralagenda_huelva",
    "viralagenda_jaen",
    "viralagenda_malaga",
    "viralagenda_sevilla",
    # Castilla y León (9)
    "viralagenda_avila",
    "viralagenda_burgos",
    "viralagenda_leon",
    "viralagenda_palencia",
    "viralagenda_salamanca",
    "viralagenda_segovia",
    "viralagenda_soria",
    "viralagenda_valladolid",
    "viralagenda_zamora",
    # Extremadura (2)
    "viralagenda_caceres",
    "viralagenda_badajoz",
    # Galicia (4)
    "viralagenda_a_coruna",
    "viralagenda_lugo",
    "viralagenda_ourense",
    "viralagenda_pontevedra",
]


async def get_source_counts() -> dict[str, int]:
    """Get event counts per Viralagenda source from DB."""
    sb = get_supabase_client()

    result = sb.client.table('events').select('external_id').like('external_id', 'viralagenda_%').execute()

    counts = {}
    for row in result.data:
        ext_id = row['external_id']
        parts = ext_id.split('_')
        if len(parts) >= 2:
            source = f'{parts[0]}_{parts[1]}'
            counts[source] = counts.get(source, 0) + 1

    return counts


async def run_batch(
    limit: int = 40,
    dry_run: bool = False,
    skip_existing: bool = True,
    min_events: int = 40,
):
    """Run pipeline for all pending Viralagenda sources.

    Args:
        limit: Max events per source
        dry_run: If True, don't insert to DB
        skip_existing: Skip sources that already have >= min_events
        min_events: Threshold for considering a source "done"
    """
    print(f"\n{'='*60}")
    print("VIRALAGENDA BATCH SCRAPER")
    print(f"{'='*60}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Limit per source: {limit}")
    print(f"Dry run: {dry_run}")
    print(f"Skip existing (>={min_events} events): {skip_existing}")
    print(f"{'='*60}\n")

    # Get current counts
    counts = await get_source_counts()

    # Filter sources to run
    sources_to_run = []
    for source in VALID_SOURCES:
        current = counts.get(source, 0)
        if skip_existing and current >= min_events:
            print(f"  SKIP {source}: already has {current} events")
        else:
            sources_to_run.append((source, current))

    print(f"\nSources to process: {len(sources_to_run)}/{len(VALID_SOURCES)}")
    print(f"{'='*60}\n")

    if not sources_to_run:
        print("All sources already have enough events!")
        return

    # Stats
    total_inserted = 0
    total_failed = 0
    results = []

    for i, (source, current) in enumerate(sources_to_run, 1):
        print(f"\n[{i}/{len(sources_to_run)}] Processing: {source}")
        print(f"  Current events in DB: {current}")
        print("-" * 40)

        try:
            result = await run_pipeline(
                source_slug=source,
                limit=limit,
                dry_run=dry_run,
                fetch_details=True,
            )

            status = "OK" if result.success else "FAIL"
            inserted = result.inserted_count if not dry_run else 0

            print(f"  Status: {status}")
            print(f"  Raw: {result.raw_count}, Parsed: {result.parsed_count}")
            if not dry_run:
                print(f"  Inserted: {result.inserted_count}, Skipped: {result.skipped_existing}")
            if result.error:
                print(f"  Error: {result.error}")

            results.append({
                "source": source,
                "success": result.success,
                "inserted": inserted,
                "parsed": result.parsed_count,
                "error": result.error,
            })

            total_inserted += inserted
            if not result.success:
                total_failed += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "source": source,
                "success": False,
                "inserted": 0,
                "parsed": 0,
                "error": str(e),
            })
            total_failed += 1

        # Delay between sources (30-60 seconds)
        if i < len(sources_to_run):
            import random
            delay = random.uniform(30, 60)
            print(f"\n  Waiting {delay:.0f}s before next source...")
            await asyncio.sleep(delay)

    # Summary
    print(f"\n{'='*60}")
    print("BATCH COMPLETE")
    print(f"{'='*60}")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Sources processed: {len(sources_to_run)}")
    print(f"Failed: {total_failed}")
    if not dry_run:
        print(f"Total events inserted: {total_inserted}")
    print(f"{'='*60}\n")

    # Failed sources
    failed = [r for r in results if not r["success"]]
    if failed:
        print("Failed sources:")
        for r in failed:
            print(f"  - {r['source']}: {r['error']}")


def main():
    parser = argparse.ArgumentParser(description="Batch scrape Viralagenda sources")
    parser.add_argument("--limit", type=int, default=40, help="Max events per source")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert to DB")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip sources with enough events")
    parser.add_argument("--min-events", type=int, default=40, help="Min events to consider source done")

    args = parser.parse_args()

    asyncio.run(run_batch(
        limit=args.limit,
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
        min_events=args.min_events,
    ))


if __name__ == "__main__":
    main()
