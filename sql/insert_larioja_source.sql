-- =============================================================
-- INSERT BRONZE LEVEL SOURCES - LA RIOJA
-- Ejecutar en Supabase SQL Editor
-- =============================================================

-- La Rioja - agenda.larioja.com - Web Scraping (Vocento CMS, JSON-LD)
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
    'larioja_agenda',
    'Agenda de La Rioja - LARIOJA.COM',
    'https://agenda.larioja.com/',
    'scraper',
    'La Rioja',
    'RI',
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
WHERE ccaa = 'La Rioja'
ORDER BY slug;
