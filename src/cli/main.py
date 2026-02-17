"""Unified CLI for Agendades event scraper.

Usage:
    agendades insert --source catalunya_agenda --limit 20
    agendades insert --tier gold --dry-run
    agendades insert --ccaa "Cataluña" --limit 10
    agendades sources --tier gold
    agendades sources --ccaa "Madrid"
"""

import asyncio
import os
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Enable LLM by default
os.environ.setdefault("LLM_ENABLED", "true")

from src.config.sources import SourceRegistry, SourceTier
from src.core.pipeline import InsertionPipeline, PipelineConfig, PipelineResult

app = typer.Typer(
    name="agendades",
    help="Cultural events scraper for Spanish regions",
    add_completion=False,
)
console = Console()


def tier_callback(value: str | None) -> SourceTier | None:
    """Convert tier string to SourceTier enum."""
    if value is None:
        return None
    try:
        return SourceTier(value.lower())
    except ValueError:
        valid = ", ".join([t.value for t in SourceTier])
        raise typer.BadParameter(f"Invalid tier. Must be one of: {valid}")


@app.command()
def insert(
    source: Optional[str] = typer.Option(
        None,
        "--source", "-s",
        help="Process only this source slug",
    ),
    tier: Optional[str] = typer.Option(
        None,
        "--tier", "-t",
        help="Process all sources of this tier (gold, silver, bronze)",
    ),
    ccaa: Optional[str] = typer.Option(
        None,
        "--ccaa", "-c",
        help="Filter sources by CCAA name",
    ),
    limit: int = typer.Option(
        20,
        "--limit", "-l",
        help="Max events per source",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Test without inserting to database",
    ),
    upsert: bool = typer.Option(
        False,
        "--upsert",
        help="Update existing events instead of skipping",
    ),
    no_details: bool = typer.Option(
        False,
        "--no-details",
        help="Skip fetching detail pages (Bronze sources)",
    ),
    no_enrich: bool = typer.Option(
        False,
        "--no-enrich",
        help="Skip LLM enrichment",
    ),
    no_images: bool = typer.Option(
        False,
        "--no-images",
        help="Skip image fetching",
    ),
    debug_prefix: bool = typer.Option(
        False,
        "--debug-prefix",
        help="Add [source_slug] prefix to titles (for testing)",
    ),
):
    """Insert events from sources into Supabase.

    Examples:
        agendades insert --source catalunya_agenda --limit 20
        agendades insert --tier gold --dry-run
        agendades insert --ccaa "Cataluña" --limit 10
        agendades insert --tier bronze --ccaa "Canarias"
    """
    # Validate options
    if not source and not tier:
        console.print("[red]Error:[/red] Must specify --source or --tier")
        raise typer.Exit(1)

    if source and tier:
        console.print("[yellow]Warning:[/yellow] Both --source and --tier specified. Using --source only.")

    # Get sources to process
    sources_to_process = []

    if source:
        config = SourceRegistry.get(source)
        if not config:
            console.print(f"[red]Error:[/red] Unknown source: {source}")
            available = SourceRegistry.slugs()[:10]
            console.print(f"Available: {', '.join(available)}...")
            raise typer.Exit(1)
        sources_to_process = [config]
    else:
        tier_enum = tier_callback(tier)
        sources_to_process = SourceRegistry.get_by_tier(tier_enum)

        if ccaa:
            sources_to_process = [
                s for s in sources_to_process
                if s.ccaa.lower() == ccaa.lower()
            ]

    if not sources_to_process:
        console.print("[yellow]Warning:[/yellow] No sources match the criteria")
        raise typer.Exit(0)

    # Print header
    console.print()
    console.print("[bold blue]AGENDADES EVENT INSERTION[/bold blue]")
    console.print(f"Sources: {len(sources_to_process)}, Limit: {limit}/source")
    console.print(f"Dry run: {dry_run}, Upsert: {upsert}")
    if no_enrich:
        console.print("[yellow]LLM enrichment disabled[/yellow]")
    if no_images:
        console.print("[yellow]Image fetching disabled[/yellow]")
    if debug_prefix:
        console.print("[cyan]Debug prefix enabled: [source_slug] Title[/cyan]")
    console.print()

    # Run pipeline for each source
    results: list[PipelineResult] = []

    async def run_all():
        for src_config in sources_to_process:
            console.print(f"\n[bold]{'='*60}[/bold]")
            console.print(f"[bold cyan]{src_config.slug.upper()}[/bold cyan]")
            console.print(f"CCAA: {src_config.ccaa} | Tier: {src_config.tier.value}")
            console.print(f"[bold]{'='*60}[/bold]")

            config = PipelineConfig(
                source_slug=src_config.slug,
                limit=limit,
                dry_run=dry_run,
                upsert=upsert,
                fetch_details=not no_details,
                skip_enrichment=no_enrich,
                skip_images=no_images,
                debug_prefix=debug_prefix,
            )
            pipeline = InsertionPipeline(config)

            console.print("  Processing...")
            result = await pipeline.run()

            results.append(result)

            # Print result
            if result.success:
                if result.dry_run:
                    console.print(f"[yellow]DRY RUN[/yellow] - Would insert {result.limited_count} events")
                else:
                    console.print(f"[green]OK[/green] - Inserted: {result.inserted_count}, Skipped: {result.skipped_existing}")
                console.print(f"  Raw: {result.raw_count}, Parsed: {result.parsed_count}, Skipped past: {result.skipped_past}")
                if result.categories:
                    console.print(f"  Categories: {result.categories}")
                if result.provinces and len(result.provinces) > 1:
                    console.print(f"  Provinces: {result.provinces}")
            else:
                console.print(f"[red]ERROR[/red]: {result.error}")

    asyncio.run(run_all())

    # Final summary
    print_summary(results)


