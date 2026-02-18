"""Job persistence layer using Supabase.

Stores scraper jobs in the database so they survive container restarts.
"""

from datetime import datetime
from typing import Any
from enum import Enum

from src.core.supabase_client import get_supabase_client
from src.logging import get_logger

logger = get_logger(__name__)


class JobStatus(str, Enum):
    """Job status enum."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LogLevel(str, Enum):
    """Log level for job logs."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


# In-memory cache for active jobs (faster reads during execution)
_job_cache: dict[str, dict[str, Any]] = {}


def _get_sb():
    """Get Supabase client."""
    return get_supabase_client().client


def create_job(
    job_id: str,
    sources: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Create a new job in the database.

    Args:
        job_id: Unique job identifier
        sources: List of source slugs to scrape
        config: Job configuration (limit, dry_run, filter, etc.)

    Returns:
        The created job dict
    """
    job = {
        "id": job_id,
        "status": JobStatus.PENDING.value,
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "sources_total": len(sources),
        "sources_completed": 0,
        "events_fetched": 0,
        "events_parsed": 0,
        "events_inserted": 0,
        "events_skipped": 0,
        "events_failed": 0,
        "errors": [],
        "logs": [],
        "results": {},
        "config": config,
    }

    try:
        sb = _get_sb()
        sb.table("scraper_jobs").insert({
            "id": job_id,
            "status": job["status"],
            "sources_total": job["sources_total"],
            "config": config,
            "progress": {
                "sources_completed": 0,
                "events_fetched": 0,
                "events_parsed": 0,
                "events_inserted": 0,
                "events_skipped": 0,
                "events_failed": 0,
            },
            "errors": [],
            "logs": [],
            "results": {},
        }).execute()

        # Cache for fast access during execution
        _job_cache[job_id] = job
        logger.info("job_created", job_id=job_id, sources=len(sources))

    except Exception as e:
        logger.error("job_create_failed", job_id=job_id, error=str(e))
        # Still cache locally if DB fails
        _job_cache[job_id] = job

    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    """Get a job by ID.

    Checks cache first, then database.

    Args:
        job_id: Job identifier

    Returns:
        Job dict or None if not found
    """
    # Check cache first
    if job_id in _job_cache:
        return _job_cache[job_id]

    # Try database
    try:
        sb = _get_sb()
        result = sb.table("scraper_jobs").select("*").eq("id", job_id).single().execute()

        if result.data:
            # Reconstruct job dict from DB
            job = _db_to_job(result.data)
            _job_cache[job_id] = job
            return job

    except Exception as e:
        logger.warning("job_get_failed", job_id=job_id, error=str(e))

    return None


def update_job(job_id: str, updates: dict[str, Any]) -> None:
    """Update a job in cache and database.

    Args:
        job_id: Job identifier
        updates: Fields to update
    """
    # Update cache
    if job_id in _job_cache:
        _job_cache[job_id].update(updates)
        job = _job_cache[job_id]
    else:
        job = updates

    # Persist to database
    try:
        sb = _get_sb()

        db_updates = {
            "updated_at": datetime.now().isoformat(),
        }

        # Map job fields to DB fields
        if "status" in updates:
            db_updates["status"] = updates["status"].value if hasattr(updates["status"], "value") else updates["status"]
        if "started_at" in updates:
            db_updates["started_at"] = updates["started_at"]
        if "completed_at" in updates:
            db_updates["completed_at"] = updates["completed_at"]
        if "duration_seconds" in updates:
            db_updates["duration_seconds"] = updates["duration_seconds"]
        if "errors" in updates:
            db_updates["errors"] = updates["errors"]
        if "results" in updates:
            db_updates["results"] = updates["results"]

        # Progress fields
        progress_fields = ["sources_completed", "events_fetched", "events_parsed",
                         "events_inserted", "events_skipped", "events_failed"]
        if any(f in updates for f in progress_fields):
            db_updates["progress"] = {
                "sources_completed": job.get("sources_completed", 0),
                "events_fetched": job.get("events_fetched", 0),
                "events_parsed": job.get("events_parsed", 0),
                "events_inserted": job.get("events_inserted", 0),
                "events_skipped": job.get("events_skipped", 0),
                "events_failed": job.get("events_failed", 0),
            }

        sb.table("scraper_jobs").update(db_updates).eq("id", job_id).execute()

    except Exception as e:
        logger.warning("job_update_failed", job_id=job_id, error=str(e))


def add_job_log(
    job_id: str,
    level: LogLevel,
    message: str,
    source: str | None = None,
    details: dict | None = None,
) -> None:
    """Add a log entry to a job.

    Args:
        job_id: Job identifier
        level: Log level
        message: Log message
        source: Source slug (optional)
        details: Additional details (optional)
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level.value if hasattr(level, "value") else level,
        "message": message,
        "source": source,
        "details": details,
    }

    # Add to cache
    if job_id in _job_cache:
        _job_cache[job_id].setdefault("logs", []).append(log_entry)
        logs = _job_cache[job_id]["logs"]
    else:
        logs = [log_entry]

    # Persist to database (batch updates to reduce DB calls)
    # Only persist every 5 logs or on important events
    should_persist = (
        len(logs) % 5 == 0 or
        level in (LogLevel.ERROR, LogLevel.SUCCESS) or
        "completado" in message.lower() or
        "iniciado" in message.lower()
    )

    if should_persist:
        try:
            sb = _get_sb()
            sb.table("scraper_jobs").update({
                "logs": logs,
                "updated_at": datetime.now().isoformat(),
            }).eq("id", job_id).execute()
        except Exception as e:
            logger.warning("job_log_persist_failed", job_id=job_id, error=str(e))


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    """List recent jobs from database.

    Args:
        limit: Maximum number of jobs to return

    Returns:
        List of job summaries (most recent first)
    """
    try:
        sb = _get_sb()
        result = sb.table("scraper_jobs").select(
            "id, status, config, progress, started_at, completed_at, duration_seconds, errors"
        ).order("created_at", desc=True).limit(limit).execute()

        jobs = []
        for row in result.data:
            progress = row.get("progress", {})
            config = row.get("config", {})
            jobs.append({
                "job_id": row["id"],
                "status": row["status"],
                "filter": config.get("filter", "unknown"),
                "sources_total": len(config.get("sources", [])),
                "sources_completed": progress.get("sources_completed", 0),
                "events_inserted": progress.get("events_inserted", 0),
                "events_skipped": progress.get("events_skipped", 0),
                "started_at": row.get("started_at"),
                "completed_at": row.get("completed_at"),
                "duration_seconds": row.get("duration_seconds"),
                "has_errors": len(row.get("errors", [])) > 0,
            })

        return jobs

    except Exception as e:
        logger.error("list_jobs_failed", error=str(e))
        # Fallback to cache
        return [
            {
                "job_id": jid,
                "status": job.get("status"),
                "filter": job.get("config", {}).get("filter", "unknown"),
                "sources_total": job.get("sources_total", 0),
                "sources_completed": job.get("sources_completed", 0),
                "events_inserted": job.get("events_inserted", 0),
                "events_skipped": job.get("events_skipped", 0),
                "started_at": job.get("started_at"),
                "completed_at": job.get("completed_at"),
                "duration_seconds": job.get("duration_seconds"),
                "has_errors": len(job.get("errors", [])) > 0,
            }
            for jid, job in list(_job_cache.items())[-limit:]
        ]


