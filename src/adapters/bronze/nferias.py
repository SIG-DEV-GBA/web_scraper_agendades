"""nFerias adapter - Business/employment fairs directory in Spain.

Source: https://www.nferias.com/negocios/espana/
Tier: Bronze (HTML scraping with pagination)
CCAA: (national scope - events across Spain)
Category: economica (business fairs, employment, entrepreneurship)

nFerias is a directory of trade fairs and business events in Spain.
Cards use Bootstrap layout with structured date/venue/category data.
Pagination via ?page=N query parameter.
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

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

BASE_URL = "https://www.nferias.com"
LISTING_URL = f"{BASE_URL}/negocios/espana/"

# Date pattern: "Del 2 al 5 marzo 2026" (dates are in <time> tags with datetime attrs)
DATE_RANGE_RE = re.compile(
    r"Del\s+(\d{1,2})\s+al\s+(\d{1,2})\s+(\w+)\s+(\d{4})",
    re.IGNORECASE,
)


def _make_external_id(title: str, event_date: date) -> str:
    raw = f"{title.strip().lower()}_{event_date.isoformat()}"
    return f"nferias_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


def _parse_date_from_time_tags(card: Any) -> tuple[date | None, date | None]:
    """Extract start/end dates from <time> tags with datetime attributes."""
    start_date = None
    end_date = None

    dtstart = card.find("time", class_="dtstart")
    if dtstart and dtstart.get("datetime"):
        try:
            start_date = date.fromisoformat(dtstart["datetime"][:10])
        except ValueError:
            pass

    dtend = card.find("time", class_="dtend")
    if dtend and dtend.get("datetime"):
        try:
            end_date = date.fromisoformat(dtend["datetime"][:10])
        except ValueError:
            pass

    return start_date, end_date


def _parse_date_from_text(text: str) -> tuple[date | None, date | None]:
    """Fallback: parse dates from 'Del X al Y mes YYYY' text."""
    m = DATE_RANGE_RE.search(text)
    if not m:
        return None, None

    day_start = int(m.group(1))
    day_end = int(m.group(2))
    month_name = m.group(3).lower()
    year = int(m.group(4))
    month = MONTHS_ES.get(month_name)

    if not month:
        return None, None

    try:
        start = date(year, month, day_start)
        end = date(year, month, day_end)
        return start, end
    except ValueError:
        return None, None


@register_adapter("nferias")
class NFeriasAdapter(BaseAdapter):
    """Adapter for nFerias - Business fairs directory in Spain."""

    source_id = "nferias"
    source_name = "nFerias - Ferias de Negocios en España"
    source_url = LISTING_URL
    ccaa = ""
    ccaa_code = ""
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    MAX_PAGES = 3

    async def fetch_events(
        self,
        enrich: bool = True,
        max_events: int = 200,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch fair listings from nferias with pagination."""
        events: list[dict[str, Any]] = []
        effective_limit = min(max_events, limit) if limit else max_events
        seen_ids: set[str] = set()

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                for page in range(1, self.MAX_PAGES + 1):
                    url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"

                    self.logger.info("fetching_nferias_page", url=url, page=page)

                    try:
                        response = await client.get(url)
                        if response.status_code == 404:
                            break
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 404:
                            break
                        raise

                    soup = BeautifulSoup(response.text, "html.parser")

                    # Cards: div.row.no-gutters.align-items-center
                    cards = soup.select("div.row.no-gutters.align-items-center")

                    if not cards:
                        self.logger.info("no_cards_found", page=page)
                        break

                    page_count = 0
                    for card in cards:
                        event_data = self._parse_card(card)
                        if not event_data:
                            continue

                        eid = event_data.get("external_id", "")
                        if eid in seen_ids:
                            continue
                        seen_ids.add(eid)

                        events.append(event_data)
                        page_count += 1

                        if len(events) >= effective_limit:
                            break

                    self.logger.info("nferias_page_parsed", page=page, found=page_count)

                    if len(events) >= effective_limit:
                        break

                    # Check if there's a next page
                    next_link = soup.find("a", string=re.compile(r"Siguiente"))
                    if not next_link:
                        break

            self.logger.info("nferias_total_events", count=len(events))

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    def _parse_card(self, card: Any) -> dict[str, Any] | None:
        """Parse a single fair card.

        Structure:
        <div class="row no-gutters align-items-center">
          <div class="col-md-3 text-center">
            <img alt="..." src="//images.neventum.com/..." />
          </div>
          <div class="col-md-9">
            <div class="card-body">
              <a class="text-dark medium font-l mb-1" href="...">Title</a>
              <div class="mb-1">
                <span class="font-weight-bold">
                  Del <time class="dtstart" datetime="...">2</time>
                  al <time class="dtend" datetime="...">5 marzo 2026</time>
                </span>
              </div>
              <div class="mb-3">Venue<br/>City, España</div>
              <div class="text-muted"><span>Category1</span>, <span>Cat2</span></div>
            </div>
          </div>
        </div>
        """
        try:
            # Title and link
            title_link = card.select_one("a.text-dark.medium")
            if not title_link:
                return None

            title = title_link.get_text(strip=True)
            detail_url = title_link.get("href", "")
            if not title:
                return None

            # Make absolute URL
            if detail_url and not detail_url.startswith("http"):
                detail_url = f"{BASE_URL}{detail_url}"

            # Dates from <time> tags
            start_date, end_date = _parse_date_from_time_tags(card)

            # Fallback: parse from text
            if not start_date:
                date_div = card.select_one("div.mb-1")
                if date_div:
                    start_date, end_date = _parse_date_from_text(
                        date_div.get_text(strip=True),
                    )

            if not start_date:
                return None

            # Venue and city
            venue = ""
            city = ""
            location_div = card.select_one("div.mb-3")
            if location_div:
                parts = location_div.get_text(separator="\n", strip=True).split("\n")
                if len(parts) >= 2:
                    venue = parts[0].strip()
                    city_text = parts[1].strip()
                    # "Barcelona, España" -> "Barcelona"
                    city = city_text.split(",")[0].strip() if city_text else ""
                elif parts:
                    venue = parts[0].strip()

            # Categories from text-muted spans
            categories = []
            cat_div = card.select_one("div.text-muted")
            if cat_div:
                for span in cat_div.find_all("span"):
                    cat_text = span.get_text(strip=True)
                    if cat_text:
                        categories.append(cat_text)

            # Image
            img = card.find("img")
            image_url = None
            if img:
                src = img.get("src", "")
                if src:
                    image_url = f"https:{src}" if src.startswith("//") else src

            external_id = _make_external_id(title, start_date)

            return {
                "title": title,
                "start_date": start_date,
                "end_date": end_date,
                "detail_url": detail_url,
                "venue": venue,
                "city": city,
                "fair_categories": categories,
                "image_url": image_url,
                "external_id": external_id,
            }

        except Exception as e:
            self.logger.debug("parse_card_error", error=str(e))
            return None

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Convert raw fair data to EventCreate."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            # Build description
            detail_url = raw_data.get("detail_url", LISTING_URL)
            parts = []

            fair_cats = raw_data.get("fair_categories", [])
            if fair_cats:
                parts.append(f"Sectores: {', '.join(fair_cats)}")

            venue = raw_data.get("venue", "")
            if venue:
                parts.append(f"Recinto: {venue}")

            end_date = raw_data.get("end_date")
            if end_date and end_date != start_date:
                parts.append(
                    f"Del {start_date.strftime('%d/%m/%Y')} al {end_date.strftime('%d/%m/%Y')}"
                )

            parts.append(
                f'Más información en <a href="{detail_url}" style="color:#2563eb">'
                f"nFerias</a>"
            )

            description = "\n\n".join(parts)

            city = raw_data.get("city", "")

            organizer = EventOrganizer(
                name="nFerias",
                url="https://www.nferias.com",
                type="empresa",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=end_date,
                description=description,
                city=city,
                province="",
                comunidad_autonoma="",
                country="España",
                location_name=raw_data.get("venue", ""),
                location_type=LocationType.PHYSICAL,
                external_url=detail_url,
                registration_url=detail_url,
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_slugs=["economica"],
                organizer=organizer,
                is_free=False,
                requires_registration=True,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), title=raw_data.get("title"))
            return None
