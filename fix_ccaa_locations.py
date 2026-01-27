#!/usr/bin/env python
"""Fix CCAA and coordinates for locations with mismatched cities.

This script:
1. Finds locations where the city doesn't match the CCAA
2. Uses the CCAA API to resolve the correct CCAA
3. Re-geocodes if coordinates are wrong
4. Updates the database
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.geocoder import get_geocoder
from src.core.supabase_client import get_supabase_client
from src.logging.logger import get_logger

logger = get_logger(__name__)


async def main():
    print("=" * 60)
    print("FIX CCAA LOCATIONS")
    print("=" * 60)

    client = get_supabase_client()
    geocoder = get_geocoder()

    # Get all locations
    result = client.client.table("event_locations").select(
        "event_id, city, comunidad_autonoma, latitude, longitude"
    ).execute()

    locations = result.data
    print(f"Total locations: {len(locations)}")

    fixed = 0
    regeocoded = 0

    for loc in locations:
        event_id = loc["event_id"]
        city = loc.get("city") or ""
        current_ccaa = loc.get("comunidad_autonoma") or ""
        lat = loc.get("latitude")
        lon = loc.get("longitude")

        if not city:
            continue

        # Resolve correct CCAA for this city
        correct_ccaa = await geocoder._resolve_ccaa(city)

        if not correct_ccaa:
            continue

        # Check if CCAA needs correction
        ccaa_mismatch = correct_ccaa.lower() != current_ccaa.lower()

        if ccaa_mismatch:
            print(f"\n{city}: {current_ccaa} -> {correct_ccaa}")

            # Re-geocode to get correct coordinates
            geo_result = await geocoder.geocode(city=city)

            update_data = {"comunidad_autonoma": correct_ccaa}

            if geo_result:
                # Check if coordinates changed significantly (> 1 degree = wrong city)
                if lat and lon:
                    lat_diff = abs(geo_result.latitude - lat)
                    lon_diff = abs(geo_result.longitude - lon)
                    if lat_diff > 1 or lon_diff > 1:
                        print(f"  Coords changed: ({lat:.2f}, {lon:.2f}) -> ({geo_result.latitude:.2f}, {geo_result.longitude:.2f})")
                        update_data["latitude"] = geo_result.latitude
                        update_data["longitude"] = geo_result.longitude
                        regeocoded += 1
                else:
                    update_data["latitude"] = geo_result.latitude
                    update_data["longitude"] = geo_result.longitude

            # Update database
            try:
                client.client.table("event_locations").update(update_data).eq("event_id", event_id).execute()
                print(f"  Updated!")
                fixed += 1
            except Exception as e:
                print(f"  ERROR: {e}")

    await geocoder.close()

    print("\n" + "=" * 60)
    print(f"Fixed CCAA: {fixed}")
    print(f"Re-geocoded: {regeocoded}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
