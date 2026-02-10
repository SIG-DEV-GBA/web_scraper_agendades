#!/usr/bin/env python3
"""Test scraping detail page from lagenda.org."""
import sys
import requests
from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

FIRECRAWL_URL = "https://firecrawl.si-erp.cloud/scrape"
DETAIL_URL = "https://lagenda.org/programacion/jonay-martin-tenerife-enero-2026-40311"

print(f"Fetching: {DETAIL_URL}")
print("=" * 70)

resp = requests.post(FIRECRAWL_URL, json={
    "url": DETAIL_URL,
    "waitFor": 5000,  # Wait 5 seconds for JS
}, timeout=90)

data = resp.json()
content = data.get("content", "")

print(f"Content length: {len(content)} bytes")
print(f"Page status: {data.get('pageStatusCode')}")

soup = BeautifulSoup(content, "html.parser")

# Page title
title = soup.find("title")
print(f"\nPage title: {title.get_text() if title else 'N/A'}")

# Look for event-specific content
print("\n" + "=" * 70)
print("BUSCANDO CONTENIDO DEL EVENTO:")
print("=" * 70)

# Try various selectors that might have event info
selectors_to_try = [
    ("h1", "Título H1"),
    ("h2", "Título H2"),
    (".event-title", "Título evento"),
    (".node-title", "Node title"),
    (".field-name-body", "Body field"),
    (".field-name-field-descripcion", "Descripción"),
    (".event-description", "Event description"),
    (".content", "Content div"),
    ("article", "Article"),
    (".precio, .price, .field-name-field-precio", "Precio"),
    (".lugar, .location, .field-name-field-lugar", "Lugar"),
    (".fecha, .date, .field-name-field-fecha", "Fecha"),
]

for selector, name in selectors_to_try:
    elem = soup.select_one(selector)
    if elem:
        text = elem.get_text(strip=True)[:150]
        print(f"\n✓ {name} ({selector}):")
        print(f"  {text}")

# Search for price keywords in full text
print("\n" + "=" * 70)
print("BÚSQUEDA DE PALABRAS CLAVE:")
print("=" * 70)

full_text = soup.get_text()
keywords = ["€", "euro", "precio", "entrada", "gratis", "gratuito", "libre"]

for kw in keywords:
    if kw.lower() in full_text.lower():
        # Find context around keyword
        idx = full_text.lower().find(kw.lower())
        context = full_text[max(0, idx-30):idx+50].replace("\n", " ").strip()
        print(f"✓ '{kw}' encontrado: ...{context}...")

# Save HTML for manual inspection
with open("detail_page.html", "w", encoding="utf-8") as f:
    f.write(content)
print("\n\nHTML guardado en detail_page.html para inspección manual")
