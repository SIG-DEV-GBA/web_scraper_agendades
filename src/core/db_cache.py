"""Dynamic database cache for categories and tags.

Loads categories and tags from Supabase on startup and provides
efficient lookup methods.
"""

from typing import Any

from src.config import get_settings
from src.logging import get_logger

logger = get_logger(__name__)


class DBCache:
    """Cache for categories and tags from database."""

    def __init__(self) -> None:
        self._categories: dict[str, dict[str, Any]] = {}  # slug -> {id, name, description}
        self._tags: dict[str, str] = {}  # slug -> id
        self._tags_by_name: dict[str, str] = {}  # name.lower() -> id
        self._loaded = False

    def load(self, supabase_client: Any) -> None:
        """Load categories and tags from database."""
        if self._loaded:
            return

        # Load categories
        response = supabase_client.table("categories").select("id, name, slug, description").execute()
        for cat in response.data:
            self._categories[cat["slug"].lower()] = {
                "id": cat["id"],
                "name": cat["name"],
                "description": cat.get("description", ""),
            }
        logger.info("Loaded categories", count=len(self._categories))

        # Load tags
        response = supabase_client.table("tags").select("id, name, slug").execute()
        for tag in response.data:
            self._tags[tag["slug"].lower()] = tag["id"]
            self._tags_by_name[tag["name"].lower()] = tag["id"]
        logger.info("Loaded tags", count=len(self._tags))

        self._loaded = True

    def get_category_id(self, slug: str) -> str | None:
        """Get category ID by slug."""
        cat = self._categories.get(slug.lower())
        return cat["id"] if cat else None

    def get_tag_id(self, name_or_slug: str) -> str | None:
        """Get tag ID by name or slug."""
        key = name_or_slug.lower().strip()
        return self._tags.get(key) or self._tags_by_name.get(key)

    def get_tag_ids(self, names_or_slugs: list[str]) -> list[str]:
        """Get list of tag IDs from names/slugs, ignoring non-existent ones."""
        ids = []
        for name in names_or_slugs:
            tag_id = self.get_tag_id(name)
            if tag_id:
                ids.append(tag_id)
        return ids

    @property
    def categories(self) -> dict[str, dict[str, Any]]:
        """Get all categories."""
        return self._categories

    @property
    def tags(self) -> dict[str, str]:
        """Get all tags (slug -> id)."""
        return self._tags

    @property
    def tag_names(self) -> set[str]:
        """Get all tag names."""
        return set(self._tags_by_name.keys())


# Singleton
_cache: DBCache | None = None


def get_db_cache() -> DBCache:
    """Get or create database cache singleton."""
    global _cache
    if _cache is None:
        _cache = DBCache()
    return _cache
