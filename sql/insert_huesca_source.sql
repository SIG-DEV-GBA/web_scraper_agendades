-- Insert Huesca source into scraper_sources table
-- RADAR Huesca - Plata tier RSS feed

INSERT INTO scraper_sources (
    slug,
    name,
    source_url,
    adapter_type,
    ccaa,
    ccaa_code,
    is_active,
    rate_limit_delay,
    batch_size
) VALUES (
    'huesca_radar',
    'RADAR Huesca - Programación Cultural',
    'https://radarhuesca.es/eventos/feed/',
    'rss',
    'Aragón',
    'AR',
    true,
    1.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    ccaa = EXCLUDED.ccaa,
    ccaa_code = EXCLUDED.ccaa_code,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- Verify insertion
SELECT id, slug, name, ccaa, adapter_type, is_active
FROM scraper_sources
WHERE slug = 'huesca_radar';
