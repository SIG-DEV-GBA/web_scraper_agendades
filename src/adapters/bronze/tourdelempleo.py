"""Tour del Empleo adapter - University employment fairs in Spain.

Source: https://www.tourdelempleo.com/ferias/
Tier: Bronze (HTML scraping, Elementor/WordPress)
CCAA: (national scope - university fairs across Spain)
Category: economica (employment, career fairs, job market)

Tour del Empleo lists upcoming university employment fairs.
Uses Elementor grid layout with .ue-grid-item cards containing
title, date, description, and links. Single page, no pagination.
"""

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

LISTING_URL = "https://www.tourdelempleo.com/ferias/"

# Date patterns:
# "28 y 29 enero 2026"
# "25 - 26 febrero 2026"
# "10 - 12 marzo 2026"
# "16 y 17 de febrero 2026"
# "19 y 20 de mayo"  (no year)
DATE_RANGE_RE = re.compile(
    r"(\d{1,2})\s*(?:y|-)\s*(\d{1,2})\s+(?:de\s+)?(\w+)\s*(\d{4})?",
    re.IGNORECASE,
)

# Single date: "28 abril 2026"
DATE_SINGLE_RE = re.compile(
    r"(\d{1,2})\s+(?:de\s+)?(\w+)\s+(\d{4})",
    re.IGNORECASE,
)


def _make_external_id(title: str, event_date: date) -> str:
    raw = f"{title.strip().lower()}_{event_date.isoformat()}"
    return f"tourempleo_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


def _extract_city_from_title(title: str) -> str:
    """Try to extract city from university name in title."""
    city_hints = {
        "UAM": "Madrid",
        "UCM": "Madrid",
        "Complutense": "Madrid",
        "Oviedo": "Oviedo",
        "Sevilla": "Sevilla",
        "Pablo de Olavide": "Sevilla",
        "UPO": "Sevilla",
        "Valencia": "Valencia",
        "Barcelona": "Barcelona",
        "Salamanca": "Salamanca",
        "Bilbao": "Bilbao",
        "Málaga": "Málaga",
        "Zaragoza": "Zaragoza",
        "Granada": "Granada",
        "Alicante": "Alicante",
    }
    for hint, city in city_hints.items():
        if hint.lower() in title.lower():
            return city
    return ""


def _parse_date(text: str) -> tuple[date | None, date | None]:
    """Parse date from text, returning (start_date, end_date)."""
    current_year = date.today().year

    # Try range first: "28 y 29 enero 2026" or "10 - 12 marzo 2026"
    m = DATE_RANGE_RE.search(text)
    if m:
        day_start = int(m.group(1))
        day_end = int(m.group(2))
        month_name = m.group(3).lower()
        year = int(m.group(4)) if m.group(4) else current_year
        month = MONTHS_ES.get(month_name)
        if month:
            try:
                return date(year, month, day_start), date(year, month, day_end)
            except ValueError:
                pass

    # Try single date: "28 abril 2026"
    m = DATE_SINGLE_RE.search(text)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = int(m.group(3))
        month = MONTHS_ES.get(month_name)
        if month:
            try:
                d = date(year, month, day)
                return d, d
            except ValueError:
                pass

    return None, None


