"""CeMIT Galicia adapter - Digital training from Xunta de Galicia.

Source: https://cemit.xunta.gal/es/formacion/formacion-presencial
Tier: Bronze (Drupal site, static HTML)
CCAA: Galicia
Category: tecnologia (digital training courses)

CeMIT (Centro de Modernización e Inclusión Tecnolóxica) offers free
digital training across Galicia. Pagination: ?page=N (0-indexed, ~30 items/page).

Card structure:
    div.activity > div.activity-content
        .activity-name > a (title + link)
        .activity-center > span.center (city) + span.location (province)
        .activity-modality (Presencial/Online)
        .activity-info-date > span.activity-date-day/month/year
        .activity-info-seats > span.seats
        .activity-info-hours > span.hours
"""

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

MONTHS_SHORT_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4,
    "may": 5, "jun": 6, "jul": 7, "ago": 8,
    "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# Province normalization: CeMIT uses "Coruña, A" format
PROVINCE_MAP = {
    "coruña, a": "A Coruña",
    "a coruña": "A Coruña",
    "pontevedra": "Pontevedra",
    "ourense": "Ourense",
    "lugo": "Lugo",
}

BASE_URL = "https://cemit.xunta.gal"


@register_adapter("cemit_galicia")
class CemitGaliciaAdapter(BaseAdapter):
    """Adapter for CeMIT Galicia - Digital training courses."""

    source_id = "cemit_galicia"
    source_name = "CeMIT Galicia - Formación Presencial"
    source_url = "https://cemit.xunta.gal/es/formacion/formacion-presencial"
    ccaa = "Galicia"
    ccaa_code = "GA"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    LISTING_URL = "https://cemit.xunta.gal/es/formacion/formacion-presencial"
    MAX_PAGES = 6

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = False,
        max_events: int = 200,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch training activities from CeMIT with pagination."""
        events = []
        effective_limit = min(max_events, limit) if limit else max_events
        seen_ids = set()

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for page in range(self.MAX_PAGES):
                    url = f"{self.LISTING_URL}?page={page}"
                    self.logger.info("fetching_cemit_page", url=url, page=page)

                    response = await client.get(url)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, "html.parser")
                    cards = soup.find_all("div", class_="activity")

                    if not cards:
                        self.logger.info("no_more_pages", page=page)
                        break

                    page_count = 0
                    for card in cards:
                        event_data = self._parse_card(card)
                        if event_data and event_data["external_id"] not in seen_ids:
                            seen_ids.add(event_data["external_id"])
                            events.append(event_data)
                            page_count += 1

                            if len(events) >= effective_limit:
                                break

                    self.logger.info("cemit_page_parsed", page=page, found=page_count)

                    if len(events) >= effective_limit:
                        break

                    # Check if there's a next page (Drupal pager)
                    next_item = soup.find("li", class_="pager__item--next")
                    if not next_item or not next_item.find("a"):
                        break

            self.logger.info("cemit_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_card(self, card: Any) -> dict[str, Any] | None:
        """Parse a single activity card.

        Structure:
        <div class="activity">
          <div class="activity-content">
            <div class="activity-name"><a href="/es/formacion/...">Title</a></div>
            <div class="activity-center">
              <span class="center">City</span>
              <span class="location">Province</span>
            </div>
            <div class="activity-modality">Presencial</div>
            <div class="activity-info-date">
              <span class="activity-date-day">27</span>
              <span class="activity-date-month">Feb</span>
              <span class="activity-date-year">26</span>
            </div>
            <div class="activity-info-seats"><span class="seats">20</span></div>
            <div class="activity-info-hours"><span class="hours">2</span></div>
          </div>
        </div>
        """
        try:
            # Title and link
            name_div = card.find("div", class_="activity-name")
            if not name_div:
                return None
            link = name_div.find("a")
            if not link:
                return None
            title = link.get_text(strip=True)
            href = link.get("href", "")
            detail_url = f"{BASE_URL}{href}" if href.startswith("/") else href

            # Extract ID from URL
            id_match = re.search(r"/(\d+)$", href)
            external_id = f"cemit_{id_match.group(1)}" if id_match else None

            # City and Province
            center_div = card.find("div", class_="activity-center")
            city = ""
            province_raw = ""
            if center_div:
                city_span = center_div.find("span", class_="center")
                loc_span = center_div.find("span", class_="location")
                city = city_span.get_text(strip=True) if city_span else ""
                province_raw = loc_span.get_text(strip=True).lower() if loc_span else ""

            province = PROVINCE_MAP.get(province_raw, province_raw.title())

            # Modality
            modality_div = card.find("div", class_="activity-modality")
            modality_text = modality_div.get_text(strip=True).lower() if modality_div else "presencial"
            if "online" in modality_text:
                location_type = "online"
            elif "mixta" in modality_text or "híbrida" in modality_text:
                location_type = "hibrido"
            else:
                location_type = "presencial"

            # Date
            start_date = None
            date_div = card.find("div", class_="activity-info-date")
            if date_div:
                day_span = date_div.find("span", class_="activity-date-day")
                month_span = date_div.find("span", class_="activity-date-month")
                year_span = date_div.find("span", class_="activity-date-year")

                if day_span and month_span and year_span:
                    day = int(day_span.get_text(strip=True))
                    month_str = month_span.get_text(strip=True).lower()[:3]
                    year_str = year_span.get_text(strip=True)
                    # Year is 2-digit (e.g., "26")
                    year = int(year_str)
                    if year < 100:
                        year += 2000
                    month = MONTHS_SHORT_ES.get(month_str)
                    if month:
                        start_date = date(year, month, day)

            if not start_date:
                return None

            # Seats
            seats = None
            seats_div = card.find("div", class_="activity-info-seats")
            if seats_div:
                seats_span = seats_div.find("span", class_="seats")
                if seats_span:
                    try:
                        seats = int(seats_span.get_text(strip=True))
                    except ValueError:
                        pass

            # Hours
            hours = None
            hours_div = card.find("div", class_="activity-info-hours")
            if hours_div:
                hours_span = hours_div.find("span", class_="hours")
                if hours_span:
                    try:
                        hours = float(hours_span.get_text(strip=True))
                    except ValueError:
                        pass

            # Activity type (from icon)
            activity_type = None
            type_span = card.find("span", class_=re.compile(r"activity-type-"))
            if type_span:
                classes = type_span.get("class", [])
                for cls in classes:
                    if cls.startswith("activity-type-"):
                        activity_type = cls.replace("activity-type-", "")

            return {
                "title": title,
                "start_date": start_date,
                "city": city,
                "province": province,
                "location_type": location_type,
                "detail_url": detail_url,
                "external_id": external_id or f"cemit_{title}_{start_date.isoformat()}",
                "seats": seats,
                "hours": hours,
                "activity_type": activity_type,
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

            city = raw_data.get("city", "")
            province = raw_data.get("province", "")
            hours = raw_data.get("hours")
            seats = raw_data.get("seats")

            # Build description
            parts = [f"Curso de formación digital del programa CeMIT (Xunta de Galicia)."]
            if hours:
                parts.append(f"Duración: {hours} horas.")
            if seats:
                parts.append(f"Plazas disponibles: {seats}.")
            parts.append("Formación gratuita.")
            parts.append("Más información en https://cemit.xunta.gal")
            description = "\n".join(parts)

            # Location type
            loc_type_str = raw_data.get("location_type", "presencial")
            loc_type = LocationType.PHYSICAL
            if loc_type_str == "online":
                loc_type = LocationType.ONLINE
            elif loc_type_str == "hibrido":
                loc_type = LocationType.HYBRID

            organizer = EventOrganizer(
                name="CeMIT - Xunta de Galicia",
                url="https://cemit.xunta.gal",
                type="institucion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                description=description,
                city=city,
                province=province,
                comunidad_autonoma="Galicia",
                country="España",
                location_type=loc_type,
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                category_slugs=["tecnologia"],
                organizer=organizer,
                is_free=True,
                requires_registration=True,
                registration_info="Inscripción en https://cemit.xunta.gal",
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
