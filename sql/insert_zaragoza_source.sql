-- Insert Zaragoza source into scraper_sources table
-- Agenda Cultural de Zaragoza - Gold tier API

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
    'zaragoza_cultura',
    'Agenda Cultural de Zaragoza',
    'https://www.zaragoza.es/sede/servicio/cultura.json',
    'api',
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
WHERE slug = 'zaragoza_cultura';
