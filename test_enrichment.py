"""Test script for LLM enrichment with multiple categories."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_settings
from src.logging import setup_logging
from src.core.llm_enricher import get_llm_enricher, SourceTier


def test_enrichment():
    """Test LLM enrichment with sample events."""
    setup_logging(level="INFO")

    enricher = get_llm_enricher()

    if not enricher.is_enabled:
        print("LLM enrichment is disabled. Set GROQ_API_KEY in .env")
        return

    # Sample events for testing
    test_events = [
        {
            "id": "test_1",
            "title": "Concierto de la Orquesta Sinfónica",
            "description": "Disfruta de un programa dedicado a Beethoven y Mozart interpretado por la Orquesta Sinfónica Nacional.",
            "@type": "MusicaClasica",
            "audience": "todos",
            "price_info": "15€ (reducida 10€, socios gratis)",
        },
        {
            "id": "test_2",
            "title": "Taller de Emprendimiento Social",
            "description": "Aprende a crear proyectos de impacto social mientras desarrollas habilidades empresariales. Incluye networking y mentorías.",
            "@type": "Taller",
            "audience": "adultos",
            "price_info": "Gratuito con inscripción previa",
        },
        {
            "id": "test_3",
            "title": "Yoga y Meditación para Mayores",
            "description": "Sesión de yoga adaptado y meditación guiada para personas mayores de 65 años. Mejora tu bienestar físico y mental.",
            "@type": "ActividadSalud",
            "audience": "mayores",
            "price_info": "5€",
        },
        {
            "id": "test_4",
            "title": "Hackathon de Inteligencia Artificial",
            "description": "48 horas para desarrollar soluciones de IA. Premios para los mejores proyectos. Comida y bebida incluida.",
            "@type": "Tecnologia",
            "audience": "adultos",
            "price_info": "25€ (estudiantes 15€)",
        },
        {
            "id": "test_5",
            "title": "Mercadillo Solidario de Navidad",
            "description": "Compra regalos artesanales mientras ayudas a familias necesitadas. Organizado por voluntarios del barrio.",
            "@type": "EventoSocial",
            "audience": "familiar",
            "price_info": "Entrada gratuita",
        },
    ]

    print("\n" + "="*60)
    print("Testing LLM Enrichment with Multiple Categories")
    print("="*60 + "\n")

    enrichments = enricher.enrich_batch(test_events, batch_size=5, tier=SourceTier.ORO)

    print("\nResults:")
    print("-"*60)

    for event in test_events:
        event_id = event["id"]
        enrichment = enrichments.get(event_id)

        print(f"\n[EVENT] {event['title']}")
        print(f"   Original price_info: {event['price_info']}")

        if enrichment:
            print(f"   [OK] Categories: {', '.join(enrichment.category_slugs)}")
            print(f"   Summary: {enrichment.summary or '(none)'}")
            print(f"   Price: {enrichment.price} EUR" if enrichment.price else "   Price: (free/not specified)")
            print(f"   Price details: {enrichment.price_details or '(none)'}")
            print(f"   Image keywords: {enrichment.image_keywords}")
            print(f"   Age range: {enrichment.age_range}")
        else:
            print(f"   [ERROR] No enrichment returned")

    print("\n" + "="*60)
    print("Test completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_enrichment()
