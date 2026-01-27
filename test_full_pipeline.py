"""Test full pipeline with sample data (when Madrid API is down)."""

import asyncio
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.llm_enricher import get_llm_enricher
from src.core.image_resolver import get_image_resolver


# Sample events (simulating Madrid API data)
SAMPLE_EVENTS = [
    {
        "id": "50166245",
        "title": "Concierto de Jazz en el Retiro",
        "description": "Disfruta de una velada de jazz al aire libre en el Parque del Retiro. Big Band Madrid interpretara clasicos del jazz americano.",
        "@type": "https://datos.madrid.es/egob/kos/actividades/Musica",
        "audience": "Todos los publicos",
    },
    {
        "id": "50166246",
        "title": "Taller de Yoga y Meditacion",
        "description": "Sesion de yoga y mindfulness para reducir el estres. Aprende tecnicas de respiracion y relajacion.",
        "@type": "https://datos.madrid.es/egob/kos/actividades/CursosTalleres",
        "audience": "Adultos",
    },
    {
        "id": "50166247",
        "title": "Curso de Programacion Python",
        "description": "Introduccion a la programacion con Python. Aprende desde cero a crear tus propias aplicaciones.",
        "@type": "https://datos.madrid.es/egob/kos/actividades/CursosTalleres",
        "audience": "Jovenes y adultos",
    },
    {
        "id": "50166248",
        "title": "Mercadillo Solidario Navidad",
        "description": "Mercadillo benefico con productos artesanales. Todos los fondos se destinaran a familias necesitadas.",
        "@type": "https://datos.madrid.es/egob/kos/actividades/FiestasCarnavales",
        "audience": "Familiar",
    },
    {
        "id": "50166249",
        "title": "Exposicion: Arte Contemporaneo Espanol",
        "description": "Muestra de obras de artistas espanoles contemporaneos. Pintura, escultura e instalaciones.",
        "@type": "https://datos.madrid.es/egob/kos/actividades/Exposiciones",
        "audience": "Todos los publicos",
    },
    {
        "id": "50166250",
        "title": "Teatro Infantil: El Principito",
        "description": "Adaptacion teatral del clasico de Saint-Exupery para toda la familia.",
        "@type": "https://datos.madrid.es/egob/kos/actividades/TeatroPerformance",
        "audience": "Infantil",
    },
]


async def test_full_pipeline():
    print("=" * 70)
    print("PIPELINE COMPLETO - LLM Enricher + Unsplash")
    print("=" * 70)

    print(f"\n[1] Usando {len(SAMPLE_EVENTS)} eventos de ejemplo...")

    print("\n[2] Enriqueciendo con LLM...")
    enricher = get_llm_enricher()
    enrichments = enricher.enrich_batch(SAMPLE_EVENTS)
    print(f"    OK - {len(enrichments)} eventos enriquecidos")

    print("\n[3] Resolviendo imagenes con Unsplash...")
    resolver = get_image_resolver()

    results = []
    for raw in SAMPLE_EVENTS:
        event_id = str(raw.get("id", ""))
        title = raw.get("title", "")
        enrichment = enrichments.get(event_id)

        # Get category and image keywords
        if enrichment:
            category = enrichment.category_slug
            keywords = enrichment.image_keywords
            summary = enrichment.summary
        else:
            category = "cultural"
            keywords = resolver._generate_basic_image_keywords(raw)
            summary = None

        # Resolve image
        image = resolver.resolve_image_full(keywords, category)

        result = {
            "id": event_id,
            "title": title,
            "category": category,
            "summary": summary,
            "keywords": keywords,
            "image_url": image.url if image else resolver._get_fallback(category),
            "image_author": image.author if image else None,
            "image_author_url": image.author_url if image else None,
            "unsplash_url": image.unsplash_url if image else None,
        }
        results.append(result)

        # Trigger download if Unsplash image (required by API terms)
        if image:
            resolver.trigger_download(image)

    print(f"    OK - {len(results)} imagenes resueltas")

    print("\n" + "=" * 70)
    print("RESULTADOS")
    print("=" * 70)

    for i, r in enumerate(results, 1):
        print(f"\n--- Evento {i} ---")
        print(f"Titulo: {r['title']}")
        print(f"Categoria: {r['category']}")
        if r['summary']:
            print(f"Resumen: {r['summary']}")
        print(f"Keywords imagen: {r['keywords']}")
        print(f"Imagen URL: {r['image_url'][:70]}...")
        if r['image_author']:
            print(f"ATRIBUCION: Photo by {r['image_author']} on Unsplash")

    # Estadisticas
    print("\n" + "=" * 70)
    print("ESTADISTICAS")
    print("=" * 70)

    categories = {}
    for r in results:
        cat = r["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print("\nDistribucion por categoria:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        pct = count / len(results) * 100
        bar = "#" * int(pct / 5)
        print(f"  {cat:12} {count:2} ({pct:4.0f}%) {bar}")

    with_unsplash = sum(1 for r in results if r["image_author"])
    print(f"\nImagenes Unsplash: {with_unsplash}/{len(results)}")

    # Ejemplo para screenshot
    print("\n" + "=" * 70)
    print("EJEMPLO PARA SCREENSHOT")
    print("=" * 70)

    ex = results[0]
    print(f"""
EVENTO: {ex['title']}
CATEGORIA: {ex['category']}

IMAGEN URL:
{ex['image_url']}

ATRIBUCION (mostrar en tu app):
Photo by {ex['image_author']} on Unsplash

HTML de atribucion:
<small>Photo by <a href="{ex['image_author_url']}?utm_source=agendades&utm_medium=referral">{ex['image_author']}</a> on <a href="https://unsplash.com/?utm_source=agendades&utm_medium=referral">Unsplash</a></small>
""")

    print("=" * 70)
    print("\nPuedes abrir la URL de la imagen en el navegador para el screenshot!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
