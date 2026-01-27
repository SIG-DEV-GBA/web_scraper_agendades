"""Test script for new scraper modules."""

import asyncio
import sys

# Add src to path
sys.path.insert(0, ".")


def test_scraper_config():
    """Test scraper configuration module."""
    print("\n=== Testing scraper_config ===")

    from src.core.scraper_config import (
        RateLimitConfig,
        ProxyConfig,
        HeadersConfig,
        SourceScraperConfig,
        get_source_config,
        USER_AGENTS,
    )

    # Test rate limit config
    rate_limit = RateLimitConfig(base_delay=2.0, jitter_max=1.0)
    delay = rate_limit.get_delay(current_backoff_level=0)
    print(f"Rate limit delay (level 0): {delay:.2f}s")

    delay_backoff = rate_limit.get_delay(current_backoff_level=2)
    print(f"Rate limit delay (level 2): {delay_backoff:.2f}s")

    # Test headers rotation
    headers_config = HeadersConfig(rotate_user_agent=True)
    headers1 = headers_config.get_headers()
    headers2 = headers_config.get_headers()
    print(f"User-Agent 1: {headers1['User-Agent'][:50]}...")
    print(f"User-Agent 2: {headers2['User-Agent'][:50]}...")
    print(f"Total User-Agents available: {len(USER_AGENTS)}")

    # Test source config
    madrid_config = get_source_config("madrid_datos_abiertos")
    print(f"\nMadrid config: {madrid_config.source_name}")
    print(f"  - Base delay: {madrid_config.rate_limit.base_delay}s")
    print(f"  - Rotate UA: {madrid_config.headers.rotate_user_agent}")

    unknown_config = get_source_config("unknown_source")
    print(f"\nUnknown source config: {unknown_config.source_id}")
    print(f"  - Base delay: {unknown_config.rate_limit.base_delay}s")

    print("\n[OK] scraper_config OK")


def test_image_provider():
    """Test image provider module."""
    print("\n=== Testing image_provider ===")

    from src.core.image_provider import (
        ImageCache,
        ImageProvider,
        FALLBACK_IMAGES,
    )

    # Test cache
    cache = ImageCache()  # In-memory only
    cache.mark_used("https://example.com/img1.jpg", ["concert", "music"])
    cache.mark_used("https://example.com/img2.jpg", ["concert", "music"])

    print(f"Cache size: {cache.size}")
    print(f"Is img1 used: {cache.is_used('https://example.com/img1.jpg')}")
    print(f"Is img3 used: {cache.is_used('https://example.com/img3.jpg')}")

    # Test get unused from list
    urls = [
        "https://example.com/img1.jpg",
        "https://example.com/img2.jpg",
        "https://example.com/img3.jpg",
    ]
    unused = cache.get_unused_from_list(urls)
    print(f"First unused: {unused}")

    # Test fallback images
    print(f"\nFallback categories: {list(FALLBACK_IMAGES.keys())}")
    print(f"Cultural fallbacks: {len(FALLBACK_IMAGES['cultural'])} images")

    # Test provider (without API keys)
    provider = ImageProvider(unsplash_key=None, pexels_key=None)
    print(f"\nProviders available: {provider.providers_available}")

    # Get fallback image
    url = provider.get_image(keywords=[], category="cultural")
    print(f"Fallback image (cultural): {url[:50]}...")

    url2 = provider.get_image(keywords=[], category="cultural")
    print(f"Fallback image 2 (cultural): {url2[:50]}...")
    print(f"Different images (rotation): {url != url2}")

    print("\n[OK] image_provider OK")


async def test_firecrawl_client():
    """Test Firecrawl client module."""
    print("\n=== Testing firecrawl_client ===")

    from src.core.firecrawl_client import FirecrawlClient

    client = FirecrawlClient(base_url="http://localhost:3002")

    # Test health check (will fail if Firecrawl not running)
    is_healthy = await client.health_check()
    print(f"Firecrawl health check: {'[OK]' if is_healthy else '[SKIP] Not running (expected if not set up)'}")

    # Test domain extraction
    domain = client._get_domain("https://www.juntadeandalucia.es/cultura/eventos")
    print(f"Domain extraction: {domain}")

    await client.close()
    print("\n[OK] firecrawl_client OK")


def test_base_adapter_import():
    """Test that BaseAdapter imports correctly with new modules."""
    print("\n=== Testing BaseAdapter import ===")

    from src.core.base_adapter import BaseAdapter, AdapterConfig

    # Check that scraper config is loaded
    from src.core.scraper_config import get_source_config

    config = get_source_config("madrid_datos_abiertos")
    print(f"Source config loaded: {config.source_id}")

    print("\n[OK] BaseAdapter import OK")


def test_settings():
    """Test that new settings are available."""
    print("\n=== Testing settings ===")

    from src.config.settings import get_settings

    settings = get_settings()

    print(f"Firecrawl URL: {settings.firecrawl_url}")
    print(f"Firecrawl API Key: {'Set' if settings.firecrawl_api_key else 'Not set'}")
    print(f"Pexels API Key: {'Set' if settings.pexels_api_key else 'Not set'}")
    print(f"Unsplash API Key: {'Set' if settings.unsplash_access_key else 'Not set'}")

    print("\n[OK] settings OK")


async def main():
    """Run all tests."""
    print("=" * 50)
    print("Testing new scraper modules")
    print("=" * 50)

    try:
        test_scraper_config()
        test_image_provider()
        await test_firecrawl_client()
        test_base_adapter_import()
        test_settings()

        print("\n" + "=" * 50)
        print("All tests passed!")
        print("=" * 50)

    except Exception as e:
        print(f"\n[X] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
