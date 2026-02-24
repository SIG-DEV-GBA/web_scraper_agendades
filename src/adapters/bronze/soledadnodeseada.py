"""Soledad No Deseada adapter - Social activities against loneliness.

Source: https://soledadnodeseada.es/actividades/
Tier: Bronze (Firecrawl with actions for dynamic loading)
CCAA: Comunidad de Madrid
Category: social (actividades contra la soledad)

Uses Firecrawl with click actions to load more activities dynamically.
Each activity has a detail page with date, time, location.
"""

import asyncio
import os
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
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


@register_adapter("soledadnodeseada")
class SoledadNoDeseadaAdapter(BaseAdapter):
    """Adapter for Soledad No Deseada - Activities against loneliness."""

    source_id = "soledadnodeseada"
    source_name = "Soledad No Deseada"
    source_url = "https://soledadnodeseada.es/"
    ccaa = "Comunidad de Madrid"
    ccaa_code = "MD"
    province = "Madrid"
    adapter_type = AdapterType.STATIC
    tier = "bronze"

    BASE_URL = "https://soledadnodeseada.es"
    LISTING_URL = "https://soledadnodeseada.es/actividades/"

    async def fetch_events(
        self,
        enrich: bool = True,
        fetch_details: bool = True,
        max_events: int = 100,
        limit: int | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Fetch activities from Soledad No Deseada.

        Uses Firecrawl with click actions to load more activities.
        Number of clicks is calculated based on limit (approx 8 events per click).
        """
        events = []
        effective_limit = min(max_events, limit) if limit else max_events

        # Calculate clicks needed (approx 8 events per click, +5 buffer)
        num_clicks = min(30, (effective_limit // 8) + 5)

        try:
            self.logger.info("fetching_soledadnodeseada", limit=effective_limit, clicks=num_clicks)

            firecrawl_url = os.getenv("FIRECRAWL_URL", "https://firecrawl.si-erp.cloud")
            firecrawl = get_firecrawl_client(base_url=firecrawl_url)

            # Build actions: initial wait + N clicks on "load more"
            actions = [{"type": "wait", "milliseconds": 3000}]
            for _ in range(num_clicks):
                actions.append({"type": "click", "selector": ".dmach-loadmore"})
                actions.append({"type": "wait", "milliseconds": 1500})

            # Fetch listing page with all clicks
            result = await firecrawl.scrape(
                self.LISTING_URL,
                formats=["html"],
                timeout=120000,  # 2 min for all clicks
                actions=actions,
            )

            if not result.success:
                self.logger.error("firecrawl_listing_error", error=result.error)
                # Fallback: try without actions (just initial content)
                result = await firecrawl.scrape(
                    self.LISTING_URL,
                    formats=["html"],
                    timeout=30000,
                )

            seen_urls = set()

            if result.success and result.html:
                soup = BeautifulSoup(result.html, "html.parser")

                # Extract all activity URLs
                for link in soup.select('a[href*="/actividades/"]'):
                    href = link.get("href", "")
                    if "/actividades/" in href and href.count("/") > 4:
                        if href.rstrip("/") != self.LISTING_URL.rstrip("/"):
                            seen_urls.add(href)

            self.logger.info(
                "urls_collected",
                clicks=num_clicks,
                total_urls=len(seen_urls),
            )

            await firecrawl.close()

            # Fetch detail pages
            urls_list = list(seen_urls)
            if fetch_details and urls_list:
                events = await self._fetch_details(urls_list, effective_limit)
            else:
                events = [{"detail_url": url} for url in urls_list[:effective_limit]]

        except Exception as e:
            self.logger.error("fetch_error", error=str(e))
            raise

        return events

    async def _fetch_details(
        self, urls: list[str], limit: int
    ) -> list[dict[str, Any]]:
        """Fetch detail pages and filter by date.

        Stops early when we have enough future events.
        """
        from src.core.firecrawl_client import get_firecrawl_client
        import os

        firecrawl_url = os.getenv("FIRECRAWL_URL", "https://firecrawl.si-erp.cloud")
        firecrawl = get_firecrawl_client(base_url=firecrawl_url)

        events = []
        future_count = 0
        today = date.today()

        # Process in batches with semaphore
        semaphore = asyncio.Semaphore(3)

        async def fetch_single(url: str) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    result = await firecrawl.scrape(
                        url, formats=["html"], timeout=20000
                    )

                    if result.success and result.html:
                        data = self._parse_detail_page(result.html, url)
                        data["detail_url"] = url

                        # Check if event is in the future
                        if data.get("start_date"):
                            if data["start_date"] >= today:
                                return data
                            else:
                                return None  # Past event
                        else:
                            # No date found, include anyway
                            return data

                except Exception as e:
                    self.logger.debug("detail_fetch_error", url=url, error=str(e))

                return None

        # Process URLs until we have enough future events
        for i, url in enumerate(urls):
            if future_count >= limit:
                self.logger.info("limit_reached", future_events=future_count)
                break

            data = await fetch_single(url)
            if data:
                events.append(data)
                future_count += 1

                if future_count % 10 == 0:
                    self.logger.info("progress", future_events=future_count, processed=i + 1)

            # Small delay
            await asyncio.sleep(0.5)

        await firecrawl.close()

        self.logger.info(
            "detail_fetch_complete",
            total_processed=len(urls),
            future_events=len(events),
        )

        return events

    def _parse_detail_page(self, html: str, url: str) -> dict[str, Any]:
        """Parse activity detail page with labeled fields.

        Expected structure:
        - TIPO DE ACTIVIDAD: ...
        - DIRIGIDO A: ...
        - Distrito: ...
        - Centro: ...
        - Ubicación: full address
        - Mes: ...
        - Fecha: date + time
        - Descripción: ...
        - Inscripciones: phone/contact
        - Colaboración: ...
        """
        details = {}
        soup = BeautifulSoup(html, "html.parser")

        # Title from <title> tag
        title_tag = soup.select_one("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            if " - " in title_text:
                details["title"] = title_text.split(" - ")[0].strip()
            else:
                details["title"] = title_text

        # Get full text
        text = soup.get_text(" ", strip=True)

        # Extract labeled fields with regex
        def extract_field(pattern: str) -> str | None:
            match = re.search(pattern, text, re.IGNORECASE)
            return match.group(1).strip() if match else None

        # Ubicación → address + venue_name
        ubicacion = extract_field(r"Ubicaci[óo]n\s*:\s*([^|]+?)(?:Mes|Fecha|Descripci|Inscripci|$)")
        if ubicacion:
            # Split venue name from address (format: "Venue Name. C/ Address")
            if ". " in ubicacion:
                parts = ubicacion.split(". ", 1)
                details["venue_name"] = parts[0].strip()
                details["address"] = parts[1].strip() if len(parts) > 1 else None
            else:
                details["address"] = ubicacion

        # Distrito
        distrito = extract_field(r"Distrito\s*:\s*([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]+?)(?:\s*Centro|Ubicaci|$)")
        if distrito:
            details["district"] = distrito.strip()

        # Centro → can be venue if no ubicacion venue
        centro = extract_field(r"Centro\s*:\s*([^|]+?)(?:Ubicaci|Mes|$)")
        if centro and not details.get("venue_name"):
            details["venue_name"] = centro.strip()

        # Fecha: "15 de diciembre a las 10:30h"
        fecha = extract_field(r"Fecha\s*:\s*([^|]+?)(?:Descripci|Inscripci|$)")
        if fecha:
            # Parse date
            date_match = re.search(
                r"(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)",
                fecha,
                re.IGNORECASE,
            )
            if date_match:
                day = int(date_match.group(1))
                month = MONTHS_ES.get(date_match.group(2).lower())
                year = date.today().year

                if month:
                    # If month passed, assume next year
                    if month < date.today().month or (month == date.today().month and day < date.today().day):
                        year += 1
                    try:
                        details["start_date"] = date(year, month, day)
                    except ValueError:
                        pass

            # Parse time from fecha field
            time_match = re.search(r"(\d{1,2}):(\d{2})", fecha)
            if time_match:
                try:
                    from datetime import time as dt_time
                    details["start_time"] = dt_time(int(time_match.group(1)), int(time_match.group(2)))
                except ValueError:
                    pass

        # Descripción
        descripcion = extract_field(r"Descripci[óo]n\s*:\s*([^|]+?)(?:Inscripci|Colaboraci|$)")
        if descripcion:
            details["description"] = descripcion.strip()

        # Inscripciones → registration_info
        inscripciones = extract_field(r"Inscripciones?\s*:\s*([^|]+?)(?:Colaboraci|$)")
        if inscripciones:
            details["registration_info"] = inscripciones.strip()

        # TIPO DE ACTIVIDAD → activity_type (for description enrichment)
        tipo = extract_field(r"TIPO DE ACTIVIDAD\s*:\s*([^|]+?)(?:DIRIGIDO|Distrito|$)")
        if tipo:
            details["activity_type"] = tipo.strip()

        # DIRIGIDO A → target_audience
        dirigido = extract_field(r"DIRIGIDO A\s*:\s*([^|]+?)(?:Distrito|Centro|$)")
        if dirigido:
            details["target_audience"] = dirigido.strip()

        # Colaboración (stop at common footer patterns)
        colaboracion = extract_field(r"Colaboraci[óo]n\s*:\s*([^|]+?)(?:soledadnodeseada|Todos los derechos|$)")
        if colaboracion:
            details["collaboration"] = colaboracion.strip()[:80]

        # Image from og:image
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image and og_image.get("content"):
            details["image_url"] = og_image["content"]

        return details

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse raw event data into EventCreate model."""
        try:
            title = raw_data.get("title")
            start_date = raw_data.get("start_date")

            if not title:
                return None

            # Default date if not found (30 days from now)
            if not start_date:
                start_date = date.today() + timedelta(days=30)

            # Build rich description
            desc_parts = []

            # Main description
            if raw_data.get("description"):
                desc_parts.append(raw_data["description"])

            # Add context info
            if raw_data.get("activity_type"):
                desc_parts.append(f"**Tipo:** {raw_data['activity_type']}")

            if raw_data.get("target_audience"):
                desc_parts.append(f"**Dirigido a:** {raw_data['target_audience']}")

            if raw_data.get("collaboration"):
                desc_parts.append(f"**Colabora:** {raw_data['collaboration']}")

            description = "\n\n".join(desc_parts) if desc_parts else None

            # Organizer
            organizer = EventOrganizer(
                name="Soledad No Deseada",
                url="https://soledadnodeseada.es",
                type="asociacion",
            )

            return EventCreate(
                title=title,
                start_date=start_date,
                start_time=raw_data.get("start_time"),
                description=description,
                venue_name=raw_data.get("venue_name"),
                address=raw_data.get("address"),
                district=raw_data.get("district"),
                city="Madrid",
                province="Madrid",
                comunidad_autonoma="Comunidad de Madrid",
                country="España",
                location_type=LocationType.PHYSICAL,
                external_url=raw_data.get("detail_url"),
                external_id=f"{self.source_id}_{raw_data.get('detail_url', '').split('/')[-2]}",
                source_id=self.source_id,
                source_image_url=raw_data.get("image_url"),
                category_slugs=["social"],  # Fixed category
                organizer=organizer,
                is_free=True,  # Most activities are free
                requires_registration=bool(raw_data.get("registration_info")),
                registration_info=raw_data.get("registration_info"),
                is_published=True,
            )

        except Exception as e:
            self.logger.warning("parse_error", error=str(e))
            return None
