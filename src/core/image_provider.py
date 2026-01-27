"""Multi-provider image system with cache, randomization, and fallbacks.

Solves the problem of repeated images by:
1. Caching used URLs to avoid duplicates
2. Randomizing selection from results (not always first)
3. Cascading through multiple providers (Unsplash → Pexels → Fallback)
"""

import hashlib
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from src.config.settings import get_settings
from src.logging.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ImageResult:
    """Result from image search."""

    url: str
    url_small: str | None = None
    url_thumb: str | None = None
    provider: str = "unknown"
    author: str | None = None
    author_url: str | None = None
    source_url: str | None = None  # Link to original on provider

    def get_attribution(self) -> str:
        """Get attribution text."""
        if self.author and self.provider:
            return f"Photo by {self.author} on {self.provider.title()}"
        return f"Image from {self.provider.title()}"


# Fallback images by category (static, always available)
FALLBACK_IMAGES: dict[str, list[str]] = {
    "cultural": [
        "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800",
        "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800",
        "https://images.unsplash.com/photo-1501281668745-f7f57925c138?w=800",
    ],
    "social": [
        "https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=800",
        "https://images.unsplash.com/photo-1511632765486-a01980e01a18?w=800",
        "https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=800",
    ],
    "economica": [
        "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800",
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=800",
    ],
    "politica": [
        "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?w=800",
        "https://images.unsplash.com/photo-1555848962-6e79363ec58f?w=800",
    ],
    "sanitaria": [
        "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800",
        "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800",
    ],
    "tecnologia": [
        "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800",
        "https://images.unsplash.com/photo-1488590528505-98d2b5aba04b?w=800",
    ],
    "default": [
        "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800",
        "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800",
        "https://images.unsplash.com/photo-1505373877841-8d25f7d46678?w=800",
    ],
}


