"""Turismo Región de Murcia adapter - Cultural events in Murcia region.

Source: https://www.turismoregiondemurcia.es/es/agenda/
Tier: Bronze (HTML scraping, no API)
CCAA: Región de Murcia
Category: cultural (primarily)

Custom HTML portal with pagination (20 events/page, pagina=1,21,41...).
Detail pages provide full description, venue address, schedule and price.
"""

import re
from datetime import date, time as dt_time, timedelta
from typing import Any

from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger
from src.utils.date_parser import MONTHS_ES

logger = get_logger(__name__)

BASE_URL = "https://www.turismoregiondemurcia.es"
LISTING_URL = "https://www.turismoregiondemurcia.es/es/agenda/?buscar=si&orden=fecha"

# Short month names used in listing (e.g. "30 SEP", "02 DIC")
_SHORT_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


def _parse_date_range(text: str) -> tuple[date | None, date | None]:
    """Parse date range like '26 FEB 2026 - 24 ABR 2026' or '30 SEP - 02 DIC'."""
    text = text.strip()
    today = date.today()

    # Pattern: DD MON YYYY - DD MON YYYY
    m = re.match(
        r"(\d{1,2})\s+(\w{3})\s+(\d{4})\s*-\s*(\d{1,2})\s+(\w{3})\s+(\d{4})",
        text, re.IGNORECASE,
    )
    if m:
        try:
            sd = date(int(m.group(3)), _SHORT_MONTHS[m.group(2).lower()], int(m.group(1)))
            ed = date(int(m.group(6)), _SHORT_MONTHS[m.group(5).lower()], int(m.group(4)))
            return sd, ed
        except (KeyError, ValueError):
            pass

    # Pattern: DD MON YYYY (single date)
    m = re.match(r"(\d{1,2})\s+(\w{3})\s+(\d{4})$", text, re.IGNORECASE)
    if m:
        try:
            sd = date(int(m.group(3)), _SHORT_MONTHS[m.group(2).lower()], int(m.group(1)))
            return sd, sd
        except (KeyError, ValueError):
            pass

    # Pattern: DD MON - DD MON (no year, infer current/next)
    m = re.match(
        r"(\d{1,2})\s+(\w{3})\s*-\s*(\d{1,2})\s+(\w{3})",
        text, re.IGNORECASE,
    )
    if m:
        try:
            sm = _SHORT_MONTHS[m.group(2).lower()]
            em = _SHORT_MONTHS[m.group(4).lower()]
            sy = today.year if sm >= today.month - 1 else today.year + 1
            ey = sy if em >= sm else sy + 1
            sd = date(sy, sm, int(m.group(1)))
            ed = date(ey, em, int(m.group(3)))
            return sd, ed
        except (KeyError, ValueError):
            pass

    return None, None


