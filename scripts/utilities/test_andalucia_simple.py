#!/usr/bin/env python3
"""Test simple de la API de Andalucía."""
import sys
from collections import Counter

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

URL = "https://www.juntadeandalucia.es/ssdigitales/datasets/contentapi/1.0.0/search/agenda.json"


def main():
    print("=" * 60)
    print("ANÁLISIS API ANDALUCÍA (contentapi)")
    print("=" * 60)

    # Fetch con parámetros en URL (máximo permitido parece ser 50)
    params = "_source=data&size=50&from=0&sort=date:desc"
    full_url = f"{URL}?{params}"

    print(f"\nURL: {full_url[:70]}...")

    resp = requests.get(full_url, timeout=60)
    print(f"Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"Error: {resp.text[:200]}")
        return

    data = resp.json()
    total = data.get("numResultados", 0)
    resultados = data.get("resultado", [])

    print(f"Total en API: {total}")
    print(f"Descargados: {len(resultados)}")

    # Analizar
    years = []
    provinces = []
    samples = []

    for item in resultados:
        if not isinstance(item, dict):
            continue

        source = item.get("_source", {})
        if not isinstance(source, dict):
            continue

        d = source.get("data", {})
        if not isinstance(d, dict):
            continue

        title = d.get("title", "?")

        # Fecha
        fechas = d.get("field_agenda_fechas", [])
        start_date = None
        for f in fechas:
            if isinstance(f, dict):
                start_date = f.get("field_inicio_plazo_tip")
                if start_date:
                    years.append(start_date[:4])
                    break

        # Provincia
        provs = d.get("field_provincia", [])
        prov_name = None
        for p in provs:
            if isinstance(p, dict):
                prov_name = p.get("name")
                if prov_name:
                    provinces.append(prov_name)
                    break

        if len(samples) < 5:
            samples.append((title[:45], start_date, prov_name))

    # Resultados
    print("\n" + "-" * 60)
    print("EVENTOS POR AÑO:")
    for year, count in sorted(Counter(years).items(), reverse=True):
        bar = "*" * min(count, 30)
        print(f"  {year}: {count:3} {bar}")

    print("\nPROVINCIAS:")
    for prov, count in Counter(provinces).most_common(8):
        print(f"  {prov}: {count}")

    print("\nEJEMPLOS RECIENTES:")
    for title, date, prov in samples:
        print(f"  [{date}] {title}... ({prov})")

    # Verificar eventos futuros
    future = sum(1 for y in years if y >= "2026")
    print(f"\n✓ Eventos 2026+: {future}/{len(years)}")


if __name__ == "__main__":
    main()
