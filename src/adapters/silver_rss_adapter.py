"""Adapter for Silver-level (Nivel Plata) RSS feed sources.

First implementation: Galicia cultura.gal RSS feed.
Reusable for other RSS-based event sources.

RSS Structure (cultura.gal):
- title: Event name
- link: URL to event page
- id: Unique GUID
- published_parsed: Event start date/time
- summary: HTML with image, date, venue, description
"""

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

import feedparser

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, LocationType
from src.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# GALICIA PROVINCE MAPPING
# ============================================================

# Map known cities/locations to their province in Galicia
GALICIA_CITY_PROVINCE: dict[str, str] = {
    "a coruña": "A Coruña",
    "coruña": "A Coruña",
    "ferrol": "A Coruña",
    "santiago de compostela": "A Coruña",
    "santiago": "A Coruña",
    "carballo": "A Coruña",
    "betanzos": "A Coruña",
    "arteixo": "A Coruña",
    "lugo": "Lugo",
    "monforte de lemos": "Lugo",
    "viveiro": "Lugo",
    "folgoso do courel": "Lugo",
    "sarria": "Lugo",
    "vilalba": "Lugo",
    "ourense": "Ourense",
    "orense": "Ourense",
    "verín": "Ourense",
    "o barco de valdeorras": "Ourense",
    "celanova": "Ourense",
    "pontevedra": "Pontevedra",
    "vigo": "Pontevedra",
    "vilagarcía de arousa": "Pontevedra",
    "cangas": "Pontevedra",
    "marín": "Pontevedra",
    "redondela": "Pontevedra",
    "tui": "Pontevedra",
    "bueu": "Pontevedra",
    "lalín": "Pontevedra",
}


@dataclass
class RSSSourceConfig:
    """Configuration for an RSS feed source."""

    slug: str
    name: str
    url: str
    ccaa: str
    ccaa_code: str

    # RSS parsing
    date_from_published: bool = True  # Use published_parsed for start_date
    summary_has_html: bool = True  # Summary contains HTML to parse

    # Location parsing from summary HTML
    # cultura.gal format: "Venue - City - Province"
    location_separator: str = " - "
    location_parts: list[str] = field(
        default_factory=lambda: ["venue", "city", "province"]
    )


# ============================================================
# SOURCE CONFIGURATIONS
# ============================================================

SILVER_RSS_SOURCES: dict[str, RSSSourceConfig] = {
    "galicia_cultura": RSSSourceConfig(
        slug="galicia_cultura",
        name="Agenda Cultural de Galicia (cultura.gal)",
        url="https://www.cultura.gal/es/rssaxenda",
        ccaa="Galicia",
        ccaa_code="GA",
    ),
}


# ============================================================
# RSS ADAPTER
# ============================================================


