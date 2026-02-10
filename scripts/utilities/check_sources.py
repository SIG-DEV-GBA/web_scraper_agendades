#!/usr/bin/env python3
"""Check DB state and configured sources."""
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.core.supabase_client import SupabaseClient

def main():
    client = SupabaseClient()

    # Count current events
    result = client.client.table("events").select("id", count="exact").execute()
    print(f"Events in DB: {result.count}")

    # List sources
    sources = client.client.table("scraper_sources").select(
        "slug,name,adapter_type,is_active,ccaa"
    ).order("adapter_type").execute()

    print("\nConfigured sources:")
    current_type = None
    for s in sources.data:
        if s["adapter_type"] != current_type:
            current_type = s["adapter_type"]
            print(f"\n  [{current_type.upper()}]")
        status = "✓" if s["is_active"] else "✗"
        print(f"    {status} {s['slug']}: {s['ccaa']}")


if __name__ == "__main__":
    main()
