"""Defensor del Pueblo adapter - Institutional agenda.

Source: https://www.defensordelpueblo.es/agenda-institucional/
Tier: Bronze (static HTML, monthly tabs)
CCAA: Comunidad de Madrid (national institution based in Madrid)
Category: politica (institutional/civic events)

The Defensor del Pueblo publishes an agenda organized by month tabs.
Each month section has class .mes-line-NN (01-12) with <li> items
containing date, title, and optional link.
"""

import hashlib
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

# Date pattern: "DD-MM-YYYY"
DATE_PATTERN = re.compile(r"(\d{1,2})-(\d{2})-(\d{4})")

BASE_URL = "https://www.defensordelpueblo.es"
AGENDA_URL = f"{BASE_URL}/agenda-institucional/"


def _make_external_id(title: str, event_date: date) -> str:
    """Generate a stable external_id from title + date."""
    raw = f"{title.strip().lower()}_{event_date.isoformat()}"
    return f"defensor_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


@register_adapter("defensor_pueblo")
class DefensorPuebloAdapter(BaseAdapter):
    """Adapter for Defensor del Pueblo - Institutional agenda."""

    source_id = "defensor_pueblo"
    source_name = "Defensor del Pueblo"
    source_url = AGENDA_URL
    ccaa = "Comunidad de Madrid"
    ccaa_code = "MD"
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
        """Fetch agenda items from Defensor del Pueblo."""
        events: list[dict[str, Any]] = []
        effective_limit = min(max_events, limit) if limit else max_events
        seen_ids: set[str] = set()

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                self.logger.info("fetching_defensor_pueblo", url=AGENDA_URL)
                response = await client.get(AGENDA_URL)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Strategy 1: find month containers .mes-line-01 to .mes-line-12
                items_found = False
                for month_num in range(1, 13):
                    container = soup.find(class_=f"mes-line-{month_num:02d}")
                    if not container:
                        continue

                    for li in container.find_all("li"):
                        event_data = self._parse_item(li)
                        if event_data and event_data["external_id"] not in seen_ids:
                            seen_ids.add(event_data["external_id"])
                            events.append(event_data)
                            items_found = True
                            if len(events) >= effective_limit:
                                break

                    if len(events) >= effective_limit:
                        break

                # Strategy 2 (fallback): find all <li> with <a><strong> + date pattern
                if not items_found:
                    self.logger.info("defensor_fallback_strategy")
                    for li in soup.find_all("li"):
                        a_tag = li.find("a")
                        strong = li.find("strong")
                        text = li.get_text()
                        if a_tag and strong and DATE_PATTERN.search(text):
                            event_data = self._parse_item(li)
                            if event_data and event_data["external_id"] not in seen_ids:
                                seen_ids.add(event_data["external_id"])
                                events.append(event_data)
                                if len(events) >= effective_limit:
                                    break

            self.logger.info("defensor_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_item(self, li: Any) -> dict[str, Any] | None:
        """Parse a single <li> agenda item.

        Expected structure:
        <li><a href="URL"><strong>Título</strong></a> DD-MM-YYYY - Descripción</li>
        """
        try:
            text = li.get_text(separator=" ", strip=True)

            # Extract date
            date_match = DATE_PATTERN.search(text)
            if not date_match:
                return None

            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3))
            try:
                start_date = date(year, month, day)
            except ValueError:
                return None

            # Extract title from <strong> or <a>
            a_tag = li.find("a")
            strong = li.find("strong")
            title = ""
            detail_url = ""

            if strong:
                title = strong.get_text(strip=True)
            elif a_tag:
                title = a_tag.get_text(strip=True)

            if a_tag:
                href = a_tag.get("href", "")
                if href.startswith("/"):
                    detail_url = f"{BASE_URL}{href}"
                elif href.startswith("http"):
                    detail_url = href

            if not title:
                return None

            # Extract description: text after the date
            description = ""
            date_end = date_match.end()
            remaining = text[date_end:].strip()
            if remaining.startswith("-"):
                remaining = remaining[1:].strip()
            if remaining:
                description = remaining

            external_id = _make_external_id(title, start_date)

            return {
                "title": title,
                "start_date": start_date,
                "description": description,
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

            # Build description
            detail_url = raw_data.get("detail_url", AGENDA_URL)
            short_desc = raw_data.get("description", "")
            parts = []
            if short_desc:
                parts.append(short_desc)
            parts.append("Actividad institucional del Defensor del Pueblo.")
            parts.append(
                f'Más información en <a href="{detail_url}" style="color:#2563eb">'
                f"{detail_url}</a>"
            )
            description = "\n\n".join(parts)

            organizer = EventOrganizer(
                name="Defensor del Pueblo",
                url="https://www.defensordelpueblo.es",
                type="institucion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
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
