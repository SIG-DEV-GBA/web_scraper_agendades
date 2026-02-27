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
        # ---- PRINCIPADO DE ASTURIAS ----
        {
            "slug": "oviedo_digital",
            "name": "Oviedo - Centros Sociales",
            "source_url": "https://centrosocialvirtualoviedo.es/actividades",
            "adapter_type": "scraper",
            "ccaa": "Principado de Asturias",
            "ccaa_code": "AS",
            "is_active": True,
            "rate_limit_delay": 2.0,
            "batch_size": 50
        },
        # ---- GALICIA ----
        {
            "slug": "cemit_galicia",
            "name": "CeMIT Galicia - Formación Presencial",
            "source_url": "https://cemit.xunta.gal/es/formacion/formacion-presencial",
            "adapter_type": "scraper",
            "ccaa": "Galicia",
            "ccaa_code": "GA",
            "is_active": True,
            "rate_limit_delay": 1.0,
            "batch_size": 50
        },
        # ---- ANDALUCÍA ----
        {
            "slug": "puntos_vuela",
            "name": "Puntos Vuela (Guadalinfo) - Actividades",
            "source_url": "https://puntosvuela.es/actividades",
            "adapter_type": "scraper",
            "ccaa": "Andalucía",
            "ccaa_code": "AN",
            "is_active": True,
            "rate_limit_delay": 2.0,
            "batch_size": 50
        },
        # ---- POLÍTICA ----
        {
            "slug": "la_moncloa",
            "name": "Agenda del Gobierno de España - La Moncloa",
            "source_url": "https://www.lamoncloa.gob.es/gobierno/agenda/Paginas/agenda.aspx",
            "adapter_type": "scraper",
            "ccaa": "Comunidad de Madrid",
            "ccaa_code": "MD",
            "is_active": True,
            "rate_limit_delay": 1.0,
            "batch_size": 50
        },
        {
            "slug": "defensor_pueblo",
            "name": "Defensor del Pueblo - Calendario de Actividades",
            "source_url": "https://www.defensordelpueblo.es/agenda-institucional/",
            "adapter_type": "scraper",
            "ccaa": "Comunidad de Madrid",
            "ccaa_code": "MD",
            "is_active": True,
            "rate_limit_delay": 1.0,
            "batch_size": 50
        },
        {
            "slug": "cnt_agenda",
            "name": "CNT - Confederación Nacional del Trabajo",
            "source_url": "https://cnt.es/noticias/category/noticias/agenda/",
            "adapter_type": "scraper",
            "ccaa": "",
            "ccaa_code": "",
            "is_active": True,
            "rate_limit_delay": 1.0,
            "batch_size": 50
        },
        {
            "slug": "segib",
            "name": "SEGIB - Secretaría General Iberoamericana",
            "source_url": "https://www.segib.org/sala-de-prensa/",
            "adapter_type": "scraper",
            "ccaa": "",
            "ccaa_code": "",
            "is_active": True,
            "rate_limit_delay": 1.0,
            "batch_size": 50
        },
        {
            "slug": "jgpa",
            "name": "Junta General del Principado de Asturias",
            "source_url": "https://www.jgpa.es/calendario-de-actividades",
            "adapter_type": "scraper",
            "ccaa": "Principado de Asturias",
            "ccaa_code": "AS",
            "is_active": True,
            "rate_limit_delay": 1.0,
            "batch_size": 50
        },
        {
            "slug": "horizonte_europa",
            "name": "Horizonte Europa - Programa europeo de I+D+i",
            "source_url": "https://horizonteeuropa.es/eventos",
            "adapter_type": "scraper",
            "ccaa": "",
            "ccaa_code": "",
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
