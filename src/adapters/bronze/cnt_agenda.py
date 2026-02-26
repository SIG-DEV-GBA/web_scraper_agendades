"""CNT Agenda adapter - Sindical/civic events archive.

Source: https://cnt.es/noticias/category/noticias/agenda/
Tier: Bronze (WordPress category archive)
CCAA: (national scope)
Category: politica (sindical/civic events)

CNT (Confederación Nacional del Trabajo) publishes events in a
WordPress category archive with standard pagination (/page/N/).
Each article card contains title, date, thumbnail, and a link to
the detail page with full description.
"""

import asyncio
import hashlib
import re
from datetime import date
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Date pattern: "28 noviembre, 2025" or "3 marzo 2026"
DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+(\w+),?\s+(\d{4})",
    re.IGNORECASE,
)

BASE_URL = "https://cnt.es"
LISTING_URL = f"{BASE_URL}/noticias/category/noticias/agenda/"


def _make_external_id(title: str, event_date: date) -> str:
    """Generate a stable external_id from title + date."""
    raw = f"{title.strip().lower()}_{event_date.isoformat()}"
    return f"cnt_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


@register_adapter("cnt_agenda")
class CntAgendaAdapter(BaseAdapter):
    """Adapter for CNT - Sindical/civic events archive."""

    source_id = "cnt_agenda"
    source_name = "CNT - Confederación Nacional del Trabajo"
    source_url = LISTING_URL
    ccaa = ""  # National scope
    ccaa_code = ""
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    MAX_PAGES = 5

    async def _fetch_detail(
        self, client: httpx.AsyncClient, detail_url: str,
    ) -> dict[str, Any]:
        """Fetch detail page for date, full description and og:image."""
        result: dict[str, Any] = {}
        try:
            resp = await client.get(detail_url)
            resp.raise_for_status()
        except Exception as e:
            self.logger.debug("detail_fetch_error", url=detail_url, error=str(e))
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        # Date from .posted-on (e.g. "28 noviembre, 2025")
        posted_on = soup.find(class_="posted-on")
        if posted_on:
            date_text = posted_on.get_text(strip=True)
            date_match = DATE_PATTERN.search(date_text)
            if date_match:
                day = int(date_match.group(1))
                month_name = date_match.group(2).lower()
                year = int(date_match.group(3))
                month = MONTHS_ES.get(month_name)
                if month:
                    try:
                        result["start_date"] = date(year, month, day)
                    except ValueError:
                        pass

        # Fallback: article:published_time meta tag
        if "start_date" not in result:
            pub_meta = soup.find("meta", property="article:published_time")
            if pub_meta:
                content = pub_meta.get("content", "")
                if content:
                    try:
                        result["start_date"] = date.fromisoformat(content[:10])
                    except ValueError:
                        pass

        # Full description from .entry-content
        content_div = soup.find(class_="entry-content")
        if content_div:
            paragraphs = []
            for p in content_div.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)
            if paragraphs:
                result["full_description"] = "\n\n".join(paragraphs[:5])

        # og:image for higher quality image
        og_image = soup.find("meta", property="og:image")
        if og_image:
            result["og_image"] = og_image.get("content", "")

        return result

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = True,
        max_events: int = 200,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch events from CNT archive with WordPress pagination."""
        events: list[dict[str, Any]] = []
        effective_limit = min(max_events, limit) if limit else max_events
        seen_ids: set[str] = set()

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for page in range(1, self.MAX_PAGES + 1):
                    if page == 1:
                        url = LISTING_URL
                    else:
                        url = f"{LISTING_URL}page/{page}/"

                    self.logger.info("fetching_cnt_page", url=url, page=page)

                    try:
                        response = await client.get(url)
                        if response.status_code == 404:
                            self.logger.info("no_more_pages", page=page)
                            break
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 404:
                            break
                        raise

                    soup = BeautifulSoup(response.text, "html.parser")
                    articles = soup.find_all("article")

                    if not articles:
                        self.logger.info("no_articles_found", page=page)
                        break

                    page_count = 0
                    for article in articles:
                        event_data = self._parse_card(article)
                        if not event_data:
                            continue

                        # Dates are only on detail pages — always fetch
                        detail_url = event_data.get("detail_url")
                        if detail_url and detail_url not in seen_ids:
                            seen_ids.add(detail_url)
                            await asyncio.sleep(0.5)
                            detail = await self._fetch_detail(client, detail_url)
                            event_data.update(detail)

                            # Skip if no date found
                            start_date = event_data.get("start_date")
                            if not start_date:
                                self.logger.debug(
                                    "no_date_found", title=event_data["title"],
                                )
                                continue

                            # Generate external_id now that we have the date
                            event_data["external_id"] = _make_external_id(
                                event_data["title"], start_date,
                            )

                            events.append(event_data)
                            page_count += 1

                            if len(events) >= effective_limit:
                                break

                    self.logger.info("cnt_page_parsed", page=page, found=page_count)

                    if len(events) >= effective_limit:
                        break

                    if page_count == 0:
                        break

            self.logger.info("cnt_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_card(self, article: Any) -> dict[str, Any] | None:
        """Parse a single <article> card from the archive.

        Note: dates are NOT available on the listing page.
        They are fetched from the detail page via _fetch_detail().

        Structure:
        <article class="post-NNNNN ...">
            <figure><a><img src="thumbnail.jpg" /></a></figure>
            <header class="entry-header">
                <h2 class="entry-title"><a href="...">Title</a></h2>
            </header>
        </article>
        """
        try:
            # Title and link
            title_el = article.find(class_="entry-title")
            if not title_el:
                title_el = article.find(["h2", "h3"])
            if not title_el:
                return None

            link = title_el.find("a")
            if not link:
                return None

            title = link.get_text(strip=True)
            detail_url = link.get("href", "")
            if not title or not detail_url:
                return None

            # Image from card thumbnail
            image_url = None
            img = article.find("img")
            if img:
                image_url = img.get("src") or img.get("data-src")

            # Use post ID from article classes as temporary ID
            article_id = article.get("id", "")  # e.g. "post-23720"

            return {
                "title": title,
                "detail_url": detail_url,
                "image_url": image_url,
                "_article_id": article_id,
            }

        except Exception as e:
            self.logger.debug("parse_card_error", error=str(e))
            return None

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            # Build description
            detail_url = raw_data.get("detail_url", LISTING_URL)
            full_desc = raw_data.get("full_description", "")
            parts = []
            if full_desc:
                parts.append(full_desc)
            parts.append("Evento publicado por CNT - Confederación Nacional del Trabajo.")
            parts.append(
                f'Más información en <a href="{detail_url}" style="color:#2563eb">'
                f"{detail_url}</a>"
            )
            description = "\n\n".join(parts)

            # Use og:image if available, fallback to card thumbnail
            image_url = raw_data.get("og_image") or raw_data.get("image_url")

            organizer = EventOrganizer(
                name="CNT - Confederación Nacional del Trabajo",
                url="https://cnt.es",
                type="asociacion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                description=description,
                city="",
                province="",
                comunidad_autonoma="",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=image_url,
                category_slugs=["politica"],
                organizer=organizer,
                is_free=True,
                requires_registration=False,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
