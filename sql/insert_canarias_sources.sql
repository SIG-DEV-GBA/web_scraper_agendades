-- =============================================================
-- INSERT BRONZE LEVEL SOURCES - CANARIAS
-- Ejecutar en Supabase SQL Editor
-- =============================================================

-- Canarias - lagenda.org (Tenerife) - Web Scraping
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
    'canarias_lagenda',
    'La Agenda de Tenerife - lagenda.org',
    'https://lagenda.org/programacion',
    'scraper',
    'Canarias',
    'CN',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Canarias - cultura.grancanaria.com (Gran Canaria) - Web Scraping
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
    'canarias_grancanaria',
    'Cultura Gran Canaria - Cabildo',
    'https://cultura.grancanaria.com/agenda/',
    'scraper',
    'Canarias',
    'CN',
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
WHERE ccaa = 'Canarias'
ORDER BY slug;
