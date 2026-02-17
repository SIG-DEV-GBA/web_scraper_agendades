"""La Rioja Agenda adapter - LARIOJA.COM cultural events.

Source: https://agenda.larioja.com/
Tier: Bronze (HTML scraping with JSON-LD structured data)
CCAA: La Rioja (uniprovincial)

This source has excellent structured data via Schema.org JSON-LD in detail pages.
"""

import json
import re
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventContact, LocationType
from src.logging import get_logger
from src.utils.contacts import extract_contact_info, extract_registration_info

logger = get_logger(__name__)


@register_adapter("larioja_agenda")
class LaRiojaAgendaAdapter(BaseAdapter):
    """Adapter for Agenda La Rioja - LARIOJA.COM."""

    source_id = "larioja_agenda"
    source_name = "Agenda La Rioja - LARIOJA.COM"
    source_url = "https://agenda.larioja.com/"
    ccaa = "La Rioja"
    ccaa_code = "LO"
    province = "La Rioja"
    adapter_type = AdapterType.STATIC  # Server-rendered, no JS needed
    tier = "bronze"

    # Scraping config
    BASE_URL = "https://agenda.larioja.com"

    # CSS Selectors - Listing page
    EVENT_CARD_SELECTOR = "article"
    TITLE_SELECTOR = ".voc-agenda-titulo a, .voc-agenda-titulo2 a"
    LINK_SELECTOR = ".voc-agenda-titulo a, .voc-agenda-titulo2 a, a.voc-horizontal"
    LOCATION_SELECTOR = ".voc-agenda-localidad"
    IMAGE_SELECTOR = "img"

    # Categories mapping
    CATEGORY_MAP = {
        "cineclub": "Cine",
        "conciertos": "Conciertos",
        "conferencias": "Conferencias",
        "espectaculos": "Espectaculos",
        "exposiciones": "Exposiciones",
        "fiestas": "Fiestas",
        "libros": "Literatura",
        "musica-clasica": "Musica Clasica",
        "planes-con-ninos": "Infantil",
        "teatro": "Teatro",
        "varios": "Otros",
        "visitas-guiadas": "Visitas Guiadas",
    }

    # Pagination config
    LISTING_URL = "https://agenda.larioja.com/eventos/la-rioja/listado.html"
    MAX_PAGES = 10  # Safety limit

    async def fetch_events(self, enrich: bool = True, fetch_details: bool = True, max_events: int = 100, **kwargs) -> list[dict[str, Any]]:
        """Fetch events from Agenda La Rioja with pagination.

        The site uses pagination via /eventos/la-rioja/listado.html?pag=X
        Each page contains ~10 events.

        Args:
            enrich: Not used (LLM enrichment done in pipeline)
            fetch_details: If True, fetch detail pages for full data
            max_events: Maximum number of events to fetch (default: 100)

        Returns:
            List of raw event dictionaries
        """
        events = []
        seen_ids = set()  # Avoid duplicates across pages

        try:
            page = 1
            while len(events) < max_events and page <= self.MAX_PAGES:
                # Build URL with pagination
                url = f"{self.LISTING_URL}?pag={page}"
                self.logger.info("fetching_larioja", url=url, page=page)

                response = await self.fetch_url(url)
                html = response.text

                # Parse listing
                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select(self.EVENT_CARD_SELECTOR)

                if not cards:
                    self.logger.info("larioja_no_more_pages", page=page)
                    break

                page_events = 0
                for card in cards:
                    event = self._parse_card(card)
                    if event:
                        # Skip duplicates
                        event_id = event.get("external_id")
                        if event_id and event_id in seen_ids:
                            continue
                        seen_ids.add(event_id)
                        events.append(event)
                        page_events += 1

                        if len(events) >= max_events:
                            break

                self.logger.info("larioja_page_parsed", page=page, events_in_page=page_events, total=len(events))

                # If no new events found, we've reached the end
                if page_events == 0:
                    break

                page += 1

            self.logger.info("larioja_total_found", count=len(events))

            # Fetch detail pages for full data
            if fetch_details and events:
                self.logger.info("fetching_event_details", count=len(events))
                await self._fetch_details(events)

        except Exception as e:
            self.logger.error("larioja_fetch_error", error=str(e))
            raise

        return events

    def _parse_card(self, card: BeautifulSoup) -> dict[str, Any] | None:
        """Parse a single event card from the listing page."""
        try:
            # Title and link
            title_elem = card.select_one(self.TITLE_SELECTOR)
            link_elem = card.select_one(self.LINK_SELECTOR)

            if not title_elem and not link_elem:
                return None

            title = title_elem.get_text(strip=True) if title_elem else None
            link = None

            if link_elem:
                link = link_elem.get("href", "")
                if link and not link.startswith("http"):
                    link = f"{self.BASE_URL}{link}"

            # Skip if no valid event link
            if not link or "/evento/" not in link:
                return None

            # If no title from title element, try to get from link
            if not title and link_elem:
                title = link_elem.get_text(strip=True)

            if not title:
                return None

            # Location (city)
            location_elem = card.select_one(self.LOCATION_SELECTOR)
            city = location_elem.get_text(strip=True) if location_elem else "Logroño"

            # Image
            img_elem = card.select_one(self.IMAGE_SELECTOR)
            image_url = None
            if img_elem:
                src = img_elem.get("src") or img_elem.get("data-src")
                if src:
                    if not src.startswith("http"):
                        image_url = f"{self.BASE_URL}{src}"
                    else:
                        image_url = src

            # Extract external_id from URL
            # URL format: /evento/event-name-831017.html
            external_id = self._extract_id(link)

            # Extract category from URL if present
            category = self._extract_category(link)

            return {
                "title": title,
                "detail_url": link,
                "city": city,
                "image_url": image_url,
                "external_id": f"{self.source_id}_{external_id}",
                "category_name": category,
            }

        except Exception as e:
            self.logger.warning("larioja_card_parse_error", error=str(e))
            return None

    def _extract_id(self, url: str) -> str:
        """Extract event ID from URL."""
        # URL format: /evento/event-name-831017.html
        match = re.search(r"-(\d+)\.html$", url)
        if match:
            return match.group(1)
        # Fallback to slug
        parts = url.rstrip("/").split("/")
        return parts[-1].replace(".html", "") if parts else "unknown"

    def _extract_category(self, url: str) -> str | None:
        """Extract category from URL path."""
        for cat_slug, cat_name in self.CATEGORY_MAP.items():
            if f"/{cat_slug}/" in url:
                return cat_name
        return None

    async def _fetch_details(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages to extract full event data from HTML."""
        for i, event in enumerate(events):
            detail_url = event.get("detail_url")
            if not detail_url:
                continue

            try:
                response = await self.fetch_url(detail_url)
                details = self._parse_detail_page(response.text, detail_url)

                # Store detail title separately to prefer it over listing title
                if details.get("title"):
                    details["detail_title"] = details.pop("title")

                event.update(details)

                if (i + 1) % 10 == 0:
                    self.logger.info("detail_fetch_progress", fetched=i + 1, total=len(events))

            except Exception as e:
                self.logger.warning("detail_fetch_error", url=detail_url, error=str(e))

        self.logger.info(
            "detail_fetch_complete",
            with_dates=sum(1 for e in events if e.get("start_date")),
            total=len(events),
        )

    def _parse_detail_page(self, html: str, url: str) -> dict[str, Any]:
        """Parse detail page extracting data from HTML structure.

        The page has this structure:
        - .voc-agenda-antetitulo → Category
        - article h1 → Title
        - .voc-agenda-localidad-detalle → City
        - span.voc-agenda-lugar + span.voc-agenda-dia pairs → Lugar, Fecha, Hora, Precio
        - article p → Full description
        """
        details = {}
        soup = BeautifulSoup(html, "html.parser")
        article = soup.find("article")

        if not article:
            return details

        # Title from h1 (better than listing)
        h1 = article.find("h1")
        if h1:
            details["title"] = h1.get_text(strip=True)

        # Category from .voc-agenda-antetitulo
        cat_elem = article.select_one(".voc-agenda-antetitulo")
        if cat_elem:
            cat_text = cat_elem.get_text(strip=True)
            # Map to our categories
            cat_lower = cat_text.lower()
            details["category_name"] = self.CATEGORY_MAP.get(cat_lower, cat_text)

        # City from .voc-agenda-localidad-detalle
        city_elem = article.select_one(".voc-agenda-localidad-detalle")
        if city_elem:
            details["city"] = city_elem.get_text(strip=True)

        # Parse label/value pairs: Lugar, Fecha, Hora, Precio
        # Structure: span.voc-agenda-lugar (label) followed by span.voc-agenda-dia (value)
        labels = article.select("span.voc-agenda-lugar")
        values = article.select("span.voc-agenda-dia")

        for label_elem, value_elem in zip(labels, values):
            label = label_elem.get_text(strip=True).lower().rstrip(".")
            value = value_elem.get_text(strip=True)

            if not value:
                continue

            if "lugar" in label:
                details["venue_name"] = value
            elif "fecha" in label:
                # Parse date: "14 de febrero de 2026"
                parsed_date = self._parse_spanish_date(value)
                if parsed_date:
                    details["start_date"] = parsed_date
                    details["end_date"] = parsed_date
            elif "hora" in label:
                # Parse time: "13:00" or "20:00"
                parsed_time = self._parse_time(value)
                if parsed_time:
                    details["start_time"] = parsed_time
            elif "precio" in label:
                # Extract numeric price
                price_match = re.search(r"(\d+(?:[.,]\d+)?)\s*€?", value)
                if price_match:
                    try:
                        details["price"] = float(price_match.group(1).replace(",", "."))
                        details["is_free"] = False
                    except ValueError:
                        pass

                if "gratis" in value.lower() or "gratuito" in value.lower():
                    details["is_free"] = True
                    details["price"] = 0

                # price_info only for additional info (not just the price)
                # Examples: "entradas limitadas", "descuento mayores 65", "De 10 a 24 €"
                value_lower = value.lower()
                # Check if there's more info than just the price
                has_extra_info = any([
                    "limitad" in value_lower,
                    "descuento" in value_lower,
                    "anticipada" in value_lower,
                    "taquilla" in value_lower,
                    "abono" in value_lower,
                    "de " in value_lower and " a " in value_lower,  # Range: "De 10 a 24 €"
                    "desde" in value_lower,
                    "hasta" in value_lower,
                    "incluye" in value_lower,
                    "libre" in value_lower and "entrada" in value_lower,
                ])
                if has_extra_info:
                    details["price_info"] = value

        # Full description from <p> tags in article
        paragraphs = article.find_all("p")
        desc_parts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Skip empty or very short paragraphs
            if text and len(text) > 20:
                desc_parts.append(text)

        if desc_parts:
            details["description"] = "\n\n".join(desc_parts)

        # Image from og:image (usually better quality)
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            img_url = og_image["content"]
            if not img_url.startswith("http"):
                img_url = f"https://{img_url.lstrip('/')}"
            details["image_url"] = img_url

        # No organizer - LARIOJA.COM is a newspaper, not the actual event organizer

        return details

    def _parse_spanish_date(self, text: str) -> date | None:
        """Parse Spanish date format: '14 de febrero de 2026'."""
        months = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }

        # Pattern: day de month de year
        match = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", text.lower())
        if match:
            day = int(match.group(1))
            month_name = match.group(2)
            year = int(match.group(3))
            month = months.get(month_name)
            if month:
                try:
                    return date(year, month, day)
                except ValueError:
                    pass
        return None

    def _parse_time(self, text: str) -> str | None:
        """Parse time format: '13:00' or '20:00 h'."""
        match = re.search(r"(\d{1,2}):(\d{2})", text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            return f"{hour:02d}:{minute:02d}"
        return None

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            # Prefer title from detail page (more complete) over listing title
            title = raw_data.get("detail_title") or raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            # Extract contact and registration from description
            description = raw_data.get("description")
            contact = None
            registration_url = None
            requires_registration = False
            registration_info = None

            if description:
                contact_data = extract_contact_info(description)
                if contact_data["email"] or contact_data["phone"]:
                    contact = EventContact(
                        email=contact_data["email"],
                        phone=contact_data["phone"],
                    )

                reg_data = extract_registration_info(description)
                if reg_data["registration_url"]:
                    registration_url = reg_data["registration_url"]
                if reg_data["requires_registration"]:
                    requires_registration = reg_data["requires_registration"]
                if reg_data["registration_info"]:
                    registration_info = reg_data["registration_info"]

            # Price info - prefer price_info from HTML, fallback to price number
            price_info = raw_data.get("price_info")
            price = raw_data.get("price")
            is_free = raw_data.get("is_free")

            # Ensure end_date >= start_date
            end_date = raw_data.get("end_date") or start_date
            if end_date and start_date and end_date < start_date:
                # Swap if inverted
                start_date, end_date = end_date, start_date

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=end_date,
                start_time=raw_data.get("start_time"),
                description=description,
                venue_name=raw_data.get("venue_name"),
                city=raw_data.get("city", "Logroño"),
                province=self.province,
                comunidad_autonoma=self.ccaa,
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_name=raw_data.get("category_name"),
                contact=contact,
                registration_url=registration_url,
                requires_registration=requires_registration,
                registration_info=registration_info,
                price=price,
                price_info=price_info,
                is_free=is_free,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("larioja_parse_error", error=str(e), raw=str(raw_data)[:200])
            return None
