"""FastAPI application for the AGENDADES scraper.

Run with:
    uvicorn src.api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import sources, scrape, runs, scheduler, dev
from src.core.job_store import mark_interrupted_jobs
from src.logging import get_logger

# Scheduler disabled - using external cron job on VPS instead
# from src.scheduler import init_scheduler

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Mark any jobs that were running when we crashed as interrupted
    interrupted = mark_interrupted_jobs()
    if interrupted:
        logger.info("startup_cleanup", jobs_marked_interrupted=interrupted)

    # Internal scheduler disabled - using external cron job on VPS
    # init_scheduler()
    yield
    # Shutdown: Nothing to clean up


app = FastAPI(
    title="AGENDADES Scraper API",
    description="API para controlar el scraper de eventos culturales de España",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, restringir a dominios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sources.router, prefix="/sources", tags=["Sources"])
app.include_router(scrape.router, prefix="/scrape", tags=["Scrape"])
app.include_router(runs.router, prefix="/runs", tags=["Runs"])
app.include_router(scheduler.router, prefix="/scheduler", tags=["Scheduler"])
app.include_router(dev.router, prefix="/dev", tags=["Development"])


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "AGENDADES Scraper API",
        "version": "1.0.0",
    }


@app.get("/health", tags=["Health"])
async def health():
    """Detailed health check."""
    from src.core.supabase_client import get_supabase_client

    try:
        sb = get_supabase_client()
        # Quick DB check
        result = sb.client.table("events").select("id", count="exact").limit(1).execute()
        db_status = "connected"
        event_count = result.count
    except Exception as e:
        db_status = f"error: {str(e)}"
        event_count = 0

    return {
        "status": "ok",
        "database": db_status,
        "events_in_db": event_count,
        "scheduler": "external_cron",
        "next_scrape": "Monday 00:01 (cron)",
    }
