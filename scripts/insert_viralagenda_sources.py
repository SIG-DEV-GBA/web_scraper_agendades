"""Insert all 49 viralagenda sources into scraper_sources table."""
import sys
sys.path.insert(0, ".")

from src.config import get_settings

settings = get_settings()
from supabase import create_client
client = create_client(settings.supabase_url, settings.supabase_service_role_key)

# Datos de las 49 fuentes viralagenda
sources = [
    # Castilla y León (9)
    ("viralagenda_avila", "Viral Agenda - Ávila", "https://www.viralagenda.com/es/castilla-y-leon/avila", "Castilla y León", "CL"),
    ("viralagenda_burgos", "Viral Agenda - Burgos", "https://www.viralagenda.com/es/castilla-y-leon/burgos", "Castilla y León", "CL"),
    ("viralagenda_leon", "Viral Agenda - León", "https://www.viralagenda.com/es/castilla-y-leon/leon", "Castilla y León", "CL"),
    ("viralagenda_palencia", "Viral Agenda - Palencia", "https://www.viralagenda.com/es/castilla-y-leon/palencia", "Castilla y León", "CL"),
    ("viralagenda_salamanca", "Viral Agenda - Salamanca", "https://www.viralagenda.com/es/castilla-y-leon/salamanca", "Castilla y León", "CL"),
    ("viralagenda_segovia", "Viral Agenda - Segovia", "https://www.viralagenda.com/es/castilla-y-leon/segovia", "Castilla y León", "CL"),
    ("viralagenda_soria", "Viral Agenda - Soria", "https://www.viralagenda.com/es/castilla-y-leon/soria", "Castilla y León", "CL"),
    ("viralagenda_valladolid", "Viral Agenda - Valladolid", "https://www.viralagenda.com/es/castilla-y-leon/valladolid", "Castilla y León", "CL"),
    ("viralagenda_zamora", "Viral Agenda - Zamora", "https://www.viralagenda.com/es/castilla-y-leon/zamora", "Castilla y León", "CL"),
    # Andalucía (8)
    ("viralagenda_almeria", "Viral Agenda - Almería", "https://www.viralagenda.com/es/andalucia/almeria", "Andalucía", "AN"),
    ("viralagenda_cadiz", "Viral Agenda - Cádiz", "https://www.viralagenda.com/es/andalucia/cadiz", "Andalucía", "AN"),
    ("viralagenda_cordoba", "Viral Agenda - Córdoba", "https://www.viralagenda.com/es/andalucia/cordoba", "Andalucía", "AN"),
    ("viralagenda_granada", "Viral Agenda - Granada", "https://www.viralagenda.com/es/andalucia/granada", "Andalucía", "AN"),
    ("viralagenda_huelva", "Viral Agenda - Huelva", "https://www.viralagenda.com/es/andalucia/huelva", "Andalucía", "AN"),
    ("viralagenda_jaen", "Viral Agenda - Jaén", "https://www.viralagenda.com/es/andalucia/jaen", "Andalucía", "AN"),
    ("viralagenda_malaga", "Viral Agenda - Málaga", "https://www.viralagenda.com/es/andalucia/malaga", "Andalucía", "AN"),
    ("viralagenda_sevilla", "Viral Agenda - Sevilla", "https://www.viralagenda.com/es/andalucia/sevilla", "Andalucía", "AN"),
    # Galicia (4)
    ("viralagenda_a_coruna", "Viral Agenda - A Coruña", "https://www.viralagenda.com/es/galicia/a-coruna", "Galicia", "GA"),
    ("viralagenda_lugo", "Viral Agenda - Lugo", "https://www.viralagenda.com/es/galicia/lugo", "Galicia", "GA"),
    ("viralagenda_ourense", "Viral Agenda - Ourense", "https://www.viralagenda.com/es/galicia/ourense", "Galicia", "GA"),
    ("viralagenda_pontevedra", "Viral Agenda - Pontevedra", "https://www.viralagenda.com/es/galicia/pontevedra", "Galicia", "GA"),
    # CLM (5)
    ("viralagenda_albacete", "Viral Agenda - Albacete", "https://www.viralagenda.com/es/castilla-la-mancha/albacete", "Castilla-La Mancha", "CM"),
    ("viralagenda_ciudad_real", "Viral Agenda - Ciudad Real", "https://www.viralagenda.com/es/castilla-la-mancha/ciudad-real", "Castilla-La Mancha", "CM"),
    ("viralagenda_cuenca", "Viral Agenda - Cuenca", "https://www.viralagenda.com/es/castilla-la-mancha/cuenca", "Castilla-La Mancha", "CM"),
    ("viralagenda_guadalajara", "Viral Agenda - Guadalajara", "https://www.viralagenda.com/es/castilla-la-mancha/guadalajara", "Castilla-La Mancha", "CM"),
    ("viralagenda_toledo", "Viral Agenda - Toledo", "https://www.viralagenda.com/es/castilla-la-mancha/toledo", "Castilla-La Mancha", "CM"),
    # Extremadura (2)
    ("viralagenda_caceres", "Viral Agenda - Cáceres", "https://www.viralagenda.com/es/extremadura/caceres/caceres", "Extremadura", "EX"),
    ("viralagenda_badajoz", "Viral Agenda - Badajoz", "https://www.viralagenda.com/es/extremadura/badajoz", "Extremadura", "EX"),
    # Canarias (2)
    ("viralagenda_las_palmas", "Viral Agenda - Las Palmas", "https://www.viralagenda.com/es/canarias/las-palmas", "Canarias", "CN"),
    ("viralagenda_santa_cruz_tenerife", "Viral Agenda - Santa Cruz de Tenerife", "https://www.viralagenda.com/es/canarias/santa-cruz-de-tenerife", "Canarias", "CN"),
    # Uniprovinciales
    ("viralagenda_asturias", "Viral Agenda - Asturias", "https://www.viralagenda.com/es/asturias", "Asturias", "AS"),
    ("viralagenda_cantabria", "Viral Agenda - Cantabria", "https://www.viralagenda.com/es/cantabria", "Cantabria", "CB"),
    ("viralagenda_murcia", "Viral Agenda - Murcia", "https://www.viralagenda.com/es/murcia", "Región de Murcia", "MC"),
    ("viralagenda_navarra", "Viral Agenda - Navarra", "https://www.viralagenda.com/es/navarra", "Navarra", "NC"),
    ("viralagenda_la_rioja", "Viral Agenda - La Rioja", "https://www.viralagenda.com/es/la-rioja", "La Rioja", "RI"),
    ("viralagenda_baleares", "Viral Agenda - Illes Balears", "https://www.viralagenda.com/es/illes-balears", "Illes Balears", "IB"),
    ("viralagenda_madrid", "Viral Agenda - Madrid", "https://www.viralagenda.com/es/madrid", "Comunidad de Madrid", "MD"),
    # País Vasco (3)
    ("viralagenda_araba", "Viral Agenda - Araba/Álava", "https://www.viralagenda.com/es/pais-vasco/araba-alava", "País Vasco", "PV"),
    ("viralagenda_bizkaia", "Viral Agenda - Bizkaia", "https://www.viralagenda.com/es/pais-vasco/bizkaia", "País Vasco", "PV"),
    ("viralagenda_gipuzkoa", "Viral Agenda - Gipuzkoa", "https://www.viralagenda.com/es/pais-vasco/gipuzkoa", "País Vasco", "PV"),
    # Aragón (3)
    ("viralagenda_huesca", "Viral Agenda - Huesca", "https://www.viralagenda.com/es/aragon/huesca", "Aragón", "AR"),
    ("viralagenda_teruel", "Viral Agenda - Teruel", "https://www.viralagenda.com/es/aragon/teruel", "Aragón", "AR"),
    ("viralagenda_zaragoza", "Viral Agenda - Zaragoza", "https://www.viralagenda.com/es/aragon/zaragoza", "Aragón", "AR"),
    # Valencia (3)
    ("viralagenda_alicante", "Viral Agenda - Alicante", "https://www.viralagenda.com/es/comunitat-valenciana/alicante", "Comunitat Valenciana", "VC"),
    ("viralagenda_castellon", "Viral Agenda - Castellón", "https://www.viralagenda.com/es/comunitat-valenciana/castellon", "Comunitat Valenciana", "VC"),
    ("viralagenda_valencia", "Viral Agenda - Valencia", "https://www.viralagenda.com/es/comunitat-valenciana/valencia", "Comunitat Valenciana", "VC"),
    # Cataluña (4)
    ("viralagenda_barcelona", "Viral Agenda - Barcelona", "https://www.viralagenda.com/es/cataluna/barcelona", "Cataluña", "CT"),
    ("viralagenda_girona", "Viral Agenda - Girona", "https://www.viralagenda.com/es/cataluna/girona", "Cataluña", "CT"),
    ("viralagenda_lleida", "Viral Agenda - Lleida", "https://www.viralagenda.com/es/cataluna/lleida", "Cataluña", "CT"),
    ("viralagenda_tarragona", "Viral Agenda - Tarragona", "https://www.viralagenda.com/es/cataluna/tarragona", "Cataluña", "CT"),
]


def main():
    inserted = 0
    for slug, name, url, ccaa, ccaa_code in sources:
        data = {
            "slug": slug,
            "name": name,
            "source_url": url,
            "adapter_type": "scraper",
            "ccaa": ccaa,
            "ccaa_code": ccaa_code,
            "is_active": True,
            "rate_limit_delay": 2.0,
            "batch_size": 50,
        }
        try:
            result = client.table("scraper_sources").upsert(data, on_conflict="slug").execute()
            if result.data:
                inserted += 1
        except Exception as e:
            print(f"Error {slug}: {e}")

    print(f"Insertadas/actualizadas: {inserted} fuentes viralagenda")

    # Verificar
    count = client.table("scraper_sources").select("slug").like("slug", "viralagenda_%").execute()
    print(f"Total en DB: {len(count.data)} fuentes viralagenda")


if __name__ == "__main__":
    main()
