"""ConSaludMental adapter - Mental health events from Confederación Salud Mental España.

Source: https://consaludmental.org/listado-eventos/
API: WordPress REST API (/wp-json/wp/v2/mec-events)
Tier: Bronze (API + HTML content parsing)
CCAA: Nacional (events across all Spain)
Category: sanitaria (mental health)

Uses WordPress REST API for Modern Events Calendar (MEC) plugin.
Dates and locations are parsed from HTML content field.
"""

import asyncio
import re
from datetime import date, time as dt_time
from html import unescape
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

# Month names in Spanish
MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Spanish provinces for location detection
PROVINCES_ES = {
    "A Coruña": ("A Coruña", "Galicia"),
    "Álava": ("Álava", "País Vasco"),
    "Albacete": ("Albacete", "Castilla-La Mancha"),
    "Alicante": ("Alicante", "Comunidad Valenciana"),
    "Almería": ("Almería", "Andalucía"),
    "Asturias": ("Asturias", "Asturias"),
    "Ávila": ("Ávila", "Castilla y León"),
    "Badajoz": ("Badajoz", "Extremadura"),
    "Barcelona": ("Barcelona", "Cataluña"),
    "Burgos": ("Burgos", "Castilla y León"),
    "Cáceres": ("Cáceres", "Extremadura"),
    "Cádiz": ("Cádiz", "Andalucía"),
    "Cantabria": ("Cantabria", "Cantabria"),
    "Castellón": ("Castellón", "Comunidad Valenciana"),
    "Ceuta": ("Ceuta", "Ceuta"),
    "Ciudad Real": ("Ciudad Real", "Castilla-La Mancha"),
    "Córdoba": ("Córdoba", "Andalucía"),
    "Cuenca": ("Cuenca", "Castilla-La Mancha"),
    "Girona": ("Girona", "Cataluña"),
    "Granada": ("Granada", "Andalucía"),
    "Guadalajara": ("Guadalajara", "Castilla-La Mancha"),
    "Guipúzcoa": ("Guipúzcoa", "País Vasco"),
    "Huelva": ("Huelva", "Andalucía"),
    "Huesca": ("Huesca", "Aragón"),
    "Illes Balears": ("Illes Balears", "Illes Balears"),
    "Jaén": ("Jaén", "Andalucía"),
    "La Rioja": ("La Rioja", "La Rioja"),
    "Las Palmas": ("Las Palmas", "Canarias"),
    "León": ("León", "Castilla y León"),
    "Lleida": ("Lleida", "Cataluña"),
    "Lugo": ("Lugo", "Galicia"),
    "Madrid": ("Madrid", "Comunidad de Madrid"),
    "Málaga": ("Málaga", "Andalucía"),
    "Melilla": ("Melilla", "Melilla"),
    "Murcia": ("Murcia", "Región de Murcia"),
    "Navarra": ("Navarra", "Navarra"),
    "Ourense": ("Ourense", "Galicia"),
    "Palencia": ("Palencia", "Castilla y León"),
    "Pontevedra": ("Pontevedra", "Galicia"),
    "Salamanca": ("Salamanca", "Castilla y León"),
    "Santa Cruz de Tenerife": ("Santa Cruz de Tenerife", "Canarias"),
    "Segovia": ("Segovia", "Castilla y León"),
    "Sevilla": ("Sevilla", "Andalucía"),
    "Soria": ("Soria", "Castilla y León"),
    "Tarragona": ("Tarragona", "Cataluña"),
    "Teruel": ("Teruel", "Aragón"),
    "Toledo": ("Toledo", "Castilla-La Mancha"),
    "Valencia": ("Valencia", "Comunidad Valenciana"),
    "Valladolid": ("Valladolid", "Castilla y León"),
    "Vizcaya": ("Vizcaya", "País Vasco"),
    "Zamora": ("Zamora", "Castilla y León"),
    "Zaragoza": ("Zaragoza", "Aragón"),
}