def delete_job(job_id: str) -> bool:
    """Delete a job from cache and database.

    Args:
        job_id: Job identifier

    Returns:
        True if deleted, False if not found
    """
    # Remove from cache
    if job_id in _job_cache:
        del _job_cache[job_id]

    # Delete from database
    try:
        sb = _get_sb()
        sb.table("scraper_jobs").delete().eq("id", job_id).execute()
        return True
    except Exception as e:
        logger.warning("job_delete_failed", job_id=job_id, error=str(e))
        return False


def _db_to_job(row: dict) -> dict[str, Any]:
    """Convert database row to job dict.

    Args:
        row: Database row

    Returns:
        Job dict
    """
    progress = row.get("progress", {})
    config = row.get("config", {})

    return {
        "status": JobStatus(row["status"]),
        "started_at": row.get("started_at"),
        "completed_at": row.get("completed_at"),
        "duration_seconds": row.get("duration_seconds"),
        "sources_total": len(config.get("sources", [])),
        "sources_completed": progress.get("sources_completed", 0),
        "events_fetched": progress.get("events_fetched", 0),
        "events_parsed": progress.get("events_parsed", 0),
        "events_inserted": progress.get("events_inserted", 0),
        "events_skipped": progress.get("events_skipped", 0),
        "events_failed": progress.get("events_failed", 0),
        "errors": row.get("errors", []),
        "logs": row.get("logs", []),
        "results": row.get("results", {}),
        "config": config,
    }
