#!/usr/bin/env python
"""Backfill missing coordinates for existing events using Nominatim geocoding.

Usage:
    python backfill_coordinates.py              # Process all without coordinates
    python backfill_coordinates.py --limit 10   # Process only 10
    python backfill_coordinates.py --dry-run    # Test without updating
"""

import argparse
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.geocoder import get_geocoder
from src.core.supabase_client import get_supabase_client
from src.logging.logger import get_logger

logger = get_logger(__name__)

# Terminal colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def get_locations_without_coords(client, limit: int | None = None) -> list[dict]:
    """Get event_locations without latitude/longitude."""
    query = (
        client.client.table("event_locations")
        .select("event_id, name, address, city, province, postal_code, comunidad_autonoma")
        .is_("latitude", "null")
    )

    if limit:
        query = query.limit(limit)

    result = query.execute()
    return result.data


async def update_location_coords(
    client, event_id: str, latitude: float, longitude: float
) -> bool:
    """Update coordinates for a location."""
    try:
        client.client.table("event_locations").update(
            {"latitude": latitude, "longitude": longitude}
        ).eq("event_id", event_id).execute()
        return True
    except Exception as e:
        logger.warning("update_failed", event_id=event_id, error=str(e))
        return False


async def main():
    parser = argparse.ArgumentParser(description="Backfill missing coordinates")
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Limit number of locations to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test without updating database",
    )

    args = parser.parse_args()

    print(f"\n{'#'*60}")
    print(f"# {BOLD}COORDINATE BACKFILL{RESET}")
    print(f"# Limit: {args.limit or 'all'}, Dry run: {args.dry_run}")
    print(f"{'#'*60}\n")

    client = get_supabase_client()
    geocoder = get_geocoder()

    # Get locations without coordinates
    print("Fetching locations without coordinates...")
    locations = await get_locations_without_coords(client, args.limit)
    print(f"Found: {len(locations)} locations to geocode\n")

    if not locations:
        print(f"{GREEN}All locations already have coordinates!{RESET}")
        return

    # Process each location
    success = 0
    failed = 0
    skipped = 0

    for i, loc in enumerate(locations):
        event_id = loc["event_id"]
        city = loc.get("city") or ""
        name = loc.get("name") or ""
        address = loc.get("address") or ""

        print(f"[{i+1}/{len(locations)}] {city}: {name[:40]}...", end=" ")

        # Geocode
        result = await geocoder.geocode(
            venue_name=loc.get("name"),
            address=loc.get("address"),
            city=loc.get("city"),
            province=loc.get("province"),
            postal_code=loc.get("postal_code"),
            comunidad_autonoma=loc.get("comunidad_autonoma"),
        )

        if not result:
            print(f"{RED}NOT FOUND{RESET}")
            failed += 1
            continue

        if args.dry_run:
            print(f"{YELLOW}DRY RUN{RESET} ({result.latitude:.4f}, {result.longitude:.4f})")
            skipped += 1
            continue

        # Update database
        updated = await update_location_coords(
            client, event_id, result.latitude, result.longitude
        )

        if updated:
            print(f"{GREEN}OK{RESET} ({result.latitude:.4f}, {result.longitude:.4f})")
            success += 1
        else:
            print(f"{RED}UPDATE FAILED{RESET}")
            failed += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"{BOLD}SUMMARY{RESET}")
    print(f"{'='*60}")
    print(f"  Total processed: {len(locations)}")
    print(f"  {GREEN}Geocoded & updated: {success}{RESET}")
    print(f"  {RED}Failed to geocode: {failed}{RESET}")
    if args.dry_run:
        print(f"  {YELLOW}Skipped (dry run): {skipped}{RESET}")

    # Cleanup
    await geocoder.close()


if __name__ == "__main__":
    asyncio.run(main())
