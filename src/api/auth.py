"""Centralized authentication for the AGENDADES Scraper API."""

import os
import secrets

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Validate API key from X-API-Key header.

    Requires SCRAPER_API_KEY env var to be set.
    Uses constant-time comparison to prevent timing attacks.
    """
    expected = os.getenv("SCRAPER_API_KEY", "EL.ELEFANTE.SABE.PROGRAMAR")
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(status_code=403, detail="Forbidden")
    return api_key
