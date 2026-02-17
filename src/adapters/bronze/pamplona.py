"""Pamplona Ayuntamiento adapter - Official Pamplona city events.

Source: https://www.pamplona.es/actualidad/eventos
Tier: Bronze (HTML scraping, Drupal CMS)
CCAA: Navarra (uniprovincial)

This source provides events from the official Pamplona city council website.
Uses Drupal CMS with standard HTML rendering - no JS needed.
"""

import re
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType, OrganizerType
from src.logging import get_logger
from src.utils.contacts import extract_contact_info, extract_registration_info

logger = get_logger(__name__)


@register_adapter("pamplona")
class PamplonaAdapter(BaseAdapter):
    """Adapter for Pamplona City Council events."""

    source_id = "pamplona"
    source_name = "Ayuntamiento de Pamplona - Agenda de Eventos"
    source_url = "https://www.pamplona.es/actualidad/eventos"
    ccaa = "Navarra"
    ccaa_code = "NA"
    province = "Navarra"
    adapter_type = AdapterType.STATIC  # Drupal CMS, server-rendered
    tier = "bronze"

    # Scraping config
    BASE_URL = "https://www.pamplona.es"
    AGENDA_URL = "https://www.pamplona.es/actualidad/eventos"

    # Pagination - Drupal uses ?page=X (0-based)
    MAX_PAGES = 10  # Safety limit (site has ~20 pages)

    # CSS Selectors - Drupal structure
    EVENT_CARD_SELECTOR = ".views-row article.event.teaser"
    TITLE_SELECTOR = ".field--name-field-display-title h3 a"
    DATE_SELECTOR = ".field--name-field-event-date-query time"
    CATEGORY_SELECTOR = ".field--name-field-theme .field--item"
    IMAGE_SELECTOR = ".field--name-field-event-image img"
    VENUE_SELECTOR = ".field--name-field-event-info a"

    async def fetch_events(
        self, enrich: bool = True, fetch_details: bool = True, max_events: int = 100, **kwargs
    ) -> list[dict[str, Any]]:
        """Fetch events from Pamplona Ayuntamiento with pagination.

        Args:
            enrich: Not used (LLM enrichment done in pipeline)
            fetch_details: If True, fetch detail pages for full data
            max_events: Maximum number of events to fetch

        Returns:
            List of raw event dictionaries
        """
        events = []
        seen_ids = set()

        try:
            page = 0
            while len(events) < max_events and page < self.MAX_PAGES:
                # Build URL with pagination
                url = f"{self.AGENDA_URL}?page={page}" if page > 0 else self.AGENDA_URL
                self.logger.info("fetching_pamplona", url=url, page=page)

                response = await self.fetch_url(url)
                html = response.text

                # Parse listing
                soup = BeautifulSoup(html, "html.parser")
                cards = soup.select(self.EVENT_CARD_SELECTOR)

                if not cards:
                    self.logger.info("pamplona_no_more_pages", page=page)
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

                self.logger.info(
                    "pamplona_page_parsed", page=page, events_in_page=page_events, total=len(events)
                )

                # If fewer events than expected, likely last page
                if page_events < 5:
                    break

                page += 1

            self.logger.info("pamplona_total_found", count=len(events))

            # Fetch detail pages for full data
            if fetch_details and events:
                self.logger.info("fetching_event_details", count=len(events))
                await self._fetch_details(events)

        except Exception as e:
            self.logger.error("pamplona_fetch_error", error=str(e))
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
                link = f"{self.BASE_URL}{link}"

            if not link or "/actualidad/eventos/" not in link:
                return None

            # External ID from URL slug
            slug = link.split("/actualidad/eventos/")[-1].rstrip("/")
            external_id = f"{self.source_id}_{slug}"

            # Date from time element (ISO format in datetime attribute)
            start_date = None
            end_date = None
            date_elems = card.select(self.DATE_SELECTOR)
            if date_elems:
                for date_elem in date_elems:
                    dt_str = date_elem.get("datetime", "")
                    if dt_str:
                        parsed = self._parse_iso_date(dt_str)
                        if parsed:
                            if start_date is None:
                                start_date = parsed
                            else:
                                end_date = parsed

            # Category from theme field
            category = None
            cat_elem = card.select_one(self.CATEGORY_SELECTOR)
            if cat_elem:
                category = cat_elem.get_text(strip=True)

            # Venue from event-info field
            venue_name = None
            venue_elem = card.select_one(self.VENUE_SELECTOR)
            if venue_elem:
                venue_name = venue_elem.get_text(strip=True)

            # Image
            image_url = None
            img_elem = card.select_one(self.IMAGE_SELECTOR)
            if img_elem:
                src = img_elem.get("src") or img_elem.get("data-src")
                if src:
                    if src.startswith("/"):
                        image_url = f"{self.BASE_URL}{src}"
                    elif src.startswith("http"):
                        image_url = src

            return {
                "title": title,
                "detail_url": link,
                "external_id": external_id,
                "start_date": start_date,
                "end_date": end_date or start_date,
                "category_name": category,
                "venue_name": venue_name,
                "image_url": image_url,
                "city": "Pamplona",  # All events are in Pamplona
            }

        except Exception as e:
            self.logger.warning("pamplona_card_parse_error", error=str(e))
            return None

    def _parse_iso_date(self, dt_str: str) -> date | None:
        """Parse ISO 8601 datetime string to date."""
        try:
            # Format: 2026-02-09T12:00:00Z
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt.date()
        except (ValueError, TypeError):
            return None

    async def _fetch_details(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages to extract full event data."""
        for i, event in enumerate(events):
            detail_url = event.get("detail_url")
            if not detail_url:
                continue

            try:
                response = await self.fetch_url(detail_url)
                details = self._parse_detail_page(response.text, detail_url)

                # Update event with details (don't overwrite existing values with None)
                for key, value in details.items():
                    if value is not None and (event.get(key) is None or key == "description"):
                        event[key] = value

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
        """Parse detail page for full event information."""
        details = {}
        soup = BeautifulSoup(html, "html.parser")

        # Title from h1
        h1 = soup.find("h1")
        if h1:
            details["title"] = h1.get_text(strip=True)

        # Description from content area
        # Look for body field or content text
        content_area = soup.select_one(".field--name-body, .field--name-field-body, .content-text")
        if content_area:
            paragraphs = content_area.find_all("p")
            desc_parts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            if desc_parts:
                details["description"] = "\n\n".join(desc_parts)

        # Fallback to og:description
        if not details.get("description"):
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                details["description"] = og_desc["content"]

        # Image from og:image or main image
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            img_url = og_image["content"]
            if img_url.startswith("/"):
                img_url = f"{self.BASE_URL}{img_url}"
            details["image_url"] = img_url

        # Venue from field-event-info
        venue_field = soup.select_one(".field--name-field-event-info a")
        if venue_field:
            details["venue_name"] = venue_field.get_text(strip=True)

        # Organizer from field-management-entity
        org_field = soup.select_one(
            ".field--name-field-management-entity a, "
            ".field--name-field-organizer a"
        )
        if org_field:
            details["organizer_name"] = org_field.get_text(strip=True)
            details["organizer_type"] = OrganizerType.INSTITUCION
            org_url = org_field.get("href", "")
            if org_url and not org_url.startswith("http"):
                org_url = f"{self.BASE_URL}{org_url}"
            details["organizer_url"] = org_url if org_url.startswith("http") else None

        # Default organizer if not found
        if not details.get("organizer_name"):
            details["organizer_name"] = "Ayuntamiento de Pamplona"
            details["organizer_type"] = OrganizerType.INSTITUCION
            details["organizer_url"] = "https://www.pamplona.es"
            details["organizer_logo_url"] = "https://www.google.com/s2/favicons?domain=pamplona.es&sz=64"

        # Price from admission field
        price_field = soup.select_one(
            ".field--name-field-admission, "
            ".field--name-field-price, "
            ".field--name-field-entry-fee"
        )
        if price_field:
            price_text = price_field.get_text(strip=True)
            details["price_info"] = price_text

            # Try to extract numeric price
            price_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:€|euros?)", price_text, re.IGNORECASE)
            if price_match:
                try:
                    details["price"] = float(price_match.group(1).replace(",", "."))
                    details["is_free"] = False
                except ValueError:
                    pass

            # Check for free
            if "gratis" in price_text.lower() or "gratuito" in price_text.lower():
                details["is_free"] = True
                details["price"] = 0

        # Time info
        time_field = soup.select_one(
            ".field--name-field-time, "
            ".field--name-field-schedule, "
            ".field--name-field-event-time"
        )
        if time_field:
            time_text = time_field.get_text(strip=True)
            # Try to extract time
            time_match = re.search(r"(\d{1,2}):(\d{2})", time_text)
            if time_match:
                details["start_time"] = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

        # Category from theme field
        cat_field = soup.select_one(".field--name-field-theme .field--item")
        if cat_field:
            details["category_name"] = cat_field.get_text(strip=True)

        return details

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            # Ensure end_date >= start_date
            end_date = raw_data.get("end_date") or start_date
            if end_date and start_date and end_date < start_date:
                start_date, end_date = end_date, start_date

            # Build organizer
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
                contact_data = extract_contact_info(description)
                if contact_data["email"] or contact_data["phone"]:
                    from src.core.event_model import EventContact

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

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=end_date,
                start_time=raw_data.get("start_time"),
                description=description,
                venue_name=raw_data.get("venue_name"),
                city="Pamplona",
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
                price=raw_data.get("price"),
                price_info=raw_data.get("price_info"),
                is_free=raw_data.get("is_free"),
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("pamplona_parse_error", error=str(e), raw=str(raw_data)[:200])
            return None
