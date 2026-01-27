"""Run Madrid scraper with 100 events limit."""

import asyncio
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import get_settings
from src.logging import setup_logging, get_logger

# Setup logging first
setup_logging(level="INFO", log_format="console")
logger = get_logger(__name__)


async def run_madrid_limited():
    """Run Madrid adapter with 100 events limit."""
    from src.adapters.madrid_datos_abiertos import MadridDatosAbiertosAdapter
    from src.core.supabase_client import get_supabase_client

    settings = get_settings()

    print("=" * 70)
    print("SCRAPER MADRID - 100 EVENTOS")
    print("=" * 70)
    print(f"\nDRY_RUN: {settings.dry_run}")
    print(f"LLM_ENABLED: {settings.llm_enabled}")
    print(f"UNSPLASH_ENABLED: {bool(settings.unsplash_access_key)}")

    # Create adapter
    adapter = MadridDatosAbiertosAdapter()

    print("\n[1] Descargando y enriqueciendo eventos...")

    # Fetch events (this triggers LLM enrichment)
    raw_events = await adapter.fetch_events()
    print(f"    Total eventos API: {len(raw_events)}")

    # Limit to 100
    raw_events = raw_events[:100]
    print(f"    Procesando: {len(raw_events)} eventos")

    # Re-enrich only these 100 (the full batch was enriched, we just parse 100)
    print("\n[2] Parseando eventos...")
    events = []
    for raw in raw_events:
        event = adapter.parse_event(raw)
        if event:
            events.append(event)

    print(f"    Eventos parseados: {len(events)}")

    # Show category distribution
    categories = {}
    for e in events:
        cat = e.category_slug or "unknown"
        categories[cat] = categories.get(cat, 0) + 1

    print("\n[3] Distribucion de categorias:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        pct = count / len(events) * 100
        bar = "#" * int(pct / 5)
        print(f"    {cat:12} {count:3} ({pct:4.0f}%) {bar}")

    # Show image stats
    with_image = sum(1 for e in events if e.source_image_url)
    with_author = sum(1 for e in events if e.image_author)
    print(f"\n[4] Imagenes:")
    print(f"    Con imagen: {with_image}/{len(events)}")
    print(f"    Con atribucion Unsplash: {with_author}/{len(events)}")

    # Insert to database
    if settings.dry_run:
        print("\n[5] DRY_RUN=true - No se insertaran eventos")
        print("    Para insertar, ejecuta: set DRY_RUN=false")
    else:
        print("\n[5] Insertando en Supabase...")
        db = get_supabase_client()

        inserted = 0
        skipped = 0
        errors = 0

        for event in events:
            try:
                # Check if exists
                exists = await db.event_exists(event.external_id)
                if exists:
                    skipped += 1
                    continue

                result = await db.insert_event(event)
                if result:
                    inserted += 1
                else:
                    errors += 1
            except Exception as e:
                logger.error("Insert error", error=str(e), title=event.title[:30])
                errors += 1

        print(f"    Insertados: {inserted}")
        print(f"    Skipped (ya existian): {skipped}")
        print(f"    Errores: {errors}")

    # Show sample event
    print("\n" + "=" * 70)
    print("EVENTO EJEMPLO")
    print("=" * 70)

    sample = events[0]
    print(f"""
Titulo: {sample.title}
Categoria: {sample.category_slug}
Fecha: {sample.start_date}
Lugar: {sample.venue_name or 'N/A'}
Gratis: {'Si' if sample.is_free else 'No'}
Tags: {sample.tags[:5]}

Imagen: {(sample.source_image_url or 'N/A')[:70]}...
Autor: {sample.image_author or 'N/A'}
""")

    print("=" * 70)
    print("COMPLETADO")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_madrid_limited())
