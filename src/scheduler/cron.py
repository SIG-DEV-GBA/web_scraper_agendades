"""Scheduled tasks for automatic scraping.

This module provides:
1. Weekly scraping job every Monday at 00:01 (Madrid timezone)
2. API endpoints to control and monitor the scheduler
"""

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.adapters import list_adapters, get_adapter
from src.core.event_model import EventBatch
from src.core.llm_enricher import get_llm_enricher, SourceTier
from src.core.image_resolver import get_image_resolver
from src.core.supabase_client import get_supabase_client
from src.logging import get_logger

logger = get_logger(__name__)

# Timezone for Spain
MADRID_TZ = ZoneInfo("Europe/Madrid")

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None

# Last run info
_last_run: dict[str, Any] = {
    "started_at": None,
    "completed_at": None,
    "status": "never_run",
    "sources_processed": 0,
    "events_inserted": 0,
    "events_skipped": 0,
    "errors": [],
    "details": {},
}


def get_tier_enum(source_id: str) -> SourceTier:
    """Get SourceTier enum for a source."""
    if "viralagenda" in source_id:
        return SourceTier.BRONCE
    if "datos_abiertos" in source_id or "kulturklik" in source_id:
        return SourceTier.ORO
    elif "rss" in source_id or "galicia" in source_id:
        return SourceTier.PLATA
    else:
        return SourceTier.BRONCE


async def run_nightly_scrape() -> dict[str, Any]:
    """Execute the nightly scraping job for all sources.

    This runs at 00:00 Madrid time and processes all registered adapters.
    """
    global _last_run

    _last_run = {
        "started_at": datetime.now(MADRID_TZ).isoformat(),
        "completed_at": None,
        "status": "running",
        "sources_processed": 0,
        "events_inserted": 0,
        "events_skipped": 0,
        "errors": [],
        "details": {},
    }

    logger.info("nightly_scrape_started", time=_last_run["started_at"])

    # Get all registered adapters
    adapter_slugs = list_adapters()
    total_sources = len(adapter_slugs)

    logger.info("nightly_scrape_sources", count=total_sources)

    # Initialize clients
    supabase = get_supabase_client()
    enricher = get_llm_enricher()
    image_resolver = get_image_resolver()

    for source_id in adapter_slugs:
        try:
            logger.info("nightly_source_start", source=source_id)

            # Get adapter
            adapter_class = get_adapter(source_id)
            if not adapter_class:
                _last_run["errors"].append(f"{source_id}: adapter not found")
                continue

            adapter = adapter_class()
            tier = get_tier_enum(source_id)

            # Fetch events
            try:
                raw_events = await adapter.fetch_events(enrich=False)
            except TypeError:
                raw_events = await adapter.fetch_events()

            if not raw_events:
                _last_run["details"][source_id] = {"fetched": 0, "inserted": 0, "skipped": 0}
                _last_run["sources_processed"] += 1
                continue

            # Parse events
            events = []
            for raw in raw_events:
                try:
                    event = adapter.parse_event(raw)
                    if event:
                        events.append(event)
                except Exception:
                    pass

            # Filter past events
            from datetime import date
            today = date.today()
            events = [e for e in events if e.start_date and e.start_date >= today]

            if not events:
                _last_run["details"][source_id] = {"fetched": len(raw_events), "parsed": 0, "inserted": 0}
                _last_run["sources_processed"] += 1
                continue

            # LLM enrichment (with smaller batch for stability)
            if enricher and enricher.is_enabled:
                events_for_llm = [
                    {
                        "id": e.external_id or str(i),
                        "title": e.title,
                        "description": e.description or "",
                        "venue_name": e.venue_name,
                        "city": e.city,
                        "province": e.province,
                        "price_info": e.price_info,
                    }
                    for i, e in enumerate(events)
                ]

                try:
                    enrichments = enricher.enrich_batch(events_for_llm, batch_size=5, tier=tier)
                    image_keywords_map = {}

                    for event in events:
                        eid = event.external_id
                        if eid and eid in enrichments:
                            enr = enrichments[eid]
                            if enr.category_slugs:
                                event.category_slugs = enr.category_slugs
                            if enr.summary:
                                event.summary = enr.summary
                            if enr.is_free is not None and event.is_free is None:
                                event.is_free = enr.is_free
                            if enr.image_keywords:
                                category = enr.category_slugs[0] if enr.category_slugs else "default"
                                image_keywords_map[eid] = (enr.image_keywords, category)

                    # Resolve images
                    if image_resolver and image_resolver.is_enabled:
                        for event in events:
                            eid = event.external_id
                            if eid in image_keywords_map and not event.source_image_url:
                                keywords, category = image_keywords_map[eid]
                                image_data = image_resolver.resolve_image_full(keywords, category)
                                if image_data:
                                    event.source_image_url = image_data.url
                                    event.image_author = image_data.author
                                    event.image_author_url = image_data.author_url
                                    event.image_source_url = image_data.unsplash_url
                except Exception as e:
                    logger.warning("nightly_enrichment_error", source=source_id, error=str(e))

            # Save to database
            batch = EventBatch(
                source_id=source_id,
                source_name=adapter.source_name,
                ccaa=getattr(adapter, 'ccaa', None),
                scraped_at=datetime.now().isoformat(),
                events=events,
                total_found=len(raw_events),
            )
            stats = await supabase.save_batch(batch, skip_existing=True, cross_source_dedup=True)

            inserted = stats.get("inserted", 0)
            skipped = stats.get("skipped", 0) + stats.get("merged", 0)

            _last_run["events_inserted"] += inserted
            _last_run["events_skipped"] += skipped
            _last_run["sources_processed"] += 1
            _last_run["details"][source_id] = {
                "fetched": len(raw_events),
                "parsed": len(events),
                "inserted": inserted,
                "skipped": skipped,
            }

            logger.info("nightly_source_done", source=source_id, inserted=inserted, skipped=skipped)

            # Small delay between sources to avoid rate limiting
            await asyncio.sleep(1)

        except Exception as e:
            logger.error("nightly_source_error", source=source_id, error=str(e))
            _last_run["errors"].append(f"{source_id}: {str(e)}")
            _last_run["sources_processed"] += 1

    # Complete
    _last_run["completed_at"] = datetime.now(MADRID_TZ).isoformat()
    _last_run["status"] = "completed" if not _last_run["errors"] else "completed_with_errors"

    logger.info(
        "nightly_scrape_completed",
        sources=_last_run["sources_processed"],
        inserted=_last_run["events_inserted"],
        skipped=_last_run["events_skipped"],
        errors=len(_last_run["errors"]),
    )

    return _last_run


