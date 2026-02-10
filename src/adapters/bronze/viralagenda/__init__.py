"""Viralagenda adapters - scraping events from viralagenda.com.

Viralagenda covers multiple Spanish CCAA with consistent HTML structure.
This module provides a base adapter and province-specific configs.
"""

from src.adapters.bronze.viralagenda.base import (
    ViralAgendaAdapter,
    ViralAgendaConfig,
    VIRALAGENDA_SOURCES,
    get_viralagenda_source_ids,
)

__all__ = [
    "ViralAgendaAdapter",
    "ViralAgendaConfig",
    "VIRALAGENDA_SOURCES",
    "get_viralagenda_source_ids",
]
