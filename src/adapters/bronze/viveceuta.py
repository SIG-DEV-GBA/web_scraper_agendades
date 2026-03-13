"""ViveCeuta adapter - Cultural events in Ceuta.

Source: https://viveceuta.es/
Tier: Bronze (but uses WordPress REST API - The Events Calendar)
CCAA: Ceuta
Category: cultural (primarily)

Uses The Events Calendar REST API for structured JSON data.
Resolves missing venue addresses via Tavily web search.
"""

import os
import re
from datetime import date, time as dt_time, timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

API_URL = "https://viveceuta.es/wp-json/tribe/events/v1/events"

# Cache for venue address lookups (venue_name -> address)
_venue_address_cache: dict[str, str | None] = {}


def _resolve_venue_address(venue_name: str, city: str) -> str | None:
    """Search for a venue's real address using Tavily web search."""
    cache_key = f"{venue_name}|{city}"
    if cache_key in _venue_address_cache:
        return _venue_address_cache[cache_key]

    tavily_key = os.getenv("TAVILY_API_KEY", "").split(";")[0].strip()
    if not tavily_key:
        _venue_address_cache[cache_key] = None
        return None

    # Regex: Spanish street patterns (case-insensitive)
    _ADDR_RE = re.compile(
        r"(?:(?:[Cc]alle|C/|[Pp]laza|Pl\.|[Aa]vda\.?|[Aa]venida|[Pp]aseo|Pº)"
        r"\s+[^;,\n\.\)]{3,60})",
    )

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": tavily_key,
                "query": f"{venue_name} {city} direccion",
                "max_results": 3,
                "include_answer": True,
            },
            timeout=10,
        )
        data = resp.json()

        # Collect all text to search: answer first, then results
        texts = []
        answer = data.get("answer", "")
        if answer:
            texts.append(answer)
        for result in data.get("results", []):
            texts.append(result.get("content", ""))

        # Search for address pattern in all texts
        for text in texts:
            match = _ADDR_RE.search(text)
            if match:
                address = match.group(0).strip().rstrip(".")
                logger.info("venue_address_resolved", venue=venue_name, address=address)
                _venue_address_cache[cache_key] = address
                return address

        # Fallback: Tavily answer often says "located at/on X"
        if answer:
            loc_match = re.search(
                r"(?:located (?:at|on)|ubicad[oa] en|direcci[oó]n[:\s]+)\s*([^.]{5,80})",
                answer,
                re.IGNORECASE,
            )
            if loc_match:
                address = loc_match.group(1).strip().rstrip(",")
                logger.info("venue_address_from_answer", venue=venue_name, address=address)
                _venue_address_cache[cache_key] = address
                return address

    except Exception as e:
        logger.debug("venue_address_lookup_failed", venue=venue_name, error=str(e))

    _venue_address_cache[cache_key] = None
    return None


@register_adapter("viveceuta")
class ViveCeutaAdapter(BaseAdapter):
    """Adapter for ViveCeuta - Cultural events via The Events Calendar API."""

    source_id = "viveceuta"
    source_name = "Vive Ceuta - Agenda Cultural"
    source_url = "https://viveceuta.es/"
    ccaa = "Ceuta"
    ccaa_code = "CE"
    province = "Ceuta"
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
                self.logger.info("fetching_viveceuta", url=url, page=page)

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
                        # Resolve address via Tavily if venue has no address
                        self._resolve_address(parsed)
                        events.append(parsed)

                total_pages = data.get("total_pages", 1)
                if page >= total_pages:
                    break
                page += 1

            self.logger.info("viveceuta_events_found", count=len(events))

            # Fetch ticket links from detail pages
            if fetch_details and events:
                await self._fetch_ticket_links(events)

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    async def _fetch_ticket_links(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages to extract ticket purchase links.

        Each event detail page has a main section (data-id=3fd2213) with the
        event-specific "Comprar entradas" button, plus a carousel section
        (data-id=4142aab) with other events' buttons. We only grab the main one.
        """
        for i, event in enumerate(events):
            detail_url = event.get("external_url")
            if not detail_url:
                continue
            try:
                response = await self.fetch_url(detail_url)
                soup = BeautifulSoup(response.text, "html.parser")
                # Main event section ticket link (not the carousel)
                main_section = soup.select_one('[data-id="3fd2213"]')
                if main_section:
                    btn = main_section.select_one(".buy-tickets a[href]")
                    if btn:
                        event["ticket_url"] = btn["href"]
                        self.logger.debug("ticket_link_found", title=event.get("title", "")[:30], url=btn["href"][:60])
            except Exception as e:
                self.logger.debug("ticket_fetch_error", idx=i, error=str(e)[:50])

    def _resolve_address(self, event_data: dict[str, Any]) -> None:
        """Resolve missing address via Tavily web search."""
        venue_name = event_data.get("venue_name")
        address = event_data.get("address")
        city = event_data.get("city", "Ceuta")

        if venue_name and not address:
            resolved = _resolve_venue_address(venue_name, city or "Ceuta")
            if resolved:
                event_data["address"] = resolved
            else:
                # No address found — keep venue_name for display, skip geocoding
                event_data["address"] = venue_name
                event_data["venue_name"] = None

    def _parse_api_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a single event from the API response."""
        try:
            title = event.get("title", "").strip()
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

            # Venue info (may be corrected later by _enrich_from_detail)
            venue = event.get("venue", {}) or {}
            venue_name = venue.get("venue")
            address = venue.get("address")
            city = venue.get("city", "Ceuta")

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
                "city": city or "Ceuta",
                "image_url": image_url,
                "external_url": event.get("url"),
                "external_id": f"viveceuta_{event_id}" if event_id else None,
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
                    url="https://viveceuta.es",
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

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=end_date,
                start_time=raw_data.get("start_time"),
                end_time=raw_data.get("end_time"),
                description=raw_data.get("description", ""),
                venue_name=raw_data.get("venue_name"),
                address=raw_data.get("address"),
                city=raw_data.get("city", "Ceuta"),
                province="Ceuta",
                comunidad_autonoma="Ceuta",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("external_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                organizer=organizer,
                registration_url=raw_data.get("ticket_url") or raw_data.get("website") or None,
                price=raw_data.get("price"),
                price_info=raw_data.get("price_info"),
                is_free=raw_data.get("is_free", False),
                alternative_dates=alternative_dates,
                requires_registration=bool(raw_data.get("ticket_url")),
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e))
            return None
