"""Category classifier using LLM + embeddings fallback.

This module provides semantic classification of events using:
1. LLM classification (Groq) as primary method — 86%+ accuracy
2. Pre-computed category embeddings as fallback when LLM is unavailable

Categories are aligned with the Agendades social program for elderly inclusion:
- cultural: Participación Cultural (arte, música, teatro, literatura, deporte)
- economica: Participación Económica (empleo, formación, emprendimiento, finanzas)
- politica: Participación Política (derechos cívicos, gobierno, instituciones)
- social: Participación Social (comunidad, voluntariado, fiestas, solidaridad)
- tecnologia: Participación Tecnológica (digital, informática, brecha digital)
- sanitaria: Participación Sanitaria (salud, bienestar, prevención, apoyo mutuo)

IMPORTANT: Only these 6 categories are valid. The classifier MUST NOT invent
new categories (e.g. "deportiva", "educativa"). Sports → sanitaria.
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
        Conciertos conmemorativos, homenajes musicales, galas benéficas con actuación.
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
        Premios literarios, premios de cine, premios artísticos.
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
        Ecología, medio ambiente, sostenibilidad, reciclaje, cambio climático.
        Huertos urbanos, huertos comunitarios, agricultura social, jardines vecinales.
        Cuidado del planeta, conciencia medioambiental, naturaleza, biodiversidad.
        Igualdad de género, día de la mujer, violencia de género, feminismo.
        Premios de igualdad, observatorio contra la violencia doméstica.
        Derechos sociales, inclusión, diversidad, accesibilidad.
        Empoderamiento, activismo social, campañas de concienciación.
    """,

    "economica": """
        Participación Económica: defender derechos económicos, acceder al empleo
        y emprendimiento, formarse financieramente y gestionar recursos con autonomía.
        Reivindicar pensiones dignas, aportar experiencia al mercado laboral y ser
        parte activa de una economía que reconoce y valora la contribución.
        Incluye: ferias de empleo, bolsas de trabajo, orientación laboral.
        Búsqueda activa de empleo, elaboración de currículum, CV, entrevistas.
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
        Gestión de almacén, logística, operaciones en caja, retail, comercio.
        Coaching profesional, desarrollo de carrera, liderazgo empresarial.
        Monitor de ocio, monitor de tiempo libre, animación sociocultural.
        Atención al cliente, habilidades comerciales, telemarketing.
        Hostelería, turismo, camarero, cocina profesional.
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
        Ofimática, procesador de texto, hojas de cálculo, presentaciones.
        Certificado digital, firma electrónica, DNI electrónico.
        Copias de seguridad, almacenamiento en la nube, backup.
        Diseño gráfico, edición de fotos, edición de vídeo.
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
        Talleres de nutrición, alimentación saludable, comer bien, dieta equilibrada.
        Elegir alimentos, comer de temporada, nutrición, hábitos alimentarios.
        Diabetes, enfermedades crónicas, hipertensión, colesterol, obesidad.
        Salud mental, bienestar emocional, psicología, grupos de apoyo.
        Ejercicio físico saludable: gimnasia suave, paseos, aquagym.
        Primeros auxilios, RCP, cursos de emergencias, socorrismo.
        Terapias alternativas, acupuntura, naturopatía.
        Charlas sobre envejecimiento activo, autonomía personal.
        Jornadas de detección precoz, revisiones, chequeos.
        Bienestar para personas mayores, programas de salud, autocuidado.
        Salud digital, apps de salud, telemedicina, cita médica online.
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
    r"\b(?:sub-?\d{2}|alevín|alevin|benjamín|benjamin|cadete|prebenjamín)\b",
    r"\bcampamento\s+(?:infantil|juvenil|de\s+verano\s+para\s+niños)\b",
    r"\bludoteca\b",
]
_CHILDREN_RE = re.compile("|".join(CHILDREN_ONLY_PATTERNS), re.IGNORECASE)

# Age range regex — extracted separately to check upper bound
_AGE_RANGE_RE = re.compile(
    r"\b(?:edad|edades)\s*:?\s*(?:de\s+)?(\d+)\s*(?:a|-)\s*(\d+)\s*años\b",
    re.IGNORECASE,
)

# Keywords that indicate the event IS open to adults/seniors even if children are mentioned
ADULT_INCLUSIVE_PATTERNS = [
    r"\bfamiliar(?:es)?\b",
    r"\bfamilias\b",
    r"\btodas\s+las\s+edades\b",
    r"\bpúblico\s+general\b",
    r"\bintergeneracional\b",
    r"\badultos?\b",
    r"\bmayores\b",
    r"\btercera\s+edad\b",
    r"\bno\s+recomendad[ao]\s+para\s+menores\b",
    r"\bvíctimas?\b",
    r"\bcongreso\b",
    r"\bjornadas?\b",
    r"\bmasterclass\b",
]
_ADULT_RE = re.compile("|".join(ADULT_INCLUSIVE_PATTERNS), re.IGNORECASE)

# "infantil" used as a topic descriptor, not audience target
_INFANTIL_TOPIC_RE = re.compile(
    r"\b(?:literatura|mirada|herida|ilusión|desarrollo|educación|psicología|salud\s+mental)\s+infantil\b",
    re.IGNORECASE,
)

# Description of a children-only event — used for embedding verification (layer 2)
_CHILDREN_EVENT_DESCRIPTION = """
    Evento exclusivamente para niños, niñas o jóvenes menores de edad.
    Actividad infantil, taller para niños, ludoteca, cuentacuentos infantil,
    espectáculo de títeres, teatro infantil, campamento juvenil, juegos para niños,
    animación infantil, parque infantil, fiesta de cumpleaños, guardería, bebeteca.
    Actividad educativa escolar, excursión escolar, campeonato sub-12, deporte base.
    Evento diseñado y dirigido exclusivamente a público menor de edad.
