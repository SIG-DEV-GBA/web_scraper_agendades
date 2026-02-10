"""Location extraction and normalization utilities.

Provides functions for extracting and normalizing Spanish location data:
cities, provinces, addresses, and venue names.
"""

import re
from typing import NamedTuple


class Location(NamedTuple):
    """Parsed location data."""

    venue_name: str | None
    address: str | None
    city: str | None
    province: str | None
    postal_code: str | None


# Spanish provinces by CCAA
PROVINCES_BY_CCAA = {
    "Andalucía": ["Almería", "Cádiz", "Córdoba", "Granada", "Huelva", "Jaén", "Málaga", "Sevilla"],
    "Aragón": ["Huesca", "Teruel", "Zaragoza"],
    "Asturias": ["Asturias"],
    "Illes Balears": ["Illes Balears"],
    "Canarias": ["Las Palmas", "Santa Cruz de Tenerife"],
    "Cantabria": ["Cantabria"],
    "Castilla y León": ["Ávila", "Burgos", "León", "Palencia", "Salamanca", "Segovia", "Soria", "Valladolid", "Zamora"],
    "Castilla-La Mancha": ["Albacete", "Ciudad Real", "Cuenca", "Guadalajara", "Toledo"],
    "Cataluña": ["Barcelona", "Girona", "Lleida", "Tarragona"],
    "Comunitat Valenciana": ["Alicante", "Castellón", "Valencia"],
    "Extremadura": ["Badajoz", "Cáceres"],
    "Galicia": ["A Coruña", "Lugo", "Ourense", "Pontevedra"],
    "Comunidad de Madrid": ["Madrid"],
    "Región de Murcia": ["Murcia"],
    "Navarra": ["Navarra"],
    "País Vasco": ["Araba/Álava", "Bizkaia", "Gipuzkoa"],
    "La Rioja": ["La Rioja"],
}

# Reverse lookup: province -> CCAA
CCAA_BY_PROVINCE = {}
for ccaa, provinces in PROVINCES_BY_CCAA.items():
    for province in provinces:
        CCAA_BY_PROVINCE[province.lower()] = ccaa

# Common street type abbreviations
STREET_ABBREVIATIONS = {
    "c/": "Calle",
    "c.": "Calle",
    "cl.": "Calle",
    "cl/": "Calle",
    "avda.": "Avenida",
    "av.": "Avenida",
    "avda": "Avenida",
    "pza.": "Plaza",
    "pl.": "Plaza",
    "plza.": "Plaza",
    "pº": "Paseo",
    "p.º": "Paseo",
    "ctra.": "Carretera",
    "crta.": "Carretera",
    "pje.": "Pasaje",
    "rda.": "Ronda",
    "urb.": "Urbanización",
    "pol.": "Polígono",
    "nº": "número",
    "n.º": "número",
    "núm.": "número",
}


def normalize_address(address: str | None) -> str | None:
    """Normalize a street address.

    Expands common abbreviations and normalizes format.

    Args:
        address: Raw address string

    Returns:
        Normalized address or None
    """
    if not address:
        return None

    result = address.strip()

    # Expand abbreviations (case-insensitive)
    for abbr, full in STREET_ABBREVIATIONS.items():
        pattern = re.compile(re.escape(abbr), re.IGNORECASE)
        result = pattern.sub(full, result)

    # Normalize whitespace
    result = re.sub(r"\s+", " ", result)

    return result.strip() if result.strip() else None


def extract_postal_code(text: str | None) -> str | None:
    """Extract Spanish postal code from text.

    Args:
        text: Text that may contain a postal code

    Returns:
        5-digit postal code or None
    """
    if not text:
        return None

    # Spanish postal codes are 5 digits, starting with 01-52
    match = re.search(r"\b(0[1-9]|[1-4]\d|5[0-2])\d{3}\b", text)
    return match.group(0) if match else None


def extract_city_from_text(text: str | None) -> str | None:
    """Extract city name from free text.

    Looks for patterns like "en Ciudad" or "de Ciudad" at the end.

    Args:
        text: Text that may contain city reference

    Returns:
        City name or None
    """
    if not text:
        return None

    # Pattern: "en/de Ciudad" at end
    match = re.search(
        r'\b(?:en|de)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de(?:l)?|la|el)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)\s*$',
        text
    )
    if match:
        return match.group(1)

    return None


