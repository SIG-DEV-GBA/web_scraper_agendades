-- =============================================================
-- INSERT BRONZE LEVEL SOURCES - ANDALUCÍA (via Viralagenda)
-- 8 provincias: Almería, Cádiz, Córdoba, Granada, Huelva, Jaén, Málaga, Sevilla
-- Ejecutar en Supabase SQL Editor
-- =============================================================

-- Almería
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
    'viralagenda_almeria',
    'Viral Agenda - Almería',
    'https://www.viralagenda.com/es/andalucia/almeria',
    'scraper',
    'Andalucía',
    'AN',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Cádiz
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
    'viralagenda_cadiz',
    'Viral Agenda - Cádiz',
    'https://www.viralagenda.com/es/andalucia/cadiz',
    'scraper',
    'Andalucía',
    'AN',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Córdoba
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
    'viralagenda_cordoba',
    'Viral Agenda - Córdoba',
    'https://www.viralagenda.com/es/andalucia/cordoba',
    'scraper',
    'Andalucía',
    'AN',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Granada
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
    'viralagenda_granada',
    'Viral Agenda - Granada',
    'https://www.viralagenda.com/es/andalucia/granada',
    'scraper',
    'Andalucía',
    'AN',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Huelva
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
    'viralagenda_huelva',
    'Viral Agenda - Huelva',
    'https://www.viralagenda.com/es/andalucia/huelva',
    'scraper',
    'Andalucía',
    'AN',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Jaén
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
    'viralagenda_jaen',
    'Viral Agenda - Jaén',
    'https://www.viralagenda.com/es/andalucia/jaen',
    'scraper',
    'Andalucía',
    'AN',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Málaga
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
    'viralagenda_malaga',
    'Viral Agenda - Málaga',
    'https://www.viralagenda.com/es/andalucia/malaga',
    'scraper',
    'Andalucía',
    'AN',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Sevilla
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
    'viralagenda_sevilla',
    'Viral Agenda - Sevilla',
    'https://www.viralagenda.com/es/andalucia/sevilla',
    'scraper',
    'Andalucía',
    'AN',
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
WHERE slug LIKE 'viralagenda_%' AND ccaa = 'Andalucía'
ORDER BY slug;