"""

# Threshold: events below this similarity to _CHILDREN_EVENT_DESCRIPTION
# are considered false positives (not truly children-only events)
_CHILDREN_EMBEDDING_THRESHOLD = 0.45

# Cache for the children-event embedding (computed once)
_children_embedding: list[float] | None = None


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


def _get_children_embedding() -> list[float] | None:
    """Get or compute the children-event reference embedding (cached in memory)."""
    global _children_embedding
    if _children_embedding is None:
        try:
            client = get_embeddings_client()
            clean_desc = " ".join(_CHILDREN_EVENT_DESCRIPTION.split())
            _children_embedding = client.generate(clean_desc)
        except Exception as e:
            logger.warning("children_embedding_failed", error=str(e))
    return _children_embedding


def _has_children_age_range(text: str) -> bool:
    """Check if text has an age range targeting only minors (max age <= 17)."""
    for m in _AGE_RANGE_RE.finditer(text):
        max_age = int(m.group(2))
        if max_age <= 17:
            return True
    return False


def _verify_children_with_embeddings(title: str, description: str) -> bool:
    """Layer 2: Verify a pattern-flagged event is truly children-only using embeddings.

    Compares the event's embedding against a reference "children-only event"
    embedding. If the similarity is below threshold, the event is likely a
    false positive (e.g., a concert mentioning ticket policy for infants,
    an art piece depicting children, a professional conference about youth).

    Returns True if the event IS confirmed children-only, False if it's
    likely a false positive.
    """
    ref_embedding = _get_children_embedding()
    if ref_embedding is None:
        # If embeddings unavailable, trust the pattern match
        return True

    try:
        client = get_embeddings_client()
        event_text = f"{title}. {description[:500]}" if description else title
        event_embedding = client.generate(event_text)

        if event_embedding is None:
            return True  # Trust pattern match if embedding fails

        similarity = cosine_similarity(event_embedding, ref_embedding)
        is_children = similarity >= _CHILDREN_EMBEDDING_THRESHOLD

        logger.debug(
            "children_embedding_verify",
            title=title[:60],
            similarity=round(similarity, 4),
            confirmed=is_children,
        )

        return is_children

    except Exception as e:
        logger.warning("children_verify_error", error=str(e))
        return True  # Trust pattern match on error


def is_children_only(title: str, description: str = "", use_embeddings: bool = True) -> bool:
    """Check if an event is exclusively for children/youth (2-layer filter).

    Layer 1 (patterns): Fast regex-based check for children keywords.
    Layer 2 (embeddings): Semantic verification for pattern-flagged events
    to eliminate false positives (concerts, art, professional conferences).

    Returns True only if both layers agree the event is children-only.
    Events marked as 'familiar', 'todas las edades', professional events
    (congreso, jornada), or adult content ratings are NOT filtered out.
    """
    text = f"{title} {description}"

    # --- Layer 1: Pattern-based filtering ---

    # Check adult-inclusive first — these override everything
    if _ADULT_RE.search(text):
        return False

    # Check "infantil" used as topic descriptor (not audience)
    if _INFANTIL_TOPIC_RE.search(text):
        cleaned = _INFANTIL_TOPIC_RE.sub("", text)
        if not _CHILDREN_RE.search(cleaned) and not _has_children_age_range(cleaned):
            return False

    # Check explicit children patterns or age ranges
    pattern_flagged = _CHILDREN_RE.search(text) or _has_children_age_range(text)

    if not pattern_flagged:
        return False

    # --- Layer 2: Embedding verification ---
    if use_embeddings:
        return _verify_children_with_embeddings(title, description)

    return True


# ============================================================
# LLM CLASSIFICATION PROMPT
# ============================================================

_LLM_CLASSIFY_SYSTEM = """Eres un clasificador de eventos para Agendades, una agenda de actividades para personas mayores en España.
Clasifica cada evento en UNA sola categoría según su PROPÓSITO PRINCIPAL para el público mayor.

