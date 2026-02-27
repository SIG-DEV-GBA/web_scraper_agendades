"""Category classifier using embeddings + LLM hybrid approach.

This module provides semantic classification of events using:
1. Pre-computed category embeddings for fast similarity matching
2. LLM fallback for ambiguous cases

Categories are aligned with the Agendades social program for elderly inclusion:
- cultural: Participación Cultural (arte, música, teatro, literatura, deporte)
- economica: Participación Económica (empleo, formación, emprendimiento, finanzas)
- politica: Participación Política (derechos cívicos, gobierno, instituciones)
- social: Participación Social (comunidad, voluntariado, fiestas, solidaridad)
- tecnologia: Participación Tecnológica (digital, informática, brecha digital)
- sanitaria: Participación Sanitaria (salud, bienestar, prevención, apoyo mutuo)

Flow:
1. LLM normalizes raw text → clean, contextual description
2. Generate embedding of normalized text
3. Compare with category embeddings via cosine similarity
4. Assign best matching category above confidence threshold
"""

import json
import math
import re
from pathlib import Path
from typing import Any

from src.core.embeddings import get_embeddings_client, EmbeddingsClient
from src.logging import get_logger

logger = get_logger(__name__)

# Cache file for pre-computed category embeddings
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CATEGORY_EMBEDDINGS_CACHE = CACHE_DIR / "category_embeddings.json"


# ============================================================
# CATEGORY DEFINITIONS
# Aligned with Agendades program for elderly inclusion.
# Descriptions from CATEGORIAS_INDICACIONES.md enriched with
# concrete examples for better embedding matching.
# ============================================================