@register_adapter("tourdelempleo")
class TourDelEmpleoAdapter(BaseAdapter):
    """Adapter for Tour del Empleo - University employment fairs."""

    source_id = "tourdelempleo"
    source_name = "Tour del Empleo - Ferias de Empleo Universitarias"
    source_url = LISTING_URL
    ccaa = ""
    ccaa_code = ""
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    async def fetch_events(
        self,
        enrich: bool = True,
        max_events: int = 200,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch employment fairs from tourdelempleo (single page)."""
        events: list[dict[str, Any]] = []
        effective_limit = min(max_events, limit) if limit else max_events

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                self.logger.info("fetching_tourdelempleo", url=LISTING_URL)

                response = await client.get(LISTING_URL)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Cards: .ue-grid-item with data-link and data-postid
                grid_items = soup.select(".ue-grid-item")

                if not grid_items:
                    self.logger.info("no_grid_items_found")
                    return events

                for item in grid_items:
                    event_data = self._parse_card(item)
                    if event_data:
                        events.append(event_data)
                        if len(events) >= effective_limit:
                            break

            self.logger.info("tourdelempleo_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_card(self, item: Any) -> dict[str, Any] | None:
        """Parse a single Elementor grid item.

        Structure:
        <div class="ue-grid-item" data-link="https://..." data-postid="941">
          <style>... background-image: url("image.jpg") ...</style>
          <h3 class="elementor-heading-title">Title</h3>
          <p class="elementor-heading-title">16 y 17 de febrero 2026</p>
          <span>Description text...</span>
          <a href="...">Más información</a>
        </div>
        """
        try:
            detail_url = item.get("data-link", "")

            # Title: h3.elementor-heading-title
            h3 = item.find("h3", class_="elementor-heading-title")
            title = h3.get_text(strip=True) if h3 else None

            if not title:
                return None

            # Date: p.elementor-heading-title (date is in a <p>, not <h3>)
            date_text = None
            for p in item.find_all("p", class_="elementor-heading-title"):
                text = p.get_text(strip=True)
                if text and any(m in text.lower() for m in MONTHS_ES):
                    date_text = text
                    break

            # Fallback: search all text for date patterns
            if not date_text:
                all_text = item.get_text(" ", strip=True)
                m = DATE_RANGE_RE.search(all_text) or DATE_SINGLE_RE.search(all_text)
                if m:
                    date_text = m.group(0)

            start_date = None
            end_date = None
            if date_text:
                start_date, end_date = _parse_date(date_text)

            if not start_date:
                return None

            # Description from <span> tags with content class
            paragraphs = []
            for span in item.find_all("span", class_=True):
                text = span.get_text(strip=True)
                if text and len(text) > 20 and text != date_text:
                    paragraphs.append(text)
                    if len(paragraphs) >= 3:
                        break

            description = " ".join(paragraphs[:3]) if paragraphs else ""

            # Image from <style> background-image
            image_url = None
            for style in item.find_all("style"):
                style_text = style.string or style.get_text()
                img_match = re.search(r'url\("([^"]+)"\)', style_text)
                if img_match:
                    image_url = img_match.group(1)
                    break

            # "Más información" link
            info_link = None
            for a in item.find_all("a", href=True):
                link_text = a.get_text(strip=True).lower()
                if "información" in link_text:
                    info_link = a["href"]
                    break

            city = _extract_city_from_title(title)

            external_id = _make_external_id(title, start_date)

            return {
                "title": title,
                "start_date": start_date,
                "end_date": end_date,
                "detail_url": detail_url or LISTING_URL,
                "info_url": info_link,
                "description": description,
                "image_url": image_url,
                "city": city,
                "external_id": external_id,
            }

        except Exception as e:
            self.logger.debug("parse_card_error", error=str(e))
            return None

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Convert raw fair data to EventCreate."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            # Build description
            detail_url = raw_data.get("detail_url", LISTING_URL)
            info_url = raw_data.get("info_url")
            parts = []

            desc = raw_data.get("description", "")
            if desc:
                parts.append(desc)

            parts.append("Feria de empleo universitaria organizada por Tour del Empleo.")

            if info_url:
                parts.append(
                    f'Inscripción en <a href="{info_url}" style="color:#2563eb">'
                    f"la web del evento</a>"
                )

            parts.append(
                f'Más información en <a href="{detail_url}" style="color:#2563eb">'
                f"Tour del Empleo</a>"
            )

            description = "\n\n".join(parts)

            organizer = EventOrganizer(
                name="Tour del Empleo",
                url="https://www.tourdelempleo.com",
                type="empresa",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=raw_data.get("end_date"),
                description=description,
                city=raw_data.get("city", ""),
                province="",
                comunidad_autonoma="",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=detail_url,
                registration_url=info_url or detail_url,
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_slugs=["economica"],
                organizer=organizer,
                is_free=False,
                requires_registration=True,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
