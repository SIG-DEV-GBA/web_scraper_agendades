"""Adapter for Bronze-level (Nivel Bronce) web scraping sources.

Uses Firecrawl for rendering JavaScript-heavy pages and BeautifulSoup for parsing.
First implementation: Canarias (lagenda.org - Tenerife events).

Bronze level sources require more processing:
1. Firecrawl fetches rendered HTML
2. BeautifulSoup parses event listings
3. LLM enriches missing fields (description, summary, categories, price)
"""

import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventCreate, EventContact, LocationType
from src.logging import get_logger
from src.utils.contacts import (
    extract_contact_info,
    extract_registration_info,
)

logger = get_logger(__name__)


def clean_text(text: str | None) -> str | None:
    """Clean text by removing encoding artifacts and normalizing Unicode.

    Fixes common issues:
    - Control characters and zero-width spaces
    - Multiple spaces and line breaks
    - Windows-1252 smart quotes
    """
    if not text:
        return text

    # Normalize Unicode (NFC form - composed characters)
    text = unicodedata.normalize("NFC", text)

    # Replace Windows-1252 smart quotes with standard ASCII
    text = text.replace("\x93", '"').replace("\x94", '"')  # Double quotes
    text = text.replace("\x91", "'").replace("\x92", "'")  # Single quotes
    text = text.replace("\u201c", '"').replace("\u201d", '"')  # Unicode double quotes
    text = text.replace("\u2018", "'").replace("\u2019", "'")  # Unicode single quotes
    text = text.replace("\u2013", "-").replace("\u2014", "-")  # En/em dash
    text = text.replace("\u2026", "...")  # Ellipsis

    # Remove control characters except newlines and tabs
    text = "".join(
        char for char in text
        if unicodedata.category(char) != "Cc" or char in "\n\t"
    )

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)  # Multiple spaces/tabs to single space
    text = re.sub(r"\n{3,}", "\n\n", text)  # Max 2 consecutive newlines
    text = text.strip()

    return text


# ============================================================
# ASTURIAS CONFIGURATION
# ============================================================

# Known Asturias municipalities (78 concejos) for city extraction from titles
ASTURIAS_MUNICIPALITIES = {
    # Main cities
    "oviedo", "gijón", "gijon", "avilés", "aviles", "langreo", "mieres",
    "siero", "castrillón", "laviana", "lena", "corvera", "san martín del rey aurelio",
    # Coastal
    "llanes", "ribadesella", "villaviciosa", "colunga", "caravia", "cudillero",
    "muros de nalón", "soto del barco", "castrillón", "gozón", "carreño",
    # Eastern
    "cangas de onís", "onís", "cabrales", "peñamellera alta", "peñamellera baja",
    "ribadedeva", "parres", "piloña", "nava", "bimenes", "amieva", "ponga",
    # Central
    "aller", "caso", "sobrescobio", "rioseco", "morcín", "riosa", "quirós",
    "teverga", "proaza", "santo adriano", "grado", "yernes y tameza", "belmonte",
    # Western
    "navia", "valdés", "tineo", "cangas del narcea", "pravia", "salas", "allande",
    "ibias", "degaña", "villayón", "coaña", "el franco", "tapia de casariego",
    "castropol", "vegadeo", "san tirso de abres", "taramundi", "santa eulalia de oscos",
    "san martín de oscos", "villanueva de oscos", "pesoz", "illano", "grandas de salime",
    # Interior
    "oviedo", "llanera", "las regueras", "ribera de arriba", "morcín",
}


def extract_asturias_city(title: str) -> str | None:
    """Extract city from Asturias event title.

    Patterns:
    - "Evento en Ciudad" or "Evento de Ciudad" at end
    - "Evento. Ciudad" (city after period)
    - "Evento en Ciudad y algo más" (known city in middle)
    """
    if not title:
        return None

    # Pattern 1: 'en Ciudad' or 'de Ciudad' at end
    match = re.search(r'\b(?:en|de)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[a-záéíóúñ]+)?)\s*$', title)
    if match:
        return match.group(1)

    # Pattern 2: Known city at end of title
    title_lower = title.lower()
    for city in ASTURIAS_MUNICIPALITIES:
        if title_lower.endswith(city) or title_lower.endswith('. ' + city):
            # Return with proper capitalization
            return title.split()[-1].rstrip('.')

    # Pattern 3: 'en [Ciudad]' anywhere in title (for cases like 'en Amieva y Alto Sella')
    match = re.search(r'\ben\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)', title)
    if match:
        candidate = match.group(1).lower()
        if candidate in ASTURIAS_MUNICIPALITIES:
            return match.group(1)

    return None


# ============================================================
# CANARIAS CONFIGURATION
# ============================================================

# Map Tenerife municipalities to "Santa Cruz de Tenerife" province
TENERIFE_MUNICIPALITIES = {
    "santa cruz", "santa cruz de tenerife", "la laguna", "la orotava",
    "puerto de la cruz", "los realejos", "arona", "adeje", "granadilla",
    "guía de isora", "icod de los vinos", "candelaria", "tacoronte",
    "el rosario", "el sauzal", "los silos", "buenavista del norte",
    "garachico", "san miguel de abona", "santiago del teide", "tegueste",
    "vilaflor", "arico", "fasnia", "güímar", "san juan de la rambla",
}

# Map Gran Canaria municipalities to "Las Palmas" province
GRAN_CANARIA_MUNICIPALITIES = {
    "las palmas", "las palmas de gran canaria", "telde", "santa lucía",
    "san bartolomé de tirajana", "arucas", "agüimes", "gáldar",
    "ingenio", "mogán", "la aldea", "santa brígida", "teror",
    "valsequillo", "firgas", "moya", "san mateo",
}


def get_canarias_province(venue_or_city: str, default: str = "Santa Cruz de Tenerife") -> str:
    """Determine province from venue/city name in Canarias.

    Args:
        venue_or_city: The venue or city name to analyze
        default: Default province if no match found. Use "Las Palmas" for Gran Canaria sources.
    """
    if not venue_or_city:
        return default

    lower = venue_or_city.lower().strip()

    # Check Tenerife municipalities
    for muni in TENERIFE_MUNICIPALITIES:
        if muni in lower:
            return "Santa Cruz de Tenerife"

    # Check Gran Canaria municipalities
    for muni in GRAN_CANARIA_MUNICIPALITIES:
        if muni in lower:
            return "Las Palmas"

    # Check island names
    if "tenerife" in lower or "tea " in lower:
        return "Santa Cruz de Tenerife"
    if "gran canaria" in lower or "canaria" in lower:
        return "Las Palmas"
    if "lanzarote" in lower or "fuerteventura" in lower:
        return "Las Palmas"
    if "la palma" in lower or "la gomera" in lower or "el hierro" in lower:
        return "Santa Cruz de Tenerife"

    return default


# ============================================================
# CASTILLA-LA MANCHA CONFIGURATION
# ============================================================

# Map CLM municipalities to their provinces
# The 5 provinces: Albacete, Ciudad Real, Cuenca, Guadalajara, Toledo

CLM_ALBACETE_MUNICIPALITIES = {
    "albacete", "hellín", "villarrobledo", "almansa", "la roda",
    "caudete", "tobarra", "chinchilla", "casas-ibáñez", "madrigueras",
}

CLM_CIUDAD_REAL_MUNICIPALITIES = {
    "ciudad real", "puertollano", "tomelloso", "alcázar de san juan",
    "alcazar de san juan",  # Without accent
    "valdepeñas", "manzanares", "daimiel", "la solana", "miguelturra",
    "argamasilla de alba", "campo de criptana", "socuéllamos", "bolaños",
    "almagro", "villanueva de los infantes", "herencia", "pedro muñoz",
}

CLM_CUENCA_MUNICIPALITIES = {
    "cuenca", "tarancón", "san clemente", "motilla del palancar",
    "quintanar del rey", "las pedroñeras", "iniesta", "villanueva de la jara",
}

CLM_GUADALAJARA_MUNICIPALITIES = {
    "guadalajara", "azuqueca de henares", "alovera", "el casar",
    "sigüenza", "molina de aragón", "marchamalo", "cabanillas del campo",
    "villanueva de la torre", "cifuentes", "brihuega",
}

CLM_TOLEDO_MUNICIPALITIES = {
    "toledo", "talavera de la reina", "illescas", "seseña", "torrijos",
    "madridejos", "fuensalida", "ocaña", "mora", "quintanar de la orden",
    "sonseca", "consuegra", "villacañas", "bargas", "añover de tajo",
}


def get_clm_province(locality: str) -> str:
    """Determine province from locality name in Castilla-La Mancha.

    Handles formats like "Albacete (capital)", "Argamasilla de Alba", etc.
    """
    if not locality:
        return "Toledo"  # Default to Toledo (capital regional)

    # Clean up locality name
    lower = locality.lower().strip()
    # Remove "(capital)" suffix
    lower = lower.replace("(capital)", "").strip()

    # Check each province's municipalities
    for muni in CLM_ALBACETE_MUNICIPALITIES:
        if muni in lower or lower in muni:
            return "Albacete"

    for muni in CLM_CIUDAD_REAL_MUNICIPALITIES:
        if muni in lower or lower in muni:
            return "Ciudad Real"

    for muni in CLM_CUENCA_MUNICIPALITIES:
        if muni in lower or lower in muni:
            return "Cuenca"

    for muni in CLM_GUADALAJARA_MUNICIPALITIES:
        if muni in lower or lower in muni:
            return "Guadalajara"

    for muni in CLM_TOLEDO_MUNICIPALITIES:
        if muni in lower or lower in muni:
            return "Toledo"

    # Check province name directly
    if "albacete" in lower:
        return "Albacete"
    if "ciudad real" in lower:
        return "Ciudad Real"
    if "cuenca" in lower:
        return "Cuenca"
    if "guadalajara" in lower:
        return "Guadalajara"
    if "toledo" in lower:
        return "Toledo"

    # Default to Toledo (regional capital)
    return "Toledo"


