-- =============================================================
-- INSERT GOLD LEVEL SOURCES (NIVEL ORO) - CCAA con APIs
-- Ejecutar en Supabase SQL Editor
-- =============================================================

-- Catalunya - Socrata/SODA API
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
    'catalunya_agenda',
    'Agenda Cultural de Catalunya',
    'https://analisi.transparenciacatalunya.cat/resource/rhpv-yr4f.json',
    'api',
    'Catalunya',
    'CT',
    true,
    1.0,
    100
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Euskadi - Kulturklik REST API
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
    'euskadi_kulturklik',
    'Kulturklik - Agenda Cultural Euskadi',
    'https://api.euskadi.eus/culture/events/v1.0/events/upcoming',
    'api',
    'País Vasco',
    'PV',
    true,
    1.0,
    20
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Castilla y León - CKAN OData API
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
    'castilla_leon_agenda',
    'Agenda Cultural Castilla y León',
    'https://analisis.datosabiertos.jcyl.es/api/explore/v2.1/catalog/datasets/eventos-de-la-agenda-cultural-categorizados-y-geolocalizados/records',
    'api',
    'Castilla y León',
    'CL',
    true,
    1.0,
    100
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Andalucía - Junta de Andalucía CKAN API
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
    'andalucia_agenda',
    'Agenda de Eventos Junta de Andalucía',
    'https://datos.juntadeandalucia.es/api/v0/schedule/all?format=json',
    'api',
    'Andalucía',
    'AN',
    true,
    1.0,
    50
)
ON CONFLICT (slug) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    adapter_type = EXCLUDED.adapter_type,
    is_active = EXCLUDED.is_active;

-- Madrid - Actualizar si ya existe
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
    'madrid_datos_abiertos',
    'Madrid Datos Abiertos - Eventos Culturales',
    'https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json',
    'api',
    'Comunidad de Madrid',
    'MD',
    true,
    1.0,
    20
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
WHERE adapter_type = 'api'
ORDER BY ccaa;
