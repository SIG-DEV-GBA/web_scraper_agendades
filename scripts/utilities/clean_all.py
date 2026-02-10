#!/usr/bin/env python3
"""Clean all events from database."""
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.core.supabase_client import SupabaseClient

def main():
    client = SupabaseClient()

    # Count before
    result = client.client.table("events").select("id", count="exact").execute()
    print(f"Events before: {result.count}")

    # Delete all
    if result.count > 0:
        client.client.table("events").delete().neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()
        print("All events deleted!")

    # Count after
    result = client.client.table("events").select("id", count="exact").execute()
    print(f"Events after: {result.count}")


if __name__ == "__main__":
    main()
