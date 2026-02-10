#!/usr/bin/env python3
"""Check prices on lagenda.org vs what we detect."""
import sys
import requests
from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Fetch listing page
url = 'https://firecrawl.si-erp.cloud/scrape'
resp = requests.post(url, json={'url': 'https://lagenda.org/programacion'}, timeout=60)
html = resp.json().get('content', '')

soup = BeautifulSoup(html, 'html.parser')
cards = soup.select('.small-post')[:15]

print('EVENTOS EN LAGENDA.ORG - Info de precios visible:')
print('=' * 70)

for i, card in enumerate(cards, 1):
    title = card.select_one('h4.title a')
    title_text = title.get_text(strip=True) if title else 'N/A'

    # Get all text from card
    card_text = card.get_text(separator=' ', strip=True)

    # Check for price patterns
    has_euro = '€' in card_text or 'euro' in card_text.lower()
    has_gratis = 'gratis' in card_text.lower() or 'gratuito' in card_text.lower() or 'libre' in card_text.lower()

    print(f'[{i}] {title_text[:55]}')
    print(f'    € visible: {has_euro} | Gratis visible: {has_gratis}')

print('\n' + '=' * 70)
print('CONCLUSIÓN: La página de listado NO muestra precios.')
print('Los precios solo están en las páginas de detalle (que no podemos scrapear).')
print('El LLM infiere precios basándose en el tipo de evento.')
