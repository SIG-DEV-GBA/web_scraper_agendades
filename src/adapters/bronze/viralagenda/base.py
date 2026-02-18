"""Base adapter for Viralagenda sources.

Viralagenda uses a consistent HTML structure across all provinces.
This base adapter handles the common scraping logic.
"""

import asyncio
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventContact, EventOrganizer, LocationType, OrganizerType
from src.logging import get_logger
from src.utils.contacts import (
    extract_contact_info,
    extract_organizer,
    extract_price_info,
    extract_registration_info,
)


def clean_viralagenda_city(city: str | None) -> str | None:
    """Clean Viralagenda city names that include comarca info.

    Examples:
        "Valladolid y Campiña del Pisuerga" -> "Valladolid"
        "León y Comarca Metropolitana" -> "León"
        "Soria" -> "Soria"
    """
    if not city:
        return None

    # Remove comarca/region suffixes
    patterns = [
        r"\s+y\s+Campiña.*$",
        r"\s+y\s+Comarca.*$",
        r"\s+y\s+Alfoz.*$",
        r"\s+y\s+Área\s+Metropolitana.*$",
        r"\s+y\s+Entorno.*$",
        r"\s+Metropolitano.*$",
    ]
    for pattern in patterns:
        city = re.sub(pattern, "", city, flags=re.IGNORECASE)

    return city.strip() if city.strip() else None

logger = get_logger(__name__)


# ============================================================
# VIRALAGENDA CONFIG
# ============================================================

@dataclass
class ViralAgendaConfig:
    """Configuration for a Viralagenda province source."""

    slug: str  # e.g., "viralagenda_sevilla"
    name: str  # e.g., "Viral Agenda - Sevilla"
    province: str  # e.g., "Sevilla"
    ccaa: str  # e.g., "Andalucía"
    ccaa_code: str  # e.g., "AN"

    # URL path after base (e.g., "andalucia/sevilla", "galicia/pontevedra")
    url_path: str

    # Optional: city if different from province (for uniprovincial or city-specific)
    default_city: str | None = None


# ============================================================
# VIRALAGENDA SOURCES BY CCAA
# ============================================================

VIRALAGENDA_SOURCES: dict[str, ViralAgendaConfig] = {}

