"""Smart LLM enricher for batch event classification and image keywords."""

import json
from enum import Enum
from typing import Any

from groq import Groq
from openai import OpenAI
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.logging.logger import get_logger

logger = get_logger(__name__)


class EnricherTier(str, Enum):
    """LLM tier for enrichment - determines which model to use."""

    ORO = "oro"  # Clean JSON APIs - use gpt-oss-120b (fast, structured)
    PLATA = "plata"  # Semi-structured HTML - use llama-3.3-70b (balanced)
    BRONCE = "bronce"  # Chaotic websites - use kimi-k2 (deep reasoning)
    FILTER = "filter"  # Pre-processing filter - use llama-3.1-8b (fast, cheap)


# Backward compatibility alias
SourceTier = EnricherTier


# ============================================================
# DB CATEGORIES - Must match Supabase categories table
# ============================================================
DB_CATEGORIES = {
    "cultural": "Cine, teatro, exposiciones, conciertos, danza, literatura, festivales artísticos",
    "social": "Encuentros vecinales, solidaridad, comunidad, voluntariado, tercera edad, fiestas populares",
    "economica": "Empleo, emprendimiento, finanzas, networking, ferias comerciales, formación profesional",
    "politica": "Debates políticos, participación ciudadana, plenos municipales, elecciones",
    "sanitaria": "Salud, yoga, meditación, bienestar, prevención, campañas sanitarias, primeros auxilios",
    "tecnologia": "Programación, charlas tech, talleres digitales, IA, robótica, videojuegos, hackathons",
}


class EventEnrichment(BaseModel):
    """Enriched data for a single event."""

    event_id: str
    category_slugs: list[str] = Field(
        default_factory=list,
        description="1-3 categories from: cultural, social, economica, politica, sanitaria, tecnologia"
    )
    summary: str | None = Field(default=None, max_length=200, description="Resumen conciso del evento")
    description: str | None = Field(default=None, max_length=1000, description="Descripción detallada del evento (para fuentes Bronze sin descripción)")
    image_keywords: list[str] = Field(default_factory=list, description="3 keywords en inglés para buscar imagen")
    age_range: str | None = Field(default=None, description="Rango de edad: infantil, familiar, adultos, mayores, todos")
    is_free: bool | None = Field(default=None, description="true=gratuito confirmado, false=de pago, null=no especificado")
    price: float | None = Field(default=None, description="Precio numérico en euros (null si gratuito o no especificado)")
    price_details: str | None = Field(default=None, description="Info adicional: descuentos, precios reducidos, etc.")


# ============================================================
# DEEP ENRICHMENT MODELS (Fase 1: Organizador, Contacto, Accesibilidad)
# ============================================================

class OrganizerType(str, Enum):
    """Type of event organizer."""
    INSTITUCION = "institucion"  # Ayuntamiento, Cabildo, Gobierno
    EMPRESA = "empresa"          # SL, SA, empresa privada
    ASOCIACION = "asociacion"    # Asociación, Fundación, ONG
    OTRO = "otro"


class OrganizerInfo(BaseModel):
    """Extracted organizer information."""
    name: str | None = None
    type: OrganizerType | None = None
    url: str | None = None
    logo_url: str | None = None


class ContactInfo(BaseModel):
    """Extracted contact information."""
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    info: str | None = Field(default=None, max_length=200)


class RegistrationInfo(BaseModel):
    """Extracted registration information."""
    required: bool = False
    url: str | None = None
    deadline: str | None = None  # ISO date string
    max_attendees: int | None = None


class AccessibilityInfo(BaseModel):
    """Extracted accessibility information."""
    wheelchair_accessible: bool = False
    sign_language: bool = False
    hearing_loop: bool = False
    braille_materials: bool = False
    other_facilities: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=80)


class DeepEnrichment(BaseModel):
    """Deep enrichment data for an event (Fase 1)."""
    event_id: str
    organizer: OrganizerInfo | None = None
    contact: ContactInfo | None = None
    registration: RegistrationInfo | None = None
    accessibility: AccessibilityInfo | None = None
    # Track what was found
    has_organizer: bool = False
    has_accessibility: bool = False


class BatchEnrichmentResult(BaseModel):
    """Result of batch enrichment."""

    events: list[EventEnrichment]


