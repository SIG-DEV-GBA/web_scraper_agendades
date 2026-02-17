"""Adapter for Eventbrite events.

Fetches events from Eventbrite using Firecrawl to render JS and extracts
structured data from JSON-LD embedded in the page.

Eventbrite provides well-structured JSON-LD data with:
- Event name, description, URL
- Start/end dates
- Location (venue name, address, city)
- Organizer info
- Image URL
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from src.core.event_model import EventCreate, LocationType
from src.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EventbriteSourceConfig:
    """Configuration for an Eventbrite source."""

    slug: str
    name: str
    search_url: str  # e.g., https://www.eventbrite.es/d/spain--illes-balears/events--this-month/
    ccaa: str
    ccaa_code: str
    province: str
    city: str = ""  # Default city for this source
    firecrawl_url: str = "https://firecrawl.si-erp.cloud/scrape"
    firecrawl_wait: int = 10000  # ms to wait for JS rendering
    max_pages: int = 3  # Number of pages to fetch
    date_filter: str = "this-month"  # Date filter: "this-month", "this-week", "today", ""


# ============================================================
# EVENTBRITE SOURCE CONFIGURATIONS
# ============================================================

EVENTBRITE_SOURCES: dict[str, EventbriteSourceConfig] = {
    # ============================================================
    # ANDALUCÍA (8 provinces)
    # ============================================================
    "eventbrite_sevilla": EventbriteSourceConfig(
        slug="eventbrite_sevilla",
        name="Eventbrite - Sevilla",
        search_url="https://www.eventbrite.es/d/spain--sevilla/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Sevilla",
        city="Sevilla",
    ),
    "eventbrite_malaga": EventbriteSourceConfig(
        slug="eventbrite_malaga",
        name="Eventbrite - Málaga",
        search_url="https://www.eventbrite.es/d/spain--m%C3%A1laga/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Málaga",
        city="Málaga",
    ),
    "eventbrite_granada": EventbriteSourceConfig(
        slug="eventbrite_granada",
        name="Eventbrite - Granada",
        search_url="https://www.eventbrite.es/d/spain--granada/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Granada",
        city="Granada",
    ),
    "eventbrite_cordoba": EventbriteSourceConfig(
        slug="eventbrite_cordoba",
        name="Eventbrite - Córdoba",
        search_url="https://www.eventbrite.es/d/spain--c%C3%B3rdoba/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Córdoba",
        city="Córdoba",
    ),
    "eventbrite_cadiz": EventbriteSourceConfig(
        slug="eventbrite_cadiz",
        name="Eventbrite - Cádiz",
        search_url="https://www.eventbrite.es/d/spain--c%C3%A1diz/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Cádiz",
        city="Cádiz",
    ),
    "eventbrite_almeria": EventbriteSourceConfig(
        slug="eventbrite_almeria",
        name="Eventbrite - Almería",
        search_url="https://www.eventbrite.es/d/spain--almer%C3%ADa/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Almería",
        city="Almería",
    ),
    "eventbrite_huelva": EventbriteSourceConfig(
        slug="eventbrite_huelva",
        name="Eventbrite - Huelva",
        search_url="https://www.eventbrite.es/d/spain--huelva/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Huelva",
        city="Huelva",
    ),
    "eventbrite_jaen": EventbriteSourceConfig(
        slug="eventbrite_jaen",
        name="Eventbrite - Jaén",
        search_url="https://www.eventbrite.es/d/spain--ja%C3%A9n/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Jaén",
        city="Jaén",
    ),
    # ============================================================
    # ARAGÓN (3 provinces)
    # ============================================================
    "eventbrite_zaragoza": EventbriteSourceConfig(
        slug="eventbrite_zaragoza",
        name="Eventbrite - Zaragoza",
        search_url="https://www.eventbrite.es/d/spain--zaragoza/events/",
        ccaa="Aragón",
        ccaa_code="AR",
        province="Zaragoza",
        city="Zaragoza",
    ),
    "eventbrite_huesca": EventbriteSourceConfig(
        slug="eventbrite_huesca",
        name="Eventbrite - Huesca",
        search_url="https://www.eventbrite.es/d/spain--huesca/events/",
        ccaa="Aragón",
        ccaa_code="AR",
        province="Huesca",
        city="Huesca",
    ),
    "eventbrite_teruel": EventbriteSourceConfig(
        slug="eventbrite_teruel",
        name="Eventbrite - Teruel",
        search_url="https://www.eventbrite.es/d/spain--teruel/events/",
        ccaa="Aragón",
        ccaa_code="AR",
        province="Teruel",
        city="Teruel",
    ),
    # ============================================================
    # ASTURIAS (uniprovincial)
    # ============================================================
    "eventbrite_asturias": EventbriteSourceConfig(
        slug="eventbrite_asturias",
        name="Eventbrite - Asturias",
        search_url="https://www.eventbrite.es/d/spain--oviedo/events/",
        ccaa="Principado de Asturias",
        ccaa_code="AS",
        province="Asturias",
        city="Oviedo",
    ),
    "eventbrite_gijon": EventbriteSourceConfig(
        slug="eventbrite_gijon",
        name="Eventbrite - Gijón",
        search_url="https://www.eventbrite.es/d/spain--gij%C3%B3n/events/",
        ccaa="Principado de Asturias",
        ccaa_code="AS",
        province="Asturias",
        city="Gijón",
    ),
    # ============================================================
    # BALEARES (uniprovincial - Illes Balears)
    # ============================================================
    "eventbrite_baleares": EventbriteSourceConfig(
        slug="eventbrite_baleares",
        name="Eventbrite - Illes Balears",
        search_url="https://www.eventbrite.es/d/spain--illes-balears/events/",
        ccaa="Illes Balears",
        ccaa_code="IB",
        province="Illes Balears",
        city="",  # City extracted from each event
        max_pages=3,
    ),
    # ============================================================
    # CANARIAS (2 provinces)
    # ============================================================
    "eventbrite_las_palmas": EventbriteSourceConfig(
        slug="eventbrite_las_palmas",
        name="Eventbrite - Las Palmas",
        search_url="https://www.eventbrite.es/d/spain--las-palmas-de-gran-canaria/events/",
        ccaa="Canarias",
        ccaa_code="CN",
        province="Las Palmas",
        city="Las Palmas de Gran Canaria",
    ),
    "eventbrite_tenerife": EventbriteSourceConfig(
        slug="eventbrite_tenerife",
        name="Eventbrite - Tenerife",
        search_url="https://www.eventbrite.es/d/spain--santa-cruz-de-tenerife/events/",
        ccaa="Canarias",
        ccaa_code="CN",
        province="Santa Cruz de Tenerife",
        city="Santa Cruz de Tenerife",
    ),
    # ============================================================
    # CANTABRIA (uniprovincial)
    # ============================================================
    "eventbrite_cantabria": EventbriteSourceConfig(
        slug="eventbrite_cantabria",
        name="Eventbrite - Cantabria",
        search_url="https://www.eventbrite.es/d/spain--santander/events/",
        ccaa="Cantabria",
        ccaa_code="CB",
        province="Cantabria",
        city="Santander",
    ),
    # ============================================================
    # CASTILLA-LA MANCHA (5 provinces)
    # ============================================================
    "eventbrite_toledo": EventbriteSourceConfig(
        slug="eventbrite_toledo",
        name="Eventbrite - Toledo",
        search_url="https://www.eventbrite.es/d/spain--toledo/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Toledo",
        city="Toledo",
    ),
    "eventbrite_ciudad_real": EventbriteSourceConfig(
        slug="eventbrite_ciudad_real",
        name="Eventbrite - Ciudad Real",
        search_url="https://www.eventbrite.es/d/spain--ciudad-real/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Ciudad Real",
        city="Ciudad Real",
    ),
    "eventbrite_albacete": EventbriteSourceConfig(
        slug="eventbrite_albacete",
        name="Eventbrite - Albacete",
        search_url="https://www.eventbrite.es/d/spain--albacete/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Albacete",
        city="Albacete",
    ),
    "eventbrite_cuenca": EventbriteSourceConfig(
        slug="eventbrite_cuenca",
        name="Eventbrite - Cuenca",
        search_url="https://www.eventbrite.es/d/spain--cuenca/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Cuenca",
        city="Cuenca",
    ),
    "eventbrite_guadalajara": EventbriteSourceConfig(
        slug="eventbrite_guadalajara",
        name="Eventbrite - Guadalajara",
        search_url="https://www.eventbrite.es/d/spain--guadalajara/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Guadalajara",
        city="Guadalajara",
    ),
    # ============================================================
    # CASTILLA Y LEÓN (9 provinces)
    # ============================================================
    "eventbrite_valladolid": EventbriteSourceConfig(
        slug="eventbrite_valladolid",
        name="Eventbrite - Valladolid",
        search_url="https://www.eventbrite.es/d/spain--valladolid/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Valladolid",
        city="Valladolid",
    ),
    "eventbrite_leon": EventbriteSourceConfig(
        slug="eventbrite_leon",
        name="Eventbrite - León",
        search_url="https://www.eventbrite.es/d/spain--le%C3%B3n/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="León",
        city="León",
    ),
    "eventbrite_salamanca": EventbriteSourceConfig(
        slug="eventbrite_salamanca",
        name="Eventbrite - Salamanca",
        search_url="https://www.eventbrite.es/d/spain--salamanca/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Salamanca",
        city="Salamanca",
    ),
    "eventbrite_burgos": EventbriteSourceConfig(
        slug="eventbrite_burgos",
        name="Eventbrite - Burgos",
        search_url="https://www.eventbrite.es/d/spain--burgos/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Burgos",
        city="Burgos",
    ),
    "eventbrite_zamora": EventbriteSourceConfig(
        slug="eventbrite_zamora",
        name="Eventbrite - Zamora",
        search_url="https://www.eventbrite.es/d/spain--zamora/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Zamora",
        city="Zamora",
    ),
    "eventbrite_palencia": EventbriteSourceConfig(
        slug="eventbrite_palencia",
        name="Eventbrite - Palencia",
        search_url="https://www.eventbrite.es/d/spain--palencia/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Palencia",
        city="Palencia",
    ),
    "eventbrite_avila": EventbriteSourceConfig(
        slug="eventbrite_avila",
        name="Eventbrite - Ávila",
        search_url="https://www.eventbrite.es/d/spain--%C3%A1vila/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Ávila",
        city="Ávila",
    ),
    "eventbrite_segovia": EventbriteSourceConfig(
        slug="eventbrite_segovia",
        name="Eventbrite - Segovia",
        search_url="https://www.eventbrite.es/d/spain--segovia/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Segovia",
        city="Segovia",
    ),
    "eventbrite_soria": EventbriteSourceConfig(
        slug="eventbrite_soria",
        name="Eventbrite - Soria",
        search_url="https://www.eventbrite.es/d/spain--soria/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Soria",
        city="Soria",
    ),
    # ============================================================
    # CATALUÑA (4 provinces)
    # ============================================================
    "eventbrite_barcelona": EventbriteSourceConfig(
        slug="eventbrite_barcelona",
        name="Eventbrite - Barcelona",
        search_url="https://www.eventbrite.es/d/spain--barcelona/events/",
        ccaa="Cataluña",
        ccaa_code="CT",
        province="Barcelona",
        city="Barcelona",
    ),
    "eventbrite_tarragona": EventbriteSourceConfig(
        slug="eventbrite_tarragona",
        name="Eventbrite - Tarragona",
        search_url="https://www.eventbrite.es/d/spain--tarragona/events/",
        ccaa="Cataluña",
        ccaa_code="CT",
        province="Tarragona",
        city="Tarragona",
    ),
    "eventbrite_girona": EventbriteSourceConfig(
        slug="eventbrite_girona",
        name="Eventbrite - Girona",
        search_url="https://www.eventbrite.es/d/spain--girona/events/",
        ccaa="Cataluña",
        ccaa_code="CT",
        province="Girona",
        city="Girona",
    ),
    "eventbrite_lleida": EventbriteSourceConfig(
        slug="eventbrite_lleida",
        name="Eventbrite - Lleida",
        search_url="https://www.eventbrite.es/d/spain--lleida/events/",
        ccaa="Cataluña",
        ccaa_code="CT",
        province="Lleida",
        city="Lleida",
    ),
    # ============================================================
    # COMUNITAT VALENCIANA (3 provinces)
    # ============================================================
    "eventbrite_valencia": EventbriteSourceConfig(
        slug="eventbrite_valencia",
        name="Eventbrite - Valencia",
        search_url="https://www.eventbrite.es/d/spain--valencia/events/",
        ccaa="Comunitat Valenciana",
        ccaa_code="VC",
        province="Valencia",
        city="Valencia",
    ),
    "eventbrite_alicante": EventbriteSourceConfig(
        slug="eventbrite_alicante",
        name="Eventbrite - Alicante",
        search_url="https://www.eventbrite.es/d/spain--alicante/events/",
        ccaa="Comunitat Valenciana",
        ccaa_code="VC",
        province="Alicante",
        city="Alicante",
    ),
    "eventbrite_castellon": EventbriteSourceConfig(
        slug="eventbrite_castellon",
        name="Eventbrite - Castellón",
        search_url="https://www.eventbrite.es/d/spain--castell%C3%B3n-de-la-plana/events/",
        ccaa="Comunitat Valenciana",
        ccaa_code="VC",
        province="Castellón",
        city="Castellón de la Plana",
    ),
    # ============================================================
    # EXTREMADURA (2 provinces)
    # ============================================================
    "eventbrite_badajoz": EventbriteSourceConfig(
        slug="eventbrite_badajoz",
        name="Eventbrite - Badajoz",
        search_url="https://www.eventbrite.es/d/spain--badajoz/events/",
        ccaa="Extremadura",
        ccaa_code="EX",
        province="Badajoz",
        city="Badajoz",
    ),
    "eventbrite_caceres": EventbriteSourceConfig(
        slug="eventbrite_caceres",
        name="Eventbrite - Cáceres",
        search_url="https://www.eventbrite.es/d/spain--c%C3%A1ceres/events/",
        ccaa="Extremadura",
        ccaa_code="EX",
        province="Cáceres",
        city="Cáceres",
    ),
    # ============================================================
    # GALICIA (4 provinces)
    # ============================================================
    "eventbrite_a_coruna": EventbriteSourceConfig(
        slug="eventbrite_a_coruna",
        name="Eventbrite - A Coruña",
        search_url="https://www.eventbrite.es/d/spain--a-coru%C3%B1a/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="A Coruña",
        city="A Coruña",
    ),
    "eventbrite_vigo": EventbriteSourceConfig(
        slug="eventbrite_vigo",
        name="Eventbrite - Vigo",
        search_url="https://www.eventbrite.es/d/spain--vigo/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="Pontevedra",
        city="Vigo",
    ),
    "eventbrite_santiago": EventbriteSourceConfig(
        slug="eventbrite_santiago",
        name="Eventbrite - Santiago de Compostela",
        search_url="https://www.eventbrite.es/d/spain--santiago-de-compostela/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="A Coruña",
        city="Santiago de Compostela",
    ),
    "eventbrite_ourense": EventbriteSourceConfig(
        slug="eventbrite_ourense",
        name="Eventbrite - Ourense",
        search_url="https://www.eventbrite.es/d/spain--ourense/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="Ourense",
        city="Ourense",
    ),
    "eventbrite_lugo": EventbriteSourceConfig(
        slug="eventbrite_lugo",
        name="Eventbrite - Lugo",
        search_url="https://www.eventbrite.es/d/spain--lugo/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="Lugo",
        city="Lugo",
    ),
    # ============================================================
    # LA RIOJA (uniprovincial)
    # ============================================================
    "eventbrite_la_rioja": EventbriteSourceConfig(
        slug="eventbrite_la_rioja",
        name="Eventbrite - La Rioja",
        search_url="https://www.eventbrite.es/d/spain--logro%C3%B1o/events/",
        ccaa="La Rioja",
        ccaa_code="RI",
        province="La Rioja",
        city="Logroño",
    ),
    # ============================================================
    # MADRID (uniprovincial)
    # ============================================================
    "eventbrite_madrid": EventbriteSourceConfig(
        slug="eventbrite_madrid",
        name="Eventbrite - Madrid",
        search_url="https://www.eventbrite.es/d/spain--madrid/events/",
        ccaa="Comunidad de Madrid",
        ccaa_code="MD",
        province="Madrid",
        city="Madrid",
    ),
    # ============================================================
    # MURCIA (uniprovincial)
    # ============================================================
    "eventbrite_murcia": EventbriteSourceConfig(
        slug="eventbrite_murcia",
        name="Eventbrite - Murcia",
        search_url="https://www.eventbrite.es/d/spain--murcia/events/",
        ccaa="Región de Murcia",
        ccaa_code="MC",
        province="Murcia",
        city="Murcia",
    ),
    "eventbrite_cartagena": EventbriteSourceConfig(
        slug="eventbrite_cartagena",
        name="Eventbrite - Cartagena",
        search_url="https://www.eventbrite.es/d/spain--cartagena/events/",
        ccaa="Región de Murcia",
        ccaa_code="MC",
        province="Murcia",
        city="Cartagena",
    ),
    # ============================================================
    # NAVARRA (uniprovincial)
    # ============================================================
    "eventbrite_navarra": EventbriteSourceConfig(
        slug="eventbrite_navarra",
        name="Eventbrite - Navarra",
        search_url="https://www.eventbrite.es/d/spain--pamplona/events/",
        ccaa="Navarra",
        ccaa_code="NC",
        province="Navarra",
        city="Pamplona",
    ),
    # ============================================================
    # PAÍS VASCO (3 provinces)
    # ============================================================
    "eventbrite_bilbao": EventbriteSourceConfig(
        slug="eventbrite_bilbao",
        name="Eventbrite - Bilbao",
        search_url="https://www.eventbrite.es/d/spain--bilbao/events/",
        ccaa="País Vasco",
        ccaa_code="PV",
        province="Bizkaia",
        city="Bilbao",
    ),
    "eventbrite_donostia": EventbriteSourceConfig(
        slug="eventbrite_donostia",
        name="Eventbrite - Donostia-San Sebastián",
        search_url="https://www.eventbrite.es/d/spain--san-sebasti%C3%A1n/events/",
        ccaa="País Vasco",
        ccaa_code="PV",
        province="Gipuzkoa",
        city="Donostia-San Sebastián",
    ),
    "eventbrite_vitoria": EventbriteSourceConfig(
        slug="eventbrite_vitoria",
        name="Eventbrite - Vitoria-Gasteiz",
        search_url="https://www.eventbrite.es/d/spain--vitoria-gasteiz/events/",
        ccaa="País Vasco",
        ccaa_code="PV",
        province="Araba/Álava",
        city="Vitoria-Gasteiz",
    ),
}


class EventbriteAdapter:
    """Adapter for fetching events from Eventbrite.

    Uses Firecrawl to render the page and extracts JSON-LD structured data.
    """

    def __init__(self, source_slug: str) -> None:
        if source_slug not in EVENTBRITE_SOURCES:
            raise ValueError(
                f"Unknown Eventbrite source: {source_slug}. "
                f"Available: {list(EVENTBRITE_SOURCES.keys())}"
            )

        self.config = EVENTBRITE_SOURCES[source_slug]
        self.source_id = self.config.slug
        self.source_name = self.config.name

    def _build_search_url(self, page: int = 1) -> str:
        """Build search URL with date filter and pagination."""
        base_url = self.config.search_url.rstrip("/")

        # Add date filter if configured (e.g., events/ -> events--this-month/)
        date_filter = getattr(self.config, "date_filter", "this-month")
        if date_filter and "/events/" in base_url:
            base_url = base_url.replace("/events/", f"/events--{date_filter}/")
        elif date_filter and base_url.endswith("/events"):
            base_url = f"{base_url}--{date_filter}"

        # Add pagination
        if page > 1:
            return f"{base_url}/?page={page}"
        return f"{base_url}/"

    async def fetch_events(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Fetch events from Eventbrite using Firecrawl with pagination.

        Args:
            limit: Maximum number of events to return (and fetch details for).
                   If None, fetches all events up to max_pages.

        Returns list of raw event dicts from JSON-LD.
        """
        all_events = []
        seen_urls = set()  # Deduplicate across pages
        max_pages = getattr(self.config, "max_pages", 1)

        for page in range(1, max_pages + 1):
            url = self._build_search_url(page)

            logger.info(
                "fetching_eventbrite_source",
                source=self.source_id,
                url=url,
                page=page,
            )

            payload = {
                "url": url,
                "formats": ["html"],
                "waitFor": self.config.firecrawl_wait,
                "timeout": 60000,
            }

            try:
                response = requests.post(
                    self.config.firecrawl_url,
                    json=payload,
                    timeout=120,
                )

                if response.status_code != 200:
                    logger.error(
                        "firecrawl_error",
                        source=self.source_id,
                        status=response.status_code,
                        page=page,
                    )
                    if page == 1:
                        return []
                    break

                data = response.json()
                html = data.get("content", data.get("data", {}).get("html", ""))

                if not html:
                    logger.warning("firecrawl_empty_response", source=self.source_id, page=page)
                    if page == 1:
                        return []
                    break

                logger.info(
                    "firecrawl_response",
                    source=self.source_id,
                    html_length=len(html),
                    page=page,
                )

                # Extract JSON-LD structured data
                page_events = self._extract_jsonld_events(html)

                # Deduplicate by event URL
                new_events = 0
                for event in page_events:
                    event_url = event.get("url", "")
                    if event_url and event_url not in seen_urls:
                        seen_urls.add(event_url)
                        all_events.append(event)
                        new_events += 1

                logger.info(
                    "eventbrite_page_events",
                    source=self.source_id,
                    page=page,
                    found=len(page_events),
                    new=new_events,
                )

                # Stop if no new events on this page
                if new_events == 0:
                    break

                # Stop early if we have enough events (considering the limit)
                if limit and len(all_events) >= limit:
                    all_events = all_events[:limit]
                    break

            except requests.exceptions.Timeout:
                logger.error("firecrawl_timeout", source=self.source_id, page=page)
                if page == 1:
                    return []
                break
            except Exception as e:
                logger.error("eventbrite_fetch_error", source=self.source_id, error=str(e), page=page)
                if page == 1:
                    return []
                break

        # Apply limit before fetching details (optimization)
        if limit and len(all_events) > limit:
            all_events = all_events[:limit]

        logger.info(
            "eventbrite_events_found",
            source=self.source_id,
            count=len(all_events),
            pages_fetched=page,
        )

        # Fetch detail pages for complete data (description, price, organizer)
        if all_events:
            all_events = self._fetch_event_details(all_events)

        return all_events

    def _fetch_event_details(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fetch detail pages to get complete event data.

        The listing page JSON-LD has minimal info. Detail pages have full:
        - Description
        - Price (lowPrice/highPrice)
        - Organizer
        - Full address
        - Event times
        """
        logger.info("fetching_eventbrite_details", source=self.source_id, count=len(events))

        enriched_events = []
        for i, event in enumerate(events):
            url = event.get("url", "")
            if not url:
                enriched_events.append(event)
                continue

            try:
                response = requests.post(
                    self.config.firecrawl_url,
                    json={
                        "url": url,
                        "formats": ["html"],
                        "waitFor": 5000,
                        "timeout": 30000,
                    },
                    timeout=60,
                )

                if response.status_code == 200:
                    data = response.json()
                    html = data.get("content", "")

                    if html:
                        # Extract Event JSON-LD from detail page
                        detail_events = self._extract_jsonld_events(html, event_types=["Event", "SportsEvent", "MusicEvent", "SocialEvent"])
                        if detail_events:
                            # Merge detail data into original event
                            detail = detail_events[0]
                            # Prefer detail page data (more complete)
                            for key in ["description", "offers", "organizer", "location", "startDate", "endDate", "image"]:
                                if key in detail and detail[key]:
                                    event[key] = detail[key]

                if (i + 1) % 5 == 0:
                    logger.info("eventbrite_detail_progress", fetched=i + 1, total=len(events))

            except Exception as e:
                logger.warning("eventbrite_detail_error", url=url[:50], error=str(e))

            enriched_events.append(event)

        logger.info("eventbrite_details_complete", source=self.source_id, enriched=len(enriched_events))
        return enriched_events

    def _extract_jsonld_events(self, html: str, event_types: list[str] | None = None) -> list[dict[str, Any]]:
        """Extract events from JSON-LD structured data in HTML.

        Args:
            html: HTML content
            event_types: List of @type values to match (default: ["Event"])
        """
        if event_types is None:
            event_types = ["Event"]

        events = []

        # Find JSON-LD script blocks
        jsonld_matches = re.findall(
            r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL,
        )

        for jsonld in jsonld_matches:
            try:
                parsed = json.loads(jsonld)

                # Handle ItemList (list of events)
                if isinstance(parsed, dict) and parsed.get("@type") == "ItemList":
                    items = parsed.get("itemListElement", [])
                    for item in items:
                        event_data = item.get("item", {})
                        if event_data.get("@type") in event_types:
                            events.append(event_data)

                # Handle single Event (or SportsEvent, MusicEvent, etc.)
                elif isinstance(parsed, dict) and parsed.get("@type") in event_types:
                    events.append(parsed)

                # Handle list of Events
                elif isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and item.get("@type") in event_types:
                            events.append(item)

            except json.JSONDecodeError:
                continue

        return events

    def parse_event(self, raw_event: dict[str, Any]) -> EventCreate | None:
        """Parse a raw Eventbrite event dict into EventCreate model."""
        try:
            # Title
            title = raw_event.get("name", "").strip()
            if not title:
                return None

            # External ID from URL
            url = raw_event.get("url", "")
            external_id = ""
            if url:
                # Extract event ID from URL like /e/event-name-tickets-123456
                match = re.search(r"-(\d+)\??", url)
                if match:
                    external_id = f"eventbrite_{match.group(1)}"
                else:
                    # Use URL hash as fallback
                    external_id = f"eventbrite_{hash(url) & 0xFFFFFFFF}"

            # Dates
            start_date = None
            end_date = None
            start_time = None
            end_time = None

            start_str = raw_event.get("startDate", "")
            if start_str:
                try:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    start_date = dt.date()
                    start_time = dt.time()
                except ValueError:
                    pass

            end_str = raw_event.get("endDate", "")
            if end_str:
                try:
                    dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    end_date = dt.date()
                    end_time = dt.time()
                except ValueError:
                    pass

            if not start_date:
                logger.debug("eventbrite_no_date", title=title[:50])
                return None

            # Description
            description = raw_event.get("description", "")

            # Location
            location = raw_event.get("location", {})
            venue_name = ""
            city = self.config.city
            address = ""

            if isinstance(location, dict):
                venue_name = location.get("name", "")
                addr = location.get("address", {})
                if isinstance(addr, dict):
                    city = addr.get("addressLocality", city)
                    address = addr.get("streetAddress", "")

            # Image
            image_url = ""
            image_data = raw_event.get("image", "")
            if isinstance(image_data, str):
                image_url = image_data
            elif isinstance(image_data, list) and image_data:
                image_url = image_data[0] if isinstance(image_data[0], str) else ""

            # Organizer
            organizer_name = ""
            organizer = raw_event.get("organizer", {})
            if isinstance(organizer, dict):
                organizer_name = organizer.get("name", "")

            # Price - handles both Offer (price) and AggregateOffer (lowPrice/highPrice)
            is_free = False
            price_info = ""
            offers = raw_event.get("offers", {})

            def is_zero(val) -> bool:
                """Check if value is zero (handles '0', '0.0', 0, 0.0)."""
                try:
                    return float(val) == 0
                except (ValueError, TypeError):
                    return False

            def extract_price_from_offer(offer: dict) -> tuple[bool, str]:
                """Extract price info from offer dict. Returns (is_free, price_info)."""
                currency = offer.get("priceCurrency", "EUR")
                # Try standard price first
                price = offer.get("price", "")
                if price:
                    if is_zero(price):
                        return True, ""
                    return False, f"{price} {currency}"
                # Fallback to AggregateOffer (lowPrice/highPrice)
                low = offer.get("lowPrice", "")
                high = offer.get("highPrice", "")
                if low or high:
                    low_is_zero = is_zero(low)
                    high_is_zero = is_zero(high)
                    if low_is_zero and high_is_zero:
                        return True, ""
                    if low_is_zero and high:
                        return False, f"Desde gratis - {high} {currency}"
                    if low == high and low:
                        return False, f"{low} {currency}"
                    if low and high:
                        return False, f"{low} - {high} {currency}"
                    if low:
                        return False, f"Desde {low} {currency}"
                    if high:
                        return False, f"Hasta {high} {currency}"
                return False, ""

            if isinstance(offers, dict):
                is_free, price_info = extract_price_from_offer(offers)
            elif isinstance(offers, list) and offers:
                first_offer = offers[0]
                if isinstance(first_offer, dict):
                    is_free, price_info = extract_price_from_offer(first_offer)
            # Legacy fallback for old format
            if not price_info and isinstance(offers, list) and offers:
                first_offer = offers[0]
                if isinstance(first_offer, dict):
                    price = first_offer.get("price", "")
                    if price == "0" or price == 0:
                        is_free = True
                    elif price:
                        price_info = f"{price} {first_offer.get('priceCurrency', 'EUR')}"

            return EventCreate(
                title=title,
                description=description,
                start_date=start_date,
                end_date=end_date,
                start_time=start_time,
                end_time=end_time,
                location_type=LocationType.PHYSICAL,
                venue_name=venue_name,
                address=address,
                city=city,
                province=self.config.province,
                comunidad_autonoma=self.config.ccaa,
                external_id=external_id,
                external_url=url,
                source=self.source_id,
                source_image_url=image_url,
                organizer_name=organizer_name,
                is_free=is_free,
                price_info=price_info,
            )

        except Exception as e:
            logger.error(
                "eventbrite_parse_error",
                error=str(e),
                title=raw_event.get("name", "?")[:50],
            )
            return None


def get_eventbrite_sources() -> list[str]:
    """Return list of available Eventbrite source slugs."""
    return list(EVENTBRITE_SOURCES.keys())


# ============================================================
# ADAPTER REGISTRATION
# ============================================================

from src.adapters import register_adapter

def create_eventbrite_adapter_class(source_slug: str) -> type:
    """Create a registered adapter class for an Eventbrite source."""

    class DynamicEventbriteAdapter(EventbriteAdapter):
        tier = "eventbrite"

        def __init__(self) -> None:
            super().__init__(source_slug)
            # Expose config properties for API visibility
            self.ccaa = self.config.ccaa
            self.province = self.config.province

    DynamicEventbriteAdapter.__name__ = (
        f"EventbriteAdapter_{source_slug.replace('-', '_').replace('eventbrite_', '').title()}"
    )
    # Register the adapter using decorator as function
    register_adapter(source_slug)(DynamicEventbriteAdapter)
    return DynamicEventbriteAdapter


# Create and register adapter classes for all Eventbrite sources
for slug in EVENTBRITE_SOURCES:
    create_eventbrite_adapter_class(slug)
