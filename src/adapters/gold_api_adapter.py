"""Generic adapter for Level Gold (Nivel Oro) APIs - CCAA with structured APIs.

This adapter supports multiple CCAA APIs with different JSON structures,
normalizing them to the unified EventCreate model.

Supported sources:
- Madrid (JSON-LD)
- Catalunya (Socrata/SODA)
- Euskadi (REST API)
- Castilla y León (CKAN OData)
- Andalucía (CKAN)
"""

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from src.adapters import register_adapter
from src.core.base_adapter import AdapterType, BaseAdapter
from src.core.event_model import EventAccessibility, EventContact, EventCreate, EventOrganizer, LocationType, OrganizerType


# Import from centralized config to avoid duplication
from src.config.sources import PaginationType
from src.core.llm_enricher import EnricherTier as SourceTier  # Alias for backward compat


@dataclass
class GoldSourceConfig:
    """Configuration for a Gold-level API source."""

    slug: str
    name: str
    url: str
    ccaa: str
    ccaa_code: str

    # Source quality tier (determines LLM model)
    tier: SourceTier = SourceTier.ORO

    # Pagination
    pagination_type: PaginationType = PaginationType.NONE
    page_size: int = 100
    offset_param: str = "offset"
    limit_param: str = "limit"
    page_param: str = "_page"

    # Response structure
    items_path: str = ""  # JSON path to items array (empty = root is array)
    total_count_path: str = ""  # JSON path to total count
    total_pages_path: str = ""  # JSON path to total pages (for PAGE pagination)

    # Field mappings (source field -> EventCreate field)
    # Supports dot notation for nested fields
    field_mappings: dict[str, str] | None = None

    # Default province (if not in data)
    default_province: str | None = None

    # Date format (for parsing)
    date_format: str = "%Y-%m-%d"
    datetime_format: str = "%Y-%m-%dT%H:%M:%SZ"

    # Price detection
    free_value: str | None = "Gratuito"  # Value that indicates free event
    free_field: str | None = None  # Separate boolean field for is_free

    # Image URL prefix (if images are relative)
    image_url_prefix: str = ""


# ============================================================
# SOURCE CONFIGURATIONS
# ============================================================

GOLD_SOURCES: dict[str, GoldSourceConfig] = {
    "catalunya_agenda": GoldSourceConfig(
        slug="catalunya_agenda",
        name="Agenda Cultural de Catalunya",
        url="https://analisi.transparenciacatalunya.cat/resource/rhpv-yr4f.json",
        ccaa="Catalunya",
        ccaa_code="CT",
        pagination_type=PaginationType.SOCRATA,
        page_size=1000,
        offset_param="$offset",
        limit_param="$limit",
        items_path="",  # Root is array
        date_format="%Y-%m-%dT%H:%M:%S.%f",
        free_value="Si",
        free_field="gratuita",
        image_url_prefix="https://agenda.cultura.gencat.cat",
        field_mappings={
            "codi": "external_id",
            "denominaci": "title",
            "descripcio": "description",
            "data_inici": "start_date",
            "data_fi": "end_date",
            "horari": "time_info",
            "gratuita": "is_free_text",
            "entrades": "price_info",
            "espai": "venue_name",
            "adre_a": "address",
            "codi_postal": "postal_code",
            "localitat": "city",
            "comarca_i_municipi": "comarca",
            "latitud": "latitude",
            "longitud": "longitude",
            "tags_categor_es": "category_tags",
            "imatges": "images",
            "linkbotoentrades": "external_url",
            "subt_tol": "summary",  # Subtitle as summary
            "url": "organizer_url",  # Venue/organizer website
            "email": "contact_email",  # Contact email
            "tel_fon": "contact_phone",  # Contact phone
            "modalitat": "modality_text",  # "Presencial", "Online", "Híbrid"
            "destacada": "is_featured_text",  # "Si" / "No"
        },
    ),
    "euskadi_kulturklik": GoldSourceConfig(
        slug="euskadi_kulturklik",
        name="Kulturklik - Agenda Cultural Euskadi",
        url="https://api.euskadi.eus/culture/events/v1.0/events/upcoming",
        ccaa="País Vasco",
        ccaa_code="PV",
        pagination_type=PaginationType.PAGE,
        page_size=20,
        page_param="_page",
        items_path="items",
        total_pages_path="totalPages",
        datetime_format="%Y-%m-%dT%H:%M:%SZ",
        field_mappings={
            "id": "external_id",
            "nameEs": "title",
            "descriptionEs": "description",
            "startDate": "start_date",
            "endDate": "end_date",
            "openingHoursEs": "time_info",
            "priceEs": "price_info",
            "establishmentEs": "venue_name",
            "municipalityEs": "city",
            "municipalityLatitude": "latitude",
            "municipalityLongitude": "longitude",
            "typeEs": "category_name",
            "images": "images",
            "purchaseUrlEs": "external_url",
            "provinceNoraCode": "province_code",
            "companyEs": "organizer_name",
            "sourceNameEs": "organizer_source",  # Fallback organizer name
            "sourceUrlEs": "organizer_url",  # Organizer/source website
        },
    ),
    "castilla_leon_agenda": GoldSourceConfig(
        slug="castilla_leon_agenda",
        name="Agenda Cultural Castilla y León",
        url="https://analisis.datosabiertos.jcyl.es/api/explore/v2.1/catalog/datasets/eventos-de-la-agenda-cultural-categorizados-y-geolocalizados/records",
        ccaa="Castilla y León",
        ccaa_code="CL",
        pagination_type=PaginationType.OFFSET_LIMIT,
        page_size=100,
        offset_param="offset",
        limit_param="limit",
        items_path="results",
        total_count_path="total_count",
        date_format="%Y-%m-%d",
        free_value="Gratuito",
        field_mappings={
            "id_evento": "external_id",
            "titulo": "title",
            "descripcion": "description",
            "fecha_inicio": "start_date",
            "fecha_fin": "end_date",
            "hora_inicio": "start_time",
            "hora_fin": "end_time",
            "precio": "price_info",
            "lugar_celebracion": "venue_name",
            "calle": "address",
            "cp": "postal_code",
            "nombre_localidad": "city",
            "nombre_provincia": "province",
            "latitud": "latitude",
            "longitud": "longitude",
            "posicion.lat": "latitude_alt",
            "posicion.lon": "longitude_alt",
            "categoria": "category_name",
            "tematica": "category_tags",
            "imagen_evento": "image_url",
            "enlace_contenido": "external_url",
            "destinatarios": "audience",
        },
    ),
    "andalucia_agenda": GoldSourceConfig(
        slug="andalucia_agenda",
        name="Agenda de Eventos Junta de Andalucía",
        # Nueva API más estable (contentapi) - ordena por fecha desc para eventos futuros
        url="https://www.juntadeandalucia.es/ssdigitales/datasets/contentapi/1.0.0/search/agenda.json?_source=data&sort=date:desc",
        ccaa="Andalucía",
        ccaa_code="AN",
        pagination_type=PaginationType.OFFSET_LIMIT,
        page_size=50,  # Máximo permitido por la API
        offset_param="from",
        limit_param="size",
        items_path="resultado",  # Los eventos están en "resultado"
        total_count_path="numResultados",
        date_format="%Y-%m-%d",
        free_value="Gratuito",
        image_url_prefix="https://www.juntadeandalucia.es",
        # Datos aplanados por _preprocess_andalucia
        field_mappings={
            "external_id": "external_id",
            "title": "title",
            "description": "description",
            "start_date": "start_date",
            "end_date": "end_date",
            "time_info": "time_info",
            "price_info": "price_info",
            "address": "address",
            "city": "city",
            "province": "province",
            "category_name": "category_name",
            "image_url": "image_url",
            "external_url": "external_url",
        },
    ),
    "madrid_datos_abiertos": GoldSourceConfig(
        slug="madrid_datos_abiertos",
        name="Madrid Datos Abiertos - Eventos Culturales",
        url="https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json",
        ccaa="Comunidad de Madrid",
        ccaa_code="MD",
        pagination_type=PaginationType.NONE,
        items_path="@graph",
        default_province="Madrid",
        datetime_format="%Y-%m-%d %H:%M:%S.%f",
        field_mappings={
            "id": "external_id",
            "title": "title",
            "description": "description",
            "dtstart": "start_date",
            "dtend": "end_date",
            "time": "start_time",
            "free": "is_free_int",
            "price": "price_info",
            "event-location": "venue_name",
            "address.area.street-address": "address",
            "address.area.postal-code": "postal_code",
            "address.area.locality": "city",
            "address.district.@id": "district_uri",
            "location.latitude": "latitude",
            "location.longitude": "longitude",
            "@type": "category_uri",
            "organization.organization-name": "organizer_name",
            "organization.accesibility": "accessibility_codes",
            "link": "external_url",
            "audience": "audience",
        },
    ),
    "valencia_ivc": GoldSourceConfig(
        slug="valencia_ivc",
        name="Institut Valencià de Cultura - Agenda Cultural",
        url="https://dadesobertes.gva.es/dataset/25cc4d21-e1dd-4d05-b057-dbcc44d4338c/resource/15084e00-c416-4b4d-b229-7a06f4bf07b0/download/lista-de-actividades-culturales-programadas-por-el-ivc.json",
        ccaa="Comunidad Valenciana",
        ccaa_code="VC",
        pagination_type=PaginationType.NONE,
        items_path="data",  # Data is inside "data" array
        date_format="%d/%m/%Y",  # DD/MM/YYYY format
        free_value="Gratuito",
        field_mappings={
            "titulo_evento": "title",
            "tipo_evento": "category_name",
            "fecha_inicio": "start_date",
            "fecha_fin": "end_date",
            "hora": "time_info",
            "provincia": "province",
            "municipio": "city",
            "lugar_evento": "venue_name",
            "direccion": "address",
            "cp": "postal_code",
            "precio": "price_info",
            "latitud": "latitude",
            "longitud": "longitude",
            "web": "external_url",
        },
    ),
    "zaragoza_cultura": GoldSourceConfig(
        slug="zaragoza_cultura",
        name="Agenda Cultural de Zaragoza",
        url="https://www.zaragoza.es/sede/servicio/cultura.json",
        ccaa="Aragón",
        ccaa_code="AR",
        pagination_type=PaginationType.NONE,
        # Response has featuredEvents + todayEvents arrays (handled specially)
        items_path="__zaragoza_special__",  # Marker for special handling
        default_province="Zaragoza",
        datetime_format="%Y-%m-%dT%H:%M:%S",
        field_mappings={
            "id": "external_id",
            "title": "title",
            "description": "description",
            "startDate": "start_date",
            "endDate": "end_date",
            "location": "venue_name",
            "type": "category_name",
            "image": "image_url",
            "url": "external_url",
            "priceComment": "price_info",
            "geometry.coordinates": "utm_coordinates",
            # Nested in subEvent[0].location
            "subEvent.0.location.streetAddress": "address",
            "subEvent.0.location.addressLocality": "city",
            "subEvent.0.location.postalCode": "postal_code",
            "subEvent.0.location.telephone": "contact_phone",
            "subEvent.0.location.email": "contact_email",
            # Category from category array
            "category.0.title": "category_name_alt",
        },
    ),
}

