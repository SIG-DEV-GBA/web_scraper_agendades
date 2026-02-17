"""Test Firecrawl with longer wait time."""
import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://firecrawl.si-erp.cloud/scrape'
payload = {
    'url': 'https://www.eventbrite.es/e/entradas-cine-ciclo-cine-familiar-febrero-1236782414219',
    'formats': ['html'],
    'waitFor': 15000,  # 15 segundos
    'timeout': 120000,  # 2 minutos
}

print('Fetching with 15s wait...')
resp = requests.post(url, json=payload, timeout=180)
data = resp.json()

print(f'Status: {resp.status_code}')
if 'error' in data:
    print(f'Error: {data["error"]}')
elif 'content' in data:
    html = data['content']
    print(f'HTML length: {len(html)}')

    # Buscar titulo del evento
    title = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
    if title:
        print(f'Title: {title.group(1)[:100]}')

    # Buscar JSON-LD
    ld_matches = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    print(f'\nJSON-LD blocks: {len(ld_matches)}')

    # Buscar og:description
    og_desc = re.search(r'<meta property="og:description" content="([^"]*)"', html)
    if og_desc:
        print(f'\nog:description: {og_desc.group(1)[:300]}')

    # Buscar meta description
    meta_desc = re.search(r'<meta name="description" content="([^"]*)"', html)
    if meta_desc:
        print(f'\nmeta description: {meta_desc.group(1)[:300]}')

    # Guardar HTML
    with open('temp_eventbrite_long.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('\nHTML saved to temp_eventbrite_long.html')
else:
    print(f'Response: {data}')
