"""Job for fetching images for events without them.

This job runs separately from the main scraper to:
1. Query Supabase for events without images
2. Extract images from source URLs
3. Update events with image URLs

Usage:
    python -m src.jobs.image_fetcher --batch-size 50 --priority week
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from src.config.settings import get_settings
from src.core.supabase_client import get_supabase_client
from src.logging.logger import get_logger
from src.utils.image_extractor import extract_image_from_page

import httpx

logger = get_logger(__name__)


class Priority(str, Enum):
    """Priority for image fetching."""

    WEEK = "week"      # Events in next 7 days
    MONTH = "month"    # Events in next 30 days
    ALL = "all"        # All events without images


class ImageFetcherJob:
    """Job for fetching and updating event images."""

    def __init__(
        self,
        batch_size: int = 50,
        delay: float = 0.5,
        priority: Priority = Priority.WEEK,
        dry_run: bool = False,
    ) -> None:
        """Initialize the image fetcher job.

        Args:
            batch_size: Maximum events to process per run
            delay: Seconds between requests (rate limiting)
            priority: Which events to prioritize
            dry_run: If True, don't update Supabase
        """
        self.batch_size = batch_size
        self.delay = delay
        self.priority = priority
        self.dry_run = dry_run
        self.settings = get_settings()
        self.supabase = get_supabase_client()
        self.stats = {
            "processed": 0,
            "found": 0,
            "updated": 0,
            "failed": 0,
            "skipped": 0,
        }

    def _get_date_filter(self) -> str | None:
        """Get date filter based on priority."""
        today = datetime.now().date()

        if self.priority == Priority.WEEK:
            end_date = today + timedelta(days=7)
            return end_date.isoformat()
        elif self.priority == Priority.MONTH:
            end_date = today + timedelta(days=30)
            return end_date.isoformat()
        else:
            return None  # No date filter

    async def get_events_without_images(self) -> list[dict[str, Any]]:
        """Query Supabase for events that need images."""
        try:
            query = (
                self.supabase.client.table("events")
                .select("id, external_id, title, external_url, start_date")
                .is_("image_url", "null")
                .not_.is_("external_url", "null")
                .order("start_date")
                .limit(self.batch_size)
            )

            # Apply date filter based on priority
            date_filter = self._get_date_filter()
            if date_filter:
                today = datetime.now().date().isoformat()
                query = query.gte("start_date", today).lte("start_date", date_filter)

            response = query.execute()
            return response.data

        except Exception as e:
            logger.error("query_error", error=str(e))
            return []

    async def update_event_image(self, event_id: str, image_url: str) -> bool:
        """Update event with image URL in Supabase."""
        if self.dry_run:
            logger.debug("dry_run_update", event_id=event_id, image_url=image_url[:60])
            return True

        try:
            response = (
                self.supabase.client.table("events")
                .update({"image_url": image_url, "updated_at": datetime.now().isoformat()})
                .eq("id", event_id)
                .execute()
            )
            return len(response.data) > 0

        except Exception as e:
            logger.error("update_error", event_id=event_id, error=str(e))
            return False

    async def run(self) -> dict[str, int]:
        """Run the image fetcher job.

        Returns:
            Stats dict with processed, found, updated, failed counts
        """
        logger.info(
            "job_start",
            batch_size=self.batch_size,
            priority=self.priority.value,
            dry_run=self.dry_run,
        )

        # Get events without images
        events = await self.get_events_without_images()

        if not events:
            logger.info("no_events_found", reason="All events have images or no source_url")
            return self.stats

        logger.info("events_to_process", count=len(events))

        # Create HTTP client
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={
                "User-Agent": "AgendadesScraper/0.1 (+https://agendades.es)",
                "Accept": "text/html,application/xhtml+xml",
            },
        ) as client:
            for i, event in enumerate(events):
                event_id = event["id"]
                title = event.get("title", "")[:40]
                source_url = event.get("external_url", "")

                if not source_url:
                    self.stats["skipped"] += 1
                    continue

                self.stats["processed"] += 1

                # Extract image
                try:
                    image_url = await extract_image_from_page(client, source_url)

                    if image_url:
                        self.stats["found"] += 1

                        # Update in Supabase
                        if await self.update_event_image(event_id, image_url):
                            self.stats["updated"] += 1
                            logger.info("image_updated", title=title, image=image_url[:60])
                        else:
                            self.stats["failed"] += 1
                    else:
                        logger.debug("no_image_found", title=title)

                except Exception as e:
                    self.stats["failed"] += 1
                    logger.warning("extract_error", title=title, error=str(e))

                # Rate limiting
                if i < len(events) - 1:
                    await asyncio.sleep(self.delay)

        logger.info("job_complete", **self.stats)
        return self.stats


async def run_image_fetcher(
    batch_size: int = 50,
    delay: float = 0.5,
    priority: str = "week",
    dry_run: bool = False,
) -> dict[str, int]:
    """Run the image fetcher job.

    Args:
        batch_size: Maximum events to process
        delay: Seconds between requests
        priority: "week", "month", or "all"
        dry_run: If True, don't update database

    Returns:
        Stats dict
    """
    priority_enum = Priority(priority)
    job = ImageFetcherJob(
        batch_size=batch_size,
        delay=delay,
        priority=priority_enum,
        dry_run=dry_run,
    )
    return await job.run()


# CLI entry point
if __name__ == "__main__":
    import argparse
    import sys

    # Fix Windows encoding
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore

    parser = argparse.ArgumentParser(description="Fetch images for events")
    parser.add_argument("--batch-size", type=int, default=50, help="Max events to process")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests")
    parser.add_argument("--priority", choices=["week", "month", "all"], default="week")
    parser.add_argument("--dry-run", action="store_true", help="Don't update database")

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("🖼️  IMAGE FETCHER JOB")
    print("=" * 60)
    print(f"\n📋 Configuration:")
    print(f"   - Batch size: {args.batch_size}")
    print(f"   - Delay: {args.delay}s")
    print(f"   - Priority: {args.priority}")
    print(f"   - Dry run: {args.dry_run}")
    print()

    stats = asyncio.run(run_image_fetcher(
        batch_size=args.batch_size,
        delay=args.delay,
        priority=args.priority,
        dry_run=args.dry_run,
    ))

    print("\n" + "-" * 60)
    print("📊 RESULTS")
    print("-" * 60)
    print(f"   Processed: {stats['processed']}")
    print(f"   Found: {stats['found']}")
    print(f"   Updated: {stats['updated']}")
    print(f"   Failed: {stats['failed']}")
    print(f"   Skipped: {stats['skipped']}")

    success_rate = (stats['found'] / stats['processed'] * 100) if stats['processed'] > 0 else 0
    print(f"\n   Success rate: {success_rate:.1f}%")
    print("\n" + "=" * 60 + "\n")
