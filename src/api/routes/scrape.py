"""Scrape routes - execute scraping jobs using the unified pipeline."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from src.config.sources import SourceRegistry, SourceTier
from src.core.pipeline import run_pipeline, PipelineResult
from src.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Load all sources
import src.config.sources.gold_sources  # noqa
import src.config.sources.bronze_sources  # noqa

# In-memory job storage (for production, use Redis or DB)
_jobs: dict[str, dict[str, Any]] = {}


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


class ScrapeRequest(BaseModel):
    """Request to start a scrape job."""
    sources: list[str] | None = Field(None, description="List of source slugs to scrape")
    tier: str | None = Field(None, description="Tier to scrape (gold, silver, bronze)")
    province: str | None = Field(None, description="Province to scrape (e.g., 'zamora', 'madrid')")
    ccaa: str | None = Field(None, description="CCAA to scrape (e.g., 'castilla y leon', 'andalucia')")
    limit: int | None = Field(None, ge=1, description="Max events per source (None = unlimited)")
    dry_run: bool = Field(False, description="Don't save to database")


class ScrapeResponse(BaseModel):
    """Response from starting a scrape job."""
    job_id: str
    status: JobStatus
    message: str
    sources: list[str]


class JobLog(BaseModel):
    """A single log entry."""
    timestamp: str
    level: LogLevel
    message: str
    source: str | None = None
    details: dict[str, Any] | None = None


class JobStatusResponse(BaseModel):
    """Response for job status query."""
    job_id: str
    status: JobStatus
    started_at: str | None
    completed_at: str | None
    duration_seconds: float | None
    sources_total: int
    sources_completed: int
    events_fetched: int
    events_parsed: int
    events_inserted: int
    events_skipped: int
    events_failed: int
    errors: list[str]
    logs: list[JobLog]
    results: dict[str, Any] | None
    config: dict[str, Any] | None


def add_job_log(job: dict, level: LogLevel, message: str, source: str | None = None, details: dict | None = None):
    """Add a log entry to the job."""
    job["logs"].append({
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
        "source": source,
        "details": details,
    })


def find_sources_by_province(province: str) -> list[str]:
    """Find all sources that match a province name."""
    province_lower = province.lower().replace(" ", "_")
    matches = []

    for slug, config in SourceRegistry._sources.items():
        # Direct match in slug (e.g., viralagenda_zamora)
        if province_lower in slug.lower():
            matches.append(slug)
            continue

        # Check config's province attribute
        config_province = getattr(config, 'province', None)
        if config_province and province_lower in config_province.lower().replace(" ", "_"):
            matches.append(slug)

    return matches


def find_sources_by_ccaa(ccaa: str) -> list[str]:
    """Find all sources that match a CCAA."""
    ccaa_lower = ccaa.lower()
    matches = []

    for slug, config in SourceRegistry._sources.items():
        if ccaa_lower in config.ccaa.lower():
            matches.append(slug)

    return matches


def find_sources_by_tier(tier: str) -> list[str]:
    """Find all sources of a specific tier."""
    tier_enum = SourceTier(tier)
    sources = SourceRegistry.get_by_tier(tier_enum)
    return [s.slug for s in sources]


async def run_scrape_job(
    job_id: str,
    sources: list[str],
    limit: int,
    dry_run: bool,
):
    """Background task to run scraping using the unified pipeline."""
    job = _jobs[job_id]
    job["status"] = JobStatus.RUNNING
    job["started_at"] = datetime.now().isoformat()

    add_job_log(job, LogLevel.INFO, f"Job iniciado para {len(sources)} fuentes", details={"sources": sources})

    for source_slug in sources:
        try:
            add_job_log(job, LogLevel.INFO, f"Iniciando scraping", source=source_slug)
            logger.info("scrape_job_source_start", job_id=job_id, source=source_slug)

            # Use the unified pipeline
            result: PipelineResult = await run_pipeline(
                source_slug=source_slug,
                limit=limit,
                dry_run=dry_run,
            )

            # Update job stats
            job["events_fetched"] += result.raw_count
            job["events_parsed"] += result.parsed_count

            if result.success:
                job["events_inserted"] += result.inserted_count
                job["events_skipped"] += result.skipped_existing

                # Log progress
                add_job_log(
                    job, LogLevel.INFO,
                    f"Obtenidos {result.raw_count} eventos raw",
                    source=source_slug
                )

                # Warning if limit not reached
                if result.requested_limit and not result.limit_reached:
                    add_job_log(
                        job, LogLevel.WARNING,
                        f"Solicitados {result.requested_limit} eventos pero solo hay {result.limited_count} disponibles",
                        source=source_slug,
                        details={"requested": result.requested_limit, "available": result.limited_count}
                    )

                if result.skipped_past > 0:
                    add_job_log(
                        job, LogLevel.INFO,
                        f"Filtrados {result.skipped_past} eventos pasados",
                        source=source_slug
                    )

                add_job_log(
                    job, LogLevel.SUCCESS,
                    f"Parseados {result.parsed_count} eventos válidos",
                    source=source_slug
                )

                if result.enriched_count > 0:
                    add_job_log(
                        job, LogLevel.SUCCESS,
                        f"Enriquecidos {result.enriched_count} eventos con LLM",
                        source=source_slug
                    )

                if result.images_found > 0:
                    add_job_log(
                        job, LogLevel.SUCCESS,
                        f"Resueltas {result.images_found} imágenes",
                        source=source_slug
                    )

                if dry_run:
                    add_job_log(
                        job, LogLevel.INFO,
                        "Modo dry_run - no se guardaron eventos",
                        source=source_slug
                    )
                elif result.inserted_count > 0:
                    add_job_log(
                        job, LogLevel.SUCCESS,
                        f"Insertados {result.inserted_count} eventos",
                        source=source_slug,
                        details={
                            "inserted": result.inserted_count,
                            "skipped": result.skipped_existing,
                            "categories": result.categories,
                        }
                    )
                else:
                    add_job_log(
                        job, LogLevel.INFO,
                        f"0 eventos nuevos (skipped: {result.skipped_existing})",
                        source=source_slug
                    )

                job["results"][source_slug] = {
                    "fetched": result.raw_count,
                    "parsed": result.parsed_count,
                    "enriched": result.enriched_count,
                    "inserted": result.inserted_count,
                    "skipped": result.skipped_existing,
                    "categories": result.categories,
                    "error": None,
                }
            else:
                job["events_failed"] += 1
                job["errors"].append(f"{source_slug}: {result.error}")
                add_job_log(job, LogLevel.ERROR, f"Error: {result.error}", source=source_slug)
                job["results"][source_slug] = {
                    "fetched": result.raw_count,
                    "parsed": result.parsed_count,
                    "inserted": 0,
                    "skipped": 0,
                    "error": result.error,
                }

            job["sources_completed"] += 1
            add_job_log(job, LogLevel.SUCCESS, f"Completado ({result.duration_seconds:.1f}s)", source=source_slug)

        except Exception as e:
            logger.error("scrape_job_source_error", job_id=job_id, source=source_slug, error=str(e))
            add_job_log(job, LogLevel.ERROR, f"Error: {str(e)}", source=source_slug)
            job["errors"].append(f"{source_slug}: {str(e)}")
            job["events_failed"] += 1
            job["results"][source_slug] = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "error": str(e)}
            job["sources_completed"] += 1

    job["status"] = JobStatus.COMPLETED
    job["completed_at"] = datetime.now().isoformat()

    # Calculate duration
    start = datetime.fromisoformat(job["started_at"])
    end = datetime.fromisoformat(job["completed_at"])
    job["duration_seconds"] = (end - start).total_seconds()

    add_job_log(job, LogLevel.SUCCESS,
                f"Job completado: {job['events_inserted']} insertados, {job['events_skipped']} omitidos",
                details={
                    "total_inserted": job["events_inserted"],
                    "total_skipped": job["events_skipped"],
                    "duration_seconds": job["duration_seconds"],
                })
    logger.info("scrape_job_completed", job_id=job_id, inserted=job["events_inserted"])


@router.post("", response_model=ScrapeResponse)
async def start_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """Start a new scrape job.

    Filters (use one):
    - sources: List of specific source slugs
    - tier: Filter by tier (gold, silver, bronze)
    - province: Filter by province name (e.g., "zamora", "madrid")
    - ccaa: Filter by autonomous community (e.g., "castilla y leon", "andalucia")
    """
    # Determine sources based on filters
    sources = []
    filter_used = None

    if request.sources:
        sources = request.sources
        filter_used = "sources"
    elif request.province:
        sources = find_sources_by_province(request.province)
        filter_used = f"province:{request.province}"
    elif request.ccaa:
        sources = find_sources_by_ccaa(request.ccaa)
        filter_used = f"ccaa:{request.ccaa}"
    elif request.tier:
        sources = find_sources_by_tier(request.tier)
        filter_used = f"tier:{request.tier}"
    else:
        raise HTTPException(status_code=400, detail="Must specify 'sources', 'tier', 'province', or 'ccaa'")

    if not sources:
        raise HTTPException(status_code=400, detail=f"No sources found for filter: {filter_used}")

    # Create job with enhanced tracking
    job_id = str(uuid4())[:8]
    _jobs[job_id] = {
        "status": JobStatus.PENDING,
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
        "config": {
            "sources": sources,
            "filter": filter_used,
            "limit": request.limit,
            "dry_run": request.dry_run,
        },
    }

    # Start background task
    background_tasks.add_task(
        run_scrape_job,
        job_id,
        sources,
        request.limit,
        request.dry_run,
    )

    return ScrapeResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=f"Scrape job started for {len(sources)} sources ({filter_used})",
        sources=sources,
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get detailed status of a scrape job including logs."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    job = _jobs[job_id]

    # Convert log dicts to JobLog models
    logs = [JobLog(**log) for log in job.get("logs", [])]

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        started_at=job["started_at"],
        completed_at=job["completed_at"],
        duration_seconds=job.get("duration_seconds"),
        sources_total=job["sources_total"],
        sources_completed=job["sources_completed"],
        events_fetched=job["events_fetched"],
        events_parsed=job.get("events_parsed", 0),
        events_inserted=job["events_inserted"],
        events_skipped=job.get("events_skipped", 0),
        events_failed=job.get("events_failed", 0),
        errors=job["errors"],
        logs=logs,
        results=job["results"] if job["status"] == JobStatus.COMPLETED else None,
        config=job.get("config"),
    )


@router.get("/status/{job_id}/logs")
async def get_job_logs(job_id: str, since: int = 0):
    """Get only logs for a job (for polling).

    Args:
        job_id: The job ID
        since: Return only logs after this index (for incremental updates)
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    job = _jobs[job_id]
    logs = job.get("logs", [])

    return {
        "job_id": job_id,
        "status": job["status"],
        "total_logs": len(logs),
        "logs": logs[since:],
        "next_index": len(logs),
    }


