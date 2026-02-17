"""Check what description comes from Eventbrite."""
import requests
import json
import re

url = 'https://firecrawl.si-erp.cloud/scrape'
payload = {
    'url': 'https://www.eventbrite.es/e/entradas-cine-ciclo-cine-familiar-febrero-1236782414219',
    'formats': ['html'],
    'waitFor': 5000,
    'timeout': 30000,
}

resp = requests.post(url, json=payload, timeout=60)
html = resp.json().get('content', '')

print(f"HTML length: {len(html)}")

# Buscar JSON-LD (escapado diferente?)
matches1 = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
matches2 = re.findall(r"<script type='application/ld\+json'[^>]*>(.*?)</script>", html, re.DOTALL)
matches3 = re.findall(r'type=.application/ld.json', html)
print(f"JSON-LD regex1: {len(matches1)}, regex2: {len(matches2)}, any ld+json: {len(matches3)}")

# Buscar description en el HTML directamente
# Eventbrite pone la descripcion en un div con class="eds-text--left"
desc_match = re.search(r'structured-content[^>]*>(.*?)</div>', html, re.DOTALL)
if desc_match:
    print(f"\nstructured-content: {desc_match.group(1)[:300]}")

# Buscar meta description
meta_match = re.search(r'<meta name="description" content="([^"]*)"', html)
if meta_match:
    print(f"\nmeta description: {meta_match.group(1)[:300]}")

# Buscar og:description
og_match = re.search(r'<meta property="og:description" content="([^"]*)"', html)
if og_match:
    print(f"\nog:description: {og_match.group(1)[:300]}")

# Guardar HTML para inspeccionar
with open('temp_eventbrite_detail.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("\nHTML saved to temp_eventbrite_detail.html")
