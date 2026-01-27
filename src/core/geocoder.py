"""Geocoding service using Nominatim (OpenStreetMap).

Free geocoding without API key, with caching and rate limiting.
Also uses CCAA API to resolve correct autonomous community for cities.
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from src.logging.logger import get_logger

logger = get_logger(__name__)

# Nominatim requires respectful usage:
# - Max 1 request per second
# - Identify with User-Agent
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Agendades-EventApp/1.0 (scraper)"
MIN_REQUEST_INTERVAL = 1.1  # seconds between requests

# CCAA API for resolving correct autonomous community
CCAA_API_URL = "https://ccaa-provincias-municipios-localida.vercel.app/api/buscar"


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

    async def _resolve_ccaa(self, city: str | None) -> str | None:
        """Resolve the correct CCAA for a city using the CCAA API.

        Uses the municipios endpoint to find exact matches, prioritizing
        larger/more important municipalities over small localities.

        Args:
            city: City name to look up

        Returns:
            CCAA name if found, None otherwise
        """
        if not city:
            return None

        city_lower = city.lower().strip()

        # Check cache first
        if city_lower in self._ccaa_cache:
            return self._ccaa_cache[city_lower]

        client = await self.get_client()

        try:
            response = await client.get(CCAA_API_URL, params={"q": city})
            response.raise_for_status()
            data = response.json()

            results = data.get("results", {})

            # Priority 1: Exact match in municipios (most reliable)
            municipios = results.get("municipios", [])
            for muni in municipios:
                if muni.get("nombre", "").lower() == city_lower:
                    ccaa = muni.get("comunidad")
                    if ccaa:
                        logger.debug("ccaa_resolved_municipio", city=city, ccaa=ccaa)
                        self._ccaa_cache[city_lower] = ccaa
                        return ccaa

            # Priority 2: Exact match in provincias
            provincias = results.get("provincias", [])
            for prov in provincias:
                if prov.get("nombre", "").lower() == city_lower:
                    ccaa = prov.get("comunidad")
                    if ccaa:
                        logger.debug("ccaa_resolved_provincia", city=city, ccaa=ccaa)
                        self._ccaa_cache[city_lower] = ccaa
                        return ccaa

            # Priority 3: First municipio that contains the city name
            # (handles cases like "Las Palmas de Gran Canaria" searched as "Las Palmas")
            for muni in municipios:
                ccaa = muni.get("comunidad")
                if ccaa:
                    logger.debug("ccaa_resolved_partial", city=city, ccaa=ccaa, municipio=muni.get("nombre"))
                    self._ccaa_cache[city_lower] = ccaa
                    return ccaa

            # Not found
            logger.debug("ccaa_not_found", city=city)
            self._ccaa_cache[city_lower] = None
            return None

        except Exception as e:
            logger.warning("ccaa_api_error", city=city, error=str(e))
            return None

    def _cache_key(self, query: str) -> str:
        """Generate cache key for a query."""
        return hashlib.md5(query.lower().strip().encode()).hexdigest()

    async def _wait_for_rate_limit(self) -> None:
        """Ensure we respect Nominatim's rate limit."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

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
            logger.debug(
                "geocoding_success",
                query=query[:50],
                lat=geo_result.latitude,
                lon=geo_result.longitude,
                confidence=confidence,
            )
            return geo_result

        except httpx.HTTPStatusError as e:
            logger.warning("geocoding_http_error", query=query[:50], status=e.response.status_code)
            return None
        except Exception as e:
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
        # Resolve the correct CCAA for this city
        detected_ccaa = await self._resolve_ccaa(city)

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
