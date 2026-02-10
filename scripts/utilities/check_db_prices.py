#!/usr/bin/env python3
"""Check prices in database for Canarias events."""
import sys
from src.config.settings import get_settings
from supabase import create_client

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

settings = get_settings()
client = create_client(settings.supabase_url, settings.supabase_service_role_key)

# Get Canarias events
result = client.table('events').select('title, is_free, price, price_info').eq('source_id', 'canarias_lagenda').limit(20).execute()

print('EVENTOS CANARIAS EN BD - Precios:')
print('=' * 80)

for e in result.data:
    title = e['title'][:40] if e['title'] else 'N/A'
    is_free = e['is_free']
    price = e['price']
    price_info = (e['price_info'] or '')[:35]

    status = "GRATIS" if is_free == True else ("PAGO" if is_free == False else "???")
    print(f'{title:40} | {status:6} | {price or "-":>5} | {price_info}')

# Summary
free = sum(1 for e in result.data if e['is_free'] == True)
paid = sum(1 for e in result.data if e['is_free'] == False)
unknown = sum(1 for e in result.data if e['is_free'] is None)

print()
print('=' * 80)
print(f'RESUMEN: Gratuitos={free}, De pago={paid}, Desconocido={unknown}')