CATEGORY_DESCRIPTIONS = {
    "cultural": """
        Participación Cultural: involucrarse en actividades y expresiones culturales
        que enriquecen la vida y favorecen la interacción con otras personas,
        sin que la edad importe. Mejora la calidad de vida, mantiene la mente activa,
        promueve la creatividad y fortalece la identidad social.
        Incluye: conciertos de música clásica, jazz, rock, pop, folk, indie.
        Teatro, obras dramáticas, comedias, musicales, monólogos, stand-up.
        Danza contemporánea, ballet, flamenco, danza urbana.
        Cine, proyecciones, festivales de cine, documentales, estrenos.
        Exposiciones de arte, pintura, escultura, fotografía.
        Museos, galerías de arte, instalaciones artísticas.
        Literatura, presentaciones de libros, lecturas poéticas, clubs de lectura.
        Ópera, zarzuela, recitales líricos.
        Festivales culturales, semanas culturales, jornadas de puertas abiertas.
        Eventos deportivos para disfrutar: fútbol, baloncesto, atletismo.
        Carreras populares, maratones, paseos, rutas senderismo.
        Talleres artísticos, manualidades, cerámica, pintura.
        Visitas guiadas, excursiones culturales, rutas turísticas.
        Espectáculos, circo, magia, humor.
    """,

    "social": """
        Participación Social: involucrarse en la vida comunitaria y asociativa
        que enriquece las relaciones personales y favorece el sentido de pertenencia,
        sin que la edad sea una barrera. Mejora la calidad de vida, combate la soledad,
        promueve la solidaridad y fortalece el tejido social para una vida más plena.
        Incluye: fiestas patronales, romerías, verbenas, ferias populares.
        Carnavales, comparsas, desfiles, cabalgatas.
        Encuentros vecinales, reuniones de barrio, asociaciones de vecinos.
        Actividades para la tercera edad, jubilados, mayores, centros de día.
        Voluntariado, acciones solidarias, ONGs, bancos de alimentos.
        Mercadillos solidarios, rastros benéficos.
        Fiestas tradicionales, costumbres locales, folklore.
        Comidas populares, calçotadas, sardinadas, paellas.
        Semana Santa, procesiones, festividades religiosas.
        Convivencias intergeneracionales, intercambio de experiencias.
        Grupos de apoyo, tertulias, cafés sociales.
        Actividades contra la soledad no deseada.
    """,

    "economica": """
        Participación Económica: defender derechos económicos, acceder al empleo
        y emprendimiento, formarse financieramente y gestionar recursos con autonomía.
        Reivindicar pensiones dignas, aportar experiencia al mercado laboral y ser
        parte activa de una economía que reconoce y valora la contribución.
        Incluye: ferias de empleo, bolsas de trabajo, orientación laboral.
        Cursos de emprendimiento, startups, incubadoras.
        Networking empresarial, encuentros profesionales.
        Formación profesional, cursos técnicos, certificaciones.
        Cursos de manipulador de alimentos, PRL, prevención de riesgos.
        Ferias comerciales, exposiciones de productos.
        Conferencias de negocios, congresos empresariales.
        Talleres de marketing, ventas, gestión empresarial.
        Charlas sobre finanzas personales, inversiones, pensiones.
        Eventos de cámaras de comercio, asociaciones empresariales.
        Economía social, cooperativas, comercio justo.
        Asesoramiento fiscal, legal, derechos del consumidor.
    """,

    "politica": """
        Participación Política: ejercer derechos y deberes cívicos, influir en
        las decisiones colectivas y exigir responsabilidad a quienes gobiernan.
        Participar amplifica tu voz, promueve cambios sociales y construye
        instituciones más legítimas, transparentes y orientadas al interés general.
        Incluye: plenos municipales, sesiones del ayuntamiento, parlamento.
        Debates políticos, mítines, actos de campaña electoral.
        Presupuestos participativos, consultas ciudadanas.
        Asambleas vecinales con temática política.
        Conferencias sobre política, geopolítica, relaciones internacionales.
        Actos institucionales de gobiernos y administraciones.
        Manifestaciones, protestas cívicas pacíficas.
        Consejos de mayores, órganos de participación ciudadana.
        Jornadas sobre derechos civiles, igualdad, justicia social.
        Agenda gubernamental, comisiones parlamentarias.
    """,

    "tecnologia": """
        Participación Tecnológica: acceder al mundo digital con seguridad y autonomía,
        comunicarse sin límites, aprender nuevas herramientas y formar parte activa
        de una sociedad conectada, superando la brecha digital.
        Va más allá de usar un móvil: es inclusión digital para personas mayores.
        Incluye: talleres de informática básica, uso de ordenador, tablet, móvil.
        Cursos de internet, navegación web, correo electrónico.
        Redes sociales, WhatsApp, videollamadas, Skype, Zoom.
        Administración electrónica, sede electrónica, cita previa online.
        Banca online, compras por internet, seguridad digital.
        Talleres de programación, coding, desarrollo web.
        Inteligencia artificial, robótica, impresión 3D.
        Ciberseguridad, privacidad digital, protección de datos.
        Alfabetización digital, reducción de la brecha digital.
        Hackathons, eventos maker, Arduino, Raspberry Pi.
    """,

    "sanitaria": """
        Participación Sanitaria: conocer tus derechos como paciente, involucrarte
        en el cuidado de tu propia salud, compartir experiencias en grupos de apoyo
        mutuo, formarte en prevención y hábitos saludables y contribuir como
        voluntario al bienestar de otros. Ser protagonista de tu salud y parte
        activa de una comunidad que cuida y se cuida.
        Incluye: clases de yoga, pilates, tai chi, meditación, mindfulness.
        Charlas de salud, prevención de enfermedades, jornadas médicas.
        Campañas de vacunación, donación de sangre.
        Talleres de nutrición, alimentación saludable.
        Salud mental, bienestar emocional, psicología, grupos de apoyo.
        Ejercicio físico saludable: gimnasia suave, paseos, aquagym.
        Primeros auxilios, RCP, cursos de emergencias.
        Terapias alternativas, acupuntura, naturopatía.
        Charlas sobre envejecimiento activo, autonomía personal.
        Jornadas de detección precoz, revisiones, chequeos.
    """,
}

# Default category when no good match is found
DEFAULT_CATEGORY = "cultural"