# City to province mapping for common cities
CITY_TO_PROVINCE = {
    "Sevilla": "Sevilla",
    "Granada": "Granada",
    "Málaga": "Málaga",
    "Córdoba": "Córdoba",
    "Burgos": "Burgos",
    "Valladolid": "Valladolid",
    "Salamanca": "Salamanca",
    "Bilbao": "Vizcaya",
    "San Sebastián": "Guipúzcoa",
    "Vitoria": "Álava",
    "Pamplona": "Navarra",
    "Logroño": "La Rioja",
    "Zaragoza": "Zaragoza",
    "Huesca": "Huesca",
    "Teruel": "Teruel",
    "Barcelona": "Barcelona",
    "Tarragona": "Tarragona",
    "Lleida": "Lleida",
    "Girona": "Girona",
    "Valencia": "Valencia",
    "Alicante": "Alicante",
    "Castellón": "Castellón",
    "Murcia": "Murcia",
    "Palma": "Illes Balears",
    "Las Palmas": "Las Palmas",
    "Santa Cruz de Tenerife": "Santa Cruz de Tenerife",
    "Oviedo": "Asturias",
    "Gijón": "Asturias",
    "Santander": "Cantabria",
    "A Coruña": "A Coruña",
    "Santiago de Compostela": "A Coruña",
    "Vigo": "Pontevedra",
    "Pontevedra": "Pontevedra",
    "Ourense": "Ourense",
    "Lugo": "Lugo",
    "Cáceres": "Cáceres",
    "Badajoz": "Badajoz",
    "Mérida": "Badajoz",
    "Toledo": "Toledo",
    "Ciudad Real": "Ciudad Real",
    "Albacete": "Albacete",
    "Cuenca": "Cuenca",
    "Guadalajara": "Guadalajara",
}


