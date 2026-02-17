"""Silver-level RSS source configurations.

Silver sources are semi-structured RSS/HTML feeds that provide event data
requiring moderate parsing effort.

These sources use the balanced LLM tier (llama-3.3-70b) for enrichment.
"""

from src.config.sources import (
    SilverSourceConfig,
    SourceRegistry,
    SourceTier,
)

# ============================================================
# SILVER SOURCE CONFIGURATIONS
# ============================================================

SILVER_SOURCES: list[SilverSourceConfig] = [
    SilverSourceConfig(
        slug="galicia_cultura",
        name="Agenda Cultural de Galicia (cultura.gal)",
        url="https://www.cultura.gal/es/rssaxenda",
        ccaa="Galicia",
        ccaa_code="GA",
        tier=SourceTier.SILVER,
        feed_type="rss",
    ),
    SilverSourceConfig(
        slug="huesca_radar",
        name="RADAR Huesca - Programación Cultural",
        url="https://radarhuesca.es/eventos/feed/",
        ccaa="Aragón",
        ccaa_code="AR",
        tier=SourceTier.SILVER,
        feed_type="rss",
    ),
]

# Register all Silver sources
SourceRegistry.register_many(SILVER_SOURCES)
