"""Utility modules for the Agendades scraper.

Provides shared utilities for:
- Text cleaning and normalization
- Date/time parsing (Spanish formats)
- URL extraction and validation
- Location parsing (cities, provinces, addresses)
- Contact extraction (email, phone)
- Event deduplication
"""

# Text utilities
from src.utils.text import (
    clean_html,
    clean_text,
    fix_encoding_artifacts,
    normalize_whitespace,
    remove_boilerplate,
    slugify,
    truncate,
)

# Date utilities
from src.utils.date_parser import (
    extract_dates_from_text,
    normalize_date_range,
    parse_spanish_date,
    parse_spanish_month,
    parse_time,
)

# URL utilities
from src.utils.urls import (
    clean_image_url,
    extract_domain,
    extract_url_from_html,
    extract_urls,
    is_image_url,
    is_valid_url,
    make_absolute_url,
    normalize_url,
)

# Location utilities
from src.utils.locations import (
    CCAA_BY_PROVINCE,
    PROVINCES_BY_CCAA,
    extract_asturias_city,
    extract_city_from_text,
    extract_postal_code,
    get_canarias_province,
    get_ccaa_from_province,
    get_province_from_city,
    normalize_address,
    parse_location_string,
)

# Contact utilities
from src.utils.contacts import (
    extract_all_emails,
    extract_all_phones,
    extract_contact_info,
    extract_email,
    extract_organizer,
    extract_phone,
    extract_price_info,
    extract_registration_info,
    extract_registration_url,
    is_valid_email,
    is_valid_phone,
    normalize_phone,
)

# Deduplication
from src.utils.deduplication import generate_event_hash, is_duplicate

__all__ = [
    # Text
    "clean_html",
    "clean_text",
    "fix_encoding_artifacts",
    "normalize_whitespace",
    "remove_boilerplate",
    "slugify",
    "truncate",
    # Dates
    "extract_dates_from_text",
    "normalize_date_range",
    "parse_spanish_date",
    "parse_spanish_month",
    "parse_time",
    # URLs
    "clean_image_url",
    "extract_domain",
    "extract_url_from_html",
    "extract_urls",
    "is_image_url",
    "is_valid_url",
    "make_absolute_url",
    "normalize_url",
    # Locations
    "CCAA_BY_PROVINCE",
    "PROVINCES_BY_CCAA",
    "extract_asturias_city",
    "extract_city_from_text",
    "extract_postal_code",
    "get_canarias_province",
    "get_ccaa_from_province",
    "get_province_from_city",
    "normalize_address",
    "parse_location_string",
    # Contacts
    "extract_all_emails",
    "extract_all_phones",
    "extract_contact_info",
    "extract_email",
    "extract_organizer",
    "extract_phone",
    "extract_price_info",
    "extract_registration_info",
    "extract_registration_url",
    "is_valid_email",
    "is_valid_phone",
    "normalize_phone",
    # Deduplication
    "generate_event_hash",
    "is_duplicate",
]
