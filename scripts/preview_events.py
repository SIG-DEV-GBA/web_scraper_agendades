"""Preview events locally before inserting into Supabase.

Usage:
    python scripts/preview_events.py --source oviedo_digital --limit 10
    python scripts/preview_events.py --source cemit_galicia
    python scripts/preview_events.py --source puntos_vuela --limit 20
    python scripts/preview_events.py --source nferias,tourdelempleo --limit 10

Supports comma-separated sources to preview multiple at once.
Generates preview/events.json and opens the browser.
"""

import argparse
import asyncio
import json
import sys
import webbrowser
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


_DIRECT_IMPORTS = {
    "oviedo_digital": "src.adapters.bronze.oviedo_digital:OviedoDigitalAdapter",
    "cemit_galicia": "src.adapters.bronze.cemit_galicia:CemitGaliciaAdapter",
    "puntos_vuela": "src.adapters.bronze.puntos_vuela:PuntosVuelaAdapter",
}


def _resolve_adapter(source_slug: str):
    """Resolve adapter class, trying direct import first to avoid missing deps."""
    # Try direct import (avoids loading unrelated adapters with missing deps)
    if source_slug in _DIRECT_IMPORTS:
        module_path, class_name = _DIRECT_IMPORTS[source_slug].rsplit(":", 1)
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)

    # Fall back to full registry
    from src.adapters import get_adapter
    return get_adapter(source_slug)


async def _fetch_source(source_slug: str, limit: int) -> dict:
    """Fetch events from a single source and return serialized output."""
    adapter_cls = _resolve_adapter(source_slug)
    if not adapter_cls:
        print(f"  Error: adapter '{source_slug}' not found.")
        return {"source_id": source_slug, "error": "adapter not found", "events": []}

    print(f"Fetching events from '{source_slug}' (limit={limit})...")
    adapter = adapter_cls()

    try:
        raw_events = await adapter.fetch_events(enrich=False, limit=limit)
        print(f"  Fetched {len(raw_events)} raw events")

        events = []
        errors = []
        for i, raw in enumerate(raw_events[:limit]):
            try:
                event = adapter.parse_event(raw)
                if event:
                    if not event.external_id:
                        event.external_id = event.generate_external_id(source_slug)
                    events.append(event)
            except Exception as e:
                errors.append(f"Event {i}: {e}")

        print(f"  Parsed {len(events)} events ({len(errors)} errors)")

        serialized = []
        for ev in events:
            d = ev.model_dump(mode="json")
            if ev.organizer:
                d["organizer"] = ev.organizer.model_dump(mode="json")
            serialized.append(d)

        return {
            "source_id": source_slug,
            "source_name": adapter.source_name,
            "total_fetched": len(raw_events),
            "total_parsed": len(events),
            "errors": errors,
            "events": serialized,
        }

    finally:
        await adapter.close_http_client()
        await adapter.close_browser()


async def preview(source_slugs: str, limit: int = 50) -> None:
    """Fetch events from one or more sources and write to preview/events.json."""
    slugs = [s.strip() for s in source_slugs.split(",") if s.strip()]

    if len(slugs) == 1:
        # Single source — original format
        output = await _fetch_source(slugs[0], limit)
    else:
        # Multiple sources — merged output
        all_events = []
        sources_summary = []
        for slug in slugs:
            result = await _fetch_source(slug, limit)
            all_events.extend(result.get("events", []))
            sources_summary.append({
                "source_id": result.get("source_id"),
                "source_name": result.get("source_name", ""),
                "count": len(result.get("events", [])),
            })

        output = {
            "source_id": ",".join(slugs),
            "source_name": f"{len(slugs)} sources combined",
            "sources": sources_summary,
            "total_fetched": sum(s["count"] for s in sources_summary),
            "total_parsed": len(all_events),
            "errors": [],
            "events": all_events,
        }
        print(f"\nCombined: {len(all_events)} events from {len(slugs)} sources")

    outpath = PROJECT_ROOT / "preview" / "events.json"
    outpath.parent.mkdir(exist_ok=True)
    outpath.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"  Written to {outpath}")

    # Open browser
    html_path = PROJECT_ROOT / "preview" / "index.html"
    if html_path.exists():
        webbrowser.open(html_path.as_uri())
        print("  Browser opened. Use Live Server for auto-reload.")
    else:
        print(f"  Preview HTML not found at {html_path}")


def main():
    parser = argparse.ArgumentParser(description="Preview events locally")
    parser.add_argument("--source", required=True, help="Source slug (e.g., oviedo_digital)")
    parser.add_argument("--limit", type=int, default=50, help="Max events to fetch")
    args = parser.parse_args()

    asyncio.run(preview(args.source, args.limit))


if __name__ == "__main__":
    main()
