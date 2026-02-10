#!/usr/bin/env python3
"""Analyze field coverage for each Gold source vs seed template."""
import asyncio
import sys
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter, GOLD_SOURCES

# Fields from seed-full-event.mjs that we SHOULD extract
SEED_FIELDS = {
    "events": [
        "title", "description", "summary", "image_url", "external_url",
        "start_date", "end_date", "start_time", "end_time", "all_day",
        "modality", "is_free", "price", "price_info"
    ],
    "event_locations": [
        "name", "address", "city", "province", "postal_code", "country",
        "comunidad_autonoma", "municipio", "latitude", "longitude", "details"
    ],
    "event_online": ["url", "platform", "access_info"],
    "event_organizers": ["name", "type", "url", "logo_url"],
    "event_contact": ["name", "email", "phone", "info"],
    "event_registration": [
        "requires_registration", "max_attendees", "registration_url",
        "registration_deadline", "waiting_list"
    ],
    "event_accessibility": [
        "wheelchair_accessible", "sign_language", "hearing_loop",
        "braille_materials", "other_facilities", "notes"
    ]
}

# Map EventCreate fields to seed table/fields
EVENTCREATE_MAPPING = {
    "title": ("events", "title"),
    "description": ("events", "description"),
    "summary": ("events", "summary"),
    "source_image_url": ("events", "image_url"),
    "external_url": ("events", "external_url"),
    "start_date": ("events", "start_date"),
    "end_date": ("events", "end_date"),
    "start_time": ("events", "start_time"),
    "end_time": ("events", "end_time"),
    "all_day": ("events", "all_day"),
    "location_type": ("events", "modality"),
    "is_free": ("events", "is_free"),
    "price": ("events", "price"),
    "price_info": ("events", "price_info"),
    "venue_name": ("event_locations", "name"),
    "address": ("event_locations", "address"),
    "city": ("event_locations", "city"),
    "province": ("event_locations", "province"),
    "postal_code": ("event_locations", "postal_code"),
    "country": ("event_locations", "country"),
    "comunidad_autonoma": ("event_locations", "comunidad_autonoma"),
    "district": ("event_locations", "municipio"),
    "latitude": ("event_locations", "latitude"),
    "longitude": ("event_locations", "longitude"),
    "online_url": ("event_online", "url"),
    "organizer.name": ("event_organizers", "name"),
    "organizer.type": ("event_organizers", "type"),
    "organizer.url": ("event_organizers", "url"),
    "organizer.logo_url": ("event_organizers", "logo_url"),
    "registration_url": ("event_registration", "registration_url"),
    "accessibility.wheelchair_accessible": ("event_accessibility", "wheelchair_accessible"),
    "accessibility.sign_language": ("event_accessibility", "sign_language"),
    "accessibility.hearing_loop": ("event_accessibility", "hearing_loop"),
    "accessibility.braille_materials": ("event_accessibility", "braille_materials"),
    "accessibility.other_facilities": ("event_accessibility", "other_facilities"),
    "accessibility.notes": ("event_accessibility", "notes"),
    "contact.email": ("event_contact", "email"),
    "contact.phone": ("event_contact", "phone"),
}


