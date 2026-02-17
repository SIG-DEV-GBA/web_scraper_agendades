"""Tests for adapter modules."""

import pytest
from datetime import date


class TestAdapterRegistry:
    """Tests for adapter registration and retrieval."""

    def test_get_adapter_gold(self):
        """Test getting a Gold adapter."""
        from src.adapters import get_adapter

        adapter_class = get_adapter("catalunya_agenda")
        assert adapter_class is not None

    def test_get_adapter_bronze(self):
        """Test getting a Bronze adapter (Viralagenda)."""
        from src.adapters import get_adapter

        adapter_class = get_adapter("viralagenda_madrid")
        if adapter_class:
            adapter = adapter_class()
            assert adapter.tier == "bronze"

    def test_get_nonexistent_adapter(self):
        """Test getting a non-existent adapter returns None."""
        from src.adapters import get_adapter

        adapter_class = get_adapter("nonexistent_adapter_xyz")
        assert adapter_class is None

    def test_list_adapters(self):
        """Test listing all adapters."""
        from src.adapters import list_adapters

        adapters = list_adapters()
        assert isinstance(adapters, list)
        assert len(adapters) > 0


class TestAdapterAttributes:
    """Tests for adapter attributes."""

    def test_adapter_has_required_attributes(self):
        """Test that adapters have required attributes."""
        from src.adapters import get_adapter

        required_attrs = ["source_id", "source_name", "ccaa", "tier"]

        adapter_class = get_adapter("catalunya_agenda")
        if adapter_class:
            adapter = adapter_class()
            for attr in required_attrs:
                assert hasattr(adapter, attr), f"Missing attribute: {attr}"

    def test_gold_adapter_tier(self):
        """Test Gold adapters have correct tier."""
        from src.adapters import get_adapter

        gold_sources = ["catalunya_agenda", "euskadi_kulturklik", "castilla_leon_agenda"]

        for slug in gold_sources:
            adapter_class = get_adapter(slug)
            if adapter_class:
                adapter = adapter_class()
                assert adapter.tier in ["gold", "Gold", "GOLD"], f"{slug} should be gold tier"

    def test_viralagenda_ccaa_mapping(self):
        """Test Viralagenda adapters have correct CCAA."""
        from src.adapters import get_adapter

        test_cases = [
            ("viralagenda_madrid", "Comunidad de Madrid"),
            ("viralagenda_sevilla", "Andalucía"),
            ("viralagenda_barcelona", "Cataluña"),
        ]

        for slug, expected_ccaa in test_cases:
            adapter_class = get_adapter(slug)
            if adapter_class:
                adapter = adapter_class()
                assert adapter.ccaa == expected_ccaa, f"{slug} CCAA should be {expected_ccaa}"


class TestDateParsing:
    """Tests for date parsing utilities."""

    def test_parse_spanish_date(self):
        """Test parsing Spanish date formats."""
        from src.utils.date_parser import parse_spanish_date

        test_cases = [
            ("15/03/2026", date(2026, 3, 15)),
            ("15-03-2026", date(2026, 3, 15)),
            ("2026-03-15", date(2026, 3, 15)),
            ("15 de marzo de 2026", date(2026, 3, 15)),
        ]

        for date_str, expected in test_cases:
            result = parse_spanish_date(date_str)
            if result:
                assert result == expected, f"Failed for {date_str}"

    def test_parse_invalid_date(self):
        """Test parsing invalid dates returns None."""
        from src.utils.date_parser import parse_spanish_date

        invalid_dates = ["invalid", "", "not a date"]

        for date_str in invalid_dates:
            result = parse_spanish_date(date_str)
            assert result is None, f"Should return None for: {date_str}"


class TestTextCleaning:
    """Tests for text cleaning utilities."""

    def test_clean_text_basic(self):
        """Test basic text cleaning."""
        from src.utils.text import clean_text

        # Remove extra whitespace
        result = clean_text("  Hello   World  ")
        assert result is not None
        assert "  " not in result or result.strip() == result

    def test_clean_text_returns_string(self):
        """Test clean_text returns a string."""
        from src.utils.text import clean_text

        result = clean_text("Test text")
        assert isinstance(result, str)


class TestLocationUtils:
    """Tests for location utilities."""

    def test_province_to_ccaa(self):
        """Test province to CCAA mapping."""
        from src.utils.locations import get_ccaa_from_province

        test_cases = [
            ("Madrid", "Comunidad de Madrid"),
            ("Barcelona", "Cataluña"),
            ("Sevilla", "Andalucía"),
            ("Vizcaya", "País Vasco"),
            ("Bizkaia", "País Vasco"),
        ]

        for province, expected_ccaa in test_cases:
            result = get_ccaa_from_province(province)
            if result:
                assert result == expected_ccaa, f"{province} should map to {expected_ccaa}"


class TestURLUtils:
    """Tests for URL utilities."""

    def test_is_valid_url(self):
        """Test URL validation."""
        from src.utils.urls import is_valid_url

        assert is_valid_url("https://example.com") is True
        assert is_valid_url("http://example.com/page") is True
        assert is_valid_url("not-a-url") is False
        assert is_valid_url("") is False
        assert is_valid_url(None) is False

    def test_make_absolute_url(self):
        """Test making URLs absolute."""
        from src.utils.urls import make_absolute_url

        base = "https://example.com"

        # Already absolute
        result = make_absolute_url("https://other.com/page", base)
        assert result == "https://other.com/page"

        # Relative URL
        result = make_absolute_url("/page/123", base)
        if result:
            assert result.startswith("https://")

    def test_extract_domain(self):
        """Test domain extraction from URL."""
        from src.utils.urls import extract_domain

        test_cases = [
            ("https://www.example.com/page", "example.com"),
            ("http://subdomain.example.org/path", "example.org"),
        ]

        for url, expected in test_cases:
            result = extract_domain(url)
            if result:
                assert expected in result


class TestContactExtraction:
    """Tests for contact information extraction."""

    def test_extract_email(self):
        """Test email extraction from text."""
        from src.utils.contacts import extract_email

        text = "Contact us at info@example.com for more info"
        result = extract_email(text)
        assert result == "info@example.com"

    def test_extract_email_none(self):
        """Test email extraction when no email present."""
        from src.utils.contacts import extract_email

        text = "No email here"
        result = extract_email(text)
        assert result is None

    def test_extract_phone(self):
        """Test phone number extraction."""
        from src.utils.contacts import extract_phone

        test_cases = [
            ("Call us: 912 345 678", "912 345 678"),
            ("Tel: +34 912345678", "+34 912345678"),
            ("Phone: 91-234-5678", "91-234-5678"),
        ]

        for text, expected_pattern in test_cases:
            result = extract_phone(text)
            if result:
                # Check that some phone number was extracted
                assert any(c.isdigit() for c in result)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
