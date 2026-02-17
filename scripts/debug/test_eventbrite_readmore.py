"""Test Firecrawl with click action for 'Read more' button."""
import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

url = 'https://firecrawl.si-erp.cloud/scrape'
payload = {
    'url': 'https://www.eventbrite.es/e/entradas-cine-ciclo-cine-familiar-febrero-1236782414219',
    'formats': ['html'],
    'waitFor': 5000,
    'timeout': 60000,
    'actions': [
        # Intentar clicar el boton Read more / Ver mas
        {'type': 'click', 'selector': '[data-testid="read-more-button"]'},
        {'type': 'wait', 'milliseconds': 2000}
    ]
}

resp = requests.post(url, json=payload, timeout=120)
data = resp.json()

print(f'Status: {resp.status_code}')
if 'error' in data:
    print(f'Error: {data["error"]}')
elif 'content' in data:
    html = data['content']
    print(f'HTML length: {len(html)}')

    # Buscar clases de descripcion expandida
    if 'Overview_summary' in html:
        print('Tiene Overview_summary!')
        # Extraer contenido
        match = re.search(r'class="Overview_summary[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if match:
            print(f'Content: {match.group(1)[:500]}')

    if 'structuredContent' in html:
        print('\nTiene structuredContent!')

    # Buscar JSON-LD description
    ld_match = re.search(r'"description":"([^"]+)"', html)
    if ld_match:
        print(f'\nJSON-LD description: {ld_match.group(1)[:200]}')

    # Guardar HTML
    with open('temp_eventbrite_readmore.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('\nHTML saved to temp_eventbrite_readmore.html')
else:
    print(f'Response: {data}')
