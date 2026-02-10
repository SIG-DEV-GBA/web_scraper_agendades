#!/usr/bin/env python
"""CLI runner for batch scraper jobs.

Usage:
    python run_batch.py --source madrid --limit 50 --dry-run
    python run_batch.py --source madrid --limit 100 --offset 50
    python run_batch.py --source madrid --limit 200 --no-llm --no-images
"""

import argparse
import asyncio
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.adapters import get_adapter
from src.core.scraper_job import ScraperJob, ScraperJobConfig


async def run_batch_job(
    source: str,
    limit: int,
    offset: int,
    dry_run: bool,
    llm_enabled: bool,
    images_enabled: bool,
) -> dict:
    """Run a batch scraper job."""

    # Set environment variables for feature toggles
    os.environ["LLM_ENABLED"] = str(llm_enabled).lower()
    os.environ["UNSPLASH_ENABLED"] = str(images_enabled).lower()

    # Create job config
    config = ScraperJobConfig(
        limit=limit,
        offset=offset,
        dry_run=dry_run,
        llm_enabled=llm_enabled,
        images_enabled=images_enabled,
    )

    # Create job tracker
    job = ScraperJob(source_name=source, config=config)
    job.start()

    print("=" * 70)
    print(f"BATCH JOB: {source}")
    print("=" * 70)
    print(f"Job ID: {job.id}")
    print(f"Limit: {limit}, Offset: {offset}")
    print(f"Dry Run: {dry_run}")
    print(f"LLM: {llm_enabled}, Images: {images_enabled}")
    print("-" * 70)

    try:
        # Get adapter by source name
        adapter_map = {
            "madrid": "madrid_datos_abiertos",
        }
        adapter_id = adapter_map.get(source, source)
        adapter_class = get_adapter(adapter_id)

        if not adapter_class:
            raise ValueError(f"Unknown source: {source}")

        # Instantiate the adapter
        adapter = adapter_class()

        # Run batch
        result = await adapter.run_batch(config)
        job.complete(result)

        print("\nRESULTS:")
        print("-" * 70)
        print(f"Total fetched:   {result.total_fetched}")
        print(f"Total processed: {result.total_processed}")
        print(f"Total inserted:  {result.total_inserted}")
        print(f"Total skipped:   {result.total_skipped}")
        print(f"Total errors:    {result.total_errors}")
        print(f"With images:     {result.with_images}")
        print(f"With Unsplash:   {result.with_unsplash}")
        print(f"\nCategories: {json.dumps(result.categories, indent=2)}")

        if result.error_details:
            print(f"\nErrors (first 5):")
            for err in result.error_details[:5]:
                print(f"  - {err['event_id']}: {err['error'][:80]}")

    except Exception as e:
        job.fail(str(e))
        print(f"\nJOB FAILED: {e}")
        raise

    finally:
        print("-" * 70)
        print(f"Duration: {job.duration_seconds:.2f}s")
        print(f"Status: {job.status.value}")
        print("=" * 70)

    return job.to_dict()


def main():
    parser = argparse.ArgumentParser(description="Run batch scraper job")
    parser.add_argument(
        "--source", "-s",
        required=True,
        choices=["madrid"],
        help="Source adapter to use",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=100,
        help="Max events to process (default: 100)",
    )
    parser.add_argument(
        "--offset", "-o",
        type=int,
        default=0,
        help="Skip first N events (default: 0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Don't insert to database (default: True)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Actually insert to database",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM enrichment",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Disable Unsplash image resolution",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    # Handle dry_run logic
    dry_run = not args.no_dry_run

    result = asyncio.run(run_batch_job(
        source=args.source,
        limit=args.limit,
        offset=args.offset,
        dry_run=dry_run,
        llm_enabled=not args.no_llm,
        images_enabled=not args.no_images,
    ))

    if args.json:
        print("\nJSON Output:")
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