@router.get("/jobs")
async def list_jobs(limit: int = 20):
    """List all scrape jobs with summary info."""
    jobs_list = []
    for jid, job in list(_jobs.items())[-limit:]:
        jobs_list.append({
            "job_id": jid,
            "status": job["status"],
            "filter": job.get("config", {}).get("filter", "unknown"),
            "sources_total": job["sources_total"],
            "sources_completed": job["sources_completed"],
            "events_inserted": job["events_inserted"],
            "events_skipped": job.get("events_skipped", 0),
            "started_at": job["started_at"],
            "completed_at": job["completed_at"],
            "duration_seconds": job.get("duration_seconds"),
            "has_errors": len(job["errors"]) > 0,
        })

    return {
        "total": len(_jobs),
        "showing": len(jobs_list),
        "jobs": list(reversed(jobs_list)),  # Most recent first
    }


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a completed job from memory."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    job = _jobs[job_id]
    if job["status"] == JobStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete a running job")

    del _jobs[job_id]
    return {"message": f"Job '{job_id}' deleted"}


@router.get("/provinces")
async def list_provinces():
    """List all available provinces with their sources."""
    provinces = {}

    for slug, config in SourceRegistry._sources.items():
        # Extract province from viralagenda slugs
        if slug.startswith("viralagenda_"):
            province = slug.replace("viralagenda_", "").replace("_", " ").title()
            if province not in provinces:
                provinces[province] = []
            provinces[province].append(slug)
        else:
            # Try to get from config
            province = getattr(config, 'province', None)
            if province:
                province = province.title()
                if province not in provinces:
                    provinces[province] = []
                provinces[province].append(slug)

    return {
        "total": len(provinces),
        "provinces": [
            {"name": name, "sources": srcs, "source_count": len(srcs)}
            for name, srcs in sorted(provinces.items())
        ],
    }


@router.get("/ccaas")
async def list_ccaas():
    """List all available CCAAs with their sources."""
    ccaas = {}

    for slug, config in SourceRegistry._sources.items():
        ccaa = config.ccaa
        if ccaa:
            if ccaa not in ccaas:
                ccaas[ccaa] = []
            ccaas[ccaa].append(slug)

    return {
        "total": len(ccaas),
        "ccaas": [
            {"name": name, "sources": srcs, "source_count": len(srcs)}
            for name, srcs in sorted(ccaas.items())
        ],
    }


@router.get("/tiers")
async def list_tiers():
    """List all tiers with their source counts."""
    tiers = {}

    for tier in SourceTier:
        sources = SourceRegistry.get_by_tier(tier)
        tiers[tier.value] = {
            "count": len(sources),
            "sources": [s.slug for s in sources],
        }

    return tiers