# Number of fields per event for Valencia IVC (flat array format)
VALENCIA_IVC_FIELDS_PER_EVENT = 16

# Euskadi province codes mapping
EUSKADI_PROVINCE_CODES = {
    "1": "Araba/Álava",
    "20": "Gipuzkoa",
    "48": "Bizkaia",
}

# Madrid accessibility codes (from datos.madrid.es)
# Maps to event_accessibility table fields
MADRID_ACCESSIBILITY_CODES = {
    "1": {"field": "wheelchair_accessible", "desc": "Accesible para personas con discapacidad física"},
    "2": {"field": "braille_materials", "desc": "Accesible para personas con discapacidad visual"},
    "3": {"field": "hearing_loop", "desc": "Accesible para personas con discapacidad auditiva"},
    "4": {"field": "other_facilities", "desc": "Accesible para personas con discapacidad intelectual"},
    "5": {"field": "wheelchair_accessible", "desc": "Reserva de plazas para personas con movilidad reducida"},
    "6": {"field": "hearing_loop", "desc": "Bucle de inducción magnética"},
    "7": {"field": "sign_language", "desc": "Lengua de signos"},
    "8": {"field": "other_facilities", "desc": "Subtitulado"},
    "9": {"field": "other_facilities", "desc": "Audiodescripción"},
}


def get_nested_value(data: dict, path: str) -> Any:
    """Get value from nested dict using dot notation."""
    if not path:
        return None
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
        if value is None:
            return None
    return value


def remove_boilerplate(text: str) -> str:
    """Remove common boilerplate phrases from event descriptions.

    Removes:
    - "Para más información..." and variants
    - Generic contact phrases
    - Promotional/spam text
    - Disclaimers
    - Redundant "visit our web" type phrases
    """
    # Patterns to remove (case insensitive)
    # Each pattern removes the phrase and everything after it on the same line
    boilerplate_patterns = [
        # "Para más información" variants
        r"para\s+(más|mas)\s+informaci[oó]n[^.\n]*[.\n]?",
        r"m[aá]s\s+informaci[oó]n\s+en[^.\n]*[.\n]?",
        r"informaci[oó]n\s+y\s+reservas?[^.\n]*[.\n]?",
        # "Consulte/Visite nuestra web" variants
        r"consulte?\s+(nuestra\s+)?(p[aá]gina\s+)?web[^.\n]*[.\n]?",
        r"visite?\s+(nuestra\s+)?(p[aá]gina\s+)?web[^.\n]*[.\n]?",
        r"en\s+(nuestra\s+)?(p[aá]gina\s+)?web[^.\n]*[.\n]?",
        # Contact redirects
        r"contacte?\s+(con\s+nosotros|nos)[^.\n]*[.\n]?",
        r"ll[aá]me?(nos)?\s+(al|para)[^.\n]*[.\n]?",
        r"esc[ií]?r[ií]?b[ae]?(nos)?\s+(a|al|un)[^.\n]*[.\n]?",
        # Generic promotional
        r"no\s+te\s+lo\s+pierdas[^.\n]*[.\n]?",
        r"¡?te\s+esperamos!?[^.\n]*[.\n]?",
        r"¡?no\s+faltes!?[^.\n]*[.\n]?",
        r"¡?an[ií]mate!?[^.\n]*[.\n]?",
        r"¡?ap[uú]ntate!?[^.\n]*[.\n]?",
        # Disclaimers
        r"la\s+organizaci[oó]n\s+se\s+reserva[^.\n]*[.\n]?",
        r"sujeto\s+a\s+cambios[^.\n]*[.\n]?",
        r"aforo\s+limitado[^.\n]*[.\n]?",
        r"hasta\s+completar\s+aforo[^.\n]*[.\n]?",
        # Redundant info phrases
        r"pr[oó]ximamente\s+m[aá]s\s+(informaci[oó]n|detalles)[^.\n]*[.\n]?",
        r"pendiente\s+de\s+confirmar[^.\n]*[.\n]?",
        # Social media
        r"s[ií]guenos\s+en[^.\n]*[.\n]?",
        r"@\w+\s*(en\s+)?(twitter|instagram|facebook)[^.\n]*[.\n]?",
    ]

    clean = text
    for pattern in boilerplate_patterns:
        clean = re.sub(pattern, "", clean, flags=re.IGNORECASE)

    return clean