# ============================================================
# DEEP ENRICHMENT PROMPT (Fase 1)
# ============================================================

DEEP_ENRICHMENT_PROMPT = """Extrae información detallada del evento. SOLO incluye campos con evidencia EXPLÍCITA en el texto.
Sin evidencia = null/false. NO inventes datos.

KEYWORDS DE REFERENCIA:

ORGANIZADOR (organizer.type):
- institucion: ayuntamiento, cabildo, gobierno, diputación, ministerio, junta, consejería
- empresa: SL, SA, empresa, compañía, productora, promotora
- asociacion: asociación, fundación, ONG, colectivo, peña, cofradía

ACCESIBILIDAD (accessibility):
- wheelchair: "silla de ruedas", "acceso adaptado", "rampa", "ascensor", "PMR", "movilidad reducida", "accesible"
- sign_language: "lengua de signos", "LSE", "intérprete de signos", "signado"
- hearing_loop: "bucle magnético", "bucle inductivo", "sistema FM", "audiodescripción"
- braille: "braille", "materiales táctiles", "lectura fácil"

INSCRIPCIÓN (registration):
- required=true: "inscripción previa", "reserva obligatoria", "aforo limitado", "plazas limitadas", "registro necesario"

Responde ESTRICTAMENTE con este JSON:
{{
  "event_id": "{event_id}",
  "organizer": {{
    "name": null,
    "type": null,
    "url": null,
    "logo_url": null
  }},
  "contact": {{
    "name": null,
    "email": null,
    "phone": null,
    "info": null
  }},
  "registration": {{
    "required": false,
    "url": null,
    "deadline": null,
    "max_attendees": null
  }},
  "accessibility": {{
    "wheelchair_accessible": false,
    "sign_language": false,
    "hearing_loop": false,
    "braille_materials": false,
    "other_facilities": null,
    "notes": null
  }}
}}

REGLAS ESTRICTAS:
1. organizer.type SOLO puede ser: "institucion", "empresa", "asociacion", "otro"
2. URLs deben ser completas (https://...)
3. Teléfonos en formato: +34 XXX XXX XXX
4. Emails: solo si son claramente de contacto del evento
5. max_attendees: número entero o null
6. deadline: formato YYYY-MM-DD o null
7. Límites: name max 100 chars, info/notes max 80 chars, other_facilities max 80 chars

CONTENIDO A ANALIZAR:
{content}"""


