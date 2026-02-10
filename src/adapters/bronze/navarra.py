"""Navarra Cultura adapter - Gobierno de Navarra cultural events.

Source: https://www.culturanavarra.es/es/agenda
Tier: Bronze (HTML scraping, no JS needed)
CCAA: Navarra (uniprovincial)
"""

import re
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventContact, EventOrganizer, LocationType, OrganizerType
from src.logging import get_logger
from src.utils.contacts import extract_contact_info, extract_registration_info

logger = get_logger(__name__)


@register_adapter("navarra_cultura")
class NavarraAdapter(BaseAdapter):
    """Adapter for Cultura Navarra - Gobierno de Navarra."""

    source_id = "navarra_cultura"
    source_name = "Cultura Navarra - Gobierno de Navarra"
    source_url = "https://www.culturanavarra.es/es/agenda"
    ccaa = "Navarra"
    ccaa_code = "NA"
    province = "Navarra"
    adapter_type = AdapterType.STATIC  # Server-rendered PHP, no JS needed

    # Scraping config
    BASE_URL = "https://www.culturanavarra.es"

    # CSS Selectors - Listing page
    EVENT_CARD_SELECTOR = ".agenda_evento"
    TITLE_SELECTOR = "h4 a"
    LINK_SELECTOR = "h4 a"
    LOCATION_SELECTOR = ".lugar"
    IMAGE_SELECTOR = "img"
    # Detail page
    DETAIL_DATE_SELECTOR = ".fecha"  # Format: DD/MM/YYYY - DD/MM/YYYY

    async def fetch_events(self, enrich: bool = True, fetch_details: bool = True) -> list[dict[str, Any]]:
        """Fetch events from Cultura Navarra.

        Args:
            enrich: Not used (LLM enrichment done in pipeline)
            fetch_details: If True, fetch detail pages for descriptions

        Returns:
            List of raw event dictionaries
        """
        events = []

        try:
            # Fetch listing page
            self.logger.info("fetching_navarra", url=self.source_url)
            response = await self.fetch_url(self.source_url)
            html = response.text

            # Parse listing
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(self.EVENT_CARD_SELECTOR)
            self.logger.info("navarra_cards_found", count=len(cards))

            for card in cards:
                event = self._parse_card(card)
                if event:
                    events.append(event)

            # Fetch detail pages if requested
            if fetch_details and events:
                self.logger.info("fetching_event_details", count=len(events))
                await self._fetch_details(events)

        except Exception as e:
            self.logger.error("navarra_fetch_error", error=str(e))
            raise

        return events

    def _parse_card(self, card: BeautifulSoup) -> dict[str, Any] | None:
        """Parse a single event card from the listing page."""
        try:
            # Title and link
            title_elem = card.select_one(self.TITLE_SELECTOR)
            if not title_elem:
                return None

            title = title_elem.get_text(strip=True)
            link = title_elem.get("href", "")
            if link and not link.startswith("http"):
                # Ensure proper URL joining
                if not link.startswith("/"):
                    link = "/" + link
                link = self.BASE_URL + link

            # Dates come from detail page, not listing
            start_date = None
            end_date = None

            # Location (venue name)
            location_elem = card.select_one(self.LOCATION_SELECTOR)
            venue_name = location_elem.get_text(strip=True) if location_elem else None

            # Image
            img_elem = card.select_one(self.IMAGE_SELECTOR)
            image_url = None
            if img_elem:
                src = img_elem.get("src") or img_elem.get("data-src")
                if src:
                    # Convert thumbnail to full size
                    if "imagen_escala.php" in src:
                        # Extract original image path
                        match = re.search(r"imagen=(.+)$", src)
                        if match:
                            image_url = f"{self.BASE_URL}/{match.group(1)}"
                    elif not src.startswith("http"):
                        image_url = f"{self.BASE_URL}/{src.lstrip('/')}"
                    else:
                        image_url = src

            # Generate external_id from URL slug
            external_id = self._extract_slug(link)

            return {
                "title": title,
                "detail_url": link,
                "start_date": start_date,
                "end_date": end_date,
                "venue_name": venue_name,
                "image_url": image_url,
                "external_id": f"{self.source_id}_{external_id}",
            }

        except Exception as e:
            self.logger.warning("navarra_card_parse_error", error=str(e))
            return None

    def _parse_date_range(self, date_text: str) -> tuple[date | None, date | None]:
        """Parse date range from text like '15/05/2025 - 26/03/2026' or 'DD/MM/YYYY'."""
        if not date_text:
            return None, None

        # Format: DD/MM/YYYY - DD/MM/YYYY or DD/MM/YYYY
        pattern = r"(\d{1,2})/(\d{1,2})/(\d{4})"
        matches = re.findall(pattern, date_text)

        dates = []
        for day, month, year in matches:
            try:
                dates.append(date(int(year), int(month), int(day)))
            except ValueError:
                pass

        if len(dates) >= 2:
            return dates[0], dates[1]
        elif len(dates) == 1:
            return dates[0], dates[0]
        return None, None

    def _extract_slug(self, url: str) -> str:
        """Extract slug from URL for external_id."""
        # URL format: https://www.culturanavarra.es/es/agenda/YYYY-MM-DD/categoria/slug
        parts = url.rstrip("/").split("/")
        return parts[-1] if parts else "unknown"

    async def _fetch_details(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages to get descriptions and additional info."""
        for i, event in enumerate(events):
            detail_url = event.get("detail_url")
            if not detail_url:
                continue

            try:
                response = await self.fetch_url(detail_url)
                details = self._parse_detail_page(response.text, detail_url)
                event.update(details)

                if (i + 1) % 5 == 0:
                    self.logger.info("detail_fetch_progress", fetched=i + 1, total=len(events))

            except Exception as e:
                self.logger.warning("detail_fetch_error", url=detail_url, error=str(e))

        self.logger.info("detail_fetch_complete", with_description=sum(1 for e in events if e.get("description")))

    def _parse_detail_page(self, html: str, url: str) -> dict[str, Any]:
        """Parse detail page for description and additional fields."""
        details = {}
        soup = BeautifulSoup(html, "html.parser")

        # Date range from .fecha element (format: DD/MM/YYYY - DD/MM/YYYY)
        date_elem = soup.select_one(".fecha")
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            start_date, end_date = self._parse_date_range(date_text)
            if start_date:
                details["start_date"] = start_date
            if end_date:
                details["end_date"] = end_date

        # Description from multiple possible selectors
        for selector in [".entradilla", ".descripcion", "article .content", ".event-description"]:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                desc_text = desc_elem.get_text(separator="\n\n", strip=True)
                desc_text = re.sub(r'\n{3,}', '\n\n', desc_text)
                if desc_text and len(desc_text) > 20:
                    details["description"] = desc_text
                    break

        # Fallback to meta description
        if not details.get("description"):
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                details["description"] = meta_desc.get("content", "").strip()

        # Category from URL path
        # URL format: /es/agenda/YYYY-MM-DD/categoria/slug
        url_parts = url.split("/")
        for i, part in enumerate(url_parts):
            if re.match(r"\d{4}-\d{2}-\d{2}", part) and i + 1 < len(url_parts):
                category = url_parts[i + 1]
                # Convert slug to readable name
                details["category_name"] = category.replace("-", " ").title()
                break

        # City from location info
        location_elem = soup.select_one(".lugar, .location, .venue")
        if location_elem:
            location_text = location_elem.get_text(strip=True)
            # Try to extract city (usually after venue name)
            if "Pamplona" in location_text or "Iruña" in location_text:
                details["city"] = "Pamplona"
            elif "," in location_text:
                # Venue, City format
                parts = location_text.split(",")
                if len(parts) >= 2:
                    details["city"] = parts[-1].strip()

        # Default city for Navarra government events
        if not details.get("city"):
            details["city"] = "Pamplona"

        # Organizer with logo from Navarra government website
        details["organizer_name"] = "Dirección General de Cultura - Gobierno de Navarra"
        details["organizer_type"] = OrganizerType.INSTITUCION
        details["organizer_url"] = "https://www.navarra.es/es/cultura"
        details["organizer_logo_url"] = "https://www.google.com/s2/favicons?domain=navarra.es&sz=64"

        # Better quality image from detail page
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            img_url = og_image["content"]
            if not img_url.startswith("http"):
                img_url = f"{self.BASE_URL}/{img_url.lstrip('/')}"
            details["image_url"] = img_url

        return details

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            # Build organizer with logo
            organizer = None
            if raw_data.get("organizer_name"):
                organizer = EventOrganizer(
                    name=raw_data["organizer_name"],
                    type=raw_data.get("organizer_type", OrganizerType.INSTITUCION),
                    url=raw_data.get("organizer_url"),
                    logo_url=raw_data.get("organizer_logo_url"),
                )

            # Extract contact and registration from description
            description = raw_data.get("description")
            contact = None
            registration_url = None
            requires_registration = False
            registration_info = None

            if description:
                # Contact extraction
                contact_data = extract_contact_info(description)
                if contact_data["email"] or contact_data["phone"]:
                    contact = EventContact(
                        email=contact_data["email"],
                        phone=contact_data["phone"],
                    )

                # Registration extraction
                reg_data = extract_registration_info(description)
                if reg_data["registration_url"]:
                    registration_url = reg_data["registration_url"]
                if reg_data["requires_registration"]:
                    requires_registration = reg_data["requires_registration"]
                if reg_data["registration_info"]:
                    registration_info = reg_data["registration_info"]

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=raw_data.get("end_date") or start_date,
                description=description,
                venue_name=raw_data.get("venue_name"),
                city=raw_data.get("city", "Pamplona"),
                province=self.province,
                comunidad_autonoma=self.ccaa,
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_name=raw_data.get("category_name"),
                organizer=organizer,
                contact=contact,
                registration_url=registration_url,
                requires_registration=requires_registration,
                registration_info=registration_info,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("navarra_parse_error", error=str(e), raw=str(raw_data)[:200])
            return None