def clean_html(text: str | None) -> str | None:
    """Convert HTML to clean text preserving structure (paragraphs, lists, line breaks)."""
    if not text:
        return None

    clean = text

    # Convert block elements to line breaks BEFORE removing tags
    # Paragraphs: <p>...</p> -> content + double newline
    clean = re.sub(r"</p>\s*", "\n\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<p[^>]*>", "", clean, flags=re.IGNORECASE)

    # Divs: </div> -> newline
    clean = re.sub(r"</div>\s*", "\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<div[^>]*>", "", clean, flags=re.IGNORECASE)

    # Line breaks
    clean = re.sub(r"<br\s*/?>", "\n", clean, flags=re.IGNORECASE)

    # Lists: <li> -> bullet point
    clean = re.sub(r"<li[^>]*>", "\n• ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"</li>", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"</?[ou]l[^>]*>", "\n", clean, flags=re.IGNORECASE)

    # Headers: add newlines
    clean = re.sub(r"<h[1-6][^>]*>", "\n\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"</h[1-6]>", "\n", clean, flags=re.IGNORECASE)

    # Remove remaining HTML tags (spans, strong, em, a, etc.)
    clean = re.sub(r"<[^>]+>", "", clean)

    # Decode ALL HTML entities (e.g., &oacute; → ó, &ldquo; → ")
    clean = html.unescape(clean)

    # Normalize multiple newlines to max 2
    clean = re.sub(r"\n{3,}", "\n\n", clean)

    # Normalize spaces (but preserve newlines)
    clean = re.sub(r"[^\S\n]+", " ", clean)

    # Clean up lines (strip each line)
    lines = [line.strip() for line in clean.split("\n")]
    clean = "\n".join(lines)

    # Remove boilerplate phrases (Para más información, etc.)
    clean = remove_boilerplate(clean)

    # Re-normalize after boilerplate removal (may leave empty lines)
    clean = re.sub(r"\n{3,}", "\n\n", clean)

    # Remove leading/trailing whitespace
    clean = clean.strip()

    return clean if clean else None


class GoldAPIAdapter(BaseAdapter):
    """Generic adapter for Gold-level CCAA APIs.

    This adapter can be configured for different sources by passing the
    source_slug parameter, which loads the appropriate configuration.
    """

    adapter_type = AdapterType.API
    tier = "gold"

    def __init__(self, source_slug: str, *args: Any, **kwargs: Any) -> None:
        """Initialize adapter with source configuration.

        Args:
            source_slug: Key from GOLD_SOURCES dict
        """
        if source_slug not in GOLD_SOURCES:
            raise ValueError(f"Unknown source: {source_slug}. Available: {list(GOLD_SOURCES.keys())}")

        # Use gold_config to avoid conflict with BaseAdapter.config (AdapterConfig)
        self.gold_config = GOLD_SOURCES[source_slug]
        self.source_id = self.gold_config.slug
        self.source_name = self.gold_config.name
        self.source_url = self.gold_config.url
        self.ccaa = self.gold_config.ccaa
        self.ccaa_code = self.gold_config.ccaa_code

        super().__init__(*args, **kwargs)

    async def fetch_events(self, max_pages: int = 10) -> list[dict[str, Any]]:
        """Fetch events from the API, handling pagination.

        Args:
            max_pages: Maximum number of pages to fetch (for paginated APIs)
        """
        self.logger.info("fetching_gold_api", source=self.source_id, url=self.source_url)

        all_items: list[dict[str, Any]] = []

        try:
            if self.gold_config.pagination_type == PaginationType.NONE:
                # Single request
                data = await self._fetch_json(self.source_url)
                items = self._extract_items(data)
                all_items.extend(items)

            elif self.gold_config.pagination_type == PaginationType.SOCRATA:
                # Socrata/SODA pagination
                offset = 0
                while True:
                    url = f"{self.source_url}?{self.gold_config.limit_param}={self.gold_config.page_size}&{self.gold_config.offset_param}={offset}"
                    data = await self._fetch_json(url)
                    items = self._extract_items(data)

                    if not items:
                        break

                    all_items.extend(items)
                    offset += len(items)

                    if len(items) < self.gold_config.page_size or offset // self.gold_config.page_size >= max_pages:
                        break

            elif self.gold_config.pagination_type == PaginationType.OFFSET_LIMIT:
                # Standard offset/limit pagination
                offset = 0
                while True:
                    separator = "&" if "?" in self.source_url else "?"
                    url = f"{self.source_url}{separator}{self.gold_config.limit_param}={self.gold_config.page_size}&{self.gold_config.offset_param}={offset}"
                    data = await self._fetch_json(url)
                    items = self._extract_items(data)

                    if not items:
                        break

                    all_items.extend(items)
                    offset += len(items)

                    # Check total count if available
                    total = get_nested_value(data, self.gold_config.total_count_path) if self.gold_config.total_count_path else None
                    if total and offset >= total:
                        break
                    if len(items) < self.gold_config.page_size or offset // self.gold_config.page_size >= max_pages:
                        break

            elif self.gold_config.pagination_type == PaginationType.PAGE:
                # Page-based pagination (Euskadi style)
                page = 1
                while True:
                    separator = "&" if "?" in self.source_url else "?"
                    url = f"{self.source_url}{separator}{self.gold_config.page_param}={page}"
                    data = await self._fetch_json(url)
                    items = self._extract_items(data)

                    if not items:
                        break

                    all_items.extend(items)

                    # Check total pages if available
                    total_pages = get_nested_value(data, self.gold_config.total_pages_path) if self.gold_config.total_pages_path else None
                    if total_pages and page >= total_pages:
                        break
                    if page >= max_pages:
                        break
                    page += 1

            self.logger.info("fetched_events", source=self.source_id, count=len(all_items))
            return all_items

        except Exception as e:
            self.logger.error("fetch_error", source=self.source_id, error=str(e))
            raise

    async def _fetch_json(self, url: str) -> dict | list:
        """Fetch and parse JSON from URL."""
        response = await self.fetch_url(url)
        content = response.text
        # Clean invalid control characters
        content = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", content)
        return json.loads(content)

    def _extract_items(self, data: dict | list) -> list[dict]:
        """Extract items array from response based on config."""
        if not self.gold_config.items_path:
            # Root is the array
            return data if isinstance(data, list) else []

        # Handle Zaragoza special structure (featuredEvents + todayEvents)
        if self.gold_config.items_path == "__zaragoza_special__" and isinstance(data, dict):
            return self._extract_zaragoza_events(data)

        items = get_nested_value(data, self.gold_config.items_path) if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []

        # Handle Valencia IVC flat array format
        # Each event's fields are spread across multiple objects in the array
        if self.source_id == "valencia_ivc" and items:
            items = self._group_valencia_ivc_events(items)

        return items

    def _extract_zaragoza_events(self, data: dict) -> list[dict]:
        """Extract and deduplicate events from Zaragoza API response.

        Zaragoza API returns:
        - featuredEvents: highlighted events
        - todayEvents: events happening today (may overlap with featured)
        - featuredPrograms: program/festival info (not individual events)

        Returns deduplicated list of events.
        """
        all_ids: set[int] = set()
        events: list[dict] = []

        # Get featured events first (usually more complete data)
        featured = data.get("featuredEvents", [])
        if isinstance(featured, list):
            for event in featured:
                eid = event.get("id")
                if eid and eid not in all_ids:
                    all_ids.add(eid)
                    events.append(event)

        # Add today events if not already in featured
        today = data.get("todayEvents", [])
        if isinstance(today, list):
            for event in today:
                eid = event.get("id")
                if eid and eid not in all_ids:
                    all_ids.add(eid)
                    events.append(event)

        self.logger.info(
            "zaragoza_events_extracted",
            featured=len(featured) if featured else 0,
            today=len(today) if today else 0,
            unique=len(events),
        )
        return events

    def _group_valencia_ivc_events(self, flat_items: list[dict]) -> list[dict]:
        """Group Valencia IVC flat array format into proper event objects.

        Valencia IVC returns data where each field is a separate object:
        [{"titulo_evento": "..."}, {"tipo_evento": "..."}, ...]

        This groups them into proper event dicts:
        [{"titulo_evento": "...", "tipo_evento": "...", ...}]
        """
        fields_per_event = VALENCIA_IVC_FIELDS_PER_EVENT
        events = []

        for i in range(0, len(flat_items), fields_per_event):
            chunk = flat_items[i : i + fields_per_event]
            event = {}
            for item in chunk:
                if isinstance(item, dict):
                    event.update(item)
            if event.get("titulo_evento"):  # Only add if has title
                events.append(event)

        self.logger.info("valencia_events_grouped", flat_count=len(flat_items), grouped_count=len(events))
        return events

    def parse_event(self, raw_data: dict[str, Any]) -> EventCreate | None:
        """Parse a single event from API format to EventCreate."""
        try:
            # Andalucía: preprocesar datos de la nueva API (contentapi)
            if self.source_id == "andalucia_agenda":
                raw_data = self._preprocess_andalucia(raw_data)
                if not raw_data:
                    return None

            # Zaragoza: preprocesar datos (subEvent nested, UTM coords)
            if self.source_id == "zaragoza_cultura":
                raw_data = self._preprocess_zaragoza(raw_data)

            mappings = self.gold_config.field_mappings or {}

            # Get mapped values
            def get_mapped(key: str) -> Any:
                """Get value using field mapping."""
                source_field = None
                for src, dst in mappings.items():
                    if dst == key:
                        source_field = src
                        break
                if source_field:
                    return get_nested_value(raw_data, source_field)
                return None

            # Required fields
            title = clean_html(get_mapped("title") or "")
            if not title:
                return None

            # Parse dates
            start_date = self._parse_date(get_mapped("start_date"))
            if not start_date:
                return None

            end_date = self._parse_date(get_mapped("end_date"))

            # Parse time
            start_time = self._parse_time(get_mapped("start_time"))
            end_time = self._parse_time(get_mapped("end_time"))
            time_info = get_mapped("time_info")

            # Zaragoza: use preprocessed start_time from openingHours
            if raw_data.get("__preprocessed") and start_time is None:
                start_time = self._parse_time(raw_data.get("__start_time"))

            # If no direct start_time, try extracting from time_info text
            if start_time is None and time_info:
                parsed_st, parsed_et = self._parse_time_from_info(str(time_info))
                if parsed_st:
                    start_time = parsed_st
                if end_time is None and parsed_et:
                    end_time = parsed_et

            # Location
            venue_name = clean_html(get_mapped("venue_name"))
            address = clean_html(get_mapped("address"))
            postal_code = get_mapped("postal_code")
            latitude = self._parse_coordinate(get_mapped("latitude") or get_mapped("latitude_alt"))
            longitude = self._parse_coordinate(get_mapped("longitude") or get_mapped("longitude_alt"))

            # Zaragoza: use preprocessed values FIRST (before _extract_city which would return venue)
            if raw_data.get("__preprocessed"):
                venue_name = venue_name or raw_data.get("__venue_name")
                address = address or raw_data.get("__address")
                postal_code = postal_code or raw_data.get("__postal_code")
                city = raw_data.get("__city") or "Zaragoza"  # Always use preprocessed or default
                latitude = latitude or raw_data.get("__latitude")
                longitude = longitude or raw_data.get("__longitude")
                province = get_mapped("province") or self._extract_province(raw_data)
            else:
                city = get_mapped("city") or self._extract_city(raw_data)
                province = get_mapped("province") or self._extract_province(raw_data)

            # District/municipio - extract from Madrid's district URI
            district = None
            district_uri = get_mapped("district_uri")
            if district_uri and "/Distrito/" in district_uri:
                # URI format: .../Distrito/Moncloa-Aravaca
                district = district_uri.split("/Distrito/")[-1].replace("-", " ")

            # Price - always provide descriptive text for UI
            price_info_raw = get_mapped("price_info")

            # Extract registration URL from price_info HTML (e.g., Zaragoza <a href="...">)
            registration_url_from_price = None
            if price_info_raw and "<a " in str(price_info_raw).lower():
                registration_url_from_price = self._extract_url_from_html(price_info_raw)

            # Clean HTML from price_info before processing
            price_info_clean = clean_html(price_info_raw) if price_info_raw else None

            is_free = self._determine_is_free(raw_data, price_info_raw)

            # Generate user-friendly price_info text (using cleaned version)
            if is_free is True:
                # Free event - use clean text if descriptive, else default
                price_info = price_info_clean if price_info_clean else "Entrada gratuita"
            elif is_free is False:
                # Paid event - use clean text if available
                price_info = price_info_clean if price_info_clean else "Consultar precio en web del organizador"
            else:
                # Unknown - provide default message
                price_info = price_info_clean if price_info_clean else "Consultar en web del organizador"

            # Category
            category_name = get_mapped("category_name") or self._extract_category(raw_data)
            # Zaragoza: use preprocessed category
            if raw_data.get("__preprocessed") and not category_name:
                category_name = raw_data.get("__category_name")

            # Image
            image_url = self._extract_image_url(raw_data)
            # Zaragoza: use preprocessed image URL
            if raw_data.get("__preprocessed") and not image_url:
                image_url = raw_data.get("__image_url")

            # External ID and URL
            raw_external_id = get_mapped('external_id') or ''

            # For CyL, include date in external_id to differentiate recurring events
            # (same id_evento appears multiple times with different dates)
            if self.source_id == "castilla_leon_agenda" and start_date:
                external_id = f"{self.source_id}_{raw_external_id}_{start_date.isoformat()}"
            else:
                external_id = f"{self.source_id}_{raw_external_id}"

            external_url = get_mapped("external_url")

            # Summary (short description/subtitle)
            summary = clean_html(get_mapped("summary"))

            # Organizer - try multiple sources
            organizer_name = get_mapped("organizer_name")
            if not organizer_name:
                # Fallback to sourceNameEs (Euskadi) or organizer_names (Andalucía)
                organizer_name = get_mapped("organizer_source")
            if not organizer_name:
                # Andalucía: organizer_names is a list
                org_names = raw_data.get("organizer_names", [])
                if org_names and isinstance(org_names, list) and org_names[0]:
                    organizer_name = org_names[0]

            organizer_url = get_mapped("organizer_url")
            organizer = self._parse_organizer(organizer_name, organizer_url) if organizer_name else None

            # Accessibility
            accessibility_info = self._extract_accessibility(raw_data)

            # Contact info (Catalunya has email, tel_fon)
            contact_email = get_mapped("contact_email")
            contact_phone = get_mapped("contact_phone")
            # Zaragoza: use preprocessed contact info
            if raw_data.get("__preprocessed"):
                contact_email = contact_email or raw_data.get("__contact_email")
                contact_phone = contact_phone or raw_data.get("__contact_phone")
            contact = None
            if contact_email or contact_phone:
                contact = EventContact(
                    email=contact_email,
                    phone=contact_phone,
                )

            # Description
            description = clean_html(get_mapped("description"))

            # Extract URLs from description text
            desc_urls = self._extract_urls_from_description(
                get_mapped("description")  # Use raw HTML to find URLs before clean_html strips them
            )

            # Fill external_url from description if not set by API field
            if not external_url and desc_urls["event_url"]:
                external_url = desc_urls["event_url"]

            # Registration URL: from price_info HTML, description, or from ticket-type external_url
            registration_url = registration_url_from_price or desc_urls["registration_url"]
            if not registration_url and external_url and self.source_id in ("euskadi_kulturklik", "catalunya_agenda", "zaragoza_cultura"):
                # These sources map ticket/purchase URLs as external_url
                # Only copy if URL looks like a ticket/booking site
                ticket_patterns = [
                    'entrad', 'ticket', 'secutix', 'sacatuentrada', 'koobin',
                    'patronbase', 'dice.fm', 'sarrerak', 'compra', 'reserva',
                    'booking', 'shop.', 'buy.', 'venta',
                ]
                url_lower = external_url.lower()
                if any(p in url_lower for p in ticket_patterns):
                    registration_url = external_url

            # Parse modality (Catalunya: "Presencial", "Online", "Híbrid")
            location_type = LocationType.PHYSICAL
            modality_text = get_mapped("modality_text")
            if modality_text:
                modality_lower = str(modality_text).lower()
                if "online" in modality_lower:
                    location_type = LocationType.ONLINE
                elif "híbrid" in modality_lower or "hibrid" in modality_lower:
                    location_type = LocationType.HYBRID

            # Parse is_featured (Catalunya: "Si" / "No")
            is_featured = False
            is_featured_text = get_mapped("is_featured_text")
            if is_featured_text:
                is_featured = str(is_featured_text).lower() in ("si", "sí", "yes", "true", "1")

            return EventCreate(
                title=title,
                description=description,
                summary=summary,
                start_date=start_date,
                end_date=end_date,
                start_time=start_time,
                end_time=end_time,
                location_type=location_type,
                venue_name=venue_name,
                address=address,
                city=city,
                district=district,
                province=province or self.gold_config.default_province,
                comunidad_autonoma=self.ccaa,
                postal_code=postal_code,
                latitude=latitude,
                longitude=longitude,
                category_name=category_name,
                category_slugs=[],  # Will be filled by LLM enricher
                organizer=organizer,
                source_id=self.source_id,
                external_url=external_url,
                registration_url=registration_url,
                external_id=external_id,
                source_image_url=image_url,
                is_free=is_free,
                price_info=price_info,
                accessibility=accessibility_info,
                contact=contact,
                is_featured=is_featured,
            )

        except Exception as e:
            self.logger.warning("parse_error", source=self.source_id, error=str(e), title=raw_data.get("title", "")[:50])
            return None

    def _parse_date(self, value: Any) -> date | None:
        """Parse date from various formats."""
        if not value:
            return None

        if isinstance(value, date):
            return value

        # Handle Andalucía date_registration array: [{"start_date_registration": "2020-03-01", ...}]
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                # Try start_date_registration or start_date
                date_str = first.get("start_date_registration") or first.get("start_date")
                if date_str:
                    return self._parse_date(date_str)
            return None

        if isinstance(value, str):
            # Try multiple formats
            formats = [
                self.gold_config.date_format,
                self.gold_config.datetime_format,
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(value[:26], fmt)
                    return dt.date()
                except (ValueError, TypeError):
                    continue

            # Try just date part
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        return None

    def _parse_time(self, value: Any) -> time | None:
        """Parse time from various formats."""
        if not value:
            return None

        if isinstance(value, time):
            return value

        if isinstance(value, str):
            # Extract HH:MM or HH.MM pattern
            match = re.search(r"(\d{1,2})[:\.](\d{2})", value)
            if match:
                try:
                    h, m = int(match.group(1)), int(match.group(2))
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        return time(h, m)
                except (ValueError, TypeError):
                    pass

        return None

    def _parse_time_from_info(self, time_info: str | None) -> tuple[time | None, time | None]:
        """Extract start_time and end_time from free-text schedule info.

        Handles formats from multiple sources:
        - Euskadi: '19:30', 'Consultar'
        - Catalunya: '11 h', '18.30 h', '20 h', '11 h Durada aproximada: 1 hora'
        - Andalucía: 'De lunes a viernes, de 9:00 a 14:00 horas'

        Returns:
            Tuple of (start_time, end_time). Either or both can be None.
        """
        if not time_info or not isinstance(time_info, str):
            return None, None

        text = time_info.strip()
        if not text:
            return None, None

        # Pattern 1: Time range "HH:MM a HH:MM" or "HH:MM - HH:MM"
        range_match = re.search(
            r"(\d{1,2})[:\.](\d{2})\s*(?:a\s|[-–]\s*)\s*(\d{1,2})[:\.](\d{2})",
            text,
        )
        if range_match:
            try:
                h1, m1 = int(range_match.group(1)), int(range_match.group(2))
                h2, m2 = int(range_match.group(3)), int(range_match.group(4))
                st = time(h1, m1) if 0 <= h1 <= 23 and 0 <= m1 <= 59 else None
                et = time(h2, m2) if 0 <= h2 <= 23 and 0 <= m2 <= 59 else None
                if st:
                    return st, et
            except (ValueError, TypeError):
                pass

        # Pattern 2: Single time "HH:MM" or "HH.MM"
        time_match = re.search(r"(\d{1,2})[:\.](\d{2})", text)
        if time_match:
            try:
                h, m = int(time_match.group(1)), int(time_match.group(2))
                if 0 <= h <= 23 and 0 <= m <= 59:
                    return time(h, m), None
            except (ValueError, TypeError):
                pass

        # Pattern 3: Catalan "HH h" (just hour with 'h' suffix)
        hour_match = re.search(r"(\d{1,2})\s*h\b", text)
        if hour_match:
            try:
                h = int(hour_match.group(1))
                if 0 <= h <= 23:
                    return time(h, 0), None
            except (ValueError, TypeError):
                pass

        return None, None

    def _parse_coordinate(self, value: Any) -> float | None:
        """Parse coordinate to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _determine_is_free(self, raw_data: dict, price_info: str | None) -> bool | None:
        """Determine if event is free.

        Strategy:
        1. Check explicit free/paid fields in the API data
        2. Check for public institution organizers → assume free
        3. Check price_info text for free/paid keywords
        4. Default: if no paid indicators found → assume free
        """
        mappings = self.gold_config.field_mappings or {}

        # Check specific free field (e.g., "free": 1 for Madrid)
        for src, dst in mappings.items():
            if dst == "is_free_int":
                val = get_nested_value(raw_data, src)
                if val is not None:
                    return val == 1
            if dst == "is_free_text":
                val = get_nested_value(raw_data, src)
                if val is not None:
                    return str(val).lower() in ("si", "sí", "yes", "true", "1")

        # Check for paid indicators first (most reliable)
        if price_info:
            price_lower = str(price_info).lower()

            # Paid indicators - contains price with € or number
            # Patterns like "11 €", "10 / 12 €", "22€", "desde 15 euros"
            if "€" in price_info or re.search(r"\d+\s*(€|euros?)", price_lower):
                return False

            # Paid indicators - ticket sales text
            paid_keywords = [
                "venta de entradas", "compra de entradas", "comprar entradas",
                "tickets", "taquilla", "adquirir entradas", "reserva de entradas",
            ]
            if any(kw in price_lower for kw in paid_keywords):
                return False

            # Paid indicator - links to ticket sales (HTML with href)
            if "<a " in price_info.lower() and any(
                kw in price_lower for kw in ["entrada", "ticket", "compra", "reserva"]
            ):
                return False

        # Castilla y León: eventos de biblioteca son gratuitos
        if self.source_id == "castilla_leon_agenda":
            evento_biblioteca = get_nested_value(raw_data, "evento_biblioteca")
            if evento_biblioteca and str(evento_biblioteca).upper() == "SI":
                return True

        # Check for public institution organizers → assume free
        # This applies to all sources
        if self._is_public_institution_event(raw_data):
            return True

        # Check price_info text for free indicators
        if price_info:
            price_lower = str(price_info).lower()

            # Free indicators - be conservative to avoid false positives
            # Note: "entrada libre" removed - it often means "open entry" not "free"
            # Note: "libre" alone removed - too ambiguous
            free_keywords = ["gratuito", "gratuita", "gratis", "de balde", "doan", "free"]
            if any(kw in price_lower for kw in free_keywords):
                return True

            # Check if free_value matches
            if self.gold_config.free_value and self.gold_config.free_value.lower() in price_lower:
                return True

        # Default: return None (unknown) instead of assuming free
        # The LLM enricher can determine this more accurately
        return None

    def _is_public_institution_event(self, raw_data: dict) -> bool:
        """Check if event is organized by a public institution.

        Public institutions typically offer free events:
        - Government bodies (Consejería, Junta, Gobierno, Ministerio)
        - Local government (Ayuntamiento, Diputación, Cabildo)
        - Public libraries, museums, cultural centers
        - Universities
        """
        # Keywords indicating public institutions
        public_keywords = [
            # Government
            "consejería", "consejeria", "junta de", "gobierno", "ministerio",
            "delegación", "delegacion", "generalitat", "xunta",
            # Local government
            "ayuntamiento", "diputación", "diputacion", "cabildo", "concello",
            # Cultural institutions
            "biblioteca", "museo", "archivo", "centro cultural", "casa de cultura",
            "filmoteca", "auditorio público", "teatro municipal",
            # Education
            "universidad", "facultad", "escuela oficial",
            # Environment/Nature
            "parque natural", "reserva natural", "espacio natural", "centro de visitantes",
            # Other public
            "instituto", "fundación pública", "organismo público",
        ]

        # Fields to check for public institution indicators
        fields_to_check = [
            # Organizer fields
            get_nested_value(raw_data, "organizer_name"),
            get_nested_value(raw_data, "organizers"),
            get_nested_value(raw_data, "organizer_names"),  # From Andalucía preprocessor
            get_nested_value(raw_data, "field_organismo_"),
            # Venue fields
            get_nested_value(raw_data, "venue_name"),
            get_nested_value(raw_data, "lugar_celebracion"),
            get_nested_value(raw_data, "address"),
            # Description might mention organizer
            get_nested_value(raw_data, "description"),
        ]

        for field_value in fields_to_check:
            if not field_value:
                continue

            # Handle lists (e.g., organizer arrays)
            if isinstance(field_value, list):
                for item in field_value:
                    if isinstance(item, dict):
                        # Check nested name fields
                        for key in ["name", "nombre", "field_nombre_largo"]:
                            name = item.get(key, "")
                            if name and any(kw in name.lower() for kw in public_keywords):
                                return True
                    elif isinstance(item, str):
                        if any(kw in item.lower() for kw in public_keywords):
                            return True
            elif isinstance(field_value, str):
                if any(kw in field_value.lower() for kw in public_keywords):
                    return True

        return False

    def _extract_city(self, raw_data: dict) -> str | None:
        """Extract city from various structures."""
        # Catalunya: comarca_i_municipi contains path like "agenda:ubicacions/barcelona/barcelones/barcelona"
        # City slug uses hyphens: "sant-andreu-de-la-barca" → "Sant Andreu de la Barca"
        comarca = get_nested_value(raw_data, "comarca_i_municipi")
        if comarca:
            parts = comarca.split("/")
            if parts:
                city_slug = parts[-1]
                # Replace hyphens with spaces and title-case
                return city_slug.replace("-", " ").title()

        # Andalucía: location field
        location = get_nested_value(raw_data, "location")
        if location and isinstance(location, str):
            return location

        return None

    def _extract_province(self, raw_data: dict) -> str | None:
        """Extract province from various structures."""
        # Euskadi: province code
        prov_code = get_nested_value(raw_data, "provinceNoraCode")
        if prov_code and str(prov_code) in EUSKADI_PROVINCE_CODES:
            return EUSKADI_PROVINCE_CODES[str(prov_code)]

        # Catalunya: extract province from municipi field
        # Format: agenda:ubicacions/{provincia}/{comarca}/{municipi}
        # Example: agenda:ubicacions/barcelona/maresme/premia-de-mar -> Barcelona
        municipi = get_nested_value(raw_data, "municipi")
        if municipi and "/" in str(municipi):
            path = str(municipi).replace("agenda:ubicacions/", "")
            parts = path.split("/")
            if parts:
                province_slug = parts[0].lower()
                cat_provinces = {
                    "barcelona": "Barcelona",
                    "girona": "Girona",
                    "lleida": "Lleida",
                    "tarragona": "Tarragona",
                }
                if province_slug in cat_provinces:
                    return cat_provinces[province_slug]

        # Andalucía: province array
        province_array = get_nested_value(raw_data, "province")
        if province_array and isinstance(province_array, list) and province_array:
            first = province_array[0]
            if isinstance(first, dict):
                return first.get("province")
            return str(first)

        return None

    def _extract_category(self, raw_data: dict) -> str | None:
        """Extract category from various structures."""
        # Catalunya: tags_categor_es
        tags = get_nested_value(raw_data, "tags_categor_es")
        if tags:
            # Format: "agenda:categories/concerts,agenda:categories/infantil"
            parts = str(tags).split(",")
            if parts:
                cat = parts[0].split("/")[-1] if "/" in parts[0] else parts[0]
                return cat.title()

        # Andalucía: themes array
        themes = get_nested_value(raw_data, "themes")
        if themes and isinstance(themes, list) and themes:
            first = themes[0]
            if isinstance(first, dict):
                return first.get("themes")
            return str(first)

        # Madrid: @type URI
        type_uri = get_nested_value(raw_data, "@type")
        if type_uri:
            return type_uri.split("/")[-1] if "/" in type_uri else type_uri

        return None

    def _extract_image_url(self, raw_data: dict) -> str | None:
        """Extract image URL from various structures."""
        prefix = self.gold_config.image_url_prefix

        # Direct image_url field (e.g., from Andalucía preprocessor)
        direct_url = get_nested_value(raw_data, "image_url")
        if direct_url:
            if direct_url.startswith("/"):
                return f"{prefix}{direct_url}"
            return direct_url

        # Catalunya: imatges field (comma-separated paths)
        imatges = get_nested_value(raw_data, "imatges")
        if imatges:
            first = str(imatges).split(",")[0].strip()
            if first:
                return f"{prefix}{first}" if not first.startswith("http") else first

        # Euskadi: images array
        images = get_nested_value(raw_data, "images")
        if images and isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                url = first.get("imageUrl")
                if url:
                    return url
            elif isinstance(first, str):
                return f"{prefix}{first}" if not first.startswith("http") else first

        # Castilla y León: preferir imagen_evento_ampliada (mejor calidad), fallback a imagen_evento
        img_ampliada = get_nested_value(raw_data, "imagen_evento_ampliada")
        if img_ampliada:
            # Decode HTML entities in URL
            return img_ampliada.replace("&amp;", "&")

        img = get_nested_value(raw_data, "imagen_evento")
        if img:
            # Decode HTML entities in URL
            return img.replace("&amp;", "&")

        # Andalucía: image array with thumbnails
        image_array = get_nested_value(raw_data, "image")
        if image_array and isinstance(image_array, list) and image_array:
            first = image_array[0]
            if isinstance(first, dict):
                thumbnails = first.get("thumbnail", [])
                if thumbnails and isinstance(thumbnails, list):
                    thumb = thumbnails[0]
                    if isinstance(thumb, dict):
                        url = thumb.get("image_url")
                        if url:
                            return f"{prefix}{url}" if not url.startswith("http") else url

        return None

    def _preprocess_andalucia(self, raw_data: dict[str, Any]) -> dict[str, Any] | None:
        """Preprocess Andalucía contentapi data to flat structure.

        The new API returns data nested in _source.data with complex field names.
        This method flattens it for the generic parser.
        """
        try:
            source = raw_data.get("_source", {})
            if not isinstance(source, dict):
                return None

            data = source.get("data", {})
            if not isinstance(data, dict):
                return None

            # Extract title
            title = data.get("title", "")
            if not title:
                return None

            # Extract dates from field_agenda_fechas array
            start_date = None
            end_date = None
            fechas = data.get("field_agenda_fechas", [])
            if isinstance(fechas, list) and fechas:
                for f in fechas:
                    if isinstance(f, dict):
                        if not start_date:
                            start_date = f.get("field_inicio_plazo_tip")
                        end_date = f.get("field_fin_plazo_tip") or end_date

            # Extract province from field_provincia array
            province = None
            provs = data.get("field_provincia", [])
            if isinstance(provs, list) and provs:
                for p in provs:
                    if isinstance(p, dict):
                        province = p.get("name")
                        if province:
                            break

            # Extract image URL from field_imagen array
            image_url = None
            imgs = data.get("field_imagen", [])
            if isinstance(imgs, list) and imgs:
                for img in imgs:
                    if isinstance(img, dict):
                        thumbs = img.get("thumbnail", [])
                        if isinstance(thumbs, list) and thumbs:
                            for t in thumbs:
                                if isinstance(t, dict):
                                    uri = t.get("uri")
                                    if uri:
                                        image_url = uri
                                        break
                        if image_url:
                            break

            # Extract category from field_tema array
            category = None
            temas = data.get("field_tema", [])
            if isinstance(temas, list) and temas:
                for t in temas:
                    if isinstance(t, dict):
                        category = t.get("name")
                        if category:
                            break

            # Build external URL from path alias
            external_url = None
            path = data.get("path", {})
            if isinstance(path, dict):
                alias = path.get("alias")
                if alias:
                    external_url = f"https://www.juntadeandalucia.es{alias}"

            # Extract organizer info from field_organismo_ array
            organizer_names = []
            organismos = data.get("field_organismo_", [])
            if isinstance(organismos, list):
                for org in organismos:
                    if isinstance(org, dict):
                        org_name = org.get("field_nombre_largo") or org.get("name")
                        if org_name:
                            organizer_names.append(org_name)

            # Get city for external_id differentiation
            city = data.get("field_agenda_localidad")

            # Build unique external_id: nid + city + date to differentiate same event in different cities
            nid = data.get("nid", "")
            external_id_parts = [str(nid)]
            if city:
                external_id_parts.append(city)
            if start_date:
                external_id_parts.append(start_date)
            unique_external_id = "_".join(external_id_parts)

            # Return flattened structure
            return {
                "title": title,
                "description": data.get("field_descripcion", ""),
                "start_date": start_date,
                "end_date": end_date,
                "time_info": data.get("field_agenda_horario"),
                "price_info": data.get("field_agenda_precio"),
                "venue_name": None,  # Not in this API
                "address": data.get("field_agenda_direccion"),
                "city": city,
                "province": province,
                "category_name": category,
                "image_url": image_url,
                "external_id": unique_external_id,
                "external_url": external_url,
                # Preserve organizer info for public institution detection
                "organizer_names": organizer_names,
            }

        except Exception as e:
            self.logger.warning(
                "andalucia_preprocess_error",
                error=str(e),
            )
            return None

    def _preprocess_zaragoza(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Preprocess Zaragoza event data to flat structure.

        Handles:
        - subEvent[0].location nested structure
        - UTM coordinates (EPSG:25830) to WGS84 conversion
        - Image URL normalization (// prefix)
        - Category extraction from nested array
        - Time extraction from subEvent openingHours
        """
        # Extract location from first subEvent
        sub_events = raw_data.get("subEvent", [])
        location_data: dict[str, Any] = {}
        opening_hours: list[dict] = []

        if sub_events and isinstance(sub_events, list):
            first_sub = sub_events[0]
            if isinstance(first_sub, dict):
                loc = first_sub.get("location", {})
                if isinstance(loc, dict):
                    location_data = loc
                opening_hours = first_sub.get("openingHours", [])

        # Convert UTM coordinates to WGS84
        latitude = None
        longitude = None
        geometry = raw_data.get("geometry", {})
        if geometry and isinstance(geometry, dict):
            coords = geometry.get("coordinates", [])
            if coords and len(coords) >= 2:
                # Zaragoza uses EPSG:25830 (UTM zone 30N)
                utm_x, utm_y = coords[0], coords[1]
                latitude, longitude = self._utm_to_wgs84(utm_x, utm_y)

        # Fallback to location geometry if main geometry missing
        if latitude is None and location_data:
            loc_geom = location_data.get("geometry", {})
            if loc_geom and isinstance(loc_geom, dict):
                coords = loc_geom.get("coordinates", [])
                if coords and len(coords) >= 2:
                    utm_x, utm_y = coords[0], coords[1]
                    latitude, longitude = self._utm_to_wgs84(utm_x, utm_y)

        # Extract category
        category_name = raw_data.get("type")  # e.g., "Exhibición, proyección, competición"
        if not category_name:
            categories = raw_data.get("category", [])
            if categories and isinstance(categories, list):
                first_cat = categories[0]
                if isinstance(first_cat, dict):
                    category_name = first_cat.get("title")

        # Normalize image URL (// prefix -> https://)
        image_url = raw_data.get("image")
        if image_url and image_url.startswith("//"):
            image_url = f"https:{image_url}"

        # Extract time from opening hours (first occurrence)
        start_time = None
        for oh in opening_hours:
            if isinstance(oh, dict):
                st = oh.get("startTime")
                if st:
                    start_time = st
                    break

        # Update raw_data with preprocessed values
        raw_data["__preprocessed"] = True
        raw_data["__latitude"] = latitude
        raw_data["__longitude"] = longitude
        raw_data["__category_name"] = category_name
        raw_data["__image_url"] = image_url
        raw_data["__start_time"] = start_time
        raw_data["__address"] = location_data.get("streetAddress")
        raw_data["__city"] = location_data.get("addressLocality", "Zaragoza")
        raw_data["__postal_code"] = location_data.get("postalCode")
        raw_data["__contact_phone"] = location_data.get("telephone")
        raw_data["__contact_email"] = location_data.get("email")
        raw_data["__venue_name"] = raw_data.get("location") or location_data.get("title")

        return raw_data

    def _utm_to_wgs84(self, easting: float, northing: float, zone: int = 30) -> tuple[float | None, float | None]:
        """Convert UTM coordinates (EPSG:25830) to WGS84 (lat, lon).

        Uses simplified conversion formula for zone 30N (Spain).
        For production, consider using pyproj for accuracy.

        Args:
            easting: UTM X coordinate
            northing: UTM Y coordinate
            zone: UTM zone (default 30 for Spain)

        Returns:
            Tuple of (latitude, longitude) in WGS84 or (None, None) if invalid
        """
        import math

        try:
            # UTM parameters
            k0 = 0.9996
            a = 6378137.0  # WGS84 semi-major axis
            e = 0.081819191  # WGS84 eccentricity
            e1sq = 0.006739497

            # Remove false easting and northing
            x = easting - 500000.0
            y = northing

            # Calculate footprint latitude
            m = y / k0
            mu = m / (a * (1 - e**2 / 4 - 3 * e**4 / 64 - 5 * e**6 / 256))

            e1 = (1 - math.sqrt(1 - e**2)) / (1 + math.sqrt(1 - e**2))
            j1 = 3 * e1 / 2 - 27 * e1**3 / 32
            j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
            j3 = 151 * e1**3 / 96
            j4 = 1097 * e1**4 / 512

            fp = mu + j1 * math.sin(2 * mu) + j2 * math.sin(4 * mu) + j3 * math.sin(6 * mu) + j4 * math.sin(8 * mu)

            # Calculate latitude and longitude
            c1 = e1sq * math.cos(fp) ** 2
            t1 = math.tan(fp) ** 2
            r1 = a * (1 - e**2) / (1 - e**2 * math.sin(fp) ** 2) ** 1.5
            n1 = a / math.sqrt(1 - e**2 * math.sin(fp) ** 2)
            d = x / (n1 * k0)

            q1 = n1 * math.tan(fp) / r1
            q2 = d**2 / 2
            q3 = (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * e1sq) * d**4 / 24
            q4 = (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * e1sq - 3 * c1**2) * d**6 / 720

            lat = fp - q1 * (q2 - q3 + q4)

            q5 = d
            q6 = (1 + 2 * t1 + c1) * d**3 / 6
            q7 = (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * e1sq + 24 * t1**2) * d**5 / 120

            # Central meridian for zone 30 is -3 degrees
            lon0 = math.radians((zone - 1) * 6 - 180 + 3)
            lon = lon0 + (q5 - q6 + q7) / math.cos(fp)

            lat_deg = math.degrees(lat)
            lon_deg = math.degrees(lon)

            # Sanity check for Spain coordinates
            if 35 <= lat_deg <= 44 and -10 <= lon_deg <= 5:
                return round(lat_deg, 6), round(lon_deg, 6)
            else:
                return None, None

        except (ValueError, ZeroDivisionError, OverflowError):
            return None, None

    def _extract_urls_from_description(self, description: str | None) -> dict:
        """Extract event and registration URLs from description text.

        Finds URLs embedded in descriptions (e.g., "Web del evento: https://..."),
        classifies them as event website or registration/ticket links.

        Returns:
            dict with 'event_url' and 'registration_url' keys (str or None)
        """
        result = {"event_url": None, "registration_url": None}
        if not description:
            return result

        # Find all URLs in text (including HTML href attributes)
        urls = re.findall(r'https?://[^\s<>"\')\]]+', description)

        # Filter out image URLs and data portal asset URLs
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp'}
        non_image_urls = []
        for url in urls:
            url = url.rstrip('.,;:)')
            path = url.split('?')[0].lower()
            if not any(path.endswith(ext) for ext in image_extensions):
                non_image_urls.append(url)

        # Deduplicate while preserving order
        seen = set()
        unique_urls = []
        for url in non_image_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        # Classify URLs
        registration_patterns = [
            'inscri', 'registro', 'rpla', 'entrad', 'ticket',
            'compra', 'reserva', 'booking', 'secutix', 'sacatuentrada',
            'patronbase', 'dice.fm',
        ]

        for url in unique_urls:
            url_lower = url.lower()
            if any(p in url_lower for p in registration_patterns):
                if not result["registration_url"]:
                    result["registration_url"] = url
            else:
                if not result["event_url"]:
                    result["event_url"] = url

        return result

    def _extract_url_from_html(self, html_text: str | None) -> str | None:
        """Extract first URL from HTML anchor tag.

        Parses HTML like: <a href="https://...">text</a>
        Returns the href URL or None if not found.
        """
        if not html_text:
            return None

        # Match href attribute in anchor tags
        match = re.search(r'<a\s+[^>]*href=["\']([^"\']+)["\']', str(html_text), re.IGNORECASE)
        if match:
            url = match.group(1)
            # Basic validation
            if url.startswith(("http://", "https://")):
                return url
        return None

    def _parse_organizer(self, name: str | None, url: str | None = None) -> EventOrganizer | None:
        """Parse organizer from name and optional URL.

        Args:
            name: Organizer name (may be cleaned up if looks like a domain)
            url: Organizer website URL

        Returns:
            EventOrganizer with name, type, url, and logo_url (favicon from domain)
        """
        if not name:
            return None

        name = clean_html(name) or ""
        if not name:
            return None

        # Detect if name looks like a domain (e.g., "zumaia.eus", "www.example.com")
        domain_pattern = r'^(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z]{2,}$'
        if re.match(domain_pattern, name.strip()):
            # Name is a domain - try to extract proper name from URL or use domain as fallback
            # Extract the main domain part as a proper name (e.g., "zumaia.eus" -> "Zumaia")
            domain_parts = name.replace("www.", "").split(".")
            if domain_parts:
                # Use first part, capitalize it (e.g., "zumaia" -> "Zumaia")
                extracted_name = domain_parts[0].capitalize()
                # If it's a common TLD, use the full domain minus www
                if len(extracted_name) >= 3:
                    name = extracted_name
                else:
                    # Too short, use full domain
                    name = name.replace("www.", "")

            # If url wasn't provided, construct it from the domain
            if not url and name:
                url = f"https://{name.lower() if '.' in name else name.lower() + '.eus'}"

        name_lower = name.lower()
        org_type = OrganizerType.OTRO

        # Instituciones públicas (orden importa - más específico primero)
        institucion_keywords = [
            "ayuntamiento", "diputación", "diputacion", "gobierno", "generalitat",
            "xunta", "junta", "comunidad de madrid", "ministerio", "consejería",
            "museo", "biblioteca", "centro cultural", "centro sociocultural",
            "centro cívico", "casa de cultura", "auditorio", "teatro municipal",
            "palacio de", "sala de exposiciones", "espacio cultural", "cultural de la villa",
            "conde duque", "matadero", "medialab", "cineteca", "filmoteca",
        ]
        if any(kw in name_lower for kw in institucion_keywords):
            org_type = OrganizerType.INSTITUCION
        elif any(kw in name_lower for kw in ["asociación", "asociacion", "fundación", "fundacion", "ong", "colectivo"]):
            org_type = OrganizerType.ASOCIACION
        elif any(kw in name_lower for kw in ["s.l.", "s.a.", " sl", " sa", "producciones", "entertainment", "events"]):
            org_type = OrganizerType.EMPRESA

        # Generate logo_url from domain favicon if we have a URL
        logo_url = None
        if url:
            logo_url = self._get_favicon_url(url)

        return EventOrganizer(name=name, type=org_type, url=url, logo_url=logo_url)

    def _get_favicon_url(self, url: str) -> str | None:
        """Get favicon URL for a domain using Google's favicon service.

        Args:
            url: Full URL or domain

        Returns:
            URL to favicon image (via Google Favicon API)
        """
        if not url:
            return None

        try:
            # Extract domain from URL
            if url.startswith(("http://", "https://")):
                # Parse domain from full URL
                from urllib.parse import urlparse
                parsed = urlparse(url)
                domain = parsed.netloc
            else:
                # Assume it's already a domain
                domain = url.replace("www.", "")

            if not domain:
                return None

            # Use Google's favicon service - reliable and free
            # Returns 16x16 favicon, use size=64 for larger
            return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"
        except Exception:
            return None

    def _extract_accessibility(self, raw_data: dict) -> EventAccessibility | None:
        """Extract and parse accessibility information from various sources.

        - Madrid: accessibility codes (1,6,7) -> structured EventAccessibility
        - Other sources: may have different formats

        Returns:
            EventAccessibility object or None if no accessibility info
        """
        mappings = self.gold_config.field_mappings or {}

        # Madrid: accessibility codes
        for src, dst in mappings.items():
            if dst == "accessibility_codes":
                codes_str = get_nested_value(raw_data, src)
                if codes_str:
                    # Parse codes like "1,6" or "1"
                    codes = [c.strip() for c in str(codes_str).split(",")]

                    # Build structured accessibility data
                    wheelchair = False
                    sign_lang = False
                    hearing = False
                    braille = False
                    other_list: list[str] = []

                    for code in codes:
                        if code in MADRID_ACCESSIBILITY_CODES:
                            info = MADRID_ACCESSIBILITY_CODES[code]
                            field = info["field"]
                            desc = info["desc"]

                            if field == "wheelchair_accessible":
                                wheelchair = True
                            elif field == "sign_language":
                                sign_lang = True
                            elif field == "hearing_loop":
                                hearing = True
                            elif field == "braille_materials":
                                braille = True
                            elif field == "other_facilities":
                                other_list.append(desc)

                    # Only return if we have any accessibility info
                    if wheelchair or sign_lang or hearing or braille or other_list:
                        return EventAccessibility(
                            wheelchair_accessible=wheelchair,
                            sign_language=sign_lang,
                            hearing_loop=hearing,
                            braille_materials=braille,
                            other_facilities=". ".join(other_list) if other_list else None,
                        )

        return None

# ============================================================
# REGISTER ADAPTERS FOR EACH SOURCE
# ============================================================


def create_adapter_class(source_slug: str) -> type:
    """Create a registered adapter class for a source."""

    @register_adapter(source_slug)
    class DynamicGoldAdapter(GoldAPIAdapter):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(source_slug, *args, **kwargs)

    DynamicGoldAdapter.__name__ = f"{source_slug.title().replace('_', '')}Adapter"
    return DynamicGoldAdapter


# Create and register adapter classes for all Gold-level sources
for slug in GOLD_SOURCES:
    create_adapter_class(slug)
