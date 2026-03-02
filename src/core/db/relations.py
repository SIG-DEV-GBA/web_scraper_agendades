"""Related entity persistence: locations, organizers, contacts, etc."""

from typing import Any

from supabase import Client

from src.core.event_model import EventCreate
from src.core.geocoder import get_geocoder
from src.logging import get_logger

from src.core.db.event_builder import PUBLIC_CALENDAR_ID

logger = get_logger(__name__)

# Official CCAA names from INE API (https://ccaa-provincias-municipios-localida.vercel.app/api/comunidades)
# Map aliases to official names for consistency in event_locations table
CCAA_OFFICIAL_NAMES = {
    # Official names map to themselves
    "andalucía": "Andalucía",
    "aragón": "Aragón",
    "canarias": "Canarias",
    "cantabria": "Cantabria",
    "castilla y león": "Castilla y León",
    "castilla-la mancha": "Castilla-La Mancha",
    "cataluña": "Cataluña",
    "ceuta": "Ceuta",
    "comunidad de madrid": "Comunidad de Madrid",
    "comunidad valenciana": "Comunidad Valenciana",
    "extremadura": "Extremadura",
    "galicia": "Galicia",
    "islas baleares": "Islas Baleares",
    "la rioja": "La Rioja",
    "melilla": "Melilla",
    "navarra": "Navarra",
    "país vasco": "País Vasco",
    "principado de asturias": "Principado de Asturias",
    "región de murcia": "Región de Murcia",
    # Aliases -> official names
    "asturias": "Principado de Asturias",
    "madrid": "Comunidad de Madrid",
    "murcia": "Región de Murcia",
    "valencia": "Comunidad Valenciana",
    "euskadi": "País Vasco",
    "catalunya": "Cataluña",
    "illes balears": "Islas Baleares",
    "comunidad foral de navarra": "Navarra",
}


def normalize_ccaa(ccaa: str | None) -> str | None:
    """Normalize CCAA name to official INE format."""
    if not ccaa:
        return None
    return CCAA_OFFICIAL_NAMES.get(ccaa.lower().strip(), ccaa)


# CCAA Calendar mapping (comunidad_autonoma name -> calendar_id)
# Includes official names and common aliases
CCAA_CALENDARS = {
    "andalucía": "c0ecdd57-3afe-419a-8164-b58b3fa49af6",
    "aragón": "eebc93e1-e2a3-466f-9d19-681a9a12d379",
    "asturias": "204d4609-2513-4c78-aa7d-1d57df965cf9",
    "principado de asturias": "204d4609-2513-4c78-aa7d-1d57df965cf9",
    "islas baleares": "f77b0b73-c9e8-42e7-a5de-f3b075000bb3",
    "illes balears": "f77b0b73-c9e8-42e7-a5de-f3b075000bb3",
    "canarias": "0b5d5367-9e55-4189-a413-07ab0d26382b",
    "cantabria": "50a6e772-a004-4fd4-8589-e0f2f24a3df1",
    "castilla-la mancha": "99a0629d-caf3-49ea-9c1a-42865a28efed",
    "castilla y león": "139f9549-4c80-4278-9e41-07f4814719e0",
    "cataluña": "ca25eb5e-0012-4fae-af61-505a27aa604b",
    "catalunya": "ca25eb5e-0012-4fae-af61-505a27aa604b",
    "comunidad de madrid": "75235734-4fca-4299-8663-4ff894ecb156",
    "madrid": "75235734-4fca-4299-8663-4ff894ecb156",
    "comunidad valenciana": "175e520f-3145-4fc6-90ad-942c8674e7ae",
    "valencia": "175e520f-3145-4fc6-90ad-942c8674e7ae",
    "extremadura": "abeaf767-1b22-4db4-889e-6cf61735b51d",
    "galicia": "588d002f-8ae6-4a0e-8cef-6bbaedfe44d3",
    "región de murcia": "262ec6bf-a98e-4665-b6b2-500c24db8d83",
    "murcia": "262ec6bf-a98e-4665-b6b2-500c24db8d83",
    "navarra": "cd79db72-096a-44fa-9331-53f8eb7456a5",
    "comunidad foral de navarra": "cd79db72-096a-44fa-9331-53f8eb7456a5",
    "país vasco": "019ee009-51e5-436c-8f20-b65262b3c6c9",
    "euskadi": "019ee009-51e5-436c-8f20-b65262b3c6c9",
    "la rioja": "e069b836-c437-4ea4-9cf9-fc9222985889",
    "ceuta": "4e337434-dddb-4dc4-b049-0ab46f751f3c",
    "melilla": "3ac0c74b-5b2b-4854-81fb-79f43c75c980",
}


