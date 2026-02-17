"""Analyze Eventbrite HTML structure."""
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('temp_eventbrite_readmore.html', 'r', encoding='utf-8') as f:
    html = f.read()

print('=== Buscando patrones en HTML ===')
print(f'HTML length: {len(html)}')

# Buscar Overview
if 'Overview' in html:
    print('\nTiene "Overview"')
    matches = re.findall(r'Overview[a-zA-Z_]*', html)
    unique = list(set(matches))[:10]
    print(f'  Clases: {unique}')

# Buscar data-testid
testids = re.findall(r'data-testid="([^"]+)"', html)
print(f'\ndata-testid encontrados: {len(testids)}')
unique_testids = list(set(testids))[:30]
for t in sorted(unique_testids):
    print(f'  - {t}')

# Buscar read-more
if 'read-more' in html.lower():
    print('\nTiene "read-more"!')
    idx = html.lower().find('read-more')
    print(f'  Context: ...{html[max(0,idx-50):idx+50]}...')

# Buscar Ver mas / Show more
for term in ['Ver más', 'Show more', 'Leer más', 'See more']:
    if term.lower() in html.lower():
        print(f'\nTiene "{term}"!')
        idx = html.lower().find(term.lower())
        print(f'  Context: ...{html[max(0,idx-100):idx+100]}...')

# Buscar description en JSON-LD
ld_matches = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
print(f'\nJSON-LD blocks: {len(ld_matches)}')
for i, ld in enumerate(ld_matches[:3]):
    if 'description' in ld.lower():
        # Extraer description
        desc_match = re.search(r'"description"\s*:\s*"([^"]*)"', ld)
        if desc_match:
            desc = desc_match.group(1)[:200]
            print(f'  Block {i}: {desc}')