async def analyze_source(source_id: str):
    """Analyze field coverage for a single source."""
    print(f"\n{'='*70}")
    print(f"SOURCE: {source_id}")
    print("=" * 70)

    try:
        adapter = GoldAPIAdapter(source_id)
        raw_events = await adapter.fetch_events(max_pages=1)

        if not raw_events:
            print("  No events fetched")
            return {}

        # Parse first 5 events and collect filled fields
        filled_fields = set()
        sample_values = {}

        for raw in raw_events[:5]:
            event = adapter.parse_event(raw)
            if not event:
                continue

            # Check each field
            for field_name in EVENTCREATE_MAPPING.keys():
                if "." in field_name:
                    # Nested field like organizer.name
                    parts = field_name.split(".")
                    obj = getattr(event, parts[0], None)
                    if obj:
                        val = getattr(obj, parts[1], None)
                        if val is not None and val != "" and val != []:
                            filled_fields.add(field_name)
                            if field_name not in sample_values:
                                sample_values[field_name] = str(val)[:50]
                else:
                    val = getattr(event, field_name, None)
                    if val is not None and val != "" and val != []:
                        filled_fields.add(field_name)
                        if field_name not in sample_values:
                            sample_values[field_name] = str(val)[:50]

        # Group by table and show coverage
        tables_coverage = {}
        for table, fields in SEED_FIELDS.items():
            table_filled = []
            table_missing = []

            for field in fields:
                # Find matching EventCreate field
                matched = False
                for ec_field, (t, f) in EVENTCREATE_MAPPING.items():
                    if t == table and f == field:
                        if ec_field in filled_fields:
                            table_filled.append(f"{field}")
                            matched = True
                        break
                if not matched:
                    table_missing.append(field)

            if table_filled or table_missing:
                tables_coverage[table] = {
                    "filled": table_filled,
                    "missing": table_missing,
                    "pct": len(table_filled) / len(fields) * 100 if fields else 0
                }

        # Print results
        total_filled = 0
        total_fields = 0
        for table, data in tables_coverage.items():
            total_filled += len(data["filled"])
            total_fields += len(data["filled"]) + len(data["missing"])

            filled_str = ", ".join(data["filled"]) if data["filled"] else "ninguno"
            missing_str = ", ".join(data["missing"]) if data["missing"] else "ninguno"

            print(f"\n  {table}: {data['pct']:.0f}%")
            print(f"    ✓ Tiene: {filled_str}")
            if data["missing"]:
                print(f"    ✗ Falta: {missing_str}")

        overall = total_filled / total_fields * 100 if total_fields else 0
        print(f"\n  TOTAL: {overall:.0f}% ({total_filled}/{total_fields} campos)")

        return {"source": source_id, "coverage": overall, "tables": tables_coverage}

    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {str(e)[:80]}")
        return {}


async def show_raw_sample(source_id: str):
    """Show raw API data sample to identify available fields."""
    print(f"\n{'='*70}")
    print(f"RAW DATA SAMPLE: {source_id}")
    print("=" * 70)

    try:
        adapter = GoldAPIAdapter(source_id)
        raw_events = await adapter.fetch_events(max_pages=1)

        if raw_events:
            # Show first event's raw keys
            first = raw_events[0]

            # For Andalucía, preprocess first
            if source_id == "andalucia_agenda":
                first = adapter._preprocess_andalucia(first)

            if isinstance(first, dict):
                print(f"\n  Campos disponibles ({len(first)} keys):")
                for key in sorted(first.keys())[:30]:
                    val = first[key]
                    val_preview = str(val)[:60] if val else "null"
                    print(f"    {key}: {val_preview}")

    except Exception as e:
        print(f"  ERROR: {e}")


async def main():
    print("=" * 70)
    print("ANÁLISIS DE COBERTURA DE CAMPOS vs SEED TEMPLATE")
    print("=" * 70)

    results = []
    for source_id in GOLD_SOURCES.keys():
        result = await analyze_source(source_id)
        if result:
            results.append(result)

    # Summary
    print("\n" + "=" * 70)
    print("RESUMEN DE COBERTURA")
    print("=" * 70)
    for r in sorted(results, key=lambda x: x.get("coverage", 0), reverse=True):
        print(f"  {r['source']}: {r['coverage']:.0f}%")

    # Show what fields are NEVER extracted from any source
    print("\n" + "=" * 70)
    print("CAMPOS DEL SEED QUE NUNCA SE EXTRAEN")
    print("=" * 70)
    never_extracted = {
        "event_locations": ["details"],
        "event_online": ["platform", "access_info"],
        "event_contact": ["name", "email", "phone", "info"],
        "event_registration": ["requires_registration", "max_attendees", "registration_deadline", "waiting_list"],
    }
    for table, fields in never_extracted.items():
        print(f"  {table}: {', '.join(fields)}")


if __name__ == "__main__":
    asyncio.run(main())
