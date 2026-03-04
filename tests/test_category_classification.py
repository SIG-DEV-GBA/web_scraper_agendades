"""Integration test: verify LLM category classification accuracy.

Tests the LLM classifier against a curated set of edge-case events,
covering historically problematic classifications.
Requires GROQ_API_KEY in .env.
"""
import os
import pytest
import dotenv

dotenv.load_dotenv()

# Skip entire module if no GROQ_API_KEY
pytestmark = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set",
)

from src.core.category_classifier import CategoryClassifier


@pytest.fixture(scope="module")
def classifier():
    """Shared classifier instance for all tests."""
    return CategoryClassifier()


# =====================================================================
# Test data: 20 curated events — edge cases and historically problematic
# (title, source_context, expected_category)
# =====================================================================

CLASSIFICATION_EVENTS = [
    # --- SANITARIA: ejercicio en centros de mayores (NO cultural) ---
    ("Baile Zumba", "Ayuntamiento de Oviedo - actividades para personas mayores", "sanitaria"),
    ("Gerontogimnasia", "Ayuntamiento de Oviedo - actividades para personas mayores", "sanitaria"),
    ("Escuela De Espalda", "Ayuntamiento de Oviedo - actividades para personas mayores", "sanitaria"),
    ("Alzheimer y tecnología", "Puntos Vuela - centros de inclusion digital en Andalucia", "sanitaria"),

    # --- ECONOMICA: empleo/finanzas en centros tech (NO tecnologia) ---
    ("Búsqueda activa de empleo", "Puntos Vuela - centros de inclusion digital en Andalucia", "economica"),
    ("Educación financiera básica para empezar con buen pie", "Puntos Vuela - centros de inclusion digital en Andalucia", "economica"),
    ("Operaciones básicas en caja", "CeMIT - centros de inclusion tecnologica de Galicia", "economica"),
    ("Foro de Empleo UCMpleo26", "Tourempleo - ferias de empleo", "economica"),

    # --- TECNOLOGIA: realmente tech ---
    ("Ciberseguridad ¿sabes qué es?", "Puntos Vuela - centros de inclusion digital en Andalucia", "tecnologia"),
    ("Iniciación a la Informática", "CeMIT - centros de inclusion tecnologica de Galicia", "tecnologia"),
    ("Inteligencia artificial y deepfakes: riesgos y prevención", "Puntos Vuela - centros de inclusion digital en Andalucia", "tecnologia"),

    # --- CULTURAL: espectáculos, arte, conciertos ---
    ("Concierto de primavera", "Madrid Datos Abiertos", "cultural"),
    ("Taller De Teatro", "Ayuntamiento de Oviedo - actividades para personas mayores", "cultural"),
    ("Costura Creativa", "Ayuntamiento de Oviedo - actividades para personas mayores", "cultural"),

    # --- SOCIAL: comunidad, igualdad, ecología ---
    ("LECTURAS COMPARTIDAS", "Soledad No Deseada - programa contra la soledad", "social"),
    ("Ecología en tu día a día", "Puntos Vuela - centros de inclusion digital en Andalucia", "social"),
    ("Grupo de personas migrantes", "Madrid Datos Abiertos", "social"),

    # --- POLITICA: instituciones ---
    ("Agenda del Defensor del Pueblo", "Defensor del Pueblo - actos institucionales", "politica"),

    # --- EDGE CASES: tango/baile como espectáculo = CULTURAL ---
    ("Poesía, Tango y Flamenco", "Madrid Datos Abiertos", "cultural"),
    ("Petanca vecinal", "Madrid Datos Abiertos", "cultural"),
]


# =====================================================================
# Tests
# =====================================================================

class TestCategoryClassificationLLM:
    """Test LLM classification accuracy with curated edge cases."""

    def test_classification_accuracy(self, classifier):
        """All 20 events should be classified correctly (>= 85% accuracy)."""
        correct = 0
        failures = []

        for title, source_ctx, expected in CLASSIFICATION_EVENTS:
            result = classifier.classify_llm(title=title, source_context=source_ctx)
            actual = result[0] if result else "EMPTY"

            if actual == expected:
                correct += 1
            else:
                failures.append((title[:50], expected, actual))

        total = len(CLASSIFICATION_EVENTS)
        accuracy = correct / total * 100

        print(f"\n  ACCURACY: {correct}/{total} = {accuracy:.1f}%")
        if failures:
            print(f"  Failures ({len(failures)}):")
            for title, expected, actual in failures:
                print(f"    '{title}' expected={expected} got={actual}")

        assert accuracy >= 85, f"Accuracy {accuracy:.0f}% < 85% ({correct}/{total})"

    def test_never_invents_categories(self, classifier):
        """LLM should NEVER return a category outside the 6 valid ones."""
        tricky_titles = [
            ("Partido de fútbol veteranos", None),       # NOT "deportiva"
            ("Curso de cocina italiana", None),           # NOT "gastronomica"
            ("Taller de jardinería", None),               # NOT "medioambiental"
            ("Clase de inglés para mayores", None),       # NOT "educativa"
            ("Excursión al Museo del Prado", None),       # NOT "turistica"
        ]
        valid = {"cultural", "social", "economica", "politica", "tecnologia", "sanitaria"}

        for title, ctx in tricky_titles:
            result = classifier.classify_llm(title=title, source_context=ctx)
            assert result, f"Empty result for '{title}'"
            assert result[0] in valid, f"Invented category '{result[0]}' for '{title}'"
