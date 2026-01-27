"""Main entry point for the Agendades scraper."""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def run_scraper(
    source_ids: list[str] | None = None,
    use_llm: bool = True,
) -> None:
    """Run scrapers for specified sources or all enabled sources.

    Args:
        source_ids: Optional list of source IDs to run. If None, runs all enabled.
        use_llm: Whether to use LLM for enrichment (default: True)
    """
    from src.adapters import ADAPTER_REGISTRY, list_adapters
    from src.core.llm_enricher import SourceTier, get_llm_enricher
    from src.core.supabase_client import get_supabase_client

    available = list_adapters()
    logger.info("Available adapters", adapters=available)

    if not available:
        logger.warning("No adapters registered. Import adapter modules to register them.")
        return

    # Filter to requested sources or all
    if source_ids:
        to_run = [sid for sid in source_ids if sid in ADAPTER_REGISTRY]
        if not to_run:
            logger.error("None of the requested sources are available", requested=source_ids)
            return
    else:
        to_run = available

    # Get Supabase client and LLM enricher
    db = get_supabase_client()
    enricher = get_llm_enricher() if use_llm else None

    # Run each adapter
    for source_id in to_run:
        adapter_class = ADAPTER_REGISTRY[source_id]
        logger.info("Running adapter", source_id=source_id)

        try:
            async with adapter_class() as adapter:
                batch = await adapter.scrape()

                logger.info(
                    "Scrape completed",
                    source_id=source_id,
                    events_found=batch.total_found,
                    events_parsed=batch.success_count,
                    errors=batch.error_count,
                )

                if batch.events:
                    # Enrich events with LLM if enabled
                    if enricher and enricher.is_enabled:
                        logger.info("Enriching events with LLM", count=len(batch.events))

                        # Convert events to dict for LLM
                        events_for_llm = [
                            {
                                "id": e.external_id,
                                "title": e.title,
                                "description": e.description or "",
                                "@type": e.category_name or "",
                                "audience": "",
                                "price_info": e.price_info or "",
                            }
                            for e in batch.events
                        ]

                        # Get enrichments
                        enrichments = enricher.enrich_batch(
                            events_for_llm,
                            batch_size=20,
                            tier=SourceTier.ORO,
                        )

                        # Apply enrichments to events
                        for event in batch.events:
                            enrichment = enrichments.get(event.external_id)
                            if enrichment:
                                event.category_slugs = enrichment.category_slugs
                                if enrichment.summary:
                                    event.summary = enrichment.summary
                                if enrichment.price is not None:
                                    event.price = enrichment.price
                                if enrichment.price_details:
                                    event.price_info = enrichment.price_details
                                if enrichment.age_range:
                                    # Could store in a field if needed
                                    pass

                        logger.info("Enrichment applied", enriched=len(enrichments))

                    stats = await db.save_batch(batch, skip_existing=True)
                    logger.info("Saved to database", source_id=source_id, **stats)

        except Exception as e:
            logger.error("Adapter failed", source_id=source_id, error=str(e), exc_info=True)


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Agendades Event Scraper")
    parser.add_argument(
        "--sources",
        "-s",
        nargs="*",
        help="Source IDs to scrape (default: all enabled)",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available adapters and exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )
    parser.add_argument(
        "--log-format",
        default="console",
        choices=["console", "json"],
        help="Log format (default: console)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM enrichment (faster, but no smart categorization)",
    )

    args = parser.parse_args()

    # Setup logging
    settings = get_settings()
    setup_logging(
        level=args.log_level,
        log_format=args.log_format,
        log_file=settings.log_file,
    )

    # List adapters and exit
    if args.list:
        from src.adapters import list_adapters

        print("Available adapters:")
        for adapter_id in list_adapters():
            print(f"  - {adapter_id}")
        return

    # Run scrapers
    logger.info("Starting Agendades Scraper", sources=args.sources or "all", llm=not args.no_llm)
    asyncio.run(run_scraper(args.sources, use_llm=not args.no_llm))
    logger.info("Scraper finished")


if __name__ == "__main__":
    main()
