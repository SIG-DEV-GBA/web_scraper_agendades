"""DonarSangre adapter - Blood donation mobile points.

Source: https://www.donarsangre.org/proximos-puntos-moviles/
Tier: Bronze (HTML scraping)
CCAA: Comunidad de Madrid (primarily)
Category: sanitaria (health/blood donation)

Lists upcoming blood donation points with dates, times, and locations.
"""

import re
from datetime import date, time as dt_time
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

# Default image for blood donation events
DEFAULT_IMAGE = "https://img.freepik.com/vector-gratis/donar-sangre-humana-sobre-fondo-blanco_1308-110922.jpg?semt=ais_user_personalization&w=740&q=80"


@register_adapter("donarsangre")
class DonarSangreAdapter(BaseAdapter):
    """Adapter for DonarSangre - Blood donation mobile points."""

    source_id = "donarsangre"
    source_name = "Donar Sangre - Puntos Móviles"
    source_url = "https://www.donarsangre.org/"
    ccaa = "Comunidad de Madrid"
    ccaa_code = "MD"
    province = "Madrid"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    BASE_URL = "https://www.donarsangre.org"
    LISTING_URL = "https://www.donarsangre.org/proximos-puntos-moviles/"

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = True,
        max_events: int = 100,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch blood donation points from the listing page."""
        events = []
        effective_limit = min(max_events, limit) if limit else max_events

        try:
            self.logger.info("fetching_donarsangre", url=self.LISTING_URL)

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(self.LISTING_URL)
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find all colecta links (each link is inside a div.flow)
            links = soup.find_all("a", href=lambda x: x and "/colecta/" in x)

            for link in links:
                if len(events) >= effective_limit:
                    break

                event_data = self._parse_event_div(link)
                if event_data:
                    events.append(event_data)

            self.logger.info(
                "donarsangre_events_found",
                count=len(events),
            )

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_event_div(self, link: Any) -> dict[str, Any] | None:
        """Parse event from the link and its parent div structure.

        Structure:
        <div class="flow">
          <img .../>
          <h3><a href="/colecta/15686/getafe/24-02-2026/">Getafe</a></h3>
          <p>C. Cipriano Diaz El Herrero</p>
          <p>17:00 - 21:00</p>
        </div>
        """
        try:
            href = link.get("href", "")
            city = link.get_text(strip=True)

            # Extract date from URL: /colecta/15686/getafe/24-02-2026/
            date_match = re.search(r"/(\d{2})-(\d{2})-(\d{4})/?$", href)
            if not date_match:
                return None

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3))
            event_date = date(year, month, day)

            # Skip past events
            if event_date < date.today():
                return None

            # Extract ID from URL
            id_match = re.search(r"/colecta/(\d+)/", href)
            external_id = f"donarsangre_{id_match.group(1)}" if id_match else f"donarsangre_{event_date.isoformat()}_{city}"

            # Get parent div to find address and time
            parent_div = link.find_parent("div", class_="flow")

            address = None
            start_time = None
            end_time = None

            if parent_div:
                # Find all p elements
                paragraphs = parent_div.find_all("p")

                for p in paragraphs:
                    text = p.get_text(strip=True)

                    # Check if it's a time range (HH:MM - HH:MM)
                    time_match = re.match(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", text)
                    if time_match:
                        try:
                            start_time = dt_time(int(time_match.group(1)), int(time_match.group(2)))
                            end_time = dt_time(int(time_match.group(3)), int(time_match.group(4)))
                        except ValueError:
                            pass
                    elif not address and text:
                        # First non-time paragraph is the address
                        address = text

            # Build detail URL
            detail_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

            return {
                "title": f"Donación de Sangre - {city}",
                "start_date": event_date,
                "start_time": start_time,
                "end_time": end_time,
                "city": city,
                "address": address,
                "detail_url": detail_url,
                "external_id": external_id,
            }

        except Exception as e:
            self.logger.debug("parse_item_error", error=str(e))
            return None

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            # Determine province/ccaa from city
            city = raw_data.get("city", "Madrid")
            province = "Madrid"  # Most are in Madrid region
            ccaa = "Comunidad de Madrid"

            # Build description
            description_parts = [
                "🩸 **Punto de donación de sangre**",
                "",
                "Acércate a donar sangre y ayuda a salvar vidas.",
                "",
            ]

            if raw_data.get("address"):
                description_parts.append(f"📍 **Ubicación:** {raw_data['address']}")

            if raw_data.get("start_time") and raw_data.get("end_time"):
                description_parts.append(
                    f"🕐 **Horario:** {raw_data['start_time'].strftime('%H:%M')} - {raw_data['end_time'].strftime('%H:%M')}"
                )

            description_parts.extend([
                "",
                "**Requisitos para donar:**",
                "- Tener entre 18 y 65 años",
                "- Pesar más de 50 kg",
                "- Estar en buen estado de salud",
                "",
                "Más información en [donarsangre.org](https://www.donarsangre.org)",
            ])

            description = "\n".join(description_parts)

            # Organizer
            organizer = EventOrganizer(
                name="Centro de Transfusión de la Comunidad de Madrid",
                url="https://www.donarsangre.org",
                type="institucion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                start_time=raw_data.get("start_time"),
                end_time=raw_data.get("end_time"),
                description=description,
                venue_name=raw_data.get("address"),
                address=raw_data.get("address"),
                city=city,
                province=province,
                comunidad_autonoma=ccaa,
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=DEFAULT_IMAGE,
                category_slugs=["sanitaria"],
                organizer=organizer,
                is_free=True,
                requires_registration=False,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e))
            return None