# Prompt optimizado para clasificación batch con múltiples categorías
BATCH_CLASSIFICATION_PROMPT = """Eres un clasificador experto de eventos culturales en ESPAÑA. Analiza CADA evento en profundidad antes de asignar categorías.

CAMPOS DE CADA EVENTO:
- id: identificador único
- title: título del evento
- description: descripción (puede estar vacía)
- venue: lugar donde se celebra ← MUY IMPORTANTE PARA DETERMINAR is_free (biblioteca, museo, etc.)
- location: REGIÓN DE ESPAÑA (ciudad, provincia, comunidad autónoma) ← USA ESTO PARA CONTEXTUALIZAR IMÁGENES
- type: tipo de evento (si está disponible)
- audience: público objetivo
- price_info: información de precio

CATEGORÍAS DISPONIBLES (usa EXACTAMENTE estos slugs):
- cultural: {cultural}
- social: {social}
- economica: {economica}
- politica: {politica}
- sanitaria: {sanitaria}
- tecnologia: {tecnologia}

⚠️ IMPORTANTE: NO pongas "cultural" por defecto. Lee la descripción y razona qué categoría encaja mejor.

GUÍA DE CLASIFICACIÓN DETALLADA:

📚 CULTURAL - Solo para arte y entretenimiento:
   ✓ Conciertos, teatro, danza, ópera, ballet
   ✓ Exposiciones de arte, museos, galerías
   ✓ Cine, proyecciones, festivales de cine
   ✓ Literatura: presentaciones de libros, lecturas poéticas
   ✓ Festivales artísticos y culturales

👥 SOCIAL - Comunidad y encuentros:
   ✓ Fiestas populares, romerías, verbenas, carnavales
   ✓ Encuentros vecinales, reuniones de barrio
   ✓ Actividades para mayores, tercera edad
   ✓ Voluntariado, acciones solidarias, ONGs
   ✓ Eventos religiosos/festividades patronales → social (no cultural)
   ✓ Mercadillos solidarios, rastros benéficos

💼 ECONOMICA - Trabajo y negocios:
   ✓ Ferias de empleo, bolsas de trabajo
   ✓ Cursos de emprendimiento, startups
   ✓ Networking empresarial, B2B
   ✓ Formación profesional, FP
   ✓ Ferias comerciales, exposiciones de productos

🗳️ POLITICA - Participación ciudadana:
   ✓ Plenos municipales, asambleas
   ✓ Debates políticos, mítines
   ✓ Presupuestos participativos
   ✓ Consultas ciudadanas

🏥 SANITARIA - Salud y bienestar:
   ✓ Yoga, pilates, meditación, mindfulness
   ✓ Charlas de salud, prevención
   ✓ Campañas de vacunación, donación de sangre
   ✓ Talleres de nutrición, vida saludable
   ✓ Salud mental, bienestar emocional

💻 TECNOLOGIA - Digital y tech:
   ✓ Talleres de programación, coding
   ✓ Charlas sobre IA, blockchain, tech
   ✓ Robótica, makers, Arduino
   ✓ Videojuegos, esports, gaming
   ✓ Alfabetización digital para mayores → [tecnologia, social]

EJEMPLOS CONCRETOS:
- "Festividad de la Virgen de Candelaria" → ["social"] (fiesta patronal, NO cultural)
- "Yoga al aire libre en el parque" → ["sanitaria"] (bienestar, NO cultural)
- "Taller de introducción a Python" → ["tecnologia"]
- "Mercadillo solidario navideño" → ["social", "economica"]
- "Concierto de jazz en el auditorio" → ["cultural"]
- "Feria de empleo juvenil" → ["economica"]
- "Carnaval de Santa Cruz" → ["social", "cultural"] (fiesta popular primero)
- "Charla: Cómo crear tu startup" → ["economica"]
- "Pleno municipal extraordinario" → ["politica"]
- "Exposición de pintura contemporánea" → ["cultural"]
- "Encuentro de jubilados" → ["social"]
- "Hackathon de IA" → ["tecnologia"]

REGLAS:
1. Asigna 1-3 categorías. La PRIMERA es la principal.
2. Si hay duda entre cultural y social, piensa: ¿es arte/entretenimiento o es comunidad/encuentro?
3. Las fiestas patronales, romerías y carnavales son SOCIAL, no cultural.
4. Yoga, meditación, bienestar = SANITARIA, no cultural.

REGLAS PARA PRECIO (INFERIR CON CONTEXTO - REVISAR CAMPO "venue"):
IMPORTANTE: Revisa el campo "venue" de cada evento para inferir si es gratis.

- "is_free": true si dice "gratuito/gratis/entrada libre" O si el VENUE es público (ver lista abajo)
- "is_free": false si hay PRECIO EXPLÍCITO (número en euros) o dice "venta de entradas/taquilla"
- "is_free": null SOLO cuando el venue es desconocido/privado Y no hay ninguna pista
- "price": número en euros o null
- "price_details": info adicional (descuentos, precios reducidos, etc.)

HEURÍSTICAS PARA INFERIR GRATUITO (is_free=true) - REVISA EL CAMPO "venue":
Lugares públicos/gubernamentales (asumir GRATIS si no hay precio):
- Bibliotecas públicas/municipales/regionales → is_free=true
- Museos públicos/gubernamentales → is_free=true
- Archivos históricos/regionales → is_free=true
- Casas de cultura municipales → is_free=true
- Centros cívicos/culturales públicos → is_free=true

Tipos de evento típicamente gratuitos (asumir GRATIS):
- Exposiciones en espacios públicos → is_free=true
- Cuentacuentos infantiles en bibliotecas → is_free=true
- Talleres infantiles/familiares en centros públicos → is_free=true
- Carnavales, murgas, comparsas → is_free=true
- Fiestas patronales, romerías → is_free=true
- Cabalgatas, desfiles, procesiones → is_free=true
- Conciertos en plazas/parques públicos → is_free=true
- Fuegos artificiales, verbenas → is_free=true
- Ferias del libro (acceso) → is_free=true

HEURÍSTICAS PARA INFERIR DE PAGO (is_free=false):
- Conciertos de artistas/bandas conocidas en auditorios/teatros → is_free=false
- Obras de teatro en teatros comerciales → is_free=false
- Eventos con "entradas a la venta", "taquilla" → is_free=false

EJEMPLOS:
  - "Entrada: 10€" → is_free=false, price=10.0
  - "Gratuito" / "Gratis" / "Entrada libre" → is_free=true
  - "Cuentacuentos en Biblioteca de Navarra" → is_free=true (biblioteca pública)
  - "Exposición en Museo de Navarra" → is_free=true (museo público)
  - "Taller infantil en Casa de Cultura" → is_free=true (centro público)
  - "Concierto de Rosalía en WiZink Center" → is_free=false (artista conocida, venue comercial)
  - "15€ (reducida 10€)" → is_free=false, price=15.0, price_details="Reducida 10€"
  - "Venta de entradas en taquilla" → is_free=false
  - Evento en venue desconocido sin ninguna pista → is_free=null

IMPORTANTE: "de_pago" NO es una categoría válida. Las categorías son SOLO: cultural, social, economica, politica, sanitaria, tecnologia.

REGLAS PARA IMAGE_KEYWORDS (MUY IMPORTANTE - genera 3 keywords en INGLÉS):

OBJETIVO: Buscar fotos en Unsplash que representen VISUALMENTE el evento.

CÓMO GENERAR BUENAS KEYWORDS:
1. Lee el título y descripción del evento
2. Identifica la ACTIVIDAD PRINCIPAL (qué está pasando)
3. Identifica ELEMENTOS VISUALES distintivos (escenario, instrumentos, materiales, entorno)
4. Genera 3 keywords que describan la ESCENA que alguien vería en el evento

⚠️ IMPORTANTE - COHERENCIA GEOGRÁFICA:
Todos estos eventos son en ESPAÑA. Las keywords deben generar imágenes coherentes con el contexto:
- Si el evento es sobre vino/vendimia → evita que salgan bodegas francesas o californianas
- Si es agricultura/campo → evita campos de arroz asiáticos o granjas americanas
- Si es danza tradicional → evita danzas de otros continentes
- Si es una fiesta popular → evita festivales de otros países

Añade contexto geográfico SOLO cuando sea necesario para evitar confusión:
- "vineyard" genérico puede dar Francia → mejor "vineyard Spain" o "Mediterranean vineyard"
- "traditional dance" puede dar cualquier país → mejor especificar el tipo (flamenco, jota, etc.)
- "city street festival" sin contexto puede dar Asia → mejor "European street festival"

NO es necesario forzar "Spain" en todas las keywords, solo cuando la keyword genérica pueda dar resultados de otros países.

EJEMPLOS:
- Concierto de rock → ["rock concert", "live music stage", "concert crowd"] (no necesita contexto geográfico)
- Exposición de arte → ["art exhibition", "gallery visitors", "paintings"] (universal)
- Taller de cerámica tradicional → ["pottery workshop", "ceramic art", "Spanish crafts"] (añadir "Spanish" da coherencia)
- Vendimia → ["grape harvest", "vineyard workers", "wine region Spain"] (evitar fotos de Napa Valley)
- Yoga en la playa → ["beach yoga", "sunset meditation", "seaside wellness"] (universal)
- Romería/procesión → ["religious procession", "Spanish tradition", "village celebration"] (contexto español)

EVENTOS A CLASIFICAR:
{events_json}

REGLAS PARA SUMMARY:
- El summary debe AÑADIR VALOR, no repetir el título
- Describe QUÉ ofrece el evento, para QUIÉN es, o por qué es interesante
- Longitud ideal: 80-150 caracteres
- Si no hay info suficiente, pon null

REGLAS PARA DESCRIPTION (MUY IMPORTANTE para fuentes SPA/web):
- Si la descripción original tiene MENOS de 250 caracteres → GENERA una descripción más completa
- Si la descripción original tiene MÁS de 250 caracteres → pon null (usamos la original)
- La descripción generada debe tener 300-500 caracteres
- Incluye: qué es el evento, qué se puede esperar, a quién va dirigido, por qué es interesante
- Usa tono informativo y atractivo, sin ser demasiado promocional
- Ejemplo: "Este espectáculo teatral nos transporta a los años 80 a través de la historia de una mujer que lucha por salir adelante. La obra combina humor y drama en una puesta en escena que ha cosechado excelentes críticas. Ideal para amantes del teatro y quienes buscan una velada entretenida con reflexión sobre la época."

REGLAS PARA PRICE_DETAILS (información de precios):
- NO repitas simplemente el precio numérico (ese ya está en "price")
- price_details debe contener INFO ADICIONAL ÚTIL como:
  * Descuentos disponibles (estudiantes, jubilados, grupos, socios)
  * Qué incluye el precio (material, coffee break, certificado, etc.)
  * Tipos de entrada (general, VIP, anticipada vs taquilla)
  * Información de reserva/compra
- Si no hay info de precio o el evento es gratuito → pon null
- Si solo hay un precio sin detalles adicionales → intenta inferir detalles típicos del tipo de evento
- Ejemplos buenos:
  * "Entrada general. Descuento del 20% para menores de 25 años y mayores de 65."
  * "Incluye acceso a todas las actividades. Grupos (+10 personas): consultar."
  * "Venta anticipada online. Niños menores de 3 años gratis."
- Ejemplos malos (evitar):
  * "10€" (redundante con price)
  * "Desde 10€" (redundante)
  * "Precio: 10 euros" (redundante)

Responde SOLO con JSON válido (array de objetos):
[
  {{
    "event_id": "...",
    "category_slugs": ["cultural"],
    "summary": "Resumen corto (max 150 chars) o null",
    "description": "Descripción más larga si no hay original (max 500 chars) o null",
    "image_keywords": ["keyword1", "keyword2", "keyword3"],
    "age_range": "infantil|familiar|adultos|mayores|todos",
    "is_free": true,
    "price": null,
    "price_details": null
  }}
]"""


