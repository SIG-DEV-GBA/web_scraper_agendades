"""Geocoding service using Nominatim (OpenStreetMap).

Free geocoding without API key, with caching and rate limiting.
Also uses CCAA API to resolve correct autonomous community for cities.
"""

import asyncio
import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from src.logging.logger import get_logger

logger = get_logger(__name__)

# Spanish address abbreviation mappings
ADDRESS_ABBREVIATIONS = {
    # Street types
    r"\bC/\.?\s*": "Calle ",
    r"\bC\.?\s+": "Calle ",
    r"\bCl\.?\s+": "Calle ",
    r"\bClle\.?\s+": "Calle ",
    r"\bAv\.?\s+": "Avenida ",
    r"\bAvda\.?\s+": "Avenida ",
    r"\bAvd\.?\s+": "Avenida ",
    r"\bPl\.?\s+": "Plaza ",
    r"\bPza\.?\s+": "Plaza ",
    r"\bPlza\.?\s+": "Plaza ",
    r"\bCtra\.?\s+": "Carretera ",
    r"\bCrta\.?\s+": "Carretera ",
    r"\bPº\.?\s*": "Paseo ",
    r"\bPso\.?\s+": "Paseo ",
    r"\bPseo\.?\s+": "Paseo ",
    r"\bRda\.?\s+": "Ronda ",
    r"\bUrb\.?\s+": "Urbanización ",
    r"\bEd\.?\s+": "Edificio ",
    r"\bEdif\.?\s+": "Edificio ",
    r"\bPol\.?\s*Ind\.?\s+": "Polígono Industrial ",
    r"\bBlq\.?\s+": "Bloque ",
    r"\bTrav\.?\s+": "Travesía ",
    r"\bPje\.?\s+": "Pasaje ",
    r"\bGlta\.?\s+": "Glorieta ",
    r"\bCjo\.?\s+": "Callejón ",
    r"\bBda\.?\s+": "Barriada ",
    r"\bPta\.?\s+": "Puerta ",
    r"\bEsc\.?\s+": "Escalera ",
    # Numbers and positions
    r"\bs/n\b": "sin número",
    r"\bS/N\b": "sin número",
    r"\bNº\.?\s*": "número ",
    r"\bnº\.?\s*": "número ",
    r"\bnum\.?\s*": "número ",
    r"\bdcha\.?\b": "derecha",
    r"\bDcha\.?\b": "derecha",
    r"\bizda\.?\b": "izquierda",
    r"\bizq\.?\b": "izquierda",
    r"\bIzda\.?\b": "izquierda",
    r"\bIzq\.?\b": "izquierda",
    r"\bbjo\.?\b": "bajo",
    r"\bBjo\.?\b": "bajo",
    r"\bdup\.?\b": "duplicado",
    r"\bDup\.?\b": "duplicado",
    # Common venue abbreviations
    r"\bCasa de la Cult\.?\b": "Casa de la Cultura",
    r"\bAudit\.?\b": "Auditorio",
    r"\bBibl\.?\b": "Biblioteca",
    r"\bCtro\.?\s+": "Centro ",
    r"\bCtr\.?\s+": "Centro ",
}


def normalize_address(text: str | None) -> str | None:
    """Normalize a Spanish address by expanding abbreviations.

    This improves geocoding accuracy by converting common abbreviations
    like "C/" to "Calle", "Av." to "Avenida", etc.

    Args:
        text: Address or venue name to normalize

    Returns:
        Normalized text with abbreviations expanded, or None if input was None
    """
    if not text:
        return text

    result = text

    # Apply all abbreviation expansions
    for pattern, replacement in ADDRESS_ABBREVIATIONS.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # Clean up multiple spaces
    result = re.sub(r"\s+", " ", result).strip()

    # Log if changes were made
    if result != text:
        logger.debug("address_normalized", original=text[:50], normalized=result[:50])

    return result

# Nominatim requires respectful usage:
# - Max 1 request per second
# - Identify with User-Agent
# - Be gentle with the service (they ban abusers)
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Agendades-EventApp/1.0 (contact@agendades.es)"
MIN_REQUEST_INTERVAL = 2.0  # seconds between requests (conservative)
MAX_REQUEST_INTERVAL = 30.0  # max backoff
BACKOFF_MULTIPLIER = 2.0  # exponential backoff on errors

# CCAA API for resolving correct autonomous community
CCAA_API_URL = "https://ccaa-provincias-municipios-localida.vercel.app/api/buscar"

