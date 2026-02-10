#!/usr/bin/env python3
"""Check events in database."""
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.core.supabase_client import SupabaseClient

def main():
    client = SupabaseClient()

    # Get total count
    total = client.client.table("events").select("id", count="exact").execute()
    print(f"Total events in DB: {total.count}")

    # Get sample events
    sample = client.client.table("events").select(
        "id,title,external_id,ccaa,province"
    ).limit(15).execute()

    print("\nSample events:")
    for e in sample.data:
        print(f"  - {e.get('external_id', 'N/A')[:50]}...")
        print(f"    Title: {e.get('title', 'N/A')[:40]}")
        print(f"    CCAA: {e.get('ccaa')} / {e.get('province')}")
        print()

    # Check Canarias specifically
    canarias = client.client.table("events").select(
        "id,title,external_id", count="exact"
    ).eq("ccaa", "Canarias").limit(5).execute()

    print(f"\nCanarias events: {canarias.count}")
    for e in canarias.data:
        print(f"  - {e.get('external_id', 'N/A')}")


if __name__ == "__main__":
    main()
