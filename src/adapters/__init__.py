"""Adapters for different event sources (one per CCAA/source)."""

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.core.base_adapter import BaseAdapter

# Registry of all available adapters
ADAPTER_REGISTRY: dict[str, type["BaseAdapter"]] = {}

# Flag to prevent circular imports during loading
_adapters_loaded = False


def register_adapter(source_id: str) -> Callable[[type["BaseAdapter"]], type["BaseAdapter"]]:
    """Decorator to register an adapter in the registry.

    Usage:
        @register_adapter("madrid_datos_abiertos")
        class MadridAdapter(BaseAdapter):
            ...
    """

    def decorator(adapter_class: type["BaseAdapter"]) -> type["BaseAdapter"]:
        ADAPTER_REGISTRY[source_id] = adapter_class
        return adapter_class

    return decorator


def get_adapter(source_id: str) -> type["BaseAdapter"] | None:
    """Get an adapter class by its source_id."""
    _ensure_adapters_loaded()
    return ADAPTER_REGISTRY.get(source_id)


def list_adapters() -> list[str]:
    """List all registered adapter source_ids."""
    _ensure_adapters_loaded()
    return list(ADAPTER_REGISTRY.keys())


def _ensure_adapters_loaded() -> None:
    """Ensure all adapter modules are loaded."""
    global _adapters_loaded
    if _adapters_loaded:
        return
    _adapters_loaded = True

    # Import adapter modules to trigger registration
    # Gold tier (structured APIs)
    from src.adapters import gold_api_adapter  # noqa: F401
    # Silver tier (RSS/iCal)
    from src.adapters import silver_rss_adapter  # noqa: F401
    # Bronze tier (HTML scraping)
    from src.adapters.bronze import navarra  # noqa: F401
    from src.adapters.bronze import visitnavarra  # noqa: F401
    from src.adapters.bronze import larioja_agenda  # noqa: F401
    from src.adapters.bronze import pamplona  # noqa: F401
    from src.adapters.bronze import soledadnodeseada  # noqa: F401
    from src.adapters.bronze import vacacionesseniors  # noqa: F401
    from src.adapters.bronze import donarsangre  # noqa: F401
    from src.adapters.bronze import consaludmental  # noqa: F401
    from src.adapters.bronze import oviedo_digital  # noqa: F401
    from src.adapters.bronze import cemit_galicia  # noqa: F401
    from src.adapters.bronze import puntos_vuela  # noqa: F401
    # Bronze tier - Politica category
    from src.adapters.bronze import la_moncloa  # noqa: F401
    from src.adapters.bronze import defensor_pueblo  # noqa: F401
    from src.adapters.bronze import cnt_agenda  # noqa: F401
    from src.adapters.bronze import segib  # noqa: F401
    from src.adapters.bronze import jgpa  # noqa: F401
    from src.adapters.bronze import horizonte_europa  # noqa: F401
    # Bronze tier - Generic scraper (CLM, Asturias, La Rioja, Badajoz, etc.)
    from src.adapters import bronze_scraper_adapter  # noqa: F401
    # Bronze tier - Viralagenda (multiple CCAA)
    from src.adapters.bronze.viralagenda import base as viralagenda_base  # noqa: F401