@register_adapter("consaludmental")
class ConSaludMentalAdapter(BaseAdapter):
    """Adapter for ConSaludMental - Mental health events across Spain."""

    source_id = "consaludmental"
    source_name = "Confederación Salud Mental España"
    source_url = "https://consaludmental.org/"
    ccaa = "Nacional"
    ccaa_code = "ES"
    province = None  # National scope
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    API_URL = "https://consaludmental.org/wp-json/wp/v2/mec-events"

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = True,
        max_events: int = 100,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch mental health events from WordPress REST API."""
        events = []
        effective_limit = min(max_events, limit) if limit else max_events
        today = date.today()

        try:
            self.logger.info("fetching_consaludmental", limit=effective_limit)

            async with httpx.AsyncClient(timeout=30) as client:
                # Fetch recent events (ordered by date desc)
                page = 1
                per_page = 100
                fetched_count = 0

                while len(events) < effective_limit:
                    response = await client.get(
                        self.API_URL,
                        params={
                            "per_page": per_page,
                            "page": page,
                            "orderby": "date",
                            "order": "desc",
                        },
                    )

                    if response.status_code == 400:
                        # No more pages
                        break

                    response.raise_for_status()
                    data = response.json()

                    if not data:
                        break

                    fetched_count += len(data)

                    for item in data:
                        if len(events) >= effective_limit:
                            break

                        event_data = self._parse_api_event(item)

                        if event_data:
                            # Filter future events only
                            if event_data.get("start_date") and event_data["start_date"] >= today:
                                events.append(event_data)
                            elif not event_data.get("start_date"):
                                # Include events without parseable date (LLM will handle)
                                events.append(event_data)

                    # Check if we've processed enough
                    if fetched_count >= 300:  # Safety limit
                        break

                    page += 1

            self.logger.info(
                "consaludmental_events_found",
                total_fetched=fetched_count,
                future_events=len(events),
            )

            # Fetch detail pages to get organizer info
            if fetch_details and events:
                events = await self._fetch_detail_pages(events)

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    async def _fetch_detail_pages(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fetch detail pages to extract organizer info."""
        semaphore = asyncio.Semaphore(3)  # Limit concurrent requests

        async def fetch_single(event: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                detail_url = event.get("detail_url")
                if not detail_url:
                    return event

                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        response = await client.get(detail_url)
                        if response.status_code == 200:
                            html = response.text
                            # Extract organizer
                            organizer_name = self._extract_organizer(html)
                            if organizer_name:
                                event["organizer_name"] = organizer_name
                            # Extract online URL (YouTube, Zoom, etc.)
                            online_url = self._extract_online_url(html)
                            if online_url:
                                event["online_url"] = online_url
                except Exception as e:
                    self.logger.debug("detail_fetch_error", url=detail_url, error=str(e))

                await asyncio.sleep(0.3)  # Rate limiting
                return event

        # Fetch all detail pages concurrently
        tasks = [fetch_single(event) for event in events]
        results = await asyncio.gather(*tasks)

        self.logger.info("detail_pages_fetched", count=len(results))
        return list(results)

    def _extract_organizer(self, html: str) -> str | None:
        """Extract organizer name from detail page HTML.

        Looks for:
        <div class="mec-single-event-organizer">
            <h6>Organizer Name</h6>
        </div>
        """
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Try MEC organizer div
            organizer_div = soup.select_one(".mec-single-event-organizer")
            if organizer_div:
                h6 = organizer_div.select_one("h6")
                if h6:
                    return h6.get_text(strip=True)

            # Fallback: look for "Organizador" or "Organiza" in text
            text = soup.get_text(" ", strip=True)
            match = re.search(r"Organiza(?:dor)?[:\s]+([A-ZÁÉÍÓÚÑ][^.]{5,60})", text)
            if match:
                return match.group(1).strip()

        except Exception:
            pass

        return None

    def _extract_online_url(self, html: str) -> str | None:
        """Extract online streaming URL from event content.

        Looks for YouTube, Zoom, Teams, or other streaming links
        specifically within the event content area (not header/footer).
        """
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Look for streaming links only in content area
            # MEC uses .mec-single-event for main content
            content_areas = soup.select(".mec-single-event, .entry-content, .wpb-content-wrapper, article")

            streaming_patterns = [
                "youtube.com/channel",
                "youtube.com/watch",
                "youtube.com/@",
                "youtu.be/",
                "zoom.us/j/",
                "zoom.us/my/",
                "teams.microsoft.com",
                "meet.google.com",
                "webex.com",
            ]

            # Skip generic channel links (main site channel)
            skip_patterns = [
                "youtube.com/c/ConfederacionSaludMentalEspana",
                "youtube.com/c/Conf",
            ]

            for area in content_areas:
                for link in area.find_all("a", href=True):
                    href = link.get("href", "")

                    # Skip generic site links
                    if any(skip in href for skip in skip_patterns):
                        continue

                    # Check if it's a streaming link
                    for pattern in streaming_patterns:
                        if pattern in href.lower():
                            return href

        except Exception:
            pass

        return None

    def _parse_api_event(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """Parse event from WordPress REST API response.

        Extracts structured data from API fields and parses
        date/location from HTML content.
        """
        try:
            # Basic fields
            event_id = item.get("id")
            title = item.get("title", {}).get("rendered", "")
            title = unescape(title).replace("&#8216;", "'").replace("&#8217;", "'")
            title = title.replace("«", '"').replace("»", '"')

            link = item.get("link", "")

            # Get content and clean HTML
            content_html = item.get("content", {}).get("rendered", "")
            content_text = self._clean_html(content_html)

            # Parse date from content
            start_date, start_time, end_time = self._parse_date_from_content(content_text)

            # Parse location from content
            location_info = self._parse_location_from_content(content_text)

            # Get image from yoast metadata
            image_url = None
            yoast = item.get("yoast_head_json", {})
            og_images = yoast.get("og_image", [])
            if og_images and len(og_images) > 0:
                image_url = og_images[0].get("url")

            # Get description from yoast or excerpt
            description = yoast.get("description", "")
            if not description:
                excerpt = item.get("excerpt", {}).get("rendered", "")
                description = self._clean_html(excerpt)[:500]

            # Get MEC categories
            mec_categories = item.get("mec_category", [])

            # Detect city from title if "En Ciudad" pattern
            city_from_title = None
            city_match = re.search(r"[Ee]n\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ\s]+)$", title)
            if city_match:
                city_from_title = city_match.group(1).strip()

            # Determine city/province
            city = location_info.get("city") or city_from_title
            province = location_info.get("province")
            ccaa = location_info.get("ccaa")

            # Lookup province/ccaa from city
            if city and not province:
                if city in CITY_TO_PROVINCE:
                    province = CITY_TO_PROVINCE[city]
                    if province in PROVINCES_ES:
                        _, ccaa = PROVINCES_ES[province]

            return {
                "external_id": f"consaludmental_{event_id}",
                "title": title,
                "description": description,
                "full_content": content_text[:2000],  # For LLM enrichment
                "start_date": start_date,
                "start_time": start_time,
                "end_time": end_time,
                "venue_name": location_info.get("venue"),
                "address": location_info.get("address"),
                "city": city,
                "province": province,
                "ccaa": ccaa,
                "detail_url": link,
                "image_url": image_url,
                "mec_categories": mec_categories,
            }

        except Exception as e:
            self.logger.debug("parse_api_event_error", error=str(e))
            return None

    def _clean_html(self, html: str) -> str:
        """Remove HTML tags and clean text."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        # Decode HTML entities
        text = unescape(text)
        # Clean whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove shortcodes
        text = re.sub(r'\[[^\]]+\]', '', text)
        return text

    def _parse_date_from_content(self, text: str) -> tuple[date | None, dt_time | None, dt_time | None]:
        """Extract date and time from content text.

        Common patterns:
        - "Fecha: 16 de febrero de 2026, a las 19:00"
        - "Cuándo: jueves 26 de febrero"
        - "sábado 21 de febrero"
        - "del 9 de febrero al 27 de marzo"
        """
        start_date = None
        start_time = None
        end_time = None

        # Pattern 1: "Fecha: DD de mes de YYYY"
        date_match = re.search(
            r"(?:Fecha|Cuándo|Cuando)[:\s]*(?:\w+\s+)?(\d{1,2})\s+de\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
            r"(?:\s+de\s+(\d{4}))?",
            text,
            re.IGNORECASE,
        )

        if not date_match:
            # Pattern 2: Day of week + date
            date_match = re.search(
                r"(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)\s+"
                r"(\d{1,2})\s+de\s+"
                r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)"
                r"(?:\s+de\s+(\d{4}))?",
                text,
                re.IGNORECASE,
            )

        if date_match:
            day = int(date_match.group(1))
            month = MONTHS_ES.get(date_match.group(2).lower())
            year = int(date_match.group(3)) if date_match.group(3) else date.today().year

            if month:
                # If no year specified, determine if current or next year
                if not date_match.group(3):
                    today = date.today()
                    # Only assume next year if date is more than 2 months in the past
                    # (to avoid marking recent past events as next year)
                    if month < today.month - 2 or (month == today.month - 2 and day < today.day):
                        year += 1
                    # If date is within last 2 months, keep current year (past event)

                try:
                    start_date = date(year, month, day)
                except ValueError:
                    pass

        # Parse time: "a las 19:00" or "17:00 - 19:00" or "17:00-19:00"
        time_match = re.search(r"(\d{1,2}):(\d{2})\s*(?:[-–]\s*(\d{1,2}):(\d{2}))?", text)
        if time_match:
            try:
                start_time = dt_time(int(time_match.group(1)), int(time_match.group(2)))
                if time_match.group(3) and time_match.group(4):
                    end_time = dt_time(int(time_match.group(3)), int(time_match.group(4)))
            except ValueError:
                pass

        return start_date, start_time, end_time

    def _parse_location_from_content(self, text: str) -> dict[str, str | None]:
        """Extract location info from content text.

        Patterns:
        - "Lugar: Venue Name. C/ Address, City"
        - "Dónde: Venue. Address"
        """
        result = {
            "venue": None,
            "address": None,
            "city": None,
            "province": None,
            "ccaa": None,
        }

        # Pattern: "Lugar: ..." or "Dónde: ..."
        loc_match = re.search(
            r"(?:Lugar|Dónde|Donde)[:\s]*([^.]+(?:\.[^.]+)?)",
            text,
            re.IGNORECASE,
        )

        if loc_match:
            location_text = loc_match.group(1).strip()

            # Try to split venue from address
            # Pattern: "Venue Name. C/ Address, City"
            if ". " in location_text:
                parts = location_text.split(". ", 1)
                result["venue"] = parts[0].strip()
                address_part = parts[1].strip() if len(parts) > 1 else ""

                # Extract city from address (usually last part after comma)
                if address_part:
                    # Look for known cities/provinces
                    for city, province in CITY_TO_PROVINCE.items():
                        if city.lower() in address_part.lower():
                            result["city"] = city
                            result["province"] = province
                            if province in PROVINCES_ES:
                                _, result["ccaa"] = PROVINCES_ES[province]
                            break

                    result["address"] = address_part
            else:
                # No clear separation
                result["venue"] = location_text

                # Check for city mentions
                for city, province in CITY_TO_PROVINCE.items():
                    if city.lower() in location_text.lower():
                        result["city"] = city
                        result["province"] = province
                        if province in PROVINCES_ES:
                            _, result["ccaa"] = PROVINCES_ES[province]
                        break

        return result

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")

            if not title:
                return None

            start_date = raw_data.get("start_date")

            # Skip if no date and content doesn't suggest future event
            if not start_date:
                return None

            # Build description
            description = raw_data.get("description", "")

            # Add mental health context
            if description:
                description = f"🧠 **Evento de salud mental**\n\n{description}"

            # Organizer - use extracted name if available
            organizer_name = raw_data.get("organizer_name") or "Confederación Salud Mental España"
            organizer = EventOrganizer(
                name=organizer_name,
                url=None,  # No URL for local organizers
                type="asociacion",
                logo_url=None,  # No logo for local organizers
            )

            # Determine location type based on extracted data
            online_url = raw_data.get("online_url")
            has_physical = raw_data.get("venue_name") or raw_data.get("address")
            full_content = raw_data.get("full_content", "").lower()
            has_online_keywords = "online" in full_content or "youtube" in full_content or "zoom" in full_content or "streaming" in full_content
            has_physical_keywords = "presencial" in full_content or "en persona" in full_content or "sede" in full_content

            # Set location type
            if online_url or has_online_keywords:
                if has_physical or has_physical_keywords:
                    location_type = LocationType.HYBRID
                else:
                    location_type = LocationType.ONLINE
            else:
                location_type = LocationType.PHYSICAL

            return EventCreate(
                title=title,
                start_date=start_date,
                start_time=raw_data.get("start_time"),
                end_time=raw_data.get("end_time"),
                description=description,
                venue_name=raw_data.get("venue_name"),
                address=raw_data.get("address"),
                city=raw_data.get("city"),
                province=raw_data.get("province"),
                comunidad_autonoma=raw_data.get("ccaa"),
                country="España",
                location_type=location_type,
                online_url=online_url,  # YouTube, Zoom, etc.
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_slugs=["sanitaria"],  # Fixed category: mental health
                organizer=organizer,
                is_free=True,  # Most events are free
                requires_registration=True,  # Usually require registration
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e))
            return None
