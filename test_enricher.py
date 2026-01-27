"""Test script for LLM enricher and image resolver."""

import asyncio
import json
import os
import re
import sys

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.llm_enricher import get_llm_enricher, DB_CATEGORIES
from src.core.image_resolver import get_image_resolver, FALLBACK_IMAGES


def test_obvious_categories():
    """Test that obvious categories are detected without LLM."""
    enricher = get_llm_enricher()

    test_events = [
        {"id": "1", "title": "Taller de yoga para mayores", "description": "Sesión de yoga y meditación para personas mayores de 65 años"},
        {"id": "2", "title": "Curso de Python para principiantes", "description": "Aprende programación en Python desde cero"},
        {"id": "3", "title": "Concierto de música clásica", "description": "Orquesta sinfónica interpreta obras de Beethoven"},
        {"id": "4", "title": "Banco de alimentos solidario", "description": "Recogida de alimentos para familias necesitadas"},
        {"id": "5", "title": "Taller de primeros auxilios", "description": "Aprende técnicas básicas de primeros auxilios y RCP"},
        {"id": "6", "title": "Curso de Arduino y robótica", "description": "Introducción a la electrónica y robótica con Arduino"},
    ]

    print("=" * 60)
    print("TEST 1: Detección de categorías obvias (sin LLM)")
    print("=" * 60)

    for event in test_events:
        obvious = enricher._is_category_obvious(event)
        print(f"\n{event['title'][:50]}")
        print(f"  → Categoría obvia: {obvious or 'NO (necesita LLM)'}")

    print("\n")


def test_image_keywords():
    """Test image keyword generation."""
    resolver = get_image_resolver()

    test_events = [
        {"@type": "https://datos.madrid.es/egob/kos/actividades/TeatroPerformance"},
        {"@type": "https://datos.madrid.es/egob/kos/actividades/Musica"},
        {"@type": "https://datos.madrid.es/egob/kos/actividades/Exposiciones"},
        {"@type": "https://datos.madrid.es/egob/kos/actividades/CursosTalleres"},
        {"@type": ""},  # No type
    ]

    print("=" * 60)
    print("TEST 2: Generación de keywords para imágenes")
    print("=" * 60)

    for event in test_events:
        keywords = resolver._generate_basic_image_keywords(event)
        type_name = event.get("@type", "").split("/")[-1] if event.get("@type") else "N/A"
        print(f"\nTipo: {type_name}")
        print(f"  → Keywords: {keywords}")

    print("\n")


def test_fallback_images():
    """Test fallback images by category."""
    resolver = get_image_resolver()

    print("=" * 60)
    print("TEST 3: Imágenes fallback por categoría")
    print("=" * 60)

    for category in DB_CATEGORIES.keys():
        url = resolver._get_fallback(category)
        print(f"\n{category}:")
        print(f"  → {url[:60]}...")

    print("\n")


async def test_real_api():
    """Test with real Madrid API data (small sample)."""
    import httpx

    print("=" * 60)
    print("TEST 4: Datos reales de API Madrid (muestra)")
    print("=" * 60)

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json",
                timeout=30
            )
            content = response.text
            # Clean invalid control characters
            content = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', content)
            data = json.loads(content)

            events = data.get("@graph", [])[:10]  # Solo 10 eventos de muestra

            print(f"\nDescargados {len(events)} eventos de muestra")

            enricher = get_llm_enricher()
            resolver = get_image_resolver()

            print("\nAnalizando eventos:")
            print("-" * 40)

            for event in events:
                event_id = event.get("id", "")
                title = event.get("title", "")[:50]
                type_name = event.get("@type", "").split("/")[-1] if event.get("@type") else "N/A"

                # Check obvious category
                obvious = enricher._is_category_obvious(event)

                # Get image keywords
                keywords = resolver._generate_basic_image_keywords(event)

                print(f"\n[{event_id}] {title}")
                print(f"  Tipo API: {type_name}")
                print(f"  Categoría obvia: {obvious or 'necesita LLM'}")
                print(f"  Keywords imagen: {keywords}")

    except Exception as e:
        print(f"Error: {e}")

    print("\n")


def test_llm_batch():
    """Test LLM batch enrichment (requires GROQ_API_KEY)."""
    enricher = get_llm_enricher()

    print("=" * 60)
    print("TEST 5: Enrichment con LLM (batch)")
    print("=" * 60)

    if not enricher.is_enabled:
        print("\n⚠️  LLM no habilitado. Configura:")
        print("   - LLM_ENABLED=true")
        print("   - GROQ_API_KEY=tu_api_key")
        print("\nSkipping LLM test.\n")
        return

    # Eventos que necesitan LLM (no son obvios)
    test_events = [
        {
            "id": "test1",
            "title": "Taller de escritura creativa",
            "description": "Aprende técnicas de escritura creativa y storytelling. Ejercicios prácticos para desarrollar tu creatividad literaria.",
            "@type": "CursosTalleres",
            "audience": "Adultos"
        },
        {
            "id": "test2",
            "title": "Charla: Alimentación saludable",
            "description": "Conferencia sobre nutrición equilibrada y hábitos alimentarios saludables. Impartida por nutricionistas profesionales.",
            "@type": "ConferenciasColoquios",
            "audience": "Todos los públicos"
        },
        {
            "id": "test3",
            "title": "Festival de cortometrajes independientes",
            "description": "Proyección de los mejores cortometrajes de directores independientes. Votación del público.",
            "@type": "CineActividadesAudiovisuales",
            "audience": "Adultos"
        },
    ]

    print(f"\nProcesando {len(test_events)} eventos con LLM...")

    enrichments = enricher.enrich_batch(test_events, batch_size=10)

    print(f"\nResultados ({len(enrichments)} enriquecidos):")
    print("-" * 40)

    for event_id, enrichment in enrichments.items():
        print(f"\n[{event_id}]")
        print(f"  Categoría: {enrichment.category_slug}")
        print(f"  Confianza: {enrichment.confidence}")
        print(f"  Resumen: {enrichment.summary}")
        print(f"  Tags: {enrichment.tags}")
        print(f"  Keywords imagen: {enrichment.image_keywords}")
        print(f"  Edad: {enrichment.age_range}")

    print("\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("TESTS DEL SISTEMA DE ENRICHMENT INTELIGENTE")
    print("=" * 60 + "\n")

    # Tests síncronos
    test_obvious_categories()
    test_image_keywords()
    test_fallback_images()

    # Test asíncrono
    asyncio.run(test_real_api())

    # Test LLM (requiere API key)
    test_llm_batch()

    print("=" * 60)
    print("TESTS COMPLETADOS")
    print("=" * 60)
