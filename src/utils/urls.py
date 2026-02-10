"""URL extraction and normalization utilities."""

import re
from urllib.parse import urljoin, urlparse


def is_valid_url(url: str | None) -> bool:
    """Check if a string is a valid URL.

    Args:
        url: URL string to validate

    Returns:
        True if valid URL, False otherwise
    """
    if not url:
        return False

    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False


def normalize_url(url: str | None) -> str | None:
    """Normalize a URL.

    - Removes trailing slashes
    - Removes fragments
    - Ensures https where applicable

    Args:
        url: URL to normalize

    Returns:
        Normalized URL or None
    """
    if not url:
        return None

    url = url.strip()

    # Add scheme if missing
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith(("http://", "https://")):
        # Check if it looks like a URL
        if "." in url and "/" in url:
            url = "https://" + url
        else:
            return None

    try:
        parsed = urlparse(url)

        # Rebuild without fragment
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Add query if present
        if parsed.query:
            normalized += f"?{parsed.query}"

        # Remove trailing slash (unless it's just the domain)
        if normalized.endswith("/") and parsed.path != "/":
            normalized = normalized.rstrip("/")

        return normalized

    except Exception:
        return None


def extract_urls(text: str | None) -> list[str]:
    """Extract all URLs from text.

    Args:
        text: Text to search for URLs

    Returns:
        List of found URLs
    """
    if not text:
        return []

    # Pattern for URLs
    url_pattern = r'https?://[^\s<>"\')\]]+[^\s<>"\')\].,;:!?]'

    urls = []
    for match in re.finditer(url_pattern, text):
        url = match.group(0)
        # Clean up common trailing characters
        url = url.rstrip(".,;:!?)")
        if is_valid_url(url):
            urls.append(url)

    return urls


def extract_url_from_html(html_text: str | None) -> str | None:
    """Extract the first URL from HTML content.

    Looks for href attributes in anchor tags.

    Args:
        html_text: HTML text

    Returns:
        First found URL or None
    """
    if not html_text:
        return None

    # Pattern for href attributes
    href_pattern = r'href=["\']([^"\']+)["\']'
    match = re.search(href_pattern, html_text, re.IGNORECASE)

    if match:
        url = match.group(1)
        if is_valid_url(url):
            return url

    return None


def make_absolute_url(url: str | None, base_url: str) -> str | None:
    """Convert a relative URL to absolute.

    Args:
        url: URL (may be relative)
        base_url: Base URL for resolution

    Returns:
        Absolute URL or None
    """
    if not url:
        return None

    # Already absolute
    if url.startswith(("http://", "https://")):
        return url

    try:
        return urljoin(base_url, url)
    except Exception:
        return None


def extract_domain(url: str | None) -> str | None:
    """Extract domain from URL.

    Args:
        url: Full URL

    Returns:
        Domain name or None
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        return parsed.netloc if parsed.netloc else None
    except Exception:
        return None


def is_image_url(url: str | None) -> bool:
    """Check if URL points to an image.

    Args:
        url: URL to check

    Returns:
        True if URL appears to be an image
    """
    if not url:
        return False

    image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp")
    url_lower = url.lower()

    # Check extension
    if any(url_lower.endswith(ext) for ext in image_extensions):
        return True

    # Check for image in path
    if any(ext + "?" in url_lower for ext in image_extensions):
        return True

    return False


def clean_image_url(url: str | None, base_url: str = "") -> str | None:
    """Clean and normalize an image URL.

    Args:
        url: Image URL (may be relative)
        base_url: Base URL for relative URLs

    Returns:
        Cleaned absolute URL or None
    """
    if not url:
        return None

    url = url.strip()

    # Skip data URLs
    if url.startswith("data:"):
        return None

    # Make absolute if needed
    if base_url and not url.startswith(("http://", "https://")):
        url = make_absolute_url(url, base_url)

    if not url or not is_valid_url(url):
        return None

    return url
