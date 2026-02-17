"""Visit Navarra adapter - Official Navarra tourism cultural events.

Source: https://www.visitnavarra.es/es/agenda
Tier: Bronze (HTML scraping, Liferay CMS)
CCAA: Navarra (uniprovincial)

This source provides tourism and cultural events from the official
Navarra tourism website. Uses Liferay CMS with server-rendered HTML.
"""

import re
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.config.settings import get_settings
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType, OrganizerType
from src.core.firecrawl_client import get_firecrawl_client
from src.logging import get_logger
from src.utils.contacts import extract_contact_info, extract_registration_info

logger = get_logger(__name__)


@register_adapter("visitnavarra")
class VisitNavarraAdapter(BaseAdapter):
    """Adapter for Visit Navarra - Official Navarra Tourism."""

    source_id = "visitnavarra"
    source_name = "Visit Navarra - Turismo de Navarra"
    source_url = "https://www.visitnavarra.es/es/agenda"
    ccaa = "Navarra"
    ccaa_code = "NA"
    province = "Navarra"
    adapter_type = AdapterType.STATIC  # Liferay CMS, server-rendered
    tier = "bronze"

    # Scraping config
    BASE_URL = "https://www.visitnavarra.es"
    AGENDA_URL = "https://www.visitnavarra.es/es/agenda"

    # Pagination - Liferay uses delta parameter
    MAX_PAGES = 10  # Safety limit
    EVENTS_PER_PAGE = 10

    # Month mapping for date parsing
    MONTHS_ES = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    }
    MONTHS_EN = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    async def fetch_events(self, enrich: bool = True, fetch_details: bool = True, max_events: int = 100, **kwargs) -> list[dict[str, Any]]:
        """Fetch events from Visit Navarra with pagination using Playwright.

        The site uses JavaScript pagination with a "Mostrar" dropdown (8/12/24/48 items).
        We use Playwright directly for full browser control.

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
            self.logger.info("fetching_visitnavarra_playwright", url=self.AGENDA_URL)

            # Use Playwright to get all events with pagination
            # This collects event links from ALL pages into self._collected_event_data
            await self._fetch_with_playwright(items_per_page=48)

            # Process collected links from all pages
            if hasattr(self, "_collected_event_data") and self._collected_event_data:
                for link in self._collected_event_data:
                    event_data = self._parse_link_element(link)
                    if event_data:
                        if event_data["external_id"] not in seen_ids:
                            seen_ids.add(event_data["external_id"])
                            events.append(event_data)

                            if len(events) >= max_events:
                                break

            self.logger.info("visitnavarra_events_collected", count=len(events))

            # Fetch detail pages
            if fetch_details and events:
                self.logger.info("fetching_event_details", count=len(events))
                await self._fetch_details(events)

        except Exception as e:
            self.logger.error("visitnavarra_fetch_error", error=str(e))
            raise

        return events

    async def _fetch_with_playwright(self, items_per_page: int = 48) -> str:
        """Fetch all pages from agenda using Playwright.

        The site uses JavaScript pagination via processForm(false, pageNumber).
        We navigate through all pages and collect all event links.

        Args:
            items_per_page: Not used (kept for API compatibility)

        Returns:
            Combined HTML content with all events
        """
        page = None
        all_event_links = []
        seen_slugs = set()

        try:
            page = await self.get_page()

            # Navigate to agenda
            self.logger.info("playwright_navigating", url=self.AGENDA_URL)
            await page.goto(self.AGENDA_URL, wait_until="networkidle", timeout=30000)

            # Close cookie banner if present
            try:
                cookie_btn = await page.query_selector(
                    "#cookiescript_accept, .cookie-accept, button:has-text('Aceptar'), "
                    "button:has-text('Accept'), [id*='cookie'] button"
                )
                if cookie_btn:
                    await cookie_btn.click()
                    self.logger.info("playwright_cookie_banner_closed")
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Collect events from all pages
            current_page = 1
            max_pages = 6  # Safety limit

            while current_page <= max_pages:
                # Wait for events to load
                await page.wait_for_selector("a[href*='/es/w/']", timeout=10000)

                # Get current page HTML
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                # Find all event links
                links = soup.find_all("a", href=lambda h: h and "/es/w/" in h)
                new_events = 0

                for link in links:
                    href = link.get("href", "")
                    slug = href.split("/es/w/")[-1].split("?")[0].rstrip("/")
                    if slug and slug not in seen_slugs:
                        seen_slugs.add(slug)
                        all_event_links.append(link)
                        new_events += 1

                self.logger.info("playwright_page_scraped", page=current_page, new_events=new_events, total=len(seen_slugs))

                # Check if there's a next page
                next_page = current_page + 1
                next_link = await page.query_selector(f"a[href*='processForm(false, {next_page})'], a:has-text('{next_page}')")

                if not next_link:
                    self.logger.info("playwright_no_more_pages", last_page=current_page)
                    break

                # Click next page
                try:
                    # Execute JavaScript directly for pagination
                    await page.evaluate(f"processForm(false, {next_page})")
                    await page.wait_for_timeout(2000)
                    await page.wait_for_selector("a[href*='/es/w/']", timeout=10000)
                    current_page = next_page
                except Exception as e:
                    self.logger.warning("playwright_next_page_failed", error=str(e)[:100])
                    break

            # Build combined HTML with all unique links
            self.logger.info("playwright_total_events_found", count=len(seen_slugs))

            # Return last page HTML (with all parsed links stored in self._collected_links)
            self._collected_event_data = all_event_links
            return await page.content()

        except Exception as e:
            self.logger.error("playwright_fetch_error", error=str(e))
            raise
        finally:
            if page:
                await page.close()

    def _parse_link_element(self, link) -> dict[str, Any] | None:
        """Parse a single link element into event data.

        Args:
            link: BeautifulSoup link element

        Returns:
            Event data dict or None
        """
        href = link.get("href", "")
        if not href or "/es/w/" not in href:
            return None

        # Clean URL
        clean_href = href.split("?")[0]
        if clean_href.startswith("/"):
            full_url = f"{self.BASE_URL}{clean_href}"
        else:
            full_url = clean_href

        # Extract slug
        slug = clean_href.split("/es/w/")[-1].rstrip("/")
        if not slug:
            return None

        # Get title
        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            return None

        # Get parent for additional data
        parent = link.find_parent(["li", "article", "div"])

        date_text = None
        location = None
        image_url = None

        if parent:
            divs = parent.find_all("div")
            for div in divs:
                text = div.get_text(strip=True)
                if re.match(r"^\d{1,2}\s+\w{3}", text) or "varias fechas" in text.lower():
                    date_text = text
                elif text and text != title and not re.match(r"^\d{1,2}\s+\w{3}", text):
                    if text.lower() not in title.lower() or len(text) < 30:
                        location = text

            img = parent.find("img")
            if img:
                src = img.get("src") or img.get("data-src")
                if src:
                    if src.startswith("/"):
                        image_url = f"{self.BASE_URL}{src}"
                    elif src.startswith("http"):
                        image_url = src

        # Parse dates
        start_date = None
        end_date = None
        if date_text:
            start_date, end_date = self._parse_listing_date(date_text)

        return {
            "title": title,
            "detail_url": full_url,
            "external_id": f"{self.source_id}_{slug}",
            "image_url": image_url,
            "start_date": start_date,
            "end_date": end_date,
            "city": location,
        }

    def _find_event_links(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Find all event links from agenda page."""
        events = []

        # Find all links that match event pattern /es/w/slug
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")

            # Event URLs: /es/w/event-slug (may include ?redirect= param)
            if "/es/w/" in href:
                # Clean URL - remove redirect param for cleaner URLs
                clean_href = href.split("?")[0]
                if clean_href.startswith("/"):
                    full_url = f"{self.BASE_URL}{clean_href}"
                else:
                    full_url = clean_href

                # Extract slug for external_id
                slug = clean_href.split("/es/w/")[-1].rstrip("/")

                # Get title from link text
                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                # Get parent container (li or div) for additional data
                parent = link.find_parent(["li", "article", "div"])

                # Extract date and location from sibling divs in parent
                date_text = None
                location = None
                image_url = None

                if parent:
                    # Find all text in sibling divs
                    divs = parent.find_all("div")
                    for div in divs:
                        text = div.get_text(strip=True)
                        # Date pattern: "15 feb - 17 mar" or "17 feb" or "Varias fechas"
                        if re.match(r"^\d{1,2}\s+\w{3}", text) or "varias fechas" in text.lower():
                            date_text = text
                        # Location: typically a city name (not the title, not the date)
                        elif text and text != title and not re.match(r"^\d{1,2}\s+\w{3}", text):
                            # Skip if it's just a repeat of the title
                            if text.lower() not in title.lower():
                                location = text
                            # If text is different from title, it could be city
                            elif len(text) < 30:
                                location = text

                    # Get image if available
                    img = parent.find("img")
                    if img:
                        src = img.get("src") or img.get("data-src")
                        if src:
                            if src.startswith("/"):
                                image_url = f"{self.BASE_URL}{src}"
                            elif src.startswith("http"):
                                image_url = src

                # Parse dates from listing if available
                start_date = None
                end_date = None
                if date_text:
                    start_date, end_date = self._parse_listing_date(date_text)

                events.append({
                    "title": title,
                    "detail_url": full_url,
                    "external_id": f"{self.source_id}_{slug}",
                    "image_url": image_url,
                    "start_date": start_date,
                    "end_date": end_date,
                    "city": location,
                })

        # Deduplicate by external_id
        seen = set()
        unique_events = []
        for e in events:
            if e["external_id"] not in seen:
                seen.add(e["external_id"])
                unique_events.append(e)

        return unique_events

    async def _fetch_details(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages for full event data."""
        # Get Firecrawl client
        settings = get_settings()
        firecrawl = get_firecrawl_client(
            base_url=settings.firecrawl_url,
            api_key=settings.firecrawl_api_key,
        )

        for i, event in enumerate(events):
            detail_url = event.get("detail_url")
            if not detail_url:
                continue

            try:
                # Use Firecrawl for detail pages too
                response = await firecrawl.scrape(
                    detail_url,
                    formats=["html", "markdown"],
                    timeout=30000,
                )

                if not response.success:
                    self.logger.warning("detail_fetch_error", url=detail_url, error=response.error)
                    continue

                html = response.html or ""
                markdown = response.markdown or ""

                if html:
                    details = self._parse_detail_page(html, markdown, detail_url)
                    # Only update fields that we got from detail page
                    # Don't overwrite listing data with None values
                    for key, value in details.items():
                        if value is not None:
                            # For dates and city, only overwrite if we don't have them yet
                            if key in ("start_date", "end_date", "city") and event.get(key) is not None:
                                continue
                            event[key] = value

                if (i + 1) % 5 == 0:
                    self.logger.info("detail_fetch_progress", fetched=i + 1, total=len(events))

            except Exception as e:
                self.logger.warning("detail_fetch_error", url=detail_url, error=str(e))

        self.logger.info(
            "detail_fetch_complete",
            with_dates=sum(1 for e in events if e.get("start_date")),
            total=len(events),
        )

    def _parse_detail_page(self, html: str, markdown: str, url: str) -> dict[str, Any]:
        """Parse detail page for full event information.

        Structure:
        - div.content-text-plan: Main content container
        - #content_text: Description paragraphs
        - ul.features_description_plan: Organizer info (Empresa)
        """
        details = {}
        soup = BeautifulSoup(html, "html.parser")

        # Title from h1 or og:title
        h1 = soup.find("h1")
        if h1:
            details["title"] = h1.get_text(strip=True)
        else:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                details["title"] = og_title["content"]

        # Description from #content_text (main content area)
        content_text = soup.select_one("#content_text")
        if content_text:
            paragraphs = content_text.find_all("p")
            desc_parts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            if desc_parts:
                details["description"] = "\n\n".join(desc_parts)

        # Fallback to og:description
        if not details.get("description"):
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                details["description"] = og_desc["content"]

        # Image from og:image, adaptive-media, or content images
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            img_url = og_image["content"]
            if img_url.startswith("/"):
                img_url = f"{self.BASE_URL}{img_url}"
            details["image_url"] = img_url

        # Fallback: look for adaptive-media images
        if not details.get("image_url"):
            adaptive_img = soup.select_one("img[src*='adaptive-media'], img[src*='/o/']")
            if adaptive_img:
                src = adaptive_img.get("src") or adaptive_img.get("data-src")
                if src:
                    if src.startswith("/"):
                        details["image_url"] = f"{self.BASE_URL}{src}"
                    elif src.startswith("http"):
                        details["image_url"] = src

        # Fallback: first large image in content
        if not details.get("image_url"):
            content_div = soup.select_one(".content-text-plan, #content_container")
            if content_div:
                img = content_div.find("img")
                if img:
                    src = img.get("src") or img.get("data-src")
                    if src:
                        if src.startswith("/"):
                            details["image_url"] = f"{self.BASE_URL}{src}"
                        elif src.startswith("http"):
                            details["image_url"] = src

        # Organizer from ul.features_description_plan
        features = soup.select_one("ul.features_description_plan")
        if features:
            empresa_link = features.find("a")
            if empresa_link:
                org_name = empresa_link.get_text(strip=True)
                org_url = empresa_link.get("href", "")
                if org_url.startswith("/"):
                    org_url = f"{self.BASE_URL}{org_url}"
                details["organizer_name"] = org_name
                details["organizer_type"] = OrganizerType.INSTITUCION
                details["organizer_url"] = org_url if org_url.startswith("http") else None
                # Use favicon as logo
                if org_url:
                    domain = org_url.split("/")[2] if "://" in org_url else "visitnavarra.es"
                    details["organizer_logo_url"] = f"https://www.google.com/s2/favicons?domain={domain}&sz=64"

        # Default organizer if not found
        if not details.get("organizer_name"):
            details["organizer_name"] = "Turismo de Navarra"
            details["organizer_type"] = OrganizerType.INSTITUCION
            details["organizer_url"] = "https://www.visitnavarra.es"
            details["organizer_logo_url"] = "https://www.google.com/s2/favicons?domain=visitnavarra.es&sz=64"

        # Look for dates in page content
        page_text = soup.get_text()
        dates = self._extract_dates(page_text)
        if dates:
            details["start_date"] = dates[0]
            details["end_date"] = dates[-1] if len(dates) > 1 else dates[0]

        # Location - try to find from content
        location = self._extract_location(page_text, soup)
        if location:
            details["city"] = location

        # Default city for Navarra tourism events
        if not details.get("city"):
            # Try to infer from URL slug
            slug = url.split("/es/w/")[-1] if "/es/w/" in url else ""
            if "pamplona" in slug.lower() or "iruña" in slug.lower():
                details["city"] = "Pamplona"
            elif "tudela" in slug.lower():
                details["city"] = "Tudela"
            elif "estella" in slug.lower():
                details["city"] = "Estella"
            elif "lantz" in slug.lower():
                details["city"] = "Lantz"
            elif "alsasua" in slug.lower():
                details["city"] = "Alsasua"

        # Category from breadcrumb or content
        breadcrumb = soup.find("nav", {"aria-label": "breadcrumb"}) or soup.find("ol", class_="breadcrumb")
        if breadcrumb:
            links = breadcrumb.find_all("a")
            for link in links:
                text = link.get_text(strip=True).lower()
                if text in ["fiestas", "tradiciones", "fiestas y tradiciones"]:
                    details["category_name"] = "Fiestas y Tradiciones"
                elif text in ["gastronomía", "gastronomia"]:
                    details["category_name"] = "Gastronomía"
                elif text in ["cultura", "cultural"]:
                    details["category_name"] = "Cultura"
                elif text in ["deportes", "deporte"]:
                    details["category_name"] = "Deportes"

        # Infer category from title/URL if not found
        if not details.get("category_name"):
            slug = url.split("/es/w/")[-1].lower() if "/es/w/" in url else ""
            title_lower = details.get("title", "").lower()
            if "carnaval" in slug or "carnaval" in title_lower:
                details["category_name"] = "Fiestas y Tradiciones"
            elif "festival" in slug or "festival" in title_lower:
                details["category_name"] = "Música"
            elif "feria" in slug or "feria" in title_lower:
                details["category_name"] = "Ferias"
            elif "ruta" in slug or "ruta" in title_lower:
                details["category_name"] = "Gastronomía"

        return details

    def _parse_listing_date(self, text: str) -> tuple[date | None, date | None]:
        """Parse date from listing format: '15 feb - 17 mar' or '17 feb' or 'Varias fechas'.

        Args:
            text: Date text from listing

        Returns:
            Tuple of (start_date, end_date)
        """
        if not text or "varias fechas" in text.lower():
            return None, None

        today = date.today()
        current_year = today.year

        # Short month names in Spanish
        months_short = {
            "ene": 1, "feb": 2, "mar": 3, "abr": 4,
            "may": 5, "jun": 6, "jul": 7, "ago": 8,
            "sep": 9, "oct": 10, "nov": 11, "dic": 12,
        }

        # Pattern: "DD mon - DD mon" or "DD mon"
        # Examples: "15 feb - 17 mar", "17 feb", "20 feb - 22 feb"
        pattern = r"(\d{1,2})\s+(\w{3})"
        matches = re.findall(pattern, text.lower())

        dates = []
        for day_str, month_str in matches:
            day = int(day_str)
            month = months_short.get(month_str)
            if month:
                # Determine year - if month is before current month, assume next year
                year = current_year
                try:
                    d = date(year, month, day)
                    # If date is more than 2 months in the past, assume next year
                    if d < today and (today - d).days > 60:
                        d = date(year + 1, month, day)
                    dates.append(d)
                except ValueError:
                    pass

        if len(dates) >= 2:
            return dates[0], dates[1]
        elif len(dates) == 1:
            return dates[0], dates[0]
        return None, None

    def _extract_description_from_markdown(self, markdown: str) -> str | None:
        """Extract clean description from markdown content."""
        # Remove navigation, headers, etc.
        lines = markdown.split("\n")
        content_lines = []

        for line in lines:
            line = line.strip()
            # Skip empty lines, navigation, short lines
            if not line or len(line) < 30:
                continue
            # Skip markdown headers
            if line.startswith("#"):
                continue
            # Skip links-only lines
            if line.startswith("[") and line.endswith(")"):
                continue
            # Skip menu items
            if line.startswith("*") or line.startswith("-"):
                continue

            content_lines.append(line)

        if content_lines:
            # Take first substantial paragraph
            return content_lines[0][:500] if content_lines else None
        return None

    def _extract_dates(self, text: str) -> list[date]:
        """Extract dates from text content."""
        dates = []
        today = date.today()

        # Pattern 1: DD de month de YYYY (Spanish)
        pattern_es = r"(\d{1,2})\s+de\s+(\w+)(?:\s+de\s+(\d{4}))?"
        for match in re.finditer(pattern_es, text.lower()):
            day = int(match.group(1))
            month_name = match.group(2)
            year = int(match.group(3)) if match.group(3) else today.year

            month = self.MONTHS_ES.get(month_name)
            if month:
                try:
                    d = date(year, month, day)
                    # Assume future year if date has passed
                    if d < today and not match.group(3):
                        d = date(year + 1, month, day)
                    dates.append(d)
                except ValueError:
                    pass

        # Pattern 2: Month DD, YYYY or Month DD - Month DD, YYYY (English)
        pattern_en = r"(\w+)\s+(\d{1,2})(?:\s*[-–]\s*\w+\s+\d{1,2})?,?\s+(\d{4})"
        for match in re.finditer(pattern_en, text):
            month_name = match.group(1).lower()
            day = int(match.group(2))
            year = int(match.group(3))

            month = self.MONTHS_EN.get(month_name)
            if month:
                try:
                    dates.append(date(year, month, day))
                except ValueError:
                    pass

        # Pattern 3: DD/MM/YYYY
        pattern_slash = r"(\d{1,2})/(\d{1,2})/(\d{4})"
        for match in re.finditer(pattern_slash, text):
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            try:
                dates.append(date(year, month, day))
            except ValueError:
                pass

        # Remove duplicates and sort
        unique_dates = sorted(set(dates))
        return unique_dates

    def _extract_location(self, text: str, soup: BeautifulSoup) -> str | None:
        """Extract location/city from page content."""
        # Look for common Navarra cities
        navarra_cities = [
            "Pamplona", "Iruña", "Tudela", "Estella", "Tafalla",
            "Sangüesa", "Olite", "Puente la Reina", "Elizondo",
            "Alsasua", "Lantz", "Ochagavía", "Roncesvalles",
        ]

        text_lower = text.lower()
        for city in navarra_cities:
            if city.lower() in text_lower:
                return city

        # Look for "Lugar:" or "Location:" patterns
        lugar_match = re.search(r"(?:lugar|ubicación|localidad)[:\s]+([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+)", text, re.IGNORECASE)
        if lugar_match:
            location = lugar_match.group(1).strip()
            # Clean up common suffixes
            location = re.sub(r"\s*\(.*\)", "", location)
            if len(location) > 2 and len(location) < 50:
                return location

        return None

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

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

            # Ensure end_date >= start_date
            end_date = raw_data.get("end_date") or start_date
            if end_date and start_date and end_date < start_date:
                # Swap if inverted
                start_date, end_date = end_date, start_date

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=end_date,
                description=description,
                venue_name=raw_data.get("venue_name"),
                city=raw_data.get("city", "Navarra"),
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
            self.logger.warning("visitnavarra_parse_error", error=str(e), raw=str(raw_data)[:200])
            return None
