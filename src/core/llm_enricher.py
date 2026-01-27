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


class SourceTier(str, Enum):
    """Quality tier of data source - determines which LLM model to use."""

    ORO = "oro"  # Clean JSON APIs - use gpt-oss-120b (fast, structured)
    PLATA = "plata"  # Semi-structured HTML - use llama-3.3-70b (balanced)
    BRONCE = "bronce"  # Chaotic websites - use kimi-k2 (deep reasoning)
    FILTER = "filter"  # Pre-processing filter - use llama-3.1-8b (fast, cheap)


# ============================================================
# DB CATEGORIES - Must match Supabase categories table
# ============================================================
DB_CATEGORIES = {
    "cultural": "Eventos artísticos, teatro, música, cine, exposiciones, danza, literatura",
    "social": "Eventos comunitarios, solidarios, vecinales, voluntariado, tercera edad",
    "economica": "Empleo, emprendimiento, ferias comerciales, networking empresarial",
    "politica": "Plenos, debates, participación ciudadana, elecciones",
    "sanitaria": "Salud, bienestar, prevención, talleres de salud mental, primeros auxilios",
    "tecnologia": "Tecnología, programación, talleres digitales, IA, robótica, videojuegos",
}


class EventEnrichment(BaseModel):
    """Enriched data for a single event."""

    event_id: str
    category_slugs: list[str] = Field(
        default_factory=list,
        description="1-3 categories from: cultural, social, economica, politica, sanitaria, tecnologia"
    )
    summary: str | None = Field(default=None, max_length=200, description="Resumen conciso del evento")
    image_keywords: list[str] = Field(default_factory=list, description="3 keywords en inglés para buscar imagen")
    age_range: str | None = Field(default=None, description="Rango de edad: infantil, familiar, adultos, mayores, todos")
    price: float | None = Field(default=None, description="Precio numérico en euros (null si gratuito o no especificado)")
    price_details: str | None = Field(default=None, description="Info adicional: descuentos, precios reducidos, etc.")


class BatchEnrichmentResult(BaseModel):
    """Result of batch enrichment."""

    events: list[EventEnrichment]


# Prompt optimizado para clasificación batch con múltiples categorías
BATCH_CLASSIFICATION_PROMPT = """Clasifica estos eventos asignando las categorías que mejor se adapten.

CATEGORÍAS DISPONIBLES (usa EXACTAMENTE estos slugs):
- cultural: {cultural}
- social: {social}
- economica: {economica}
- politica: {politica}
- sanitaria: {sanitaria}
- tecnologia: {tecnologia}

REGLAS DE CLASIFICACIÓN:
1. Asigna 1-3 categorías según el evento. La PRIMERA es la principal.
2. Un evento puede tener múltiples categorías si aplica (ej: "Taller de emprendimiento social" → ["economica", "social"])
3. "cultural" incluye: conciertos, teatro, danza, exposiciones, cine, música, literatura, festivales artísticos
4. "tecnologia" es para: programación, informática, robótica, IA, videojuegos, talleres digitales
5. "sanitaria" incluye: salud, yoga, meditación, bienestar, prevención
6. "social" incluye: encuentros vecinales, solidaridad, voluntariado, tercera edad
7. "economica" incluye: empleo, emprendimiento, networking, ferias comerciales
8. "politica" incluye: participación ciudadana, plenos, debates políticos

REGLAS PARA PRECIO (MUY IMPORTANTE - usa el campo "price_info"):
- "price": número en euros (ej: 5.0, 12.50) o null si gratuito/no especificado
- "price_details": info ADICIONAL como "50% dto socios", "Niños gratis", "Entrada reducida 8€"
- EXTRAE EL PRIMER PRECIO NUMÉRICO que encuentres:
  - "Entrada: 10€" → price=10.0
  - "Preus: 10 € i 22 €" → price=10.0, price_details="También 22€"
  - "Matrícula: 10 euros cada sesión" → price=10.0, price_details="cada sesión"
  - "Preu: 15 €" → price=15.0
  - "15€ (reducida 10€, socios gratis)" → price=15.0, price_details="Reducida 10€, socios gratis"
  - "Gratuito" / "Gratuït" / "Gratis" → price=null
  - "Entrada libre" / "Entrada lliure" → price=null
- Si hay MÚLTIPLES PRECIOS, usa el principal/general (no el reducido)

REGLAS PARA IMAGE_KEYWORDS:
- Deben describir VISUALMENTE el evento para buscar fotos en Unsplash
- Usa keywords en INGLÉS que describan la escena
- Piensa: "¿qué foto ilustraría este evento?"

EVENTOS A CLASIFICAR:
{events_json}

REGLAS PARA SUMMARY:
- El summary debe AÑADIR VALOR, no repetir el título
- Describe QUÉ ofrece el evento, para QUIÉN es, o por qué es interesante
- Si no hay info suficiente, pon null

Responde SOLO con JSON válido (array de objetos):
[
  {{
    "event_id": "...",
    "category_slugs": ["cultural"],
    "summary": "Descripción útil (max 150 chars) o null",
    "image_keywords": ["keyword1", "keyword2", "keyword3"],
    "age_range": "infantil|familiar|adultos|mayores|todos",
    "price": 10.0,
    "price_details": "Reducida 8€, socios gratis"
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
            SourceTier.ORO: self.settings.llm_model_oro,
            SourceTier.PLATA: self.settings.llm_model_plata,
            SourceTier.BRONCE: self.settings.llm_model_bronce,
            SourceTier.FILTER: self.settings.llm_model_filter,
        }
        return tier_to_model.get(tier, self.settings.groq_model)

    def _prepare_event_for_llm(self, event: dict[str, Any]) -> dict[str, str]:
        """Prepare event data for LLM prompt (minimal fields)."""
        return {
            "id": str(event.get("id", event.get("external_id", "unknown"))),
            "title": (event.get("title", "") or "")[:200],
            "description": (event.get("description", "") or "")[:500],
            "type": (event.get("@type", "") or "").split("/")[-1],
            "audience": event.get("audience", "") or "",
            "price_info": event.get("price_info", "") or "",
        }

    def enrich_batch(
        self,
        events: list[dict[str, Any]],
        batch_size: int = 20,
        skip_with_image: bool = True,
        tier: SourceTier = SourceTier.ORO,
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

# Singleton
_enricher: LLMEnricher | None = None


def get_llm_enricher() -> LLMEnricher:
    """Get singleton LLM enricher instance."""
    global _enricher
    if _enricher is None:
        _enricher = LLMEnricher()
    return _enricher