@dataclass
class BronzeSourceConfig:
    """Configuration for a Bronze-level scraping source."""

    slug: str
    name: str
    listing_url: str
    ccaa: str
    ccaa_code: str
    province: str = ""  # Default province for this source
    firecrawl_url: str = "https://firecrawl.si-erp.cloud/scrape"

    # Selectors for parsing
    event_card_selector: str = ".small-post"
    title_selector: str = "h4.title a"
    image_selector: str = ".thumb img"
    category_selector: str = ".post-category a"
    date_selector: str = ".post-date .date-display-single"
    time_selector: str = ""  # Optional time selector
    location_selector: str = ""  # Optional locality/city selector (for province detection)
    venue_selector: str = ""  # Optional venue/place name selector
    link_selector: str = ""  # If different from title selector

    # Pagination
    max_pages: int = 1  # Number of listing pages to fetch
    page_param: str = "page"

    # Detail page config
    detail_url_pattern: str = ""  # Pattern to build detail URL (e.g., "https://site.com/node/{id}")
    detail_id_extractor: str = "url_suffix"  # How to get detail ID: "url_suffix", "query_param"
    detail_id_param: str = ""  # Query param name if using query_param extractor
    detail_description_selector: str = ".field-name-body, .node-content, article .content"
    detail_dates_selector: str = ".date-display-single, .field-name-field-fecha"
    detail_price_selector: str = ".field-name-field-precio, .price-info"

    # Base URL for relative links
    base_url: str = ""


# ============================================================
# SOURCE CONFIGURATIONS
# ============================================================

