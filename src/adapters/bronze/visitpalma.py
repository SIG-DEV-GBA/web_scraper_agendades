"""VisitPalma adapter - Cultural events in Palma de Mallorca.

Source: https://visitpalma.com/es/agenda/
Tier: Bronze (but uses WordPress REST API - The Events Calendar)
CCAA: Illes Balears
Category: cultural (primarily)

Uses The Events Calendar REST API for structured JSON data.
Same API pattern as viveceuta. Website field provides ticket/info links.
"""

import html
import re
from datetime import date, time as dt_time, timedelta
from typing import Any

from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

API_URL = "https://visitpalma.com/wp-json/tribe/events/v1/events"


@register_adapter("visitpalma_agenda")
class VisitPalmaAdapter(BaseAdapter):
    """Adapter for VisitPalma - Cultural events via The Events Calendar API."""

    source_id = "visitpalma_agenda"
    source_name = "Visit Palma - Agenda de Eventos"
    source_url = "https://visitpalma.com/es/agenda/"
    ccaa = "Illes Balears"
    ccaa_code = "IB"
    province = "Illes Balears"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    MAX_EVENTS = 100

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = True,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch events from The Events Calendar REST API."""
        events = []
        effective_limit = min(self.MAX_EVENTS, limit) if limit else self.MAX_EVENTS
        page = 1

        try:
            while len(events) < effective_limit:
                # Fetch from 60 days ago to catch multi-day events still active today
                lookback = (date.today() - timedelta(days=60)).isoformat()
                url = f"{API_URL}?per_page=50&page={page}&start_date={lookback}"
                self.logger.info("fetching_visitpalma", url=url, page=page)

                response = await self.fetch_url(url)
                data = response.json()

                api_events = data.get("events", [])
                if not api_events:
                    break

                for event in api_events:
                    if len(events) >= effective_limit:
                        break
                    # Skip events that already ended
                    end_str = event.get("end_date", "")
                    if end_str:
                        try:
                            end_d = date(*map(int, end_str.split(" ")[0].split("-")))
                            if end_d < date.today():
                                continue
                        except (ValueError, IndexError):
                            pass
                    parsed = self._parse_api_event(event)
                    if parsed:
                        events.append(parsed)

                total_pages = data.get("total_pages", 1)
                if page >= total_pages:
                    break
                page += 1

            self.logger.info("visitpalma_events_found", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_api_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a single event from the API response."""
        try:
            title = html.unescape(event.get("title", "").strip())
            if not title:
                return None

            event_id = event.get("id")
            start_str = event.get("start_date", "")
            end_str = event.get("end_date", "")

            # Parse start date/time
            start_date = None
            start_time = None
            if start_str:
                parts = start_str.split(" ")
                date_parts = parts[0].split("-")
                start_date = date(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
                if len(parts) > 1 and not event.get("all_day"):
                    time_parts = parts[1].split(":")
                    start_time = dt_time(int(time_parts[0]), int(time_parts[1]))

            # Parse end date/time
            end_date = None
            end_time = None
            if end_str:
                parts = end_str.split(" ")
                ed_parts = parts[0].split("-")
                end_date = date(int(ed_parts[0]), int(ed_parts[1]), int(ed_parts[2]))
                if len(parts) > 1 and not event.get("all_day"):
                    time_parts = parts[1].split(":")
                    end_time = dt_time(int(time_parts[0]), int(time_parts[1]))

            # Venue info
            venue = event.get("venue", {}) or {}
            if isinstance(venue, list):
                venue = {}
            venue_name = venue.get("venue")
            address = venue.get("address")
            city = venue.get("city", "Palma")

            # Image
            image = event.get("image", {}) or {}
            image_url = image.get("url")

            # Description - clean HTML
            description_html = event.get("description", "")
            description = ""
            if description_html:
                soup = BeautifulSoup(description_html, "html.parser")
                description = soup.get_text(separator="\n", strip=True)

            # Cost / price
            cost = event.get("cost", "")
            cost_details = event.get("cost_details", {}) or {}
            values = cost_details.get("values", [])

            price = None
            if values:
                try:
                    price = float(values[0])
                except (ValueError, IndexError):
                    pass

            is_free = False
            if price is not None:
                is_free = price == 0
            elif cost:
                cost_lower = cost.lower().strip()
                is_free = cost_lower in ("gratuito", "gratis", "free")

            # Categories from API
            categories = event.get("categories", [])
            cat_names = [c.get("name", "") for c in categories] if isinstance(categories, list) else []

            # Organizer
            organizers = event.get("organizer", [])
            organizer_name = None
            if isinstance(organizers, list) and organizers:
                organizer_name = organizers[0].get("organizer")

            return {
                "title": title,
                "start_date": start_date,
                "end_date": end_date,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "venue_name": venue_name,
                "address": address,
                "city": city or "Palma",
                "image_url": image_url,
                "external_url": event.get("url"),
                "external_id": f"visitpalma_{event_id}" if event_id else None,
                "is_free": is_free,
                "price": price if price and price > 0 else None,
                "price_info": cost if cost else None,
                "website": event.get("website", ""),
                "categories": cat_names,
                "organizer_name": organizer_name,
            }

        except Exception as e:
            self.logger.debug("parse_api_event_error", error=str(e))
            return None

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            organizer = None
            org_name = raw_data.get("organizer_name")
            if org_name:
                organizer = EventOrganizer(
                    name=org_name,
                    url="https://visitpalma.com",
                    type="institucion",
                )

            # Build alternative_dates for multi-day events (exhibitions, etc.)
            end_date = raw_data.get("end_date")
            alternative_dates = None
            if end_date and end_date != start_date:
                all_dates = []
                d = start_date
                while d <= end_date:
                    all_dates.append(d)
                    d += timedelta(days=1)
                alternative_dates = {
                    "dates": [d.isoformat() for d in all_dates],
                    "prices": {},
                }

            # Registration URL from website field (ticket/info links)
            registration_url = raw_data.get("website") or None

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=end_date,
                start_time=raw_data.get("start_time"),
                end_time=raw_data.get("end_time"),
                description=raw_data.get("description", ""),
                venue_name=raw_data.get("venue_name"),
                address=raw_data.get("address"),
                city=raw_data.get("city", "Palma"),
                province="Illes Balears",
                comunidad_autonoma="Illes Balears",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("external_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                organizer=organizer,
                registration_url=registration_url,
                price=raw_data.get("price"),
                price_info=raw_data.get("price_info"),
                is_free=raw_data.get("is_free", False),
                alternative_dates=alternative_dates,
                requires_registration=bool(registration_url),
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e))
            return None
