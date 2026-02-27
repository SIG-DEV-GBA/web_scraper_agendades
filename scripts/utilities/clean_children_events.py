#!/usr/bin/env python3
"""Identify and optionally delete children-only events from production DB."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

from src.core.supabase_client import SupabaseClient
from src.core.category_classifier import is_children_only

client = SupabaseClient()

# Fetch all events
print("Fetching events from DB...")
all_events = []
offset = 0
PAGE = 1000
while True:
    result = client.client.table("events").select(
        "id,title,description,source_id"
    ).range(offset, offset + PAGE - 1).execute()
    if not result.data:
        break
    all_events.extend(result.data)
    if len(result.data) < PAGE:
        break
    offset += PAGE

print(f"Total events: {len(all_events)}")

# Source slug map
sources = client.client.table("scraper_sources").select("id,slug").execute()
src_map = {s["id"]: s["slug"] for s in sources.data}

# Run 2-layer filter
flagged = []
for e in all_events:
    title = e["title"] or ""
    desc = (e.get("description") or "")[:1500]
    source = src_map.get(e.get("source_id", ""), "?")

    if is_children_only(title, desc):
        flagged.append({
            "id": e["id"],
            "title": title[:70],
            "source": source,
        })

# Group by source
from collections import Counter
source_counts = Counter(f["source"] for f in flagged)

print(f"\nChildren-only events to remove: {len(flagged)}")
print(f"\nBy source:")
for src, count in source_counts.most_common():
    print(f"  {src:<30} {count}")

print(f"\n{'Title':<70} {'Source':<25}")
print("=" * 95)
for f in flagged:
    print(f"{f['title']:<70} {f['source']:<25}")

# Ask for confirmation
if "--delete" in sys.argv:
    print(f"\n--- DELETING {len(flagged)} events ---")
    ids = [f["id"] for f in flagged]
    # Delete in batches of 50
    deleted = 0
    for i in range(0, len(ids), 50):
        batch = ids[i:i+50]
        # Delete event_categories first (FK)
        client.client.table("event_categories").delete().in_("event_id", batch).execute()
        # Delete events
        client.client.table("events").delete().in_("id", batch).execute()
        deleted += len(batch)
        print(f"  Deleted {deleted}/{len(ids)}...")
    print(f"\nDone. Removed {deleted} children-only events.")
else:
    print(f"\nDry run. To delete, run: python scripts/utilities/clean_children_events.py --delete")
