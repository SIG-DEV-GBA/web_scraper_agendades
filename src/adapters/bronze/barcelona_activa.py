"""Barcelona Activa adapter - Entrepreneurship workshops and activities.

Source: https://emprenedoria.barcelonactiva.cat/es/activitats/activity-timetable
Tier: Bronze (JS-rendered, fetched via Tavily extract)
CCAA: Cataluña
Category: economica (entrepreneurship, business training, employment)

Barcelona Activa is Barcelona's local development agency offering
free workshops on entrepreneurship, business skills, and employment.
The activity calendar is JS-rendered and uses Liferay-style IDs.
"""

import hashlib
import os
import re
from datetime import date
from typing import Any

import httpx

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


def _fuzzy_month(text: str) -> int | None:
    """Match month name even with garbled encoding (e.g. 'sep�iembre' → 9).

    Strategy: strip non-ASCII chars, then check if the cleaned text
    starts with a known month prefix (3+ chars).
    """
    # First try exact match
    clean = text.lower().strip()
    if clean in MONTHS_ES:
        return MONTHS_ES[clean]

    # Strip non-ASCII chars (replacement char, etc.)
    ascii_only = re.sub(r"[^\x00-\x7f]", "", clean)
    if ascii_only in MONTHS_ES:
        return MONTHS_ES[ascii_only]

    # Prefix match (at least 3 chars)
    for name, num in MONTHS_ES.items():
        if len(ascii_only) >= 3 and name.startswith(ascii_only[:3]):
            return num
        # Also try if garbled text contains the key consonants
        if len(ascii_only) >= 4 and ascii_only[:2] == name[:2] and ascii_only[-2:] == name[-2:]:
            return num

    return None

LISTING_URL = "https://emprenedoria.barcelonactiva.cat/es/activitats/activity-timetable"
DETAIL_BASE = "https://emprenedoria.barcelonactiva.cat/activitats/detall-activitat?id="
TAVILY_API_URL = "https://api.tavily.com/extract"

# Pattern: "lunes 02 marzo · 16:00"
# Note: day/month names may have garbled chars (mi�rcoles, etc.)
DATE_RE = re.compile(
    r"(\S+)\s+(\d{1,2})\s+(\S+)\s*[·.]?\s*(\d{1,2}:\d{2})?",
    re.IGNORECASE,
)


def _make_external_id(activity_id: str) -> str:
    return f"bcnactiva_{activity_id}"


@register_adapter("barcelona_activa")
class BarcelonaActivaAdapter(BaseAdapter):
    """Adapter for Barcelona Activa - Entrepreneurship activities."""

    source_id = "barcelona_activa"
    source_name = "Barcelona Activa - Emprendimiento"
    source_url = LISTING_URL
    ccaa = "Cataluña"
    ccaa_code = "CT"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    async def fetch_events(
        self,
        enrich: bool = True,
        max_events: int = 200,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch activities via Tavily extract."""
        events: list[dict[str, Any]] = []
        effective_limit = min(max_events, limit) if limit else max_events

        tavily_key = os.environ.get("TAVILY_API_KEY", "")
        if not tavily_key:
            self.logger.error("tavily_api_key_missing")
            raise RuntimeError("TAVILY_API_KEY environment variable required")

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                self.logger.info("fetching_bcnactiva_via_tavily", url=LISTING_URL)

                resp = await client.post(
                    TAVILY_API_URL,
                    headers={
                        "Authorization": f"Bearer {tavily_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "urls": [LISTING_URL],
                        "extract_depth": "advanced",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                if not results:
                    self.logger.warning("no_tavily_results")
                    return events

                content = results[0].get("raw_content", "")
                if not content:
                    self.logger.warning("empty_tavily_content")
                    return events

                events = self._parse_content(content, effective_limit)

            self.logger.info("bcnactiva_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_content(self, content: str, limit: int) -> list[dict[str, Any]]:
        """Parse Tavily markdown content into event dicts.

        Content pattern:
        [Title](https://emprenedoria.barcelonactiva.cat/activitats/detall-activitat?id=NNNNNN)
        Cuándo:lunes 02 marzo · 16:00
        """
        events: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        current_year = date.today().year

        lines = content.split("\n")
        i = 0
        while i < len(lines) and len(events) < limit:
            line = lines[i].strip()

            # Match activity link: [Title](URL with detall-activitat?id=NNNN)
            # URL may be full (https://...) or relative (detall-activitat?id=...)
            link_match = re.match(
                r"\[([^\]]+)\]\(([^\)]*detall-activitat\?id=(\d+))\)",
                line,
            )
            if not link_match:
                i += 1
                continue

            title = link_match.group(1).strip()
            raw_url = link_match.group(2)
            activity_id = link_match.group(3)
            # Ensure full URL
            if raw_url.startswith("http"):
                detail_url = raw_url
            else:
                detail_url = f"{DETAIL_BASE}{activity_id}"

            # Skip duplicates
            if activity_id in seen_ids:
                i += 1
                continue
            seen_ids.add(activity_id)

            # Look ahead for date: "Cuándo:lunes 02 marzo · 16:00"
            # Note: Tavily may return garbled UTF-8 (Cu�ndo, Cu\xe1ndo, etc.)
            event_date = None
            time_str = None
            j = i + 1
            while j < len(lines) and j < i + 10:
                next_line = lines[j].strip()
                if re.search(r"Cu.{0,4}ndo:", next_line, re.IGNORECASE):
                    # Remove prefix (handle garbled encoding)
                    date_text = re.sub(r"Cu.{0,4}ndo:\s*", "", next_line, flags=re.IGNORECASE)
                    date_match = DATE_RE.search(date_text)
                    if date_match:
                        day = int(date_match.group(2))
                        month_name = date_match.group(3)
                        month = _fuzzy_month(month_name)
                        time_str = date_match.group(4)
                        if month:
                            try:
                                event_date = date(current_year, month, day)
                            except ValueError:
                                pass
                    break
                elif next_line.startswith("[") and "detall-activitat" in next_line:
                    break
                j += 1

            if not event_date:
                i += 1
                continue

            events.append({
                "title": title,
                "start_date": event_date,
                "time": time_str,
                "detail_url": detail_url,
                "activity_id": activity_id,
                "external_id": _make_external_id(activity_id),
            })

            i = j + 1

        return events

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Convert raw activity data to EventCreate."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            detail_url = raw_data.get("detail_url", LISTING_URL)
            parts = []

            time_str = raw_data.get("time")
            if time_str:
                parts.append(f"Horario: {time_str}")

            parts.append(
                "Actividad gratuita de emprendimiento organizada por Barcelona Activa."
            )
            parts.append(
                f'Más información e inscripción en <a href="{detail_url}" style="color:#2563eb">'
                f"Barcelona Activa</a>"
            )

            description = "\n\n".join(parts)

            organizer = EventOrganizer(
                name="Barcelona Activa",
                url="https://www.barcelonactiva.cat",
                type="institucion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                description=description,
                city="Barcelona",
                province="Barcelona",
                comunidad_autonoma="Cataluña",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=detail_url,
                registration_url=detail_url,
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                category_slugs=["economica"],
                organizer=organizer,
                is_free=True,
                requires_registration=True,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
