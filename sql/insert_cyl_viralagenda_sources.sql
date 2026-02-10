-- =============================================================
-- INSERT BRONZE LEVEL SOURCES - CASTILLA Y LEÓN (via Viralagenda)
-- 9 provincias: Ávila, Burgos, León, Palencia, Salamanca, Segovia, Soria, Valladolid, Zamora
-- Ejecutar en Supabase SQL Editor
-- =============================================================

-- Ávila
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
    'viralagenda_avila',
    'Viral Agenda - Ávila',
    'https://www.viralagenda.com/es/castilla-y-leon/avila',
    'scraper',
    'Castilla y León',
    'CL',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Burgos
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
    'viralagenda_burgos',
    'Viral Agenda - Burgos',
    'https://www.viralagenda.com/es/castilla-y-leon/burgos',
    'scraper',
    'Castilla y León',
    'CL',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- León
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
    'viralagenda_leon',
    'Viral Agenda - León',
    'https://www.viralagenda.com/es/castilla-y-leon/leon',
    'scraper',
    'Castilla y León',
    'CL',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Palencia
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
    'viralagenda_palencia',
    'Viral Agenda - Palencia',
    'https://www.viralagenda.com/es/castilla-y-leon/palencia',
    'scraper',
    'Castilla y León',
    'CL',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Salamanca
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
    'viralagenda_salamanca',
    'Viral Agenda - Salamanca',
    'https://www.viralagenda.com/es/castilla-y-leon/salamanca',
    'scraper',
    'Castilla y León',
    'CL',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Segovia
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
    'viralagenda_segovia',
    'Viral Agenda - Segovia',
    'https://www.viralagenda.com/es/castilla-y-leon/segovia',
    'scraper',
    'Castilla y León',
    'CL',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Soria
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
    'viralagenda_soria',
    'Viral Agenda - Soria',
    'https://www.viralagenda.com/es/castilla-y-leon/soria',
    'scraper',
    'Castilla y León',
    'CL',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Valladolid
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
    'viralagenda_valladolid',
    'Viral Agenda - Valladolid',
    'https://www.viralagenda.com/es/castilla-y-leon/valladolid',
    'scraper',
    'Castilla y León',
    'CL',
    true,
    2.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Zamora
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
    'viralagenda_zamora',
    'Viral Agenda - Zamora',
    'https://www.viralagenda.com/es/castilla-y-leon/zamora',
    'scraper',
    'Castilla y León',
    'CL',
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
WHERE slug LIKE 'viralagenda_%' AND ccaa = 'Castilla y León'
ORDER BY slug;
