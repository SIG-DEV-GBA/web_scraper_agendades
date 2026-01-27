"""Image resolver using Unsplash API for event cover images."""

import httpx
from pydantic import BaseModel

from src.config.settings import get_settings
from src.logging.logger import get_logger

logger = get_logger(__name__)


class UnsplashImage(BaseModel):
    """Resolved image from Unsplash.

    IMPORTANT: Unsplash API Terms require:
    1. Hotlinking to original URLs (we do this)
    2. Triggering download endpoint when photo is used
    3. Attribution: "Photo by {author} on Unsplash" with links
    """

    url: str  # Regular size URL (good for display)
    url_small: str  # Small size for thumbnails
    url_thumb: str  # Thumbnail
    author: str  # Photographer name
    author_url: str  # Link to photographer profile
    unsplash_url: str  # Link to photo on Unsplash
    download_location: str  # Endpoint to trigger download (required by API terms)

    def get_attribution_html(self) -> str:
        """Get HTML attribution as required by Unsplash."""
        return f'Photo by <a href="{self.author_url}?utm_source=agendades&utm_medium=referral">{self.author}</a> on <a href="https://unsplash.com/?utm_source=agendades&utm_medium=referral">Unsplash</a>'

    def get_attribution_text(self) -> str:
        """Get plain text attribution."""
        return f"Photo by {self.author} on Unsplash"


# Fallback images by category when Unsplash fails or is not configured
FALLBACK_IMAGES = {
    "cultural": "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=800",  # Concert
    "social": "https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=800",  # Community
    "economica": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800",  # Business
    "politica": "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?w=800",  # City hall
    "sanitaria": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800",  # Wellness/yoga
    "tecnologia": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=800",  # Tech
    "default": "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800",  # Event
}


