"""Puntos Vuela adapter - Digital activities from Andalucía.

Source: https://puntosvuela.es/actividades
Tier: Bronze (Laravel, AJAX pagination with HTML response)
CCAA: Andalucía (8 provinces)
Category: tecnologia (digital inclusion)

Puntos Vuela (rebranded Guadalinfo) offers free digital training
across Andalucía. Activities are loaded via AJAX with X-Requested-With header.

Card structure (AJAX response):
    div.card.card-event
        a > img.card-img-top (image)
        a.card-body (link to detail)
            h5.card-title (title)
            p > span (location: "City (Province)")
            p > span (date: "día, DD de month, YYYY")
            p.card-text (short description)
"""

import asyncio
import re
from datetime import date, time
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

# Province mapping for Andalucía
ANDALUCIA_PROVINCES = {
    "almería", "cádiz", "córdoba", "granada",
    "huelva", "jaén", "málaga", "sevilla",
}

# Date pattern: "lun., 23 de febrero, 2026" or "jue., 26 de febrero, 2026"
DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+de\s+(\w+),?\s+(\d{4})",
    re.IGNORECASE,
)

# Detail page date+time: "lunes, 23 de febrero del 2026 a las 07:00"
DETAIL_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+de\s+(\w+)\s+del?\s+(\d{4})\s+a\s+las\s+(\d{1,2}:\d{2})",
    re.IGNORECASE,
)

# Coordinates from Google Maps link: q=lat,lon
COORDS_PATTERN = re.compile(r"q=([-\d.]+),([-\d.]+)")

# Location pattern: "City (Province)"
LOCATION_PATTERN = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")


