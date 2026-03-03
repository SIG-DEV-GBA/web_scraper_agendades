"""Scheduler control routes - manage automatic scraping jobs."""

from fastapi import APIRouter, BackgroundTasks, Depends

from src.api.auth import require_api_key
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
async def pause(_: str = Depends(require_api_key)):
    """Pause the scheduler (jobs won't run until resumed)."""
    pause_scheduler()
    return {"status": "paused", "message": "Scheduler paused. Jobs will not run until resumed."}


@router.post("/resume")
async def resume(_: str = Depends(require_api_key)):
    """Resume the scheduler."""
    resume_scheduler()
    return {"status": "resumed", "message": "Scheduler resumed. Jobs will run as scheduled."}


@router.post("/trigger")
async def trigger(background_tasks: BackgroundTasks, _: str = Depends(require_api_key)):
    """Manually trigger a full scrape job (runs in background)."""
    logger.info("manual_trigger_requested")
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