# Keywords that indicate children/youth-only events (to filter out)
CHILDREN_ONLY_PATTERNS = [
    r"\b(?:infantil|infantiles)\b",
    r"\b(?:juvenil|juveniles)\b",
    r"\b(?:niños|niñas|niñ@s)\b",
    r"\b(?:bebés|bebeteca)\b",
    r"\bpara\s+(?:niños|niñas|jóvenes|adolescentes|menores)\b",
    r"\b(?:edad|edades)\s*:?\s*(?:de\s+)?\d+\s*(?:a|-)\s*\d+\s*años\b",
    r"\b(?:sub-?\d{2}|alevín|alevin|benjamín|benjamin|cadete|prebenjamín)\b",
    r"\bcampamento\s+(?:infantil|juvenil|de\s+verano\s+para\s+niños)\b",
    r"\bludoteca\b",
]
_CHILDREN_RE = re.compile("|".join(CHILDREN_ONLY_PATTERNS), re.IGNORECASE)

# Keywords that indicate the event IS open to adults/seniors even if children are mentioned
ADULT_INCLUSIVE_PATTERNS = [
    r"\bfamiliar(?:es)?\b",
    r"\btodas\s+las\s+edades\b",
    r"\bpúblico\s+general\b",
    r"\bintergeneracional\b",
    r"\badultos\b",
    r"\bmayores\b",
    r"\btercera\s+edad\b",
]
_ADULT_RE = re.compile("|".join(ADULT_INCLUSIVE_PATTERNS), re.IGNORECASE)


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def is_children_only(title: str, description: str = "") -> bool:
    """Check if an event is exclusively for children/youth.

    Returns True only if children-only keywords are found AND no adult-inclusive
    keywords are present. Events marked as 'familiar' or 'todas las edades'
    are NOT filtered out.
    """
    text = f"{title} {description}"
    if _CHILDREN_RE.search(text):
        # Has children keywords — but check if also open to adults
        if _ADULT_RE.search(text):
            return False
        return True
    return False


