"""La Moncloa adapter - Spanish Government daily agenda.

Source: https://www.lamoncloa.gob.es/gobierno/agenda/Paginas/agenda.aspx
Tier: Bronze (static HTML, one page per day)
CCAA: Comunidad de Madrid (national government based in Madrid)
Category: politica (government/institutional events)

La Moncloa publishes the daily agenda for the President and ministers.
URLs are predictable: agenda.aspx?d=YYYYMMDD

Page structure (well-structured with CSS classes):
  div#containerAgenda > ul.eventList.personList
    li (per official):
      h2.eventTitle > span.nombrePersona  — name
      p.eventDescription.cargo  — role
      ul.eventList
        li (per event):
          span.eventDate  — time "10:30 h."
          p.eventPersonTitle  — description
          p.eventLocation  — optional location info
"""

import asyncio
import hashlib
import re
from datetime import date, time, timedelta
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

# Time pattern: "10:30 h." or "9:00 h."
TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})\s*h\.")

BASE_URL = "https://www.lamoncloa.gob.es"
AGENDA_BASE = f"{BASE_URL}/gobierno/agenda/Paginas/agenda.aspx"


def _make_external_id(event_date: date, cargo: str, desc: str) -> str:
    """Generate a stable external_id from date + cargo + description."""
    raw = f"{event_date.isoformat()}_{cargo.strip().lower()}_{desc.strip().lower()[:80]}"
    return f"moncloa_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


@register_adapter("la_moncloa")
class LaMoncloaAdapter(BaseAdapter):
    """Adapter for La Moncloa - Spanish Government daily agenda."""

    source_id = "la_moncloa"
    source_name = "Agenda del Gobierno de España"
    source_url = AGENDA_BASE
    ccaa = "Comunidad de Madrid"
    ccaa_code = "MD"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    # Scrape 1 day back + 7 days ahead
    DAYS_BACK = 1
    DAYS_AHEAD = 7

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = False,
        max_events: int = 200,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch agenda items from La Moncloa for a range of days."""
        events: list[dict[str, Any]] = []
        effective_limit = min(max_events, limit) if limit else max_events
        seen_ids: set[str] = set()

        today = date.today()
        start_day = today - timedelta(days=self.DAYS_BACK)
        end_day = today + timedelta(days=self.DAYS_AHEAD)

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                current = start_day
                while current <= end_day:
                    url = f"{AGENDA_BASE}?d={current:%Y%m%d}"
                    self.logger.info("fetching_moncloa_day", url=url, date=current.isoformat())

                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        self.logger.warning(
                            "day_fetch_error", date=current.isoformat(),
                            status=e.response.status_code,
                        )
                        current += timedelta(days=1)
                        continue

                    day_events = self._parse_day_page(response.text, current)

                    for event_data in day_events:
                        if event_data["external_id"] not in seen_ids:
                            seen_ids.add(event_data["external_id"])
                            events.append(event_data)
                            if len(events) >= effective_limit:
                                break

                    self.logger.info(
                        "moncloa_day_parsed",
                        date=current.isoformat(),
                        found=len(day_events),
                    )

                    if len(events) >= effective_limit:
                        break

                    current += timedelta(days=1)
                    await asyncio.sleep(0.5)

            self.logger.info("moncloa_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_day_page(self, html: str, event_date: date) -> list[dict[str, Any]]:
        """Parse a single day's agenda page.

        Structure:
        div#containerAgenda > ul.personList
          li (per official):
            h2.eventTitle > span.nombrePersona
            p.cargo
            ul.eventList > li (per event):
              span.eventDate ("10:30 h.")
              p.eventPersonTitle (description)
        """
        events: list[dict[str, Any]] = []
        soup = BeautifulSoup(html, "html.parser")

        container = soup.find(id="containerAgenda")
        if not container:
            container = soup.find(class_="agendaGobiernoContainer")
        if not container:
            return events

        # Top-level list: each <li> is an official
        person_list = container.find("ul", class_="personList")
        if not person_list:
            return events

        for person_li in person_list.find_all("li", recursive=False):
            # Name + role
            name_span = person_li.find("span", class_="nombrePersona")
            cargo_p = person_li.find("p", class_="cargo")
            name = name_span.get_text(strip=True) if name_span else ""
            cargo = cargo_p.get_text(strip=True) if cargo_p else ""
            full_cargo = f"{name} - {cargo}" if name and cargo else name or cargo
            if not full_cargo:
                continue

            # Nested event list
            event_ul = person_li.find("ul", class_="eventList")
            if not event_ul:
                continue

            for event_li in event_ul.find_all("li", recursive=False):
                # Time
                event_time: time | None = None
                date_span = event_li.find("span", class_="eventDate")
                if date_span:
                    time_match = TIME_PATTERN.search(date_span.get_text())
                    if time_match:
                        try:
                            event_time = time(
                                int(time_match.group(1)),
                                int(time_match.group(2)),
                            )
                        except ValueError:
                            pass

                # Description from eventPersonTitle
                desc_p = event_li.find("p", class_="eventPersonTitle")
                description = desc_p.get_text(strip=True) if desc_p else ""
                if not description:
                    continue

                # Optional location
                loc_p = event_li.find("p", class_="eventLocation")
                location = loc_p.get_text(strip=True) if loc_p else ""

                events.append(self._build_event(
                    event_date, full_cargo, description, event_time, location,
                ))

        return events

    def _build_event(
        self,
        event_date: date,
        cargo: str,
        description: str,
        event_time: time | None,
        location: str = "",
    ) -> dict[str, Any]:
        """Build a raw event dict from parsed data."""
        # Title: "Cargo - Description[:80]"
        short_desc = description[:80].rstrip()
        if len(description) > 80:
            short_desc += "..."
        title = f"{cargo} - {short_desc}"

        day_url = f"{AGENDA_BASE}?d={event_date:%Y%m%d}"
        external_id = _make_external_id(event_date, cargo, description)

        return {
            "title": title,
            "start_date": event_date,
            "start_time": event_time,
            "cargo": cargo,
            "description": description,
            "location": location,
            "detail_url": day_url,
            "external_id": external_id,
        }

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            cargo = raw_data.get("cargo", "")
            raw_desc = raw_data.get("description", "")
            detail_url = raw_data.get("detail_url", AGENDA_BASE)

            # Build description
            parts = []
            if raw_desc:
                parts.append(raw_desc)
            if cargo:
                parts.append(f"Agenda de: {cargo}")
            parts.append("Agenda del Gobierno de España - La Moncloa.")
            parts.append(
                f'Más información en <a href="{detail_url}" style="color:#2563eb">'
                f"{detail_url}</a>"
            )
            description = "\n\n".join(parts)

            organizer = EventOrganizer(
                name="Gobierno de España",
                url="https://www.lamoncloa.gob.es",
                type="institucion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                start_time=raw_data.get("start_time"),
                description=description,
                city="Madrid",
                province="Madrid",
                comunidad_autonoma="Comunidad de Madrid",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                category_slugs=["politica"],
                organizer=organizer,
                is_free=True,
                requires_registration=False,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
