"""Scrape routes - execute scraping jobs using the unified pipeline."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from src.config.sources import SourceRegistry, SourceTier
from src.core.pipeline import run_pipeline, PipelineResult
from src.core.job_store import (
    JobStatus,
    LogLevel,
    create_job,
    get_job,
    update_job,
    add_job_log,
    list_jobs as list_jobs_from_store,
    delete_job as delete_job_from_store,
)
from src.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Load all sources
import src.config.sources.gold_sources  # noqa
import src.config.sources.silver_sources  # noqa
import src.config.sources.bronze_sources  # noqa


class ScrapeRequest(BaseModel):
    """Request to start a scrape job."""
    sources: list[str] | None = Field(None, description="List of source slugs to scrape")
    tier: str | None = Field(None, description="Tier to scrape (gold, silver, bronze)")
    province: str | None = Field(None, description="Province to scrape (e.g., 'zamora', 'madrid')")
    ccaa: str | None = Field(None, description="CCAA to scrape (e.g., 'castilla y leon', 'andalucia')")
    limit: int = Field(10, ge=1, description="Max events per source (default: 10)")
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
    # Get job from store (persisted)
    job = get_job(job_id)
    if not job:
        logger.error("job_not_found", job_id=job_id)
        return

    started_at = datetime.now().isoformat()
    update_job(job_id, {"status": JobStatus.RUNNING, "started_at": started_at})
    job["started_at"] = started_at

    add_job_log(job_id, LogLevel.INFO, f"Job iniciado para {len(sources)} fuentes", details={"sources": sources})

    for source_slug in sources:
        try:
            add_job_log(job_id, LogLevel.INFO, f"Iniciando scraping", source=source_slug)
            logger.info("scrape_job_source_start", job_id=job_id, source=source_slug)

            # Use the unified pipeline
            result: PipelineResult = await run_pipeline(
                source_slug=source_slug,
                limit=limit,
                dry_run=dry_run,
            )

            # Update job stats
            job["events_fetched"] = job.get("events_fetched", 0) + result.raw_count
            job["events_parsed"] = job.get("events_parsed", 0) + result.parsed_count

            if result.success:
                job["events_inserted"] = job.get("events_inserted", 0) + result.inserted_count
                job["events_skipped"] = job.get("events_skipped", 0) + result.skipped_existing

                # Log progress
                add_job_log(job_id, LogLevel.INFO, f"Obtenidos {result.raw_count} eventos raw", source=source_slug)

                # Warning if limit not reached
                if result.requested_limit and not result.limit_reached:
                    add_job_log(
                        job_id, LogLevel.WARNING,
                        f"Solicitados {result.requested_limit} eventos pero solo hay {result.limited_count} disponibles",
                        source=source_slug,
                        details={"requested": result.requested_limit, "available": result.limited_count}
                    )

                if result.skipped_past > 0:
                    add_job_log(job_id, LogLevel.INFO, f"Filtrados {result.skipped_past} eventos pasados", source=source_slug)

                # Log filtered existing (new feature)
                if result.filtered_existing > 0:
                    add_job_log(job_id, LogLevel.INFO, f"Omitidos {result.filtered_existing} eventos existentes", source=source_slug)

                add_job_log(job_id, LogLevel.SUCCESS, f"Parseados {result.parsed_count} eventos válidos", source=source_slug)

                if result.enriched_count > 0:
                    add_job_log(job_id, LogLevel.SUCCESS, f"Enriquecidos {result.enriched_count} eventos con LLM", source=source_slug)

                if result.images_found > 0:
                    add_job_log(job_id, LogLevel.SUCCESS, f"Resueltas {result.images_found} imágenes", source=source_slug)

                if dry_run:
                    add_job_log(job_id, LogLevel.INFO, "Modo dry_run - no se guardaron eventos", source=source_slug)
                elif result.inserted_count > 0:
                    add_job_log(
                        job_id, LogLevel.SUCCESS,
                        f"Insertados {result.inserted_count} eventos",
                        source=source_slug,
                        details={"inserted": result.inserted_count, "skipped": result.skipped_existing, "categories": result.categories}
                    )
                else:
                    add_job_log(job_id, LogLevel.INFO, f"0 eventos nuevos (skipped: {result.skipped_existing})", source=source_slug)

                job.setdefault("results", {})[source_slug] = {
                    "fetched": result.raw_count,
                    "parsed": result.parsed_count,
                    "enriched": result.enriched_count,
                    "inserted": result.inserted_count,
                    "skipped": result.skipped_existing,
                    "categories": result.categories,
                    "error": None,
                }
            else:
                job["events_failed"] = job.get("events_failed", 0) + 1
                job.setdefault("errors", []).append(f"{source_slug}: {result.error}")
                add_job_log(job_id, LogLevel.ERROR, f"Error: {result.error}", source=source_slug)
                job.setdefault("results", {})[source_slug] = {
                    "fetched": result.raw_count,
                    "parsed": result.parsed_count,
                    "inserted": 0,
                    "skipped": 0,
                    "error": result.error,
                }

            job["sources_completed"] = job.get("sources_completed", 0) + 1
            add_job_log(job_id, LogLevel.SUCCESS, f"Completado ({result.duration_seconds:.1f}s)", source=source_slug)

            # Persist progress after each source
            update_job(job_id, {
                "events_fetched": job["events_fetched"],
                "events_parsed": job["events_parsed"],
                "events_inserted": job["events_inserted"],
                "events_skipped": job["events_skipped"],
                "events_failed": job.get("events_failed", 0),
                "sources_completed": job["sources_completed"],
                "results": job.get("results", {}),
                "errors": job.get("errors", []),
            })

        except Exception as e:
            logger.error("scrape_job_source_error", job_id=job_id, source=source_slug, error=str(e))
            add_job_log(job_id, LogLevel.ERROR, f"Error: {str(e)}", source=source_slug)
            job.setdefault("errors", []).append(f"{source_slug}: {str(e)}")
            job["events_failed"] = job.get("events_failed", 0) + 1
            job.setdefault("results", {})[source_slug] = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "error": str(e)}
            job["sources_completed"] = job.get("sources_completed", 0) + 1

    completed_at = datetime.now().isoformat()
    start = datetime.fromisoformat(job["started_at"])
    end = datetime.fromisoformat(completed_at)
    duration = (end - start).total_seconds()

    update_job(job_id, {
        "status": JobStatus.COMPLETED,
        "completed_at": completed_at,
        "duration_seconds": duration,
        "results": job.get("results", {}),
        "errors": job.get("errors", []),
    })

    add_job_log(
        job_id, LogLevel.SUCCESS,
        f"Job completado: {job.get('events_inserted', 0)} insertados, {job.get('events_skipped', 0)} omitidos",
        details={
            "total_inserted": job.get("events_inserted", 0),
            "total_skipped": job.get("events_skipped", 0),
            "duration_seconds": duration,
        }
    )
    logger.info("scrape_job_completed", job_id=job_id, inserted=job.get("events_inserted", 0))


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

    # Create job in persistent store
    job_id = str(uuid4())[:8]
    config = {
        "sources": sources,
        "filter": filter_used,
        "limit": request.limit,
        "dry_run": request.dry_run,
    }
    create_job(job_id, sources, config)

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
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # Convert log dicts to JobLog models
    logs = [JobLog(**log) for log in job.get("logs", [])]

    # Handle status as enum or string
    status = job.get("status")
    if hasattr(status, "value"):
        status = status
    else:
        status = JobStatus(status) if status else JobStatus.PENDING

    return JobStatusResponse(
        job_id=job_id,
        status=status,
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        duration_seconds=job.get("duration_seconds"),
        sources_total=job.get("sources_total", 0),
        sources_completed=job.get("sources_completed", 0),
        events_fetched=job.get("events_fetched", 0),
        events_parsed=job.get("events_parsed", 0),
        events_inserted=job.get("events_inserted", 0),
        events_skipped=job.get("events_skipped", 0),
        events_failed=job.get("events_failed", 0),
        errors=job.get("errors", []),
        logs=logs,
        results=job.get("results") if status == JobStatus.COMPLETED else None,
        config=job.get("config"),
    )


@router.get("/status/{job_id}/logs")
async def get_job_logs(job_id: str, since: int = 0):
    """Get only logs for a job (for polling).

    Args:
        job_id: The job ID
        since: Return only logs after this index (for incremental updates)
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    logs = job.get("logs", [])
    status = job.get("status")
    if hasattr(status, "value"):
        status = status.value

    return {
        "job_id": job_id,
        "status": status,
        "total_logs": len(logs),
        "logs": logs[since:],
        "next_index": len(logs),
    }


