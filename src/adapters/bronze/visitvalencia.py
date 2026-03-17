"""VisitValencia Agenda adapter - Cultural events in València.

Source: https://www.visitvalencia.com/agenda-valencia
Tier: Bronze (HTML scraping)
CCAA: Comunidad Valenciana

Pagination by month: ?date=YYYY-MM. Fetches current month + next 2 months.
Listing provides title, date range (DD/MM/YYYY), link, and teaser image.
Detail pages add description and full-resolution og:image.
"""

import re
from datetime import date, timedelta
from typing import Any

from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, LocationType
from src.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.visitvalencia.com"
LISTING_URL = "https://www.visitvalencia.com/agenda-valencia"


def _parse_date(text: str) -> tuple[date | None, date | None]:
    """Parse 'Del DD/MM/YYYY al DD/MM/YYYY' or single 'DD/MM/YYYY'."""
    text = text.strip()

    # Range: Del DD/MM/YYYY al DD/MM/YYYY
    m = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{4})\s*al\s*(\d{1,2})/(\d{1,2})/(\d{4})",
        text,
    )
    if m:
        try:
            sd = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            ed = date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
            return sd, ed
        except ValueError:
            pass

    # Single: DD/MM/YYYY
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        try:
            sd = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            return sd, sd
        except ValueError:
            pass

    return None, None


@register_adapter("visitvalencia_agenda")
class VisitValenciaAdapter(BaseAdapter):
    """Adapter for VisitValencia - Agenda de eventos."""

    source_id = "visitvalencia_agenda"
    source_name = "VisitValencia - Agenda"
    source_url = LISTING_URL
    ccaa = "Comunidad Valenciana"
    ccaa_code = "VC"
    province = "Valencia"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    MAX_EVENTS = 200
    MONTHS_AHEAD = 3  # current month + 2 more

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = True,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch events from multiple monthly pages, optionally enrich from detail pages."""
        effective_limit = min(self.MAX_EVENTS, limit) if limit else self.MAX_EVENTS

        events: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        # Build list of months to fetch: current + next N-1
        today = date.today()
        months_to_fetch = []
        for i in range(self.MONTHS_AHEAD):
            m = today.month + i
            y = today.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            months_to_fetch.append(f"{y}-{m:02d}")

        for month_str in months_to_fetch:
            url = f"{LISTING_URL}?date={month_str}"
            self.logger.info("fetching_visitvalencia", url=url, month=month_str)
            try:
                response = await self.fetch_url(url)
            except Exception as e:
                self.logger.warning("month_fetch_error", month=month_str, error=str(e)[:80])
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select(".card--event")
            self.logger.info("visitvalencia_cards_found", month=month_str, count=len(cards))

            for card in cards:
                parsed = self._parse_card(card)
                if parsed and parsed["detail_url"] not in seen_urls:
                    seen_urls.add(parsed["detail_url"])
                    events.append(parsed)
                    if len(events) >= effective_limit:
                        break
            if len(events) >= effective_limit:
                break

        self.logger.info("visitvalencia_total_events", count=len(events))

        # Fetch detail pages for description + full image
        if fetch_details and events:
            await self._fetch_details(events)

        return events

    def _parse_card(self, card: BeautifulSoup) -> dict[str, Any] | None:
        """Parse a listing card (.card--event)."""
        try:
            # Title
            heading = card.select_one(".card__heading")
            if not heading:
                return None
            title = heading.get_text(strip=True)
            if not title:
                return None

            # Link
            link = card.select_one("a")
            if not link:
                return None
            href = link.get("href", "")
            detail_url = href if href.startswith("http") else BASE_URL + href

            # Date
            date_el = card.select_one(".card__date")
            date_text = date_el.get_text(" ", strip=True) if date_el else ""
            start_date, end_date = _parse_date(date_text)

            # Image
            img = card.select_one("img")
            image_url = None
            if img:
                src = img.get("src", "") or img.get("data-src", "")
                if src:
                    image_url = src if src.startswith("http") else BASE_URL + src

            # External ID from URL slug
            slug = detail_url.rstrip("/").split("/")[-1]
            external_id = f"visitvalencia_{slug}"

            return {
                "title": title,
                "detail_url": detail_url,
                "start_date": start_date,
                "end_date": end_date,
                "image_url": image_url,
                "external_id": external_id,
            }

        except Exception as e:
            self.logger.debug("card_parse_error", error=str(e))
            return None

    async def _fetch_details(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages for description and full image."""
        for i, event in enumerate(events):
            detail_url = event.get("detail_url")
            if not detail_url:
                continue
            try:
                self.logger.info("fetching_detail", idx=f"{i + 1}/{len(events)}")
                response = await self.fetch_url(detail_url)
                soup = BeautifulSoup(response.text, "html.parser")

                # Description: concatenate all paragraphs from main
                main = soup.select_one("main")
                if main:
                    paragraphs = []
                    for p in main.select("p"):
                        text = p.get_text(strip=True)
                        if len(text) > 30:
                            paragraphs.append(text)
                    if paragraphs:
                        event["description"] = "\n\n".join(paragraphs)[:2000]

                # Fallback to meta description
                if not event.get("description"):
                    meta_desc = soup.find("meta", attrs={"name": "description"})
                    if meta_desc and meta_desc.get("content"):
                        event["description"] = meta_desc["content"]

                # Full-resolution image from og:image
                og_img = soup.find("meta", attrs={"property": "og:image"})
                if og_img and og_img.get("content"):
                    event["og_image"] = og_img["content"]

            except Exception as e:
                self.logger.debug("detail_fetch_error", idx=i, error=str(e)[:50])

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            end_date = raw_data.get("end_date")

            # Build alternative_dates for multi-day events
            alternative_dates = None
            if end_date and end_date != start_date:
                delta = (end_date - start_date).days
                if 1 < delta <= 365:
                    all_dates = []
                    d = start_date
                    while d <= end_date:
                        all_dates.append(d)
                        d += timedelta(days=1)
                    alternative_dates = {
                        "dates": [d.isoformat() for d in all_dates],
                        "prices": {},
                    }

            # Prefer og:image (full res) over listing teaser
            image_url = raw_data.get("og_image") or raw_data.get("image_url")

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=end_date,
                description=raw_data.get("description", ""),
                city="Valencia",
                province="Valencia",
                comunidad_autonoma="Comunidad Valenciana",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=image_url,
                alternative_dates=alternative_dates,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e))
            return None
