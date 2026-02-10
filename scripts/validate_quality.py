#!/usr/bin/env python
"""Validate data quality of inserted events.

Checks field coverage and data quality against target metrics.

Usage:
    python scripts/validate_quality.py
    python scripts/validate_quality.py --source viralagenda_sevilla
    python scripts/validate_quality.py --recent 100
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.supabase_client import get_supabase_client


# Target coverage percentages (from ARQUITECTURA_DEFINITIVA.md)
QUALITY_TARGETS = {
    "description": 90,      # % eventos con description
    "image_url": 80,        # % eventos con image_url (source_image_url)
    "coordinates": 70,      # % eventos con latitude/longitude
    "category_slugs": 95,   # % eventos con categorias
    "organizer": 50,        # % eventos con organizer
    "contact": 30,          # % eventos con contact (email o phone)
    "registration_url": 20, # % eventos con registration_url
    "city": 95,             # % eventos con city
    "venue_name": 80,       # % eventos con venue_name
    "is_free": 70,          # % eventos con is_free definido (no null)
}


def validate_events(source_id: str | None = None, limit: int = 500) -> dict:
    """Validate event data quality.

    Args:
        source_id: Optional filter by source
        limit: Max events to check

    Returns:
        Dict with coverage stats and quality metrics
    """
    supabase = get_supabase_client()

    # Build query
    query = supabase.client.table("events").select(
        "id, title, description, summary, source_image_url, is_free, price, price_info, "
        "source_id, created_at"
    ).order("created_at", desc=True).limit(limit)

    if source_id:
        # Get source UUID from slug
        source_result = supabase.client.table("scraper_sources").select("id").eq("slug", source_id).single().execute()
        if source_result.data:
            query = query.eq("source_id", source_result.data["id"])

    events = query.execute().data

    if not events:
        return {"error": "No events found", "total": 0}

    total = len(events)
    event_ids = [e["id"] for e in events]

    # Get related data
    locations = {}
    loc_result = supabase.client.table("event_locations").select("*").in_("event_id", event_ids).execute()
    for loc in loc_result.data:
        locations[loc["event_id"]] = loc

    contacts = {}
    contact_result = supabase.client.table("event_contact").select("*").in_("event_id", event_ids).execute()
    for c in contact_result.data:
        contacts[c["event_id"]] = c

    organizers = {}
    org_result = supabase.client.table("event_organizers").select("*").in_("event_id", event_ids).execute()
    for o in org_result.data:
        organizers[o["event_id"]] = o

    categories = {}
    cat_result = supabase.client.table("event_categories").select("event_id, category_id").in_("event_id", event_ids).execute()
    for c in cat_result.data:
        if c["event_id"] not in categories:
            categories[c["event_id"]] = []
        categories[c["event_id"]].append(c["category_id"])

    registrations = {}
    reg_result = supabase.client.table("event_registration").select("*").in_("event_id", event_ids).execute()
    for r in reg_result.data:
        registrations[r["event_id"]] = r

    # Calculate coverage
    coverage = {
        "description": 0,
        "image_url": 0,
        "coordinates": 0,
        "category_slugs": 0,
        "organizer": 0,
        "contact": 0,
        "registration_url": 0,
        "city": 0,
        "venue_name": 0,
        "is_free": 0,
        "summary": 0,
        "price_info": 0,
    }

    # Track issues for debugging
    issues = {
        "no_description": [],
        "no_image": [],
        "no_coordinates": [],
        "no_category": [],
        "no_city": [],
    }

    for event in events:
        eid = event["id"]
        title = event.get("title", "")[:50]
        loc = locations.get(eid, {})
        contact = contacts.get(eid, {})
        org = organizers.get(eid)
        cats = categories.get(eid, [])
        reg = registrations.get(eid, {})

        # Check each field
        if event.get("description"):
            coverage["description"] += 1
        else:
            issues["no_description"].append(title)

        if event.get("source_image_url"):
            coverage["image_url"] += 1
        else:
            issues["no_image"].append(title)

        if loc.get("latitude") and loc.get("longitude"):
            coverage["coordinates"] += 1
        else:
            issues["no_coordinates"].append(title)

        if cats:
            coverage["category_slugs"] += 1
        else:
            issues["no_category"].append(title)

        if org:
            coverage["organizer"] += 1

        if contact.get("email") or contact.get("phone"):
            coverage["contact"] += 1

        if reg.get("registration_url"):
            coverage["registration_url"] += 1

        if loc.get("city"):
            coverage["city"] += 1
        else:
            issues["no_city"].append(title)

        if loc.get("name"):  # venue_name is stored as 'name' in event_locations
            coverage["venue_name"] += 1

        if event.get("is_free") is not None:
            coverage["is_free"] += 1

        if event.get("summary"):
            coverage["summary"] += 1

        if event.get("price_info"):
            coverage["price_info"] += 1

    # Calculate percentages
    percentages = {k: round(v / total * 100, 1) for k, v in coverage.items()}

    # Check against targets
    results = {
        "total_events": total,
        "coverage": coverage,
        "percentages": percentages,
        "targets": QUALITY_TARGETS,
        "status": {},
        "issues": {k: v[:5] for k, v in issues.items()},  # First 5 issues
    }

    # Determine pass/fail for each metric
    all_pass = True
    for metric, target in QUALITY_TARGETS.items():
        actual = percentages.get(metric, 0)
        passed = actual >= target
        results["status"][metric] = {
            "target": target,
            "actual": actual,
            "passed": passed,
            "diff": round(actual - target, 1),
        }
        if not passed:
            all_pass = False

    results["all_passed"] = all_pass

    return results


def safe_print(text: str):
    """Print text, replacing non-encodable characters."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def print_report(results: dict, source_id: str | None = None):
    """Print a formatted quality report."""
    if results.get("error"):
        print(f"Error: {results['error']}")
        return

    print("=" * 70)
    print("DATA QUALITY REPORT")
    print("=" * 70)
    if source_id:
        print(f"Source: {source_id}")
    print(f"Events analyzed: {results['total_events']}")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("-" * 70)

    # Coverage table
    print("\n{:<20} {:>10} {:>10} {:>10} {:>10}".format(
        "METRIC", "COUNT", "ACTUAL %", "TARGET %", "STATUS"
    ))
    print("-" * 70)

    for metric in QUALITY_TARGETS.keys():
        status = results["status"].get(metric, {})
        count = results["coverage"].get(metric, 0)
        actual = status.get("actual", 0)
        target = status.get("target", 0)
        passed = status.get("passed", False)

        status_str = "[OK]" if passed else "[FAIL]"
        diff = status.get("diff", 0)
        diff_str = f"+{diff}" if diff >= 0 else str(diff)

        print("{:<20} {:>10} {:>9}% {:>9}% {:>10} ({})".format(
            metric, count, actual, target, status_str, diff_str
        ))

    # Extra metrics (no target)
    print("-" * 70)
    print("Additional metrics (no target):")
    for metric in ["summary", "price_info"]:
        if metric in results["percentages"]:
            count = results["coverage"].get(metric, 0)
            pct = results["percentages"].get(metric, 0)
            print(f"  {metric}: {count} ({pct}%)")

    # Overall status
    print("\n" + "=" * 70)
    if results["all_passed"]:
        print("OVERALL: [PASS] All quality targets met!")
    else:
        failed = [m for m, s in results["status"].items() if not s.get("passed")]
        print(f"OVERALL: [FAIL] {len(failed)} metrics below target")
        print(f"  Failed: {', '.join(failed)}")
    print("=" * 70)

    # Show sample issues
    issues = results.get("issues", {})
    if any(issues.values()):
        print("\nSAMPLE ISSUES (first 5 each):")
        for issue_type, items in issues.items():
            if items:
                print(f"\n  {issue_type}:")
                for item in items[:3]:
                    safe_print(f"    - {item}")


def main():
    parser = argparse.ArgumentParser(description="Validate event data quality")
    parser.add_argument(
        "--source", "-s",
        help="Filter by source slug (e.g., viralagenda_sevilla)",
    )
    parser.add_argument(
        "--recent", "-r",
        type=int,
        default=500,
        help="Number of recent events to check (default: 500)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of formatted report",
    )

    args = parser.parse_args()

    results = validate_events(
        source_id=args.source,
        limit=args.recent,
    )

    if args.json:
        import json
        print(json.dumps(results, indent=2, default=str))
    else:
        print_report(results, args.source)


if __name__ == "__main__":
    main()
