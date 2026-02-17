"""Unified event insertion pipeline.

Provides a single pipeline that handles:
1. Fetching events from any source tier (Gold, Silver, Bronze, Eventbrite)
2. Filtering past events
3. LLM enrichment (categories, summaries, prices)
4. Image fetching for events without images
5. Supabase insertion

Usage:
    from src.core.pipeline import InsertionPipeline, PipelineConfig

    config = PipelineConfig(
        source_slug="catalunya_agenda",
        limit=20,
        dry_run=True,
    )
    pipeline = InsertionPipeline(config)
    result = await pipeline.run()
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from src.config.sources import (
    AnySourceConfig,
    BronzeSourceConfig,
    EventbriteSourceConfig,
    GoldSourceConfig,
    SilverSourceConfig,
    SourceRegistry,
    SourceTier,
)
from src.core.event_model import EventBatch, EventCreate
from src.core.image_provider import get_image_provider
from src.core.category_classifier import get_category_classifier
from src.core.llm_enricher import SourceTier as EnricherTier, get_llm_enricher
from src.core.supabase_client import get_supabase_client
from src.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for the insertion pipeline."""

    source_slug: str
    limit: int | None = None  # None = unlimited
    dry_run: bool = False
    upsert: bool = False
    fetch_details: bool = True
    skip_enrichment: bool = False
    skip_images: bool = False
    batch_size: int = 10
    debug_prefix: bool = False  # Add source prefix to titles for testing


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    source_slug: str
    source_name: str
    ccaa: str
    tier: SourceTier

    # Counts
    raw_count: int = 0
    parsed_count: int = 0
    skipped_past: int = 0
    limited_count: int = 0
    enriched_count: int = 0
    images_found: int = 0
    inserted_count: int = 0
    skipped_existing: int = 0
    failed_count: int = 0

    # Limit info
    requested_limit: int | None = None
    limit_reached: bool = True  # False if requested more than available

    # Distributions
    categories: dict[str, int] = field(default_factory=dict)
    provinces: dict[str, int] = field(default_factory=dict)

    # Status
    success: bool = True
    error: str | None = None
    dry_run: bool = False

    # Timing
    duration_seconds: float = 0.0


