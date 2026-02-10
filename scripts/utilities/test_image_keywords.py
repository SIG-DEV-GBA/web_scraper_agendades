"""Test de generación de image_keywords con contexto regional."""

import json
from src.core.llm_enricher import get_llm_enricher, SourceTier

def test_regional_image_keywords():
    """Test que los image_keywords consideran la región."""

    # Eventos de prueba con diferentes regiones y temáticas
    test_events = [
        {
            "id": "test_1",
            "title": "Jornada de agricultura ecológica",
            "description": "Taller sobre técnicas de cultivo sostenible en la meseta castellana. Incluye visita a fincas locales.",
            "venue_name": "Casa de la Agricultura",
            "city": "Toledo",
            "province": "Toledo",
            "comunidad_autonoma": "Castilla-La Mancha",
        },
        {
            "id": "test_2",
            "title": "Vendimia tradicional",
            "description": "Participa en la recogida de uva y aprende sobre la elaboración del vino riojano.",
            "venue_name": "Bodega San Vicente",
            "city": "Haro",
            "province": "La Rioja",
            "comunidad_autonoma": "La Rioja",
        },
        {
            "id": "test_3",
            "title": "Festival de flamenco",
            "description": "Espectáculo de baile flamenco con artistas locales en el corazón de Triana.",
            "venue_name": "Casa de la Memoria",
            "city": "Sevilla",
            "province": "Sevilla",
            "comunidad_autonoma": "Andalucía",
        },
        {
            "id": "test_4",
            "title": "Romería de la Virgen del Rocío",
            "description": "Celebración tradicional con hermandades y carretas hacia la aldea del Rocío.",
            "venue_name": "Aldea del Rocío",
            "city": "Almonte",
            "province": "Huelva",
            "comunidad_autonoma": "Andalucía",
        },
        {
            "id": "test_5",
            "title": "Taller de cerámica talaverana",
            "description": "Aprende las técnicas tradicionales de la cerámica de Talavera, Patrimonio de la Humanidad.",
            "venue_name": "Escuela de Artesanía",
            "city": "Talavera de la Reina",
            "province": "Toledo",
            "comunidad_autonoma": "Castilla-La Mancha",
        },
        {
            "id": "test_6",
            "title": "Yoga al atardecer en la playa",
            "description": "Sesión de yoga con vistas al Mediterráneo. Todos los niveles bienvenidos.",
            "venue_name": "Playa de la Malvarrosa",
            "city": "Valencia",
            "province": "Valencia",
            "comunidad_autonoma": "Comunidad Valenciana",
        },
    ]

    enricher = get_llm_enricher()

    if not enricher.is_enabled:
        print("❌ LLM no configurado (GROQ_API_KEY o OLLAMA_URL)")
        return

    print("=" * 70)
    print("TEST: Generación de image_keywords con contexto regional")
    print("=" * 70)

    # Enriquecer eventos
    enrichments = enricher.enrich_batch(test_events, batch_size=10, tier=SourceTier.ORO)

    print("\nRESULTADOS:")
    print("-" * 70)

    for event in test_events:
        event_id = event["id"]
        enrichment = enrichments.get(event_id)

        print(f"\n>> {event['title']}")
        print(f"   Ubicacion: {event['city']}, {event['comunidad_autonoma']}")

        if enrichment:
            print(f"   Categorias: {enrichment.category_slugs}")
            print(f"   IMAGE_KEYWORDS: {enrichment.image_keywords}")

            # Verificar que no son keywords genéricas
            keywords_str = " ".join(enrichment.image_keywords).lower()
            if "spain" in keywords_str or "spanish" in keywords_str or "mediterranean" in keywords_str:
                print("   [OK] Contexto espanol detectado")
            elif "flamenco" in keywords_str or "andalus" in keywords_str or "castil" in keywords_str:
                print("   [OK] Contexto regional detectado")
            else:
                print("   [?] Sin contexto espanol explicito (revisar)")
        else:
            print("   [ERROR] Sin enriquecimiento")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    test_regional_image_keywords()
