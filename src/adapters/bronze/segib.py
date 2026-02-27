"""SEGIB adapter - Secretaría General Iberoamericana events.

Source: https://www.segib.org/sala-de-prensa/
Tier: Bronze (static HTML, WordPress)
Category: politica (international institutional events)

SEGIB publishes events related to Iberoamerican cooperation.
WordPress site with ACF fields. Events have class "evento" in li.wp-block-post.

Page structure:
  div.wp-block-query
    ul.wp-block-post-template
      li.wp-block-post.evento
        div.tematica > span — category tags
        div.contenido-evento
          h5 > a — title + link
          div.is-acf-field > div.value — date "DD/MM/YYYY"
          div.info p — description
"""

import asyncio
import hashlib
import re
from datetime import date, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.segib.org"
LISTING_URL = f"{BASE_URL}/sala-de-prensa/"

DATE_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
MAX_PAGES = 5


def _make_external_id(title: str, date_str: str) -> str:
    raw = f"{title.strip().lower()[:80]}_{date_str}"
    return f"segib_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


@register_adapter("segib")
class SegibAdapter(BaseAdapter):
    """Adapter for SEGIB - Secretaría General Iberoamericana."""

    source_id = "segib"
    source_name = "SEGIB - Secretaría General Iberoamericana"
    source_url = LISTING_URL
    ccaa = ""  # International scope
    ccaa_code = ""
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = False,
        max_events: int = 200,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        effective_limit = min(max_events, limit) if limit else max_events
        seen_ids: set[str] = set()

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for page_num in range(1, MAX_PAGES + 1):
                    url = LISTING_URL if page_num == 1 else f"{LISTING_URL}page/{page_num}/"
                    self.logger.info("fetching_segib_page", url=url, page=page_num)

                    try:
                        response = await client.get(url)
                        if response.status_code == 404:
                            self.logger.info("segib_pagination_end", page=page_num)
                            break
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        self.logger.warning("page_fetch_error", page=page_num, status=e.response.status_code)
                        break

                    page_events = self._parse_listing(response.text)
                    if not page_events:
                        break

                    for ev in page_events:
                        if ev["external_id"] not in seen_ids:
                            seen_ids.add(ev["external_id"])
                            events.append(ev)
                            if len(events) >= effective_limit:
                                break

                    self.logger.info("segib_page_parsed", page=page_num, found=len(page_events))

                    if len(events) >= effective_limit:
                        break

                    await asyncio.sleep(0.5)

            self.logger.info("segib_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_listing(self, html: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        soup = BeautifulSoup(html, "html.parser")

        # Find event items - they are li with class "evento"
        cards = soup.select("li.wp-block-post.evento")
        if not cards:
            # Fallback: try any li.wp-block-post
            cards = soup.select("li.wp-block-post")

        for card in cards:
            try:
                ev = self._parse_card(card)
                if ev:
                    events.append(ev)
            except Exception as e:
                self.logger.warning("card_parse_error", error=str(e))

        return events

    def _parse_card(self, card) -> dict[str, Any] | None:
        # Title + link
        title_el = card.select_one("h5 a") or card.select_one(".titulo a") or card.select_one("a")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        link = title_el.get("href", "")
        if link and not link.startswith("http"):
            link = f"{BASE_URL}{link}"

        # Date from ACF field
        date_el = card.select_one("div.value") or card.select_one(".is-acf-field .value")
        event_date = None
        date_str = ""
        if date_el:
            date_text = date_el.get_text(strip=True)
            m = DATE_PATTERN.search(date_text)
            if m:
                try:
                    event_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                    date_str = event_date.isoformat()
                except ValueError:
                    pass

        if not event_date:
            return None

        # Description
        info_el = card.select_one("div.info p") or card.select_one("div.info")
        description = info_el.get_text(strip=True) if info_el else ""

        # Image
        img_el = card.select_one("img")
        image_url = img_el.get("src", "") if img_el else ""

        # Category tags
        cat_el = card.select_one("div.tematica span") or card.select_one(".tematica-superior span")
        category = cat_el.get_text(strip=True) if cat_el else ""

        external_id = _make_external_id(title, date_str)

        return {
            "title": title,
            "start_date": event_date,
            "description": description,
            "detail_url": link,
            "external_id": external_id,
            "image_url": image_url,
            "source_category": category,
        }

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            raw_desc = raw_data.get("description", "")
            detail_url = raw_data.get("detail_url", LISTING_URL)

            parts = []
            if raw_desc:
                parts.append(raw_desc)
            parts.append("Evento de la Secretaría General Iberoamericana (SEGIB).")
            parts.append(
                f'Más información en <a href="{detail_url}" style="color:#2563eb">'
                f"{detail_url}</a>"
            )
            description = "\n\n".join(parts)

            organizer = EventOrganizer(
                name="Secretaría General Iberoamericana (SEGIB)",
                url="https://www.segib.org",
                type="institucion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                description=description,
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=detail_url,
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_slugs=["politica"],
                organizer=organizer,
                is_free=True,
                requires_registration=False,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