class InsertionPipeline:
    """Unified pipeline for inserting events from any source.

    Handles the full workflow:
    1. Get source config from registry
    2. Create appropriate adapter
    3. Fetch events
    4. Filter past events
    5. Apply limit
    6. Run LLM enrichment
    7. Fetch images
    8. Insert to Supabase
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.source_config: AnySourceConfig | None = None
        self.adapter: Any = None

    async def run(self) -> PipelineResult:
        """Execute the full pipeline.

        Returns:
            PipelineResult with stats and status
        """
        start_time = datetime.now()

        # Initialize result
        result = PipelineResult(
            source_slug=self.config.source_slug,
            source_name="",
            ccaa="",
            tier=SourceTier.GOLD,
            dry_run=self.config.dry_run,
        )

        try:
            # Step 1: Get source config
            self.source_config = SourceRegistry.get(self.config.source_slug)
            if not self.source_config:
                raise ValueError(f"Unknown source: {self.config.source_slug}")

            result.source_name = self.source_config.name
            result.ccaa = self.source_config.ccaa
            result.tier = self.source_config.tier

            logger.info(
                "pipeline_start",
                source=self.config.source_slug,
                tier=self.source_config.tier.value,
                ccaa=self.source_config.ccaa,
            )

            # Step 2: Create adapter
            self.adapter = self._create_adapter()

            # Step 3: Fetch events
            raw_events = await self._fetch_events()
            result.raw_count = len(raw_events)

            # Step 4: Parse and filter
            events, skipped = self._parse_and_filter(raw_events)
            result.parsed_count = len(events)
            result.skipped_past = skipped

            if not events:
                logger.warning("pipeline_no_events", source=self.config.source_slug)
                return result

            # Step 5: Apply limit (if specified)
            result.requested_limit = self.config.limit
            if self.config.limit is not None:
                if len(events) < self.config.limit:
                    result.limit_reached = False
                    logger.warning(
                        "pipeline_limit_not_reached",
                        source=self.config.source_slug,
                        requested=self.config.limit,
                        available=len(events),
                        message=f"Solicitados {self.config.limit} eventos pero solo hay {len(events)} disponibles",
                    )
                else:
                    result.limit_reached = True
                events = events[: self.config.limit]
            result.limited_count = len(events)

            # Step 5b: Add debug prefix to titles (for testing)
            if self.config.debug_prefix:
                prefix = f"[{self.config.source_slug}] "
                for event in events:
                    if not event.title.startswith("["):
                        event.title = prefix + event.title

            # Step 6: LLM enrichment
            if not self.config.skip_enrichment:
                enrichments = self._run_enrichment(events)
                self._apply_enrichments(events, enrichments)
                result.enriched_count = len(enrichments)

            # Step 7: Fetch images
            if not self.config.skip_images:
                images_found = self._fetch_images(events, enrichments if not self.config.skip_enrichment else {})
                result.images_found = images_found

            # Step 8: Calculate distributions
            result.categories = self._count_categories(events)
            result.provinces = self._count_provinces(events)

            # Step 9: Insert to Supabase (or dry run)
            if self.config.dry_run:
                logger.info(
                    "pipeline_dry_run",
                    source=self.config.source_slug,
                    would_insert=len(events),
                )
            else:
                stats = await self._insert_events(events)
                result.inserted_count = stats["inserted"]
                result.skipped_existing = stats["skipped"]
                result.failed_count = stats["failed"]

            result.success = True

        except Exception as e:
            logger.error(
                "pipeline_error",
                source=self.config.source_slug,
                error=str(e),
            )
            result.success = False
            result.error = str(e)

        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        return result

    def _create_adapter(self) -> Any:
        """Create the appropriate adapter for the source."""
        if isinstance(self.source_config, GoldSourceConfig):
            from src.adapters import get_adapter

            adapter_class = get_adapter(self.config.source_slug)
            if not adapter_class:
                raise ValueError(f"No adapter registered for {self.config.source_slug}")
            return adapter_class()

        elif isinstance(self.source_config, BronzeSourceConfig):
            from src.adapters.bronze_scraper_adapter import BronzeScraperAdapter

            return BronzeScraperAdapter(self.config.source_slug)

        elif isinstance(self.source_config, EventbriteSourceConfig):
            from src.adapters.eventbrite_adapter import EventbriteAdapter

            return EventbriteAdapter(self.config.source_slug)

        elif isinstance(self.source_config, SilverSourceConfig):
            from src.adapters.silver_rss_adapter import SilverRSSAdapter

            return SilverRSSAdapter(self.config.source_slug)

        else:
            raise ValueError(f"Unknown source config type: {type(self.source_config)}")

    async def _fetch_events(self) -> list[dict[str, Any]]:
        """Fetch events from the source."""
        tier = self.source_config.tier

        if tier == SourceTier.GOLD:
            return await self.adapter.fetch_events(max_pages=3)

        elif tier == SourceTier.BRONZE:
            return await self.adapter.fetch_events(
                enrich=False,
                fetch_details=self.config.fetch_details,
            )

        elif tier == SourceTier.EVENTBRITE:
            # Pass limit to avoid fetching details for events we won't use
            return await self.adapter.fetch_events(limit=self.config.limit)

        elif tier == SourceTier.SILVER:
            return await self.adapter.fetch_events()

        else:
            raise ValueError(f"Unknown tier: {tier}")

    def _parse_and_filter(self, raw_events: list[dict]) -> tuple[list[EventCreate], int]:
        """Parse raw events and filter past events.

        Returns:
            Tuple of (valid events, count of skipped past events)
        """
        today = date.today()
        events = []
        skipped_past = 0

        for raw in raw_events:
            event = self.adapter.parse_event(raw)
            if not event:
                continue

            # Check if event is valid (not past)
            is_valid = self._is_future_or_ongoing(event, today)
            if is_valid:
                events.append(event)
            else:
                skipped_past += 1

        return events, skipped_past

    def _is_future_or_ongoing(self, event: EventCreate, today: date) -> bool:
        """Check if event is future or ongoing.

        An event is valid if:
        - end_date >= today (ongoing), or
        - start_date >= today (future, no end_date)
        """
        try:
            end_dt = event.end_date
            start_dt = event.start_date

            # Convert to date objects if needed
            if end_dt and not isinstance(end_dt, date):
                end_dt = datetime.fromisoformat(str(end_dt).replace("Z", "")).date()
            if start_dt and not isinstance(start_dt, date):
                start_dt = datetime.fromisoformat(str(start_dt).replace("Z", "")).date()

            # Check validity
            if end_dt and end_dt >= today:
                return True
            if start_dt and start_dt >= today:
                return True
            return False

        except (ValueError, TypeError):
            # If date parsing fails, include the event
            return True

    def _run_enrichment(self, events: list[EventCreate]) -> dict[str, Any]:
        """Run LLM enrichment on events."""
        enricher = get_llm_enricher()

        # Prepare events for LLM
        events_for_llm = []
        for e in events:
            events_for_llm.append({
                "id": e.external_id,
                "title": e.title,
                "description": e.description or "",
                "venue": e.venue_name or "",  # Important for is_free inference
                "location": f"{e.city or ''}, {e.province or ''}, {e.comunidad_autonoma or ''}".strip(", "),
                "@type": e.category_name or "",
                "audience": "",
                "price_info": e.price_info or "",
            })

        # Map source tier to enricher tier
        tier_map = {
            SourceTier.GOLD: EnricherTier.ORO,
            SourceTier.SILVER: EnricherTier.PLATA,
            SourceTier.BRONZE: EnricherTier.BRONCE,
            SourceTier.EVENTBRITE: EnricherTier.BRONCE,  # Eventbrite uses Bronze tier
        }
        enricher_tier = tier_map.get(self.source_config.tier, EnricherTier.ORO)

        return enricher.enrich_batch(
            events_for_llm,
            batch_size=self.config.batch_size,
            tier=enricher_tier,
        )

    def _apply_enrichments(self, events: list[EventCreate], enrichments: dict[str, Any]) -> None:
        """Apply LLM enrichments to events with hybrid classification.

        Uses embedding-based classification on the normalized_text from LLM.
        This provides more consistent category assignment than LLM alone.
        """
        # Get category classifier for embedding-based classification
        classifier = get_category_classifier()

        for event in events:
            enrichment = enrichments.get(event.external_id)
            if not enrichment:
                continue

            # Hybrid classification: Use normalized_text for embedding-based categorization
            if enrichment.normalized_text:
                # Classify using embeddings (more consistent than LLM categories)
                categories, scores = classifier.classify(
                    text=enrichment.normalized_text,
                    title=event.title,
                )
                if categories:
                    event.category_slugs = categories
                    logger.debug(
                        "hybrid_classification",
                        event_id=event.external_id,
                        categories=categories,
                        top_score=max(scores.values()) if scores else 0,
                    )
                elif enrichment.category_slugs:
                    # Fallback to LLM categories if embedding fails
                    event.category_slugs = enrichment.category_slugs
            elif enrichment.category_slugs:
                # No normalized_text, use LLM categories directly
                event.category_slugs = enrichment.category_slugs

            # Summary
            if enrichment.summary:
                event.summary = enrichment.summary

            # is_free from LLM (highest priority)
            if enrichment.is_free is not None:
                event.is_free = enrichment.is_free

            # Price
            if enrichment.price is not None:
                event.price = enrichment.price
                event.is_free = False

            # Price info/details
            if enrichment.price_details:
                details = enrichment.price_details.strip()
                if details.lower() in ["gratis", "gratuito", "gratuït", "libre", "entrada libre"]:
                    event.price_info = None
                    event.is_free = True
                else:
                    event.price_info = details if details else None
            elif enrichment.price is not None:
                # Clear price_info to avoid duplication
                event.price_info = None

            # Fallback: infer from price_info text
            if event.is_free is None and event.price_info:
                price_lower = event.price_info.lower()
                free_words = ["gratis", "gratuito", "gratuït", "libre", "lliure"]
                if any(word in price_lower for word in free_words):
                    event.is_free = True
                    event.price_info = None

            # Fallback: infer from venue (public venues often free)
            if event.is_free is None and event.venue_name:
                venue_lower = event.venue_name.lower()
                free_venue_keywords = [
                    "biblioteca", "museo", "archivo", "casa de cultura",
                    "centro cultural", "centro cívico", "sala de exposiciones",
                ]
                if any(kw in venue_lower for kw in free_venue_keywords):
                    event.is_free = True

    def _fetch_images(self, events: list[EventCreate], enrichments: dict[str, Any]) -> int:
        """Fetch images for events without source_image_url."""
        image_provider = get_image_provider()
        if not image_provider.unsplash:
            return 0

        images_found = 0
        for event in events:
            if event.source_image_url:
                continue

            enrichment = enrichments.get(event.external_id)
            if enrichment and enrichment.image_keywords:
                image_url = image_provider.get_image(
                    keywords=enrichment.image_keywords,
                    category=enrichment.category_slugs[0] if enrichment.category_slugs else "default",
                )
                if image_url:
                    event.source_image_url = image_url
                    images_found += 1

        return images_found

    def _count_categories(self, events: list[EventCreate]) -> dict[str, int]:
        """Count events by primary category."""
        counts: dict[str, int] = {}
        for e in events:
            cat = e.category_slugs[0] if e.category_slugs else "N/A"
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def _count_provinces(self, events: list[EventCreate]) -> dict[str, int]:
        """Count events by province."""
        counts: dict[str, int] = {}
        for e in events:
            prov = e.province or "N/A"
            counts[prov] = counts.get(prov, 0) + 1
        return counts

    async def _insert_events(self, events: list[EventCreate]) -> dict[str, int]:
        """Insert events to Supabase."""
        client = get_supabase_client()

        batch = EventBatch(
            source_id=self.config.source_slug,
            source_name=self.source_config.name,
            ccaa=self.source_config.ccaa,
            scraped_at=datetime.now().isoformat(),
            events=events,
            total_found=len(events),
        )

        return await client.save_batch(batch, skip_existing=not self.config.upsert)


async def run_pipeline(
    source_slug: str,
    limit: int = 20,
    dry_run: bool = False,
    upsert: bool = False,
    fetch_details: bool = True,
) -> PipelineResult:
    """Convenience function to run a single source pipeline.

    Args:
        source_slug: Source identifier
        limit: Max events to process
        dry_run: If True, don't insert to database
        upsert: If True, update existing events
        fetch_details: If True, fetch detail pages (Bronze)

    Returns:
        PipelineResult with stats
    """
    config = PipelineConfig(
        source_slug=source_slug,
        limit=limit,
        dry_run=dry_run,
        upsert=upsert,
        fetch_details=fetch_details,
    )
    pipeline = InsertionPipeline(config)
    return await pipeline.run()


async def run_tier_pipeline(
    tier: SourceTier,
    limit: int = 20,
    dry_run: bool = False,
    upsert: bool = False,
    ccaa_filter: str | None = None,
) -> list[PipelineResult]:
    """Run pipeline for all sources in a tier.

    Args:
        tier: Source tier (GOLD, SILVER, BRONZE, EVENTBRITE)
        limit: Max events per source
        dry_run: If True, don't insert to database
        upsert: If True, update existing events
        ccaa_filter: Optional CCAA to filter sources

    Returns:
        List of PipelineResult for each source
    """
    sources = SourceRegistry.get_by_tier(tier)

    if ccaa_filter:
        sources = [s for s in sources if s.ccaa.lower() == ccaa_filter.lower()]

    results = []
    for source in sources:
        result = await run_pipeline(
            source_slug=source.slug,
            limit=limit,
            dry_run=dry_run,
            upsert=upsert,
        )
        results.append(result)

    return results
