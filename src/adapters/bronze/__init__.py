"""Bronze tier adapters - Web scraping sources (HTML/Firecrawl)."""

from src.adapters.bronze.larioja_agenda import LaRiojaAgendaAdapter
from src.adapters.bronze.navarra import NavarraAdapter
from src.adapters.bronze.visitnavarra import VisitNavarraAdapter

__all__ = ["LaRiojaAgendaAdapter", "NavarraAdapter", "VisitNavarraAdapter"]
