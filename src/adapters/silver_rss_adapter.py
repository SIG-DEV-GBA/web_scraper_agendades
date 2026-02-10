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
from icalendar import Calendar

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventContact, EventCreate, LocationType
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

    # Feed type: "cultura_gal" (HTML summary) or "mec" (Modern Events Calendar)
    feed_type: str = "cultura_gal"

    # Default province (for single-province sources)
    default_province: str | None = None

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
        feed_type="cultura_gal",
    ),
    "huesca_radar": RSSSourceConfig(
        slug="huesca_radar",
        name="RADAR Huesca - Programación Cultural",
        url="https://radarhuesca.es/eventos/feed/",
        ccaa="Aragón",
        ccaa_code="AR",
        feed_type="mec",  # Modern Events Calendar format
        default_province="Huesca",
    ),
    # cantabria_turismo eliminada - cubierta por viralagenda_cantabria con más eventos
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
        """Fetch and parse RSS/iCal feed into raw event dicts."""
        self.logger.info(
            "fetching_feed",
            source=self.source_id,
            url=self.source_url,
            feed_type=self.rss_config.feed_type,
        )

        # Handle iCal feeds separately
        if self.rss_config.feed_type == "ical":
            return await self._fetch_ical_events()

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
                "content_encoded": entry.get("content", [{}])[0].get("value", ""),
            }

            # Extract MEC (Modern Events Calendar) fields if present
            if self.rss_config.feed_type == "mec":
                item["mec_start_date"] = entry.get("mec_startdate", "")
                item["mec_end_date"] = entry.get("mec_enddate", "")
                item["mec_start_hour"] = entry.get("mec_starthour", "")
                item["mec_end_hour"] = entry.get("mec_endhour", "")
                item["mec_location"] = entry.get("mec_location", "")
                item["mec_cost"] = entry.get("mec_cost", "")
                item["mec_category"] = entry.get("mec_category", "")

            items.append(item)

        self.logger.info(
            "fetched_rss_events",
            source=self.source_id,
            count=len(items),
        )
        return items

    async def _fetch_ical_events(self) -> list[dict[str, Any]]:
        """Fetch and parse iCal/VCALENDAR feed into raw event dicts."""
        try:
            # Use async HTTP client
            response = await self.fetch_url(self.source_url)

            # Parse iCal content
            cal = Calendar.from_ical(response.content)

            items = []
            for component in cal.walk():
                if component.name == "VEVENT":
                    # Extract VEVENT fields
                    item = {
                        "feed_type": "ical",
                        "uid": str(component.get("UID", "")),
                        "title": str(component.get("SUMMARY", "")),
                        "description": str(component.get("DESCRIPTION", "")),
                        "url": str(component.get("URL", "")),
                        "location": str(component.get("LOCATION", "")),
                        "categories": [],
                        "dtstart": None,
                        "dtend": None,
                    }

                    # Parse dates
                    dtstart = component.get("DTSTART")
                    if dtstart:
                        dt = dtstart.dt
                        if isinstance(dt, datetime):
                            item["dtstart"] = dt
                            item["start_date"] = dt.date()
                            item["start_time"] = dt.time()
                        else:  # date only
                            item["dtstart"] = dt
                            item["start_date"] = dt
                            item["start_time"] = None

                    dtend = component.get("DTEND")
                    if dtend:
                        dt = dtend.dt
                        if isinstance(dt, datetime):
                            item["dtend"] = dt
                            item["end_date"] = dt.date()
                        else:
                            item["dtend"] = dt
                            item["end_date"] = dt

                    # Parse categories
                    categories = component.get("CATEGORIES")
                    if categories:
                        if hasattr(categories, "cats"):
                            item["categories"] = [str(c) for c in categories.cats]
                        elif hasattr(categories, "to_ical"):
                            item["categories"] = [str(categories)]

                    items.append(item)

            self.logger.info(
                "fetched_ical_events",
                source=self.source_id,
                count=len(items),
            )
            return items

        except Exception as e:
            self.logger.error("ical_fetch_error", error=str(e))
            return []

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse a single RSS/iCal item into EventCreate."""
        # Dispatch based on feed type
        if self.rss_config.feed_type == "ical":
            return self._parse_ical_event(raw_data)
        if self.rss_config.feed_type == "mec":
            return self._parse_mec_event(raw_data)
        return self._parse_cultura_gal_event(raw_data)

    def _parse_mec_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse MEC (Modern Events Calendar) format RSS item."""
        try:
            # Title
            title = html.unescape(raw_data.get("title", "")).strip()
            if not title:
                return None

            # Date from MEC fields (YYYY-MM-DD format)
            mec_start = raw_data.get("mec_start_date", "")
            mec_end = raw_data.get("mec_end_date", "")

            if mec_start:
                try:
                    start_date = datetime.strptime(mec_start, "%Y-%m-%d").date()
                except ValueError:
                    return None
            else:
                # Fallback to published_parsed
                pp = raw_data.get("published_parsed")
                if not pp:
                    return None
                start_date = date(pp.tm_year, pp.tm_mon, pp.tm_mday)

            end_date = None
            if mec_end:
                try:
                    end_date = datetime.strptime(mec_end, "%Y-%m-%d").date()
                except ValueError:
                    pass

            # Time from MEC fields (HH:MM format)
            start_time_val = None
            mec_start_hour = raw_data.get("mec_start_hour", "")
            if mec_start_hour:
                try:
                    parts = mec_start_hour.split(":")
                    if len(parts) >= 2:
                        start_time_val = time(int(parts[0]), int(parts[1]))
                except (ValueError, IndexError):
                    pass

            # External ID and URL
            guid = raw_data.get("guid", "")
            # Extract numeric ID from URL
            # MEC format: https://radarhuesca.es/?post_type=mec-events&p=12849
            ext_id = None
            if "?" in guid:
                # Try to extract 'p=' parameter from query string
                query_part = guid.split("?")[1] if "?" in guid else ""
                for param in query_part.split("&"):
                    if param.startswith("p="):
                        ext_id = param.split("=")[1]
                        break
            if not ext_id:
                # Fallback: try to extract from path
                path_part = guid.split("?")[0] if "?" in guid else guid
                if path_part.endswith("/"):
                    path_part = path_part[:-1]
                ext_id = path_part.split("/")[-1] if "/" in path_part else guid

            external_id = f"{self.source_id}_{ext_id}" if ext_id else None
            external_url = raw_data.get("link", "")

            # Location from MEC field
            mec_location = raw_data.get("mec_location", "")
            venue_name = mec_location if mec_location else None

            # Extract city from location - for Huesca, use default province as city
            city = self.rss_config.default_province

            # Province - use default for single-province sources
            province = self.rss_config.default_province

            # Price info from MEC cost
            mec_cost = raw_data.get("mec_cost", "")
            price_info = mec_cost if mec_cost else None
            price = None
            is_free = None
            requires_registration = False

            if price_info:
                cost_lower = price_info.lower()

                # Check for registration keywords
                if any(w in cost_lower for w in ["inscripción", "inscripcion", "inscripciones", "reserva"]):
                    requires_registration = True

                # Check for free keywords
                if any(w in cost_lower for w in ["gratis", "gratuita", "gratuito", "libre", "free"]):
                    is_free = True
                    # Clean up price_info - remove just the free word, keep other info
                    cleaned = re.sub(r"\b(gratuito|gratis|gratuita|libre|free)\b\.?\s*", "", cost_lower, flags=re.IGNORECASE).strip()
                    if cleaned:
                        # Has additional info like "Inscripción previa"
                        price_info = cleaned.capitalize()
                    else:
                        price_info = None

                # Extract numeric price (e.g., "6€", "8,00€", "10.50 euros")
                price_match = re.search(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur)", price_info or mec_cost, re.IGNORECASE)
                if price_match:
                    is_free = False
                    try:
                        price = float(price_match.group(1).replace(",", "."))
                    except ValueError:
                        pass

                # Handle multiple prices (e.g., "Ibercaja: 8€ Básico: 10€") - use lowest
                all_prices = re.findall(r"(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?)", price_info or mec_cost, re.IGNORECASE)
                if len(all_prices) > 1:
                    try:
                        prices = [float(p.replace(",", ".")) for p in all_prices]
                        price = min(prices)  # Use lowest price as base
                    except ValueError:
                        pass

                # Clean price_info: remove price amounts since we have numeric price
                # "Entradas: 6€ * info..." → "info..."
                # "Precio cliente Ibercaja: 8,00€ Básico: 10,00€" → keep as has multiple tiers
                if price is not None and price_info:
                    if len(all_prices) > 1:
                        # Multiple prices = keep original (has tier info like "Ibercaja: 8€ Básico: 10€")
                        pass
                    else:
                        # Single price - remove the price from info, keep extra details
                        # Remove patterns like "6€", "Entradas: 6€", "Precio: 10 euros"
                        cleaned_info = re.sub(
                            r"(?:entradas?|precio|entrada)?\s*:?\s*\d+(?:[.,]\d{1,2})?\s*(?:€|euros?)\s*",
                            "",
                            price_info,
                            flags=re.IGNORECASE,
                        ).strip()
                        # Remove leading punctuation/separators
                        cleaned_info = re.sub(r"^[\*\-\|/]+\s*", "", cleaned_info).strip()
                        # If we still have meaningful info, use it
                        if cleaned_info and len(cleaned_info) > 5:
                            price_info = cleaned_info
                        else:
                            # Only had price, no extra info
                            price_info = None

            # Category from MEC
            category_name = raw_data.get("mec_category", "")

            # Image from summary_html or content:encoded (HTML with <img>)
            # MEC feeds often put image in summary_html
            summary = raw_data.get("summary_html", "")
            content = raw_data.get("content_encoded", "")
            image_url = self._extract_mec_image(summary) or self._extract_mec_image(content)

            # Description from content (remove HTML)
            description = self._extract_mec_description(content)

            # Extract contact info from description (email, phone for registration)
            contact_email, contact_phone = self._extract_contact_from_text(description or "")

            # Check description for registration keywords (even if mec_cost didn't mention it)
            if not requires_registration and description:
                desc_lower = description.lower()
                if any(w in desc_lower for w in [
                    "inscribirse", "inscripción", "inscripciones", "inscripcion",
                    "reserva previa", "hay que reservar", "reservar plaza",
                    "apuntarse", "plazas limitadas", "aforo limitado",
                ]):
                    requires_registration = True

            # Build registration_info if requires_registration but no URL
            registration_info = None
            if requires_registration and (contact_email or contact_phone):
                parts = []
                if contact_phone:
                    parts.append(f"Tel: {contact_phone}")
                if contact_email:
                    parts.append(f"Email: {contact_email}")
                registration_info = " / ".join(parts)

            # Build contact object if we have email or phone
            contact = None
            if contact_email or contact_phone:
                contact = EventContact(
                    email=contact_email,
                    phone=contact_phone,
                    info="Información de inscripción" if requires_registration else None,
                )

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
                comunidad_autonoma=self.ccaa,
                source_id=self.source_id,
                external_url=external_url,
                external_id=external_id,
                source_image_url=image_url,
                category_name=category_name,
                price_info=price_info,
                price=price,
                is_free=is_free,
                requires_registration=requires_registration,
                registration_info=registration_info,
                contact=contact,
                category_slugs=[],  # Filled by LLM enricher
            )

        except Exception as e:
            self.logger.warning(
                "mec_parse_error",
                error=str(e),
                title=raw_data.get("title", "")[:50],
            )
            return None

    def _parse_ical_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse iCal/VCALENDAR format VEVENT into EventCreate."""
        try:
            # Title
            title = html.unescape(raw_data.get("title", "")).strip()
            if not title:
                return None

            # Dates from parsed iCal
            start_date = raw_data.get("start_date")
            if not start_date:
                return None

            end_date = raw_data.get("end_date")
            start_time_val = raw_data.get("start_time")

            # External ID and URL
            uid = raw_data.get("uid", "")
            external_id = f"{self.source_id}_{uid}" if uid else None
            external_url = raw_data.get("url", "")

            # Description - clean up escaped characters
            description = raw_data.get("description", "")
            if description:
                # Clean escaped newlines and commas from iCal format
                description = description.replace("\\n", "\n").replace("\\,", ",")
                # Remove excessive whitespace
                description = re.sub(r"\n{3,}", "\n\n", description).strip()
                # Truncate if too long
                if len(description) > 2000:
                    description = description[:2000] + "..."

            # Location parsing - Cantabria format: "City, City, Region"
            location = raw_data.get("location", "")
            venue_name = None
            city = None

            if location:
                # Clean escaped commas
                location = location.replace("\\,", ",")
                # Split by comma - format: "Castro Urdiales, Castro Urdiales, Asón-Agüera"
                parts = [p.strip() for p in location.split(",")]
                if len(parts) >= 2:
                    city = parts[0]  # First part is usually the city
                    # If first two parts are the same, just use one
                    if len(parts) >= 2 and parts[0].lower() == parts[1].lower():
                        city = parts[0]
                    venue_name = parts[0] if len(parts) > 2 else None
                elif len(parts) == 1:
                    city = parts[0]

            # Province is always Cantabria (uniprovincial)
            province = self.rss_config.default_province or "Cantabria"

            # Categories
            categories = raw_data.get("categories", [])
            category_name = categories[0] if categories else None

            # Check for free indicators in description
            is_free = None
            if description:
                desc_lower = description.lower()
                if any(w in desc_lower for w in ["gratis", "gratuito", "gratuita", "entrada libre"]):
                    is_free = True

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
                comunidad_autonoma=self.ccaa,
                source_id=self.source_id,
                external_url=external_url,
                external_id=external_id,
                category_name=category_name,
                is_free=is_free,
                category_slugs=[],  # Filled by LLM enricher
            )

        except Exception as e:
            self.logger.warning(
                "ical_parse_error",
                error=str(e),
                title=raw_data.get("title", "")[:50],
            )
            return None

    def _parse_cultura_gal_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse cultura.gal format RSS item (HTML in summary)."""
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
    # MEC (MODERN EVENTS CALENDAR) PARSING HELPERS
    # ============================================================

    def _extract_mec_image(self, content_html: str) -> str | None:
        """Extract image URL from MEC content:encoded HTML.

        MEC typically includes images in various formats:
        - <img src="...">
        - wp-content/uploads paths
        """
        # Try to find <img> tag with src attribute
        match = re.search(
            r'<img[^>]+src="([^"]+)"',
            content_html,
            re.IGNORECASE,
        )
        if match:
            url = match.group(1)
            # Skip small icons and default images
            if "icon" not in url.lower() and "default" not in url.lower():
                return url
        return None

    def _extract_mec_description(self, content_html: str) -> str | None:
        """Extract clean description text from MEC content.

        Removes HTML tags and cleans up the text.
        """
        if not content_html:
            return None

        # Remove img tags completely (we extract image separately)
        text = re.sub(r"<img[^>]*>", "", content_html)

        # Remove style and script tags with their content
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)

        # Replace common block elements with newlines
        text = re.sub(r"</?(p|div|br|li|ul|ol)[^>]*>", "\n", text)

        # Remove remaining HTML tags
        text = re.sub(r"<[^>]+>", "", text)

        # Decode HTML entities
        text = html.unescape(text)

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]

        # Skip very short descriptions (likely just date info)
        result = "\n\n".join(lines)
        if len(result) < 50:
            return None

        # Remove WordPress RSS footer ("La entrada X se publicó primero en Y")
        result = re.sub(
            r"\s*La entrada .+ se publicó primero en .+\.?\s*$",
            "",
            result,
            flags=re.IGNORECASE,
        ).strip()

        return result if result else None

    def _extract_contact_from_text(self, text: str) -> tuple[str | None, str | None]:
        """Extract email and phone from text (for registration contact).

        Args:
            text: Description or content text

        Returns:
            Tuple of (email, phone) - either can be None
        """
        if not text:
            return None, None

        # Extract email
        email = None
        email_match = re.search(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            text,
        )
        if email_match:
            email = email_match.group(0)

        # Extract Spanish phone numbers (9 digits, may have spaces/dots)
        phone = None
        # Pattern: 974 243 760 or 974243760 or 974-243-760 or +34 974 243 760
        phone_match = re.search(
            r"(?:\+34\s?)?(?:9[0-9]{2}[\s.-]?[0-9]{3}[\s.-]?[0-9]{3})",
            text,
        )
        if phone_match:
            # Normalize phone: remove spaces/dots, keep +34 if present
            raw_phone = phone_match.group(0)
            phone = re.sub(r"[\s.-]", "", raw_phone)
            if not phone.startswith("+"):
                phone = "+34 " + phone[:3] + " " + phone[3:6] + " " + phone[6:]

        return email, phone


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