def print_summary(results: list[PipelineResult]) -> None:
    """Print final summary table."""
    console.print()
    console.print("[bold blue]FINAL SUMMARY[/bold blue]")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Source")
    table.add_column("CCAA")
    table.add_column("Parsed", justify="right")
    table.add_column("Inserted", justify="right")
    table.add_column("Skipped", justify="right")
    table.add_column("Status")

    total_parsed = 0
    total_inserted = 0
    total_skipped = 0

    for r in results:
        total_parsed += r.parsed_count
        total_inserted += r.inserted_count
        total_skipped += r.skipped_existing

        if r.success:
            status = "[yellow]DRY[/yellow]" if r.dry_run else "[green]OK[/green]"
        else:
            status = f"[red]ERR[/red]"

        table.add_row(
            r.source_slug,
            r.ccaa[:15],
            str(r.parsed_count),
            str(r.inserted_count),
            str(r.skipped_existing),
            status,
        )

    console.print(table)
    console.print()
    console.print(f"[bold]TOTALS:[/bold] Parsed: {total_parsed}, Inserted: {total_inserted}, Skipped: {total_skipped}")


@app.command()
def sources(
    tier: Optional[str] = typer.Option(
        None,
        "--tier", "-t",
        help="Filter by tier (gold, silver, bronze)",
    ),
    ccaa: Optional[str] = typer.Option(
        None,
        "--ccaa", "-c",
        help="Filter by CCAA name",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show full source details",
    ),
):
    """List available event sources.

    Examples:
        agendades sources
        agendades sources --tier gold
        agendades sources --ccaa "Cataluña"
    """
    sources = SourceRegistry.all()

    if tier:
        tier_enum = tier_callback(tier)
        sources = [s for s in sources if s.tier == tier_enum]

    if ccaa:
        sources = [s for s in sources if s.ccaa.lower() == ccaa.lower()]

    if not sources:
        console.print("[yellow]No sources match the criteria[/yellow]")
        raise typer.Exit(0)

    # Group by tier
    by_tier: dict[SourceTier, list] = {}
    for s in sources:
        if s.tier not in by_tier:
            by_tier[s.tier] = []
        by_tier[s.tier].append(s)

    for tier_key in [SourceTier.GOLD, SourceTier.SILVER, SourceTier.BRONZE]:
        if tier_key not in by_tier:
            continue

        tier_sources = by_tier[tier_key]
        console.print()
        console.print(f"[bold cyan]{tier_key.value.upper()}[/bold cyan] ({len(tier_sources)} sources)")
        console.print()

        table = Table(show_header=True, header_style="bold")
        table.add_column("Slug")
        table.add_column("Name")
        table.add_column("CCAA")
        if verbose:
            table.add_column("Province")

        for s in sorted(tier_sources, key=lambda x: (x.ccaa, x.slug)):
            if verbose:
                province = getattr(s, "province", "") or ""
                table.add_row(s.slug, s.name[:40], s.ccaa, province)
            else:
                table.add_row(s.slug, s.name[:40], s.ccaa)

        console.print(table)

    # Summary
    console.print()
    counts = SourceRegistry.count_by_tier()
    console.print(f"[bold]Total:[/bold] {SourceRegistry.count()} sources")
    for t, c in counts.items():
        if c > 0:
            console.print(f"  {t.value}: {c}")


@app.command()
def stats():
    """Show database statistics (requires Supabase connection)."""
    console.print("[yellow]Stats command not yet implemented[/yellow]")
    console.print("Will show: events by CCAA, by source, by category, etc.")


@app.command()
def version():
    """Show version information."""
    console.print("[bold]Agendades Event Scraper[/bold]")
    console.print("Version: 2.0.0")
    console.print("Python: 3.11+")

    # Show counts
    counts = SourceRegistry.count_by_tier()
    console.print()
    console.print("[bold]Registered sources:[/bold]")
    for t, c in counts.items():
        if c > 0:
            console.print(f"  {t.value}: {c}")
    console.print(f"  Total: {SourceRegistry.count()}")


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