@register_adapter("puntos_vuela")
class PuntosVuelaAdapter(BaseAdapter):
    """Adapter for Puntos Vuela - Andalucía digital activities."""

    source_id = "puntos_vuela"
    source_name = "Puntos Vuela - Andalucía"
    source_url = "https://puntosvuela.es/actividades"
    ccaa = "Andalucía"
    ccaa_code = "AN"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    LISTING_URL = "https://puntosvuela.es/actividades"
    MAX_PAGES = 50  # 212 pages exist, but cap for safety

    async def _fetch_detail(
        self, client: httpx.AsyncClient, detail_url: str,
    ) -> dict[str, Any]:
        """Fetch detail page and extract sessions, venue, address, coords."""
        result: dict[str, Any] = {}
        try:
            resp = await client.get(
                detail_url,
                headers={"X-Requested-With": ""},  # override AJAX header
            )
            resp.raise_for_status()
        except Exception as e:
            self.logger.debug("detail_fetch_error", url=detail_url, error=str(e))
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        # --- Sessions (dates + times) ---
        sessions_div = soup.find("div", class_="activity-sessions")
        if sessions_div:
            parsed_sessions: list[tuple[date, time | None]] = []
            for p in sessions_div.find_all("p"):
                m = DETAIL_DATE_PATTERN.search(p.get_text())
                if not m:
                    continue
                day = int(m.group(1))
                month = MONTHS_ES.get(m.group(2).lower())
                year = int(m.group(3))
                h, mn = m.group(4).split(":")
                if month:
                    try:
                        d = date(year, month, day)
                        t = time(int(h), int(mn))
                        parsed_sessions.append((d, t))
                    except ValueError:
                        pass

            if parsed_sessions:
                result["start_date"] = parsed_sessions[0][0]
                result["start_time"] = parsed_sessions[0][1]
                if len(parsed_sessions) > 1:
                    result["end_date"] = parsed_sessions[-1][0]
                    result["alternative_dates"] = {
                        "dates": [s[0].isoformat() for s in parsed_sessions],
                    }

        # --- Organizer / Venue / Address / Coords ---
        for details_div in soup.find_all("div", class_="event-details"):
            center_link = details_div.find("a", class_="center-link")
            if center_link:
                # Normalize whitespace (source has huge gaps like "Punto Vuela    CITY")
                name = " ".join(center_link.get_text(strip=True).split())
                result["venue_name"] = name

            maps_link = details_div.find("a", class_="maps-link")
            if maps_link:
                result["address"] = maps_link.get_text(strip=True)
                href = maps_link.get("href", "")
                coord_match = COORDS_PATTERN.search(href)
                if coord_match:
                    result["latitude"] = float(coord_match.group(1))
                    result["longitude"] = float(coord_match.group(2))

        return result

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = True,
        max_events: int = 200,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch activities from Puntos Vuela with ?off=N pagination."""
        events = []
        effective_limit = min(max_events, limit) if limit else max_events
        seen_ids = set()

        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "text/html, */*; q=0.01",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        try:
            async with httpx.AsyncClient(
                timeout=30,
                follow_redirects=True,
                verify=False,
                headers=headers,
            ) as client:
                for page in range(1, self.MAX_PAGES + 1):
                    # Pagination uses ?off=N (1-indexed, page 1 has no param)
                    params = {"off": page} if page > 1 else {}
                    self.logger.info("fetching_puntos_vuela_page", url=self.LISTING_URL, page=page)

                    try:
                        response = await client.get(self.LISTING_URL, params=params)
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        self.logger.warning("page_error", page=page, status=e.response.status_code)
                        break

                    soup = BeautifulSoup(response.text, "html.parser")
                    cards = soup.find_all("div", class_="card-event")

                    if not cards:
                        self.logger.info("no_more_pages", page=page)
                        break

                    page_count = 0
                    for card in cards:
                        event_data = self._parse_card(card)
                        if event_data and event_data["external_id"] not in seen_ids:
                            seen_ids.add(event_data["external_id"])

                            # Fetch detail page for sessions, venue, coords
                            if fetch_details and event_data.get("detail_url"):
                                await asyncio.sleep(0.3)
                                detail = await self._fetch_detail(
                                    client, event_data["detail_url"],
                                )
                                event_data.update(detail)

                            events.append(event_data)
                            page_count += 1

                            if len(events) >= effective_limit:
                                break

                    self.logger.info("puntos_vuela_page_parsed", page=page, found=page_count)

                    if len(events) >= effective_limit:
                        break

                    # If no new unique events found, pagination exhausted
                    if page_count == 0:
                        break

            self.logger.info("puntos_vuela_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_card(self, card: Any) -> dict[str, Any] | None:
        """Parse a single activity card.

        Structure:
        <div class="card card-event h-100 relative">
            <a href="https://puntosvuela.es/actividades/373779">
                <img src="..." class="card-img-top" alt="...">
            </a>
            <a class="card-body" href="...">
                <h5 class="card-title lh-base">Title</h5>
                <p class='d-block'><span>City (Province)</span></p>
                <p><span>jue., 26 de febrero, 2026</span></p>
                <p class="card-text">Short description...</p>
            </a>
        </div>
        """
        try:
            # Title and link
            body_link = card.find("a", class_="card-body")
            if not body_link:
                return None

            title_h5 = body_link.find("h5", class_="card-title")
            title = title_h5.get_text(strip=True) if title_h5 else None
            if not title:
                return None

            detail_url = body_link.get("href", "")

            # Extract activity ID from URL
            id_match = re.search(r"/actividades/(\d+)", detail_url)
            activity_id = id_match.group(1) if id_match else None
            external_id = f"puntos_vuela_{activity_id}" if activity_id else None

            # Image
            img_link = card.find("a", href=re.compile(r"/actividades/\d+"))
            image_url = None
            if img_link:
                img_tag = img_link.find("img", class_="card-img-top")
                if img_tag:
                    image_url = img_tag.get("src")

            # Location and date from paragraphs
            paragraphs = body_link.find_all("p")
            city = ""
            province = ""
            start_date = None
            description = ""

            for p in paragraphs:
                text = p.get_text(strip=True)

                # Check for location: "City (Province)"
                loc_match = LOCATION_PATTERN.match(text)
                if loc_match:
                    city = loc_match.group(1).strip()
                    province = loc_match.group(2).strip()
                    continue

                # Check for date
                date_match = DATE_PATTERN.search(text)
                if date_match and not start_date:
                    day = int(date_match.group(1))
                    month_name = date_match.group(2).lower()
                    year = int(date_match.group(3))
                    month = MONTHS_ES.get(month_name)
                    if month:
                        try:
                            start_date = date(year, month, day)
                        except ValueError:
                            pass
                    continue

                # Description (card-text)
                if "card-text" in (p.get("class") or []):
                    description = text

            if not start_date:
                return None

            return {
                "title": title,
                "start_date": start_date,
                "city": city,
                "province": province,
                "detail_url": detail_url,
                "external_id": external_id or f"puntos_vuela_{title}_{start_date.isoformat()}",
                "image_url": image_url,
                "description": description,
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

            # Build description with HTML links
            detail_url = raw_data.get("detail_url", "https://puntosvuela.es")
            short_desc = raw_data.get("description", "")
            parts = []
            if short_desc:
                parts.append(short_desc)
            parts.append("Actividad gratuita de la red Puntos Vuela (Andalucía).")
            parts.append(
                f'Más información en <a href="{detail_url}" style="color:#2563eb">{detail_url}</a>'
            )
            description = "\n\n".join(parts)

            # Organizer: use venue name from detail if available
            venue_name = raw_data.get("venue_name")
            organizer_name = venue_name or "Puntos Vuela - Consorcio Andalucía"

            organizer = EventOrganizer(
                name=organizer_name,
                url="https://puntosvuela.es",
                type="institucion",
            )

            registration_url = detail_url if detail_url != "https://puntosvuela.es" else None
            registration_info = (
                f'Inscripción en <a href="{detail_url}" style="color:#2563eb">{detail_url}</a>'
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                start_time=raw_data.get("start_time"),
                end_date=raw_data.get("end_date"),
                alternative_dates=raw_data.get("alternative_dates"),
                description=description,
                city=city,
                province=province,
                comunidad_autonoma="Andalucía",
                country="España",
                location_type=LocationType.PHYSICAL,
                venue_name=venue_name,
                address=raw_data.get("address"),
                latitude=raw_data.get("latitude"),
                longitude=raw_data.get("longitude"),
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=None,
                category_slugs=["tecnologia"],
                organizer=organizer,
                is_free=True,
                requires_registration=True,
                registration_url=registration_url,
                registration_info=registration_info,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
