"""Embeddings client using Ollama with BGE-M3 model."""

import httpx
from typing import Any

from src.config.settings import get_settings
from src.logging.logger import get_logger

logger = get_logger(__name__)

# Default Ollama configuration
DEFAULT_OLLAMA_URL = "https://ollama.si-erp.cloud"
DEFAULT_MODEL = "bge-m3:latest"
EMBEDDING_DIMENSIONS = 1024  # BGE-M3 default


class EmbeddingsClient:
    """Client for generating embeddings using Ollama."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize embeddings client.

        Args:
            base_url: Ollama API URL (default: from settings or DEFAULT_OLLAMA_URL)
            model: Model name (default: bge-m3:latest)
            timeout: Request timeout in seconds
        """
        settings = get_settings()
        self.base_url = base_url or getattr(settings, 'ollama_url', None) or DEFAULT_OLLAMA_URL
        self.model = model or getattr(settings, 'embedding_model', None) or DEFAULT_MODEL
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Lazy initialization of HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def generate(self, text: str) -> list[float] | None:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats (embedding vector) or None on error
        """
        if not text or not text.strip():
            return None

        try:
            response = self.client.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model,
                    "input": text.strip()[:8000],  # Truncate to avoid token limit
                },
            )
            response.raise_for_status()
            data = response.json()

            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]

            return None

        except Exception as e:
            logger.warning("embedding_error", error=str(e), text_preview=text[:50])
            return None

    def generate_batch(self, texts: list[str], show_progress: bool = True) -> list[list[float] | None]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            show_progress: Print progress

        Returns:
            List of embeddings (same order as input, None for failed items)
        """
        results: list[list[float] | None] = []

        for i, text in enumerate(texts):
            if show_progress and (i + 1) % 10 == 0:
                logger.info("embedding_progress", current=i + 1, total=len(texts))

            embedding = self.generate(text)
            results.append(embedding)

        success_count = sum(1 for e in results if e is not None)
        logger.info("batch_embeddings_complete", total=len(texts), success=success_count)

        return results

    def generate_for_event(self, title: str, description: str | None = None) -> list[float] | None:
        """Generate embedding for an event using title + description.

        Args:
            title: Event title
            description: Event description (optional)

        Returns:
            Embedding vector or None
        """
        # Combine title and description for richer embedding
        text_parts = [title]
        if description:
            # Take first 500 chars of description to keep embedding focused
            text_parts.append(description[:500])

        combined_text = " | ".join(text_parts)
        return self.generate(combined_text)

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


# Singleton instance
_client: EmbeddingsClient | None = None


def get_embeddings_client() -> EmbeddingsClient:
    """Get or create embeddings client singleton."""
    global _client
    if _client is None:
        _client = EmbeddingsClient()
    return _client
