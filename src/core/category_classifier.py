"""Category classifier using embeddings + LLM hybrid approach.

This module provides semantic classification of events using:
1. Pre-computed category embeddings for fast similarity matching
2. LLM fallback for ambiguous cases

Flow:
1. LLM normalizes raw text → clean, contextual description
2. Generate embedding of normalized text
3. Compare with category embeddings via cosine similarity
4. Assign top categories above confidence threshold
"""

import json
import math
from pathlib import Path
from typing import Any

from src.core.embeddings import get_embeddings_client, EmbeddingsClient
from src.logging import get_logger

logger = get_logger(__name__)

# Cache file for pre-computed category embeddings
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CATEGORY_EMBEDDINGS_CACHE = CACHE_DIR / "category_embeddings.json"


# ============================================================
# CATEGORY DEFINITIONS - Rich descriptions for better embeddings
# ============================================================

CATEGORY_DESCRIPTIONS = {
    "cultural": """
        Eventos artísticos, entretenimiento y espectáculos.
        Incluye: conciertos de música clásica, jazz, rock, pop, indie.
        Teatro, obras dramáticas, comedias, musicales, monólogos, stand-up.
        Danza contemporánea, ballet, flamenco, danza urbana.
        Cine, proyecciones, festivales de cine, documentales, estrenos.
        Exposiciones de arte, pintura, escultura, fotografía.
        Museos, galerías de arte, instalaciones artísticas.
        Literatura, presentaciones de libros, lecturas poéticas, clubs de lectura.
        Ópera, zarzuela, recitales líricos.
        Festivales culturales, semanas culturales.
        Eventos deportivos: fútbol, baloncesto, boxeo, MMA, artes marciales.
        Carreras populares, maratones, trails, ciclismo, triatlón.
        Torneos, competiciones deportivas, partidos, ligas.
        Esports, torneos de videojuegos.
        Espectáculos en general que no encajen en otras categorías.
    """,

    "social": """
        Eventos comunitarios, encuentros sociales y fiestas populares.
        Incluye: fiestas patronales, romerías, verbenas, ferias populares.
        Carnavales, comparsas, murgas, desfiles de disfraces.
        Semana Santa, procesiones religiosas, festividades católicas.
        Encuentros vecinales, reuniones de barrio, asambleas ciudadanas.
        Actividades para la tercera edad, jubilados, mayores.
        Voluntariado, acciones solidarias, ONGs, bancos de alimentos.
        Mercadillos solidarios, rastros benéficos.
        Fiestas tradicionales, costumbres locales, folklore.
        Cabalgatas, desfiles cívicos, actos conmemorativos.
        Comidas populares, calçotadas, sardinadas, paellas gigantes.
        NO incluye: competiciones deportivas, cursos profesionales.
    """,

    "economica": """
        Eventos relacionados con empleo, negocios, formación profesional y cursos con certificación.
        Incluye: ferias de empleo, bolsas de trabajo, job fairs.
        Cursos de emprendimiento, startups, incubadoras.
        Networking empresarial, B2B, encuentros profesionales.
        Formación profesional, cursos técnicos, certificaciones, carnets profesionales.
        Cursos de manipulador de alimentos, PRL, prevención de riesgos.
        Cursos de hostelería, cocina profesional, camarero.
        Carnet de carretillero, operador de maquinaria.
        Ferias comerciales, exposiciones de productos, stands.
        Conferencias de negocios, congresos empresariales.
        Talleres de marketing, ventas, gestión empresarial.
        Charlas sobre finanzas personales, inversiones.
        Eventos de cámaras de comercio, asociaciones empresariales.
        Cualquier curso que otorgue certificación profesional o habilitación laboral.
    """,

    "politica": """
        Eventos de participación ciudadana y actividad política.
        Incluye: plenos municipales, sesiones del ayuntamiento.
        Debates políticos, mítines, actos de campaña electoral.
        Presupuestos participativos, consultas ciudadanas.
        Asambleas vecinales con temática política.
        Conferencias sobre política, geopolítica, relaciones internacionales.
        Presentaciones de programas electorales.
        Actos institucionales de gobiernos y administraciones.
        Manifestaciones, protestas cívicas (pacíficas).
    """,

    "sanitaria": """
        Eventos de salud, bienestar personal y calidad de vida.
        Incluye: clases de yoga, pilates, tai chi, meditación.
        Mindfulness, relajación, gestión del estrés.
        Charlas de salud, prevención de enfermedades.
        Campañas de vacunación, donación de sangre.
        Talleres de nutrición, alimentación saludable, dietas.
        Salud mental, bienestar emocional, psicología.
        Fitness recreativo orientado a salud (no competitivo): zumba, aerobic, spinning.
        Primeros auxilios, RCP, cursos de emergencias (no profesionales).
        Jornadas médicas, charlas de doctores.
        Terapias alternativas, acupuntura, naturopatía, reiki.
        NO incluye: boxeo, MMA, artes marciales competitivas, veladas deportivas.
        NO incluye: maratones, carreras, trails, competiciones deportivas.
        NO incluye: cursos con certificación profesional (eso es economica).
    """,

    "tecnologia": """
        Eventos de tecnología, innovación y mundo digital.
        Incluye: talleres de programación, coding, desarrollo web.
        Charlas sobre inteligencia artificial, machine learning, IA.
        Blockchain, criptomonedas, web3, NFTs.
        Robótica, makers, Arduino, Raspberry Pi, electrónica.
        Videojuegos, gaming, cultura gamer.
        Hackathons, maratones de programación.
        Ciberseguridad, hacking ético, privacidad digital.
        Alfabetización digital, cursos de informática básica.
        Realidad virtual, realidad aumentada, metaverso.
        Startups tecnológicas, demos de productos tech.
    """,
}

