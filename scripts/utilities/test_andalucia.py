#!/usr/bin/env python3
"""Test Andalucía API connection."""
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

URL = "https://datos.juntadeandalucia.es/api/v0/schedule/all?format=json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def test_with_retry():
    """Test con retry automático."""
    print("\n" + "=" * 60)
    print("TEST CON RETRY Y HEADERS")
    print("=" * 60)

    session = requests.Session()

    # Configurar retry
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)

    for attempt in range(3):
        print(f"\nIntento {attempt + 1}/3...")
        try:
            start = time.time()
            resp = session.get(URL, headers=HEADERS, timeout=180)

            elapsed = time.time() - start
            print(f"  Status: {resp.status_code}")
            print(f"  Tamaño: {len(resp.content)/1024/1024:.2f} MB en {elapsed:.1f}s")

            data = resp.json()
            print(f"  ✓ JSON válido: {len(data)} eventos")

            if data:
                print(f"\n  Primer evento:")
                first = data[0]
                print(f"    id: {first.get('id')}")
                print(f"    title: {first.get('title', '')[:50]}")

            return data

        except Exception as e:
            print(f"  ✗ Error: {type(e).__name__}: {str(e)[:80]}")
            time.sleep(2)

    return None


def test_connection():
    print("=" * 60)
    print("TEST CONEXIÓN ANDALUCÍA")
    print("=" * 60)
    print(f"\nURL: {URL}")
    print("\nProbando conexión básica...")

    try:
        start = time.time()
        resp = requests.get(URL, timeout=120, stream=True)

        print(f"Status: {resp.status_code}")
        print(f"Content-Length: {resp.headers.get('Content-Length', 'N/A')}")
        print(f"Content-Type: {resp.headers.get('Content-Type', 'N/A')}")

        # Descargar en chunks
        total = 0
        chunks = 0
        for chunk in resp.iter_content(chunk_size=8192):
            total += len(chunk)
            chunks += 1
            if chunks % 100 == 0:
                elapsed = time.time() - start
                speed = total / elapsed / 1024
                print(f"  ... {total/1024/1024:.2f} MB ({speed:.1f} KB/s)")

        elapsed = time.time() - start
        print(f"\n✓ Descarga completa: {total/1024/1024:.2f} MB en {elapsed:.1f}s")

    except requests.exceptions.ChunkedEncodingError as e:
        print(f"\n✗ ERROR ChunkedEncoding: conexión cortada")
        print("  → Probando con retry...")

    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")


