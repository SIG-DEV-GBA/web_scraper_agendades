"""Development/testing routes for the scraper API."""

import os

import httpx
from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import require_api_key
from src.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Web URL for cache invalidation
WEB_URL = os.getenv("WEB_URL", "https://www.agendades.es")


@router.post("/revalidate")
async def revalidate_web_cache(_: str = Depends(require_api_key)):
    """Invalidate the web cache to see new events immediately."""
    revalidate_url = f"{WEB_URL}/api/revalidate"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(revalidate_url, timeout=15)

            if response.status_code == 200:
                data = response.json()
                logger.info("web_cache_invalidated", url=revalidate_url)
                return {
                    "success": True,
                    "message": "Cache invalidado correctamente",
                    "web_response": data,
                }
            else:
                logger.warning(
                    "web_cache_invalidate_failed",
                    status=response.status_code,
                )
                raise HTTPException(
                    status_code=502,
                    detail="Error al invalidar cache de la web",
                )

    except httpx.TimeoutException:
        logger.error("web_cache_invalidate_timeout", url=revalidate_url)
        raise HTTPException(status_code=504, detail="Timeout al contactar la web")

    except httpx.RequestError as e:
        logger.error("web_cache_invalidate_error", error=str(e))
        raise HTTPException(status_code=502, detail="Error de conexion con la web")


@router.get("/status")
async def dev_status():
    """Check development endpoints status."""
    return {
        "web_url": WEB_URL,
        "revalidate_endpoint": f"{WEB_URL}/api/revalidate",
        "endpoints": [
            "POST /dev/revalidate - Invalidate web cache (requires API key)",
        ],
    }