class ImageResolver:
    """Resolve event images using Unsplash API."""

    UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._cache: dict[str, UnsplashImage | None] = {}

    @property
    def is_enabled(self) -> bool:
        """Check if Unsplash API is configured."""
        return bool(getattr(self.settings, "unsplash_access_key", None))

    def resolve_image(
        self,
        keywords: list[str],
        category_slug: str = "default",
    ) -> str:
        """Resolve an image URL for the given keywords.

        Args:
            keywords: List of keywords to search (in English)
            category_slug: Category for fallback image

        Returns:
            Image URL (Unsplash if available, fallback otherwise)
        """
        if not keywords:
            return self._get_fallback(category_slug)

        # Check cache
        cache_key = "_".join(sorted(keywords))
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return cached.url if cached else self._get_fallback(category_slug)

        # Try Unsplash if enabled
        if self.is_enabled:
            image = self._search_unsplash(keywords)
            self._cache[cache_key] = image
            if image:
                return image.url

        return self._get_fallback(category_slug)

    def resolve_image_full(
        self,
        keywords: list[str],
        category_slug: str = "default",
    ) -> UnsplashImage | None:
        """Resolve full image data (with attribution).

        Returns None if using fallback.
        """
        if not keywords or not self.is_enabled:
            return None

        cache_key = "_".join(sorted(keywords))
        if cache_key in self._cache:
            return self._cache[cache_key]

        image = self._search_unsplash(keywords)
        self._cache[cache_key] = image
        return image

    def _search_unsplash(self, keywords: list[str]) -> UnsplashImage | None:
        """Search Unsplash for an image."""
        try:
            query = " ".join(keywords)

            with httpx.Client(timeout=10) as client:
                response = client.get(
                    self.UNSPLASH_API_URL,
                    params={
                        "query": query,
                        "per_page": 1,
                        "orientation": "landscape",
                        "content_filter": "high",  # Safe content only
                    },
                    headers={
                        "Authorization": f"Client-ID {self.settings.unsplash_access_key}",
                    },
                )

                if response.status_code == 401:
                    logger.error("unsplash_auth_error", status=response.status_code)
                    return None

                if response.status_code == 403:
                    logger.warning("unsplash_rate_limit")
                    return None

                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                if not results:
                    logger.debug("unsplash_no_results", query=query)
                    return None

                photo = results[0]
                urls = photo.get("urls", {})
                user = photo.get("user", {})
                links = photo.get("links", {})

                image = UnsplashImage(
                    url=urls.get("regular", ""),
                    url_small=urls.get("small", ""),
                    url_thumb=urls.get("thumb", ""),
                    author=user.get("name", "Unknown"),
                    author_url=user.get("links", {}).get("html", ""),
                    unsplash_url=links.get("html", ""),
                    download_location=links.get("download_location", ""),
                )

                logger.debug(
                    "unsplash_found",
                    query=query,
                    author=image.author,
                )
                return image

        except httpx.TimeoutException:
            logger.warning("unsplash_timeout", keywords=keywords)
            return None
        except Exception as e:
            logger.error("unsplash_error", error=str(e), keywords=keywords)
            return None

    def _get_fallback(self, category_slug: str) -> str:
        """Get fallback image URL by category."""
        return FALLBACK_IMAGES.get(category_slug, FALLBACK_IMAGES["default"])

    def trigger_download(self, image: UnsplashImage) -> bool:
        """Trigger download endpoint as required by Unsplash API terms.

        Call this when a photo is actually used/displayed in your app.
        This doesn't download the image, just notifies Unsplash for stats.
        """
        if not image.download_location or not self.is_enabled:
            return False

        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(
                    image.download_location,
                    headers={
                        "Authorization": f"Client-ID {self.settings.unsplash_access_key}",
                    },
                )
                response.raise_for_status()
                logger.debug("unsplash_download_triggered", author=image.author)
                return True
        except Exception as e:
            logger.warning("unsplash_download_trigger_failed", error=str(e))
            return False

    def _generate_basic_image_keywords(self, event: dict) -> list[str]:
        """Generate basic image keywords from event type (for events without LLM enrichment)."""
        type_uri = event.get("@type", "") or ""
        type_name = type_uri.split("/")[-1].lower() if type_uri else ""

        # Map common Madrid API types to Unsplash-friendly keywords
        type_to_keywords = {
            "teatroperformance": ["theater", "stage", "performance"],
            "circomagia": ["circus", "magic", "show"],
            "musica": ["concert", "music", "live"],
            "musicaclasica": ["orchestra", "classical", "concert hall"],
            "musicamoderna": ["concert", "rock", "live music"],
            "danza": ["dance", "ballet", "performance"],
            "danzabaile": ["dance", "ballroom", "dancing"],
            "danzacontemporanea": ["contemporary dance", "modern dance", "performance"],
            "cine": ["cinema", "movie", "film"],
            "cineactividadesaudiovisuales": ["cinema", "film", "screening"],
            "exposiciones": ["art", "gallery", "exhibition"],
            "exposicionfotografia": ["photography", "gallery", "exhibition"],
            "exposicionpintura": ["painting", "art gallery", "exhibition"],
            "conferenciascoloquios": ["conference", "talk", "seminar"],
            "cursostalleres": ["workshop", "learning", "classroom"],
            "actividadesdeportivas": ["sports", "fitness", "outdoor"],
            "cuentacuentostiteresmarionetas": ["puppets", "children", "storytelling"],
            "recitalespresentacionesactosliterarios": ["books", "reading", "literature"],
            "clubeslectura": ["books", "reading", "library"],
            "navidad": ["christmas", "holiday", "celebration"],
            "fiestascarnavales": ["carnival", "festival", "celebration"],
            "actividadescallearteurbano": ["street art", "urban", "mural"],
            "excursionesitinerariosvisitas": ["tour", "sightseeing", "city"],
            "itinerariosotrasactividadesambientales": ["nature", "environment", "outdoor"],
            "1ciudad21distritos": ["community", "neighborhood", "madrid"],
        }

        return type_to_keywords.get(type_name, ["event", "community", "gathering"])

    def resolve_batch(
        self,
        events_keywords: dict[str, tuple[list[str], str]],
    ) -> dict[str, str]:
        """Resolve images for multiple events.

        Args:
            events_keywords: Dict of event_id -> (keywords, category_slug)

        Returns:
            Dict of event_id -> image_url
        """
        results: dict[str, str] = {}

        for event_id, (keywords, category) in events_keywords.items():
            results[event_id] = self.resolve_image(keywords, category)

        return results


# Singleton
_resolver: ImageResolver | None = None


def get_image_resolver() -> ImageResolver:
    """Get singleton image resolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = ImageResolver()
    return _resolver
