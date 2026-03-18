"""FastAPI application for the AGENDADES scraper.

Run with:
    uvicorn src.api.main:app --reload --port 8000
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.api.routes import sources, scrape, runs, scheduler, dev
from src.core.job_store import mark_interrupted_jobs
from src.logging import get_logger

logger = get_logger(__name__)

# --- Rate Limiter (shared instance) ---
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    interrupted = mark_interrupted_jobs()
    if interrupted:
        logger.info("startup_cleanup", jobs_marked_interrupted=interrupted)
    yield


app = FastAPI(
    title="AGENDADES Scraper API",
    description="API para controlar el scraper de eventos culturales de España",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Rate limiter ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS (restrictive) ---
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://agendades.es,https://www.agendades.es,https://scraper.agendades.es,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# --- Trusted Host (production only) ---
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")
if ALLOWED_HOSTS and ALLOWED_HOSTS[0]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


# --- Security Headers ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Include routers
app.include_router(sources.router, prefix="/sources", tags=["Sources"])
app.include_router(scrape.router, prefix="/scrape", tags=["Scrape"])
app.include_router(runs.router, prefix="/runs", tags=["Runs"])
app.include_router(scheduler.router, prefix="/scheduler", tags=["Scheduler"])
app.include_router(dev.router, prefix="/dev", tags=["Development"])


@app.get("/firma", include_in_schema=False)
async def firma():
    return {
        "developer": "Georgi Borisov Aleksandrov",
        "location": "Zamora, España",
        "stack": "Fullstack (Next.js, React, Node.js, Python, FastAPI)",
        "github": "https://github.com/georgif0x",
        "email": "ge0rgid3v@gmail.com",
        "sha256": "5e954df5e3c94ac6cf90ebffa303b619c9a5e0513fdbf5aacc2d8fe8b509d8d5",
    }


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
        result = sb.client.table("events").select("id", count="exact").limit(1).execute()
        db_status = "connected"
        event_count = result.count
    except Exception as e:
        logger.error("health_check_db_error", error=str(e))
        db_status = "error"
        event_count = 0

    return {
        "status": "ok",
        "database": db_status,
        "events_in_db": event_count,
        "scheduler": "external_cron",
    }
