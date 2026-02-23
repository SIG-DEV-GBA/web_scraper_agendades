"""Vacaciones Seniors adapter - Senior travel circuits.

Source: https://vacacionesseniors.com/
Tier: Bronze (HTML scraping + Firecrawl for detail pages)
CCAA: Nacional (salidas desde varias CCAA)
Category: social (viajes para mayores de 55)

Each circuit has multiple departure dates with varying prices.
We create ONE event per circuit with the next available date.
Uses Firecrawl for detail pages to get JS-rendered price tables.
"""

import asyncio
import os
import random
import re
from datetime import date, timedelta
from typing import Any

from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventOrganizer, LocationType
from src.core.firecrawl_client import get_firecrawl_client
from src.logging import get_logger

logger = get_logger(__name__)

# Month names in Spanish
MONTHS_ES = {
    "ene": 1, "enero": 1,
    "feb": 2, "febrero": 2,
    "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4,
    "may": 5, "mayo": 5,
    "jun": 6, "junio": 6,
    "jul": 7, "julio": 7,
    "ago": 8, "agosto": 8,
    "sep": 9, "sept": 9, "septiembre": 9,
    "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11,
    "dic": 12, "diciembre": 12,
}


@register_adapter("vacacionesseniors")
class VacacionesSeniorsAdapter(BaseAdapter):
    """Adapter for Vacaciones Seniors - Travel circuits for seniors."""

    source_id = "vacacionesseniors"
    source_name = "Vacaciones Seniors"
    source_url = "https://vacacionesseniors.com/"
    ccaa = "Comunidad de Madrid"  # Default departure point
    ccaa_code = "MD"
    province = "Madrid"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    # Config
    BASE_URL = "https://vacacionesseniors.com"
    LISTING_URL = "https://vacacionesseniors.com/circuitos-culturales-salidas-desde-madrid/"

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = True,
        max_events: int = 100,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch travel circuits from Vacaciones Seniors.

        Args:
            enrich: Not used (LLM enrichment done in pipeline)
            fetch_details: If True, fetch detail pages for full data
            max_events: Maximum number of events to fetch
            limit: If set, applies early limit

        Returns:
            List of raw event dictionaries
        """
        events = []
        seen_urls = set()
        effective_max = min(max_events, limit) if limit else max_events

        try:
            self.logger.info("fetching_vacacionesseniors", url=self.LISTING_URL)

            response = await self.fetch_url(self.LISTING_URL)
            html = response.text

            soup = BeautifulSoup(html, "html.parser")

            # Find all article.dp-dfg-item elements (circuit cards)
            cards = soup.select("article.dp-dfg-item")
            self.logger.info("vacacionesseniors_cards_found", count=len(cards))

            for card in cards:
                card_data = self._extract_card_data(card)
                if card_data and card_data.get("detail_url"):
                    url = card_data["detail_url"]
                    if url not in seen_urls:
                        seen_urls.add(url)
                        events.append(card_data)

                        if len(events) >= effective_max:
                            break

            self.logger.info("vacacionesseniors_cards_parsed", count=len(events))

            # Fetch detail pages for full data
            if fetch_details and events:
                self.logger.info("fetching_circuit_details", count=len(events))
                await self._fetch_details(events)

        except Exception as e:
            self.logger.error("vacacionesseniors_fetch_error", error=str(e))
            raise

        return events

    def _extract_card_data(self, card: BeautifulSoup) -> dict[str, Any] | None:
        """Extract data from a circuit card (article.dp-dfg-item)."""
        try:
            # Title from h1 in .dp-dfg-header
            title_elem = card.select_one(".dp-dfg-header h1, h1")
            if not title_elem:
                return None
            title_text = title_elem.get_text(strip=True)

            # Link from first <a> with valid href
            link = None
            link_elem = card.select_one("a[href*='vacacionesseniors.com']")
            if link_elem:
                link = link_elem.get("href", "")

            if not link:
                return None

            # Get card text for extracting price/date/duration
            card_text = card.get_text(" ", strip=True)

            # Extract price: "desde X €" or just "X €"
            price = None
            price_match = re.search(r"desde\s*(\d+)\s*€", card_text, re.IGNORECASE)
            if not price_match:
                price_match = re.search(r"(\d+)\s*€", card_text)
            if price_match:
                price = int(price_match.group(1))

            # Extract date: "Salida(s) X" or "hasta X"
            date_text = None
            date_match = re.search(r"Salidas?\s+([\d\w\s\.]+?)(?:\s*\d+\s*días|$)", card_text)
            if date_match:
                date_text = date_match.group(1).strip()[:50]

            # Extract duration: "X días"
            duration = None
            dur_match = re.search(r"(\d+)\s*días", card_text)
            if dur_match:
                duration = int(dur_match.group(1))

            # Find image
            image_url = None
            img = card.select_one("img")
            if img:
                src = img.get("src", "")
                if src.startswith("data:"):
                    src = img.get("data-src", "") or img.get("data-lazy-src", "")
                if src and "wp-content/uploads" in src:
                    image_url = src

            # Generate external_id from URL
            external_id = self._extract_id_from_url(link)

            return {
                "title": title_text,
                "detail_url": link,
                "price": price,
                "date_hint": date_text,
                "duration_days": duration,
                "image_url": image_url,
                "external_id": f"{self.source_id}_{external_id}",
            }

        except Exception as e:
            self.logger.warning("card_parse_error", error=str(e))
            return None

    def _extract_id_from_url(self, url: str) -> str:
        """Extract a unique ID from URL."""
        # URL format: https://vacacionesseniors.com/galicia-terra-unica/
        parts = url.rstrip("/").split("/")
        return parts[-1] if parts else "unknown"

    async def _fetch_details(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages with optimized concurrency and adaptive delays.

        Strategy:
        - Semaphore limits concurrent requests (avoid overwhelming server)
        - Adaptive delays: short (1-2s) on success, longer (3-5s) on failure
        - Firecrawl first, fallback to direct HTTP on failure
        - Progress logging every request
        """
        firecrawl_url = os.getenv("FIRECRAWL_URL", "https://firecrawl.si-erp.cloud")
        firecrawl = get_firecrawl_client(base_url=firecrawl_url)

        # Concurrency control: max 2 parallel requests
        semaphore = asyncio.Semaphore(2)

        # Shared state for adaptive behavior
        stats = {"success": 0, "fallback": 0, "errors": 0}
        base_delay = 1.5  # Base delay between requests

        async def fetch_single(idx: int, event: dict) -> None:
            """Fetch single detail page with rate limiting."""
            detail_url = event.get("detail_url")
            if not detail_url:
                return

            async with semaphore:
                # Adaptive delay based on recent success rate
                if idx > 0:
                    # More failures = longer delay
                    failure_rate = stats["fallback"] / max(1, stats["success"] + stats["fallback"])
                    delay = base_delay + (failure_rate * 3)  # 1.5s to 4.5s
                    await asyncio.sleep(delay)

                try:
                    success = False
                    self.logger.info(
                        "fetching",
                        idx=f"{idx + 1}/{len(events)}",
                        url=detail_url.split("/")[-2] if "/" in detail_url else detail_url[-30:],
                    )

                    # Try Firecrawl first
                    result = await firecrawl.scrape(
                        detail_url,
                        formats=["html"],
                        timeout=15000,  # 15s timeout
                    )

                    if result.success and (result.html or result.markdown):
                        content = result.html or result.markdown
                        details = self._parse_detail_page(content, detail_url)
                        event.update(details)
                        stats["success"] += 1
                        success = True
                    else:
                        stats["fallback"] += 1
                        self.logger.debug("firecrawl_fail", error=result.error[:50] if result.error else "no_content")

                    # Fallback to direct HTTP
                    if not success:
                        response = await self.fetch_url(detail_url)
                        details = self._parse_detail_page(response.text, detail_url)
                        event.update(details)

                except Exception as e:
                    stats["errors"] += 1
                    self.logger.warning("fetch_error", idx=idx + 1, error=str(e)[:50])

        # Process all events with controlled concurrency
        tasks = [fetch_single(i, event) for i, event in enumerate(events)]
        await asyncio.gather(*tasks)

        await firecrawl.close()

        self.logger.info(
            "detail_fetch_complete",
            total=len(events),
            firecrawl_ok=stats["success"],
            http_fallback=stats["fallback"],
            errors=stats["errors"],
            with_dates=sum(1 for e in events if e.get("start_date")),
        )

    def _parse_detail_page(self, html: str, url: str) -> dict[str, Any]:
        """Parse detail page extracting data from accordions."""
        details = {}
        soup = BeautifulSoup(html, "html.parser")

        # Title from main h1
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
            # Skip if it's a category title
            if title not in ["Circuitos Nacionales", "Circuitos por Europa"]:
                details["detail_title"] = title

        # Image from og:image
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            details["image_url"] = og_image["content"]

        # Description: intro paragraph (outside accordions)
        intro_text = None
        main_content = soup.select_one(".et_pb_section")
        if main_content:
            for p in main_content.find_all("p"):
                # Skip paragraphs inside accordions
                if p.find_parent(class_="et_pb_toggle"):
                    continue
                text = p.get_text(strip=True)
                if text and len(text) > 50 and "Vacaciones Seniors" not in text:
                    intro_text = text
                    break

        # Fallback for Firecrawl: extract intro from full text
        if not intro_text:
            full_text = soup.get_text(" ", strip=True)
            desc_match = re.search(
                r'(?:España|Circuito|Opcional)[^A-Z]{0,50}([A-ZÁÉÍÓÚ][^€]{50,800}?)(?:Información|Precios|Duración)',
                full_text,
                re.DOTALL
            )
            if desc_match:
                intro_text = re.sub(r'\s+', ' ', desc_match.group(1).strip())

        details["intro"] = intro_text

        # Parse accordions
        accordions = soup.select(".et_pb_toggle")
        for acc in accordions:
            title_elem = acc.select_one(".et_pb_toggle_title")
            content_elem = acc.select_one(".et_pb_toggle_content")

            if not title_elem or not content_elem:
                continue

            acc_title = title_elem.get_text(strip=True).lower()
            content_text = content_elem.get_text(" ", strip=True)

            if "información" in acc_title:
                # Extract duration and dates
                self._parse_info_accordion(content_text, details)

            elif "precio" in acc_title:
                # Extract prices
                self._parse_price_accordion(content_text, details)

            elif "itinerario" in acc_title:
                # Extract full itinerary (day by day)
                itinerary = self._parse_full_itinerary(content_elem)
                if itinerary:
                    details["itinerary"] = itinerary

        return details

    def _parse_info_accordion(self, text: str, details: dict) -> None:
        """Parse information accordion for duration, dates, destination."""
        # Duration: "6 días / 5 noches"
        dur_match = re.search(r"(\d+)\s*días", text)
        if dur_match:
            details["duration_days"] = int(dur_match.group(1))

        # Destination (look for place names after "España" or in title)
        # For now, we'll extract from the title/URL later

        # Parse all departure dates
        dates = self._parse_all_dates(text)
        if dates:
            details["all_dates"] = dates
            # First future date
            today = date.today()
            future_dates = [d for d in dates if d >= today]
            if future_dates:
                details["start_date"] = future_dates[0]
            elif dates:
                details["start_date"] = dates[0]

    def _parse_price_accordion(self, text: str, details: dict) -> None:
        """Parse prices accordion with date-specific prices.

        Extracts patterns like:
        'Salidas 08, 22 de Marzo ... 305 €'
        'Salidas 02, 09, 16 de Agosto ... 525 €'
        """
        # Pattern: "Salidas DD, DD de Month ... NNN €"
        date_price_pattern = r"Salidas?\s+([\d,\s]+(?:de\s+)?(?:Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre))[^€]{0,100}?(\d+)\s*€"
        matches = re.findall(date_price_pattern, text, re.IGNORECASE)

        if matches:
            prices = []
            date_prices = {}  # date -> price mapping
            current_year = date.today().year

            for date_str, price_str in matches:
                try:
                    price = int(price_str)
                    prices.append(price)

                    # Parse individual dates from "08, 22 de Marzo"
                    # Extract month
                    month_match = re.search(r"(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)", date_str, re.IGNORECASE)
                    if month_match:
                        month_name = month_match.group(1).lower()
                        month = MONTHS_ES.get(month_name)
                        if month:
                            # Extract day numbers
                            days = re.findall(r"\d+", date_str.split("de")[0] if "de" in date_str.lower() else date_str)
                            for day_str in days:
                                day = int(day_str)
                                if 1 <= day <= 31:
                                    # Determine year
                                    year = current_year
                                    if month < date.today().month or (month == date.today().month and day < date.today().day):
                                        year = current_year + 1
                                    try:
                                        d = date(year, month, day)
                                        date_prices[d] = price
                                    except ValueError:
                                        pass
                except ValueError:
                    pass

            if prices:
                min_price = min(prices)
                max_price = max(prices)
                details["price"] = min_price
                details["is_free"] = False
                details["date_prices"] = date_prices  # Store date->price mapping

                if min_price != max_price:
                    details["price_info"] = f"Desde {min_price}€ (precio variable según fecha: {min_price}€-{max_price}€)"
                else:
                    details["price_info"] = f"{min_price}€ por persona"
        else:
            # Try to find any price in text
            price_match = re.search(r"(\d+)\s*€", text)
            if price_match:
                price = int(price_match.group(1))
                details["price"] = price
                details["is_free"] = False
                details["price_info"] = f"{price}€ por persona"

    def _parse_itinerary(self, text: str) -> str | None:
        """Extract a summary of the itinerary (legacy - not used)."""
        days = re.findall(r"Día\s+\d+\s*[•·]\s*([^D]+?)(?=Día\s+\d+|$)", text, re.IGNORECASE)
        if days:
            summary_parts = []
            if len(days) >= 1:
                summary_parts.append(f"Día 1: {days[0].strip()[:100]}")
            if len(days) >= 2:
                summary_parts.append(f"... ({len(days)} días)")
            return " ".join(summary_parts)
        return None

    def _parse_full_itinerary(self, content_elem: BeautifulSoup) -> list[dict] | None:
        """Extract full day-by-day itinerary from accordion content.

        Returns list of dicts: [{"day": 1, "title": "Madrid / Asturias", "text": "..."}]
        """
        if not content_elem:
            return None

        text = content_elem.get_text(" ", strip=True)

        # Pattern: "Día N • Title Description" - use D.a to handle encoding (Día/Dìa/D�a)
        day_pattern = r"D.a\s+(\d+)\s*[•·–-]\s*(.+?)(?=D.a\s+\d+\s*[•·–-]|$)"
        matches = re.findall(day_pattern, text, re.IGNORECASE | re.DOTALL)

        if not matches:
            return None

        days = []
        for day_num, content in matches:
            content = content.strip()

            # Title is "Ciudad / Ciudad" or "Ciudad de Origen / Destino" format
            # Look for pattern ending with common keywords that start description
            title_match = re.match(
                r"^(.+?)(?=\s+(?:Salida|Desayuno|Llegada|Por la|Almuerzo|Cena|Visita|Tiempo|Ma.ana|Estancia|R.gimen|Jornada))",
                content,
                re.IGNORECASE
            )
            if title_match:
                title = title_match.group(1).strip()
                desc = content[len(title):].strip()
            else:
                # Fallback: split at first sentence
                first_sentence = re.match(r"^([^.]{10,80}\.)", content)
                if first_sentence:
                    title = first_sentence.group(1).rstrip(".")
                    desc = content[len(first_sentence.group(1)):].strip()
                else:
                    title = content[:50].strip()
                    desc = content[50:].strip() if len(content) > 50 else ""

            # Clean
            desc = re.sub(r"\s+", " ", desc).strip()

            days.append({
                "day": int(day_num),
                "title": title,
                "text": desc[:400] if desc else None
            })

        return days if days else None

    def _parse_all_dates(self, text: str) -> list[date]:
        """Parse all departure dates from text."""
        dates = []
        current_year = date.today().year

        # Pattern: "Marzo: 08, 22" or "08, 22 de Marzo"
        # First try: "Month: day, day"
        month_days_pattern = r"(\w+):\s*([\d,\s]+)"
        for match in re.finditer(month_days_pattern, text):
            month_name = match.group(1).lower().strip()
            days_str = match.group(2)

            month = MONTHS_ES.get(month_name)
            if not month:
                continue

            # Extract day numbers
            day_numbers = re.findall(r"\d+", days_str)
            for day_str in day_numbers:
                try:
                    day = int(day_str)
                    if 1 <= day <= 31:
                        # Determine year (if month has passed, use next year)
                        year = current_year
                        if month < date.today().month:
                            year = current_year + 1
                        elif month == date.today().month and day < date.today().day:
                            year = current_year + 1

                        d = date(year, month, day)
                        dates.append(d)
                except ValueError:
                    pass

        return sorted(set(dates))

    def _extract_destination(self, title: str, url: str) -> tuple[str | None, str | None]:
        """Extract destination city and province from title/URL."""
        # Common destination patterns
        destinations = {
            "galicia": ("Galicia", "Pontevedra"),
            "asturias": ("Asturias", "Asturias"),
            "cantabria": ("Cantabria", "Cantabria"),
            "andalucia": ("Andalucía", "Sevilla"),
            "extremadura": ("Extremadura", "Cáceres"),
            "castilla": ("Castilla", "Burgos"),
            "aragon": ("Aragón", "Zaragoza"),
            "navarra": ("Navarra", "Navarra"),
            "rioja": ("La Rioja", "La Rioja"),
            "pais vasco": ("País Vasco", "Bizkaia"),
            "euskadi": ("País Vasco", "Bizkaia"),
            "valencia": ("Valencia", "Valencia"),
            "murcia": ("Murcia", "Murcia"),
            "almeria": ("Almería", "Almería"),
            "cadiz": ("Cádiz", "Cádiz"),
            "malaga": ("Málaga", "Málaga"),
            "cordoba": ("Córdoba", "Córdoba"),
            "sevilla": ("Sevilla", "Sevilla"),
            "granada": ("Granada", "Granada"),
            "leon": ("León", "León"),
            "burgos": ("Burgos", "Burgos"),
            "segovia": ("Segovia", "Segovia"),
            "avila": ("Ávila", "Ávila"),
            "salamanca": ("Salamanca", "Salamanca"),
        }

        title_lower = title.lower()
        url_lower = url.lower()

        for key, (city, province) in destinations.items():
            if key in title_lower or key in url_lower:
                return city, province

        return None, None

    def _build_markdown_description(
        self, raw_data: dict[str, Any], duration: int, city: str | None
    ) -> str | None:
        """Build a clean, readable description with intro + itinerary.

        Format:
        - Intro paragraph (what the trip is about)
        - Day-by-day itinerary with bold day headers

        Does NOT duplicate: dates, prices, city (already in event fields)
        """
        parts = []

        # Intro paragraph
        intro = raw_data.get("intro", "").strip()
        if intro:
            parts.append(intro)

        # Itinerary (day by day)
        itinerary = raw_data.get("itinerary")
        if itinerary and isinstance(itinerary, list):
            itinerary_parts = []
            for day in itinerary:
                day_num = day.get("day", "?")
                title = day.get("title", "")
                text = day.get("text", "")

                # Format: **Día 1 - Madrid / Asturias**
                header = f"**Día {day_num}**"
                if title:
                    header += f" - *{title}*"

                if text:
                    itinerary_parts.append(f"{header}\n{text}")
                else:
                    itinerary_parts.append(header)

            if itinerary_parts:
                parts.append("\n\n".join(itinerary_parts))

        if not parts:
            # Fallback to old description field
            desc = raw_data.get("description", "").strip()
            if desc:
                return desc
            return None

        return "\n\n".join(parts)

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("detail_title") or raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title:
                return None

            # If no start_date from detail, try to parse from date_hint
            if not start_date:
                date_hint = raw_data.get("date_hint", "")
                if date_hint:
                    # Try to extract a date from "03 May." or similar
                    match = re.search(r"(\d{1,2})\s*(\w+)", date_hint)
                    if match:
                        day = int(match.group(1))
                        month_str = match.group(2).lower().rstrip(".")
                        month = MONTHS_ES.get(month_str)
                        if month:
                            year = date.today().year
                            if month < date.today().month:
                                year += 1
                            try:
                                start_date = date(year, month, day)
                            except ValueError:
                                pass

            # If still no date, use a date 30 days from now as placeholder
            if not start_date:
                start_date = date.today() + timedelta(days=30)

            # Calculate end_date from duration
            duration = raw_data.get("duration_days", 1)
            end_date = start_date + timedelta(days=duration - 1)

            # Extract destination
            detail_url = raw_data.get("detail_url", "")
            city, province = self._extract_destination(title, detail_url)

            # Build Markdown description
            description = self._build_markdown_description(raw_data, duration, city)

            # Price info
            price = raw_data.get("price")
            price_info = raw_data.get("price_info")

            # Generate price_info if we have price but no info
            if price and not price_info:
                price_info = f"{int(price)}€ por persona"

            # Alternative dates for multi-date events (for frontend dropdown)
            alternative_dates = None
            all_dates = raw_data.get("all_dates", [])
            if all_dates and len(all_dates) > 1:
                # Build JSON structure with dates and prices
                date_prices = raw_data.get("date_prices", {})
                alternative_dates = {
                    "dates": [d.isoformat() for d in all_dates],
                    "prices": {d.isoformat(): date_prices.get(d, price) for d in all_dates} if price else {},
                }

            # Organizer
            organizer = EventOrganizer(
                name="Vacaciones Seniors",
                url="https://vacacionesseniors.com",
                logo_url="https://vacacionesseniors.com/wp-content/uploads/2020/03/Vacaciones-Seniors-Color.png",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                end_date=end_date,
                description=description,
                city=city or "Varios destinos",
                province=province,
                comunidad_autonoma=None,  # Multi-region
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=detail_url,
                external_id=raw_data.get("external_id"),
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_slugs=["social"],  # Fixed category for senior travel
                organizer=organizer,
                price=float(price) if price else None,
                price_info=price_info,
                alternative_dates=alternative_dates,
                is_free=False,  # Travel circuits are never free
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e), raw=str(raw_data)[:200])
            return None