# Default category when no good match is found
DEFAULT_CATEGORY = "cultural"


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


class CategoryClassifier:
    """Hybrid category classifier using embeddings + optional LLM fallback."""

    def __init__(
        self,
        confidence_threshold: float = 0.50,
        fallback_threshold: float = 0.48,
        max_categories: int = 2,
    ) -> None:
        """Initialize classifier.

        Args:
            confidence_threshold: Minimum similarity to assign category with confidence
            fallback_threshold: If best match is below this, use default category
            max_categories: Maximum categories to assign per event
        """
        self.confidence_threshold = confidence_threshold
        self.fallback_threshold = fallback_threshold
        self.max_categories = max_categories
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
                    logger.info("category_embeddings_loaded", count=len(cached))
                    return cached
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

        Args:
            text: Normalized/clean text to classify (from LLM)
            title: Optional title for additional context

        Returns:
            Tuple of (category_slugs, similarity_scores)
        """
        # Combine title + text for richer embedding
        if title:
            full_text = f"{title}. {text}"
        else:
            full_text = text

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

        # Select categories above threshold
        selected = []
        for slug, score in sorted_categories:
            if score >= self.confidence_threshold and len(selected) < self.max_categories:
                selected.append(slug)

        # If nothing above confidence threshold, use best match or default
        if not selected and sorted_categories:
            best_slug, best_score = sorted_categories[0]
            # If best match is above fallback threshold, use it
            if best_score >= self.fallback_threshold:
                selected = [best_slug]
                logger.info(
                    "category_best_match",
                    category=best_slug,
                    score=best_score,
                    threshold=self.confidence_threshold,
                )
            else:
                # Very low confidence, use default (cultural)
                selected = [DEFAULT_CATEGORY]
                logger.info(
                    "category_fallback_to_default",
                    default=DEFAULT_CATEGORY,
                    best_match=(best_slug, best_score),
                    fallback_threshold=self.fallback_threshold,
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
