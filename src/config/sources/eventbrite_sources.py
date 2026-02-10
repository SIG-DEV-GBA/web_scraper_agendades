"""Eventbrite source configurations.

Eventbrite sources use Firecrawl for JS rendering and extract JSON-LD
structured data. Coverage: all 52 Spanish provinces.
"""

from src.config.sources import (
    EventbriteSourceConfig,
    SourceRegistry,
    SourceTier,
)

# ============================================================
# EVENTBRITE SOURCE CONFIGURATIONS
# ============================================================

EVENTBRITE_SOURCES: list[EventbriteSourceConfig] = [
    # ============================================================
    # ANDALUCÍA (8 provinces)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_sevilla",
        name="Eventbrite - Sevilla",
        search_url="https://www.eventbrite.es/d/spain--sevilla/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Sevilla",
        city="Sevilla",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_malaga",
        name="Eventbrite - Málaga",
        search_url="https://www.eventbrite.es/d/spain--m%C3%A1laga/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Málaga",
        city="Málaga",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_granada",
        name="Eventbrite - Granada",
        search_url="https://www.eventbrite.es/d/spain--granada/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Granada",
        city="Granada",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_cordoba",
        name="Eventbrite - Córdoba",
        search_url="https://www.eventbrite.es/d/spain--c%C3%B3rdoba/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Córdoba",
        city="Córdoba",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_cadiz",
        name="Eventbrite - Cádiz",
        search_url="https://www.eventbrite.es/d/spain--c%C3%A1diz/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Cádiz",
        city="Cádiz",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_almeria",
        name="Eventbrite - Almería",
        search_url="https://www.eventbrite.es/d/spain--almer%C3%ADa/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Almería",
        city="Almería",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_huelva",
        name="Eventbrite - Huelva",
        search_url="https://www.eventbrite.es/d/spain--huelva/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Huelva",
        city="Huelva",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_jaen",
        name="Eventbrite - Jaén",
        search_url="https://www.eventbrite.es/d/spain--ja%C3%A9n/events/",
        ccaa="Andalucía",
        ccaa_code="AN",
        province="Jaén",
        city="Jaén",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # ARAGÓN (3 provinces)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_zaragoza",
        name="Eventbrite - Zaragoza",
        search_url="https://www.eventbrite.es/d/spain--zaragoza/events/",
        ccaa="Aragón",
        ccaa_code="AR",
        province="Zaragoza",
        city="Zaragoza",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_huesca",
        name="Eventbrite - Huesca",
        search_url="https://www.eventbrite.es/d/spain--huesca/events/",
        ccaa="Aragón",
        ccaa_code="AR",
        province="Huesca",
        city="Huesca",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_teruel",
        name="Eventbrite - Teruel",
        search_url="https://www.eventbrite.es/d/spain--teruel/events/",
        ccaa="Aragón",
        ccaa_code="AR",
        province="Teruel",
        city="Teruel",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # ASTURIAS (uniprovincial - 2 cities)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_asturias",
        name="Eventbrite - Asturias",
        search_url="https://www.eventbrite.es/d/spain--oviedo/events/",
        ccaa="Asturias",
        ccaa_code="AS",
        province="Asturias",
        city="Oviedo",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_gijon",
        name="Eventbrite - Gijón",
        search_url="https://www.eventbrite.es/d/spain--gij%C3%B3n/events/",
        ccaa="Asturias",
        ccaa_code="AS",
        province="Asturias",
        city="Gijón",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # ILLES BALEARS (uniprovincial - 3 islands)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_baleares",
        name="Eventbrite - Illes Balears",
        search_url="https://www.eventbrite.es/d/spain--palma-de-mallorca/events/",
        ccaa="Illes Balears",
        ccaa_code="IB",
        province="Illes Balears",
        city="Palma",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_ibiza",
        name="Eventbrite - Ibiza",
        search_url="https://www.eventbrite.es/d/spain--ibiza/events/",
        ccaa="Illes Balears",
        ccaa_code="IB",
        province="Illes Balears",
        city="Ibiza",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_menorca",
        name="Eventbrite - Menorca",
        search_url="https://www.eventbrite.es/d/spain--menorca/events/",
        ccaa="Illes Balears",
        ccaa_code="IB",
        province="Illes Balears",
        city="Mahon",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # CANARIAS (2 provinces)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_las_palmas",
        name="Eventbrite - Las Palmas",
        search_url="https://www.eventbrite.es/d/spain--las-palmas-de-gran-canaria/events/",
        ccaa="Canarias",
        ccaa_code="CN",
        province="Las Palmas",
        city="Las Palmas de Gran Canaria",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_tenerife",
        name="Eventbrite - Tenerife",
        search_url="https://www.eventbrite.es/d/spain--santa-cruz-de-tenerife/events/",
        ccaa="Canarias",
        ccaa_code="CN",
        province="Santa Cruz de Tenerife",
        city="Santa Cruz de Tenerife",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # CANTABRIA (uniprovincial)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_cantabria",
        name="Eventbrite - Cantabria",
        search_url="https://www.eventbrite.es/d/spain--santander/events/",
        ccaa="Cantabria",
        ccaa_code="CB",
        province="Cantabria",
        city="Santander",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # CASTILLA-LA MANCHA (5 provinces)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_toledo",
        name="Eventbrite - Toledo",
        search_url="https://www.eventbrite.es/d/spain--toledo/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Toledo",
        city="Toledo",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_ciudad_real",
        name="Eventbrite - Ciudad Real",
        search_url="https://www.eventbrite.es/d/spain--ciudad-real/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Ciudad Real",
        city="Ciudad Real",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_albacete",
        name="Eventbrite - Albacete",
        search_url="https://www.eventbrite.es/d/spain--albacete/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Albacete",
        city="Albacete",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_cuenca",
        name="Eventbrite - Cuenca",
        search_url="https://www.eventbrite.es/d/spain--cuenca/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Cuenca",
        city="Cuenca",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_guadalajara",
        name="Eventbrite - Guadalajara",
        search_url="https://www.eventbrite.es/d/spain--guadalajara/events/",
        ccaa="Castilla-La Mancha",
        ccaa_code="CM",
        province="Guadalajara",
        city="Guadalajara",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # CASTILLA Y LEÓN (9 provinces)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_valladolid",
        name="Eventbrite - Valladolid",
        search_url="https://www.eventbrite.es/d/spain--valladolid/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Valladolid",
        city="Valladolid",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_leon",
        name="Eventbrite - León",
        search_url="https://www.eventbrite.es/d/spain--le%C3%B3n/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="León",
        city="León",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_salamanca",
        name="Eventbrite - Salamanca",
        search_url="https://www.eventbrite.es/d/spain--salamanca/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Salamanca",
        city="Salamanca",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_burgos",
        name="Eventbrite - Burgos",
        search_url="https://www.eventbrite.es/d/spain--burgos/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Burgos",
        city="Burgos",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_zamora",
        name="Eventbrite - Zamora",
        search_url="https://www.eventbrite.es/d/spain--zamora/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Zamora",
        city="Zamora",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_palencia",
        name="Eventbrite - Palencia",
        search_url="https://www.eventbrite.es/d/spain--palencia/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Palencia",
        city="Palencia",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_avila",
        name="Eventbrite - Ávila",
        search_url="https://www.eventbrite.es/d/spain--%C3%A1vila/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Ávila",
        city="Ávila",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_segovia",
        name="Eventbrite - Segovia",
        search_url="https://www.eventbrite.es/d/spain--segovia/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Segovia",
        city="Segovia",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_soria",
        name="Eventbrite - Soria",
        search_url="https://www.eventbrite.es/d/spain--soria/events/",
        ccaa="Castilla y León",
        ccaa_code="CL",
        province="Soria",
        city="Soria",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # CATALUÑA (4 provinces)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_barcelona",
        name="Eventbrite - Barcelona",
        search_url="https://www.eventbrite.es/d/spain--barcelona/events/",
        ccaa="Cataluña",
        ccaa_code="CT",
        province="Barcelona",
        city="Barcelona",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_tarragona",
        name="Eventbrite - Tarragona",
        search_url="https://www.eventbrite.es/d/spain--tarragona/events/",
        ccaa="Cataluña",
        ccaa_code="CT",
        province="Tarragona",
        city="Tarragona",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_girona",
        name="Eventbrite - Girona",
        search_url="https://www.eventbrite.es/d/spain--girona/events/",
        ccaa="Cataluña",
        ccaa_code="CT",
        province="Girona",
        city="Girona",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_lleida",
        name="Eventbrite - Lleida",
        search_url="https://www.eventbrite.es/d/spain--lleida/events/",
        ccaa="Cataluña",
        ccaa_code="CT",
        province="Lleida",
        city="Lleida",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # COMUNITAT VALENCIANA (3 provinces)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_valencia",
        name="Eventbrite - Valencia",
        search_url="https://www.eventbrite.es/d/spain--valencia/events/",
        ccaa="Comunitat Valenciana",
        ccaa_code="VC",
        province="Valencia",
        city="Valencia",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_alicante",
        name="Eventbrite - Alicante",
        search_url="https://www.eventbrite.es/d/spain--alicante/events/",
        ccaa="Comunitat Valenciana",
        ccaa_code="VC",
        province="Alicante",
        city="Alicante",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_castellon",
        name="Eventbrite - Castellón",
        search_url="https://www.eventbrite.es/d/spain--castell%C3%B3n-de-la-plana/events/",
        ccaa="Comunitat Valenciana",
        ccaa_code="VC",
        province="Castellón",
        city="Castellón de la Plana",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # EXTREMADURA (2 provinces)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_badajoz",
        name="Eventbrite - Badajoz",
        search_url="https://www.eventbrite.es/d/spain--badajoz/events/",
        ccaa="Extremadura",
        ccaa_code="EX",
        province="Badajoz",
        city="Badajoz",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_caceres",
        name="Eventbrite - Cáceres",
        search_url="https://www.eventbrite.es/d/spain--c%C3%A1ceres/events/",
        ccaa="Extremadura",
        ccaa_code="EX",
        province="Cáceres",
        city="Cáceres",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # GALICIA (4 provinces + 1 city)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_a_coruna",
        name="Eventbrite - A Coruña",
        search_url="https://www.eventbrite.es/d/spain--a-coru%C3%B1a/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="A Coruña",
        city="A Coruña",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_vigo",
        name="Eventbrite - Vigo",
        search_url="https://www.eventbrite.es/d/spain--vigo/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="Pontevedra",
        city="Vigo",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_santiago",
        name="Eventbrite - Santiago de Compostela",
        search_url="https://www.eventbrite.es/d/spain--santiago-de-compostela/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="A Coruña",
        city="Santiago de Compostela",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_ourense",
        name="Eventbrite - Ourense",
        search_url="https://www.eventbrite.es/d/spain--ourense/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="Ourense",
        city="Ourense",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_lugo",
        name="Eventbrite - Lugo",
        search_url="https://www.eventbrite.es/d/spain--lugo/events/",
        ccaa="Galicia",
        ccaa_code="GA",
        province="Lugo",
        city="Lugo",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # LA RIOJA (uniprovincial)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_la_rioja",
        name="Eventbrite - La Rioja",
        search_url="https://www.eventbrite.es/d/spain--logro%C3%B1o/events/",
        ccaa="La Rioja",
        ccaa_code="RI",
        province="La Rioja",
        city="Logroño",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # MADRID (uniprovincial)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_madrid",
        name="Eventbrite - Madrid",
        search_url="https://www.eventbrite.es/d/spain--madrid/events/",
        ccaa="Comunidad de Madrid",
        ccaa_code="MD",
        province="Madrid",
        city="Madrid",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # REGIÓN DE MURCIA (uniprovincial + city)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_murcia",
        name="Eventbrite - Murcia",
        search_url="https://www.eventbrite.es/d/spain--murcia/events/",
        ccaa="Región de Murcia",
        ccaa_code="MC",
        province="Murcia",
        city="Murcia",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_cartagena",
        name="Eventbrite - Cartagena",
        search_url="https://www.eventbrite.es/d/spain--cartagena/events/",
        ccaa="Región de Murcia",
        ccaa_code="MC",
        province="Murcia",
        city="Cartagena",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # NAVARRA (uniprovincial)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_navarra",
        name="Eventbrite - Navarra",
        search_url="https://www.eventbrite.es/d/spain--pamplona/events/",
        ccaa="Navarra",
        ccaa_code="NC",
        province="Navarra",
        city="Pamplona",
        tier=SourceTier.EVENTBRITE,
    ),
    # ============================================================
    # PAÍS VASCO (3 provinces)
    # ============================================================
    EventbriteSourceConfig(
        slug="eventbrite_bilbao",
        name="Eventbrite - Bilbao",
        search_url="https://www.eventbrite.es/d/spain--bilbao/events/",
        ccaa="País Vasco",
        ccaa_code="PV",
        province="Bizkaia",
        city="Bilbao",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_donostia",
        name="Eventbrite - Donostia-San Sebastián",
        search_url="https://www.eventbrite.es/d/spain--san-sebasti%C3%A1n/events/",
        ccaa="País Vasco",
        ccaa_code="PV",
        province="Gipuzkoa",
        city="Donostia-San Sebastián",
        tier=SourceTier.EVENTBRITE,
    ),
    EventbriteSourceConfig(
        slug="eventbrite_vitoria",
        name="Eventbrite - Vitoria-Gasteiz",
        search_url="https://www.eventbrite.es/d/spain--vitoria-gasteiz/events/",
        ccaa="País Vasco",
        ccaa_code="PV",
        province="Araba/Álava",
        city="Vitoria-Gasteiz",
        tier=SourceTier.EVENTBRITE,
    ),
]

# Register all Eventbrite sources
SourceRegistry.register_many(EVENTBRITE_SOURCES)


def get_eventbrite_source(slug: str) -> EventbriteSourceConfig | None:
    """Get an Eventbrite source by slug.

    Args:
        slug: Source identifier

    Returns:
        EventbriteSourceConfig or None
    """
    source = SourceRegistry.get(slug)
    if source and isinstance(source, EventbriteSourceConfig):
        return source
    return None


def get_all_eventbrite_sources() -> list[EventbriteSourceConfig]:
    """Get all Eventbrite sources.

    Returns:
        List of EventbriteSourceConfig
    """
    return [
        s for s in SourceRegistry.get_by_tier(SourceTier.EVENTBRITE)
        if isinstance(s, EventbriteSourceConfig)
    ]