class ImageCache:
    """Persistent cache of used image URLs to avoid repetition."""

    def __init__(self, cache_file: str | None = None):
        """Initialize cache.

        Args:
            cache_file: Path to JSON file for persistence (optional)
        """
        self.cache_file = Path(cache_file) if cache_file else None
        self._used_urls: set[str] = set()
        self._keyword_to_urls: dict[str, list[str]] = {}  # keyword hash -> used URLs

        if self.cache_file and self.cache_file.exists():
            self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from file."""
        try:
            with open(self.cache_file, "r") as f:
                data = json.load(f)
                self._used_urls = set(data.get("used_urls", []))
                self._keyword_to_urls = data.get("keyword_to_urls", {})
                logger.debug("image_cache_loaded", count=len(self._used_urls))
        except Exception as e:
            logger.warning("image_cache_load_error", error=str(e))

    def _save_cache(self) -> None:
        """Save cache to file."""
        if not self.cache_file:
            return

        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump({
                    "used_urls": list(self._used_urls),
                    "keyword_to_urls": self._keyword_to_urls,
                }, f)
        except Exception as e:
            logger.warning("image_cache_save_error", error=str(e))

    def _hash_keywords(self, keywords: list[str]) -> str:
        """Create hash from keywords for lookup."""
        key = "_".join(sorted(k.lower().strip() for k in keywords))
        return hashlib.md5(key.encode()).hexdigest()[:16]

    def is_used(self, url: str) -> bool:
        """Check if URL has been used."""
        return url in self._used_urls

    def mark_used(self, url: str, keywords: list[str] | None = None) -> None:
        """Mark URL as used."""
        self._used_urls.add(url)

        if keywords:
            key = self._hash_keywords(keywords)
            if key not in self._keyword_to_urls:
                self._keyword_to_urls[key] = []
            if url not in self._keyword_to_urls[key]:
                self._keyword_to_urls[key].append(url)

        self._save_cache()

    def get_unused_from_list(self, urls: list[str]) -> str | None:
        """Get first unused URL from list."""
        for url in urls:
            if not self.is_used(url):
                return url
        return None

    def get_random_unused_from_list(self, urls: list[str], max_attempts: int = 10) -> str | None:
        """Get random unused URL from list."""
        available = [u for u in urls if not self.is_used(u)]
        if available:
            return random.choice(available)
        return None

    def clear(self) -> None:
        """Clear cache."""
        self._used_urls.clear()
        self._keyword_to_urls.clear()
        self._save_cache()

    @property
    def size(self) -> int:
        """Number of cached URLs."""
        return len(self._used_urls)


class UnsplashProvider:
    """Unsplash image provider."""

    API_URL = "https://api.unsplash.com/search/photos"

    def __init__(self, access_key: str):
        self.access_key = access_key

    def search(
        self,
        keywords: list[str],
        per_page: int = 15,
        orientation: str = "landscape",
    ) -> list[ImageResult]:
        """Search Unsplash for images.

        Args:
            keywords: Search keywords
            per_page: Number of results (max 30)
            orientation: landscape, portrait, squarish

        Returns:
            List of ImageResult objects
        """
        try:
            query = " ".join(keywords)

            with httpx.Client(timeout=10) as client:
                response = client.get(
                    self.API_URL,
                    params={
                        "query": query,
                        "per_page": min(per_page, 30),
                        "orientation": orientation,
                        "content_filter": "high",
                    },
                    headers={"Authorization": f"Client-ID {self.access_key}"},
                )

                if response.status_code == 403:
                    logger.warning("unsplash_rate_limit")
                    return []

                if response.status_code != 200:
                    logger.warning("unsplash_error", status=response.status_code)
                    return []

                data = response.json()
                results: list[ImageResult] = []

                for photo in data.get("results", []):
                    urls = photo.get("urls", {})
                    user = photo.get("user", {})

                    results.append(ImageResult(
                        url=urls.get("regular", ""),
                        url_small=urls.get("small"),
                        url_thumb=urls.get("thumb"),
                        provider="unsplash",
                        author=user.get("name"),
                        author_url=user.get("links", {}).get("html"),
                        source_url=photo.get("links", {}).get("html"),
                    ))

                logger.debug("unsplash_search", query=query, results=len(results))
                return results

        except httpx.TimeoutException:
            logger.warning("unsplash_timeout")
            return []
        except Exception as e:
            logger.error("unsplash_error", error=str(e))
            return []


class PexelsProvider:
    """Pexels image provider (fallback)."""

    API_URL = "https://api.pexels.com/v1/search"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(
        self,
        keywords: list[str],
        per_page: int = 15,
        orientation: str = "landscape",
    ) -> list[ImageResult]:
        """Search Pexels for images.

        Args:
            keywords: Search keywords
            per_page: Number of results (max 80)
            orientation: landscape, portrait, square

        Returns:
            List of ImageResult objects
        """
        try:
            query = " ".join(keywords)

            with httpx.Client(timeout=10) as client:
                response = client.get(
                    self.API_URL,
                    params={
                        "query": query,
                        "per_page": min(per_page, 80),
                        "orientation": orientation,
                    },
                    headers={"Authorization": self.api_key},
                )

                if response.status_code == 429:
                    logger.warning("pexels_rate_limit")
                    return []

                if response.status_code != 200:
                    logger.warning("pexels_error", status=response.status_code)
                    return []

                data = response.json()
                results: list[ImageResult] = []

                for photo in data.get("photos", []):
                    src = photo.get("src", {})

                    results.append(ImageResult(
                        url=src.get("large", src.get("original", "")),
                        url_small=src.get("medium"),
                        url_thumb=src.get("small"),
                        provider="pexels",
                        author=photo.get("photographer"),
                        author_url=photo.get("photographer_url"),
                        source_url=photo.get("url"),
                    ))

                logger.debug("pexels_search", query=query, results=len(results))
                return results

        except httpx.TimeoutException:
            logger.warning("pexels_timeout")
            return []
        except Exception as e:
            logger.error("pexels_error", error=str(e))
            return []


class ImageProvider:
    """Multi-provider image resolver with cache and randomization.

    Features:
    - Cascades through providers: Unsplash → Pexels → Fallback
    - Caches used URLs to avoid repetition
    - Randomizes selection from results
    - Supports keyword variations for more variety

    Example:
        ```python
        provider = ImageProvider()
        url = provider.get_image(
            keywords=["concert", "music", "piano"],
            category="cultural"
        )
        ```
    """

    def __init__(
        self,
        unsplash_key: str | None = None,
        pexels_key: str | None = None,
        cache_file: str | None = None,
    ):
        """Initialize image provider.

        Args:
            unsplash_key: Unsplash API access key
            pexels_key: Pexels API key
            cache_file: Path to cache file for persistence
        """
        settings = get_settings()

        self.unsplash = UnsplashProvider(
            unsplash_key or settings.unsplash_access_key or ""
        ) if (unsplash_key or settings.unsplash_access_key) else None

        self.pexels = PexelsProvider(
            pexels_key or getattr(settings, "pexels_api_key", "") or ""
        ) if (pexels_key or getattr(settings, "pexels_api_key", None)) else None

        self.cache = ImageCache(
            cache_file or ".cache/used_images.json"
        )

        # Track fallback usage
        self._fallback_index: dict[str, int] = {}

    def get_image(
        self,
        keywords: list[str],
        category: str = "default",
        prefer_unused: bool = True,
        randomize: bool = True,
        max_results: int = 15,
    ) -> str:
        """Get an image URL for the given keywords.

        Args:
            keywords: Search keywords (in English)
            category: Category for fallback selection
            prefer_unused: Prefer images not used before
            randomize: Randomize selection from results
            max_results: Max results to fetch from providers

        Returns:
            Image URL
        """
        if not keywords:
            return self._get_fallback(category)

        # Try Unsplash first
        if self.unsplash:
            results = self.unsplash.search(keywords, per_page=max_results)
            url = self._select_image(results, keywords, randomize, prefer_unused)
            if url:
                return url

        # Try Pexels as fallback
        if self.pexels:
            results = self.pexels.search(keywords, per_page=max_results)
            url = self._select_image(results, keywords, randomize, prefer_unused)
            if url:
                return url

        # Try with simplified keywords (just first 2)
        if len(keywords) > 2:
            simplified = keywords[:2]
            logger.debug("trying_simplified_keywords", original=keywords, simplified=simplified)

            if self.unsplash:
                results = self.unsplash.search(simplified, per_page=max_results)
                url = self._select_image(results, simplified, randomize, prefer_unused)
                if url:
                    return url

        # Final fallback
        return self._get_fallback(category)

    def get_image_full(
        self,
        keywords: list[str],
        category: str = "default",
    ) -> ImageResult | None:
        """Get full image result with metadata.

        Returns None if using fallback.
        """
        if not keywords:
            return None

        # Try Unsplash
        if self.unsplash:
            results = self.unsplash.search(keywords, per_page=15)
            if results:
                selected = self._select_image_result(results, keywords, True, True)
                if selected:
                    return selected

        # Try Pexels
        if self.pexels:
            results = self.pexels.search(keywords, per_page=15)
            if results:
                selected = self._select_image_result(results, keywords, True, True)
                if selected:
                    return selected

        return None

    def _select_image(
        self,
        results: list[ImageResult],
        keywords: list[str],
        randomize: bool,
        prefer_unused: bool,
    ) -> str | None:
        """Select an image URL from results."""
        if not results:
            return None

        urls = [r.url for r in results if r.url]

        if prefer_unused:
            if randomize:
                url = self.cache.get_random_unused_from_list(urls)
            else:
                url = self.cache.get_unused_from_list(urls)

            if url:
                self.cache.mark_used(url, keywords)
                return url

        # All used, pick random anyway
        if randomize:
            url = random.choice(urls) if urls else None
        else:
            url = urls[0] if urls else None

        if url:
            self.cache.mark_used(url, keywords)

        return url

    def _select_image_result(
        self,
        results: list[ImageResult],
        keywords: list[str],
        randomize: bool,
        prefer_unused: bool,
    ) -> ImageResult | None:
        """Select a full ImageResult from results."""
        if not results:
            return None

        if prefer_unused:
            available = [r for r in results if r.url and not self.cache.is_used(r.url)]
            if available:
                selected = random.choice(available) if randomize else available[0]
                self.cache.mark_used(selected.url, keywords)
                return selected

        # All used, pick anyway
        selected = random.choice(results) if randomize else results[0]
        if selected.url:
            self.cache.mark_used(selected.url, keywords)
        return selected

    def _get_fallback(self, category: str) -> str:
        """Get fallback image, rotating through available options."""
        images = FALLBACK_IMAGES.get(category, FALLBACK_IMAGES["default"])

        # Rotate through fallbacks
        idx = self._fallback_index.get(category, 0)
        url = images[idx % len(images)]
        self._fallback_index[category] = idx + 1

        return url

    def clear_cache(self) -> None:
        """Clear the image cache."""
        self.cache.clear()
        self._fallback_index.clear()

    @property
    def cache_size(self) -> int:
        """Number of cached image URLs."""
        return self.cache.size

    @property
    def providers_available(self) -> list[str]:
        """List of available providers."""
        providers = []
        if self.unsplash:
            providers.append("unsplash")
        if self.pexels:
            providers.append("pexels")
        providers.append("fallback")
        return providers


# Singleton
_provider: ImageProvider | None = None


def get_image_provider() -> ImageProvider:
    """Get singleton image provider instance."""
    global _provider
    if _provider is None:
        _provider = ImageProvider()
    return _provider


def reset_image_provider() -> None:
    """Reset singleton (for testing)."""
    global _provider
    _provider = None