@register_adapter("turismo_murcia")
class TurismoMurciaAdapter(BaseAdapter):
    """Adapter for Turismo Región de Murcia - Agenda de eventos."""

    source_id = "turismo_murcia"
    source_name = "Turismo Región de Murcia - Agenda"
    source_url = "https://www.turismoregiondemurcia.es/es/agenda/"
    ccaa = "Región de Murcia"
    ccaa_code = "MC"
    province = "Murcia"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    MAX_EVENTS = 200
    EVENTS_PER_PAGE = 20
    MAX_PAGES = 10

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = True,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch events from listing pages, then optionally fetch details."""
        events = []
        seen_urls = set()
        effective_limit = min(self.MAX_EVENTS, limit) if limit else self.MAX_EVENTS

        try:
            for page_num in range(self.MAX_PAGES):
                pagina = 1 + page_num * self.EVENTS_PER_PAGE
                url = f"{LISTING_URL}&pagina={pagina}"
                self.logger.info("fetching_turismo_murcia", url=url, page=page_num + 1)

                response = await self.fetch_url(url)
                soup = BeautifulSoup(response.text, "html.parser")

                cards = soup.select(".resultado-card")
                if not cards:
                    break

                for card in cards:
                    parsed = self._parse_card(card)
                    if parsed and parsed["detail_url"] not in seen_urls:
                        seen_urls.add(parsed["detail_url"])
                        events.append(parsed)

                        if len(events) >= effective_limit:
                            break

                if len(events) >= effective_limit or len(cards) < self.EVENTS_PER_PAGE:
                    break

            self.logger.info("turismo_murcia_cards_found", count=len(events))

            # Fetch detail pages for full data
            if fetch_details and events:
                await self._fetch_details(events)

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_card(self, card: BeautifulSoup) -> dict[str, Any] | None:
        """Parse a listing card (.resultado-card)."""
        try:
            # Title
            h6 = card.select_one("h6")
            if not h6:
                return None
            title = h6.get_text(strip=True)
            if not title:
                return None

            # Link - find in parent col
            parent_col = card.find_parent("div", class_="col-md-3") or card.find_parent("a")
            link_elem = None
            if parent_col:
                link_elem = parent_col.find("a", href=lambda h: h and "/evento/" in h)
            if not link_elem:
                # Try sibling or wrapper
                link_elem = card.find("a", href=lambda h: h and "/evento/" in h)
            if not link_elem:
                return None

            href = link_elem.get("href", "")
            detail_url = href if href.startswith("http") else BASE_URL + href

            # Image
            img = card.select_one("img")
            image_url = None
            if img:
                src = img.get("src", "")
                if src:
                    image_url = src if src.startswith("http") else BASE_URL + src

            # City and dates from <p> elements
            ps = card.select("p")
            city = ""
            date_text = ""
            for p in ps:
                text = p.get_text(strip=True)
                classes = " ".join(p.get("class", []))
                if "fw-semibold" in classes and "text-muted" not in classes and text:
                    city = text
                elif "text-muted" in classes and re.search(r"\d{1,2}\s+\w{3}", text):
                    date_text = text

            # Parse dates
            start_date, end_date = _parse_date_range(date_text)

            # External ID from URL
            slug = detail_url.rstrip("/").split("/")[-1]
            external_id = f"turismo_murcia_{slug}"

            return {
                "title": title,
                "detail_url": detail_url,
                "image_url": image_url,
                "city": city or "Murcia",
                "start_date": start_date,
                "end_date": end_date,
                "external_id": external_id,
            }

        except Exception as e:
            self.logger.debug("card_parse_error", error=str(e))
            return None

    async def _fetch_details(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages to enrich events with description, venue, etc."""
        for i, event in enumerate(events):
            detail_url = event.get("detail_url")
            if not detail_url:
                continue
            try:
                self.logger.info("fetching_detail", idx=f"{i + 1}/{len(events)}")
                response = await self.fetch_url(detail_url)
                details = self._parse_detail_page(response.text)
                event.update(details)
            except Exception as e:
                self.logger.debug("detail_fetch_error", idx=i, error=str(e)[:50])

    def _parse_detail_page(self, html: str) -> dict[str, Any]:
        """Parse a detail page for description, venue, schedule, price."""
        details: dict[str, Any] = {}
        soup = BeautifulSoup(html, "html.parser")

        # Title
        h1 = soup.select_one("h1")
        if h1:
            details["detail_title"] = h1.get_text(strip=True)

        # Date from h5 (e.g. "26 FEB 2026 - 24 ABR 2026")
        for h5 in soup.select("h5.fw-semibold"):
            text = h5.get_text(strip=True)
            if re.search(r"\d{1,2}\s+\w{3}\s+\d{4}", text):
                sd, ed = _parse_date_range(text)
                if sd:
                    details["detail_start_date"] = sd
                if ed:
                    details["detail_end_date"] = ed
                break

        # Venue + address from div.my-4 > p.text-muted
        venue_div = soup.select_one("div.my-4")
        if venue_div:
            venue_p = venue_div.select_one("p.text-muted")
            if venue_p:
                # Text has venue name + address + city concatenated
                lines = [line.strip() for line in venue_p.stripped_strings]
                if lines:
                    details["venue_name"] = lines[0] if lines else None
                    details["address"] = lines[1] if len(lines) > 1 else None
                    details["detail_city"] = lines[2] if len(lines) > 2 else None

        # Sections by h5 headers
        sections = {}
        for h5 in soup.select("h5.fw-semibold"):
            title = h5.get_text(strip=True).lower().rstrip(":")
            # Get next sibling content
            sibling = h5.find_next_sibling()
            if sibling:
                sections[title] = sibling.get_text(strip=True)

        # Description from "información" section
        info = sections.get("información", "")
        if info:
            details["description"] = info[:2000]

        # Schedule from "horario" section
        schedule = sections.get("horario", "")
        if schedule:
            details["schedule"] = schedule[:500]
            # Try to extract time
            time_match = re.search(r"(\d{1,2})[.:h](\d{2})", schedule)
            if time_match:
                try:
                    details["start_time"] = dt_time(int(time_match.group(1)), int(time_match.group(2)))
                except ValueError:
                    pass

        # Price from "precio" section
        precio = sections.get("precio", "")
        if precio:
            details["price_info"] = precio[:200]
            price_match = re.search(r"(\d+(?:[.,]\d+)?)\s*€", precio)
            if price_match:
                details["price"] = float(price_match.group(1).replace(",", "."))
                details["is_free"] = False
            elif any(w in precio.lower() for w in ("gratis", "gratuito", "libre", "free")):
                details["is_free"] = True

        # "Más información" section may have URL
        mas_info = sections.get("más información", "")
        if mas_info:
            url_match = re.search(r"https?://[^\s<>\"']+", mas_info)
            if url_match:
                details["website"] = url_match.group(0)

        return details

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("detail_title") or raw_data.get("title")
            start_date = raw_data.get("detail_start_date") or raw_data.get("start_date")

            if not title or not start_date:
                return None

            end_date = raw_data.get("detail_end_date") or raw_data.get("end_date")
            city = raw_data.get("detail_city") or raw_data.get("city", "Murcia")

            # Build alternative_dates for multi-day events
            alternative_dates = None
            if end_date and end_date != start_date:
                all_dates = []
                d = start_date
                while d <= end_date:
                    all_dates.append(d)
                    d += timedelta(days=1)
                # Cap at 365 days to avoid absurd ranges
                if len(all_dates) <= 365:
                    alternative_dates = {
                        "dates": [d.isoformat() for d in all_dates],
                        "prices": {},
                    }

            # Registration URL
            registration_url = raw_data.get("website") or None

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=end_date,
                start_time=raw_data.get("start_time"),
                description=raw_data.get("description", ""),
                venue_name=raw_data.get("venue_name"),
                address=raw_data.get("address"),
                city=city,
                province="Murcia",
                comunidad_autonoma="Región de Murcia",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
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
