"""Gold-level API source configurations.

Gold sources are high-quality structured APIs from Spanish CCAAs that provide
clean JSON data requiring minimal transformation.

These sources use the fastest LLM tier (gpt-oss-120b) for enrichment.
"""

from src.config.sources import (
    GoldSourceConfig,
    PaginationType,
    SourceRegistry,
    SourceTier,
)

# ============================================================
# GOLD SOURCE CONFIGURATIONS
# ============================================================

GOLD_SOURCES: list[GoldSourceConfig] = [
    # ============================================================
    # NAVARRA - Adaptadores personalizados con Playwright
    # ============================================================
    GoldSourceConfig(
        slug="visitnavarra",
        name="Visit Navarra - Turismo de Navarra",
        url="https://www.visitnavarra.es/es/agenda",
        ccaa="Navarra",
        ccaa_code="NA",
        tier=SourceTier.GOLD,  # Uses registered adapter
        pagination_type=PaginationType.NONE,  # Handled by adapter
        default_province="Navarra",
    ),
    # larioja_agenda - usa adapter custom en bronze/larioja_agenda.py
    GoldSourceConfig(
        slug="pamplona",
        name="Ayuntamiento de Pamplona - Agenda de Eventos",
        url="https://www.pamplona.es/actualidad/eventos",
        ccaa="Navarra",
        ccaa_code="NA",
        tier=SourceTier.GOLD,  # Uses registered adapter
        pagination_type=PaginationType.NONE,  # Handled by adapter
        default_province="Navarra",
    ),
    # ============================================================
    # APIs Gold - Datos estructurados
    # ============================================================
    GoldSourceConfig(
        slug="catalunya_agenda",
        name="Agenda Cultural de Catalunya",
        url="https://analisi.transparenciacatalunya.cat/resource/rhpv-yr4f.json",
        ccaa="Cataluña",
        ccaa_code="CT",
        tier=SourceTier.GOLD,
        pagination_type=PaginationType.SOCRATA,
        page_size=1000,
        offset_param="$offset",
        limit_param="$limit",
        items_path="",
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
            "subt_tol": "summary",
            "url": "organizer_url",
            "email": "contact_email",
            "tel_fon": "contact_phone",
            "modalitat": "modality_text",
            "destacada": "is_featured_text",
        },
    ),
    GoldSourceConfig(
        slug="euskadi_kulturklik",
        name="Kulturklik - Agenda Cultural Euskadi",
        url="https://api.euskadi.eus/culture/events/v1.0/events/upcoming",
        ccaa="País Vasco",
        ccaa_code="PV",
        tier=SourceTier.GOLD,
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
            "sourceNameEs": "organizer_source",
            "sourceUrlEs": "organizer_url",
        },
    ),
    GoldSourceConfig(
        slug="castilla_leon_agenda",
        name="Agenda Cultural Castilla y León",
        url="https://analisis.datosabiertos.jcyl.es/api/explore/v2.1/catalog/datasets/eventos-de-la-agenda-cultural-categorizados-y-geolocalizados/records",
        ccaa="Castilla y León",
        ccaa_code="CL",
        tier=SourceTier.GOLD,
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
    GoldSourceConfig(
        slug="andalucia_agenda",
        name="Agenda de Eventos Junta de Andalucía",
        url="https://www.juntadeandalucia.es/ssdigitales/datasets/contentapi/1.0.0/search/agenda.json?_source=data&sort=date:desc",
        ccaa="Andalucía",
        ccaa_code="AN",
        tier=SourceTier.GOLD,
        pagination_type=PaginationType.OFFSET_LIMIT,
        page_size=50,
        offset_param="from",
        limit_param="size",
        items_path="resultado",
        total_count_path="numResultados",
        date_format="%Y-%m-%d",
        free_value="Gratuito",
        image_url_prefix="https://www.juntadeandalucia.es",
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
    GoldSourceConfig(
        slug="madrid_datos_abiertos",
        name="Madrid Datos Abiertos - Eventos Culturales",
        # URL actualizada Feb 2026 - antiguo dataset 206974 migrado a 300107 en CKAN
        url="https://datos.madrid.es/dataset/300107-0-agenda-actividades-eventos/resource/300107-5-agenda-actividades-eventos-json/download/300107-0-agenda-actividades-eventos.json",
        ccaa="Comunidad de Madrid",
        ccaa_code="MD",
        tier=SourceTier.GOLD,
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
    GoldSourceConfig(
        slug="valencia_ivc",
        name="Institut Valencià de Cultura - Agenda Cultural",
        url="https://dadesobertes.gva.es/dataset/25cc4d21-e1dd-4d05-b057-dbcc44d4338c/resource/15084e00-c416-4b4d-b229-7a06f4bf07b0/download/lista-de-actividades-culturales-programadas-por-el-ivc.json",
        ccaa="Comunitat Valenciana",
        ccaa_code="VC",
        tier=SourceTier.GOLD,
        pagination_type=PaginationType.NONE,
        items_path="data",
        date_format="%d/%m/%Y",
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
    GoldSourceConfig(
        slug="zaragoza_cultura",
        name="Agenda Cultural de Zaragoza",
        url="https://www.zaragoza.es/sede/servicio/cultura.json",
        ccaa="Aragón",
        ccaa_code="AR",
        tier=SourceTier.GOLD,
        pagination_type=PaginationType.NONE,
        items_path="__zaragoza_special__",
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
            "subEvent.0.location.streetAddress": "address",
            "subEvent.0.location.addressLocality": "city",
            "subEvent.0.location.postalCode": "postal_code",
            "subEvent.0.location.telephone": "contact_phone",
            "subEvent.0.location.email": "contact_email",
            "category.0.title": "category_name_alt",
        },
    ),
]

# Euskadi province codes mapping
EUSKADI_PROVINCE_CODES = {
    "1": "Araba/Álava",
    "20": "Gipuzkoa",
    "48": "Bizkaia",
}

# Madrid accessibility codes
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

# Number of fields per event for Valencia IVC (flat array format)
VALENCIA_IVC_FIELDS_PER_EVENT = 16


# Register all Gold sources
SourceRegistry.register_many(GOLD_SOURCES)


def get_gold_source(slug: str) -> GoldSourceConfig | None:
    """Get a Gold source by slug.

    Args:
        slug: Source identifier

    Returns:
        GoldSourceConfig or None
    """
    source = SourceRegistry.get(slug)
    if source and isinstance(source, GoldSourceConfig):
        return source
    return None


def get_all_gold_sources() -> list[GoldSourceConfig]:
    """Get all Gold sources.

    Returns:
        List of GoldSourceConfig
    """
    return [s for s in SourceRegistry.get_by_tier(SourceTier.GOLD) if isinstance(s, GoldSourceConfig)]
