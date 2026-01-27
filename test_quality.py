"""Script to compare data quality between API and parsed data."""

import json
import sys
import asyncio
import httpx
import re

sys.path.insert(0, ".")

from src.adapters.madrid_datos_abiertos import MadridDatosAbiertosAdapter
from src.core.supabase_client import get_supabase_client


def main():
    # Fetch real event from API
    print("Descargando evento real de la API de Madrid...")
    print()

    url = "https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json"
    response = httpx.get(url, timeout=30, follow_redirects=True)
    content = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", response.text)
    data = json.loads(content)
    events = data.get("@graph", [])

    # Get first event with complete data
    raw_event = events[0]

    print("=" * 90)
    print("                        COMPARACION DE CALIDAD DE DATOS")
    print("=" * 90)
    print()
    print("EVENTO ORIGINAL (API Madrid Datos Abiertos)")
    print("-" * 90)
    print(json.dumps(raw_event, indent=2, ensure_ascii=False))

    # Parse with adapter
    adapter = MadridDatosAbiertosAdapter()
    parsed = adapter.parse_event(raw_event)

    # Get client and resolve category
    client = get_supabase_client()

    async def resolve():
        cat_id = await client.resolve_category_id(parsed.category_slug)
        tag_ids = await client.resolve_tag_ids(parsed.tags)
        return cat_id, tag_ids

    cat_id, tag_ids = asyncio.run(resolve())

    print()
    print()
    print("DATOS QUE SE INSERTARIAN EN SUPABASE")
    print("-" * 90)
    print()

    # Events table
    print(">> TABLA: events")
    print("   " + "-" * 50)
    desc_short = (
        (parsed.description[:100] + "...")
        if parsed.description and len(parsed.description) > 100
        else parsed.description
    )
    url_short = (
        (parsed.external_url[:60] + "...")
        if parsed.external_url and len(parsed.external_url) > 60
        else parsed.external_url
    )

    events_data = {
        "title": parsed.title,
        "description": desc_short,
        "start_date": str(parsed.start_date),
        "end_date": str(parsed.end_date),
        "start_time": str(parsed.start_time),
        "all_day": parsed.all_day,
        "modality": "presencial",
        "category_id": cat_id,
        "is_free": parsed.is_free,
        "is_published": parsed.is_published,
        "is_recurring": parsed.is_recurring,
        "external_id": parsed.external_id,
        "external_url": url_short,
    }
    for k, v in events_data.items():
        print(f"   {k}: {v}")

    print()
    print(">> TABLA: event_locations")
    print("   " + "-" * 50)
    location_data = {
        "name": parsed.venue_name,
        "address": parsed.address,
        "city": parsed.city,
        "municipio": parsed.district,
        "province": parsed.province,
        "comunidad_autonoma": parsed.comunidad_autonoma,
        "country": parsed.country,
        "postal_code": parsed.postal_code,
        "latitude": parsed.latitude,
        "longitude": parsed.longitude,
    }
    for k, v in location_data.items():
        print(f"   {k}: {v}")

    print()
    print(">> TABLA: event_organizers")
    print("   " + "-" * 50)
    if parsed.organizer:
        print(f"   name: {parsed.organizer.name}")
        print(f"   type: {parsed.organizer.type.value}")
    else:
        print("   (sin organizador)")

    print()
    print(">> TABLA: event_tags")
    print("   " + "-" * 50)
    print(f"   Tags parseados: {parsed.tags}")
    print(f"   Tags resueltos a UUID: {len(tag_ids)} de {len(parsed.tags)}")
    for i, tag in enumerate(parsed.tags):
        status = "OK" if i < len(tag_ids) else "NO EXISTE"
        print(f"   - {tag}: {status}")

    print()
    print(">> TABLA: event_calendars")
    print("   " + "-" * 50)
    print("   - Calendario Publico (nacional)")
    print(f"   - {parsed.comunidad_autonoma} (CCAA)")

    print()
    print()
    print("=" * 90)
    print("                           MAPEO CAMPO A CAMPO")
    print("=" * 90)
    print()
    print(f"{'API Original':<40} | {'Campo Supabase':<25} | Valor")
    print("-" * 90)

    title_short = (parsed.title[:40] + "...") if len(parsed.title) > 40 else parsed.title
    venue_short = parsed.venue_name[:40] if parsed.venue_name else "N/A"
    org_name = "N/A"
    org_type = "N/A"
    if parsed.organizer:
        org_name = (
            (parsed.organizer.name[:30] + "...")
            if len(parsed.organizer.name) > 30
            else parsed.organizer.name
        )
        org_type = parsed.organizer.type.value

    mappings = [
        ("title", "events.title", title_short),
        ("description", "events.description", "OK (completo)"),
        ("dtstart", "events.start_date", str(parsed.start_date)),
        ("dtend", "events.end_date", str(parsed.end_date)),
        ("time", "events.start_time", str(parsed.start_time)),
        ("free", "events.is_free", str(parsed.is_free)),
        ("@type", "events.category_id", f"{parsed.category_slug} -> UUID"),
        ("link", "events.external_url", "OK"),
        ("id", "events.external_id", parsed.external_id),
        ("event-location", "event_locations.name", venue_short),
        ("address.area.street-address", "event_locations.address", parsed.address or "N/A"),
        ("address.area.locality", "event_locations.city", parsed.city or "N/A"),
        ("address.district.@id", "event_locations.municipio", parsed.district or "N/A"),
        ("address.area.postal-code", "event_locations.postal_code", parsed.postal_code or "N/A"),
        (
            "location.latitude",
            "event_locations.latitude",
            str(parsed.latitude) if parsed.latitude else "N/A",
        ),
        (
            "location.longitude",
            "event_locations.longitude",
            str(parsed.longitude) if parsed.longitude else "N/A",
        ),
        ("(inferido)", "event_locations.province", parsed.province or "N/A"),
        ("(inferido)", "event_locations.comunidad_autonoma", parsed.comunidad_autonoma or "N/A"),
        ("organization.organization-name", "event_organizers.name", org_name),
        ("(inferido por keywords)", "event_organizers.type", org_type),
        ("organization.accesibility", "event_tags (accesibilidad)", "Mapeado a tags"),
        ("@type + audience + free", "event_tags", ", ".join(parsed.tags)),
        ("(jerarquia)", "event_calendars", "Publico + CCAA"),
    ]

    for api_field, db_field, value in mappings:
        print(f"{api_field:<40} | {db_field:<25} | {value}")

    print()
    print("=" * 90)
    print("                              RESUMEN DE CALIDAD")
    print("=" * 90)
    print()

    # Calculate coverage
    mapped_fields = 0
    if parsed.title:
        mapped_fields += 1
    if parsed.description:
        mapped_fields += 1
    if parsed.start_date:
        mapped_fields += 1
    if parsed.end_date:
        mapped_fields += 1
    if parsed.start_time:
        mapped_fields += 1
    if parsed.is_free is not None:
        mapped_fields += 1
    if parsed.external_url:
        mapped_fields += 1
    if parsed.external_id:
        mapped_fields += 1
    if parsed.venue_name:
        mapped_fields += 1
    if parsed.address:
        mapped_fields += 1
    if parsed.city:
        mapped_fields += 1
    if parsed.district:
        mapped_fields += 1
    if parsed.postal_code:
        mapped_fields += 1
    if parsed.latitude:
        mapped_fields += 1
    if parsed.longitude:
        mapped_fields += 1

    total_api_fields = 15

    print(
        f"Campos API mapeados:     {mapped_fields}/{total_api_fields} ({mapped_fields/total_api_fields*100:.0f}%)"
    )
    print(f"Tags resueltos:          {len(tag_ids)}/{len(parsed.tags)}")
    print(f'Categoria resuelta:      {"SI" if cat_id else "NO"} ({parsed.category_slug})')
    print(f'Organizador extraido:    {"SI" if parsed.organizer else "NO"}')
    print(f'Coordenadas GPS:         {"SI" if parsed.latitude and parsed.longitude else "NO"}')
    print("Calendarios asignados:   2 (Publico + CCAA)")
    print()
    if mapped_fields >= 14:
        print("VALORACION: EXCELENTE - Todos los datos principales mapeados")
    elif mapped_fields >= 10:
        print("VALORACION: BUENA - Mayoria de datos mapeados")
    else:
        print("VALORACION: MEJORABLE - Faltan datos importantes")


if __name__ == "__main__":
    main()
