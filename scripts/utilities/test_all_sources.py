#!/usr/bin/env python3
"""Test all sources - insert 10 events from each."""
import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.adapters.gold_api_adapter import GoldAPIAdapter, GOLD_SOURCES
from src.adapters.bronze_scraper_adapter import BronzeScraperAdapter
from src.core.llm_enricher import get_llm_enricher, SourceTier
from src.core.supabase_client import SupabaseClient

LIMIT = 10


async def test_gold_sources(db: SupabaseClient, enricher):
    """Test Gold API sources."""
    print("\n" + "=" * 70)
    print("GOLD SOURCES (API)")
    print("=" * 70)

    results = {}
    for source_id in ["catalunya_agenda", "euskadi_kulturklik", "castilla_leon_agenda", "andalucia_agenda", "madrid_datos_abiertos"]:
        print(f"\n  [{source_id}]")
        try:
            adapter = GoldAPIAdapter(source_id)
            all_events = await adapter.fetch_events(max_pages=1)  # Just 1 page for speed
            events = all_events[:LIMIT]  # Limit to 10
            print(f"    Fetched: {len(events)}")

            if events and enricher.is_enabled:
                # Enrich
                events_for_llm = [
                    {
                        "id": e.external_id,
                        "title": e.title,
                        "description": e.description or "",
                        "@type": "",
                        "audience": "",
                        "price_info": e.price_info or "",
                    }
                    for e in events[:LIMIT]
                ]
                enrichments = enricher.enrich_batch(events_for_llm, batch_size=10, tier=SourceTier.ORO)

                for event in events[:LIMIT]:
                    enr = enrichments.get(event.external_id)
                    if enr:
                        event.category_slugs = enr.category_slugs
                        if enr.summary:
                            event.summary = enr.summary
                        if enr.price is not None:
                            event.price = enr.price
                        if enr.price_details:
                            event.price_info = enr.price_details
                        else:
                            event.price_info = None

                    # If no price_info but registration_url exists
                    if not event.price_info and event.registration_url:
                        event.price_info = event.registration_url

            # Insert
            inserted = 0
            for event in events[:LIMIT]:
                try:
                    result = await db.insert_event(event, generate_embedding=False)
                    if result:
                        inserted += 1
                except Exception as e:
                    pass  # Skip errors silently

            results[source_id] = {"fetched": len(events), "inserted": inserted}
            print(f"    Inserted: {inserted}")

        except Exception as e:
            results[source_id] = {"fetched": 0, "inserted": 0, "error": str(e)[:50]}
            print(f"    Error: {str(e)[:50]}")

    return results


async def test_silver_sources(db: SupabaseClient, enricher):
    """Test Silver RSS sources."""
    print("\n" + "=" * 70)
    print("SILVER SOURCES (RSS)")
    print("=" * 70)

    # For now, just show placeholder - need to implement RSS fetch
    print("\n  [galicia_cultura]")
    print("    Skipped - requires separate implementation")
    return {"galicia_cultura": {"fetched": 0, "inserted": 0, "note": "separate script"}}


async def test_bronze_sources(db: SupabaseClient, enricher):
    """Test Bronze Scraper sources."""
    print("\n" + "=" * 70)
    print("BRONZE SOURCES (Scraper)")
    print("=" * 70)

    results = {}

    print("\n  [canarias_lagenda]")
    try:
        adapter = BronzeScraperAdapter("canarias_lagenda")
        events_raw = await adapter.fetch_events(enrich=False, fetch_details=True)
        events_raw = events_raw[:LIMIT]
        print(f"    Fetched: {len(events_raw)}")

        # Enrich
        if events_raw and enricher.is_enabled:
            events_for_llm = [
                {
                    "id": e["external_id"],
                    "title": e["title"],
                    "description": e.get("description", ""),
                    "@type": e.get("category_raw", ""),
                    "audience": "",
                    "price_info": e.get("price_raw", ""),
                }
                for e in events_raw
            ]
            enrichments = enricher.enrich_batch(events_for_llm, batch_size=10, tier=SourceTier.BRONCE)

        # Build and insert
        inserted = 0
        for raw in events_raw:
            event = adapter.parse_event(raw)
            if not event:
                continue

            enrichment = enrichments.get(raw["external_id"]) if enricher.is_enabled else None
            if enrichment:
                event.summary = enrichment.summary
                event.category_slugs = enrichment.category_slugs or []
                event.is_free = enrichment.is_free
                event.price = enrichment.price
                if enrichment.price_details:
                    event.price_info = enrichment.price_details
                else:
                    event.price_info = None

            try:
                result = await db.insert_event(event, generate_embedding=False)
                if result:
                    inserted += 1
            except Exception:
                pass

        results["canarias_lagenda"] = {"fetched": len(events_raw), "inserted": inserted}
        print(f"    Inserted: {inserted}")

    except Exception as e:
        results["canarias_lagenda"] = {"fetched": 0, "inserted": 0, "error": str(e)[:50]}
        print(f"    Error: {str(e)[:50]}")

    return results


async def main():
    print("=" * 70)
    print("TEST ALL SOURCES - 10 events each")
    print("=" * 70)

    db = SupabaseClient()
    enricher = get_llm_enricher()

    print(f"\nLLM: {'Enabled' if enricher.is_enabled else 'Disabled'}")

    # Clean DB first
    print("\nCleaning existing events...")
    try:
        db.client.table("events").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        print("  Cleaned!")
    except Exception as e:
        print(f"  Clean error: {e}")

    # Test each tier
    gold_results = await test_gold_sources(db, enricher)
    silver_results = await test_silver_sources(db, enricher)
    bronze_results = await test_bronze_sources(db, enricher)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_fetched = 0
    total_inserted = 0

    print("\n  GOLD (API):")
    for source, data in gold_results.items():
        status = f"{data['inserted']}/{data['fetched']}"
        if "error" in data:
            status += f" ⚠️ {data['error'][:30]}"
        print(f"    {source}: {status}")
        total_fetched += data["fetched"]
        total_inserted += data["inserted"]

    print("\n  SILVER (RSS):")
    for source, data in silver_results.items():
        if "note" in data:
            print(f"    {source}: {data['note']}")
        else:
            print(f"    {source}: {data['inserted']}/{data['fetched']}")

    print("\n  BRONZE (Scraper):")
    for source, data in bronze_results.items():
        status = f"{data['inserted']}/{data['fetched']}"
        if "error" in data:
            status += f" ⚠️ {data['error'][:30]}"
        print(f"    {source}: {status}")
        total_fetched += data["fetched"]
        total_inserted += data["inserted"]

    print(f"\n  TOTAL: {total_inserted}/{total_fetched} events inserted")

    # Final count
    result = db.client.table("events").select("id", count="exact").execute()
    print(f"  Events in DB: {result.count}")


if __name__ == "__main__":
    asyncio.run(main())
