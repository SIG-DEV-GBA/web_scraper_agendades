#!/usr/bin/env python3
"""Find hidden API in lagenda.org."""
import sys
import re
import requests
from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

FIRECRAWL_URL = "https://firecrawl.si-erp.cloud/scrape"

# Fetch the main page and look for API endpoints in JS
print("Buscando API oculta en lagenda.org...")
print("=" * 70)

resp = requests.post(FIRECRAWL_URL, json={"url": "https://lagenda.org/programacion"}, timeout=60)
html = resp.json().get("content", "")

# Look for API endpoints in scripts
api_patterns = [
    r'api["\']?\s*[:\=]\s*["\']([^"\']+)["\']',
    r'endpoint["\']?\s*[:\=]\s*["\']([^"\']+)["\']',
    r'fetch\(["\']([^"\']+)["\']',
    r'axios\.[a-z]+\(["\']([^"\']+)["\']',
    r'/api/[a-zA-Z0-9/_-]+',
    r'/v1/[a-zA-Z0-9/_-]+',
    r'\.json["\']',
]

found_urls = set()
for pattern in api_patterns:
    matches = re.findall(pattern, html, re.IGNORECASE)
    for m in matches:
        if m and len(m) > 3:
            found_urls.add(m)

print("Posibles endpoints encontrados en JS:")
for url in sorted(found_urls)[:20]:
    print(f"  - {url}")

# The site seems to be Drupal-based (based on CSS). Try common Drupal endpoints
print("\n" + "=" * 70)
print("Probando endpoints comunes de Drupal...")
print("=" * 70)

drupal_endpoints = [
    "https://lagenda.org/api/events",
    "https://lagenda.org/jsonapi",
    "https://lagenda.org/jsonapi/node/event",
    "https://lagenda.org/rest/session/token",
    "https://lagenda.org/node/40311?_format=json",
    "https://lagenda.org/programacion/jonay-martin-tenerife-enero-2026-40311?_format=json",
]

for endpoint in drupal_endpoints:
    try:
        r = requests.get(endpoint, timeout=10, headers={"Accept": "application/json"})
        if r.status_code == 200 and len(r.text) > 10:
            print(f"✓ {endpoint}")
            print(f"  Status: {r.status_code}, Length: {len(r.text)}")
            print(f"  Preview: {r.text[:200]}...")
        else:
            print(f"✗ {endpoint} - {r.status_code}")
    except Exception as e:
        print(f"✗ {endpoint} - Error: {e}")

# Check if there are any AJAX endpoints
print("\n" + "=" * 70)
print("Buscando en el HTML por data attributes y configs...")
print("=" * 70)

soup = BeautifulSoup(html, "html.parser")

# Look for Drupal settings
scripts = soup.find_all("script")
for script in scripts:
    text = script.get_text()
    if "drupalSettings" in text or "Drupal.settings" in text:
        print("Encontrado Drupal settings!")
        # Extract relevant parts
        if "basePath" in text:
            match = re.search(r'basePath["\']?\s*[:\=]\s*["\']([^"\']+)', text)
            if match:
                print(f"  basePath: {match.group(1)}")
