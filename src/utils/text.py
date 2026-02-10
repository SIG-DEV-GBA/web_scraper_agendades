"""Text cleaning and normalization utilities.

Provides functions for cleaning HTML, normalizing text, removing boilerplate,
and handling encoding issues common in Spanish web content.
"""

import html
import re
import unicodedata


def normalize_unicode(text: str) -> str:
    """Normalize Unicode to NFC form (composed characters).

    Args:
        text: Input text

    Returns:
        Normalized text
    """
    return unicodedata.normalize("NFC", text)


def fix_encoding_artifacts(text: str) -> str:
    """Fix common encoding artifacts from Windows-1252 and other encodings.

    Replaces smart quotes, dashes, and other problematic characters with
    their ASCII equivalents.

    Args:
        text: Input text with possible encoding artifacts

    Returns:
        Cleaned text
    """
    if not text:
        return text

    # Windows-1252 smart quotes
    replacements = {
        "\x93": '"',
        "\x94": '"',
        "\x91": "'",
        "\x92": "'",
        # Unicode smart quotes
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        # Dashes
        "\u2013": "-",  # En dash
        "\u2014": "-",  # Em dash
        # Other
        "\u2026": "...",  # Ellipsis
        "\u00a0": " ",  # Non-breaking space
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def remove_control_characters(text: str, keep_newlines: bool = True) -> str:
    """Remove control characters from text.

    Args:
        text: Input text
        keep_newlines: If True, preserve newlines and tabs

    Returns:
        Text without control characters
    """
    if not text:
        return text

    allowed = "\n\t" if keep_newlines else ""
    return "".join(
        char for char in text
        if unicodedata.category(char) != "Cc" or char in allowed
    )


def normalize_whitespace(text: str, preserve_newlines: bool = True) -> str:
    """Normalize whitespace in text.

    Args:
        text: Input text
        preserve_newlines: If True, preserve newlines (normalized to max 2)

    Returns:
        Text with normalized whitespace
    """
    if not text:
        return text

    if preserve_newlines:
        # Multiple spaces/tabs to single space (preserve newlines)
        text = re.sub(r"[ \t]+", " ", text)
        # Max 2 consecutive newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        # All whitespace to single space
        text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_text(text: str | None) -> str | None:
    """Clean text by removing encoding artifacts and normalizing.

    Applies all text cleaning operations:
    1. Unicode normalization (NFC)
    2. Fix encoding artifacts (smart quotes, etc.)
    3. Remove control characters
    4. Normalize whitespace

    Args:
        text: Input text

    Returns:
        Cleaned text or None if input was None/empty
    """
    if not text:
        return None

    result = text
    result = normalize_unicode(result)
    result = fix_encoding_artifacts(result)
    result = remove_control_characters(result)
    result = normalize_whitespace(result)

    return result if result else None


# Boilerplate patterns to remove from descriptions
BOILERPLATE_PATTERNS = [
    r"para más información[:\s]*.*?(?=\n|$)",
    r"más información[:\s]*.*?(?=\n|$)",
    r"info(?:rmación)?[:\s]*\S+@\S+",  # Email addresses
    r"(?:tel(?:éfono)?|tfno?)[:\s]*[\d\s\-\+]+",  # Phone numbers
    r"(?:web|página)[:\s]*(?:https?://)?[\w\.\-/]+",  # URLs
    r"reserv(?:as?|e)[:\s]*.*?(?=\n|$)",
    r"entrada(?:s)?\s+(?:gratis|libre|gratuita)",
    r"aforo\s+limitado.*?(?=\n|$)",
]


def remove_boilerplate(text: str) -> str:
    """Remove common boilerplate phrases from text.

    Args:
        text: Input text

    Returns:
        Text with boilerplate removed
    """
    if not text:
        return text

    result = text
    for pattern in BOILERPLATE_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    return result


def clean_html(text: str | None) -> str | None:
    """Convert HTML to clean text preserving structure.

    Converts HTML to plain text while preserving:
    - Paragraphs (as double newlines)
    - Line breaks
    - Lists (as bullet points)
    - Headers (with newlines)

    Args:
        text: HTML text

    Returns:
        Plain text or None if input was None/empty
    """
    if not text:
        return None

    result = text

    # Convert block elements to line breaks BEFORE removing tags
    # Paragraphs: <p>...</p> -> content + double newline
    result = re.sub(r"</p>\s*", "\n\n", result, flags=re.IGNORECASE)
    result = re.sub(r"<p[^>]*>", "", result, flags=re.IGNORECASE)

    # Divs: </div> -> newline
    result = re.sub(r"</div>\s*", "\n", result, flags=re.IGNORECASE)
    result = re.sub(r"<div[^>]*>", "", result, flags=re.IGNORECASE)

    # Line breaks
    result = re.sub(r"<br\s*/?>", "\n", result, flags=re.IGNORECASE)

    # Lists: <li> -> bullet point
    result = re.sub(r"<li[^>]*>", "\n• ", result, flags=re.IGNORECASE)
    result = re.sub(r"</li>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"</?[ou]l[^>]*>", "\n", result, flags=re.IGNORECASE)

    # Headers: add newlines
    result = re.sub(r"<h[1-6][^>]*>", "\n\n", result, flags=re.IGNORECASE)
    result = re.sub(r"</h[1-6]>", "\n", result, flags=re.IGNORECASE)

    # Remove remaining HTML tags
    result = re.sub(r"<[^>]+>", "", result)

    # Decode HTML entities
    result = html.unescape(result)

    # Clean up lines
    lines = [line.strip() for line in result.split("\n")]
    result = "\n".join(lines)

    # Remove boilerplate
    result = remove_boilerplate(result)

    # Normalize whitespace
    result = normalize_whitespace(result)

    return result if result else None


def truncate(text: str | None, max_length: int, suffix: str = "...") -> str | None:
    """Truncate text to maximum length.

    Args:
        text: Input text
        max_length: Maximum length (including suffix)
        suffix: Suffix to add if truncated

    Returns:
        Truncated text or None if input was None
    """
    if not text:
        return None

    if len(text) <= max_length:
        return text

    # Truncate at word boundary
    truncated = text[: max_length - len(suffix)]
    last_space = truncated.rfind(" ")
    if last_space > max_length // 2:
        truncated = truncated[:last_space]

    return truncated + suffix


def extract_first_sentence(text: str | None) -> str | None:
    """Extract the first sentence from text.

    Useful for generating summaries from descriptions.

    Args:
        text: Input text

    Returns:
        First sentence or None if input was None
    """
    if not text:
        return None

    # Find first sentence ending
    match = re.search(r"^(.+?[.!?])\s", text)
    if match:
        return match.group(1)

    # No sentence ending found, return up to first newline or full text
    first_line = text.split("\n")[0].strip()
    return first_line if first_line else None


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug.

    Args:
        text: Input text

    Returns:
        Slugified text
    """
    if not text:
        return ""

    # Normalize and lowercase
    result = normalize_unicode(text.lower())

    # Replace Spanish characters
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ñ": "n", "ü": "u",
    }
    for old, new in replacements.items():
        result = result.replace(old, new)

    # Replace non-alphanumeric with hyphens
    result = re.sub(r"[^a-z0-9]+", "-", result)

    # Remove leading/trailing hyphens
    result = result.strip("-")

    return result