# Fallback coordinates for Spanish cities (capitals and major cities)
# Used when Nominatim fails (rate limit, timeout, etc.)
CITY_COORDINATES: dict[str, tuple[float, float]] = {
    # Capitales de provincia
    "a coruña": (43.3623, -8.4115),
    "álava": (42.8467, -2.6726),
    "albacete": (38.9942, -1.8585),
    "alicante": (38.3452, -0.4815),
    "almería": (36.8340, -2.4637),
    "asturias": (43.3614, -5.8493),
    "ávila": (40.6566, -4.6818),
    "badajoz": (38.8794, -6.9706),
    "barcelona": (41.3851, 2.1734),
    "bilbao": (43.2630, -2.9350),
    "burgos": (42.3439, -3.6969),
    "cáceres": (39.4753, -6.3724),
    "cádiz": (36.5271, -6.2886),
    "cantabria": (43.4623, -3.8100),
    "castellón": (39.9864, -0.0513),
    "ceuta": (35.8894, -5.3198),
    "ciudad real": (38.9848, -3.9274),
    "córdoba": (37.8882, -4.7794),
    "cuenca": (40.0704, -2.1374),
    "donostia": (43.3183, -1.9812),
    "girona": (41.9794, 2.8214),
    "granada": (37.1773, -3.5986),
    "guadalajara": (40.6337, -3.1674),
    "guipúzcoa": (43.3183, -1.9812),
    "huelva": (37.2614, -6.9447),
    "huesca": (42.1401, -0.4089),
    "jaén": (37.7796, -3.7849),
    "la rioja": (42.4627, -2.4449),
    "las palmas": (28.1235, -15.4363),
    "león": (42.5987, -5.5671),
    "lleida": (41.6176, 0.6200),
    "logroño": (42.4627, -2.4449),
    "lugo": (43.0097, -7.5567),
    "madrid": (40.4168, -3.7038),
    "málaga": (36.7213, -4.4214),
    "melilla": (35.2923, -2.9381),
    "mérida": (38.9161, -6.3436),
    "murcia": (37.9922, -1.1307),
    "navarra": (42.8125, -1.6458),
    "ourense": (42.3358, -7.8639),
    "oviedo": (43.3614, -5.8493),
    "palencia": (42.0096, -4.5288),
    "palma": (39.5696, 2.6502),
    "pamplona": (42.8125, -1.6458),
    "pontevedra": (42.4310, -8.6446),
    "salamanca": (40.9701, -5.6635),
    "san sebastián": (43.3183, -1.9812),
    "santa cruz de tenerife": (28.4636, -16.2518),
    "santander": (43.4623, -3.8100),
    "segovia": (40.9429, -4.1088),
    "sevilla": (37.3891, -5.9845),
    "soria": (41.7636, -2.4649),
    "tarragona": (41.1189, 1.2445),
    "teruel": (40.3456, -1.1065),
    "toledo": (39.8628, -4.0273),
    "valencia": (39.4699, -0.3763),
    "valladolid": (41.6523, -4.7245),
    "vigo": (42.2406, -8.7207),
    "vitoria": (42.8467, -2.6726),
    "zamora": (41.5034, -5.7467),
    "zaragoza": (41.6488, -0.8891),
    # Ciudades importantes adicionales
    "gijón": (43.5453, -5.6615),
    "elche": (38.2669, -0.6983),
    "cartagena": (37.6057, -0.9913),
    "jerez de la frontera": (36.6850, -6.1261),
    "sabadell": (41.5463, 2.1086),
    "móstoles": (40.3223, -3.8650),
    "alcalá de henares": (40.4818, -3.3636),
    "fuenlabrada": (40.2839, -3.7940),
    "leganés": (40.3281, -3.7644),
    "getafe": (40.3058, -3.7328),
    "alcorcón": (40.3456, -3.8248),
    "hospitalet de llobregat": (41.3596, 2.0997),
    "badalona": (41.4500, 2.2474),
    "terrassa": (41.5630, 2.0089),
    "mataró": (41.5400, 2.4445),
    "santa coloma de gramenet": (41.4516, 2.2080),
    "reus": (41.1559, 1.1089),
    "sant cugat del vallès": (41.4736, 2.0863),
    "rubí": (41.4936, 2.0322),
}


