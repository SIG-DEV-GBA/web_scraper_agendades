-- =============================================================
-- INSERT BRONZE LEVEL SOURCES - NAVARRA
-- Ejecutar en Supabase SQL Editor
-- =============================================================

-- Navarra - culturanavarra.es - Web Scraping (Server-rendered, no Firecrawl)
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
    'navarra_cultura',
    'Cultura Navarra - Gobierno de Navarra',
    'https://www.culturanavarra.es/es/agenda',
    'scraper',
    'Navarra',
    'NA',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- =============================================================
-- VERIFICACIÓN
-- =============================================================

SELECT
    slug,
    name,
    ccaa,
    adapter_type,
    is_active,
    batch_size
FROM scraper_sources
WHERE ccaa = 'Navarra'
ORDER BY slug;