class LLMEnricher:
    """Smart LLM-based event enricher with batch processing."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Groq | OpenAI | None = None
        self._cache: dict[str, EventEnrichment] = {}

    @property
    def provider(self) -> str:
        """Get the configured LLM provider."""
        return self.settings.llm_provider

    @property
    def client(self) -> Groq | OpenAI:
        """Lazy initialization of LLM client (Groq or Ollama)."""
        if self._client is None:
            if self.provider == "ollama":
                if not self.settings.ollama_url:
                    raise ValueError("OLLAMA_URL not configured")
                # Ollama uses OpenAI-compatible API
                # Longer timeout for self-hosted Ollama (slower than cloud APIs)
                self._client = OpenAI(
                    base_url=f"{self.settings.ollama_url}/v1",
                    api_key="ollama",  # Ollama doesn't need real API key
                    timeout=180.0,  # 3 minutes for slower VPS
                )
                logger.info("llm_client_initialized", provider="ollama", url=self.settings.ollama_url)
            else:
                if not self.settings.groq_api_key:
                    raise ValueError("GROQ_API_KEY not configured")
                self._client = Groq(api_key=self.settings.groq_api_key)
                logger.info("llm_client_initialized", provider="groq")
        return self._client

    @property
    def is_enabled(self) -> bool:
        """Check if LLM enrichment is enabled."""
        if self.provider == "ollama":
            return self.settings.llm_enabled and bool(self.settings.ollama_url)
        return self.settings.llm_enabled and bool(self.settings.groq_api_key)

    def get_model_for_tier(self, tier: SourceTier) -> str:
        """Get the appropriate LLM model for a source tier.

        Tier strategy (Groq):
        - ORO: gpt-oss-120b - Fast, structured data (clean JSON)
        - PLATA: llama-3.3-70b - Balanced (semi-structured HTML)
        - BRONCE: kimi-k2-0905 - Deep reasoning (chaotic websites)
        - FILTER: llama-3.1-8b - Pre-processing (cheap, fast)

        For Ollama: Uses configured ollama_model for all tiers (no rate limits)
        """
        # Ollama uses single model for all tiers (simpler, no rate limits)
        if self.provider == "ollama":
            return self.settings.ollama_model

        tier_to_model = {
            EnricherTier.ORO: self.settings.llm_model_oro,
            EnricherTier.PLATA: self.settings.llm_model_plata,
            EnricherTier.BRONCE: self.settings.llm_model_bronce,
            EnricherTier.FILTER: self.settings.llm_model_filter,
        }
        return tier_to_model.get(tier, self.settings.groq_model)

    def _prepare_event_for_llm(self, event: dict[str, Any]) -> dict[str, str | int]:
        """Prepare event data for LLM prompt (minimal fields)."""
        description = (event.get("description", "") or "")

        # Build location string for regional context
        location_parts = []
        city = event.get("city", "") or ""
        province = event.get("province", "") or ""
        ccaa = event.get("comunidad_autonoma", "") or ""
        if city:
            location_parts.append(city)
        if province and province != city:
            location_parts.append(province)
        if ccaa:
            location_parts.append(ccaa)
        location = ", ".join(location_parts) if location_parts else "España"

        return {
            "id": str(event.get("id", event.get("external_id", "unknown"))),
            "title": (event.get("title", "") or "")[:200],
            "description": description[:500],
            "description_length": len(description),  # So LLM knows if it needs to expand
            "venue": (event.get("venue_name", "") or "")[:100],
            "location": location,  # Regional context for image keywords
            "type": (event.get("@type", "") or "").split("/")[-1],
            "audience": event.get("audience", "") or "",
            "price_info": event.get("price_info", "") or event.get("price_raw", "") or "",
        }

    def enrich_batch(
        self,
        events: list[dict[str, Any]],
        batch_size: int = 20,
        skip_with_image: bool = True,
        tier: EnricherTier = EnricherTier.ORO,
    ) -> dict[str, EventEnrichment]:
        """Enrich all events using LLM for categorization.

        Args:
            events: Raw events from API
            batch_size: Events per LLM call
            skip_with_image: Skip image_keywords for events that already have images
            tier: Source quality tier (ORO, PLATA, BRONCE) - determines LLM model

        Returns:
            Dict mapping event_id to EventEnrichment
        """
        if not self.is_enabled:
            logger.info("llm_enricher_disabled")
            return {}

        # Get model for this tier
        model = self.get_model_for_tier(tier)
        logger.info("enricher_using_model", tier=tier.value, model=model, total_events=len(events))

        results: dict[str, EventEnrichment] = {}

        # Process all events through LLM in batches
        for i in range(0, len(events), batch_size):
            batch = events[i : i + batch_size]
            batch_results = self._process_batch(batch, model=model)
            results.update(batch_results)
            logger.info("batch_complete", batch_num=i // batch_size + 1, enriched=len(batch_results))

        logger.info("enrichment_complete", total=len(events), enriched=len(results))
        return results

    def _process_batch(self, events: list[dict[str, Any]], model: str | None = None) -> dict[str, EventEnrichment]:
        """Process a single batch with LLM."""
        if not events:
            return {}

        # Use provided model or fallback to default
        use_model = model or self.settings.groq_model

        # Prepare minimal event data for prompt
        events_data = [self._prepare_event_for_llm(e) for e in events]
        events_json = json.dumps(events_data, ensure_ascii=False, indent=2)

        prompt = BATCH_CLASSIFICATION_PROMPT.format(
            events_json=events_json,
            **DB_CATEGORIES,
        )

        try:
            response = self.client.chat.completions.create(
                model=use_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un clasificador de eventos experto. Respondes SOLO en JSON válido.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4000,
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("llm_empty_response")
                return {}

            # Clean potential markdown code blocks
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            # Parse response
            enrichments_data = json.loads(content)

            results: dict[str, EventEnrichment] = {}
            for item in enrichments_data:
                try:
                    # Validate category_slugs - filter to only valid categories
                    slugs = item.get("category_slugs", [])
                    if isinstance(slugs, str):
                        slugs = [slugs]  # Handle single string
                    valid_slugs = [s for s in slugs if s in DB_CATEGORIES]
                    if not valid_slugs:
                        valid_slugs = ["cultural"]  # Default fallback
                    item["category_slugs"] = valid_slugs

                    enrichment = EventEnrichment(**item)
                    results[enrichment.event_id] = enrichment
                except Exception as e:
                    logger.warning("parse_enrichment_error", error=str(e), item=str(item)[:100])

            logger.info("batch_processed", batch_size=len(events), enriched=len(results))
            return results

        except json.JSONDecodeError as e:
            logger.error("llm_json_error", error=str(e), content=content[:200] if content else "")
            return {}
        except Exception as e:
            logger.error("llm_batch_error", error=str(e))
            return {}

    # ============================================================
    # DEEP ENRICHMENT (Fase 1: Organizador, Contacto, Accesibilidad)
    # ============================================================

    def _fetch_page_content(self, url: str) -> str | None:
        """Fetch page content using Firecrawl for Markdown conversion."""
        import requests

        firecrawl_url = self.settings.firecrawl_url
        if not firecrawl_url:
            firecrawl_url = "https://firecrawl.si-erp.cloud/scrape"

        try:
            response = requests.post(
                firecrawl_url,
                json={"url": url},
                timeout=60
            )
            if response.status_code == 200:
                data = response.json()
                # Firecrawl returns markdown content
                return data.get("markdown") or data.get("content", "")
            else:
                logger.warning("firecrawl_fetch_error", url=url, status=response.status_code)
        except Exception as e:
            logger.error("firecrawl_exception", url=url, error=str(e))
        return None

    def enrich_deep(
        self,
        event_id: str,
        content: str,
        event_url: str | None = None,
        organizer_url: str | None = None,
        venue_url: str | None = None,
        tier: SourceTier = SourceTier.BRONCE,
    ) -> DeepEnrichment | None:
        """Extract deep enrichment data (organizer, contact, accessibility).

        Args:
            event_id: Unique event identifier
            content: Page content (Markdown or HTML) to analyze
            event_url: Original event URL (for re-fetching if needed)
            organizer_url: URL of organizer website (if known)
            venue_url: URL of venue website (for accessibility info)
            tier: Source tier for model selection

        Returns:
            DeepEnrichment with extracted data, or None on failure
        """
        if not self.is_enabled:
            return None

        model = self.get_model_for_tier(tier)

        # Truncate content to avoid token limits (keep most relevant parts)
        content_truncated = content[:6000] if content else ""

        prompt = DEEP_ENRICHMENT_PROMPT.format(
            event_id=event_id,
            content=content_truncated
        )

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un extractor de datos. Respondes SOLO en JSON válido. NO inventes datos.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,  # Deterministic for extraction
                max_tokens=1500,
            )

            content_response = response.choices[0].message.content
            if not content_response:
                return None

            # Clean markdown code blocks
            content_response = content_response.strip()
            if content_response.startswith("```"):
                content_response = content_response.split("```")[1]
                if content_response.startswith("json"):
                    content_response = content_response[4:]
            content_response = content_response.strip()

            # Parse JSON
            data = json.loads(content_response)

            # Build DeepEnrichment
            enrichment = DeepEnrichment(
                event_id=event_id,
                organizer=OrganizerInfo(**data.get("organizer", {})) if data.get("organizer") else None,
                contact=ContactInfo(**data.get("contact", {})) if data.get("contact") else None,
                registration=RegistrationInfo(**data.get("registration", {})) if data.get("registration") else None,
                accessibility=AccessibilityInfo(**data.get("accessibility", {})) if data.get("accessibility") else None,
            )

            # Track what was found
            if enrichment.organizer and enrichment.organizer.name:
                enrichment.has_organizer = True
            if enrichment.accessibility:
                acc = enrichment.accessibility
                enrichment.has_accessibility = (
                    acc.wheelchair_accessible or acc.sign_language or
                    acc.hearing_loop or acc.braille_materials or
                    bool(acc.other_facilities)
                )

            logger.info(
                "deep_enrichment_complete",
                event_id=event_id,
                has_organizer=enrichment.has_organizer,
                has_accessibility=enrichment.has_accessibility,
            )

            # If no accessibility found and we have venue_url, investigate venue page
            if not enrichment.has_accessibility and venue_url:
                enrichment = self._investigate_venue_accessibility(enrichment, venue_url, model)

            # If no organizer logo and we have organizer_url, investigate
            if enrichment.organizer and enrichment.organizer.name and not enrichment.organizer.logo_url and organizer_url:
                enrichment = self._investigate_organizer_logo(enrichment, organizer_url)

            return enrichment

        except json.JSONDecodeError as e:
            logger.error("deep_enrichment_json_error", event_id=event_id, error=str(e))
        except Exception as e:
            logger.error("deep_enrichment_error", event_id=event_id, error=str(e))

        return None

    def _investigate_venue_accessibility(
        self,
        enrichment: DeepEnrichment,
        venue_url: str,
        model: str
    ) -> DeepEnrichment:
        """Fetch venue page and extract accessibility info."""
        logger.info("investigating_venue_accessibility", url=venue_url)

        venue_content = self._fetch_page_content(venue_url)
        if not venue_content:
            return enrichment

        # Simple prompt focused only on accessibility
        prompt = f"""Analiza esta página de un recinto/venue y extrae SOLO información de accesibilidad.
