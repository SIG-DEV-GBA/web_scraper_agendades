-- Insert viralagenda sources for 7 new CCAAs
-- Galicia (4), Asturias (1), Canarias (2), Cantabria (1), Castilla-La Mancha (5), Murcia (1), Navarra (1)

-- ============================================================
-- GALICIA (4 provinces)
-- ============================================================
INSERT INTO scraper_sources (slug, name, ccaa, ccaa_code, source_url, adapter_type, is_active)
VALUES
    ('viralagenda_a_coruna', 'Viral Agenda - A Coruña', 'Galicia', 'GA', 'https://www.viralagenda.com/es/galicia/a-coruna', 'bronze', true),
    ('viralagenda_lugo', 'Viral Agenda - Lugo', 'Galicia', 'GA', 'https://www.viralagenda.com/es/galicia/lugo', 'bronze', true),
    ('viralagenda_ourense', 'Viral Agenda - Ourense', 'Galicia', 'GA', 'https://www.viralagenda.com/es/galicia/ourense', 'bronze', true),
    ('viralagenda_pontevedra', 'Viral Agenda - Pontevedra', 'Galicia', 'GA', 'https://www.viralagenda.com/es/galicia/pontevedra', 'bronze', true)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    source_url = EXCLUDED.source_url,
    is_active = EXCLUDED.is_active;

-- ============================================================
-- ASTURIAS (uniprovincial)
-- ============================================================
INSERT INTO scraper_sources (slug, name, ccaa, ccaa_code, source_url, adapter_type, is_active)
VALUES
    ('viralagenda_asturias', 'Viral Agenda - Asturias', 'Asturias', 'AS', 'https://www.viralagenda.com/es/asturias', 'bronze', true)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    source_url = EXCLUDED.source_url,
    is_active = EXCLUDED.is_active;

-- ============================================================
-- CANARIAS (2 provinces)
-- ============================================================
INSERT INTO scraper_sources (slug, name, ccaa, ccaa_code, source_url, adapter_type, is_active)
VALUES
    ('viralagenda_las_palmas', 'Viral Agenda - Las Palmas', 'Canarias', 'CN', 'https://www.viralagenda.com/es/canarias/las-palmas', 'bronze', true),
    ('viralagenda_santa_cruz_tenerife', 'Viral Agenda - Santa Cruz de Tenerife', 'Canarias', 'CN', 'https://www.viralagenda.com/es/canarias/santa-cruz-de-tenerife', 'bronze', true)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    source_url = EXCLUDED.source_url,
    is_active = EXCLUDED.is_active;

-- ============================================================
-- CANTABRIA (uniprovincial)
-- ============================================================
INSERT INTO scraper_sources (slug, name, ccaa, ccaa_code, source_url, adapter_type, is_active)
VALUES
    ('viralagenda_cantabria', 'Viral Agenda - Cantabria', 'Cantabria', 'CB', 'https://www.viralagenda.com/es/cantabria', 'bronze', true)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    source_url = EXCLUDED.source_url,
    is_active = EXCLUDED.is_active;

-- ============================================================
-- CASTILLA-LA MANCHA (5 provinces)
-- ============================================================
INSERT INTO scraper_sources (slug, name, ccaa, ccaa_code, source_url, adapter_type, is_active)
VALUES
    ('viralagenda_albacete', 'Viral Agenda - Albacete', 'Castilla-La Mancha', 'CM', 'https://www.viralagenda.com/es/castilla-la-mancha/albacete', 'bronze', true),
    ('viralagenda_ciudad_real', 'Viral Agenda - Ciudad Real', 'Castilla-La Mancha', 'CM', 'https://www.viralagenda.com/es/castilla-la-mancha/ciudad-real', 'bronze', true),
    ('viralagenda_cuenca', 'Viral Agenda - Cuenca', 'Castilla-La Mancha', 'CM', 'https://www.viralagenda.com/es/castilla-la-mancha/cuenca', 'bronze', true),
    ('viralagenda_guadalajara', 'Viral Agenda - Guadalajara', 'Castilla-La Mancha', 'CM', 'https://www.viralagenda.com/es/castilla-la-mancha/guadalajara', 'bronze', true),
    ('viralagenda_toledo', 'Viral Agenda - Toledo', 'Castilla-La Mancha', 'CM', 'https://www.viralagenda.com/es/castilla-la-mancha/toledo', 'bronze', true)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    source_url = EXCLUDED.source_url,
    is_active = EXCLUDED.is_active;

-- ============================================================
-- MURCIA (uniprovincial)
-- ============================================================
INSERT INTO scraper_sources (slug, name, ccaa, ccaa_code, source_url, adapter_type, is_active)
VALUES
    ('viralagenda_murcia', 'Viral Agenda - Murcia', 'Murcia', 'MC', 'https://www.viralagenda.com/es/murcia', 'bronze', true)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    source_url = EXCLUDED.source_url,
    is_active = EXCLUDED.is_active;

-- ============================================================
-- NAVARRA (uniprovincial)
-- ============================================================
INSERT INTO scraper_sources (slug, name, ccaa, ccaa_code, source_url, adapter_type, is_active)
VALUES
    ('viralagenda_navarra', 'Viral Agenda - Navarra', 'Navarra', 'NC', 'https://www.viralagenda.com/es/navarra', 'bronze', true)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    source_url = EXCLUDED.source_url,
    is_active = EXCLUDED.is_active;