def get_province_from_city(city: str, ccaa: str | None = None) -> str | None:
    """Get province from city name.

    For major cities that are also province capitals.

    Args:
        city: City name
        ccaa: Optional CCAA to narrow search

    Returns:
        Province name or None
    """
    if not city:
        return None

    city_lower = city.lower().strip()

    # Major cities that match province names
    city_to_province = {
        "madrid": "Madrid",
        "barcelona": "Barcelona",
        "valencia": "Valencia",
        "sevilla": "Sevilla",
        "zaragoza": "Zaragoza",
        "málaga": "Málaga",
        "malaga": "Málaga",
        "murcia": "Murcia",
        "palma": "Illes Balears",
        "las palmas": "Las Palmas",
        "bilbao": "Bizkaia",
        "alicante": "Alicante",
        "córdoba": "Córdoba",
        "cordoba": "Córdoba",
        "valladolid": "Valladolid",
        "vigo": "Pontevedra",
        "gijón": "Asturias",
        "gijon": "Asturias",
        "granada": "Granada",
        "vitoria": "Araba/Álava",
        "oviedo": "Asturias",
        "santander": "Cantabria",
        "pamplona": "Navarra",
        "logroño": "La Rioja",
        "badajoz": "Badajoz",
        "cáceres": "Cáceres",
        "caceres": "Cáceres",
    }

    return city_to_province.get(city_lower)


def get_ccaa_from_province(province: str) -> str | None:
    """Get CCAA from province name.

    Args:
        province: Province name

    Returns:
        CCAA name or None
    """
    if not province:
        return None

    return CCAA_BY_PROVINCE.get(province.lower().strip())


def parse_location_string(location_str: str | None) -> Location:
    """Parse a location string into components.

    Attempts to extract venue, address, city from combined strings.

    Args:
        location_str: Combined location string

    Returns:
        Location namedtuple with parsed components
    """
    if not location_str:
        return Location(None, None, None, None, None)

    venue_name = None
    address = None
    city = None
    province = None
    postal_code = None

    # Extract postal code first
    postal_code = extract_postal_code(location_str)

    # Split by common separators
    parts = re.split(r"[,\-–—]", location_str)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) >= 3:
        # Format: "Venue, Address, City"
        venue_name = parts[0]
        address = normalize_address(parts[1])
        city = parts[-1]
    elif len(parts) == 2:
        # Format: "Venue, City" or "Address, City"
        first = parts[0]
        second = parts[1]

        # If first part looks like an address
        if re.search(r'\b(?:calle|avenida|plaza|paseo|c/|av\.|pza\.)\b', first, re.IGNORECASE):
            address = normalize_address(first)
            city = second
        else:
            venue_name = first
            city = second
    elif len(parts) == 1:
        # Just venue or city
        venue_name = parts[0]

    return Location(
        venue_name=venue_name,
        address=address,
        city=city,
        province=province,
        postal_code=postal_code,
    )


# Regional municipality sets for city extraction
ASTURIAS_MUNICIPALITIES = {
    "oviedo", "gijón", "gijon", "avilés", "aviles", "langreo", "mieres",
    "siero", "castrillón", "laviana", "lena", "corvera",
    "llanes", "ribadesella", "villaviciosa", "colunga", "cudillero",
    "cangas de onís", "onís", "cabrales", "parres", "piloña", "nava",
    "aller", "caso", "sobrescobio", "morcín", "riosa", "quirós",
    "navia", "valdés", "tineo", "cangas del narcea", "pravia", "salas",
}

TENERIFE_MUNICIPALITIES = {
    "santa cruz", "santa cruz de tenerife", "la laguna", "la orotava",
    "puerto de la cruz", "los realejos", "arona", "adeje", "granadilla",
    "guía de isora", "icod de los vinos", "candelaria", "tacoronte",
}

GRAN_CANARIA_MUNICIPALITIES = {
    "las palmas", "las palmas de gran canaria", "telde", "santa lucía",
    "san bartolomé de tirajana", "arucas", "agüimes", "gáldar",
    "ingenio", "mogán", "la aldea", "santa brígida", "teror",
}


def get_canarias_province(venue_or_city: str, default: str = "Santa Cruz de Tenerife") -> str:
    """Determine Canarias province from venue or city name.

    Args:
        venue_or_city: Venue or city name
        default: Default province if not determined

    Returns:
        Province name
    """
    if not venue_or_city:
        return default

    text_lower = venue_or_city.lower()

    # Check for Gran Canaria indicators
    if any(m in text_lower for m in GRAN_CANARIA_MUNICIPALITIES):
        return "Las Palmas"

    if "gran canaria" in text_lower:
        return "Las Palmas"

    # Check for Tenerife indicators
    if any(m in text_lower for m in TENERIFE_MUNICIPALITIES):
        return "Santa Cruz de Tenerife"

    return default


def extract_asturias_city(title: str) -> str | None:
    """Extract city from Asturias event title.

    Args:
        title: Event title

    Returns:
        City name or None
    """
    if not title:
        return None

    # Pattern: 'en Ciudad' or 'de Ciudad' at end
    match = re.search(r'\b(?:en|de)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[a-záéíóúñ]+)?)\s*$', title)
    if match:
        return match.group(1)

    # Check for known municipalities
    title_lower = title.lower()
    for city in ASTURIAS_MUNICIPALITIES:
        if title_lower.endswith(city) or title_lower.endswith('. ' + city):
            return title.split()[-1].rstrip('.')

    return None