def get_fallback_coordinates(city: str | None, province: str | None = None) -> tuple[float, float] | None:
    """Get fallback coordinates for a city from the local database.

    Args:
        city: City name to look up
        province: Province name (used as fallback if city not found)

    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    if city:
        city_lower = city.lower().strip()
        if city_lower in CITY_COORDINATES:
            return CITY_COORDINATES[city_lower]

    if province:
        province_lower = province.lower().strip()
        if province_lower in CITY_COORDINATES:
            return CITY_COORDINATES[province_lower]

    return None


@dataclass
class GeocodingResult:
    """Result from geocoding a location."""

    latitude: float
    longitude: float
    display_name: str
    place_id: int
    osm_type: str
    osm_id: int
    confidence: float  # 0-1 based on result quality
    detected_ccaa: str | None = None  # CCAA detected from city name
    is_fallback: bool = False  # True if coordinates are from fallback database


class NominatimGeocoder:
    """Geocoder using OpenStreetMap's Nominatim service.

    Features:
    - In-memory cache to avoid repeated requests
    - Rate limiting (1 req/sec as per Nominatim policy)
    - Multiple search strategies (specific to general)
    - Limited to Spain (countrycodes=es)
    - CCAA resolution via external API to detect correct autonomous community
    """

    def __init__(self) -> None:
        self._cache: dict[str, GeocodingResult | None] = {}
        self._ccaa_cache: dict[str, str | None] = {}  # city -> CCAA
        self._last_request_time: float = 0
        self._http_client: httpx.AsyncClient | None = None
        self._current_interval: float = MIN_REQUEST_INTERVAL
        self._consecutive_errors: int = 0

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"User-Agent": USER_AGENT},
            )
        return self._http_client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def _resolve_ccaa(self, city: str | None, province: str | None = None) -> str | None:
        """Resolve the correct CCAA for a city using the CCAA API.

        Uses the municipios endpoint to find exact matches, prioritizing
        larger/more important municipalities over small localities.
        If province is provided, uses it to disambiguate cities with same name.

        Args:
            city: City name to look up
            province: Province name to help disambiguate (optional)

        Returns:
            CCAA name if found, None otherwise
        """
        if not city:
            return None

        city_lower = city.lower().strip()
        province_lower = province.lower().strip() if province else None

        # Include province in cache key for disambiguation
        cache_key = f"{city_lower}|{province_lower or ''}"

        # Check cache first
        if cache_key in self._ccaa_cache:
            return self._ccaa_cache[cache_key]

        client = await self.get_client()

        try:
            response = await client.get(CCAA_API_URL, params={"q": city})
            response.raise_for_status()
            data = response.json()

            results = data.get("results", {})
            municipios = results.get("municipios", [])

            # Priority 1: Exact match in municipios with matching province (if provided)
            if province_lower:
                for muni in municipios:
                    if muni.get("nombre", "").lower() == city_lower:
                        muni_prov = muni.get("provincia", "").lower()
                        if province_lower in muni_prov or muni_prov in province_lower:
                            ccaa = muni.get("comunidad")
                            if ccaa:
                                logger.debug("ccaa_resolved_municipio_with_province", city=city, province=province, ccaa=ccaa)
                                self._ccaa_cache[cache_key] = ccaa
                                return ccaa

            # Priority 2: Exact match in municipios (without province check)
            for muni in municipios:
                if muni.get("nombre", "").lower() == city_lower:
                    ccaa = muni.get("comunidad")
                    if ccaa:
                        logger.debug("ccaa_resolved_municipio", city=city, ccaa=ccaa)
                        self._ccaa_cache[cache_key] = ccaa
                        return ccaa

            # Priority 3: Exact match in provincias
            provincias = results.get("provincias", [])
            for prov in provincias:
                if prov.get("nombre", "").lower() == city_lower:
                    ccaa = prov.get("comunidad")
                    if ccaa:
                        logger.debug("ccaa_resolved_provincia", city=city, ccaa=ccaa)
                        self._ccaa_cache[cache_key] = ccaa
                        return ccaa

            # Priority 4: Partial match with province validation (if provided)
            # This avoids "Santa Cruz" matching "Santa Cruz de Marchena" when province is "Tenerife"
            if province_lower:
                for muni in municipios:
                    muni_prov = muni.get("provincia", "").lower()
                    if province_lower in muni_prov or muni_prov in province_lower:
                        ccaa = muni.get("comunidad")
                        if ccaa:
                            logger.debug("ccaa_resolved_partial_with_province", city=city, province=province, ccaa=ccaa, municipio=muni.get("nombre"))
                            self._ccaa_cache[cache_key] = ccaa
                            return ccaa

            # Priority 5: First municipio (last resort - may be wrong for ambiguous names)
            # Only use if no province provided and exact match failed
            if not province_lower and municipios:
                muni = municipios[0]
                ccaa = muni.get("comunidad")
                if ccaa:
                    logger.debug("ccaa_resolved_partial", city=city, ccaa=ccaa, municipio=muni.get("nombre"))
                    self._ccaa_cache[cache_key] = ccaa
                    return ccaa

            # Not found
            logger.debug("ccaa_not_found", city=city)
            self._ccaa_cache[cache_key] = None
            return None

        except Exception as e:
            logger.warning("ccaa_api_error", city=city, error=str(e))
            return None

    def _cache_key(self, query: str) -> str:
        """Generate cache key for a query."""
        return hashlib.md5(query.lower().strip().encode()).hexdigest()

    async def _wait_for_rate_limit(self) -> None:
        """Ensure we respect Nominatim's rate limit with exponential backoff."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._current_interval:
            wait_time = self._current_interval - elapsed
            logger.debug("geocoding_rate_limit_wait", wait_seconds=round(wait_time, 1))
            await asyncio.sleep(wait_time)
        self._last_request_time = time.time()

    def _on_request_success(self) -> None:
        """Reset backoff on successful request."""
        self._consecutive_errors = 0
        self._current_interval = MIN_REQUEST_INTERVAL

    def _on_request_error(self) -> None:
        """Increase backoff on error."""
        self._consecutive_errors += 1
        self._current_interval = min(
            MAX_REQUEST_INTERVAL,
            MIN_REQUEST_INTERVAL * (BACKOFF_MULTIPLIER ** self._consecutive_errors)
        )
        logger.debug(
            "geocoding_backoff_increased",
            consecutive_errors=self._consecutive_errors,
            new_interval=round(self._current_interval, 1)
        )

    async def _search(self, query: str) -> GeocodingResult | None:
        """Perform a single search request to Nominatim."""
        cache_key = self._cache_key(query)

        # Check cache first
        if cache_key in self._cache:
            logger.debug("geocoding_cache_hit", query=query[:50])
            return self._cache[cache_key]

        await self._wait_for_rate_limit()

        client = await self.get_client()

        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "countrycodes": "es",  # Limit to Spain
            "addressdetails": 1,
        }

        try:
            response = await client.get(NOMINATIM_BASE_URL, params=params)
            response.raise_for_status()

            results = response.json()

            if not results:
                logger.debug("geocoding_no_results", query=query[:50])
                self._cache[cache_key] = None
                self._on_request_success()  # No results is not an error
                return None

            result = results[0]

            # Calculate confidence based on importance and type
            importance = float(result.get("importance", 0.5))
            place_type = result.get("type", "")

            # Higher confidence for specific places
            type_boost = {
                "theatre": 0.2,
                "arts_centre": 0.2,
                "community_centre": 0.2,
                "museum": 0.2,
                "library": 0.15,
                "venue": 0.15,
                "building": 0.1,
                "street": 0.05,
                "city": 0.0,
                "town": 0.0,
            }
            confidence = min(1.0, importance + type_boost.get(place_type, 0))

            geo_result = GeocodingResult(
                latitude=float(result["lat"]),
                longitude=float(result["lon"]),
                display_name=result["display_name"],
                place_id=int(result["place_id"]),
                osm_type=result.get("osm_type", ""),
                osm_id=int(result.get("osm_id", 0)),
                confidence=confidence,
            )

            self._cache[cache_key] = geo_result
            self._on_request_success()
            logger.debug(
                "geocoding_success",
                query=query[:50],
                lat=geo_result.latitude,
                lon=geo_result.longitude,
                confidence=confidence,
            )
            return geo_result

        except httpx.HTTPStatusError as e:
            self._on_request_error()
            logger.warning("geocoding_http_error", query=query[:50], status=e.response.status_code)
            return None
        except Exception as e:
            self._on_request_error()
            logger.warning("geocoding_error", query=query[:50], error=str(e))
            return None

    async def geocode(
        self,
        venue_name: str | None = None,
        address: str | None = None,
        city: str | None = None,
        province: str | None = None,
        postal_code: str | None = None,
        comunidad_autonoma: str | None = None,
    ) -> GeocodingResult | None:
        """Geocode a location using multiple strategies.

        First resolves the correct CCAA for the city using the CCAA API.
        If the resolved CCAA differs from the passed one, uses the correct one
        to avoid geocoding errors (e.g., "Madrid, Andalucía" finding a small village).

        Normalizes addresses by expanding Spanish abbreviations (C/ → Calle, etc.)

        Tries from most specific to least specific:
        1. venue_name + city + province
        2. address + city + province
        3. address + city
        4. venue_name + city
        5. city + province (no CCAA to avoid conflicts)
        6. city only

        Args:
            venue_name: Name of the venue (e.g., "Teatro Real")
            address: Street address
            city: City name
            province: Province name
            postal_code: Postal code (not currently used but could help)
            comunidad_autonoma: Autonomous community (from source, may be incorrect)

        Returns:
            GeocodingResult with detected_ccaa set if city was resolved
        """
        # Normalize address abbreviations for better geocoding
        venue_name = normalize_address(venue_name)
        address = normalize_address(address)

        # Resolve the correct CCAA for this city (use province to disambiguate)
        detected_ccaa = await self._resolve_ccaa(city, province)

        # If the resolved CCAA differs from source, log a warning
        ccaa_mismatch = False
        if detected_ccaa and comunidad_autonoma:
            if detected_ccaa.lower() != comunidad_autonoma.lower():
                logger.info(
                    "ccaa_mismatch_detected",
                    city=city,
                    source_ccaa=comunidad_autonoma,
                    detected_ccaa=detected_ccaa,
                )
                ccaa_mismatch = True

        # Build search strategies from most to least specific
        # IMPORTANT: Don't use source CCAA in searches to avoid false matches
        strategies: list[str] = []

        # Strategy 1: Full venue + city + province (most specific, no CCAA)
        if venue_name and city and province:
            strategies.append(f"{venue_name}, {city}, {province}, España")

        # Strategy 2: Address + city + province
        if address and city and province:
            strategies.append(f"{address}, {city}, {province}, España")

        # Strategy 3: Address + city
        if address and city:
            strategies.append(f"{address}, {city}, España")

        # Strategy 4: Venue + city
        if venue_name and city:
            strategies.append(f"{venue_name}, {city}, España")

        # Strategy 5: City + province (without CCAA - safer)
        if city and province:
            strategies.append(f"{city}, {province}, España")

        # Strategy 6: Just city (Nominatim is already limited to Spain)
        if city:
            strategies.append(f"{city}, España")

        # Try each strategy
        for strategy in strategies:
            result = await self._search(strategy)
            if result:
                # Set the detected CCAA in the result
                result.detected_ccaa = detected_ccaa
                return result

        # Fallback: use local coordinates database if Nominatim failed
        fallback_coords = get_fallback_coordinates(city, province)
        if fallback_coords:
            logger.info(
                "geocoding_fallback_used",
                city=city,
                province=province,
                lat=fallback_coords[0],
                lon=fallback_coords[1],
            )
            return GeocodingResult(
                latitude=fallback_coords[0],
                longitude=fallback_coords[1],
                display_name=f"{city or province}, España",
                place_id=0,
                osm_type="fallback",
                osm_id=0,
                confidence=0.5,  # Lower confidence for fallback
                detected_ccaa=detected_ccaa,
                is_fallback=True,
            )

        return None

    async def geocode_batch(
        self,
        locations: list[dict[str, Any]],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, GeocodingResult | None]:
        """Geocode multiple locations.

        Args:
            locations: List of dicts with keys: event_id, venue_name, address, city, etc.
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Dict mapping event_id to GeocodingResult
        """
        results: dict[str, GeocodingResult | None] = {}
        total = len(locations)

        for i, loc in enumerate(locations):
            event_id = loc.get("event_id")
            if not event_id:
                continue

            result = await self.geocode(
                venue_name=loc.get("venue_name") or loc.get("name"),
                address=loc.get("address"),
                city=loc.get("city"),
                province=loc.get("province"),
                postal_code=loc.get("postal_code"),
                comunidad_autonoma=loc.get("comunidad_autonoma"),
            )

            results[event_id] = result

            if progress_callback:
                progress_callback(i + 1, total)

        return results


# Singleton instance
_geocoder: NominatimGeocoder | None = None


def get_geocoder() -> NominatimGeocoder:
    """Get singleton geocoder instance."""
    global _geocoder
    if _geocoder is None:
        _geocoder = NominatimGeocoder()
    return _geocoder
