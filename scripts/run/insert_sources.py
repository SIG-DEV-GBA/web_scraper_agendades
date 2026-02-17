#!/usr/bin/env python3
"""Insert Bronze sources to scraper_sources table."""
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from src.core.supabase_client import SupabaseClient

def main():
    client = SupabaseClient()

    sources = [
        # ---- CANARIAS ----
        {
            "slug": "canarias_lagenda",
            "name": "La Agenda de Tenerife - lagenda.org",
            "source_url": "https://lagenda.org/programacion",
            "adapter_type": "scraper",
            "ccaa": "Canarias",
            "ccaa_code": "CN",
            "is_active": True,
            "rate_limit_delay": 2.0,
            "batch_size": 50
        },
        {
            "slug": "canarias_grancanaria",
            "name": "Cultura Gran Canaria - Cabildo",
            "source_url": "https://cultura.grancanaria.com/agenda/",
            "adapter_type": "scraper",
            "ccaa": "Canarias",
            "ccaa_code": "CN",
            "is_active": True,
            "rate_limit_delay": 2.0,
            "batch_size": 50
        },
        # ---- CASTILLA-LA MANCHA ----
        {
            "slug": "clm_agenda",
            "name": "Agenda Cultural de Castilla-La Mancha",
            "source_url": "https://agendacultural.castillalamancha.es",
            "adapter_type": "scraper",
            "ccaa": "Castilla-La Mancha",
            "ccaa_code": "CM",
            "is_active": True,
            "rate_limit_delay": 1.0,
            "batch_size": 50
        },
    ]

    for source in sources:
        try:
            result = client.client.table("scraper_sources").upsert(
                source, on_conflict="slug"
            ).execute()
            print(f"Inserted: {source['slug']}")
        except Exception as e:
            print(f"Error {source['slug']}: {e}")

    # Verify
    result = client.client.table("scraper_sources").select(
        "slug,name,ccaa,adapter_type"
    ).in_("adapter_type", ["scraper"]).execute()

    print("\nBronze (scraper) sources in DB:")
    for s in result.data:
        print(f"  - [{s['ccaa']}] {s['slug']}: {s['name']}")


if __name__ == "__main__":
    main()