@router.get("/jobs")
async def list_jobs_endpoint(limit: int = 20):
    """List all scrape jobs with summary info."""
    jobs_list = list_jobs_from_store(limit=limit)

    return {
        "total": len(jobs_list),
        "showing": len(jobs_list),
        "jobs": jobs_list,
    }


@router.delete("/jobs/{job_id}")
async def delete_job_endpoint(job_id: str):
    """Delete a completed job from database."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    status = job.get("status")
    if status == JobStatus.RUNNING or status == "running":
        raise HTTPException(status_code=400, detail="Cannot delete a running job")

    deleted = delete_job_from_store(job_id)
    if deleted:
        return {"message": f"Job '{job_id}' deleted"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete job")


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


class PreviewResponse(BaseModel):
    """Response from preview endpoint."""
    source: str
    raw_count: int
    valid_count: int
    error: str | None = None


@router.get("/preview/{source_slug}", response_model=PreviewResponse)
async def preview_source(source_slug: str):
    """Preview how many valid events a source has without inserting.

    Fetches and parses events from the source to show the count
    of valid events that would be scraped.
    """
    from src.core.pipeline import InsertionPipeline, PipelineConfig

    try:
        # Check source exists
        config = SourceRegistry.get(source_slug)
        if not config:
            raise HTTPException(status_code=404, detail=f"Source '{source_slug}' not found")

        # Create pipeline in dry_run mode (no insertion)
        # Skip details, enrichment, images for fast preview
        pipeline_config = PipelineConfig(
            source_slug=source_slug,
            limit=None,  # No limit - get full count
            fetch_details=False,  # Skip detail pages for speed
            skip_enrichment=True,  # Skip LLM to be fast
            skip_images=True,  # Skip images to be fast
            dry_run=True,
        )
        pipeline = InsertionPipeline(pipeline_config)

        # Run fetch and parse only (no enrichment, no insertion)
        result = await pipeline.run()

        return PreviewResponse(
            source=source_slug,
            raw_count=result.raw_count,
            valid_count=result.parsed_count,
            error=result.error,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("preview_error", source=source_slug, error=str(e))
        return PreviewResponse(
            source=source_slug,
            raw_count=0,
            valid_count=0,
            error=str(e),
        )


# ============================================================
# BATCH VIRALAGENDA ENDPOINT (for cron jobs)
# ============================================================

# Valid Viralagenda sources (only CCAA that exist)
VALID_VIRALAGENDA_SOURCES = [
    # Andalucía (8)
    "viralagenda_almeria", "viralagenda_cadiz", "viralagenda_cordoba",
    "viralagenda_granada", "viralagenda_huelva", "viralagenda_jaen",
    "viralagenda_malaga", "viralagenda_sevilla",
    # Castilla y León (9)
    "viralagenda_avila", "viralagenda_burgos", "viralagenda_leon",
    "viralagenda_palencia", "viralagenda_salamanca", "viralagenda_segovia",
    "viralagenda_soria", "viralagenda_valladolid", "viralagenda_zamora",
    # Extremadura (2)
    "viralagenda_caceres", "viralagenda_badajoz",
    # Galicia (4)
    "viralagenda_a_coruna", "viralagenda_lugo", "viralagenda_ourense",
    "viralagenda_pontevedra",
]


class BatchViralAgendaRequest(BaseModel):
    """Request for batch Viralagenda scraping."""
    limit: int = Field(40, ge=1, le=100, description="Max events per source")
    min_events: int = Field(40, ge=1, description="Skip sources with >= this many events")
    dry_run: bool = Field(False, description="Don't save to database")


class BatchViralAgendaResponse(BaseModel):
    """Response from batch Viralagenda endpoint."""
    job_id: str
    status: JobStatus
    message: str
    sources_to_process: int
    sources_skipped: int
    sources: list[str]


async def get_viralagenda_counts() -> dict[str, int]:
    """Get event counts per Viralagenda source from DB."""
    from src.core.supabase_client import get_supabase_client

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


@router.post("/batch/viralagenda", response_model=BatchViralAgendaResponse)
async def batch_viralagenda(
    request: BatchViralAgendaRequest,
    background_tasks: BackgroundTasks,
):
    """Run batch scraping for all valid Viralagenda sources.

    Skips sources that already have >= min_events in the database.
    Processes sources one at a time with delays to avoid blocking.

    Use this endpoint for weekly cron jobs:
    - Cron: 0 19 * * 3 (every Wednesday at 19:00)
    - Command: curl -X POST http://localhost:8000/scrape/batch/viralagenda
    """
    # Get current counts
    counts = await get_viralagenda_counts()

    # Filter sources to process
    sources_to_run = []
    sources_skipped = []

    for source in VALID_VIRALAGENDA_SOURCES:
        current = counts.get(source, 0)
        if current >= request.min_events:
            sources_skipped.append(source)
        else:
            sources_to_run.append(source)

    if not sources_to_run:
        return BatchViralAgendaResponse(
            job_id="none",
            status=JobStatus.COMPLETED,
            message="All sources already have enough events",
            sources_to_process=0,
            sources_skipped=len(sources_skipped),
            sources=[],
        )

    # Create job in persistent store
    job_id = str(uuid4())[:8]
    config = {
        "sources": sources_to_run,
        "filter": "batch_viralagenda",
        "limit": request.limit,
        "dry_run": request.dry_run,
        "skipped_sources": sources_skipped,
    }
    create_job(job_id, sources_to_run, config)

    # Start background task
    background_tasks.add_task(
        run_scrape_job,
        job_id,
        sources_to_run,
        request.limit,
        request.dry_run,
    )

    logger.info(
        "batch_viralagenda_started",
        job_id=job_id,
        sources_to_process=len(sources_to_run),
        sources_skipped=len(sources_skipped),
    )

    return BatchViralAgendaResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=f"Batch job started: {len(sources_to_run)} sources to process, {len(sources_skipped)} skipped",
        sources_to_process=len(sources_to_run),
        sources_skipped=len(sources_skipped),
        sources=sources_to_run,
    )