BRONZE_SOURCES: dict[str, BronzeSourceConfig] = {
    # ---- CASTILLA-LA MANCHA ----
    "clm_agenda": BronzeSourceConfig(
        slug="clm_agenda",
        name="Agenda Cultural de Castilla-La Mancha",
        listing_url="https://agendacultural.castillalamancha.es",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Toledo",  # Default, will be detected from locality
        base_url="https://agendacultural.castillalamancha.es",
        # Drupal view with activity nodes
        event_card_selector=".view-actividades .views-row article.node--type-actividad",
        title_selector=".field--name-title p",
        link_selector="a.article__link",
        image_selector=".field--name-field-image img",
        date_selector=".field--name-field-fecha-actividad",
        location_selector=".field--name-field-localidad-actividad",  # For province detection
        venue_selector=".field--name-field-lugar-actividad",  # Actual venue name
        # Pagination - web has ?page=0, ?page=1, etc.
        max_pages=5,  # Fetch up to 5 pages (~60 events)
        page_param="page",
        # Detail page config - URL is relative path from href (e.g., /impresiones)
        detail_url_pattern="https://agendacultural.castillalamancha.es{id}",
        # Note: {id} already includes leading slash from href
        detail_id_extractor="url_suffix",
        detail_description_selector=".field--name-body, .node__content, .activity__content",
    ),
    # ---- CANARIAS ----
    "canarias_lagenda": BronzeSourceConfig(
        slug="canarias_lagenda",
        name="Lagenda - Agenda de eventos en Tenerife",
        listing_url="https://lagenda.org/programacion",
        ccaa="Canarias",
        ccaa_code="CN",
        province="Santa Cruz de Tenerife",
        base_url="https://lagenda.org",
        detail_url_pattern="https://lagenda.org/node/{id}",
        detail_id_extractor="url_suffix",
    ),
    "canarias_grancanaria": BronzeSourceConfig(
        slug="canarias_grancanaria",
        name="Cultura Gran Canaria - Cabildo",
        listing_url="https://cultura.grancanaria.com/agenda/",
        ccaa="Canarias",
        ccaa_code="CN",
        province="Las Palmas",
        base_url="https://cultura.grancanaria.com",
        # Selectors for Gran Canaria Liferay portal
        event_card_selector=".calendar-booking-item",
        title_selector="h3.title",
        link_selector="a[href*=detalle-agenda]",
        date_selector=".time-date",
        time_selector=".hora",
        location_selector=".ubicacion a",
        image_selector="",  # No images in listing
        category_selector="",  # No categories in listing
        # Detail page
        detail_url_pattern="https://cultura.grancanaria.com/agenda//detalle-agenda?calendarBookingId={id}",
        detail_id_extractor="query_param",
        detail_id_param="calendarBookingId",
        detail_description_selector=".descripcion, .content, .detalle-contenido",
    ),
    # ---- ARAGÓN (TERUEL) ----
    "teruel_ayuntamiento": BronzeSourceConfig(
        slug="teruel_ayuntamiento",
        name="Agenda Cultural Ayuntamiento de Teruel",
        listing_url="https://www.teruel.es/eventos/feed/",  # RSS feed for URLs
        ccaa="Aragón",
        ccaa_code="AR",
        province="Teruel",
        base_url="https://www.teruel.es",
        firecrawl_url="https://firecrawl.si-erp.cloud/v1/scrape",  # V1 API
        # RSS-based source: we get URLs from RSS, then scrape detail pages
        event_card_selector="item",  # RSS items
        title_selector="title",
        link_selector="link",
        # Detail page - uses JSON-LD schema.org Event data
        detail_url_pattern="{id}",  # URL comes directly from RSS
        detail_id_extractor="url_suffix",
    ),
    # ---- NAVARRA ----
    "navarra_cultura": BronzeSourceConfig(
        slug="navarra_cultura",
        name="Cultura Navarra - Gobierno de Navarra",
        listing_url="https://www.culturanavarra.es/es/agenda",
        ccaa="Navarra",
        ccaa_code="NA",
        province="Navarra",  # Navarra is uniprovincial
        base_url="https://www.culturanavarra.es/",
        # Selectors for culturanavarra.es
        event_card_selector=".agenda_evento",
        title_selector="h4 a",
        link_selector="h4 a",
        image_selector="img.btn-block",
        date_selector=".fecha",
        category_selector="h3",
        location_selector=".localidad span:last-child",  # City
        venue_selector=".localidad span:first-child",  # Venue name
        # No pagination - single page with current month events
        max_pages=1,
        # Detail page - relative URLs like es/agenda/YYYY-MM-DD/categoria/slug
        detail_url_pattern="https://www.culturanavarra.es/{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".entradilla, .descripcion, article .content",
    ),
    # ---- ASTURIAS ----
    "asturias_turismo": BronzeSourceConfig(
        slug="asturias_turismo",
        name="Turismo Asturias - Agenda de Eventos",
        listing_url="https://www.turismoasturias.es/es/agenda-de-asturias",
        ccaa="Principado de Asturias",
        ccaa_code="AS",
        province="Asturias",  # Asturias is uniprovincial
        base_url="https://www.turismoasturias.es",
        # Selectors for turismoasturias.es (Liferay-based, server-rendered)
        # card-title is a <span> without link, link is directly in card
        event_card_selector=".card",
        title_selector=".card-title",
        link_selector="a",  # First <a> in card has the event URL
        image_selector="img",
        # No pagination visible - single page with featured events
        max_pages=1,
        # Detail page - full URLs from listing, uses JSON-LD for structured data
        detail_url_pattern="{id}",  # Full URL comes from listing
        detail_id_extractor="url_suffix",
        detail_description_selector=".descripcion, .event-description, article .content",
    ),
    # ---- LA RIOJA ----
    "larioja_agenda": BronzeSourceConfig(
        slug="larioja_agenda",
        name="Agenda de La Rioja - LARIOJA.COM",
        listing_url="https://agenda.larioja.com/",
        ccaa="La Rioja",
        ccaa_code="RI",
        province="La Rioja",  # La Rioja is uniprovincial
        base_url="https://agenda.larioja.com",
        # Selectors for agenda.larioja.com (Vocento CMS)
        # Featured events use .voc-agenda-titulo, others use .voc-agenda-titulo2
        event_card_selector="article",
        title_selector=".voc-agenda-titulo a, .voc-agenda-titulo2 a",
        link_selector=".voc-agenda-titulo a, .voc-agenda-titulo2 a",
        image_selector="img.figure-img",
        location_selector=".voc-agenda-localidad",
        # No pagination - single page with all events
        max_pages=1,
        # Detail page - URLs like /evento/slug-123456.html, uses JSON-LD for data
        detail_url_pattern="https://agenda.larioja.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".voc-evento-descripcion, .evento-body",
    ),
    # ---- EXTREMADURA (Badajoz) ----
    "badajoz_agenda": BronzeSourceConfig(
        slug="badajoz_agenda",
        name="Agenda Cultural Ayuntamiento de Badajoz",
        listing_url="https://www.aytobadajoz.es/es/ayto/agenda/",
        ccaa="Extremadura",
        ccaa_code="EX",
        province="Badajoz",
        base_url="https://www.aytobadajoz.es",
        # Requires Firecrawl (JS-heavy site with Playwright)
        firecrawl_url="https://firecrawl.si-erp.cloud/scrape",
        # Selectors for aytobadajoz.es
        event_card_selector=".agenda-listado.evento",
        title_selector=".titulo a",
        link_selector=".titulo a",
        image_selector=".imagen-evento img",
        date_selector=".fechas-agenda-menu-actualidad",  # "Del DD-MM-YYYY al DD-MM-YYYY"
        category_selector=".categoria-agenda",  # "Ferias y Fiestas / Carnaval"
        time_selector=".info-evento-agenda .fa-clock",  # Parent has time text
        venue_selector=".info-evento-agenda .fa-map-marker-alt",  # Parent has venue text
        # Single page listing
        max_pages=1,
        # Detail page - URL format: /es/ayto/agenda/evento/{id}/{slug}/
        detail_url_pattern="{id}",  # Full URL from listing
        detail_id_extractor="url_suffix",
        detail_description_selector=".descripcion-evento, .texto-evento, .contenido-evento, .cuerpo-principal",
    ),
    # ---- EXTREMADURA (Cáceres via Viralagenda) ----
    "viralagenda_caceres": BronzeSourceConfig(
        slug="viralagenda_caceres",
        name="Viral Agenda - Cáceres",
        listing_url="https://www.viralagenda.com/es/extremadura/caceres/caceres",
        ccaa="Extremadura",
        ccaa_code="EX",
        province="Cáceres",
        base_url="https://www.viralagenda.com",
        # Server-rendered, no Firecrawl needed
        # Selectors for viralagenda.com
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",  # No images in listing
        date_selector=".viral-event-date",  # "JUE05FEBHOY" format
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",  # "19:00|Cáceres|Venue|Category"
        # Single page with 20+ events
        max_pages=1,
        # Detail page - relative URLs like /es/events/{id}/{slug}
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    # ---- ANDALUCÍA (via Viralagenda) ----
    # 8 provinces: Almería, Cádiz, Córdoba, Granada, Huelva, Jaén, Málaga, Sevilla
    "viralagenda_almeria": BronzeSourceConfig(
        slug="viralagenda_almeria",
        name="Viral Agenda - Almería",
        listing_url="https://www.viralagenda.com/es/andalucia/almeria",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Almería",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_cadiz": BronzeSourceConfig(
        slug="viralagenda_cadiz",
        name="Viral Agenda - Cádiz",
        listing_url="https://www.viralagenda.com/es/andalucia/cadiz",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Cádiz",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_cordoba": BronzeSourceConfig(
        slug="viralagenda_cordoba",
        name="Viral Agenda - Córdoba",
        listing_url="https://www.viralagenda.com/es/andalucia/cordoba",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Córdoba",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_granada": BronzeSourceConfig(
        slug="viralagenda_granada",
        name="Viral Agenda - Granada",
        listing_url="https://www.viralagenda.com/es/andalucia/granada",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Granada",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_huelva": BronzeSourceConfig(
        slug="viralagenda_huelva",
        name="Viral Agenda - Huelva",
        listing_url="https://www.viralagenda.com/es/andalucia/huelva",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Huelva",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_jaen": BronzeSourceConfig(
        slug="viralagenda_jaen",
        name="Viral Agenda - Jaén",
        listing_url="https://www.viralagenda.com/es/andalucia/jaen",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Jaén",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_malaga": BronzeSourceConfig(
        slug="viralagenda_malaga",
        name="Viral Agenda - Málaga",
        listing_url="https://www.viralagenda.com/es/andalucia/malaga",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Málaga",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_sevilla": BronzeSourceConfig(
        slug="viralagenda_sevilla",
        name="Viral Agenda - Sevilla",
        listing_url="https://www.viralagenda.com/es/andalucia/sevilla",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Sevilla",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    # ---- CASTILLA Y LEÓN (via Viralagenda) ----
    # 9 provinces: Ávila, Burgos, León, Palencia, Salamanca, Segovia, Soria, Valladolid, Zamora
    "viralagenda_avila": BronzeSourceConfig(
        slug="viralagenda_avila",
        name="Viral Agenda - Ávila",
        listing_url="https://www.viralagenda.com/es/castilla-y-leon/avila",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Ávila",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_burgos": BronzeSourceConfig(
        slug="viralagenda_burgos",
        name="Viral Agenda - Burgos",
        listing_url="https://www.viralagenda.com/es/castilla-y-leon/burgos",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Burgos",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_leon": BronzeSourceConfig(
        slug="viralagenda_leon",
        name="Viral Agenda - León",
        listing_url="https://www.viralagenda.com/es/castilla-y-leon/leon",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="León",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_palencia": BronzeSourceConfig(
        slug="viralagenda_palencia",
        name="Viral Agenda - Palencia",
        listing_url="https://www.viralagenda.com/es/castilla-y-leon/palencia",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Palencia",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_salamanca": BronzeSourceConfig(
        slug="viralagenda_salamanca",
        name="Viral Agenda - Salamanca",
        listing_url="https://www.viralagenda.com/es/castilla-y-leon/salamanca",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Salamanca",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_segovia": BronzeSourceConfig(
        slug="viralagenda_segovia",
        name="Viral Agenda - Segovia",
        listing_url="https://www.viralagenda.com/es/castilla-y-leon/segovia",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Segovia",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_soria": BronzeSourceConfig(
        slug="viralagenda_soria",
        name="Viral Agenda - Soria",
        listing_url="https://www.viralagenda.com/es/castilla-y-leon/soria",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Soria",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_valladolid": BronzeSourceConfig(
        slug="viralagenda_valladolid",
        name="Viral Agenda - Valladolid",
        listing_url="https://www.viralagenda.com/es/castilla-y-leon/valladolid",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Valladolid",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_zamora": BronzeSourceConfig(
        slug="viralagenda_zamora",
        name="Viral Agenda - Zamora",
        listing_url="https://www.viralagenda.com/es/castilla-y-leon/zamora",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Zamora",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    # ============================================================
    # GALICIA - Viralagenda (4 provinces)
    # ============================================================
    "viralagenda_a_coruna": BronzeSourceConfig(
        slug="viralagenda_a_coruna",
        name="Viral Agenda - A Coruña",
        listing_url="https://www.viralagenda.com/es/galicia/a-coruna",
        ccaa="Galicia",
        ccaa_code="GA",
        province="A Coruña",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_lugo": BronzeSourceConfig(
        slug="viralagenda_lugo",
        name="Viral Agenda - Lugo",
        listing_url="https://www.viralagenda.com/es/galicia/lugo",
        ccaa="Galicia",
        ccaa_code="GA",
        province="Lugo",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_ourense": BronzeSourceConfig(
        slug="viralagenda_ourense",
        name="Viral Agenda - Ourense",
        listing_url="https://www.viralagenda.com/es/galicia/ourense",
        ccaa="Galicia",
        ccaa_code="GA",
        province="Ourense",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_pontevedra": BronzeSourceConfig(
        slug="viralagenda_pontevedra",
        name="Viral Agenda - Pontevedra",
        listing_url="https://www.viralagenda.com/es/galicia/pontevedra",
        ccaa="Galicia",
        ccaa_code="GA",
        province="Pontevedra",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    # ============================================================
    # ASTURIAS - Viralagenda (uniprovincial)
    # ============================================================
    "viralagenda_asturias": BronzeSourceConfig(
        slug="viralagenda_asturias",
        name="Viral Agenda - Asturias",
        listing_url="https://www.viralagenda.com/es/asturias",
        ccaa="Asturias",
        ccaa_code="AS",
        province="Asturias",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    # ============================================================
    # CANARIAS - Viralagenda (2 provinces)
    # ============================================================
    "viralagenda_las_palmas": BronzeSourceConfig(
        slug="viralagenda_las_palmas",
        name="Viral Agenda - Las Palmas",
        listing_url="https://www.viralagenda.com/es/canarias/las-palmas",
        ccaa="Canarias",
        ccaa_code="CN",
        province="Las Palmas",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_santa_cruz_tenerife": BronzeSourceConfig(
        slug="viralagenda_santa_cruz_tenerife",
        name="Viral Agenda - Santa Cruz de Tenerife",
        listing_url="https://www.viralagenda.com/es/canarias/santa-cruz-de-tenerife",
        ccaa="Canarias",
        ccaa_code="CN",
        province="Santa Cruz de Tenerife",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    # ============================================================
    # CANTABRIA - Viralagenda (uniprovincial)
    # ============================================================
    "viralagenda_cantabria": BronzeSourceConfig(
        slug="viralagenda_cantabria",
        name="Viral Agenda - Cantabria",
        listing_url="https://www.viralagenda.com/es/cantabria",
        ccaa="Cantabria",
        ccaa_code="CB",
        province="Cantabria",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    # ============================================================
    # CASTILLA-LA MANCHA - Viralagenda (5 provinces)
    # ============================================================
    "viralagenda_albacete": BronzeSourceConfig(
        slug="viralagenda_albacete",
        name="Viral Agenda - Albacete",
        listing_url="https://www.viralagenda.com/es/castilla-la-mancha/albacete",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Albacete",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_ciudad_real": BronzeSourceConfig(
        slug="viralagenda_ciudad_real",
        name="Viral Agenda - Ciudad Real",
        listing_url="https://www.viralagenda.com/es/castilla-la-mancha/ciudad-real",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Ciudad Real",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_cuenca": BronzeSourceConfig(
        slug="viralagenda_cuenca",
        name="Viral Agenda - Cuenca",
        listing_url="https://www.viralagenda.com/es/castilla-la-mancha/cuenca",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Cuenca",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_guadalajara": BronzeSourceConfig(
        slug="viralagenda_guadalajara",
        name="Viral Agenda - Guadalajara",
        listing_url="https://www.viralagenda.com/es/castilla-la-mancha/guadalajara",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Guadalajara",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    "viralagenda_toledo": BronzeSourceConfig(
        slug="viralagenda_toledo",
        name="Viral Agenda - Toledo",
        listing_url="https://www.viralagenda.com/es/castilla-la-mancha/toledo",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Toledo",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    # ============================================================
    # MURCIA - Viralagenda (uniprovincial)
    # ============================================================
    "viralagenda_murcia": BronzeSourceConfig(
        slug="viralagenda_murcia",
        name="Viral Agenda - Murcia",
        listing_url="https://www.viralagenda.com/es/murcia",
        ccaa="Murcia",
        ccaa_code="MC",
        province="Murcia",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
    # ============================================================
    # NAVARRA - Viralagenda (uniprovincial)
    # ============================================================
    "viralagenda_navarra": BronzeSourceConfig(
        slug="viralagenda_navarra",
        name="Viral Agenda - Navarra",
        listing_url="https://www.viralagenda.com/es/navarra",
        ccaa="Navarra",
        ccaa_code="NC",
        province="Navarra",
        base_url="https://www.viralagenda.com",
        event_card_selector="li.viral-event",
        title_selector=".viral-event-title a",
        link_selector=".viral-event-title a",
        image_selector="",
        date_selector=".viral-event-date",
        category_selector=".viral-event-cats a",
        location_selector=".viral-event-places",
        max_pages=1,
        detail_url_pattern="https://www.viralagenda.com{id}",
        detail_id_extractor="url_suffix",
        detail_description_selector=".viral-event-description, .description, article",
    ),
}


# ============================================================
# BRONZE ADAPTER
# ============================================================


class BronzeScraperAdapter(BaseAdapter):
    """Adapter for Bronze-level web scraping sources.

    Uses Firecrawl to fetch rendered HTML and BeautifulSoup to parse.
    Designed for sites without APIs that need JavaScript rendering.
    """

    adapter_type = AdapterType.STATIC  # Uses HTTP but parses HTML

    def __init__(self, source_slug: str, *args: Any, **kwargs: Any) -> None:
        if source_slug not in BRONZE_SOURCES:
            raise ValueError(
                f"Unknown Bronze source: {source_slug}. "
                f"Available: {list(BRONZE_SOURCES.keys())}"
            )

        self.bronze_config = BRONZE_SOURCES[source_slug]
        self.source_id = self.bronze_config.slug
        self.source_name = self.bronze_config.name
        self.source_url = self.bronze_config.listing_url
        self.ccaa = self.bronze_config.ccaa
        self.ccaa_code = self.bronze_config.ccaa_code

        super().__init__(*args, **kwargs)

    def _fetch_page(self, url: str, use_firecrawl: bool = True) -> str | None:
        """Fetch a page using Firecrawl or direct HTTP.

        For CLM and other server-rendered sites, direct HTTP is preferred.
        Firecrawl is used for JS-heavy sites like lagenda.org.
        """
        # Sites that work better with direct HTTP (Firecrawl blocked or not needed)
        # - CLM: server-rendered Drupal, no JS needed
        # - Gran Canaria: Firecrawl returns 500 (IP blocked?)
        # - Navarra: server-rendered PHP, no JS needed
        # - Asturias: server-rendered Liferay, no JS needed
        # NOTE: Viralagenda REQUIRES Firecrawl (403 with direct HTTP)
        direct_http_sources = {
            "clm_agenda",
            "canarias_grancanaria",
            "navarra_cultura",
            "asturias_turismo",
            "larioja_agenda",
        }
        if self.bronze_config.slug in direct_http_sources:
            use_firecrawl = False

        if not use_firecrawl:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = requests.get(url, headers=headers, timeout=60)
                if response.status_code == 200:
                    # Let requests auto-detect encoding from Content-Type header
                    return response.text
                else:
                    logger.warning("direct_fetch_error", url=url, status=response.status_code)
            except Exception as e:
                logger.error("direct_fetch_exception", url=url, error=str(e))
            return None

        # Use Firecrawl for JS-heavy sites
        try:
            response = requests.post(
                self.bronze_config.firecrawl_url,
                json={"url": url},
                timeout=60
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("content", "")
            else:
                logger.warning(
                    "firecrawl_error",
                    url=url,
                    status=response.status_code,
                )
        except Exception as e:
            logger.error("firecrawl_exception", url=url, error=str(e))
        return None

    def _parse_date_spanish(self, date_str: str) -> date | None:
        """Parse Spanish date like 'Sáb, 28/02/26' or '28-02-2026' to date object."""
        if not date_str:
            return None

        # Remove day name prefix
        date_str = re.sub(r"^[A-Za-záéíóúñü]+,?\s*", "", date_str.strip())

        # Try DD/MM/YY or DD-MM-YYYY format
        match = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", date_str)
        if match:
            day, month, year = match.groups()
            if len(year) == 2:
                year = "20" + year
            # Fix years like "0026" -> "2026"
            year_int = int(year)
            if year_int < 100:
                year_int = 2000 + year_int
            try:
                return date(year_int, int(month), int(day))
            except ValueError:
                pass
        return None

    def _parse_date_range(self, date_str: str) -> tuple[date | None, date | None]:
        """Parse date range like '01-10-2025 a 01-05-2026'.

        Returns tuple of (start_date, end_date).
        If not a range, returns (parsed_date, parsed_date).
        """
        if not date_str:
            return None, None

        # Check for range pattern with "a" or "-" separator
        # Format: "DD-MM-YYYY a DD-MM-YYYY" or "DD/MM/YYYY - DD/MM/YYYY"
        range_match = re.search(
            r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:a|al|-|hasta)\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
            date_str,
            re.IGNORECASE
        )

        if range_match:
            start_str, end_str = range_match.groups()
            start_date = self._parse_date_spanish(start_str)
            end_date = self._parse_date_spanish(end_str)
            return start_date, end_date

        # Not a range, parse as single date
        single_date = self._parse_date_flexible(date_str)
        return single_date, single_date

    def _parse_date_flexible(self, date_str: str) -> date | None:
        """Parse date from various Spanish formats.

        Supports:
        - "Hoy" -> today
        - "Mañana" -> tomorrow
        - "sábado, 31 de enero" -> date with Spanish month name
        - "31 de enero de 2026" -> full date with year
        - "DD/MM/YY" or "DD/MM/YYYY" -> numeric format
        """
        if not date_str:
            return None

        date_str = date_str.strip().lower()
        today = date.today()

        # Handle relative dates
        if date_str in ("hoy", "today"):
            return today
        if date_str in ("mañana", "tomorrow"):
            from datetime import timedelta
            return today + timedelta(days=1)

        # Spanish month names
        months_es = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }

        # Try "31 de enero de 2026" or "31 de enero, 2026"
        match = re.search(r"(\d{1,2})\s+de\s+(\w+)(?:\s+de|\s*,?\s*)?\s*(\d{4})?", date_str)
        if match:
            day, month_name, year = match.groups()
            month = months_es.get(month_name.lower())
            if month:
                year = int(year) if year else today.year
                # If no year and date is in the past, assume next year
                try:
                    parsed = date(year, month, int(day))
                    if not match.group(3) and parsed < today:
                        parsed = date(year + 1, month, int(day))
                    return parsed
                except ValueError:
                    pass

        # Try "sábado, 31 de enero" (day name prefix)
        match = re.search(r"[a-záéíóúñü]+,?\s*(\d{1,2})\s+de\s+(\w+)", date_str)
        if match:
            day, month_name = match.groups()
            month = months_es.get(month_name.lower())
            if month:
                year = today.year
                try:
                    parsed = date(year, month, int(day))
                    if parsed < today:
                        parsed = date(year + 1, month, int(day))
                    return parsed
                except ValueError:
                    pass

        # Fallback to DD/MM/YY format
        return self._parse_date_spanish(date_str)

    def _extract_node_id(self, url: str) -> str | None:
        """Extract Drupal node ID from lagenda.org URL.

        URL format: https://lagenda.org/programacion/event-name-40311
        Node ID is the number at the end.
        """
        if not url:
            return None
        match = re.search(r"-(\d+)$", url.rstrip("/"))
        return match.group(1) if match else None

    def _extract_detail_id(self, url: str) -> str | None:
        """Extract detail page ID based on source configuration."""
        if not url:
            return None

        config = self.bronze_config

        if config.detail_id_extractor == "query_param" and config.detail_id_param:
            # Extract from query param: ?calendarBookingId=123
            match = re.search(rf"{config.detail_id_param}=(\d+)", url)
            return match.group(1) if match else None
        else:
            # Default: extract from URL suffix (lagenda.org pattern: /event-name-12345)
            return self._extract_node_id(url)

    def _build_detail_url(self, url: str) -> str | None:
        """Build the detail page URL based on source configuration."""
        if not url:
            return None

        config = self.bronze_config

        # If URL is already absolute, use it directly
        if url.startswith("http"):
            return url

        # Try to extract detail ID for pattern-based URL construction
        detail_id = self._extract_detail_id(url)

        if detail_id and config.detail_url_pattern:
            return config.detail_url_pattern.replace("{id}", detail_id)

        # Fallback: construct from base_url + relative path
        if config.base_url and url.startswith("/"):
            return config.base_url + url

        return None

    def _fetch_event_detail(self, url: str) -> dict[str, Any]:
        """Fetch full event details from individual event page.

        Uses direct requests to detail URL which renders server-side.

        Returns dict with description, price_raw, image_url if found.
        """
        details: dict[str, Any] = {}

        if not url:
            return details

        # Build the detail URL based on config
        detail_url = self._build_detail_url(url)
        if not detail_url:
            return details

        node_url = detail_url  # Keep variable name for minimal changes below

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(node_url, headers=headers, timeout=30)
            if response.status_code != 200:
                return details

            # Let requests auto-detect encoding from Content-Type header
            soup = BeautifulSoup(response.text, "html.parser")

            # Get description from meta description (most reliable)
            meta_desc = soup.find("meta", {"name": "description"})
            if meta_desc and meta_desc.get("content"):
                details["description"] = meta_desc.get("content", "").strip()

            # Get image from og:image
            og_image = soup.find("meta", {"property": "og:image"})
            if og_image and og_image.get("content"):
                og_image_url = og_image.get("content", "")
                # Fix protocol-relative URLs (//example.com/...) to https://
                if og_image_url.startswith("//"):
                    og_image_url = "https:" + og_image_url
                details["og_image"] = og_image_url
            else:
                # Fallback: find first content image (not logo/icon/theme)
                SKIP_IMAGE_PATTERNS = [
                    "logo", "icon", "avatar", "banner", "favicon",
                    "/theme/", "-theme/", "/o/",  # Liferay theme paths
                    "sprite", "placeholder", "loading", "spinner",
                ]
                for img in soup.select("img"):
                    src = img.get("src", "")
                    if not src:
                        continue
                    # Skip non-content images
                    if any(x in src.lower() for x in SKIP_IMAGE_PATTERNS):
                        continue
                    # Look for document/content images
                    if "/documents/" in src or "/uploads/" in src or "/images/" in src:
                        if src.startswith("/"):
                            from urllib.parse import urlparse
                            parsed = urlparse(node_url)
                            src = f"{parsed.scheme}://{parsed.netloc}{src}"
                        details["og_image"] = src
                        break

            # Get full title from og:title or h1 (listing pages often truncate titles)
            # Skip generic og:titles that are just page names, not event titles
            GENERIC_TITLE_PATTERNS = [
                "detalle-agenda",
                "detalle agenda",
                "agenda cultural",
                "eventos",
                "event detail",
            ]

            og_title = soup.find("meta", {"property": "og:title"})
            if og_title and og_title.get("content"):
                full_title = og_title.get("content", "").strip()
                # Remove site suffix if present (e.g., "Event Title | Lagenda")
                if " | " in full_title:
                    full_title = full_title.split(" | ")[0].strip()
                # Check if og:title is generic (not a real event title)
                is_generic = any(
                    pattern in full_title.lower()
                    for pattern in GENERIC_TITLE_PATTERNS
                )
                if full_title and not full_title.endswith("...") and not is_generic:
                    details["full_title"] = full_title

            # Fallback to .title selector or h1 if no og:title or it was generic
            if "full_title" not in details:
                # Try .title first (works for Gran Canaria, etc.)
                title_elem = soup.select_one(".title")
                if title_elem:
                    full_title = title_elem.get_text(strip=True)
                    if full_title and not full_title.endswith("..."):
                        details["full_title"] = full_title
                else:
                    # Fallback to h1
                    h1 = soup.find("h1")
                    if h1:
                        full_title = h1.get_text(strip=True)
                        if full_title and not full_title.endswith("..."):
                            details["full_title"] = full_title

            # Try to find price in page content
            page_text = soup.get_text().lower()

            # Price patterns - order matters (most specific first)
            price_patterns = [
                # "desde 6 euros", "6 euros"
                r"(?:desde\s+)?(\d+(?:[.,]\d{2})?)\s*euros?",
                # "6€", "6 €"
                r"(\d+(?:[.,]\d{2})?)\s*€",
                # "€6", "€ 6"
                r"€\s*(\d+(?:[.,]\d{2})?)",
                # "entrada desde 6", "entradas 6"
                r"entrada[s]?\s*(?:desde\s+)?(\d+(?:[.,]\d{2})?)",
                # "precio desde 6", "precios 6"
                r"precio[s]?\s*(?:desde\s+)?(\d+(?:[.,]\d{2})?)",
                # "anticipada 15", "taquilla 18"
                r"(?:anticipada|taquilla)\s*[:\s]*(\d+(?:[.,]\d{2})?)",
                # "abono 25"
                r"abono[s]?\s*[:\s]*(\d+(?:[.,]\d{2})?)",
            ]

            for pattern in price_patterns:
                match = re.search(pattern, page_text)
                if match:
                    # Extract numeric value and validate range
                    num_match = re.search(r"(\d+(?:[.,]\d{2})?)", match.group(0))
                    if num_match:
                        price_val = float(num_match.group(1).replace(",", "."))
                        # Skip unrealistic prices (likely false positives from dates)
                        if price_val > 200:
                            continue
                        details["price_raw"] = match.group(0).strip()
                        details["price_value"] = price_val
                        break

            # Check for free indicators (Spanish, Catalan, and common variations)
            free_keywords = [
                "gratuito", "gratis", "entrada libre", "entrada gratuita", "acceso libre",
                "acceso gratuito", "libre acceso", "de balde", "gratuït", "lliure",
                "entrada lliure", "sin coste", "sin costo", "0€", "0 €", "0 euros",
            ]
            for kw in free_keywords:
                if kw in page_text:
                    details["is_free"] = True
                    details["price_raw"] = kw
                    break

            # Try to get fuller description from body content
            body_selectors = [
                ".field-name-body",
                ".field--name-body",
                ".node-content",
                "article .content",
                ".event-description",
            ]
            for selector in body_selectors:
                elem = soup.select_one(selector)
                if elem:
                    body_text = elem.get_text(separator="\n", strip=True)[:1500]
                    if len(body_text) > len(details.get("description", "")):
                        details["description"] = body_text
                    break

            # Store full page content for deep enrichment
            # This allows extracting organizer, contact, accessibility later
            details["page_content"] = soup.get_text(separator="\n", strip=True)[:8000]

            # ============================================================
            # CLM-SPECIFIC FIELD EXTRACTION
            # ============================================================
            if self.bronze_config.ccaa == "Castilla-La Mancha":
                # Category/Type (Música, Teatro, etc.)
                cat_elem = soup.select_one(".field--name-field-tipo-actividad")
                if cat_elem:
                    details["category_name"] = cat_elem.get_text(strip=True)

                # Start time (horario)
                time_elem = soup.select_one(".field--name-field-horario2-actividad")
                if time_elem:
                    time_text = time_elem.get_text(strip=True)
                    # Parse time like "19:30" or "19:30h"
                    time_match = re.search(r"(\d{1,2})[:\.](\d{2})", time_text)
                    if time_match:
                        details["start_time"] = f"{time_match.group(1)}:{time_match.group(2)}"

                # Full address with postal code
                addr_elem = soup.select_one(".field--name-field-direccion-actividad")
                if addr_elem:
                    address_text = addr_elem.get_text(strip=True)
                    details["address"] = address_text
                    # Extract postal code (5 digits)
                    postal_match = re.search(r"\b(\d{5})\b", address_text)
                    if postal_match:
                        details["postal_code"] = postal_match.group(1)

                # Price info (full text)
                price_elem = soup.select_one(".field--name-field-precio2-actividad")
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    # Remove "Precio" prefix if present
                    price_text = re.sub(r"^Precio\s*", "", price_text, flags=re.IGNORECASE)
                    details["price_info"] = price_text
                    # Check for free
                    if any(kw in price_text.lower() for kw in ["gratis", "gratuita", "libre", "free"]):
                        details["is_free"] = True

                # Organizer
                org_elem = soup.select_one(".field--name-field-organizador-actividad")
                if org_elem:
                    org_text = org_elem.get_text(strip=True)
                    # Remove "Organizador/promotor" prefix
                    org_text = re.sub(r"^Organizador/?promotor\s*", "", org_text, flags=re.IGNORECASE)
                    details["organizer_name"] = org_text

                # Target audience
                audience_elem = soup.select_one(".field--name-field-publico-actividad")
                if audience_elem:
                    audience_text = audience_elem.get_text(strip=True)
                    # Remove prefix
                    audience_text = re.sub(r"^Público al que va dirigido\s*", "", audience_text, flags=re.IGNORECASE)
                    details["audience"] = audience_text

            # ============================================================
            # NAVARRA-SPECIFIC FIELD EXTRACTION
            # ============================================================
            if self.bronze_config.ccaa == "Navarra":
                # Category from URL path (exposiciones, arte-contemporaneo, etc.)
                # URL format: https://www.culturanavarra.es/es/agenda/YYYY-MM-DD/categoria/slug
                # Split: ['https:', '', 'www.culturanavarra.es', 'es', 'agenda', 'YYYY-MM-DD', 'categoria', 'slug']
                url_path = node_url.split("/")
                # Find index after the date (YYYY-MM-DD pattern)
                for i, part in enumerate(url_path):
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", part) and i + 1 < len(url_path):
                        category_slug = url_path[i + 1]
                        # Convert slug to title (exposiciones -> Exposiciones)
                        category_name = category_slug.replace("-", " ").title()
                        if category_name and category_name not in ["", "Slug"]:
                            details["category_name"] = category_name
                        break

                # Venue and city from h3 inside evento_dentro (format: "Venue - City")
                venue_city = soup.select_one(".evento_dentro h3")
                if venue_city:
                    venue_city_text = venue_city.get_text(strip=True)
                    if " - " in venue_city_text:
                        parts = venue_city_text.split(" - ", 1)
                        details["venue_name"] = parts[0].strip()
                        details["city"] = parts[1].strip()
                    else:
                        details["venue_name"] = venue_city_text

                # Description from .cuerpo (main content area)
                cuerpo = soup.select_one(".evento_dentro .cuerpo")
                if cuerpo:
                    cuerpo_text = cuerpo.get_text(separator=" ", strip=True)[:2000]
                    if cuerpo_text:
                        details["description"] = cuerpo_text

                # Fallback to meta description if cuerpo is empty
                if not details.get("description"):
                    meta_desc = soup.find("meta", {"name": "description"})
                    if meta_desc and meta_desc.get("content"):
                        details["description"] = meta_desc.get("content", "").strip()

                # Default organizer for Navarra government cultural events
                details["organizer_name"] = "Dirección General de Cultura - Gobierno de Navarra"

                # Note: is_free detection is handled by LLM enricher based on venue context
                # (biblioteca pública, museo, etc. → typically free)

            # ============================================================
            # LA RIOJA-SPECIFIC FIELD EXTRACTION (JSON-LD based)
            # ============================================================
            if self.bronze_config.ccaa == "La Rioja":
                import json

                # Extract JSON-LD structured data
                ld_json = soup.find("script", {"type": "application/ld+json"})
                if ld_json:
                    try:
                        ld_data = json.loads(ld_json.string)
                        if ld_data.get("@type") == "Event":
                            # Venue from location.name
                            location = ld_data.get("location", {})
                            if isinstance(location, dict):
                                details["venue_name"] = location.get("name")
                                # City from address.addressLocality
                                address = location.get("address", {})
                                if isinstance(address, dict):
                                    details["city"] = address.get("addressLocality")

                            # Image URL (may be relative, needs https://)
                            image_url = ld_data.get("image")
                            if image_url and not image_url.startswith("http"):
                                image_url = "https://" + image_url
                            if image_url:
                                details["og_image"] = image_url

                            # Date from startDate (ISO format)
                            start_date_str = ld_data.get("startDate")
                            if start_date_str:
                                details["start_date_iso"] = start_date_str

                            end_date_str = ld_data.get("endDate")
                            if end_date_str:
                                details["end_date_iso"] = end_date_str

                    except (json.JSONDecodeError, KeyError):
                        pass

                # Title from og:title (JSON-LD name is just the slug)
                og_title = soup.find("meta", {"property": "og:title"})
                if og_title and og_title.get("content"):
                    title = og_title.get("content", "").strip()
                    # Remove surrounding quotes if present
                    if title.startswith('"') and title.endswith('"'):
                        title = title[1:-1]
                    if title.startswith("'") and title.endswith("'"):
                        title = title[1:-1]
                    details["full_title"] = title

                # Description from og:description
                og_desc = soup.find("meta", {"property": "og:description"})
                if og_desc and og_desc.get("content"):
                    details["description"] = og_desc.get("content", "").strip()

                # Category from URL path (eventos/logrono/conciertos/...)
                # or from the listing category links
                url_path = node_url.lower()
                category_mapping = {
                    "conciertos": "Conciertos",
                    "teatro": "Teatro",
                    "exposiciones": "Exposiciones",
                    "cineclub": "Cine",
                    "conferencias": "Conferencias",
                    "espectaculos": "Espectáculos",
                    "ferias": "Ferias",
                    "fiestas": "Fiestas",
                    "libros": "Libros",
                    "musica-clasica": "Música Clásica",
                    "planes-con-ninos": "Familiar",
                    "visitas-guiadas": "Visitas Guiadas",
                }
                for slug, cat_name in category_mapping.items():
                    if slug in url_path:
                        details["category_name"] = cat_name
                        break

            # ============================================================
            # VIRALAGENDA-SPECIFIC FIELD EXTRACTION
            # ============================================================
            if self.bronze_config.slug.startswith("viralagenda"):
                # Clean title: remove " - VIRAL" suffix from og:title
                if details.get("full_title"):
                    title = details["full_title"]
                    # Remove common suffixes
                    for suffix in [" - VIRAL", " | VIRAL", " - Viral Agenda", " | Viral Agenda"]:
                        if title.endswith(suffix):
                            title = title[:-len(suffix)].strip()
                            break
                    details["full_title"] = title

                # Viralagenda needs JS rendering, use Firecrawl for detail pages
                try:
                    import httpx
                    firecrawl_url = os.getenv("FIRECRAWL_API_URL", "https://firecrawl.si-erp.cloud")
                    fc_response = httpx.post(
                        f"{firecrawl_url}/scrape",
                        json={
                            "url": node_url,
                            "formats": ["html"],
                            "waitFor": 3000
                        },
                        timeout=30
                    )
                    if fc_response.status_code == 200:
                        fc_data = fc_response.json()
                        fc_content = fc_data.get("content", "")
                        if fc_content:
                            fc_soup = BeautifulSoup(fc_content, "html.parser")

                            # Description from .viral-event-description pre
                            # Preserve paragraph structure with double newlines
                            desc_elem = fc_soup.select_one(".viral-event-description pre")
                            if desc_elem:
                                # Get text with separator to preserve <p> tags as paragraphs
                                desc_text = desc_elem.get_text(separator="\n\n", strip=True)
                                # Clean up excessive whitespace while keeping paragraphs
                                desc_text = re.sub(r'\n{3,}', '\n\n', desc_text)
                                if desc_text:
                                    details["description"] = desc_text

                            # Category from .viral-event-category
                            cat_elem = fc_soup.select_one(".viral-event-category")
                            if cat_elem:
                                details["category_name"] = cat_elem.get_text(strip=True)

                            # Time from .viral-event-time (e.g., "21:00 hasta las 23:00")
                            time_elem = fc_soup.select_one(".viral-event-time")
                            if time_elem:
                                time_text = time_elem.get_text(strip=True)
                                # Extract start time
                                time_match = re.search(r"(\d{1,2}:\d{2})", time_text)
                                if time_match:
                                    details["start_time"] = time_match.group(1)
                                # Extract end time if present
                                end_match = re.search(r"hasta\s*(?:las\s*)?(\d{1,2}:\d{2})", time_text)
                                if end_match:
                                    details["end_time"] = end_match.group(1)

                            # Venue from .viral-event-links-place span[itemprop="name"]
                            venue_elem = fc_soup.select_one('.viral-event-links-place span[itemprop="name"]')
                            if venue_elem:
                                details["venue_name"] = venue_elem.get_text(strip=True)

                            # Address from viral-event-links-place (after venue name)
                            addr_elem = fc_soup.select_one('.viral-event-links-place span[itemprop="address"]')
                            if addr_elem:
                                details["address"] = addr_elem.get_text(strip=True)

                            # Price extraction from page text
                            page_text = fc_soup.get_text().lower()

                            # Check for free event indicators first
                            free_keywords = ["gratis", "gratuito", "entrada libre", "acceso libre", "free"]
                            if any(kw in page_text for kw in free_keywords):
                                details["is_free"] = True
                                details["price_value"] = 0.0
                            else:
                                # Look for price patterns like "12€", "anticipada 15€"
                                price_match = re.search(r"(\d+(?:[.,]\d{2})?)\s*€", page_text)
                                if price_match:
                                    price_val = float(price_match.group(1).replace(",", "."))
                                    if price_val <= 200:  # Skip unrealistic prices
                                        details["price_value"] = price_val
                                        details["is_free"] = False
                                        # Look for descriptive price info (anticipada, taquilla, etc.)
                                        price_desc_match = re.search(
                                            r"(anticipada[:\s]*\d+[€]?|taquilla[:\s]*\d+[€]?|"
                                            r"general[:\s]*\d+[€]?|reducida[:\s]*\d+[€]?|"
                                            r"niños[:\s]*\d+[€]?|jubilados[:\s]*\d+[€]?)",
                                            page_text
                                        )
                                        if price_desc_match:
                                            details["price_info"] = price_desc_match.group(1)

                except Exception as fc_err:
                    logger.debug("viralagenda_detail_firecrawl_error", url=node_url, error=str(fc_err))

        except Exception as e:
            logger.warning("detail_fetch_error", url=node_url, error=str(e))

        return details

    def _parse_event_cards(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        """Parse event cards from a BeautifulSoup object.

        Returns list of raw event dicts.
        """
        events = []
        config = self.bronze_config
        event_cards = soup.select(config.event_card_selector)

        for card in event_cards:
            try:
                # Title - use title_selector
                title_elem = card.select_one(config.title_selector)
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)

                # URL - use link_selector if defined, otherwise try title_selector
                link_selector = config.link_selector or config.title_selector
                link_elem = card.select_one(link_selector)
                url = ""
                if link_elem:
                    url = link_elem.get("href", "")
                    if not url and title_elem != link_elem:
                        url = title_elem.get("href", "")
                if url and not url.startswith("http"):
                    url = (config.base_url or "") + url

                # Extract event ID based on config
                external_id = None
                if url:
                    if config.detail_id_extractor == "query_param" and config.detail_id_param:
                        match = re.search(rf"{config.detail_id_param}=(\d+)", url)
                        if match:
                            external_id = f"{self.source_id}_{match.group(1)}"
                    elif config.ccaa == "Principado de Asturias":
                        # Asturias URL: /calendarsuite/event/{slug}/{id}/{timestamp}/{token}
                        # Extract slug (after /event/) as unique ID
                        match = re.search(r"/event/([^/]+)/", url)
                        if match:
                            external_id = f"{self.source_id}_{match.group(1)}"
                    elif config.ccaa == "La Rioja":
                        # La Rioja URL: /evento/slug-123456.html
                        # Extract numeric ID from end of URL
                        match = re.search(r"-(\d+)\.html$", url)
                        if match:
                            external_id = f"{self.source_id}_{match.group(1)}"
                    elif config.slug.startswith("viralagenda"):
                        # Viralagenda URL: /es/events/{id}/{slug}
                        match = re.search(r"/events/(\d+)/", url)
                        if match:
                            external_id = f"{self.source_id}_{match.group(1)}"
                    elif config.ccaa == "Extremadura":
                        if config.slug.startswith("viralagenda"):
                            # Already handled above
                            pass
                        else:
                            # Badajoz URL: /es/ayto/agenda/evento/{id}/{slug}/
                            match = re.search(r"/evento/(\d+)/", url)
                            if match:
                                external_id = f"{self.source_id}_{match.group(1)}"
                    else:
                        external_id = f"{self.source_id}_{url.split('/')[-1].split('?')[0]}"

                # Image - skip data URIs (placeholders)
                image_url = None
                if config.slug.startswith("viralagenda"):
                    # Viralagenda: image is in data-img attribute of .viral-event-image div
                    img_div = card.select_one(".viral-event-image")
                    if img_div:
                        image_url = img_div.get("data-img")
                    # Fallback: meta itemprop="image"
                    if not image_url:
                        meta_img = card.select_one('meta[itemprop="image"]')
                        if meta_img:
                            image_url = meta_img.get("content")
                elif config.image_selector:
                    img_elem = card.select_one(config.image_selector)
                    if img_elem:
                        # Try src first, then data-src (lazy loading)
                        image_url = img_elem.get("src") or img_elem.get("data-src")
                        # Skip data URIs (SVG placeholders, base64, etc.)
                        if image_url and image_url.startswith("data:"):
                            image_url = None
                        # Make relative URLs absolute
                        if image_url and not image_url.startswith("http"):
                            image_url = (config.base_url or "") + image_url

                # Category
                category = None
                if config.category_selector:
                    category_elems = card.select(config.category_selector)
                    category = category_elems[0].get_text(strip=True) if category_elems else None

                # Locality (for province detection)
                locality = None
                if config.location_selector:
                    loc_elem = card.select_one(config.location_selector)
                    if loc_elem:
                        # For viralagenda, preserve newlines for parsing time/city/venue
                        if config.slug.startswith("viralagenda"):
                            locality = loc_elem.get_text(separator="\n", strip=True)
                        else:
                            locality = loc_elem.get_text(strip=True)

                # Venue/Place name
                venue = None
                start_time_parsed = None
                if config.venue_selector:
                    venue_elem = card.select_one(config.venue_selector)
                    if venue_elem:
                        # For Badajoz: selector is icon (.fa-map-marker-alt), text is in parent
                        if config.ccaa == "Extremadura" and venue_elem.name == "i":
                            parent = venue_elem.parent
                            if parent:
                                # Get text from parent, excluding the icon
                                venue = parent.get_text(strip=True)
                        else:
                            venue = venue_elem.get_text(strip=True)
                elif config.slug.startswith("viralagenda") and locality:
                    # Parse viralagenda locality format:
                    # "19:30\nValladolid y Campiña del Pisuerga\nMuseo Casa de Cervantes\nConciertos"
                    parts = [p.strip() for p in locality.split("\n") if p.strip()]

                    # First part is time (HH:MM) or "N/D"
                    if parts and re.match(r"^\d{1,2}:\d{2}$", parts[0]):
                        time_str = parts.pop(0)
                        try:
                            h, m = time_str.split(":")
                            from datetime import time as time_cls
                            start_time_parsed = time_cls(int(h), int(m))
                        except (ValueError, IndexError):
                            pass
                    elif parts and parts[0] == "N/D":
                        parts.pop(0)

                    # Second part is comarca (we'll extract city in transform)
                    # Third part is venue
                    if len(parts) >= 2:
                        venue = parts[1]  # Venue is second item after comarca
                    elif len(parts) == 1:
                        venue = parts[0]  # Only one item, use as venue
                elif not config.venue_selector and config.location_selector:
                    venue = locality
                elif config.category_selector:
                    category_elems = card.select(config.category_selector)
                    venue = category_elems[1].get_text(strip=True) if len(category_elems) > 1 else None

                # Date - try range parsing first, then flexible parsing
                date_elem = card.select_one(config.date_selector)
                date_str = date_elem.get_text(strip=True) if date_elem else None

                # Initialize date variables
                start_date = None
                end_date = None

                # Special handling for viralagenda.com
                # Format can be:
                # - "JUE05FEBHOY" (compact)
                # - "MIE\n11\nFEB\nHOY" (with newlines from Firecrawl)
                # - "MIE\n11\nFEB\nHOY\nHASTA\n28\nFEB" (range with newlines)
                if config.slug.startswith("viralagenda") and date_str:
                    months_short = {
                        "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4,
                        "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8,
                        "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
                    }
                    year = date.today().year

                    # Normalize: remove newlines and whitespace, uppercase
                    date_clean = re.sub(r"\s+", "", date_str.upper())

                    # Extract start date: DAY_NAME + DAY_NUM + MONTH_CODE
                    # Pattern: 3 letters (day) + 1-2 digits + 3 letters (month)
                    start_match = re.search(r"([A-ZÁÉÍÓÚ]{2,4})(\d{1,2})([A-Z]{3})", date_clean)
                    if start_match:
                        _, day_num, month_code = start_match.groups()
                        month_num = months_short.get(month_code, 0)
                        if month_num:
                            try:
                                start_date = date(year, month_num, int(day_num))
                                # If date is in past, assume next year
                                if start_date < date.today():
                                    start_date = date(year + 1, month_num, int(day_num))
                                end_date = start_date
                            except ValueError:
                                pass

                    # Check for end date (HASTA pattern)
                    end_match = re.search(r"HASTA(\d{1,2})([A-Z]{3})", date_clean)
                    if end_match:
                        end_day, end_month_code = end_match.groups()
                        end_month_num = months_short.get(end_month_code, 0)
                        if end_month_num:
                            try:
                                end_date = date(year, end_month_num, int(end_day))
                                if end_date < start_date:
                                    end_date = date(year + 1, end_month_num, int(end_day))
                            except ValueError:
                                pass

                if not start_date:
                    start_date, end_date = self._parse_date_range(date_str)
                if not start_date:
                    parsed_date = self._parse_date_flexible(date_str)
                    start_date = parsed_date or date.today()
                    end_date = parsed_date

                # Time (if separate selector)
                time_str = None
                if config.time_selector:
                    time_elem = card.select_one(config.time_selector)
                    if time_elem:
                        # For Badajoz: selector is icon (.fa-clock), text is in parent
                        if config.ccaa == "Extremadura" and time_elem.name == "i":
                            parent = time_elem.parent
                            if parent:
                                time_str = parent.get_text(strip=True)
                        else:
                            time_str = time_elem.get_text(strip=True)

                event = {
                    "title": title,
                    "external_url": url,
                    "external_id": external_id,
                    "image_url": image_url,
                    "category_raw": category,
                    "locality": locality,
                    "venue_name": venue,
                    "start_date": start_date,
                    "end_date": end_date,
                    "raw_date": date_str,
                    "raw_time": time_str,
                }
                events.append(event)

            except Exception as e:
                logger.warning("bronze_parse_error", error=str(e))
                continue

        return events

    async def fetch_events(self, enrich: bool = True, fetch_details: bool = False) -> list[dict[str, Any]]:
        """Fetch and parse events from listing page(s).

        Args:
            enrich: If True, apply LLM enrichment (not used here, done in insert script)
            fetch_details: If True, fetch each event's detail page for description

        Returns:
            List of raw event dicts
        """
        config = self.bronze_config
        events = []
        seen_ids = set()  # Dedup across pages

        # Fetch multiple pages if configured
        for page_num in range(config.max_pages):
            # Build page URL
            if page_num == 0:
                page_url = self.source_url
            else:
                separator = "&" if "?" in self.source_url else "?"
                page_url = f"{self.source_url}{separator}{config.page_param}={page_num}"

            logger.info(
                "fetching_bronze_source",
                source=self.source_id,
                url=page_url,
                page=page_num + 1,
            )

            html = self._fetch_page(page_url)
            if not html:
                if page_num == 0:
                    logger.error("bronze_fetch_failed", source=self.source_id)
                    return []
                else:
                    # No more pages
                    break

            soup = BeautifulSoup(html, "html.parser")
            page_events = self._parse_event_cards(soup)

            logger.info(
                "bronze_cards_found",
                source=self.source_id,
                page=page_num + 1,
                count=len(page_events),
            )

            if not page_events:
                # No events on this page, stop pagination
                break

            # Dedup and add events
            for event in page_events:
                eid = event.get("external_id")
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    events.append(event)

        logger.info(
            "bronze_events_parsed",
            source=self.source_id,
            count=len(events),
            pages_fetched=min(page_num + 1, config.max_pages),
        )

        # Optionally fetch detail pages for descriptions
        if fetch_details and events:
            logger.info(
                "fetching_event_details",
                source=self.source_id,
                count=len(events),
            )
            for i, event in enumerate(events):
                url = event.get("external_url")
                if url:
                    details = self._fetch_event_detail(url)
                    # Prefer full title from detail page over truncated listing title
                    if details.get("full_title"):
                        event["title"] = details["full_title"]
                    if details.get("description"):
                        event["description"] = details["description"]
                    if details.get("price_raw"):
                        event["price_raw"] = details["price_raw"]
                    if details.get("price_value") is not None:
                        event["price_value"] = details["price_value"]
                    if details.get("is_free") is not None:
                        event["is_free"] = details["is_free"]
                    if details.get("dates_raw"):
                        event["dates_raw"] = details["dates_raw"]
                    # Prefer full-size og:image over thumbnail from listing
                    if details.get("og_image"):
                        event["image_url"] = details["og_image"]
                    # Store page content for deep enrichment
                    if details.get("page_content"):
                        event["page_content"] = details["page_content"]

                    # CCAA-specific fields (CLM, Navarra, etc.)
                    if details.get("category_name"):
                        event["category_name"] = details["category_name"]
                    if details.get("start_time"):
                        event["start_time"] = details["start_time"]
                    if details.get("address"):
                        event["address"] = details["address"]
                    if details.get("postal_code"):
                        event["postal_code"] = details["postal_code"]
                    if details.get("price_info"):
                        event["price_info"] = details["price_info"]
                    if details.get("organizer_name"):
                        event["organizer_name"] = details["organizer_name"]
                    if details.get("audience"):
                        event["audience"] = details["audience"]
                    # Navarra-specific: city and venue from detail page
                    if details.get("city"):
                        event["city"] = details["city"]
                    if details.get("venue_name"):
                        event["venue_name"] = details["venue_name"]

                    if (i + 1) % 5 == 0:
                        logger.info(
                            "detail_fetch_progress",
                            fetched=i + 1,
                            total=len(events),
                        )

            logger.info(
                "detail_fetch_complete",
                source=self.source_id,
                with_description=sum(1 for e in events if e.get("description")),
            )

        return events

    def parse_event(self, raw_event: dict[str, Any]) -> EventCreate | None:
        """Convert raw event dict to EventCreate model."""
        try:
            title = raw_event.get("title", "").strip()
            if not title:
                return None

            # Get venue and locality
            venue_name = raw_event.get("venue_name")
            locality = raw_event.get("locality") or venue_name

            # Determine province based on CCAA
            if self.bronze_config.ccaa == "Castilla-La Mancha":
                province = get_clm_province(locality)
                # For CLM, city is the locality (cleaned)
                city = locality.replace("(capital)", "").strip() if locality else None
            elif self.bronze_config.ccaa == "Canarias":
                # Default province depends on source: Gran Canaria sources -> Las Palmas
                default_prov = "Las Palmas" if "grancanaria" in self.bronze_config.slug else "Santa Cruz de Tenerife"
                province = get_canarias_province(locality, default=default_prov)
                # City detection for Canarias
                city = None
                if venue_name:
                    venue_lower = venue_name.lower()
                    for muni in TENERIFE_MUNICIPALITIES | GRAN_CANARIA_MUNICIPALITIES:
                        if muni in venue_lower:
                            city = venue_name
                            break
                    if not city:
                        city = venue_name
            elif self.bronze_config.ccaa == "Navarra":
                # Navarra is uniprovincial
                province = "Navarra"
                # City comes from detail page extraction or locality
                city = raw_event.get("city") or locality
            elif self.bronze_config.ccaa == "Principado de Asturias":
                # Asturias is uniprovincial
                province = "Asturias"
                # Extract city from title using helper function
                city = extract_asturias_city(title)
                # Fallback to locality if no city in title
                if not city:
                    city = locality
            elif self.bronze_config.ccaa == "La Rioja":
                # La Rioja is uniprovincial
                province = "La Rioja"
                # City comes from JSON-LD or listing locality
                city = raw_event.get("city") or locality
                # Clean up city if it has extra whitespace
                if city:
                    city = city.strip()
            elif self.bronze_config.slug.startswith("viralagenda"):
                # Viralagenda sources are province-specific
                province = self.bronze_config.province
                city = province  # Default to province capital

                # Parse locality format from Firecrawl:
                # "19:30\n\nValladolid y Campiña del Pisuerga\n\n\n\nMuseo de la Ciencia\n\nMúsica"
                # Parts separated by newlines: [time, comarca, venue, category]
                if locality:
                    # Split by multiple newlines and filter empty
                    parts = [p.strip() for p in re.split(r"\n+", locality) if p.strip()]

                    # First part might be time (HH:MM) or "N/D"
                    start_time = None
                    if parts and re.match(r"^\d{1,2}:\d{2}$", parts[0]):
                        time_str = parts.pop(0)
                        try:
                            h, m = time_str.split(":")
                            from datetime import time as time_cls
                            start_time = time_cls(int(h), int(m))
                            raw_event["start_time"] = start_time
                        except (ValueError, IndexError):
                            pass
                    elif parts and parts[0] == "N/D":
                        parts.pop(0)  # Remove "N/D" (no time specified)

                    # Second part is usually comarca/region (e.g., "Valladolid y Campiña del Pisuerga")
                    # Extract city name from comarca if possible
                    if parts:
                        comarca = parts.pop(0)
                        # Extract first word/city before " y " or before common suffixes
                        city_match = re.match(r"^([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+de\s+[A-Za-záéíóúñ]+)?)", comarca)
                        if city_match:
                            city = city_match.group(1)

                    # Third part might be venue name
                    if parts:
                        potential_venue = parts.pop(0)
                        # Check it's not a category
                        categories = {"Música", "Musica", "Teatro", "Danza", "Cine", "Exposiciones",
                                     "Conferencias", "Infantil", "Flamenco", "Varios", "Formación"}
                        if potential_venue not in categories:
                            venue_name = potential_venue

                    # Fourth part is usually category (we can capture for enrichment later)
                    if parts:
                        raw_event["category_raw"] = parts[0]
            elif self.bronze_config.ccaa == "Extremadura":
                # Extremadura has 2 provinces: Badajoz and Cáceres
                if self.bronze_config.slug == "badajoz_agenda":
                    # Badajoz city source - all events in Badajoz
                    province = "Badajoz"
                    city = "Badajoz"
                else:
                    # Other Extremadura sources - detect province from locality
                    province = self.bronze_config.province or "Cáceres"
                    city = raw_event.get("city") or locality
                    if locality:
                        loc_lower = locality.lower()
                        if "badajoz" in loc_lower:
                            province = "Badajoz"
                        elif "cáceres" in loc_lower or "caceres" in loc_lower:
                            province = "Cáceres"
            else:
                # Default: use configured province
                province = self.bronze_config.province
                city = locality

            # Use description from detail page if available
            description = raw_event.get("description")

            # Parse start_time if available
            start_time = None
            if raw_event.get("start_time"):
                from datetime import time as dt_time
                raw_time = raw_event["start_time"]
                # Already a time object (from viralagenda parsing)
                if isinstance(raw_time, dt_time):
                    start_time = raw_time
                # String format "HH:MM"
                elif isinstance(raw_time, str):
                    try:
                        parts = raw_time.split(":")
                        start_time = dt_time(int(parts[0]), int(parts[1]))
                    except (ValueError, IndexError):
                        pass

            # Get price info from detail page
            # If no price info found, leave it as None (unknown) rather than a confusing message
            price = raw_event.get("price_value")  # Numeric price (float)
            price_info = raw_event.get("price_info")  # Descriptive text
            is_free = raw_event.get("is_free")  # None = unknown, True = free, False = paid

            # If we have a numeric price, set is_free accordingly
            if price is not None and price > 0:
                is_free = False
            elif price == 0:
                is_free = True

            # Build organizer if available
            organizer = None
            if raw_event.get("organizer_name"):
                from src.core.event_model import EventOrganizer, OrganizerType
                organizer = EventOrganizer(
                    name=raw_event["organizer_name"],
                    type=OrganizerType.INSTITUCION,  # Default for CLM government site
                )

            # Extract contact info from description
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
                title=clean_text(title),
                description=clean_text(description),  # From detail page or None
                start_date=raw_event.get("start_date", date.today()),
                end_date=raw_event.get("end_date"),
                start_time=start_time,  # NEW: parsed time
                location_type=LocationType.PHYSICAL,
                venue_name=clean_text(venue_name),
                address=clean_text(raw_event.get("address")),  # NEW: full address
                city=clean_text(city),
                province=province,
                comunidad_autonoma=self.ccaa,
                postal_code=raw_event.get("postal_code"),  # NEW: postal code
                source_id=self.source_id,
                external_url=raw_event.get("external_url"),
                external_id=raw_event.get("external_id"),
                source_image_url=raw_event.get("image_url"),
                # Category from detail page
                category_name=clean_text(raw_event.get("category_name")),  # NEW: Música, Teatro, etc.
                # Organizer
                organizer=organizer,  # NEW: organizer info
                # These will be enriched by LLM
                summary=None,
                category_slugs=[],
                is_free=is_free,  # None=unknown, True=free, False=paid
                price=price,  # Numeric price (float)
                price_info=clean_text(price_info),  # Descriptive text (e.g., "rebaja para niños")
                # Contact and registration from description extraction
                contact=contact,
                registration_url=registration_url,
                requires_registration=requires_registration,
                registration_info=registration_info,
            )

        except Exception as e:
            logger.error(
                "bronze_event_parse_error",
                title=raw_event.get("title", "unknown"),
                error=str(e),
            )
            return None


# ============================================================
# ADAPTER REGISTRATION
# ============================================================


def create_bronze_adapter_class(source_slug: str) -> type:
    """Create a registered adapter class for a Bronze source."""

    class DynamicBronzeAdapter(BronzeScraperAdapter):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(source_slug, *args, **kwargs)

    DynamicBronzeAdapter.__name__ = (
        f"BronzeAdapter_{source_slug.replace('-', '_').title()}"
    )
    return DynamicBronzeAdapter


# Create and register adapter classes for all Bronze sources
for slug in BRONZE_SOURCES:
    create_bronze_adapter_class(slug)
