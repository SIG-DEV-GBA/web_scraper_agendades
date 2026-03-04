"""Unit tests for the insertion pipeline core logic.

Tests _is_future_or_ongoing, _parse_and_filter, _apply_enrichments,
PipelineConfig defaults, and PipelineResult tracking.
All with mocks - no DB or HTTP calls.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.config.sources import SourceTier
from src.core.event_model import EventCreate
from src.core.llm_enricher import EventEnrichment
from src.core.pipeline import InsertionPipeline, PipelineConfig, PipelineResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    title: str = "Test Event",
    start_date: date | None = None,
    end_date: date | None = None,
    external_id: str = "test_123",
    source_id: str = "test_source",
    category_slugs: list[str] | None = None,
    **kwargs,
) -> EventCreate:
    """Create a minimal valid EventCreate for testing."""
    return EventCreate(
        title=title,
        start_date=start_date or (date.today() + timedelta(days=7)),
        end_date=end_date,
        external_url=f"https://example.com/{external_id}",
        external_id=external_id,
        source_id=source_id,
        category_slugs=category_slugs or [],
        **kwargs,
    )


def _make_pipeline(source_slug: str = "test_source", **config_kwargs) -> InsertionPipeline:
    """Create an InsertionPipeline with a mocked adapter (no DB dependency)."""
    config = PipelineConfig(source_slug=source_slug, **config_kwargs)
    pipeline = InsertionPipeline(config)
    pipeline.adapter = MagicMock()
    return pipeline


# ===========================================================================
# PipelineConfig
# ===========================================================================


class TestPipelineConfig:
    """Test PipelineConfig defaults and validation."""

    def test_defaults(self):
        """All defaults should match the dataclass definition."""
        config = PipelineConfig(source_slug="test")
        assert config.source_slug == "test"
        assert config.limit is None
        assert config.dry_run is False
        assert config.upsert is False
        assert config.fetch_details is True
        assert config.skip_enrichment is False
        assert config.skip_images is False
        assert config.batch_size == 10
        assert config.debug_prefix is False
        assert config.streaming_insert is True
        assert config.streaming_batch_size == 5
        assert config.filter_existing is True

    def test_custom_values(self):
        """Custom values should override defaults."""
        config = PipelineConfig(
            source_slug="my_source",
            limit=50,
            dry_run=True,
            upsert=True,
            fetch_details=False,
            skip_enrichment=True,
            skip_images=True,
            batch_size=25,
            debug_prefix=True,
            streaming_insert=False,
            streaming_batch_size=10,
            filter_existing=False,
        )
        assert config.source_slug == "my_source"
        assert config.limit == 50
        assert config.dry_run is True
        assert config.upsert is True
        assert config.fetch_details is False
        assert config.skip_enrichment is True
        assert config.skip_images is True
        assert config.batch_size == 25
        assert config.debug_prefix is True
        assert config.streaming_insert is False
        assert config.streaming_batch_size == 10
        assert config.filter_existing is False

    def test_dry_run_mode(self):
        """dry_run flag should be independent of other flags."""
        config = PipelineConfig(source_slug="x", dry_run=True, upsert=True)
        assert config.dry_run is True
        assert config.upsert is True

    def test_limit_none_means_unlimited(self):
        """limit=None means no cap on events."""
        config = PipelineConfig(source_slug="x")
        assert config.limit is None

    def test_limit_zero(self):
        """limit=0 is a valid (though edge-case) value."""
        config = PipelineConfig(source_slug="x", limit=0)
        assert config.limit == 0


# ===========================================================================
# PipelineResult
# ===========================================================================


class TestPipelineResult:
    """Test PipelineResult tracking."""

    def _base(self, **overrides) -> PipelineResult:
        defaults = dict(
            source_slug="test",
            source_name="Test Source",
            ccaa="Test CCAA",
            tier=SourceTier.GOLD,
        )
        defaults.update(overrides)
        return PipelineResult(**defaults)

    def test_initial_state(self):
        """Freshly created result should have zero counts and success=True."""
        result = self._base()
        assert result.raw_count == 0
        assert result.parsed_count == 0
        assert result.skipped_past == 0
        assert result.filtered_existing == 0
        assert result.limited_count == 0
        assert result.enriched_count == 0
        assert result.images_found == 0
        assert result.inserted_count == 0
        assert result.skipped_existing == 0
        assert result.failed_count == 0
        assert result.success is True
        assert result.error is None
        assert result.dry_run is False
        assert result.duration_seconds == 0.0
        assert result.categories == {}
        assert result.provinces == {}

    def test_success_result(self):
        """A successful run stores counts correctly."""
        result = self._base(
            raw_count=100,
            parsed_count=95,
            skipped_past=5,
            enriched_count=95,
            inserted_count=90,
            skipped_existing=5,
            duration_seconds=12.3,
        )
        assert result.success is True
        assert result.raw_count == 100
        assert result.parsed_count == 95
        assert result.skipped_past == 5
        assert result.enriched_count == 95
        assert result.inserted_count == 90
        assert result.skipped_existing == 5
        assert result.duration_seconds == 12.3

    def test_failed_result(self):
        """A failed result should carry the error message."""
        result = self._base(success=False, error="Connection timeout")
        assert result.success is False
        assert result.error == "Connection timeout"

    def test_limit_reached_default(self):
        """limit_reached defaults to True."""
        result = self._base()
        assert result.limit_reached is True

    def test_limit_not_reached(self):
        """When fewer events are available than requested."""
        result = self._base(
            requested_limit=50,
            limit_reached=False,
            limited_count=30,
        )
        assert result.requested_limit == 50
        assert result.limit_reached is False
        assert result.limited_count == 30

    def test_dry_run_flag(self):
        """Result can flag that it was a dry run."""
        result = self._base(dry_run=True)
        assert result.dry_run is True

    def test_distributions(self):
        """Category and province distributions are dictionaries."""
        result = self._base(
            categories={"cultural": 5, "social": 3},
            provinces={"Madrid": 4, "Barcelona": 4},
        )
        assert result.categories["cultural"] == 5
        assert result.provinces["Barcelona"] == 4


# ===========================================================================
# _is_future_or_ongoing
# ===========================================================================


class TestIsFutureOrOngoing:
    """Test _is_future_or_ongoing date filtering."""

    def setup_method(self):
        self.pipeline = _make_pipeline()
        self.today = date.today()

    def test_future_event(self):
        """start_date in the future -> True."""
        event = _make_event(start_date=self.today + timedelta(days=7))
        assert self.pipeline._is_future_or_ongoing(event, self.today) is True

    def test_past_event(self):
        """start_date and end_date both in the past -> False."""
        event = _make_event(
            start_date=self.today - timedelta(days=14),
            end_date=self.today - timedelta(days=7),
        )
        assert self.pipeline._is_future_or_ongoing(event, self.today) is False

    def test_ongoing_event(self):
        """start_date in past but end_date in future -> True (ongoing)."""
        event = _make_event(
            start_date=self.today - timedelta(days=3),
            end_date=self.today + timedelta(days=3),
        )
        assert self.pipeline._is_future_or_ongoing(event, self.today) is True

    def test_today_start(self):
        """start_date is today -> True."""
        event = _make_event(start_date=self.today)
        assert self.pipeline._is_future_or_ongoing(event, self.today) is True

    def test_today_end(self):
        """end_date is today -> True (event ends today, still ongoing)."""
        event = _make_event(
            start_date=self.today - timedelta(days=5),
            end_date=self.today,
        )
        assert self.pipeline._is_future_or_ongoing(event, self.today) is True

    def test_no_end_date_future_start(self):
        """start_date in future, no end_date -> True."""
        event = _make_event(start_date=self.today + timedelta(days=1))
        assert event.end_date is None
        assert self.pipeline._is_future_or_ongoing(event, self.today) is True

    def test_no_end_date_past_start(self):
        """start_date in past, no end_date -> False."""
        event = _make_event(start_date=self.today - timedelta(days=1))
        assert event.end_date is None
        assert self.pipeline._is_future_or_ongoing(event, self.today) is False

    def test_far_future_event(self):
        """Event a year from now -> True."""
        event = _make_event(start_date=self.today + timedelta(days=365))
        assert self.pipeline._is_future_or_ongoing(event, self.today) is True

    def test_yesterday_start_no_end(self):
        """Yesterday start, no end -> False (single-day event already passed)."""
        event = _make_event(start_date=self.today - timedelta(days=1))
        assert self.pipeline._is_future_or_ongoing(event, self.today) is False


# ===========================================================================
# _parse_and_filter
# ===========================================================================


class TestParseAndFilter:
    """Test _parse_and_filter with mocked adapter and children filter."""

    def setup_method(self):
        self.pipeline = _make_pipeline()
        self.today = date.today()

    def _raw(self, title: str, start_date: date, end_date: date | None = None) -> dict:
        """Build a minimal raw event dict."""
        return {"title": title, "start_date": start_date, "end_date": end_date}

    @patch("src.core.category_classifier.is_children_only", return_value=False)
    def test_filters_past_events(self, _mock_children):
        """Past events should be filtered out."""
        past_event = _make_event(
            title="Past",
            start_date=self.today - timedelta(days=10),
            external_id="past_1",
        )
        future_event = _make_event(
            title="Future",
            start_date=self.today + timedelta(days=10),
            external_id="future_1",
        )

        self.pipeline.adapter.parse_event = MagicMock(
            side_effect=[past_event, future_event],
        )

        raw = [self._raw("Past", self.today - timedelta(days=10)),
               self._raw("Future", self.today + timedelta(days=10))]

        events, skipped = self.pipeline._parse_and_filter(raw)

        assert len(events) == 1
        assert events[0].title == "Future"
        assert skipped == 1

    @patch("src.core.category_classifier.is_children_only", return_value=False)
    def test_keeps_future_events(self, _mock_children):
        """Future events should be kept."""
        ev1 = _make_event(title="A", start_date=self.today + timedelta(days=1), external_id="a")
        ev2 = _make_event(title="B", start_date=self.today + timedelta(days=2), external_id="b")

        self.pipeline.adapter.parse_event = MagicMock(side_effect=[ev1, ev2])

        raw = [self._raw("A", self.today + timedelta(days=1)),
               self._raw("B", self.today + timedelta(days=2))]

        events, skipped = self.pipeline._parse_and_filter(raw)

        assert len(events) == 2
        assert skipped == 0

    @patch("src.core.category_classifier.is_children_only", return_value=False)
    def test_counts_skipped_correctly(self, _mock_children):
        """Skipped count should equal the number of past events."""
        parsed = [
            _make_event(title=f"past_{i}", start_date=self.today - timedelta(days=i + 1), external_id=f"p{i}")
            for i in range(5)
        ]
        parsed.append(
            _make_event(title="future", start_date=self.today + timedelta(days=1), external_id="f1"),
        )

        self.pipeline.adapter.parse_event = MagicMock(side_effect=parsed)
        raw = [{}] * 6

        events, skipped = self.pipeline._parse_and_filter(raw)

        assert skipped == 5
        assert len(events) == 1

    @patch("src.core.category_classifier.is_children_only", return_value=False)
    def test_skips_none_from_adapter(self, _mock_children):
        """If adapter.parse_event returns None, event is silently dropped."""
        future_event = _make_event(
            title="Valid", start_date=self.today + timedelta(days=5), external_id="v1",
        )
        self.pipeline.adapter.parse_event = MagicMock(
            side_effect=[None, future_event, None],
        )
        raw = [{}, {}, {}]

        events, skipped = self.pipeline._parse_and_filter(raw)

        assert len(events) == 1
        assert events[0].title == "Valid"
        assert skipped == 0  # None returns are not counted as "skipped past"

    @patch("src.core.category_classifier.is_children_only", return_value=True)
    def test_filters_children_only_events(self, _mock_children):
        """Events flagged as children-only should be filtered out."""
        ev = _make_event(
            title="Taller infantil de pintura",
            start_date=self.today + timedelta(days=3),
            external_id="child_1",
        )
        self.pipeline.adapter.parse_event = MagicMock(return_value=ev)
        raw = [{}]

        events, skipped = self.pipeline._parse_and_filter(raw)

        assert len(events) == 0
        assert skipped == 0  # children filter is separate from past filter

    @patch("src.core.category_classifier.is_children_only", return_value=False)
    def test_ongoing_events_kept(self, _mock_children):
        """Ongoing events (past start, future end) should be kept."""
        ev = _make_event(
            title="Expo",
            start_date=self.today - timedelta(days=10),
            end_date=self.today + timedelta(days=10),
            external_id="ongoing_1",
        )
        self.pipeline.adapter.parse_event = MagicMock(return_value=ev)
        raw = [{}]

        events, skipped = self.pipeline._parse_and_filter(raw)

        assert len(events) == 1
        assert skipped == 0

    @patch("src.core.category_classifier.is_children_only", return_value=False)
    def test_empty_raw_list(self, _mock_children):
        """Empty input returns empty output."""
        events, skipped = self.pipeline._parse_and_filter([])
        assert events == []
        assert skipped == 0


# ===========================================================================
# _apply_enrichments
# ===========================================================================


class TestApplyEnrichments:
    """Test _apply_enrichments merging logic."""

    def setup_method(self):
        self.pipeline = _make_pipeline()
        # Mock the source_config so _apply_enrichments can work
        self.pipeline.source_config = MagicMock()
        self.pipeline.source_config.tier = SourceTier.GOLD

    def _enrichment(self, event_id: str, **kwargs) -> EventEnrichment:
        """Build an EventEnrichment with defaults."""
        return EventEnrichment(event_id=event_id, **kwargs)

    @patch("src.core.pipeline.get_category_classifier")
    def test_llm_classifier_assigns_category(self, mock_get_classifier):
        """LLM classifier assigns category as primary method."""
        mock_classifier = MagicMock()
        mock_classifier.classify_llm.return_value = ["cultural"]
        mock_get_classifier.return_value = mock_classifier

        event = _make_event(external_id="e1")
        enrichments = {
            "e1": self._enrichment(
                "e1",
                normalized_text="Concierto de musica clasica en auditorio",
                category_slugs=["cultural"],
            ),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.category_slugs == ["cultural"]
        mock_classifier.classify_llm.assert_called_once()
        # Embedding classifier should NOT be called when LLM succeeds
        mock_classifier.classify.assert_not_called()

    @patch("src.core.pipeline.get_category_classifier")
    def test_llm_classifier_overrides_adapter(self, mock_get_classifier):
        """LLM classifier overrides adapter's hardcoded category."""
        mock_classifier = MagicMock()
        mock_classifier.classify_llm.return_value = ["sanitaria"]
        mock_get_classifier.return_value = mock_classifier

        event = _make_event(external_id="e1", category_slugs=["tecnologia"])
        enrichments = {
            "e1": self._enrichment(
                "e1",
                normalized_text="Taller de nutricion y vida saludable",
            ),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.category_slugs == ["sanitaria"]

    @patch("src.core.pipeline.get_category_classifier")
    def test_embedding_fallback_when_llm_unavailable(self, mock_get_classifier):
        """When LLM returns empty, embedding classifier is used as fallback."""
        mock_classifier = MagicMock()
        mock_classifier.classify_llm.return_value = []  # LLM unavailable
        mock_classifier.confidence_threshold = 0.48
        mock_classifier.classify.return_value = (["social"], {"social": 0.85})
        mock_get_classifier.return_value = mock_classifier

        event = _make_event(external_id="e1")
        enrichments = {
            "e1": self._enrichment(
                "e1",
                normalized_text="Evento social comunitario",
                category_slugs=["social"],
            ),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.category_slugs == ["social"]
        mock_classifier.classify.assert_called_once()

    @patch("src.core.pipeline.get_category_classifier")
    def test_adapter_fallback_when_both_classifiers_fail(self, mock_get_classifier):
        """When LLM and embeddings both fail, adapter category is preserved."""
        mock_classifier = MagicMock()
        mock_classifier.classify_llm.return_value = []  # LLM unavailable
        mock_classifier.confidence_threshold = 0.48
        mock_classifier.classify.return_value = (["cultural"], {"cultural": 0.35})
        mock_get_classifier.return_value = mock_classifier

        event = _make_event(external_id="e1", category_slugs=["social"])
        enrichments = {
            "e1": self._enrichment(
                "e1",
                normalized_text="Algo ambiguo",
                category_slugs=["cultural"],
            ),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        # Adapter category preserved because LLM failed and embeddings low confidence
        assert event.category_slugs == ["social"]

    @patch("src.core.pipeline.get_category_classifier")
    def test_merges_summary(self, mock_get_classifier):
        """Summary from enrichment should be applied to the event."""
        mock_get_classifier.return_value = MagicMock(
            classify_llm=MagicMock(return_value=[]),
            confidence_threshold=0.48,
            classify=MagicMock(return_value=([], {})),
        )

        event = _make_event(external_id="e1")
        enrichments = {
            "e1": self._enrichment("e1", summary="Resumen del evento"),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.summary == "Resumen del evento"

    @patch("src.core.pipeline.get_category_classifier")
    def test_merges_is_free(self, mock_get_classifier):
        """is_free from enrichment should be applied."""
        mock_get_classifier.return_value = MagicMock(
            classify_llm=MagicMock(return_value=[]),
            confidence_threshold=0.48,
            classify=MagicMock(return_value=([], {})),
        )

        event = _make_event(external_id="e1")
        assert event.is_free is None

        enrichments = {
            "e1": self._enrichment("e1", is_free=True),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.is_free is True

    @patch("src.core.pipeline.get_category_classifier")
    def test_merges_price(self, mock_get_classifier):
        """Numeric price from enrichment should be set and is_free forced False."""
        mock_get_classifier.return_value = MagicMock(
            classify_llm=MagicMock(return_value=[]),
            confidence_threshold=0.48,
            classify=MagicMock(return_value=([], {})),
        )

        event = _make_event(external_id="e1")
        enrichments = {
            "e1": self._enrichment("e1", price=15.0),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.price == 15.0
        assert event.is_free is False

    @patch("src.core.pipeline.get_category_classifier")
    def test_merges_normalized_address(self, mock_get_classifier):
        """normalized_address from enrichment should be set as event.address."""
        mock_get_classifier.return_value = MagicMock(
            classify_llm=MagicMock(return_value=[]),
            confidence_threshold=0.48,
            classify=MagicMock(return_value=([], {})),
        )

        event = _make_event(external_id="e1")
        enrichments = {
            "e1": self._enrichment("e1", normalized_address="Calle Mayor 1, Madrid"),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.address == "Calle Mayor 1, Madrid"

    @patch("src.core.pipeline.get_category_classifier")
    def test_price_details_gratis_sets_free(self, mock_get_classifier):
        """price_details containing 'gratis' should set is_free=True and clear price_info."""
        mock_get_classifier.return_value = MagicMock(
            classify_llm=MagicMock(return_value=[]),
            confidence_threshold=0.48,
            classify=MagicMock(return_value=([], {})),
        )

        event = _make_event(external_id="e1")
        enrichments = {
            "e1": self._enrichment("e1", price_details="Gratis"),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.is_free is True
        assert event.price_info is None

    @patch("src.core.pipeline.get_category_classifier")
    def test_price_details_non_free(self, mock_get_classifier):
        """price_details with actual info should populate price_info."""
        mock_get_classifier.return_value = MagicMock(
            classify_llm=MagicMock(return_value=[]),
            confidence_threshold=0.48,
            classify=MagicMock(return_value=([], {})),
        )

        event = _make_event(external_id="e1")
        enrichments = {
            "e1": self._enrichment("e1", price_details="10 EUR - descuento jubilados"),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.price_info == "10 EUR - descuento jubilados"

    @patch("src.core.pipeline.get_category_classifier")
    def test_no_enrichment_for_event(self, mock_get_classifier):
        """Events without a matching enrichment should be left unchanged."""
        mock_get_classifier.return_value = MagicMock()

        event = _make_event(external_id="e1", category_slugs=[])
        enrichments = {
            "other_id": self._enrichment("other_id", summary="Not for e1"),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.summary is None
        assert event.category_slugs == []

    @patch("src.core.pipeline.get_category_classifier")
    def test_venue_based_free_inference(self, mock_get_classifier):
        """Venue name containing 'biblioteca' should infer is_free=True."""
        mock_get_classifier.return_value = MagicMock(
            classify_llm=MagicMock(return_value=[]),
            confidence_threshold=0.48,
            classify=MagicMock(return_value=([], {})),
        )

        event = _make_event(external_id="e1", venue_name="Biblioteca Municipal")
        # Enrichment with no price info -> is_free stays None from enrichment
        enrichments = {
            "e1": self._enrichment("e1"),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.is_free is True

    @patch("src.core.pipeline.get_category_classifier")
    def test_category_fallback_to_enrichment_when_no_normalized_text(self, mock_get_classifier):
        """When LLM unavailable and no normalized_text, enrichment category_slugs are used."""
        mock_classifier = MagicMock()
        mock_classifier.classify_llm.return_value = []  # LLM unavailable
        mock_classifier.confidence_threshold = 0.48
        mock_get_classifier.return_value = mock_classifier

        event = _make_event(external_id="e1")
        enrichments = {
            "e1": self._enrichment(
                "e1",
                normalized_text=None,
                category_slugs=["tecnologia"],
            ),
        }

        self.pipeline._apply_enrichments([event], enrichments)

        assert event.category_slugs == ["tecnologia"]
        # Embedding classifier should NOT be called when there's no normalized_text
        mock_classifier.classify.assert_not_called()


# ===========================================================================
# Helper methods: _count_categories, _count_provinces
# ===========================================================================


class TestCountHelpers:
    """Test _count_categories and _count_provinces."""

    def setup_method(self):
        self.pipeline = _make_pipeline()

    def test_count_categories(self):
        events = [
            _make_event(external_id="1", category_slugs=["cultural"]),
            _make_event(external_id="2", category_slugs=["cultural", "social"]),
            _make_event(external_id="3", category_slugs=["social"]),
            _make_event(external_id="4"),  # no categories -> "N/A"
        ]

        result = self.pipeline._count_categories(events)

        assert result["cultural"] == 2
        assert result["social"] == 1
        assert result["N/A"] == 1

    def test_count_categories_empty(self):
        assert self.pipeline._count_categories([]) == {}

    def test_count_provinces(self):
        events = [
            _make_event(external_id="1", province="Madrid"),
            _make_event(external_id="2", province="Madrid"),
            _make_event(external_id="3", province="Barcelona"),
            _make_event(external_id="4"),  # no province -> "N/A"
        ]

        result = self.pipeline._count_provinces(events)

        assert result["Madrid"] == 2
        assert result["Barcelona"] == 1
        assert result["N/A"] == 1

    def test_count_provinces_empty(self):
        assert self.pipeline._count_provinces([]) == {}
