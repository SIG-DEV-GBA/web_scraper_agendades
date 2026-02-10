"""Scrape routes - execute scraping jobs with detailed logging."""

import asyncio
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.adapters import list_adapters, get_adapter
from src.core.event_model import EventBatch
from src.core.llm_enricher import get_llm_enricher, SourceTier
from src.core.image_resolver import get_image_resolver
from src.core.supabase_client import get_supabase_client
from src.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

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
    limit: int = Field(10, ge=1, le=100, description="Max events per source")
    llm_enabled: bool = Field(True, description="Enable LLM enrichment")
    images_enabled: bool = Field(True, description="Enable Unsplash image resolution")
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


def get_tier_enum(source_id: str) -> SourceTier:
    """Get SourceTier enum for a source."""
    # Viralagenda is Bronze tier (web scraping)
    if "viralagenda" in source_id:
        return SourceTier.BRONCE
    # Gold tier: official APIs with structured data
    if "datos_abiertos" in source_id or "kulturklik" in source_id or source_id.endswith("_agenda"):
        return SourceTier.ORO
    # Silver tier: RSS feeds
    elif "rss" in source_id or "radar" in source_id or "galicia" in source_id:
        return SourceTier.PLATA
    else:
        return SourceTier.BRONCE


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
    adapter_slugs = list_adapters()
    matches = []

    for slug in adapter_slugs:
        # Direct match in slug (e.g., viralagenda_zamora)
        if province_lower in slug.lower():
            matches.append(slug)
            continue

        # Check adapter's province attribute
        adapter_class = get_adapter(slug)
        if adapter_class:
            try:
                adapter = adapter_class()
                adapter_province = getattr(adapter, 'province', None) or getattr(adapter, 'city', None)
                if adapter_province and province_lower in adapter_province.lower().replace(" ", "_"):
                    matches.append(slug)
            except Exception:
                pass

    return matches


def find_sources_by_ccaa(ccaa: str) -> list[str]:
    """Find all sources that match a CCAA."""
    ccaa_lower = ccaa.lower()
    adapter_slugs = list_adapters()
    matches = []

    for slug in adapter_slugs:
        adapter_class = get_adapter(slug)
        if adapter_class:
            try:
                adapter = adapter_class()
                adapter_ccaa = getattr(adapter, 'ccaa', None)
                if adapter_ccaa and ccaa_lower in adapter_ccaa.lower():
                    matches.append(slug)
            except Exception:
                pass

    return matches


