"""Tests for the pipeline module."""

import pytest
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.pipeline import PipelineConfig, PipelineResult
from src.core.event_model import EventCreate
from src.config.sources import SourceTier


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PipelineConfig(source_slug="test_source")

        assert config.source_slug == "test_source"
        assert config.limit is None  # unlimited by default
        assert config.dry_run is False
        assert config.skip_enrichment is False
        assert config.skip_images is False

    def test_config_with_limit(self):
        """Test configuration with event limit."""
        config = PipelineConfig(source_slug="test", limit=10)

        assert config.limit == 10

    def test_dry_run_mode(self):
        """Test dry run configuration."""
        config = PipelineConfig(source_slug="test", dry_run=True)

        assert config.dry_run is True


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_successful_result(self):
        """Test successful pipeline result."""
        result = PipelineResult(
            source_slug="test",
            source_name="Test Source",
            ccaa="Test CCAA",
            tier=SourceTier.GOLD,
            raw_count=100,
            parsed_count=95,
            inserted_count=90,
            skipped_existing=5,
            duration_seconds=10.5,
        )

        assert result.success is True
        assert result.raw_count == 100
        assert result.parsed_count == 95
        assert result.inserted_count == 90
        assert result.error is None

    def test_failed_result(self):
        """Test failed pipeline result with error."""
        result = PipelineResult(
            source_slug="test",
            source_name="Test Source",
            ccaa="Test CCAA",
            tier=SourceTier.GOLD,
            success=False,
            error="Connection timeout",
        )

        assert result.success is False
        assert result.error == "Connection timeout"

    def test_limit_tracking(self):
        """Test limit reached tracking."""
        result = PipelineResult(
            source_slug="test",
            source_name="Test Source",
            ccaa="Test CCAA",
            tier=SourceTier.GOLD,
            requested_limit=50,
            limit_reached=False,  # Less events than requested
            limited_count=30,
        )

        assert result.requested_limit == 50
        assert result.limit_reached is False
        assert result.limited_count == 30


class TestEventFiltering:
    """Tests for event filtering logic."""

    def test_filter_past_events(self):
        """Test that past events are filtered out."""
        from datetime import date, timedelta

        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        events = [
            EventCreate(
                title="Past Event",
                start_date=yesterday,
                source_id="test",
                external_id="past-1",
            ),
            EventCreate(
                title="Today Event",
                start_date=today,
                source_id="test",
                external_id="today-1",
            ),
            EventCreate(
                title="Future Event",
                start_date=tomorrow,
                source_id="test",
                external_id="future-1",
            ),
        ]

        # Filter to only future/today events
        filtered = [e for e in events if e.start_date >= today]

        assert len(filtered) == 2
        assert all(e.start_date >= today for e in filtered)


class TestEventValidation:
    """Tests for event validation."""

    def test_valid_event(self):
        """Test valid event creation."""
        event = EventCreate(
            title="Test Event",
            start_date=date(2026, 3, 15),
            source_id="test_source",
            external_id="test-123",
        )

        assert event.title == "Test Event"
        assert event.start_date == date(2026, 3, 15)

    def test_event_with_all_fields(self):
        """Test event with all optional fields."""
        event = EventCreate(
            title="Complete Event",
            start_date=date(2026, 3, 15),
            end_date=date(2026, 3, 16),
            start_time=time(18, 0),
            end_time=time(22, 0),
            description="A complete event description",
            summary="Short summary",
            venue_name="Test Venue",
            address="123 Test Street",
            city="Madrid",
            province="Madrid",
            comunidad_autonoma="Comunidad de Madrid",
            latitude=40.4168,
            longitude=-3.7038,
            is_free=True,
            price_info="Gratuito",
            category_slugs=["musica", "conciertos"],
            source_id="test_source",
            external_id="test-456",
            external_url="https://example.com/event/456",
        )

        assert event.city == "Madrid"
        assert event.is_free is True
        assert len(event.category_slugs) == 2


class TestDeduplication:
    """Tests for deduplication utilities."""

    def test_normalize_text(self):
        """Test text normalization."""
        from src.utils.deduplication import normalize_text

        # Remove punctuation and normalize whitespace
        assert normalize_text("Hello, World!") == "hello world"
        assert normalize_text("  Multiple   Spaces  ") == "multiple spaces"
        assert normalize_text("") == ""

    def test_title_similarity(self):
        """Test title similarity calculation."""
        from src.utils.deduplication import title_similarity

        # Identical titles
        assert title_similarity("Test Event", "Test Event") == 1.0

        # Similar titles
        sim = title_similarity("Concierto de Jazz", "Concierto Jazz")
        assert sim > 0.8

        # Different titles
        sim = title_similarity("Concierto", "Teatro")
        assert sim < 0.5

    def test_generate_event_hash(self):
        """Test event hash generation."""
        from src.utils.deduplication import generate_event_hash

        event1 = EventCreate(
            title="Test Event",
            start_date=date(2026, 3, 15),
            source_id="test",
            external_id="e1",
        )
        event2 = EventCreate(
            title="Test Event",
            start_date=date(2026, 3, 15),
            source_id="test",
            external_id="e2",
        )
        event3 = EventCreate(
            title="Different Event",
            start_date=date(2026, 3, 15),
            source_id="test",
            external_id="e3",
        )

        hash1 = generate_event_hash(event1)
        hash2 = generate_event_hash(event2)
        hash3 = generate_event_hash(event3)

        # Same title and date should produce same hash
        assert hash1 == hash2
        # Different title should produce different hash
        assert hash1 != hash3


class TestSourceRegistry:
    """Tests for source registry."""

    def test_get_source_by_slug(self):
        """Test getting source by slug."""
        from src.config.sources import SourceRegistry

        # Try to get a known source
        source = SourceRegistry.get("catalunya_agenda")
        if source:
            assert source.slug == "catalunya_agenda"
            assert source.ccaa == "Cataluña"

    def test_get_sources_by_tier(self):
        """Test getting sources by tier."""
        from src.config.sources import SourceRegistry, SourceTier

        gold_sources = SourceRegistry.get_by_tier(SourceTier.GOLD)
        bronze_sources = SourceRegistry.get_by_tier(SourceTier.BRONZE)

        # Should have sources in each tier
        assert len(gold_sources) > 0
        assert len(bronze_sources) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
