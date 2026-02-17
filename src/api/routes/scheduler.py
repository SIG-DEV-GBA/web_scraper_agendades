"""Scheduler control routes - manage automatic scraping jobs."""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from src.scheduler import (
    get_scheduler_status,
    pause_scheduler,
    resume_scheduler,
    trigger_manual_scrape,
)
from src.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("")
async def scheduler_status():
    """Get current scheduler status including last run info."""
    return get_scheduler_status()


@router.post("/pause")
async def pause():
    """Pause the scheduler (jobs won't run until resumed)."""
    pause_scheduler()
    return {"status": "paused", "message": "Scheduler paused. Jobs will not run until resumed."}


@router.post("/resume")
async def resume():
    """Resume the scheduler."""
    resume_scheduler()
    return {"status": "resumed", "message": "Scheduler resumed. Jobs will run as scheduled."}


@router.post("/trigger")
async def trigger(background_tasks: BackgroundTasks):
    """Manually trigger a full scrape job (runs in background).

    This is the same as the nightly job but can be triggered on demand.
    """
    logger.info("manual_trigger_requested")

    # Run in background to avoid timeout
    background_tasks.add_task(trigger_manual_scrape)

    return {
        "status": "triggered",
        "message": "Full scrape job started in background. Check /scheduler for status.",
    }


@router.get("/last-run")
async def last_run():
    """Get details of the last scheduled run."""
    status = get_scheduler_status()
    return status.get("last_run", {"status": "never_run"})