def _register_viralagenda_sources():
    """Register all Viralagenda sources."""

    # ---- ANDALUCÍA (8 provinces) ----
    andalucia_provinces = [
        ("almeria", "Almería"),
        ("cadiz", "Cádiz"),
        ("cordoba", "Córdoba"),
        ("granada", "Granada"),
        ("huelva", "Huelva"),
        ("jaen", "Jaén"),
        ("malaga", "Málaga"),
        ("sevilla", "Sevilla"),
    ]
    for slug_suffix, province in andalucia_provinces:
        VIRALAGENDA_SOURCES[f"viralagenda_{slug_suffix}"] = ViralAgendaConfig(
            slug=f"viralagenda_{slug_suffix}",
            name=f"Viral Agenda - {province}",
            province=province,
            ccaa="Andalucía",
            ccaa_code="AN",
            url_path=f"andalucia/{slug_suffix}",
        )

    # ---- CASTILLA Y LEÓN (9 provinces) ----
    cyl_provinces = [
        ("avila", "Ávila"),
        ("burgos", "Burgos"),
        ("leon", "León"),
        ("palencia", "Palencia"),
        ("salamanca", "Salamanca"),
        ("segovia", "Segovia"),
        ("soria", "Soria"),
        ("valladolid", "Valladolid"),
        ("zamora", "Zamora"),
    ]
    for slug_suffix, province in cyl_provinces:
        VIRALAGENDA_SOURCES[f"viralagenda_{slug_suffix}"] = ViralAgendaConfig(
            slug=f"viralagenda_{slug_suffix}",
            name=f"Viral Agenda - {province}",
            province=province,
            ccaa="Castilla y León",
            ccaa_code="CL",
            url_path=f"castilla-y-leon/{slug_suffix}",
        )

    # ---- GALICIA (4 provinces) ----
    galicia_provinces = [
        ("a_coruna", "A Coruña", "a-coruna"),
        ("lugo", "Lugo", "lugo"),
        ("ourense", "Ourense", "ourense"),
        ("pontevedra", "Pontevedra", "pontevedra"),
    ]
    for slug_suffix, province, url_suffix in galicia_provinces:
        VIRALAGENDA_SOURCES[f"viralagenda_{slug_suffix}"] = ViralAgendaConfig(
            slug=f"viralagenda_{slug_suffix}",
            name=f"Viral Agenda - {province}",
            province=province,
            ccaa="Galicia",
            ccaa_code="GA",
            url_path=f"galicia/{url_suffix}",
        )

    # ---- CASTILLA-LA MANCHA (5 provinces) ----
    clm_provinces = [
        ("albacete", "Albacete"),
        ("ciudad_real", "Ciudad Real", "ciudad-real"),
        ("cuenca", "Cuenca"),
        ("guadalajara", "Guadalajara"),
        ("toledo", "Toledo"),
    ]
    for item in clm_provinces:
        if len(item) == 2:
            slug_suffix, province = item
            url_suffix = slug_suffix
        else:
            slug_suffix, province, url_suffix = item
        VIRALAGENDA_SOURCES[f"viralagenda_{slug_suffix}"] = ViralAgendaConfig(
            slug=f"viralagenda_{slug_suffix}",
            name=f"Viral Agenda - {province}",
            province=province,
            ccaa="Castilla-La Mancha",
            ccaa_code="CM",
            url_path=f"castilla-la-mancha/{url_suffix}",
        )

    # ---- CANARIAS (2 provinces) ----
    VIRALAGENDA_SOURCES["viralagenda_las_palmas"] = ViralAgendaConfig(
        slug="viralagenda_las_palmas",
        name="Viral Agenda - Las Palmas",
        province="Las Palmas",
        ccaa="Canarias",
        ccaa_code="CN",
        url_path="canarias/las-palmas",
    )
    VIRALAGENDA_SOURCES["viralagenda_santa_cruz_tenerife"] = ViralAgendaConfig(
        slug="viralagenda_santa_cruz_tenerife",
        name="Viral Agenda - Santa Cruz de Tenerife",
        province="Santa Cruz de Tenerife",
        ccaa="Canarias",
        ccaa_code="CN",
        url_path="canarias/santa-cruz-de-tenerife",
    )

    # ---- EXTREMADURA (1 province via Viralagenda - Cáceres) ----
    VIRALAGENDA_SOURCES["viralagenda_caceres"] = ViralAgendaConfig(
        slug="viralagenda_caceres",
        name="Viral Agenda - Cáceres",
        province="Cáceres",
        ccaa="Extremadura",
        ccaa_code="EX",
        url_path="extremadura/caceres/caceres",
    )

    # ---- UNIPROVINCIALES ----
    # Asturias
    VIRALAGENDA_SOURCES["viralagenda_asturias"] = ViralAgendaConfig(
        slug="viralagenda_asturias",
        name="Viral Agenda - Asturias",
        province="Asturias",
        ccaa="Principado de Asturias",
        ccaa_code="AS",
        url_path="asturias",
    )

    # Cantabria
    VIRALAGENDA_SOURCES["viralagenda_cantabria"] = ViralAgendaConfig(
        slug="viralagenda_cantabria",
        name="Viral Agenda - Cantabria",
        province="Cantabria",
        ccaa="Cantabria",
        ccaa_code="CB",
        url_path="cantabria",
    )

    # Murcia
    VIRALAGENDA_SOURCES["viralagenda_murcia"] = ViralAgendaConfig(
        slug="viralagenda_murcia",
        name="Viral Agenda - Murcia",
        province="Murcia",
        ccaa="Región de Murcia",
        ccaa_code="MC",
        url_path="murcia",
    )

    # Navarra
    VIRALAGENDA_SOURCES["viralagenda_navarra"] = ViralAgendaConfig(
        slug="viralagenda_navarra",
        name="Viral Agenda - Navarra",
        province="Navarra",
        ccaa="Navarra",
        ccaa_code="NA",
        url_path="navarra",
    )


# Initialize sources
_register_viralagenda_sources()