SOLO marca true si hay evidencia EXPLÍCITA. Sin evidencia = false.

Keywords: "silla de ruedas", "rampa", "ascensor", "PMR", "accesible", "lengua de signos", "bucle magnético", "braille"

Responde SOLO este JSON:
{{
  "wheelchair_accessible": false,
  "sign_language": false,
  "hearing_loop": false,
  "braille_materials": false,
  "other_facilities": null,
  "notes": null
}}

CONTENIDO:
{venue_content[:4000]}"""

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Extractor de accesibilidad. Solo JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=500,
            )

            content = response.choices[0].message.content
            if content:
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                content = content.strip()

                acc_data = json.loads(content)
                enrichment.accessibility = AccessibilityInfo(**acc_data)

                # Update has_accessibility flag
                acc = enrichment.accessibility
                enrichment.has_accessibility = (
                    acc.wheelchair_accessible or acc.sign_language or
                    acc.hearing_loop or acc.braille_materials or
                    bool(acc.other_facilities)
                )

                if enrichment.has_accessibility:
                    logger.info("venue_accessibility_found", url=venue_url)

        except Exception as e:
            logger.warning("venue_accessibility_error", url=venue_url, error=str(e))

        return enrichment

    def _investigate_organizer_logo(
        self,
        enrichment: DeepEnrichment,
        organizer_url: str
    ) -> DeepEnrichment:
        """Fetch organizer page and extract logo URL."""
        logger.info("investigating_organizer_logo", url=organizer_url)

        org_content = self._fetch_page_content(organizer_url)
        if not org_content:
            return enrichment

        # Look for logo in meta tags or common patterns
        import re

        # Common logo patterns in HTML/Markdown
        logo_patterns = [
            r'og:image["\s]+content=["\']([^"\']+)["\']',
            r'logo["\s:]+["\']?(https?://[^\s"\'<>]+(?:\.png|\.jpg|\.jpeg|\.svg|\.webp))',
            r'<img[^>]+class=["\'][^"\']*logo[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
            r'!\[.*?logo.*?\]\((https?://[^\)]+)\)',  # Markdown image with "logo"
        ]

        for pattern in logo_patterns:
            match = re.search(pattern, org_content, re.IGNORECASE)
            if match:
                logo_url = match.group(1)
                if logo_url.startswith("http"):
                    enrichment.organizer.logo_url = logo_url
                    logger.info("organizer_logo_found", url=logo_url)
                    break

        return enrichment

    def enrich_deep_batch(
        self,
        events: list[dict[str, Any]],
        tier: SourceTier = SourceTier.BRONCE,
    ) -> dict[str, DeepEnrichment]:
        """Batch deep enrichment for multiple events.

        Args:
            events: List of events with 'external_id', 'content' or 'description'
            tier: Source tier for model selection

        Returns:
            Dict mapping event_id to DeepEnrichment
        """
        results: dict[str, DeepEnrichment] = {}

        for event in events:
            event_id = event.get("external_id") or event.get("id")
            if not event_id:
                continue

            content = event.get("page_content") or event.get("description") or ""
            if not content:
                continue

            enrichment = self.enrich_deep(
                event_id=str(event_id),
                content=content,
                event_url=event.get("external_url"),
                organizer_url=event.get("organizer_url"),
                venue_url=event.get("venue_url"),
                tier=tier,
            )

            if enrichment:
                results[str(event_id)] = enrichment

        logger.info("deep_enrichment_batch_complete", total=len(events), enriched=len(results))
        return results


# Singleton
_enricher: LLMEnricher | None = None


def get_llm_enricher() -> LLMEnricher:
    """Get singleton LLM enricher instance."""
    global _enricher
    if _enricher is None:
        _enricher = LLMEnricher()
    return _enricher
