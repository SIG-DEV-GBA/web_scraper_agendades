"""Image extractor for Madrid events.

Extracts event images from madrid.es pages in batches with rate limiting.
"""

import asyncio
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.logging.logger import get_logger

logger = get_logger(__name__)

# Base URL for Madrid images
MADRID_BASE_URL = "https://www.madrid.es"

# Rate limiting
DEFAULT_DELAY = 0.5  # seconds between requests
DEFAULT_BATCH_SIZE = 20


async def extract_image_from_page(
    client: httpx.AsyncClient,
    event_url: str,
) -> str | None:
    """Extract main event image from a madrid.es event page.

    Args:
        client: HTTP client to use
        event_url: URL of the event page

    Returns:
        Full image URL or None if not found
    """
    if not event_url:
        return None

    try:
        response = await client.get(event_url, follow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Strategy 1: Look for og:image meta tag (preferred)
        og_image = soup.find("meta", property="og:image")
        if og_image:
            img_url = og_image.get("content", "")
            # Skip generic logos
            if img_url and "escudo" not in img_url.lower():
                return img_url

        # Strategy 2: Look for images in content area
        # Madrid uses specific paths for event images
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if not src:
                continue

            # Skip common non-content images
            skip_patterns = [
                "logo", "icon", "banner", "footer", "header",
                "escudo", "marca", "rss", "social", "button"
            ]
            if any(p in src.lower() for p in skip_patterns):
                continue

            # Look for event-specific image paths
            if any(p in src for p in ["/UGBBDD/", "/Actividades/", "/eventos/"]):
                # Make absolute URL if relative
                if src.startswith("/"):
                    return f"{MADRID_BASE_URL}{src}"
                elif not src.startswith("http"):
                    return f"{MADRID_BASE_URL}/{src}"
                return src

        # Strategy 3: First substantial image in main content
        main_content = soup.find("div", class_=re.compile(r"contenido|content|main", re.I))
        if main_content:
            for img in main_content.find_all("img"):
                src = img.get("src", "")
                if src and not any(p in src.lower() for p in ["logo", "icon", "escudo"]):
                    if src.startswith("/"):
                        return f"{MADRID_BASE_URL}{src}"
                    return src

        return None

    except Exception as e:
        logger.warning("image_extract_error", url=event_url[:50], error=str(e))
        return None


async def extract_images_batch(
    events: list[dict[str, Any]],
    url_field: str = "source_url",
    id_field: str = "external_id",
    batch_size: int = DEFAULT_BATCH_SIZE,
    delay: float = DEFAULT_DELAY,
) -> dict[str, str]:
    """Extract images for a batch of events.

    Args:
        events: List of event dicts with URLs
        url_field: Field name containing the event page URL
        id_field: Field name containing the event ID
        batch_size: Max events to process
        delay: Seconds to wait between requests

    Returns:
        Dict mapping event ID to image URL
    """
    results: dict[str, str] = {}
    events_to_process = [e for e in events[:batch_size] if e.get(url_field)]

    if not events_to_process:
        logger.info("image_batch_empty", reason="No events with URLs")
        return results

    logger.info("image_batch_start", total=len(events_to_process))

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0),
        headers={
            "User-Agent": "AgendadesScraper/0.1 (+https://agendades.es)",
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        for i, event in enumerate(events_to_process):
            event_id = event.get(id_field, "")
            event_url = event.get(url_field, "")

            if not event_id or not event_url:
                continue

            image_url = await extract_image_from_page(client, event_url)

            if image_url:
                results[event_id] = image_url
                logger.debug("image_found", event_id=event_id, image=image_url[:60])
            else:
                logger.debug("image_not_found", event_id=event_id)

            # Rate limiting
            if i < len(events_to_process) - 1:
                await asyncio.sleep(delay)

    logger.info("image_batch_complete", processed=len(events_to_process), found=len(results))
    return results


async def enrich_events_with_images(
    events: list[dict[str, Any]],
    url_field: str = "source_url",
    id_field: str = "external_id",
    image_field: str = "image_url",
    batch_size: int = DEFAULT_BATCH_SIZE,
    delay: float = DEFAULT_DELAY,
) -> list[dict[str, Any]]:
    """Enrich events with image URLs in place.

    Args:
        events: List of event dicts to enrich
        url_field: Field name containing the event page URL
        id_field: Field name containing the event ID
        image_field: Field name to store the image URL
        batch_size: Max events to process for images
        delay: Seconds to wait between requests

    Returns:
        The same events list with image_url populated where found
    """
    images = await extract_images_batch(
        events,
        url_field=url_field,
        id_field=id_field,
        batch_size=batch_size,
        delay=delay,
    )

    for event in events:
        event_id = event.get(id_field, "")
        if event_id in images:
            event[image_field] = images[event_id]

    return events