async def save_location(client: Client, event_id: str, event: EventCreate) -> bool:
    """Save location to event_locations table.

    Fields in event_locations:
    - name, address, city, municipio, province, comunidad_autonoma,
    - country, postal_code, latitude, longitude, details, map_url

    Automatically geocodes if coordinates are missing but address/city available.
    """
    # Check if we have any location data
    has_location = any([
        event.venue_name,
        event.address,
        event.city,
        event.latitude,
        event.longitude,
    ])

    if not has_location:
        return True

    try:
        # Get coordinates from event or geocode if missing
        latitude = event.latitude
        longitude = event.longitude

        # Geocode if we have address/city but no coordinates
        # Also resolves the correct CCAA for the city
        detected_ccaa = None
        if latitude is None or longitude is None:
            has_geocodable = any([event.venue_name, event.address, event.city])
            if has_geocodable:
                geocoder = get_geocoder()
                result = await geocoder.geocode(
                    venue_name=event.venue_name,
                    address=event.address,
                    city=event.city,
                    province=event.province,
                    postal_code=event.postal_code,
                    comunidad_autonoma=event.comunidad_autonoma,
                )
                if result:
                    latitude = result.latitude
                    longitude = result.longitude
                    detected_ccaa = result.detected_ccaa
                    logger.debug(
                        "geocoded_location",
                        event_id=event_id,
                        lat=latitude,
                        lon=longitude,
                        confidence=result.confidence,
                        detected_ccaa=detected_ccaa,
                    )

        # CCAA resolution: trust source over geocoder detection
        # The source already knows the correct CCAA (e.g., canarias_lagenda = Canarias)
        # Geocoder can fail with ambiguous cities (Santa Cruz exists in Andalucía AND Canarias)
        final_ccaa = event.comunidad_autonoma
        if detected_ccaa and detected_ccaa != event.comunidad_autonoma:
            if event.comunidad_autonoma:
                # Source has CCAA - trust it, just log the mismatch for debugging
                logger.debug(
                    "ccaa_mismatch_ignored",
                    event_id=event_id,
                    city=event.city,
                    source_ccaa=event.comunidad_autonoma,
                    detected_ccaa=detected_ccaa,
                    reason="trusting source CCAA over geocoder detection",
                )
                # Keep final_ccaa = event.comunidad_autonoma (source wins)
            else:
                # Source has no CCAA - use detected
                logger.info(
                    "ccaa_filled_from_geocoder",
                    event_id=event_id,
                    city=event.city,
                    detected_ccaa=detected_ccaa,
                )
                final_ccaa = detected_ccaa

        # Determine municipio: for Madrid city, use "Madrid" not district
        # Districts are subdivisions of the Madrid municipality
        municipio = event.city or ""
        city_lower = (event.city or "").lower().strip()
        if city_lower == "madrid" or city_lower == "madrid capital":
            municipio = "Madrid"
        elif event.district and event.district != event.city:
            # For other cities, district might be a different municipio
            municipio = event.district

        data = {
            "event_id": event_id,
            "name": event.venue_name or "",
            "address": event.address or "",
            "city": event.city or "",
            "municipio": municipio,
            "province": event.province or "",
            "comunidad_autonoma": normalize_ccaa(final_ccaa),  # Normalize to official INE name
            "country": event.country or "España",
            "postal_code": event.postal_code or "",
        }

        # Add coordinates if available (from event or geocoding)
        if latitude is not None:
            data["latitude"] = latitude
        if longitude is not None:
            data["longitude"] = longitude

        # Add details if available (parking, access info, meeting point, etc.)
        if event.location_details:
            data["details"] = event.location_details

        client.table("event_locations").insert(data).execute()
        return True
    except Exception as e:
        logger.warning("Failed to save location", event_id=event_id, error=str(e))
        return False


async def save_organizer(client: Client, event_id: str, event: EventCreate) -> bool:
    """Save organizer to event_organizers table."""
    organizer = event.organizer
    if not organizer:
        return True

    try:
        data = {
            "event_id": event_id,
            "name": organizer.name,
            "type": organizer.type.value if hasattr(organizer.type, "value") else organizer.type,
            "url": organizer.url,
            "logo_url": organizer.logo_url,
        }
        client.table("event_organizers").insert(data).execute()
        return True
    except Exception as e:
        logger.warning("Failed to save organizer", event_id=event_id, error=str(e))
        return False


