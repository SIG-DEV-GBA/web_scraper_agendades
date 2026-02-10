"""Unified CLI for Agendades scraper.

Usage:
    python -m src.cli [command] [options]

Commands:
    insert      Insert events from sources
    sources     List available sources
    stats       Show database statistics
"""

from src.cli.main import app

__all__ = ["app"]
