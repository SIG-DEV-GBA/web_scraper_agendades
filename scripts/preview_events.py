"""Preview events locally before inserting into Supabase.

Usage:
    python scripts/preview_events.py --source oviedo_digital --limit 10
    python scripts/preview_events.py --source cemit_galicia
    python scripts/preview_events.py --source puntos_vuela --limit 20

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


async def preview(source_slug: str, limit: int = 50) -> None:
    """Fetch events from a source and write to preview/events.json."""
    adapter_cls = _resolve_adapter(source_slug)
    if not adapter_cls:
        print(f"Error: adapter '{source_slug}' not found.")
        print(f"Known direct imports: {', '.join(_DIRECT_IMPORTS.keys())}")
        sys.exit(1)

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

        # Serialize to JSON
        output = {
            "source_id": source_slug,
            "source_name": adapter.source_name,
            "total_fetched": len(raw_events),
            "total_parsed": len(events),
            "errors": errors,
            "events": [],
        }

        for ev in events:
            d = ev.model_dump(mode="json")
            # Ensure organizer is serialized
            if ev.organizer:
                d["organizer"] = ev.organizer.model_dump(mode="json")
            output["events"].append(d)

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

    finally:
        await adapter.close_http_client()
        await adapter.close_browser()


def main():
    parser = argparse.ArgumentParser(description="Preview events locally")
    parser.add_argument("--source", required=True, help="Source slug (e.g., oviedo_digital)")
    parser.add_argument("--limit", type=int, default=50, help="Max events to fetch")
    args = parser.parse_args()

    asyncio.run(preview(args.source, args.limit))


if __name__ == "__main__":
    main()