def init_scheduler() -> AsyncIOScheduler:
    """Initialize and start the scheduler."""
    global scheduler

    if scheduler is not None:
        return scheduler

    scheduler = AsyncIOScheduler(timezone=MADRID_TZ)

    # Add weekly job: every Monday at 00:01 Madrid time
    scheduler.add_job(
        run_nightly_scrape,
        CronTrigger(day_of_week="mon", hour=0, minute=1, timezone=MADRID_TZ),
        id="weekly_scrape",
        name="Weekly Global Scrape (Monday 00:01)",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("scheduler_started", next_run=get_next_run())

    return scheduler


def get_scheduler_status() -> dict[str, Any]:
    """Get current scheduler status."""
    if scheduler is None:
        return {
            "status": "not_initialized",
            "jobs": [],
            "next_run": None,
        }

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })

    return {
        "status": "running" if scheduler.running else "paused",
        "jobs": jobs,
        "next_run": get_next_run(),
        "last_run": _last_run,
    }


def get_next_run() -> str | None:
    """Get the next scheduled run time."""
    if scheduler is None:
        return None

    job = scheduler.get_job("weekly_scrape")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


def pause_scheduler():
    """Pause the scheduler."""
    if scheduler:
        scheduler.pause()
        logger.info("scheduler_paused")


def resume_scheduler():
    """Resume the scheduler."""
    if scheduler:
        scheduler.resume()
        logger.info("scheduler_resumed")


async def trigger_manual_scrape() -> dict[str, Any]:
    """Manually trigger the nightly scrape job."""
    logger.info("manual_scrape_triggered")
    return await run_nightly_scrape()