class SilverRSSAdapter(BaseAdapter):
    """Adapter for Silver-level RSS feed sources.

    Parses RSS feeds using feedparser, extracting structured event data
    from the HTML content embedded in RSS item summaries.
    """

    adapter_type = AdapterType.API  # Uses HTTP fetch (no browser needed)

    def __init__(self, source_slug: str, *args: Any, **kwargs: Any) -> None:
        if source_slug not in SILVER_RSS_SOURCES:
            raise ValueError(
                f"Unknown RSS source: {source_slug}. "
                f"Available: {list(SILVER_RSS_SOURCES.keys())}"
            )

        self.rss_config = SILVER_RSS_SOURCES[source_slug]
        self.source_id = self.rss_config.slug
        self.source_name = self.rss_config.name
        self.source_url = self.rss_config.url
        self.ccaa = self.rss_config.ccaa
        self.ccaa_code = self.rss_config.ccaa_code

        super().__init__(*args, **kwargs)

    async def fetch_events(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Fetch and parse RSS feed into raw event dicts."""
        self.logger.info(
            "fetching_rss",
            source=self.source_id,
            url=self.source_url,
        )

        # Fetch RSS content via HTTP
        response = await self.fetch_url(self.source_url)
        feed = feedparser.parse(response.text)

        if feed.bozo and not feed.entries:
            self.logger.error(
                "rss_parse_error",
                error=str(feed.bozo_exception),
            )
            return []

        # Convert feedparser entries to dicts
        items = []
        for entry in feed.entries:
            item = {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "guid": entry.get("id", ""),
                "summary_html": entry.get("summary", ""),
                "published": entry.get("published", ""),
                "published_parsed": entry.get("published_parsed"),
            }
            items.append(item)

        self.logger.info(
            "fetched_rss_events",
            source=self.source_id,
            count=len(items),
        )
        return items

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse a single RSS item into EventCreate."""
        try:
            # Title
            title = html.unescape(raw_data.get("title", "")).strip()
            if not title:
                return None

            # Date/time from published_parsed
            pp = raw_data.get("published_parsed")
            if not pp:
                return None

            start_date = date(pp.tm_year, pp.tm_mon, pp.tm_mday)
            start_time_val = (
                time(pp.tm_hour, pp.tm_min)
                if pp.tm_hour > 0 or pp.tm_min > 0
                else None
            )

            # Parse end_date from summary HTML date line
            end_date = None
            summary_html = raw_data.get("summary_html", "")
            date_line = self._extract_date_line(summary_html)
            if date_line:
                end_date = self._parse_end_date_from_line(date_line, start_date)

            # External ID and URL
            guid = raw_data.get("guid", "")
            external_id = f"galicia_cultura_{guid}" if guid else None
            external_url = raw_data.get("link", "")

            # Parse summary HTML for location, image, description
            image_url = self._extract_image_url(summary_html)
            venue_name, city, province = self._extract_location(summary_html)
            description = self._extract_description(summary_html)

            # Resolve province if not in location line
            if not province and city:
                province = GALICIA_CITY_PROVINCE.get(city.lower())

            return EventCreate(
                title=title,
                description=description,
                start_date=start_date,
                end_date=end_date,
                start_time=start_time_val,
                location_type=LocationType.PHYSICAL,
                venue_name=venue_name,
                city=city,
                province=province,
                comunidad_autonoma="Galicia",
                source_id=self.source_id,
                external_url=external_url,
                external_id=external_id,
                source_image_url=image_url,
                category_slugs=[],  # Filled by LLM enricher
            )

        except Exception as e:
            self.logger.warning(
                "rss_parse_error",
                error=str(e),
                title=raw_data.get("title", "")[:50],
            )
            return None

    # ============================================================
    # HTML PARSING HELPERS
    # ============================================================

    def _extract_image_url(self, summary_html: str) -> str | None:
        """Extract image URL from <div class="imaxe"><img src="...">."""
        match = re.search(
            r'<div\s+class="imaxe">\s*<img[^>]+src="([^"]+)"',
            summary_html,
        )
        if match:
            return match.group(1)
        return None

    def _extract_date_line(self, summary_html: str) -> str | None:
        """Extract the date line from the info div.

        Pattern: first text line inside <div class="info">
        Examples:
            "27 de enero, 18:00"
            "De 15 de diciembre a 26 de enero"
        """
        match = re.search(
            r'<div\s+class="info">\s*\n?\s*(.+?)<br',
            summary_html,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        return None

    def _parse_end_date_from_line(
        self, date_line: str, start_date: date
    ) -> date | None:
        """Parse end date from lines like 'De 15 de diciembre a 26 de enero'."""
        # Match "De ... a DD de MONTH" pattern
        match = re.search(
            r"a\s+(\d{1,2})\s+de\s+(\w+)",
            date_line,
            re.IGNORECASE,
        )
        if not match:
            return None

        day = int(match.group(1))
        month_name = match.group(2).lower()
        month = _SPANISH_MONTHS.get(month_name)
        if not month:
            return None

        # Determine year: if end month is before start month, it's next year
        year = start_date.year
        if month < start_date.month:
            year += 1

        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _extract_location(
        self, summary_html: str
    ) -> tuple[str | None, str | None, str | None]:
        """Extract venue, city, province from location line.

        Pattern: "Venue - City - Province" (second line in info div)
        """
        # Find the location line (second <br /> separated line in info div)
        match = re.search(
            r'<div\s+class="info">\s*\n?\s*.+?<br\s*/?\>\s*\n?\s*(.+?)<br',
            summary_html,
            re.DOTALL,
        )
        if not match:
            return None, None, None

        location_text = match.group(1).strip()
        # Remove any HTML tags
        location_text = re.sub(r"<[^>]+>", "", location_text).strip()

        if not location_text:
            return None, None, None

        parts = [p.strip() for p in location_text.split(" - ")]

        venue = parts[0] if len(parts) >= 1 else None
        city = parts[1] if len(parts) >= 2 else None
        province = parts[2] if len(parts) >= 3 else None

        return venue, city, province

    def _extract_description(self, summary_html: str) -> str | None:
        """Extract description text from <p> tags in the info div."""
        # Find all <p> content inside the info div
        info_match = re.search(
            r'<div\s+class="info">(.+?)</div>',
            summary_html,
            re.DOTALL,
        )
        if not info_match:
            return None

        info_content = info_match.group(1)

        # Extract text from <p> tags
        paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", info_content, re.DOTALL)
        if not paragraphs:
            return None

        # Clean each paragraph
        clean_parts = []
        for p in paragraphs:
            # Remove HTML tags
            text = re.sub(r"<[^>]+>", "", p)
            # Decode HTML entities
            text = html.unescape(text).strip()
            if text and text != "\xa0":  # Skip empty/nbsp paragraphs
                clean_parts.append(text)

        return "\n\n".join(clean_parts) if clean_parts else None


# ============================================================
# SPANISH MONTH NAMES
# ============================================================

_SPANISH_MONTHS: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


# ============================================================
# REGISTER ADAPTERS
# ============================================================


def create_rss_adapter_class(source_slug: str) -> type:
    """Create a registered adapter class for an RSS source."""

    @register_adapter(source_slug)
    class DynamicRSSAdapter(SilverRSSAdapter):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(source_slug, *args, **kwargs)

    DynamicRSSAdapter.__name__ = (
        f"{source_slug.title().replace('_', '')}Adapter"
    )
    return DynamicRSSAdapter


# Create and register adapter classes for all Silver RSS sources
for slug in SILVER_RSS_SOURCES:
    create_rss_adapter_class(slug)
