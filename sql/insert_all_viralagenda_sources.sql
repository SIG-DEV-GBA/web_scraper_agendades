-- =============================================================
-- INSERT ALL VIRALAGENDA SOURCES (33 provincias)
-- Ejecutar en Supabase SQL Editor
-- =============================================================

-- ============ CASTILLA Y LEON (9) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_avila', 'Viral Agenda - Ávila', 'https://www.viralagenda.com/es/castilla-y-leon/avila', 'scraper', 'Castilla y León', 'CL', true, 2.0, 50),
('viralagenda_burgos', 'Viral Agenda - Burgos', 'https://www.viralagenda.com/es/castilla-y-leon/burgos', 'scraper', 'Castilla y León', 'CL', true, 2.0, 50),
('viralagenda_leon', 'Viral Agenda - León', 'https://www.viralagenda.com/es/castilla-y-leon/leon', 'scraper', 'Castilla y León', 'CL', true, 2.0, 50),
('viralagenda_palencia', 'Viral Agenda - Palencia', 'https://www.viralagenda.com/es/castilla-y-leon/palencia', 'scraper', 'Castilla y León', 'CL', true, 2.0, 50),
('viralagenda_salamanca', 'Viral Agenda - Salamanca', 'https://www.viralagenda.com/es/castilla-y-leon/salamanca', 'scraper', 'Castilla y León', 'CL', true, 2.0, 50),
('viralagenda_segovia', 'Viral Agenda - Segovia', 'https://www.viralagenda.com/es/castilla-y-leon/segovia', 'scraper', 'Castilla y León', 'CL', true, 2.0, 50),
('viralagenda_soria', 'Viral Agenda - Soria', 'https://www.viralagenda.com/es/castilla-y-leon/soria', 'scraper', 'Castilla y León', 'CL', true, 2.0, 50),
('viralagenda_valladolid', 'Viral Agenda - Valladolid', 'https://www.viralagenda.com/es/castilla-y-leon/valladolid', 'scraper', 'Castilla y León', 'CL', true, 2.0, 50),
('viralagenda_zamora', 'Viral Agenda - Zamora', 'https://www.viralagenda.com/es/castilla-y-leon/zamora', 'scraper', 'Castilla y León', 'CL', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ ANDALUCIA (8) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_almeria', 'Viral Agenda - Almería', 'https://www.viralagenda.com/es/andalucia/almeria', 'scraper', 'Andalucía', 'AN', true, 2.0, 50),
('viralagenda_cadiz', 'Viral Agenda - Cádiz', 'https://www.viralagenda.com/es/andalucia/cadiz', 'scraper', 'Andalucía', 'AN', true, 2.0, 50),
('viralagenda_cordoba', 'Viral Agenda - Córdoba', 'https://www.viralagenda.com/es/andalucia/cordoba', 'scraper', 'Andalucía', 'AN', true, 2.0, 50),
('viralagenda_granada', 'Viral Agenda - Granada', 'https://www.viralagenda.com/es/andalucia/granada', 'scraper', 'Andalucía', 'AN', true, 2.0, 50),
('viralagenda_huelva', 'Viral Agenda - Huelva', 'https://www.viralagenda.com/es/andalucia/huelva', 'scraper', 'Andalucía', 'AN', true, 2.0, 50),
('viralagenda_jaen', 'Viral Agenda - Jaén', 'https://www.viralagenda.com/es/andalucia/jaen', 'scraper', 'Andalucía', 'AN', true, 2.0, 50),
('viralagenda_malaga', 'Viral Agenda - Málaga', 'https://www.viralagenda.com/es/andalucia/malaga', 'scraper', 'Andalucía', 'AN', true, 2.0, 50),
('viralagenda_sevilla', 'Viral Agenda - Sevilla', 'https://www.viralagenda.com/es/andalucia/sevilla', 'scraper', 'Andalucía', 'AN', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ GALICIA (4) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_a_coruna', 'Viral Agenda - A Coruña', 'https://www.viralagenda.com/es/galicia/a-coruna', 'scraper', 'Galicia', 'GA', true, 2.0, 50),
('viralagenda_lugo', 'Viral Agenda - Lugo', 'https://www.viralagenda.com/es/galicia/lugo', 'scraper', 'Galicia', 'GA', true, 2.0, 50),
('viralagenda_ourense', 'Viral Agenda - Ourense', 'https://www.viralagenda.com/es/galicia/ourense', 'scraper', 'Galicia', 'GA', true, 2.0, 50),
('viralagenda_pontevedra', 'Viral Agenda - Pontevedra', 'https://www.viralagenda.com/es/galicia/pontevedra', 'scraper', 'Galicia', 'GA', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ CASTILLA-LA MANCHA (5) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_albacete', 'Viral Agenda - Albacete', 'https://www.viralagenda.com/es/castilla-la-mancha/albacete', 'scraper', 'Castilla-La Mancha', 'CM', true, 2.0, 50),
('viralagenda_ciudad_real', 'Viral Agenda - Ciudad Real', 'https://www.viralagenda.com/es/castilla-la-mancha/ciudad-real', 'scraper', 'Castilla-La Mancha', 'CM', true, 2.0, 50),
('viralagenda_cuenca', 'Viral Agenda - Cuenca', 'https://www.viralagenda.com/es/castilla-la-mancha/cuenca', 'scraper', 'Castilla-La Mancha', 'CM', true, 2.0, 50),
('viralagenda_guadalajara', 'Viral Agenda - Guadalajara', 'https://www.viralagenda.com/es/castilla-la-mancha/guadalajara', 'scraper', 'Castilla-La Mancha', 'CM', true, 2.0, 50),
('viralagenda_toledo', 'Viral Agenda - Toledo', 'https://www.viralagenda.com/es/castilla-la-mancha/toledo', 'scraper', 'Castilla-La Mancha', 'CM', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ EXTREMADURA (1) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_caceres', 'Viral Agenda - Cáceres', 'https://www.viralagenda.com/es/extremadura/caceres/caceres', 'scraper', 'Extremadura', 'EX', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ CANARIAS (2) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_las_palmas', 'Viral Agenda - Las Palmas', 'https://www.viralagenda.com/es/canarias/las-palmas', 'scraper', 'Canarias', 'CN', true, 2.0, 50),
('viralagenda_santa_cruz_tenerife', 'Viral Agenda - Santa Cruz de Tenerife', 'https://www.viralagenda.com/es/canarias/santa-cruz-de-tenerife', 'scraper', 'Canarias', 'CN', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ ASTURIAS (1) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_asturias', 'Viral Agenda - Asturias', 'https://www.viralagenda.com/es/asturias', 'scraper', 'Asturias', 'AS', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ CANTABRIA (1) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_cantabria', 'Viral Agenda - Cantabria', 'https://www.viralagenda.com/es/cantabria', 'scraper', 'Cantabria', 'CB', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ MURCIA (1) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_murcia', 'Viral Agenda - Murcia', 'https://www.viralagenda.com/es/murcia', 'scraper', 'Región de Murcia', 'MC', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ NAVARRA (1) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_navarra', 'Viral Agenda - Navarra', 'https://www.viralagenda.com/es/navarra', 'scraper', 'Navarra', 'NC', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ LA RIOJA (1) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_la_rioja', 'Viral Agenda - La Rioja', 'https://www.viralagenda.com/es/la-rioja', 'scraper', 'La Rioja', 'RI', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ PAIS VASCO (3) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_araba', 'Viral Agenda - Araba/Álava', 'https://www.viralagenda.com/es/pais-vasco/araba-alava', 'scraper', 'País Vasco', 'PV', true, 2.0, 50),
('viralagenda_bizkaia', 'Viral Agenda - Bizkaia', 'https://www.viralagenda.com/es/pais-vasco/bizkaia', 'scraper', 'País Vasco', 'PV', true, 2.0, 50),
('viralagenda_gipuzkoa', 'Viral Agenda - Gipuzkoa', 'https://www.viralagenda.com/es/pais-vasco/gipuzkoa', 'scraper', 'País Vasco', 'PV', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ ARAGON (3) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_huesca', 'Viral Agenda - Huesca', 'https://www.viralagenda.com/es/aragon/huesca', 'scraper', 'Aragón', 'AR', true, 2.0, 50),
('viralagenda_teruel', 'Viral Agenda - Teruel', 'https://www.viralagenda.com/es/aragon/teruel', 'scraper', 'Aragón', 'AR', true, 2.0, 50),
('viralagenda_zaragoza', 'Viral Agenda - Zaragoza', 'https://www.viralagenda.com/es/aragon/zaragoza', 'scraper', 'Aragón', 'AR', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ COMUNITAT VALENCIANA (3) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_alicante', 'Viral Agenda - Alicante', 'https://www.viralagenda.com/es/comunitat-valenciana/alicante', 'scraper', 'Comunitat Valenciana', 'VC', true, 2.0, 50),
('viralagenda_castellon', 'Viral Agenda - Castellón', 'https://www.viralagenda.com/es/comunitat-valenciana/castellon', 'scraper', 'Comunitat Valenciana', 'VC', true, 2.0, 50),
('viralagenda_valencia', 'Viral Agenda - Valencia', 'https://www.viralagenda.com/es/comunitat-valenciana/valencia', 'scraper', 'Comunitat Valenciana', 'VC', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ CATALUÑA (4) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_barcelona', 'Viral Agenda - Barcelona', 'https://www.viralagenda.com/es/cataluna/barcelona', 'scraper', 'Cataluña', 'CT', true, 2.0, 50),
('viralagenda_girona', 'Viral Agenda - Girona', 'https://www.viralagenda.com/es/cataluna/girona', 'scraper', 'Cataluña', 'CT', true, 2.0, 50),
('viralagenda_lleida', 'Viral Agenda - Lleida', 'https://www.viralagenda.com/es/cataluna/lleida', 'scraper', 'Cataluña', 'CT', true, 2.0, 50),
('viralagenda_tarragona', 'Viral Agenda - Tarragona', 'https://www.viralagenda.com/es/cataluna/tarragona', 'scraper', 'Cataluña', 'CT', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ ILLES BALEARS (1) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_baleares', 'Viral Agenda - Illes Balears', 'https://www.viralagenda.com/es/illes-balears', 'scraper', 'Illes Balears', 'IB', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ COMUNIDAD DE MADRID (1) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_madrid', 'Viral Agenda - Madrid', 'https://www.viralagenda.com/es/madrid', 'scraper', 'Comunidad de Madrid', 'MD', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- ============ EXTREMADURA - BADAJOZ (1) ============
INSERT INTO scraper_sources (slug, name, source_url, adapter_type, ccaa, ccaa_code, is_active, rate_limit_delay, batch_size)
VALUES
('viralagenda_badajoz', 'Viral Agenda - Badajoz', 'https://www.viralagenda.com/es/extremadura/badajoz', 'scraper', 'Extremadura', 'EX', true, 2.0, 50)
ON CONFLICT (slug) DO UPDATE SET source_url = EXCLUDED.source_url, is_active = EXCLUDED.is_active;

-- =============================================================
-- VERIFICACION (49 fuentes totales)
-- =============================================================

SELECT
    ccaa,
    COUNT(*) as count
FROM scraper_sources
WHERE slug LIKE 'viralagenda_%'
GROUP BY ccaa
ORDER BY ccaa;