async def save_registration(client: Client, event_id: str, event: EventCreate) -> bool:
    """Save registration info to event_registration table.

    Saves if:
    - event has registration_url, OR
    - event.requires_registration is True (e.g., registration via phone/email)
    - event has registration_info (instructions for how to register)
    """
    # Only save if we have registration data
    has_registration_data = any([
        event.registration_url,
        event.requires_registration,
        event.registration_info,
    ])
    if not has_registration_data:
        return True

    try:
        data = {
            "event_id": event_id,
            "requires_registration": event.requires_registration or bool(event.registration_url),
        }
        if event.registration_url:
            data["registration_url"] = event.registration_url
        if event.registration_info:
            data["registration_info"] = event.registration_info
        client.table("event_registration").insert(data).execute()
        return True
    except Exception as e:
        logger.warning("Failed to save registration", event_id=event_id, error=str(e))
        return False


async def save_accessibility(client: Client, event_id: str, event: EventCreate) -> bool:
    """Save accessibility info to event_accessibility table."""
    if not event.accessibility:
        return True

    try:
        data = {
            "event_id": event_id,
            "wheelchair_accessible": event.accessibility.wheelchair_accessible,
            "sign_language": event.accessibility.sign_language,
            "hearing_loop": event.accessibility.hearing_loop,
            "braille_materials": event.accessibility.braille_materials,
            "other_facilities": event.accessibility.other_facilities,
            "notes": event.accessibility.notes,
        }
        client.table("event_accessibility").insert(data).execute()
        return True
    except Exception as e:
        logger.warning("Failed to save accessibility", event_id=event_id, error=str(e))
        return False


async def save_contact(client: Client, event_id: str, event: EventCreate) -> bool:
    """Save contact info to event_contact table."""
    if not event.contact:
        return True

    # Only save if at least one field has data
    if not any([event.contact.name, event.contact.email, event.contact.phone, event.contact.info]):
        return True

    try:
        data = {
            "event_id": event_id,
            "name": event.contact.name,
            "email": event.contact.email,
            "phone": event.contact.phone,
            "info": event.contact.info,
        }
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        client.table("event_contact").insert(data).execute()
        return True
    except Exception as e:
        logger.warning("Failed to save contact", event_id=event_id, error=str(e))
        return False


async def save_online(client: Client, event_id: str, event: EventCreate) -> bool:
    """Save online event info to event_online table.

    For hybrid/online events with streaming URLs (YouTube, Zoom, etc.)
    """
    if not event.online_url:
        return True

    try:
        # Detect platform from URL
        platform = None
        url_lower = event.online_url.lower()
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            platform = "YouTube"
        elif "zoom.us" in url_lower:
            platform = "Zoom"
        elif "teams.microsoft.com" in url_lower:
            platform = "Microsoft Teams"
        elif "meet.google.com" in url_lower:
            platform = "Google Meet"
        elif "webex.com" in url_lower:
            platform = "Webex"

        data = {
            "event_id": event_id,
            "url": event.online_url,
            "platform": platform,
        }
        client.table("event_online").insert(data).execute()
        return True
    except Exception as e:
        logger.warning("Failed to save online info", event_id=event_id, error=str(e))
        return False


def get_calendar_ids_for_event(event: EventCreate) -> list[str]:
    """Get list of calendar IDs for an event based on its location."""
    calendar_ids = [PUBLIC_CALENDAR_ID]

    if event.comunidad_autonoma:
        ccaa_lower = event.comunidad_autonoma.lower().strip()
        if ccaa_lower in CCAA_CALENDARS:
            calendar_ids.append(CCAA_CALENDARS[ccaa_lower])

    return calendar_ids


async def link_event_to_calendars(client: Client, event_id: str, calendar_ids: list[str]) -> bool:
    """Link event to calendars via event_calendars junction table."""
    try:
        records = [{"event_id": event_id, "calendar_id": cid} for cid in calendar_ids]
        client.table("event_calendars").insert(records).execute()
        return True
    except Exception as e:
        logger.warning("Failed to link calendars", event_id=event_id, error=str(e))
        return False


async def link_event_to_categories(client: Client, event_id: str, category_ids: list[str]) -> bool:
    """Link event to categories via event_categories junction table (N:M)."""
    if not category_ids:
        return True

    try:
        # Remove duplicates
        unique_ids = list(dict.fromkeys(category_ids))
        records = [{"event_id": event_id, "category_id": cid} for cid in unique_ids]
        client.table("event_categories").insert(records).execute()
        return True
    except Exception as e:
        logger.warning("Failed to link categories", event_id=event_id, error=str(e))
        return False
