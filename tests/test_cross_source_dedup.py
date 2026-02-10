"""Tests for cross-source deduplication module.

Tests:
1. normalize_city() - city name normalization
2. calculate_quality_score() - event quality scoring
3. is_cross_source_duplicate() - duplicate detection
4. merge_events() - event merging logic
5. should_update_event() - update decision logic
"""

from datetime import date, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.event_model import EventCreate, LocationType
from src.utils.cross_source_dedup import (
    QUALITY_WEIGHTS,
    CrossSourceDeduplicator,
    DeduplicationResult,
    calculate_quality_score,
    is_cross_source_duplicate,
    merge_events,
    normalize_city,
    should_update_event,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def base_event() -> EventCreate:
    """Basic event with minimal fields."""
    return EventCreate(
        title="Concierto de Jazz",
        description="Un concierto increíble de jazz en el centro de la ciudad.",
        start_date=date(2025, 3, 15),
        location_type=LocationType.PHYSICAL,
        city="Valladolid",
        province="Valladolid",
        comunidad_autonoma="Castilla y León",
        source_id="viralagenda_valladolid",
    )


@pytest.fixture
def complete_event() -> EventCreate:
    """Event with all quality fields filled."""
    return EventCreate(
        title="Festival de Música",
        description="Gran festival de música con artistas internacionales. " * 5,
        start_date=date(2025, 3, 15),
        end_date=date(2025, 3, 17),
        start_time=time(18, 0),
        end_time=time(23, 0),
        location_type=LocationType.PHYSICAL,
        venue_name="Auditorio Municipal",
        city="Valladolid",
        province="Valladolid",
        comunidad_autonoma="Castilla y León",
        source_id="eventbrite_valladolid",
        external_url="https://example.com/festival",
        source_image_url="https://example.com/image.jpg",
        price_info="20€ anticipada, 25€ taquilla",
        latitude=41.6523,
        longitude=-4.7245,
        organizer_name="Ayuntamiento de Valladolid",
        category_slugs=["musica", "conciertos"],
    )


@pytest.fixture
def existing_event_dict() -> dict:
    """Existing event from database as dict."""
    return {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "Concierto de Jazz en Valladolid",
        "description": "Concierto de jazz",
        "start_date": "2025-03-15",
        "city": "Valladolid",
        "province": "Valladolid",
        "source": "viralagenda_valladolid",
        "venue_name": None,
        "image_url": None,
        "source_image_url": None,
        "end_date": None,
        "start_time": None,
        "end_time": None,
        "price_info": None,
        "latitude": None,
        "longitude": None,
        "organizer_name": None,
        "category_id": None,
        "category_slugs": [],
        "external_url": None,
    }


# =============================================================================
# Tests: normalize_city()
# =============================================================================


class TestNormalizeCity:
    """Tests for city name normalization."""

    def test_lowercase(self):
        """Should convert to lowercase."""
        assert normalize_city("MADRID") == "madrid"
        assert normalize_city("Barcelona") == "barcelona"

    def test_remove_accents(self):
        """Should remove Spanish accents."""
        assert normalize_city("Córdoba") == "cordoba"
        assert normalize_city("Cádiz") == "cadiz"
        assert normalize_city("Logroño") == "logrono"
        assert normalize_city("Ávila") == "avila"

    def test_normalize_whitespace(self):
        """Should normalize extra whitespace."""
        assert normalize_city("  Madrid  ") == "madrid"
        assert normalize_city("San  Sebastián") == "san sebastian"

    def test_empty_and_none(self):
        """Should handle empty and None values."""
        assert normalize_city("") == ""
        assert normalize_city(None) == ""

    def test_complex_names(self):
        """Should handle complex city names."""
        assert normalize_city("Palma de Mallorca") == "palma de mallorca"
        assert normalize_city("Santiago de Compostela") == "santiago de compostela"

    def test_remove_comarca_suffixes(self):
        """Should remove Viralagenda comarca/campiña suffixes."""
        # Campiña pattern
        assert normalize_city("Valladolid y Campiña del Pisuerga") == "valladolid"
        # Comarca pattern
        assert normalize_city("León y Comarca Metropolitana") == "leon"
        # Área metropolitana
        assert normalize_city("Sevilla y Área Metropolitana") == "sevilla"
        # Mixed case
        assert normalize_city("BURGOS Y COMARCA") == "burgos"
        # No suffix - should remain unchanged
        assert normalize_city("Valladolid") == "valladolid"


# =============================================================================
# Tests: calculate_quality_score()
# =============================================================================


class TestCalculateQualityScore:
    """Tests for event quality scoring."""

    def test_minimal_event_low_score(self, base_event):
        """Minimal event should have low score."""
        score = calculate_quality_score(base_event)
        # Only has description >50 chars
        assert score == QUALITY_WEIGHTS["description"]

    def test_complete_event_high_score(self, complete_event):
        """Complete event should have high score."""
        score = calculate_quality_score(complete_event)
        # Should have: description, image, end_date, start_time, end_time,
        # price_info, coordinates, organizer, category (via slugs), external_url
        expected = (
            QUALITY_WEIGHTS["description"]
            + QUALITY_WEIGHTS["image_url"]
            + QUALITY_WEIGHTS["end_date"]
            + QUALITY_WEIGHTS["start_time"]
            + QUALITY_WEIGHTS["end_time"]
            + QUALITY_WEIGHTS["price_info"]
            + QUALITY_WEIGHTS["coordinates"]
            + QUALITY_WEIGHTS["organizer_name"]
            + QUALITY_WEIGHTS["category_id"]  # category_slugs also scores
            + QUALITY_WEIGHTS["external_url"]
        )
        assert score == expected

    def test_dict_input(self, existing_event_dict):
        """Should work with dict input (from DB)."""
        score = calculate_quality_score(existing_event_dict)
        # Only short description, no other fields
        assert score == 0  # description < 50 chars

    def test_short_description_no_points(self):
        """Short description (<50 chars) should not score."""
        event = EventCreate(
            title="Test",
            description="Short",
            start_date=date(2025, 1, 1),
            location_type=LocationType.PHYSICAL,
            city="Madrid",
            province="Madrid",
            comunidad_autonoma="Madrid",
            source_id="test",
        )
        score = calculate_quality_score(event)
        assert score == 0


# =============================================================================
# Tests: is_cross_source_duplicate()
# =============================================================================


class TestIsCrossSourceDuplicate:
    """Tests for duplicate detection."""

    def test_same_title_same_date_same_city_is_duplicate(self, base_event):
        """Same title, date, city = duplicate."""
        candidate = {
            "title": "Concierto de Jazz",
            "start_date": "2025-03-15",
            "city": "Valladolid",
            "venue_name": None,
        }
        assert is_cross_source_duplicate(base_event, candidate) is True

    def test_similar_title_same_date_same_city_is_duplicate(self, base_event):
        """Similar title (>0.85), same date, city = duplicate."""
        # "Concierto de Jazz" vs "Concierto Jazz" should have >0.85 similarity
        candidate = {
            "title": "Concierto Jazz",
            "start_date": "2025-03-15",
            "city": "Valladolid",
            "venue_name": None,
        }
        assert is_cross_source_duplicate(base_event, candidate) is True

    def test_different_date_not_duplicate(self, base_event):
        """Different date = not duplicate."""
        candidate = {
            "title": "Concierto de Jazz",
            "start_date": "2025-03-16",
            "city": "Valladolid",
            "venue_name": None,
        }
        assert is_cross_source_duplicate(base_event, candidate) is False

    def test_different_title_not_duplicate(self, base_event):
        """Very different title = not duplicate."""
        candidate = {
            "title": "Exposición de Arte Moderno",
            "start_date": "2025-03-15",
            "city": "Valladolid",
            "venue_name": None,
        }
        assert is_cross_source_duplicate(base_event, candidate) is False

    def test_same_venue_different_city_is_duplicate(self):
        """Same venue = duplicate (even without city match)."""
        event = EventCreate(
            title="Concierto Rock",
            description="Test",
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            venue_name="Teatro Calderón",
            city=None,
            province="Valladolid",
            comunidad_autonoma="Castilla y León",
            source_id="test",
        )
        candidate = {
            "title": "Concierto de Rock",
            "start_date": "2025-03-15",
            "city": None,
            "venue_name": "Teatro Calderón",
        }
        assert is_cross_source_duplicate(event, candidate) is True

    def test_very_high_title_similarity_without_city(self):
        """Very high similarity (>0.95) = duplicate even without city."""
        event = EventCreate(
            title="Festival Internacional de Jazz 2025",
            description="Test",
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            city=None,
            province="Unknown",
            comunidad_autonoma="Unknown",
            source_id="test",
        )
        candidate = {
            "title": "Festival Internacional de Jazz 2025",
            "start_date": "2025-03-15",
            "city": None,
            "venue_name": None,
        }
        assert is_cross_source_duplicate(event, candidate) is True


# =============================================================================
# Tests: merge_events()
# =============================================================================


class TestMergeEvents:
    """Tests for event merging logic."""

    def test_fills_empty_fields(self, existing_event_dict):
        """Should fill empty fields from new event."""
        new_event = EventCreate(
            title="Concierto de Jazz",
            description="Test",
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            venue_name="Teatro Principal",
            city="Valladolid",
            province="Valladolid",
            comunidad_autonoma="Castilla y León",
            source_id="eventbrite_valladolid",
            source_image_url="https://example.com/img.jpg",
            price_info="15€",
        )

        merged, fields = merge_events(existing_event_dict, new_event)

        assert merged["venue_name"] == "Teatro Principal"
        assert merged["source_image_url"] == "https://example.com/img.jpg"
        assert merged["price_info"] == "15€"
        assert "venue_name" in fields
        assert "source_image_url" in fields
        assert "price_info" in fields

    def test_keeps_existing_values(self, existing_event_dict):
        """Should keep existing values, not overwrite."""
        existing_event_dict["venue_name"] = "Auditorio"

        new_event = EventCreate(
            title="Test",
            description="Test",
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            venue_name="Otro Lugar",
            city="Valladolid",
            province="Valladolid",
            comunidad_autonoma="Castilla y León",
            source_id="test",
        )

        merged, fields = merge_events(existing_event_dict, new_event)

        assert merged["venue_name"] == "Auditorio"  # Kept original
        assert "venue_name" not in fields

    def test_prefers_longer_description(self, existing_event_dict):
        """Should prefer significantly longer description."""
        existing_event_dict["description"] = "Short description."

        new_event = EventCreate(
            title="Test",
            description="This is a much longer and more detailed description of the event. " * 5,
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            city="Valladolid",
            province="Valladolid",
            comunidad_autonoma="Castilla y León",
            source_id="test",
        )

        merged, fields = merge_events(existing_event_dict, new_event)

        assert len(merged["description"]) > 100
        assert "description" in fields

    def test_merges_category_slugs(self, existing_event_dict):
        """Should merge category_slugs lists."""
        existing_event_dict["category_slugs"] = ["musica"]

        new_event = EventCreate(
            title="Test",
            description="Test",
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            city="Valladolid",
            province="Valladolid",
            comunidad_autonoma="Castilla y León",
            source_id="test",
            category_slugs=["conciertos", "jazz"],
        )

        merged, fields = merge_events(existing_event_dict, new_event)

        assert set(merged["category_slugs"]) == {"musica", "conciertos", "jazz"}
        assert "category_slugs" in fields


# =============================================================================
# Tests: should_update_event()
# =============================================================================


class TestShouldUpdateEvent:
    """Tests for update decision logic."""

    def test_should_update_when_adds_value(self, existing_event_dict):
        """Should update when new event adds significant value."""
        new_event = EventCreate(
            title="Test",
            description="Test " * 20,  # Long description
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            city="Valladolid",
            province="Valladolid",
            comunidad_autonoma="Castilla y León",
            source_id="test",
            source_image_url="https://example.com/img.jpg",  # Adds image
            latitude=41.65,  # Adds coordinates
            longitude=-4.72,
        )

        assert should_update_event(existing_event_dict, new_event) is True

    def test_should_not_update_when_no_improvement(self):
        """Should not update when no meaningful improvement."""
        existing = {
            "id": "123",
            "title": "Test Event",
            "description": "A very long and complete description. " * 5,
            "start_date": "2025-03-15",
            "city": "Madrid",
            "image_url": "https://example.com/img.jpg",
            "venue_name": "Teatro",
            "price_info": "10€",
        }

        new_event = EventCreate(
            title="Test",
            description="Short",
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            city="Madrid",
            province="Madrid",
            comunidad_autonoma="Madrid",
            source_id="test",
        )

        assert should_update_event(existing, new_event) is False


# =============================================================================
# Tests: CrossSourceDeduplicator
# =============================================================================


class TestCrossSourceDeduplicator:
    """Tests for the deduplicator class."""

    @pytest.fixture
    def mock_client(self):
        """Mock Supabase client."""
        client = MagicMock()
        client._client = MagicMock()
        return client

    @pytest.fixture
    def deduplicator(self, mock_client):
        """Deduplicator instance with mock client."""
        return CrossSourceDeduplicator(mock_client)

    @pytest.mark.asyncio
    async def test_process_event_returns_insert_when_no_duplicate(
        self, deduplicator, base_event, mock_client
    ):
        """Should return insert action when no duplicate found."""
        # Mock empty candidates (new format without ilike)
        mock_client._client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        result = await deduplicator.process_event(base_event)

        assert result.action == "insert"
        assert result.existing_id is None

    @pytest.mark.asyncio
    async def test_process_event_returns_skip_when_duplicate_no_improvement(
        self, deduplicator, mock_client
    ):
        """Should skip when duplicate found but no improvement."""
        # Mock existing complete event with event_locations embedded (new format)
        existing = {
            "id": "existing-uuid",
            "title": "Concierto de Jazz",
            "description": "Complete description " * 10,
            "start_date": "2025-03-15",
            "source": "other_source",
            "image_url": "https://example.com/img.jpg",
            "venue_name": "Teatro",
            "price_info": "20€",
            "latitude": 41.65,
            "longitude": -4.72,
            "event_locations": {
                "city": "Valladolid",
                "province": "Valladolid",
                "name": "Teatro",
                "address": "Calle Principal 1",
            },
        }
        # New mock chain without ilike (now uses select with embedded relations)
        mock_client._client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [existing]

        # New event with minimal data
        new_event = EventCreate(
            title="Concierto de Jazz",
            description="Short",
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            city="Valladolid",
            province="Valladolid",
            comunidad_autonoma="Castilla y León",
            source_id="viralagenda_valladolid",
        )

        result = await deduplicator.process_event(new_event)

        assert result.action == "skip"
        assert result.existing_id == "existing-uuid"

    @pytest.mark.asyncio
    async def test_process_event_returns_merge_when_duplicate_with_improvement(
        self, deduplicator, mock_client
    ):
        """Should merge when duplicate found and improvement possible."""
        # Mock existing minimal event with event_locations embedded (new format)
        existing = {
            "id": "existing-uuid",
            "title": "Concierto de Jazz",
            "description": "Short",
            "start_date": "2025-03-15",
            "source": "other_source",
            "image_url": None,
            "venue_name": None,
            "price_info": None,
            "latitude": None,
            "longitude": None,
            "event_locations": {
                "city": "Valladolid",
                "province": "Valladolid",
                "name": None,
                "address": None,
            },
        }
        # New mock chain without ilike (now uses select with embedded relations)
        mock_client._client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [existing]

        # New event with more data
        new_event = EventCreate(
            title="Concierto de Jazz",
            description="Much longer and better description " * 5,
            start_date=date(2025, 3, 15),
            location_type=LocationType.PHYSICAL,
            city="Valladolid",
            province="Valladolid",
            comunidad_autonoma="Castilla y León",
            source_id="eventbrite_valladolid",
            source_image_url="https://example.com/img.jpg",
            venue_name="Teatro Principal",
            price_info="15€",
        )

        result = await deduplicator.process_event(new_event)

        assert result.action == "merge"
        assert result.existing_id == "existing-uuid"
        assert result.fields_merged is not None
        assert len(result.fields_merged) > 0

    def test_clear_cache(self, deduplicator):
        """Should clear the candidate cache."""
        deduplicator._candidate_cache["key"] = [{"test": "data"}]
        deduplicator.clear_cache()
        assert len(deduplicator._candidate_cache) == 0


# =============================================================================
# Tests: DeduplicationResult
# =============================================================================


class TestDeduplicationResult:
    """Tests for DeduplicationResult dataclass."""

    def test_insert_result(self):
        """Should create insert result."""
        result = DeduplicationResult(action="insert")
        assert result.action == "insert"
        assert result.existing_id is None
        assert result.fields_merged is None

    def test_merge_result(self):
        """Should create merge result with fields."""
        result = DeduplicationResult(
            action="merge",
            existing_id="uuid-123",
            fields_merged=["description", "image_url"],
            quality_before=10,
            quality_after=25,
        )
        assert result.action == "merge"
        assert result.existing_id == "uuid-123"
        assert "description" in result.fields_merged
        assert result.quality_after > result.quality_before

    def test_skip_result(self):
        """Should create skip result."""
        result = DeduplicationResult(
            action="skip",
            existing_id="uuid-456",
            quality_before=40,
        )
        assert result.action == "skip"
        assert result.existing_id == "uuid-456"


# =============================================================================
# Integration-style tests
# =============================================================================


class TestDeduplicationScenarios:
    """Real-world deduplication scenarios."""

    def test_viralagenda_plus_eventbrite_same_event(self):
        """Scenario: Same event from viralagenda and eventbrite."""
        # Viralagenda event (less data)
        viralagenda = EventCreate(
            title="Festival Jazz 2025",  # Shorter title for higher similarity
            description="Festival de jazz en el centro.",
            start_date=date(2025, 6, 15),
            location_type=LocationType.PHYSICAL,
            city="Salamanca",
            province="Salamanca",
            comunidad_autonoma="Castilla y León",
            source_id="viralagenda_salamanca",
        )

        # Eventbrite event (more data) - same base title
        eventbrite_dict = {
            "id": "eb-123",
            "title": "Festival Jazz 2025",  # Same title
            "description": "El mejor festival de jazz. " * 10,
            "start_date": "2025-06-15",
            "city": "Salamanca",
            "source": "eventbrite_salamanca",
            "image_url": "https://eventbrite.com/img.jpg",
            "venue_name": "Plaza Mayor",
            "price_info": "Entrada libre",
        }

        # Should detect as duplicate
        assert is_cross_source_duplicate(viralagenda, eventbrite_dict) is True

        # Merge should add eventbrite's extra data
        merged, fields = merge_events(eventbrite_dict, viralagenda)

        # Eventbrite already has more, so minimal merge
        assert merged["venue_name"] == "Plaza Mayor"

    def test_different_events_same_day_same_city(self):
        """Scenario: Different events on same day in same city."""
        event1 = EventCreate(
            title="Concierto de Rock",
            description="Concierto de rock pesado.",
            start_date=date(2025, 5, 20),
            location_type=LocationType.PHYSICAL,
            city="León",
            province="León",
            comunidad_autonoma="Castilla y León",
            source_id="source1",
        )

        event2_dict = {
            "title": "Exposición de Fotografía",
            "start_date": "2025-05-20",
            "city": "León",
            "venue_name": "Museo de Arte",
        }

        # Should NOT detect as duplicate (different titles)
        assert is_cross_source_duplicate(event1, event2_dict) is False
