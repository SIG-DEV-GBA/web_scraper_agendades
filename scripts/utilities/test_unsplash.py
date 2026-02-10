"""Test Unsplash API integration."""

import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.image_resolver import get_image_resolver

def test_unsplash():
    resolver = get_image_resolver()

    print("=" * 60)
    print("TEST UNSPLASH API")
    print("=" * 60)

    print(f"\nUnsplash enabled: {resolver.is_enabled}")

    if not resolver.is_enabled:
        print("ERROR: Unsplash no habilitado. Verifica UNSPLASH_ACCESS_KEY en .env")
        return

    # Test searches
    test_queries = [
        (["theater", "stage", "performance"], "cultural"),
        (["yoga", "wellness", "meditation"], "sanitaria"),
        (["programming", "coding", "computer"], "tecnologia"),
        (["community", "volunteers", "charity"], "social"),
    ]

    print("\nBuscando imagenes...\n")

    for keywords, category in test_queries:
        print(f"Keywords: {keywords}")
        image = resolver.resolve_image_full(keywords, category)

        if image:
            print(f"  URL: {image.url[:60]}...")
            print(f"  Autor: {image.author}")
            print(f"  Atribucion: {image.get_attribution_text()}")
            print(f"  Download location: {'OK' if image.download_location else 'MISSING'}")

            # Trigger download (required by API terms)
            triggered = resolver.trigger_download(image)
            print(f"  Download triggered: {triggered}")
        else:
            print(f"  FALLBACK: {resolver._get_fallback(category)[:50]}...")

        print()

    print("=" * 60)
    print("TEST COMPLETADO")
    print("=" * 60)

if __name__ == "__main__":
    test_unsplash()
