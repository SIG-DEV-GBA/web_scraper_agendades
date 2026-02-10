-- =============================================================
-- INSERT SILVER/GOLD LEVEL SOURCES - CANTABRIA
-- Ejecutar en Supabase SQL Editor
-- =============================================================

-- Cantabria - turismodecantabria.com iCal feed (Gold-level structured data)
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
    'cantabria_turismo',
    'Turismo de Cantabria - Agenda de Eventos',
    'https://turismodecantabria.com/proximamente-eventos/?ical=1',
    'rss',
    'Cantabria',
    'CB',
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
WHERE ccaa = 'Cantabria'
ORDER BY slug;
