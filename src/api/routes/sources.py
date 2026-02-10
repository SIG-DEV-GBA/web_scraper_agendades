"""Sources routes - list available scraper sources."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.adapters import list_adapters, get_adapter
from src.core.supabase_client import get_supabase_client

router = APIRouter()


class SourceInfo(BaseModel):
    """Source information."""
    slug: str
    name: str
    tier: str
    ccaa: str | None = None
    enabled: bool = True


class SourcesResponse(BaseModel):
    """Response for sources list."""
    total: int
    sources: list[SourceInfo]


@router.get("", response_model=SourcesResponse)
async def list_sources():
    """List all available scraper sources."""
    adapter_slugs = list_adapters()

    sources = []
    for slug in adapter_slugs:
        adapter_class = get_adapter(slug)
        if not adapter_class:
            sources.append(SourceInfo(
                slug=slug,
                name=slug,
                tier='unknown',
                enabled=False,
            ))
            continue

        try:
            adapter = adapter_class()
            sources.append(SourceInfo(
                slug=slug,
                name=getattr(adapter, 'source_name', slug),
                tier=getattr(adapter, 'tier', 'unknown'),
                ccaa=getattr(adapter, 'ccaa', None),
                enabled=True,
            ))
        except Exception:
            sources.append(SourceInfo(
                slug=slug,
                name=slug,
                tier='unknown',
                enabled=False,
            ))

    # Sort by tier (gold first) then by name
    tier_order = {'gold': 0, 'silver': 1, 'bronze': 2, 'unknown': 3}
    sources.sort(key=lambda s: (tier_order.get(s.tier, 3), s.name))

    return SourcesResponse(total=len(sources), sources=sources)


@router.get("/by-tier/{tier}")
async def list_sources_by_tier(tier: str):
    """List sources filtered by tier (gold, silver, bronze)."""
    adapter_slugs = list_adapters()

    sources = []
    for slug in adapter_slugs:
        adapter_class = get_adapter(slug)
        if not adapter_class:
            continue
        try:
            adapter = adapter_class()
            adapter_tier = getattr(adapter, 'tier', 'unknown')
            if adapter_tier == tier:
                sources.append(SourceInfo(
                    slug=slug,
                    name=getattr(adapter, 'source_name', slug),
                    tier=adapter_tier,
                    ccaa=getattr(adapter, 'ccaa', None),
                    enabled=True,
                ))
        except Exception:
            pass

    sources.sort(key=lambda s: s.name)
    return SourcesResponse(total=len(sources), sources=sources)


@router.get("/by-ccaa/{ccaa}")
async def list_sources_by_ccaa(ccaa: str):
    """List sources filtered by CCAA."""
    adapter_slugs = list_adapters()

    sources = []
    for slug in adapter_slugs:
        adapter_class = get_adapter(slug)
        if not adapter_class:
            continue
        try:
            adapter = adapter_class()
            adapter_ccaa = getattr(adapter, 'ccaa', None)
            if adapter_ccaa and ccaa.lower() in adapter_ccaa.lower():
                sources.append(SourceInfo(
                    slug=slug,
                    name=getattr(adapter, 'source_name', slug),
                    tier=getattr(adapter, 'tier', 'unknown'),
                    ccaa=adapter_ccaa,
                    enabled=True,
                ))
        except Exception:
            pass

    sources.sort(key=lambda s: s.name)
    return SourcesResponse(total=len(sources), sources=sources)


@router.get("/{slug}")
async def get_source(slug: str):
    """Get details for a specific source."""
    adapter_slugs = list_adapters()

    if slug not in adapter_slugs:
        raise HTTPException(status_code=404, detail=f"Source '{slug}' not found")

    try:
        adapter_class = get_adapter(slug)
        adapter = adapter_class()

        # Get event count from DB
        sb = get_supabase_client()
        source_result = sb.client.table("scraper_sources").select("id").eq("slug", slug).single().execute()

        event_count = 0
        if source_result.data:
            count_result = sb.client.table("events").select("id", count="exact").eq("source_id", source_result.data["id"]).execute()
            event_count = count_result.count or 0

        return {
            "slug": slug,
            "name": getattr(adapter, 'source_name', slug),
            "tier": getattr(adapter, 'tier', 'unknown'),
            "ccaa": getattr(adapter, 'ccaa', None),
            "enabled": True,
            "events_in_db": event_count,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