def analyze_dates(data):
    """Analizar fechas de los eventos."""
    print("\n" + "=" * 60)
    print("ANÁLISIS DE FECHAS")
    print("=" * 60)

    from datetime import datetime
    from collections import Counter

    years = []
    for event in data:
        date_reg = event.get("date_registration", [])
        if date_reg and isinstance(date_reg, list):
            for dr in date_reg:
                start = dr.get("start_date_registration")
                if start:
                    try:
                        year = int(start[:4])
                        years.append(year)
                    except:
                        pass

    if years:
        counts = Counter(years)
        print("\nEventos por año:")
        for year, count in sorted(counts.items()):
            bar = "*" * min(count // 5, 40)
            print(f"  {year}: {count:4} {bar}")

        print(f"\nTotal eventos: {len(data)}")
        print(f"Con fecha: {len(years)}")
        future = sum(1 for y in years if y >= 2026)
        print(f"Futuros (2026+): {future}")
    else:
        print("No se encontraron fechas")


def test_alternative_api():
    """Probar API alternativa con parámetros."""
    print("\n" + "=" * 60)
    print("TEST API ALTERNATIVA (contentapi)")
    print("=" * 60)

    import json

    base_url = "https://www.juntadeandalucia.es/ssdigitales/datasets/contentapi/1.0.0/search/agenda.json"

    params = {"_source": "data", "size": 20, "from": 0, "sort": "date:desc"}

    print(f"\nURL: {base_url}")
    print(f"Params: {params}")

    try:
        resp = requests.get(base_url, params=params, headers=HEADERS, timeout=30)
        print(f"Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()
            print(f"Total resultados: {data.get('numResultados')}")

            resultados = data.get("resultado", [])
            print(f"Items en esta página: {len(resultados)}")

            if resultados:
                print("\nPrimeros 5 eventos:")
                print("-" * 60)
                for i, item in enumerate(resultados[:5], 1):
                    title = item.get("title", "")[:50]
                    date = item.get("date", "N/A")
                    location = item.get("location", "N/A")
                    print(f"  {i}. {title}")
                    print(f"     Fecha: {date}")
                    print(f"     Lugar: {location}")
                    print()

                # Ver estructura completa del primer evento
                print("\nEstructura primer evento:")
                first = resultados[0]
                for key in sorted(first.keys()):
                    val = first[key]
                    if isinstance(val, str) and len(val) > 60:
                        val = val[:60] + "..."
                    print(f"  {key}: {val}")

    except Exception as e:
        print(f"Error: {e}")


def test_date_filter():
    """Probar filtros de fecha en la API alternativa."""
    print("\n" + "=" * 60)
    print("TEST FILTROS DE FECHA")
    print("=" * 60)

    base_url = "https://www.juntadeandalucia.es/ssdigitales/datasets/contentapi/1.0.0/search/agenda.json"

    # Probar diferentes filtros
    filters = [
        # Intentar filtro por rango de fecha
        {"_source": "data", "size": 5, "from": 0, "q": "2026"},
        {"_source": "data", "size": 5, "from": 0, "filter": "date:[2026-01-01 TO *]"},
        {"_source": "data", "size": 5, "from": 0, "date.gte": "2026-01-01"},
    ]

    for params in filters:
        print(f"\nProbando: {params}")
        try:
            resp = requests.get(base_url, params=params, headers=HEADERS, timeout=30)
            print(f"  Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                total = data.get("numResultados", 0)
                resultados = data.get("resultado", [])
                print(f"  Total: {total}, Items: {len(resultados)}")
                if resultados:
                    first = resultados[0].get("_source", {}).get("data", {})
                    fechas = first.get("field_agenda_fechas", [])
                    if fechas:
                        print(f"  Primera fecha: {fechas[0].get('field_inicio_plazo_tip')}")
        except Exception as e:
            print(f"  Error: {e}")


def summarize_new_api():
    """Resumen de la API alternativa."""
    print("\n" + "=" * 60)
    print("RESUMEN API ALTERNATIVA")
    print("=" * 60)

    base_url = "https://www.juntadeandalucia.es/ssdigitales/datasets/contentapi/1.0.0/search/agenda.json"
    params = {"_source": "data", "size": 100, "from": 0, "sort": "date:desc"}

    resp = requests.get(base_url, params=params, headers=HEADERS, timeout=30)
    data = resp.json()

    total = data.get("numResultados", 0)
    resultados = data.get("resultado", [])

    print(f"\nTotal eventos: {total}")
    print(f"Descargados: {len(resultados)}")

    # Debug estructura
    if resultados:
        print(f"\nTipo primer resultado: {type(resultados[0])}")
        if isinstance(resultados[0], dict):
            print(f"Keys: {list(resultados[0].keys())[:10]}")

    # Analizar fechas
    from collections import Counter
    years = []
    for item in resultados:
        if not isinstance(item, dict):
            continue
        source = item.get("_source", {})
        if isinstance(source, dict):
            data_field = source.get("data", {})
            if isinstance(data_field, dict):
                fechas = data_field.get("field_agenda_fechas", [])
                for f in fechas:
                    if isinstance(f, dict):
                        start = f.get("field_inicio_plazo_tip", "")
                        if start:
                            years.append(start[:4])

    if years:
        counts = Counter(years)
        print("\nEventos por año (últimos 100):")
        for year, count in sorted(counts.items(), reverse=True):
            print(f"  {year}: {count}")


def test_working_api():
    """Probar con los parámetros que funcionaron antes."""
    print("\n" + "=" * 60)
    print("TEST API - CONFIGURACIÓN ORIGINAL")
    print("=" * 60)

    import json

    # URL exacta que funcionó en el primer test
    url = "https://www.juntadeandalucia.es/ssdigitales/datasets/contentapi/1.0.0/search/agenda.json?_source=data&size=10&from=0&sort=date:desc"

    print(f"URL: {url}")

    resp = requests.get(url, headers=HEADERS, timeout=30)
    print(f"Status: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        print(f"numResultados: {data.get('numResultados')}")

        resultados = data.get("resultado", [])
        print(f"Items: {len(resultados)}")

        if resultados:
            print(f"\nTipo item: {type(resultados[0])}")

            # Mostrar primer item completo
            print(f"\nPrimer item (raw):")
            print(json.dumps(resultados[0], indent=2, ensure_ascii=False, default=str)[:2000])


def analyze_events():
    """Analizar eventos de la nueva API."""
    print("\n" + "=" * 60)
    print("ANÁLISIS EVENTOS ANDALUCÍA (API Nueva)")
    print("=" * 60)

    from collections import Counter

    url = "https://www.juntadeandalucia.es/ssdigitales/datasets/contentapi/1.0.0/search/agenda.json?_source=data&size=100&from=0&sort=date:desc"

    resp = requests.get(url, headers=HEADERS, timeout=30)
    data = resp.json()

    print(f"Total: {data.get('numResultados')}")

    resultados = data.get("resultado", [])
    print(f"Descargados: {len(resultados)}")

    years = []
    provinces = []
    sample_events = []

    for item in resultados:
        source = item.get("_source", {}).get("data", {})

        # Título
        title = source.get("title", "Sin título")

        # Fechas
        fechas = source.get("field_agenda_fechas", [])
        start_date = None
        for f in fechas:
            if isinstance(f, dict):
                start_date = f.get("field_inicio_plazo_tip")
                if start_date:
                    years.append(start_date[:4])
                    break

        # Provincia
        provs = source.get("field_provincia", [])
        for p in provs:
            if isinstance(p, dict):
                prov_name = p.get("name")
                if prov_name:
                    provinces.append(prov_name)

        # Sample
        if len(sample_events) < 5:
            sample_events.append({
                "title": title[:50],
                "date": start_date,
                "province": provinces[-1] if provinces else "N/A"
            })

    # Estadísticas
    print("\nEventos por año (top 100):")
    for year, count in sorted(Counter(years).items(), reverse=True):
        bar = "*" * min(count, 30)
        print(f"  {year}: {count:3} {bar}")

    print("\nProvincias:")
    for prov, count in Counter(provinces).most_common(8):
        print(f"  {prov}: {count}")

    print("\nEjemplos eventos recientes:")
    for e in sample_events:
        print(f"  - {e['title']}...")
        print(f"    {e['date']} | {e['province']}")


if __name__ == "__main__":
    analyze_events()