class CategoryClassifier:
    """Hybrid category classifier using embeddings + optional LLM fallback."""

    def __init__(
        self,
        confidence_threshold: float = 0.48,
        fallback_threshold: float = 0.42,
        max_categories: int = 1,
    ) -> None:
        """Initialize classifier.

        Args:
            confidence_threshold: Minimum similarity to assign category with confidence
            fallback_threshold: If best match is below this, use default category
            max_categories: Maximum categories to assign per event (default: 1)
        """
        self.confidence_threshold = confidence_threshold
        self.fallback_threshold = fallback_threshold
        self.max_categories = max_categories
        self.allowed_categories = {
            "cultural", "social", "economica", "politica", "tecnologia", "sanitaria",
        }
        self._embeddings_client: EmbeddingsClient | None = None
        self._category_embeddings: dict[str, list[float]] | None = None

    @property
    def embeddings_client(self) -> EmbeddingsClient:
        """Lazy initialization of embeddings client."""
        if self._embeddings_client is None:
            self._embeddings_client = get_embeddings_client()
        return self._embeddings_client

    @property
    def category_embeddings(self) -> dict[str, list[float]]:
        """Get or compute category embeddings (cached)."""
        if self._category_embeddings is None:
            self._category_embeddings = self._load_or_compute_embeddings()
        return self._category_embeddings

    def _load_or_compute_embeddings(self) -> dict[str, list[float]]:
        """Load category embeddings from cache or compute them."""
        # Try loading from cache
        if CATEGORY_EMBEDDINGS_CACHE.exists():
            try:
                with open(CATEGORY_EMBEDDINGS_CACHE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    # Verify cache has all 6 categories
                    if set(cached.keys()) == set(CATEGORY_DESCRIPTIONS.keys()):
                        logger.info("category_embeddings_loaded", count=len(cached))
                        return cached
                    else:
                        logger.info("cache_stale_recomputing",
                                    cached=list(cached.keys()),
                                    expected=list(CATEGORY_DESCRIPTIONS.keys()))
            except Exception as e:
                logger.warning("cache_load_error", error=str(e))

        # Compute embeddings
        logger.info("computing_category_embeddings")
        embeddings = {}

        for slug, description in CATEGORY_DESCRIPTIONS.items():
            # Clean and normalize description
            clean_desc = " ".join(description.split())
            embedding = self.embeddings_client.generate(clean_desc)

            if embedding:
                embeddings[slug] = embedding
                logger.info("category_embedding_computed", category=slug)
            else:
                logger.error("category_embedding_failed", category=slug)

        # Save to cache
        if embeddings:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CATEGORY_EMBEDDINGS_CACHE, "w", encoding="utf-8") as f:
                json.dump(embeddings, f)
            logger.info("category_embeddings_cached", path=str(CATEGORY_EMBEDDINGS_CACHE))

        return embeddings

    def classify(
        self,
        text: str,
        title: str | None = None,
    ) -> tuple[list[str], dict[str, float]]:
        """Classify text into categories using embedding similarity.

        Compares all 6 categories and picks the best match above threshold.
        Falls back to 'cultural' if no category is confident enough.

        Args:
            text: Normalized/clean text to classify (from LLM)
            title: Optional title for additional context

        Returns:
            Tuple of (category_slugs, similarity_scores)
        """
        # Combine title + text for richer embedding
        full_text = f"{title}. {text}" if title else text

        # Generate embedding for input text
        event_embedding = self.embeddings_client.generate(full_text[:2000])

        if not event_embedding:
            logger.warning("event_embedding_failed", text_preview=full_text[:50])
            return [], {}

        # Calculate similarity with each category
        scores: dict[str, float] = {}
        for slug, cat_embedding in self.category_embeddings.items():
            similarity = cosine_similarity(event_embedding, cat_embedding)
            scores[slug] = round(similarity, 4)

        # Sort by similarity (descending)
        sorted_categories = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if not sorted_categories:
            return [DEFAULT_CATEGORY], scores

        best_slug, best_score = sorted_categories[0]

        # Pick the best category if above confidence threshold
        if best_score >= self.confidence_threshold:
            selected = [best_slug]
            logger.debug(
                "category_confident",
                category=best_slug,
                score=best_score,
            )
        elif best_score >= self.fallback_threshold:
            # Marginal confidence — use it but log warning
            selected = [best_slug]
            logger.debug(
                "category_marginal",
                category=best_slug,
                score=best_score,
            )
        else:
            # Below fallback threshold — default to cultural
            selected = [DEFAULT_CATEGORY]
            logger.debug(
                "category_default",
                original_best=(best_slug, best_score),
            )

        logger.debug(
            "classification_complete",
            categories=selected,
            top_scores={k: v for k, v in sorted_categories[:3]},
        )

        return selected, scores

    def classify_batch(
        self,
        events: list[dict[str, Any]],
        text_field: str = "normalized_text",
        title_field: str = "title",
    ) -> dict[str, tuple[list[str], dict[str, float]]]:
        """Classify multiple events.

        Args:
            events: List of event dicts
            text_field: Field containing normalized text
            title_field: Field containing title

        Returns:
            Dict mapping event_id to (categories, scores)
        """
        results = {}

        for event in events:
            event_id = event.get("external_id") or event.get("id")
            if not event_id:
                continue

            text = event.get(text_field) or event.get("description") or ""
            title = event.get(title_field) or ""

            if not text and not title:
                continue

            categories, scores = self.classify(text, title)
            results[str(event_id)] = (categories, scores)

        logger.info("batch_classification_complete", total=len(events), classified=len(results))
        return results

    def refresh_cache(self) -> None:
        """Force recompute category embeddings."""
        if CATEGORY_EMBEDDINGS_CACHE.exists():
            CATEGORY_EMBEDDINGS_CACHE.unlink()
        self._category_embeddings = None
        _ = self.category_embeddings  # Trigger recompute


# Singleton
_classifier: CategoryClassifier | None = None


def get_category_classifier() -> CategoryClassifier:
    """Get singleton category classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = CategoryClassifier()
    return _classifier
