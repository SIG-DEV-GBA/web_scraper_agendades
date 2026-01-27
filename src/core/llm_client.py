"""LLM client for event enrichment using Groq."""

import json
from typing import Any

from groq import Groq
from pydantic import BaseModel

from src.config.settings import get_settings
from src.logging.logger import get_logger

logger = get_logger(__name__)


class EnrichedEvent(BaseModel):
    """Model for LLM-enriched event data."""

    summary: str | None = None  # Short summary (max 150 chars)
    category: str | None = None  # Normalized category
    tags: list[str] = []  # Extracted keywords/tags
    target_audience: str | None = None  # Público objetivo normalizado


# Categorías válidas para agendades.es (ajustar según esquema real)
VALID_CATEGORIES = [
    "teatro",
    "música",
    "danza",
    "cine",
    "exposición",
    "conferencia",
    "taller",
    "infantil",
    "festival",
    "feria",
    "deportes",
    "gastronomía",
    "literatura",
    "circo",
    "magia",
    "otros",
]

ENRICHMENT_PROMPT = """Analiza este evento cultural y extrae información estructurada.

EVENTO:
Título: {title}
Descripción: {description}
Tipo original: {category_raw}
Audiencia: {audience}

INSTRUCCIONES:
1. summary: Resumen conciso del evento (máximo 150 caracteres). Solo el contenido esencial.
2. category: Clasifica en UNA de estas categorías: {categories}
3. tags: Lista de 3-5 palabras clave relevantes (en español)
4. target_audience: Público objetivo (ej: "familiar", "adultos", "infantil", "todos")

Responde SOLO con JSON válido, sin explicaciones:
{{"summary": "...", "category": "...", "tags": ["...", "..."], "target_audience": "..."}}"""


class LLMClient:
    """Client for LLM-based event enrichment."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Groq | None = None

    @property
    def client(self) -> Groq:
        """Lazy initialization of Groq client."""
        if self._client is None:
            if not self.settings.groq_api_key:
                raise ValueError("GROQ_API_KEY not configured")
            self._client = Groq(api_key=self.settings.groq_api_key)
        return self._client

    @property
    def is_enabled(self) -> bool:
        """Check if LLM enrichment is enabled and configured."""
        return self.settings.llm_enabled and bool(self.settings.groq_api_key)

    def enrich_event(self, event_data: dict[str, Any]) -> EnrichedEvent | None:
        """Enrich a single event with LLM.

        Args:
            event_data: Raw event data with title, description, etc.

        Returns:
            EnrichedEvent with summary, category, tags, or None if failed
        """
        if not self.is_enabled:
            logger.debug("llm_disabled", reason="LLM not enabled or no API key")
            return None

        title = event_data.get("title", "")
        description = event_data.get("description", "")

        # Skip if description is too short
        if len(description) < 50:
            logger.debug("llm_skip_short", title=title, desc_len=len(description))
            return None

        prompt = ENRICHMENT_PROMPT.format(
            title=title,
            description=description[:1500],  # Truncate to save tokens
            category_raw=event_data.get("category_raw", ""),
            audience=event_data.get("audience", ""),
            categories=", ".join(VALID_CATEGORIES),
        )

        try:
            response = self.client.chat.completions.create(
                model=self.settings.groq_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Eres un asistente que clasifica eventos culturales. Respondes solo en JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,  # Low temperature for consistent output
                max_tokens=300,
            )

            content = response.choices[0].message.content
            if not content:
                logger.warning("llm_empty_response", title=title)
                return None

            # Parse JSON response
            data = json.loads(content)

            # Validate category
            if data.get("category") not in VALID_CATEGORIES:
                data["category"] = "otros"

            enriched = EnrichedEvent(**data)
            logger.info(
                "llm_enriched",
                title=title[:50],
                category=enriched.category,
                tags_count=len(enriched.tags),
            )
            return enriched

        except json.JSONDecodeError as e:
            logger.warning("llm_json_error", title=title, error=str(e))
            return None
        except Exception as e:
            logger.error("llm_error", title=title, error=str(e))
            return None

    def enrich_batch(
        self, events: list[dict[str, Any]], max_events: int | None = None
    ) -> dict[str, EnrichedEvent]:
        """Enrich multiple events.

        Args:
            events: List of event data dicts
            max_events: Maximum events to process (uses settings default if None)

        Returns:
            Dict mapping event ID to EnrichedEvent
        """
        if not self.is_enabled:
            logger.info("llm_batch_disabled")
            return {}

        max_events = max_events or self.settings.llm_batch_size
        results: dict[str, EnrichedEvent] = {}

        events_to_process = events[:max_events]
        logger.info("llm_batch_start", total=len(events), processing=len(events_to_process))

        for event in events_to_process:
            event_id = str(event.get("id", event.get("external_id", "")))
            if not event_id:
                continue

            enriched = self.enrich_event(event)
            if enriched:
                results[event_id] = enriched

        logger.info("llm_batch_complete", processed=len(events_to_process), enriched=len(results))
        return results


# Singleton instance
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get singleton LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