IMPORTANTE: Considera el contexto del programa del que proviene el evento.
- Un "Baile Zumba" en un programa de bienestar para mayores es SANITARIA (ejercicio), no cultural.
- Una "Lectura compartida" en un programa contra la soledad es SOCIAL (combatir aislamiento), no cultural.
- La agenda de un ministro es POLITICA aunque visite un museo.
- Un taller de ChatGPT para emprendedores es ECONOMICA, no tecnologia.
- Eventos deportivos como ejercicio o bienestar son SANITARIA, no inventar "deportiva".

Categorías (SOLO estas 6, no inventes nuevas):
- cultural: Espectáculos, conciertos, teatro, cine, exposiciones, museos, arte, literatura, deporte como entretenimiento
- social: Comunidad, voluntariado, fiestas, ecología, medio ambiente, igualdad de género, inclusión, solidaridad, combatir soledad
- economica: Empleo, emprendimiento, formación profesional, ferias comerciales, finanzas, coaching laboral
- politica: Gobierno, parlamento, instituciones, agenda ministerial, actos institucionales, derechos cívicos
- tecnologia: Informática, internet, programación, IA, robótica, ciberseguridad, brecha digital, ofimática, apps
- sanitaria: Salud, nutrición, alimentación, ejercicio físico, primeros auxilios, salud mental, prevención, yoga, zumba, pilates

Responde SOLO con el slug de la categoría. Sin explicación, sin comillas, sin puntuación."""


class CategoryClassifier:
    """Category classifier using LLM as primary method, embeddings as fallback."""

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
        self._llm_client: Any = None
        self._llm_available: bool | None = None  # None = not checked yet

    @property
    def llm_client(self) -> Any:
        """Lazy initialization of Groq LLM client."""
        if self._llm_client is None:
            try:
                from src.config.settings import get_settings
                settings = get_settings()
                if not settings.groq_api_key:
                    self._llm_available = False
                    return None
                from groq import Groq
                self._llm_client = Groq(api_key=settings.groq_api_key)
                self._llm_available = True
                logger.info("category_llm_initialized", provider="groq")
            except Exception as e:
                logger.warning("category_llm_init_failed", error=str(e))
                self._llm_available = False
        return self._llm_client

    def classify_llm(
        self,
        title: str,
        source_context: str | None = None,
    ) -> list[str]:
        """Classify event using LLM (Groq).

        Primary classification method. Uses the event title and optional
        source context to determine the most appropriate category.

        Only returns valid category slugs — never invents new categories.
        Falls back to DEFAULT_CATEGORY if LLM returns an invalid response.

        Args:
            title: Event title
            source_context: Optional description of the event source
                (e.g. "CeMIT - centros de inclusión tecnológica de Galicia")

        Returns:
            List with a single category slug
        """
        client = self.llm_client
        if client is None:
            return []  # Signal caller to use fallback

        user_msg = f"Título: {title}"
        if source_context:
            user_msg += f"\nFuente: {source_context}"

        try:
            from src.config.settings import get_settings
            settings = get_settings()
            model = settings.groq_model

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _LLM_CLASSIFY_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=10,
            )
            raw = response.choices[0].message.content.strip().lower()
            # Clean common LLM artifacts
            raw = raw.replace('"', '').replace("'", "").replace(".", "").strip()

            if raw in self.allowed_categories:
                logger.debug(
                    "category_llm_ok",
                    title=title[:60],
                    category=raw,
                )
                return [raw]

            # LLM returned invalid category — reject it
            logger.warning(
                "category_llm_invalid",
                title=title[:60],
                raw_response=raw,
            )
            return []  # Signal caller to use fallback

        except Exception as e:
            logger.warning("category_llm_error", error=str(e), title=title[:60])
            self._llm_available = False  # Disable for rest of session
            return []  # Signal caller to use fallback

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
