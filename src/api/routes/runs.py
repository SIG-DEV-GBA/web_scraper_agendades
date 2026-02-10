"""Runs routes - view scraping history and statistics."""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.core.supabase_client import get_supabase_client

router = APIRouter()


class EventStats(BaseModel):
    """Event statistics."""
    total: int
    by_source: dict[str, int]
    by_ccaa: dict[str, int]
    with_image: int
    with_description: int
    with_coordinates: int


class QualityMetrics(BaseModel):
    """Quality metrics for events."""
    total_events: int
    description_coverage: float
    image_coverage: float
    coordinates_coverage: float
    category_coverage: float
    summary_coverage: float


@router.get("/stats")
async def get_stats():
    """Get overall statistics."""
    sb = get_supabase_client()

    # Total events
    total_result = sb.client.table("events").select("id", count="exact").execute()
    total = total_result.count or 0

    # By source
    sources_result = sb.client.table("scraper_sources").select("id, slug").execute()
    source_map = {s["id"]: s["slug"] for s in sources_result.data}

    by_source = {}
    for source_id, slug in source_map.items():
        count_result = sb.client.table("events").select("id", count="exact").eq("source_id", source_id).execute()
        if count_result.count:
            by_source[slug] = count_result.count

    # Events with image
    with_image_result = sb.client.table("events").select("id", count="exact").not_.is_("source_image_url", "null").execute()
    with_image = with_image_result.count or 0

    # Events with description
    with_desc_result = sb.client.table("events").select("id", count="exact").not_.is_("description", "null").execute()
    with_desc = with_desc_result.count or 0

    return {
        "total_events": total,
        "by_source": by_source,
        "with_image": with_image,
        "with_image_pct": round(with_image / total * 100, 1) if total > 0 else 0,
        "with_description": with_desc,
        "with_description_pct": round(with_desc / total * 100, 1) if total > 0 else 0,
    }


@router.get("/quality", response_model=QualityMetrics)
async def get_quality_metrics(limit: int = Query(100, description="Number of recent events to analyze")):
    """Get quality metrics for recent events."""
    sb = get_supabase_client()

    # Get recent events
    events_result = sb.client.table("events").select(
        "id, description, summary, source_image_url"
    ).order("created_at", desc=True).limit(limit).execute()

    events = events_result.data
    total = len(events)

    if total == 0:
        return QualityMetrics(
            total_events=0,
            description_coverage=0,
            image_coverage=0,
            coordinates_coverage=0,
            category_coverage=0,
            summary_coverage=0,
        )

    # Get related data
    event_ids = [e["id"] for e in events]

    # Locations with coordinates
    locations_result = sb.client.table("event_locations").select(
        "event_id, latitude, longitude"
    ).in_("event_id", event_ids).execute()
    events_with_coords = set(
        loc["event_id"] for loc in locations_result.data
        if loc.get("latitude") and loc.get("longitude")
    )

    # Categories
    categories_result = sb.client.table("event_categories").select(
        "event_id"
    ).in_("event_id", event_ids).execute()
    events_with_category = set(cat["event_id"] for cat in categories_result.data)

    # Calculate metrics
    with_desc = sum(1 for e in events if e.get("description"))
    with_image = sum(1 for e in events if e.get("source_image_url"))
    with_summary = sum(1 for e in events if e.get("summary"))

    return QualityMetrics(
        total_events=total,
        description_coverage=round(with_desc / total * 100, 1),
        image_coverage=round(with_image / total * 100, 1),
        coordinates_coverage=round(len(events_with_coords) / total * 100, 1),
        category_coverage=round(len(events_with_category) / total * 100, 1),
        summary_coverage=round(with_summary / total * 100, 1),
    )


@router.get("/recent")
async def get_recent_events(
    limit: int = Query(20, ge=1, le=100),
    source: str | None = Query(None, description="Filter by source slug"),
):
    """Get recently inserted events."""
    sb = get_supabase_client()

    query = sb.client.table("events").select(
        "id, title, start_date, source_id, source_image_url, created_at"
    ).order("created_at", desc=True).limit(limit)

    if source:
        # Get source UUID
        source_result = sb.client.table("scraper_sources").select("id").eq("slug", source).single().execute()
        if source_result.data:
            query = query.eq("source_id", source_result.data["id"])

    result = query.execute()

    # Get source names
    sources_result = sb.client.table("scraper_sources").select("id, slug, name").execute()
    source_map = {s["id"]: {"slug": s["slug"], "name": s["name"]} for s in sources_result.data}

    events = []
    for e in result.data:
        source_info = source_map.get(e["source_id"], {"slug": "unknown", "name": "Unknown"})
        events.append({
            "id": e["id"],
            "title": e["title"],
            "start_date": e["start_date"],
            "source_slug": source_info["slug"],
            "source_name": source_info["name"],
            "has_image": bool(e.get("source_image_url")),
            "created_at": e["created_at"],
        })

    return {"total": len(events), "events": events}


@router.get("/by-date")
async def get_events_by_date(
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
):
    """Get event counts by insertion date."""
    sb = get_supabase_client()

    # Get events from last N days
    since = (datetime.now() - timedelta(days=days)).isoformat()

    result = sb.client.table("events").select(
        "created_at"
    ).gte("created_at", since).execute()

    # Group by date
    by_date: dict[str, int] = {}
    for e in result.data:
        date_str = e["created_at"][:10]  # YYYY-MM-DD
        by_date[date_str] = by_date.get(date_str, 0) + 1

    # Sort by date
    sorted_dates = sorted(by_date.items())

    return {
        "days": days,
        "total": len(result.data),
        "by_date": [{"date": d, "count": c} for d, c in sorted_dates],
    }
