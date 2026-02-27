"""JGPA adapter - Junta General del Principado de Asturias calendar.

Source: https://www.jgpa.es/calendario-de-actividades
Tier: Bronze (static HTML, Liferay portal - SSR)
CCAA: Principado de Asturias
Category: politica (parliamentary/legislative events)

JGPA publishes a weekly calendar of parliamentary activities (plenary sessions,
committee meetings, speaker meetings, etc.).

The site uses Liferay Portal with a week-view calendar portlet. Content is
server-side rendered (no JS needed).

Weekly URL pattern: /calendario-de-actividades/-/events-week/DD/MM/YYYY

Page structure:
  div.view-week
    div.day-wrapper
      div.day-events-wrapper
        div.day-events
          span[itemprop="startDate"]  — "Mon Feb 23 14:17:52 GMT 2026"
          a.date > span.day / span.month / span.day-of-week
          div.events
            div.calevent-wrapper
              a.calevent[href][title]
                span.info
                  span.calevent-title > span.title
                  span.data > span.hour
"""

import asyncio
import hashlib
import re
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.jgpa.es"
CALENDAR_URL = f"{BASE_URL}/calendario-de-actividades"
WEEK_URL = f"{CALENDAR_URL}/-/events-week"

# Liferay date format: "Mon Feb 23 14:17:52 GMT 2026"
LIFERAY_DATE_PATTERN = re.compile(
    r"\w{3}\s+(\w{3})\s+(\d{1,2})\s+[\d:]+\s+\w+\s+(\d{4})"
)

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Spanish month names for fallback
MONTH_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}

TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})")

# Fetch current week + next 3 weeks
WEEKS_AHEAD = 4


def _make_external_id(title: str, event_date: date) -> str:
    raw = f"{title.strip().lower()[:80]}_{event_date.isoformat()}"
    return f"jgpa_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


def _parse_liferay_date(text: str) -> date | None:
    """Parse Liferay date: 'Mon Feb 23 14:17:52 GMT 2026'."""
    m = LIFERAY_DATE_PATTERN.search(text)
    if m:
        month_str, day, year = m.group(1), int(m.group(2)), int(m.group(3))
        month = MONTH_MAP.get(month_str)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass
    return None


def _parse_spanish_date(day_num: str, month_name: str, year: int | None = None) -> date | None:
    """Parse date from Spanish day number + month name."""
    month = MONTH_ES.get(month_name.lower())
    if not month:
        return None
    if not year:
        year = date.today().year
    try:
        return date(year, month, int(day_num))
    except ValueError:
        return None


@register_adapter("jgpa")
class JgpaAdapter(BaseAdapter):
    """Adapter for JGPA - Junta General del Principado de Asturias."""

    source_id = "jgpa"
    source_name = "Junta General del Principado de Asturias"
    source_url = CALENDAR_URL
    ccaa = "Principado de Asturias"
    ccaa_code = "AS"
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

        today = date.today()

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for week_offset in range(WEEKS_AHEAD):
                    week_start = today + timedelta(weeks=week_offset)
                    # Monday of that week
                    monday = week_start - timedelta(days=week_start.weekday())
                    url = f"{WEEK_URL}/{monday:%d}/{monday:%m}/{monday:%Y}"

                    self.logger.info("fetching_jgpa_week", url=url, week=week_offset)

                    try:
                        response = await client.get(url)
                        if response.status_code == 404:
                            self.logger.info("jgpa_week_not_found", week=week_offset)
                            continue
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        self.logger.warning(
                            "week_fetch_error", week=week_offset,
                            status=e.response.status_code,
                        )
                        continue

                    week_events = self._parse_week_page(response.text)

                    for ev in week_events:
                        if ev["external_id"] not in seen_ids:
                            seen_ids.add(ev["external_id"])
                            events.append(ev)
                            if len(events) >= effective_limit:
                                break

                    self.logger.info(
                        "jgpa_week_parsed", week=week_offset, found=len(week_events),
                    )

                    if len(events) >= effective_limit:
                        break

                    await asyncio.sleep(0.5)

            self.logger.info("jgpa_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_week_page(self, html: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        soup = BeautifulSoup(html, "html.parser")

        # Find day wrappers
        day_wrappers = soup.select("div.day-events-wrapper")
        if not day_wrappers:
            # Fallback: try direct day-events divs
            day_wrappers = soup.select("div.day-events")

        for day_wrapper in day_wrappers:
            # Get the date for this day
            event_date = None

            # Try itemprop startDate
            date_span = day_wrapper.find("span", attrs={"itemprop": "startDate"})
            if date_span:
                event_date = _parse_liferay_date(date_span.get_text())

            # Fallback: parse from visible date elements
            if not event_date:
                day_el = day_wrapper.select_one("span.day")
                month_el = day_wrapper.select_one("span.month")
                if day_el and month_el:
                    event_date = _parse_spanish_date(
                        day_el.get_text(strip=True),
                        month_el.get_text(strip=True),
                    )

            if not event_date:
                continue

            # Find all events in this day
            calevent_wrappers = day_wrapper.select("div.calevent-wrapper")
            for cw in calevent_wrappers:
                try:
                    ev = self._parse_event_card(cw, event_date)
                    if ev:
                        events.append(ev)
                except Exception as e:
                    self.logger.warning("event_parse_error", error=str(e))

        return events

    def _parse_event_card(self, card, event_date: date) -> dict[str, Any] | None:
        # Title
        title_el = card.select_one("span.title")
        if not title_el:
            title_el = card.select_one("a.calevent")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title:
            return None

        # Link
        link_el = card.select_one("a.calevent")
        link = ""
        if link_el:
            href = link_el.get("href", "")
            if href:
                link = f"{BASE_URL}{href}" if not href.startswith("http") else href

        # Time
        event_time = None
        hour_el = card.select_one("span.hour")
        if hour_el:
            m = TIME_PATTERN.search(hour_el.get_text())
            if m:
                try:
                    event_time = time(int(m.group(1)), int(m.group(2)))
                except ValueError:
                    pass

        external_id = _make_external_id(title, event_date)

        return {
            "title": title,
            "start_date": event_date,
            "start_time": event_time,
            "detail_url": link,
            "external_id": external_id,
        }

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            detail_url = raw_data.get("detail_url", CALENDAR_URL)

            parts = [
                title,
                "Actividad de la Junta General del Principado de Asturias.",
            ]
            parts.append(
                f'Más información en <a href="{detail_url}" style="color:#2563eb">'
                f"{detail_url}</a>"
            )
            description = "\n\n".join(parts)

            organizer = EventOrganizer(
                name="Junta General del Principado de Asturias",
                url="https://www.jgpa.es",
                type="institucion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                start_time=raw_data.get("start_time"),
                description=description,
                city="Oviedo",
                province="Asturias",
                comunidad_autonoma="Principado de Asturias",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=detail_url,
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
