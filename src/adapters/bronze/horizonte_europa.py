"""Horizonte Europa adapter - EU research & innovation events.

Source: https://horizonteeuropa.es/eventos
Tier: Bronze (static HTML, Drupal)
Category: politica (EU institutional/policy events)

Horizonte Europa is the Spanish portal for EU's Horizon Europe programme.
Publishes events about EU research funding, policy, and innovation.

Drupal site with well-structured HTML. Pagination via ?page=N.

Page structure:
  div.pagina-eventos.view-listado-de-eventos
    div.view-content
      div.fila-pagina-eventos.views-row
        div.evento-wrapper
          div.tematica
            img — event image
            span — category tags
          div.contenido-evento
            div.tematica-superior > span — category
            div.titulo > a — title + link
            div.fecha > time[datetime] — ISO date (may have range with 2 times)
            div.direccion — location
            div.info > p — description
"""

import asyncio
import hashlib
from datetime import date, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://horizonteeuropa.es"
LISTING_URL = f"{BASE_URL}/eventos"

MAX_PAGES = 5


def _make_external_id(title: str, date_str: str) -> str:
    raw = f"{title.strip().lower()[:80]}_{date_str}"
    return f"heuropa_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


@register_adapter("horizonte_europa")
class HorizonteEuropaAdapter(BaseAdapter):
    """Adapter for Horizonte Europa - EU research & innovation events."""

    source_id = "horizonte_europa"
    source_name = "Horizonte Europa"
    source_url = LISTING_URL
    ccaa = ""  # National/EU scope
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
                for page_num in range(MAX_PAGES):
                    url = LISTING_URL if page_num == 0 else f"{LISTING_URL}?page={page_num}"
                    self.logger.info("fetching_heuropa_page", url=url, page=page_num)

                    try:
                        response = await client.get(url)
                        if response.status_code == 404:
                            self.logger.info("heuropa_pagination_end", page=page_num)
                            break
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        self.logger.warning(
                            "page_fetch_error", page=page_num,
                            status=e.response.status_code,
                        )
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

                    self.logger.info(
                        "heuropa_page_parsed", page=page_num, found=len(page_events),
                    )

                    if len(events) >= effective_limit:
                        break

                    # Check if there's a next page
                    soup = BeautifulSoup(response.text, "html.parser")
                    next_link = soup.select_one("li.pager__item--next a")
                    if not next_link:
                        break

                    await asyncio.sleep(0.5)

            self.logger.info("heuropa_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_listing(self, html: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        soup = BeautifulSoup(html, "html.parser")

        # Find the events view container
        container = soup.select_one("div.pagina-eventos.view-listado-de-eventos")
        if not container:
            container = soup

        cards = container.select("div.fila-pagina-eventos.views-row")
        if not cards:
            cards = container.select("div.evento-wrapper")

        for card in cards:
            try:
                ev = self._parse_card(card)
                if ev:
                    events.append(ev)
            except Exception as e:
                self.logger.warning("card_parse_error", error=str(e))

        return events

    def _parse_card(self, card) -> dict[str, Any] | None:
        # Get the wrapper if we selected the outer row
        wrapper = card.select_one("div.evento-wrapper") or card

        # Title + link
        title_el = wrapper.select_one("div.titulo a")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None
        link = title_el.get("href", "")
        if link and not link.startswith("http"):
            link = f"{BASE_URL}{link}"

        # Date from <time datetime="...">
        event_date = None
        end_date = None
        date_str = ""
        fecha_div = wrapper.select_one("div.fecha")
        if fecha_div:
            time_els = fecha_div.select("time[datetime]")
            if time_els:
                dt_str = time_els[0].get("datetime", "")
                event_date = self._parse_iso_date(dt_str)
                if event_date:
                    date_str = event_date.isoformat()
                # End date if range
                if len(time_els) > 1:
                    end_dt_str = time_els[1].get("datetime", "")
                    end_date = self._parse_iso_date(end_dt_str)

        if not event_date:
            return None

        # Location
        location = ""
        dir_el = wrapper.select_one("div.direccion")
        if dir_el:
            # Remove the icon <i> tag
            for i_tag in dir_el.select("i"):
                i_tag.decompose()
            location = dir_el.get_text(strip=True)

        # Description
        description = ""
        info_el = wrapper.select_one("div.info p") or wrapper.select_one("div.info")
        if info_el:
            description = info_el.get_text(strip=True)

        # Image
        img_el = wrapper.select_one("div.tematica img")
        image_url = ""
        if img_el:
            src = img_el.get("src", "")
            image_url = f"{BASE_URL}{src}" if src and not src.startswith("http") else src

        # Category
        cat_el = wrapper.select_one("div.tematica-superior span")
        category = cat_el.get_text(strip=True) if cat_el else ""

        # Detect if online
        location_type = "online" if self._is_online(location) else "physical"

        external_id = _make_external_id(title, date_str)

        return {
            "title": title,
            "start_date": event_date,
            "end_date": end_date,
            "description": description,
            "location": location,
            "location_type": location_type,
            "detail_url": link,
            "external_id": external_id,
            "image_url": image_url,
            "source_category": category,
        }

    @staticmethod
    def _parse_iso_date(dt_str: str) -> date | None:
        """Parse ISO datetime string like '2026-03-02T12:00:00Z'."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).date()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_online(location: str) -> bool:
        if not location:
            return False
        lower = location.lower().strip()
        return lower in ("online", "en línea", "virtual", "webinar")

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            raw_desc = raw_data.get("description", "")
            detail_url = raw_data.get("detail_url", LISTING_URL)
            location = raw_data.get("location", "")

            parts = []
            if raw_desc:
                parts.append(raw_desc)
            if raw_data.get("source_category"):
                parts.append(f"Área: {raw_data['source_category']}")
            parts.append("Evento de Horizonte Europa (Programa europeo de I+D+i).")
            parts.append(
                f'Más información en <a href="{detail_url}" style="color:#2563eb">'
                f"{detail_url}</a>"
            )
            description = "\n\n".join(parts)

            loc_type = (
                LocationType.ONLINE
                if raw_data.get("location_type") == "online"
                else LocationType.PHYSICAL
            )

            organizer = EventOrganizer(
                name="Horizonte Europa (FECYT/CDTI)",
                url="https://horizonteeuropa.es",
                type="institucion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=raw_data.get("end_date"),
                description=description,
                location_name=location if location else None,
                country="España",
                location_type=loc_type,
                external_url=detail_url,
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_slugs=["politica"],
                organizer=organizer,
                is_free=True,
                requires_registration=True,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
