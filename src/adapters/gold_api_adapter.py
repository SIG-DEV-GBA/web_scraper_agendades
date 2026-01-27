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
from src.core.event_model import EventCreate, EventOrganizer, LocationType, OrganizerType


class PaginationType(str, Enum):
    """Pagination strategy for each API."""

    NONE = "none"  # No pagination, single request
    OFFSET_LIMIT = "offset_limit"  # Uses offset + limit params
    PAGE = "page"  # Uses _page param (Euskadi style)
    SOCRATA = "socrata"  # Uses $offset + $limit (Socrata/SODA)


class SourceTier(str, Enum):
    """Quality tier of data source - determines which LLM model to use."""

    ORO = "oro"  # Clean JSON APIs - use gpt-oss-120b (fast, structured)
    PLATA = "plata"  # Semi-structured HTML - use llama-3.3-70b (balanced)
    BRONCE = "bronce"  # Chaotic websites - use kimi-k2 (deep reasoning)


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
        image_url_prefix="https://gencat.cat",
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
        url="https://datos.juntadeandalucia.es/api/v0/schedule/all?format=json",
        ccaa="Andalucía",
        ccaa_code="AN",
        pagination_type=PaginationType.NONE,  # Returns all in one response
        items_path="",  # Root is array
        date_format="%Y-%m-%d",
        free_value="Gratuito",
        image_url_prefix="https://www.juntadeandalucia.es",
        field_mappings={
            "id": "external_id",
            "title": "title",
            "description": "description",
            "date_registration": "start_date",  # Array with start_date_registration inside
            "schedule": "time_info",
            "cost": "price_info",
            "address": "address",
            "location": "city",
            "province": "province_array",
            "organizers": "organizer_name",
            "image": "images_array",
            "themes": "category_array",
            "coordinates": "coordinates_array",
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
}

# Number of fields per event for Valencia IVC (flat array format)
VALENCIA_IVC_FIELDS_PER_EVENT = 16

# Euskadi province codes mapping
EUSKADI_PROVINCE_CODES = {
    "1": "Araba/Álava",
    "20": "Gipuzkoa",
    "48": "Bizkaia",
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

    # Remove leading/trailing whitespace
    clean = clean.strip()

    return clean if clean else None


class GoldAPIAdapter(BaseAdapter):
    """Generic adapter for Gold-level CCAA APIs.

    This adapter can be configured for different sources by passing the
    source_slug parameter, which loads the appropriate configuration.
    """

    adapter_type = AdapterType.API

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
                    url = f"{self.source_url}?{self.gold_config.limit_param}={self.gold_config.page_size}&{self.gold_config.offset_param}={offset}"
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

        items = get_nested_value(data, self.gold_config.items_path) if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []

        # Handle Valencia IVC flat array format
        # Each event's fields are spread across multiple objects in the array
        if self.source_id == "valencia_ivc" and items:
            items = self._group_valencia_ivc_events(items)

        return items

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
            city = get_mapped("city") or self._extract_city(raw_data)
            province = get_mapped("province") or self._extract_province(raw_data)
            latitude = self._parse_coordinate(get_mapped("latitude") or get_mapped("latitude_alt"))
            longitude = self._parse_coordinate(get_mapped("longitude") or get_mapped("longitude_alt"))

            # Price
            price_info = get_mapped("price_info")
            is_free = self._determine_is_free(raw_data, price_info)

            # Category
            category_name = get_mapped("category_name") or self._extract_category(raw_data)

            # Image
            image_url = self._extract_image_url(raw_data)

            # External ID and URL
            raw_external_id = get_mapped('external_id') or ''

            # For CyL, include date in external_id to differentiate recurring events
            # (same id_evento appears multiple times with different dates)
            if self.source_id == "castilla_leon_agenda" and start_date:
                external_id = f"{self.source_id}_{raw_external_id}_{start_date.isoformat()}"
            else:
                external_id = f"{self.source_id}_{raw_external_id}"

            external_url = get_mapped("external_url")

            # Organizer
            organizer_name = get_mapped("organizer_name")
            organizer = self._parse_organizer(organizer_name) if organizer_name else None

            # Description
            description = clean_html(get_mapped("description"))

            # Extract URLs from description text
            desc_urls = self._extract_urls_from_description(
                get_mapped("description")  # Use raw HTML to find URLs before clean_html strips them
            )

            # Fill external_url from description if not set by API field
            if not external_url and desc_urls["event_url"]:
                external_url = desc_urls["event_url"]

            # Registration URL: from description, or from ticket-type external_url
            registration_url = desc_urls["registration_url"]
            if not registration_url and external_url and self.source_id in ("euskadi_kulturklik", "catalunya_agenda"):
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
        """Determine if event is free."""
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

        # Check price_info text
        if price_info and self.gold_config.free_value:
            if self.gold_config.free_value.lower() in str(price_info).lower():
                return True

        return None

    def _extract_city(self, raw_data: dict) -> str | None:
        """Extract city from various structures."""
        # Catalunya: comarca_i_municipi contains path like "agenda:ubicacions/barcelona/barcelones/barcelona"
        comarca = get_nested_value(raw_data, "comarca_i_municipi")
        if comarca:
            parts = comarca.split("/")
            if parts:
                return parts[-1].title()

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

        # Castilla y León: imagen_evento
        img = get_nested_value(raw_data, "imagen_evento")
        if img:
            # Decode HTML entities in URL
            img = img.replace("&amp;", "&")
            return img

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

    def _parse_organizer(self, name: str | None) -> EventOrganizer | None:
        """Parse organizer from name."""
        if not name:
            return None

        name = clean_html(name) or ""
        if not name:
            return None

        name_lower = name.lower()
        org_type = OrganizerType.OTRO

        if any(kw in name_lower for kw in ["ayuntamiento", "diputación", "diputacion", "gobierno", "generalitat", "xunta", "junta"]):
            org_type = OrganizerType.INSTITUCION
        elif any(kw in name_lower for kw in ["museo", "biblioteca", "centro cultural", "teatro"]):
            org_type = OrganizerType.INSTITUCION
        elif any(kw in name_lower for kw in ["asociación", "asociacion", "fundación", "fundacion"]):
            org_type = OrganizerType.ASOCIACION
        elif any(kw in name_lower for kw in ["s.l.", "s.a.", "sl", "sa"]):
            org_type = OrganizerType.EMPRESA

        return EventOrganizer(name=name, type=org_type)

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
