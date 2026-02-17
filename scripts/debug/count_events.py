"""Count events in database."""

import sys
sys.path.insert(0, r"C:\Users\Usuario\Desktop\AGENDADES_WEB_SCRAPPER")

from src.core.supabase_client import get_supabase_client

client = get_supabase_client()

# Count total events
result = client.table('evento').select('id', count='exact').execute()
print(f"Total eventos en BD: {result.count}")

# Get distinct sources
sources = client.table('evento').select('scraper_source_id').execute()
unique_sources = set(s['scraper_source_id'] for s in sources.data if s['scraper_source_id'])
print(f"Fuentes distintas con eventos: {len(unique_sources)}")