async def run_scrape_job(
    job_id: str,
    sources: list[str],
    limit: int,
    llm_enabled: bool,
    images_enabled: bool,
    dry_run: bool,
):
    """Background task to run scraping with detailed logging."""
    job = _jobs[job_id]
    job["status"] = JobStatus.RUNNING
    job["started_at"] = datetime.now().isoformat()

    add_job_log(job, LogLevel.INFO, f"Job iniciado para {len(sources)} fuentes", details={"sources": sources})

    supabase = get_supabase_client()
    enricher = get_llm_enricher() if llm_enabled else None
    image_resolver = get_image_resolver() if images_enabled else None

    if enricher and enricher.is_enabled:
        add_job_log(job, LogLevel.INFO, "LLM enrichment habilitado")
    if image_resolver and image_resolver.is_enabled:
        add_job_log(job, LogLevel.INFO, "Unsplash image resolver habilitado")

    for source_id in sources:
        try:
            add_job_log(job, LogLevel.INFO, f"Iniciando scraping", source=source_id)
            logger.info("scrape_job_source_start", job_id=job_id, source=source_id)

            # Get adapter
            adapter_class = get_adapter(source_id)
            if not adapter_class:
                add_job_log(job, LogLevel.ERROR, "Adapter no encontrado", source=source_id)
                job["errors"].append(f"{source_id}: adapter not found")
                job["sources_completed"] += 1
                continue

            adapter = adapter_class()
            tier = get_tier_enum(source_id)
            add_job_log(job, LogLevel.INFO, f"Adapter cargado (tier: {tier.value})", source=source_id)

            # Fetch events (pass limit to adapter if supported)
            try:
                raw_events = await adapter.fetch_events(enrich=False, limit=limit)
            except TypeError:
                # Adapter doesn't support limit parameter
                try:
                    raw_events = await adapter.fetch_events(enrich=False)
                except TypeError:
                    raw_events = await adapter.fetch_events()

            if not raw_events:
                add_job_log(job, LogLevel.WARNING, "No se encontraron eventos", source=source_id)
                job["results"][source_id] = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "error": None}
                job["sources_completed"] += 1
                continue

            total_raw = len(raw_events)

            # Limit
            if limit and len(raw_events) > limit:
                raw_events = raw_events[:limit]
                add_job_log(job, LogLevel.INFO, f"Limitado a {limit} eventos (de {total_raw} disponibles)", source=source_id)

            job["events_fetched"] += len(raw_events)
            add_job_log(job, LogLevel.INFO, f"Obtenidos {len(raw_events)} eventos raw", source=source_id)

            # Parse events
            events = []
            parse_errors = 0
            for raw in raw_events:
                try:
                    event = adapter.parse_event(raw)
                    if event:
                        events.append(event)
                except Exception as e:
                    parse_errors += 1

            if parse_errors > 0:
                add_job_log(job, LogLevel.WARNING, f"{parse_errors} eventos fallaron al parsear", source=source_id)

            # Filter past events
            today = date.today()
            future_events = [e for e in events if e.start_date and e.start_date >= today]
            past_filtered = len(events) - len(future_events)
            events = future_events

            job["events_parsed"] += len(events)

            if past_filtered > 0:
                add_job_log(job, LogLevel.INFO, f"Filtrados {past_filtered} eventos pasados", source=source_id)

            if not events:
                add_job_log(job, LogLevel.WARNING, "No hay eventos futuros", source=source_id)
                job["results"][source_id] = {"fetched": len(raw_events), "parsed": 0, "inserted": 0, "skipped": 0, "error": "no future events"}
                job["sources_completed"] += 1
                continue

            add_job_log(job, LogLevel.SUCCESS, f"Parseados {len(events)} eventos válidos", source=source_id)

            # LLM enrichment
            enriched_count = 0
            if llm_enabled and enricher and enricher.is_enabled:
                add_job_log(job, LogLevel.INFO, f"Enriqueciendo con LLM ({tier.value})...", source=source_id)

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

                enrichments = enricher.enrich_batch(events_for_llm, batch_size=5, tier=tier)
                image_keywords_map = {}

                for event in events:
                    eid = event.external_id
                    if eid and eid in enrichments:
                        enr = enrichments[eid]
                        enriched_count += 1
                        if enr.category_slugs:
                            event.category_slugs = enr.category_slugs
                        if enr.summary:
                            event.summary = enr.summary
                        if enr.is_free is not None and event.is_free is None:
                            event.is_free = enr.is_free
                        if enr.image_keywords:
                            category = enr.category_slugs[0] if enr.category_slugs else "default"
                            image_keywords_map[eid] = (enr.image_keywords, category)

                add_job_log(job, LogLevel.SUCCESS, f"Enriquecidos {enriched_count}/{len(events)} eventos", source=source_id)

                # Unsplash images
                images_resolved = 0
                if images_enabled and image_resolver and image_resolver.is_enabled and image_keywords_map:
                    events_needing_image = [e for e in events if e.external_id in image_keywords_map and not e.source_image_url]

                    if events_needing_image:
                        add_job_log(job, LogLevel.INFO, f"Buscando imágenes para {len(events_needing_image)} eventos...", source=source_id)

                        for event in events_needing_image:
                            eid = event.external_id
                            keywords, category = image_keywords_map[eid]
                            image_data = image_resolver.resolve_image_full(keywords, category)
                            if image_data:
                                event.source_image_url = image_data.url
                                event.image_author = image_data.author
                                event.image_author_url = image_data.author_url
                                event.image_source_url = image_data.unsplash_url
                                images_resolved += 1

                        add_job_log(job, LogLevel.SUCCESS, f"Resueltas {images_resolved} imágenes de Unsplash", source=source_id)
                    else:
                        events_with_img = len([e for e in events if e.source_image_url])
                        add_job_log(job, LogLevel.INFO, f"Todos los eventos ya tienen imagen ({events_with_img})", source=source_id)

            # Save to DB
            inserted = 0
            skipped = 0
            if not dry_run:
                add_job_log(job, LogLevel.INFO, f"Guardando en base de datos...", source=source_id)

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
                job["events_inserted"] += inserted
                job["events_skipped"] += skipped

                if inserted > 0:
                    add_job_log(job, LogLevel.SUCCESS, f"Insertados {inserted} eventos", source=source_id,
                               details={"inserted": inserted, "skipped": skipped})
                else:
                    add_job_log(job, LogLevel.INFO, f"0 eventos nuevos (skipped: {skipped})", source=source_id)
            else:
                add_job_log(job, LogLevel.INFO, "Modo dry_run - no se guardaron eventos", source=source_id)

            job["results"][source_id] = {
                "fetched": len(raw_events),
                "parsed": len(events),
                "enriched": enriched_count,
                "inserted": inserted,
                "skipped": skipped,
                "error": None,
            }
            job["sources_completed"] += 1
            add_job_log(job, LogLevel.SUCCESS, f"Completado", source=source_id)

        except Exception as e:
            logger.error("scrape_job_source_error", job_id=job_id, source=source_id, error=str(e))
            add_job_log(job, LogLevel.ERROR, f"Error: {str(e)}", source=source_id)
            job["errors"].append(f"{source_id}: {str(e)}")
            job["events_failed"] += 1
            job["results"][source_id] = {"fetched": 0, "parsed": 0, "inserted": 0, "skipped": 0, "error": str(e)}
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
        adapter_slugs = list_adapters()
        for slug in adapter_slugs:
            adapter_class = get_adapter(slug)
            if not adapter_class:
                continue
            try:
                adapter = adapter_class()
                if getattr(adapter, 'tier', '') == request.tier:
                    sources.append(slug)
            except Exception:
                pass
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
            "llm_enabled": request.llm_enabled,
            "images_enabled": request.images_enabled,
            "dry_run": request.dry_run,
        },
    }

    # Start background task
    background_tasks.add_task(
        run_scrape_job,
        job_id,
        sources,
        request.limit,
        request.llm_enabled,
        request.images_enabled,
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
    adapter_slugs = list_adapters()

    for slug in adapter_slugs:
        # Extract province from viralagenda slugs
        if slug.startswith("viralagenda_"):
            province = slug.replace("viralagenda_", "").replace("_", " ").title()
            if province not in provinces:
                provinces[province] = []
            provinces[province].append(slug)
        else:
            # Try to get from adapter
            adapter_class = get_adapter(slug)
            if adapter_class:
                try:
                    adapter = adapter_class()
                    province = getattr(adapter, 'province', None) or getattr(adapter, 'city', None)
                    if province:
                        province = province.title()
                        if province not in provinces:
                            provinces[province] = []
                        provinces[province].append(slug)
                except Exception:
                    pass

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
    adapter_slugs = list_adapters()

    for slug in adapter_slugs:
        adapter_class = get_adapter(slug)
        if adapter_class:
            try:
                adapter = adapter_class()
                ccaa = getattr(adapter, 'ccaa', None)
                if ccaa:
                    if ccaa not in ccaas:
                        ccaas[ccaa] = []
                    ccaas[ccaa].append(slug)
            except Exception:
                pass

    return {
        "total": len(ccaas),
        "ccaas": [
            {"name": name, "sources": srcs, "source_count": len(srcs)}
            for name, srcs in sorted(ccaas.items())
        ],
    }