def get_viralagenda_source_ids() -> list[str]:
    """Get all Viralagenda source IDs."""
    return list(VIRALAGENDA_SOURCES.keys())


# ============================================================
# VIRALAGENDA ADAPTER
# ============================================================

class ViralAgendaAdapter(BaseAdapter):
    """Adapter for Viralagenda sources.

    Viralagenda uses Firecrawl for rendering (JS-heavy) and has consistent
    HTML structure across all provinces.
    """

    adapter_type = AdapterType.DYNAMIC  # Requires JS rendering
    tier = "bronze"

    # Firecrawl config
    FIRECRAWL_URL = "https://firecrawl.si-erp.cloud/scrape"
    BASE_URL = "https://www.viralagenda.com"

    # CSS Selectors (consistent across all provinces)
    EVENT_CARD_SELECTOR = "li.viral-event"
    TITLE_SELECTOR = ".viral-event-title a"
    LINK_SELECTOR = ".viral-event-title a"
    DATE_SELECTOR = ".viral-event-date"
    CATEGORY_SELECTOR = ".viral-event-cats a"
    LOCATION_SELECTOR = ".viral-event-places"

    # Detail page selectors
    DETAIL_DESCRIPTION_SELECTOR = ".viral-event-description pre"
    DETAIL_CATEGORY_SELECTOR = ".viral-event-category"
    DETAIL_PRICE_SELECTOR = ".viral-event-price"

    def __init__(self, source_slug: str, *args: Any, **kwargs: Any) -> None:
        """Initialize adapter for a specific Viralagenda source."""
        if source_slug not in VIRALAGENDA_SOURCES:
            raise ValueError(
                f"Unknown Viralagenda source: {source_slug}. "
                f"Available: {list(VIRALAGENDA_SOURCES.keys())[:5]}..."
            )

        self.config = VIRALAGENDA_SOURCES[source_slug]
        self.source_id = self.config.slug
        self.source_name = self.config.name
        self.source_url = f"{self.BASE_URL}/es/{self.config.url_path}"
        self.ccaa = self.config.ccaa
        self.ccaa_code = self.config.ccaa_code
        self.province = self.config.province

        super().__init__(*args, **kwargs)

    async def _fetch_with_playwright(self, limit: int | None = None) -> str:
        """Fetch listing page using Playwright with infinite scroll support.

        Args:
            limit: Target number of events (scrolls until reached or no more load)

        Returns:
            HTML content of the page after scrolling
        """
        # Calculate how many scrolls we need (each loads ~20 events)
        max_scrolls = 10  # Default max
        if limit:
            max_scrolls = min((limit // 20) + 2, 15)  # +2 buffer, max 15 scrolls

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_viewport_size({"width": 1920, "height": 1080})

                self.logger.info(
                    "playwright_loading",
                    source=self.source_id,
                    url=self.source_url,
                )

                await page.goto(self.source_url, wait_until="networkidle")

                # Scroll loop - scroll to last card to trigger infinite scroll
                prev_count = 0
                for i in range(max_scrolls):
                    cards = await page.query_selector_all(self.EVENT_CARD_SELECTOR)
                    count = len(cards)

                    self.logger.debug(
                        "playwright_scroll",
                        source=self.source_id,
                        scroll=i,
                        cards=count,
                    )

                    # Stop if no more cards loading
                    if count == prev_count:
                        self.logger.info(
                            "playwright_scroll_complete",
                            source=self.source_id,
                            total_cards=count,
                            scrolls=i,
                        )
                        break

                    # Stop if we have enough cards
                    if limit and count >= limit:
                        self.logger.info(
                            "playwright_limit_reached",
                            source=self.source_id,
                            cards=count,
                            limit=limit,
                        )
                        break

                    prev_count = count

                    # Scroll to last card to trigger lazy loading
                    if cards:
                        await cards[-1].scroll_into_view_if_needed()
                        await asyncio.sleep(2)  # Wait for content to load

                html = await page.content()
                return html

            finally:
                await browser.close()

    async def fetch_events(
        self,
        enrich: bool = False,
        fetch_details: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch events from Viralagenda.

        Args:
            enrich: Not used (LLM enrichment done in pipeline)
            fetch_details: If True, fetch detail pages for descriptions
            limit: Max number of events to fetch (limits cards before detail fetch)

        Returns:
            List of raw event dictionaries
        """
        events = []

        try:
            # Fetch listing page via Playwright (handles infinite scroll)
            self.logger.info(
                "fetching_viralagenda_playwright",
                source=self.source_id,
                url=self.source_url,
            )

            html = await self._fetch_with_playwright(limit=limit)

            if not html:
                self.logger.warning("playwright_empty_response", source=self.source_id)
                return []

            # Parse listing
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(self.EVENT_CARD_SELECTOR)

            self.logger.info(
                "viralagenda_cards_found",
                source=self.source_id,
                count=len(cards),
            )

            for card in cards:
                event = self._parse_card(card)
                if event:
                    events.append(event)

            # Apply limit before fetching details (saves resources)
            if limit and len(events) > limit:
                self.logger.info(
                    "limiting_events",
                    source=self.source_id,
                    original=len(events),
                    limited_to=limit,
                )
                events = events[:limit]

            # Fetch detail pages if requested
            if fetch_details and events:
                # Delay before starting detail fetches (anti-blocking)
                delay = random.uniform(3, 6)
                self.logger.info(
                    "fetching_event_details",
                    source=self.source_id,
                    count=len(events),
                    pre_delay_seconds=round(delay, 1),
                )
                await asyncio.sleep(delay)
                await self._fetch_details(events)

        except Exception as e:
            self.logger.error(
                "viralagenda_fetch_error",
                source=self.source_id,
                error=str(e),
            )
            raise

        return events

    async def fetch_events_streaming(
        self,
        batch_size: int = 5,
        limit: int | None = None,
    ):
        """Fetch events in streaming batches - fetch details, yield batch immediately.

        This is more resilient to crashes as each batch is yielded for
        immediate processing/insertion before fetching the next batch.

        Args:
            batch_size: Number of events per batch (default 5)
            limit: Max total events to fetch

        Yields:
            List of raw event dictionaries (batch_size at a time)
        """
        try:
            # Step 1: Fetch listing page (all cards)
            self.logger.info(
                "streaming_fetch_start",
                source=self.source_id,
                url=self.source_url,
            )

            html = await self._fetch_with_playwright(limit=limit)

            if not html:
                self.logger.warning("playwright_empty_response", source=self.source_id)
                return

            # Parse all cards from listing
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select(self.EVENT_CARD_SELECTOR)

            self.logger.info(
                "streaming_cards_found",
                source=self.source_id,
                count=len(cards),
            )

            # Parse cards into basic event data (no details yet)
            all_events = []
            for card in cards:
                event = self._parse_card(card)
                if event:
                    all_events.append(event)

            # Apply limit
            if limit and len(all_events) > limit:
                all_events = all_events[:limit]

            total_events = len(all_events)
            total_batches = (total_events + batch_size - 1) // batch_size

            self.logger.info(
                "streaming_batches_planned",
                source=self.source_id,
                total_events=total_events,
                batch_size=batch_size,
                total_batches=total_batches,
            )

            # Step 2: Process in batches - fetch details and yield
            for batch_num, i in enumerate(range(0, total_events, batch_size), 1):
                batch = all_events[i:i + batch_size]

                self.logger.info(
                    "streaming_batch_fetch_start",
                    source=self.source_id,
                    batch=f"{batch_num}/{total_batches}",
                    events=len(batch),
                )

                # Delay before batch (anti-blocking)
                if batch_num > 1:
                    delay = random.uniform(3, 6)
                    await asyncio.sleep(delay)

                # Fetch details for this batch only
                await self._fetch_details(batch)

                self.logger.info(
                    "streaming_batch_fetch_complete",
                    source=self.source_id,
                    batch=f"{batch_num}/{total_batches}",
                    with_description=sum(1 for e in batch if e.get("description")),
                )

                # Yield batch for immediate processing/insertion
                yield batch

        except Exception as e:
            self.logger.error(
                "streaming_fetch_error",
                source=self.source_id,
                error=str(e),
            )
            raise

    def _parse_card(self, card: BeautifulSoup) -> dict[str, Any] | None:
        """Parse a single event card from the listing page."""
        try:
            # Title and link
            title_elem = card.select_one(self.TITLE_SELECTOR)
            if not title_elem:
                return None

            title = title_elem.get_text(strip=True)
            # Remove "VIRAL" suffix if present
            if title.endswith(" VIRAL"):
                title = title[:-6].strip()

            link = title_elem.get("href", "")
            if link and not link.startswith("http"):
                link = f"{self.BASE_URL}{link}"

            # Date parsing (format: "JUE05FEBHOY" or "SAB15FEB")
            date_elem = card.select_one(self.DATE_SELECTOR)
            start_date = None
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                start_date = self._parse_viral_date(date_text)

            # Location info (format: "19:00|City|Venue|Category")
            location_elem = card.select_one(self.LOCATION_SELECTOR)
            start_time = None
            city = None
            venue_name = None

            if location_elem:
                # Use separator to split elements (each child becomes separated)
                location_text = location_elem.get_text(separator="|", strip=True)
                parts = [p.strip() for p in location_text.split("|") if p.strip() and p.strip() != "+"]

                # Time (first part if HH:MM format)
                if parts and re.match(r"\d{1,2}:\d{2}", parts[0]):
                    try:
                        h, m = parts[0].split(":")
                        start_time = time(int(h), int(m))
                    except (ValueError, IndexError):
                        pass
                    parts = parts[1:]

                # Format: City|City|Venue|Category... (city sometimes repeated)
                if len(parts) >= 1:
                    city = clean_viralagenda_city(parts[0].strip())
                # Skip second city if same as first, get venue
                if len(parts) >= 3 and parts[0].lower() == parts[1].lower():
                    venue_name = parts[2].strip()  # Third element is venue
                elif len(parts) >= 2:
                    venue_name = parts[1].strip()  # Second element is venue

            # Category from listing
            category_elem = card.select_one(self.CATEGORY_SELECTOR)
            category_name = category_elem.get_text(strip=True) if category_elem else None

            # Image (usually not in listing, will come from detail)
            image_url = None

            # Generate external_id
            external_id = self._generate_external_id(link, title, start_date)

            return {
                "title": title,
                "detail_url": link,
                "start_date": start_date,
                "start_time": start_time,
                "city": city or getattr(self.config, 'default_city', None),
                "venue_name": venue_name,
                "category_name": category_name,
                "image_url": image_url,
                "external_id": external_id,
            }

        except Exception as e:
            self.logger.warning(
                "viralagenda_card_parse_error",
                source=self.source_id,
                error=str(e),
            )
            return None

    def _parse_viral_date(self, date_text: str) -> date | None:
        """Parse Viralagenda date format (e.g., 'JUE05FEBHOY', 'SAB15FEB')."""
        if not date_text:
            return None

        # Remove day name prefix (3 chars) and "HOY" suffix
        date_text = date_text.upper()
        if len(date_text) >= 3:
            date_text = date_text[3:]  # Remove LUN, MAR, MIE, JUE, VIE, SAB, DOM
        date_text = date_text.replace("HOY", "").strip()

        # Extract day and month (e.g., "05FEB", "15MAR")
        match = re.match(r"(\d{1,2})([A-Z]{3})", date_text)
        if not match:
            return None

        day = int(match.group(1))
        month_str = match.group(2)

        month_map = {
            "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4,
            "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8,
            "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
        }

        month = month_map.get(month_str)
        if not month:
            return None

        # Determine year (current or next if month is in the past)
        today = date.today()
        year = today.year

        try:
            result = date(year, month, day)
            # If date is more than 2 months in the past, assume next year
            if (today - result).days > 60:
                result = date(year + 1, month, day)
            return result
        except ValueError:
            return None

    def _generate_external_id(
        self,
        url: str,
        title: str,
        start_date: date | None,
    ) -> str:
        """Generate external_id for deduplication."""
        # Extract slug from URL (last path segment)
        if url:
            slug = url.rstrip("/").split("/")[-1]
            return f"{self.source_id}_{slug}"

        # Fallback: hash title + date
        import hashlib
        date_str = start_date.isoformat() if start_date else "nodate"
        hash_input = f"{title}_{date_str}"
        hash_val = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"{self.source_id}_{hash_val}"

    async def _fetch_details(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages to get descriptions."""
        for i, event in enumerate(events):
            detail_url = event.get("detail_url")
            if not detail_url:
                continue

            # Anti-blocking delay between each detail request (2-5 seconds)
            if i > 0:
                delay = random.uniform(2, 5)
                self.logger.debug(
                    "detail_fetch_delay",
                    source=self.source_id,
                    event_index=i,
                    delay_seconds=round(delay, 1),
                )
                await asyncio.sleep(delay)

            try:
                # Use Firecrawl for detail page too (JS-rendered)
                response = requests.post(
                    self.FIRECRAWL_URL,
                    json={
                        "url": detail_url,
                        "formats": ["html"],
                        "timeout": 30000,
                        "waitFor": 2000,
                    },
                    timeout=60,
                )

                if response.status_code == 200:
                    data = response.json()
                    html = data.get("content") or data.get("html", "")

                    if html:
                        details = self._parse_detail_page(html, detail_url)
                        event.update(details)
                elif response.status_code in (403, 429, 500):
                    # Rate limited or blocked - longer backoff
                    backoff = random.uniform(10, 20)
                    self.logger.warning(
                        "detail_fetch_blocked",
                        source=self.source_id,
                        status=response.status_code,
                        backoff_seconds=round(backoff, 1),
                    )
                    await asyncio.sleep(backoff)

                if (i + 1) % 5 == 0:
                    self.logger.info(
                        "detail_fetch_progress",
                        fetched=i + 1,
                        total=len(events),
                    )

            except Exception as e:
                self.logger.warning(
                    "detail_fetch_error",
                    url=detail_url,
                    error=str(e),
                )
                # Extra delay after error (potential rate limit)
                await asyncio.sleep(random.uniform(5, 10))

        self.logger.info(
            "detail_fetch_complete",
            source=self.source_id,
            with_description=sum(1 for e in events if e.get("description")),
        )

    def _parse_detail_page(self, html: str, url: str) -> dict[str, Any]:
        """Parse detail page for description and additional fields."""
        details = {}
        soup = BeautifulSoup(html, "html.parser")

        # Description from .viral-event-description pre
        desc_elem = soup.select_one(self.DETAIL_DESCRIPTION_SELECTOR)
        description_text = ""
        if desc_elem:
            desc_text = desc_elem.get_text(separator="\n\n", strip=True)
            # Clean up excessive whitespace while keeping paragraphs
            desc_text = re.sub(r'\n{3,}', '\n\n', desc_text)
            if desc_text:
                details["description"] = desc_text
                description_text = desc_text

        # Category from .viral-event-category
        cat_elem = soup.select_one(self.DETAIL_CATEGORY_SELECTOR)
        if cat_elem:
            details["category_name"] = cat_elem.get_text(strip=True)

        # Price from .viral-event-price
        price_elem = soup.select_one(self.DETAIL_PRICE_SELECTOR)
        price_text = ""
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            details["price_raw"] = price_text

            # Use our price extractor for better parsing
            price_info = extract_price_info(price_text)
            if price_info["is_free"] is not None:
                details["is_free"] = price_info["is_free"]
            if price_info["price"] is not None:
                details["price"] = price_info["price"]

        # Image from og:image
        og_image = soup.find("meta", {"property": "og:image"})
        if og_image and og_image.get("content"):
            img_url = og_image["content"]
            if not img_url.startswith("http"):
                img_url = f"{self.BASE_URL}{img_url}"
            details["image_url"] = img_url

        # --- PHASE 2: Enhanced extraction from description ---
        # Combine all text for extraction
        full_text = f"{description_text}\n{price_text}"

        # Extract contact info (email, phone)
        contact_info = extract_contact_info(full_text)
        if contact_info["email"] or contact_info["phone"]:
            details["contact_email"] = contact_info["email"]
            details["contact_phone"] = contact_info["phone"]

        # Extract registration info
        reg_info = extract_registration_info(full_text)
        if reg_info["registration_url"]:
            details["registration_url"] = reg_info["registration_url"]
        if reg_info["requires_registration"] is not None:
            details["requires_registration"] = reg_info["requires_registration"]
        if reg_info["registration_info"]:
            details["registration_info"] = reg_info["registration_info"]

        # Extract organizer info
        org_info = extract_organizer(full_text)
        if org_info["organizer_name"]:
            details["organizer_name"] = org_info["organizer_name"]
            details["organizer_type"] = org_info["organizer_type"]

        return details

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title or not start_date:
                return None

            # Build contact if extracted
            contact = None
            if raw_data.get("contact_email") or raw_data.get("contact_phone"):
                contact = EventContact(
                    email=raw_data.get("contact_email"),
                    phone=raw_data.get("contact_phone"),
                )

            # Build organizer with logo_url
            organizer = None
            organizer_name = raw_data.get("organizer_name")
            if organizer_name:
                # Detect organizer type from name
                org_type = self._detect_organizer_type(organizer_name)
                organizer = EventOrganizer(
                    name=organizer_name,
                    type=org_type,
                    logo_url=self._get_favicon_url(raw_data.get("external_url")),
                )

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=raw_data.get("end_date") or start_date,
                start_time=raw_data.get("start_time"),
                description=raw_data.get("description"),
                venue_name=raw_data.get("venue_name"),
                city=raw_data.get("city"),
                province=self.province,
                comunidad_autonoma=self.ccaa,
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("detail_url"),
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_name=raw_data.get("category_name"),
                price=raw_data.get("price"),
                price_info=raw_data.get("price_raw"),
                is_free=raw_data.get("is_free"),
                # Contact
                contact=contact,
                # Registration (fields directly on EventCreate)
                registration_url=raw_data.get("registration_url"),
                requires_registration=raw_data.get("requires_registration", False),
                registration_info=raw_data.get("registration_info"),
                # Organizer (now structured)
                organizer=organizer,
                is_published=True,
            )

        except Exception as e:
            self.logger.warning(
                "viralagenda_parse_error",
                source=self.source_id,
                error=str(e),
                raw=str(raw_data)[:200],
            )
            return None

    def _detect_organizer_type(self, name: str) -> OrganizerType:
        """Detect organizer type from name."""
        name_lower = name.lower()

        # Government/public institutions
        if any(kw in name_lower for kw in [
            "ayuntamiento", "diputación", "diputacion", "gobierno", "generalitat",
            "xunta", "junta", "ministerio", "consejería", "conselleria",
            "museo", "biblioteca", "centro cultural", "centro cívico",
            "casa de cultura", "auditorio", "teatro municipal"
        ]):
            return OrganizerType.INSTITUCION

        # Associations/foundations
        if any(kw in name_lower for kw in [
            "asociación", "asociacion", "fundación", "fundacion", "ong", "colectivo"
        ]):
            return OrganizerType.ASOCIACION

        # Companies
        if any(kw in name_lower for kw in [
            "s.l.", "s.a.", " sl", " sa", "producciones", "entertainment", "events"
        ]):
            return OrganizerType.EMPRESA

        return OrganizerType.OTRO

    def _get_favicon_url(self, url: str | None) -> str | None:
        """Get favicon URL for a domain using Google's favicon service.

        Args:
            url: Full URL

        Returns:
            URL to favicon image (via Google Favicon API)
        """
        if not url:
            return None

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc

            if not domain:
                return None

            # Use Google's favicon service
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
        except Exception:
            return None


# ============================================================
# REGISTER ADAPTERS
# ============================================================

def _create_and_register_adapters():
    """Create and register adapter classes for all Viralagenda sources."""
    for source_slug in VIRALAGENDA_SOURCES:
        # Create a closure to capture source_slug
        def make_adapter_class(slug: str):
            @register_adapter(slug)
            class DynamicViralAgendaAdapter(ViralAgendaAdapter):
                def __init__(self, *args: Any, **kwargs: Any) -> None:
                    super().__init__(slug, *args, **kwargs)

            DynamicViralAgendaAdapter.__name__ = f"ViralAgenda_{slug.replace('viralagenda_', '').title()}Adapter"
            return DynamicViralAgendaAdapter

        make_adapter_class(source_slug)


# Register all adapters on module load
_create_and_register_adapters()
