-- Insert Teruel Ayuntamiento source
INSERT INTO scraper_sources (
    slug,
    name,
    tier,
    ccaa,
    ccaa_code,
    province,
    url,
    feed_type,
    is_active,
    notes
) VALUES (
    'teruel_ayuntamiento',
    'Agenda Cultural Ayuntamiento de Teruel',
    'bronce',
    'Aragón',
    'AR',
    'Teruel',
    'https://www.teruel.es/eventos/feed/',
    'rss_firecrawl',
    true,
    'RSS feed + Firecrawl scraping + LLM extraction. Uses The Events Calendar WordPress plugin.'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    tier = EXCLUDED.tier,
    url = EXCLUDED.url,
    feed_type = EXCLUDED.feed_type,
    is_active = EXCLUDED.is_active,
    notes = EXCLUDED.notes;
