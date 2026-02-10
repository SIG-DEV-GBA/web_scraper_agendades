-- =============================================================
-- INSERT BRONZE LEVEL SOURCE - BADAJOZ (EXTREMADURA)
-- Ejecutar en Supabase SQL Editor
-- =============================================================

-- Badajoz - aytobadajoz.es - Web Scraping (Firecrawl + Bronze adapter)
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
    'badajoz_agenda',
    'Agenda Cultural Ayuntamiento de Badajoz',
    'https://www.aytobadajoz.es/es/ayto/agenda/',
    'scraper',
    'Extremadura',
    'EX',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- =============================================================
-- VERIFICACION
-- =============================================================

SELECT
    slug,
    name,
    ccaa,
    adapter_type,
    is_active,
    batch_size
FROM scraper_sources
WHERE ccaa = 'Extremadura'
ORDER BY slug;
