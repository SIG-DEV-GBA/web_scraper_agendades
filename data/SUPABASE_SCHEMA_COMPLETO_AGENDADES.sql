-- ============================================================================
-- ESQUEMA COMPLETO DE BASE DE DATOS - AGENDADES (Si-Agenda)
-- ============================================================================
--
-- Proyecto: Calendario de Eventos para Sistema de Informacion de GBA
-- Fecha de exportacion: 2026-01-20
-- 
-- Este archivo contiene todas las migraciones de Supabase concatenadas:
-- - Tablas (events, users, calendars, categories, tags, etc.)
-- - Relaciones (event_calendars, event_tags, calendar_shares, etc.)
-- - Enums (event_status, notification_type, organizer_type, etc.)
-- - Funciones (archive_event, get_shared_events, etc.)
-- - Triggers (auto-archive, notifications, audit logs)
-- - Politicas RLS (Row Level Security)
-- - Indices de rendimiento
--
-- Para usar en otro proyecto:
-- 1. Crear un nuevo proyecto en Supabase
-- 2. Ejecutar este script en SQL Editor (por secciones si es muy largo)
-- 3. Ajustar segun necesidades del nuevo proyecto
--
-- ============================================================================

-- Migración: Crear relación muchos-a-muchos entre eventos y calendarios
-- Fecha: 2024-12-15

-- 1. Crear tabla pivote event_calendars
CREATE TABLE IF NOT EXISTS event_calendars (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  calendar_id UUID NOT NULL REFERENCES calendars(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(event_id, calendar_id)
);

-- 2. Índices para mejorar rendimiento
CREATE INDEX IF NOT EXISTS idx_event_calendars_event_id ON event_calendars(event_id);
CREATE INDEX IF NOT EXISTS idx_event_calendars_calendar_id ON event_calendars(calendar_id);

-- 3. Migrar datos existentes de calendar_id a event_calendars
INSERT INTO event_calendars (event_id, calendar_id)
SELECT id, calendar_id FROM events
WHERE calendar_id IS NOT NULL
ON CONFLICT (event_id, calendar_id) DO NOTHING;

-- 4. Habilitar RLS
ALTER TABLE event_calendars ENABLE ROW LEVEL SECURITY;

-- 5. Políticas RLS
-- Lectura pública para calendarios públicos
CREATE POLICY "Lectura pública event_calendars" ON event_calendars
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM calendars
      WHERE calendars.id = event_calendars.calendar_id
      AND calendars.is_public = true
    )
  );

-- Admins pueden todo
CREATE POLICY "Admins full access event_calendars" ON event_calendars
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND users.role IN ('admin', 'superadmin')
    )
  );

-- Usuarios pueden gestionar sus propios calendarios
CREATE POLICY "Users manage own calendars event_calendars" ON event_calendars
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM calendars
      WHERE calendars.id = event_calendars.calendar_id
      AND calendars.user_id = auth.uid()
    )
  );
-- Migración: Añadir campos de localización y tipo de calendario
-- Fecha: 2024-12-17

-- 1. Añadir campo comunidad_autonoma a event_locations si no existe
ALTER TABLE event_locations
ADD COLUMN IF NOT EXISTS comunidad_autonoma TEXT,
ADD COLUMN IF NOT EXISTS municipio TEXT;

-- 2. Añadir campo type a calendars para clasificar (nacional, ccaa, provincia)
ALTER TABLE calendars
ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'other',
ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES calendars(id);

-- 3. Actualizar calendarios existentes con su tipo
UPDATE calendars SET type = 'nacional' WHERE name IN ('Público', 'Calendario Público', 'Nacional');
UPDATE calendars SET type = 'ccaa' WHERE name IN (
  'Andalucía', 'Aragón', 'Asturias', 'Islas Baleares', 'Canarias',
  'Cantabria', 'Castilla-La Mancha', 'Castilla y León', 'Cataluña',
  'Extremadura', 'Galicia', 'Madrid', 'Murcia', 'Navarra',
  'País Vasco', 'La Rioja', 'Valencia', 'Ceuta', 'Melilla'
);

-- 4. Crear índices para búsqueda
CREATE INDEX IF NOT EXISTS idx_event_locations_comunidad ON event_locations(comunidad_autonoma);
CREATE INDEX IF NOT EXISTS idx_event_locations_municipio ON event_locations(municipio);
CREATE INDEX IF NOT EXISTS idx_calendars_type ON calendars(type);
CREATE INDEX IF NOT EXISTS idx_calendars_parent ON calendars(parent_id);
-- ==========================================
-- FIX: Permitir creación de usuarios desde el trigger
-- ==========================================

-- El trigger handle_new_user debe ser SECURITY DEFINER para bypasear RLS
-- Primero, recreamos la función con SECURITY DEFINER

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER  -- Importante: ejecutar con permisos del owner (postgres)
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name, avatar_url, birth_date, gender, location_ccaa_id, location_provincia_id, created_at, updated_at)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
    COALESCE(NEW.raw_user_meta_data->>'avatar_url', NEW.raw_user_meta_data->>'picture', NULL),
    CASE
      WHEN NEW.raw_user_meta_data->>'birth_date' IS NOT NULL
      THEN (NEW.raw_user_meta_data->>'birth_date')::date
      ELSE NULL
    END,
    NEW.raw_user_meta_data->>'gender',
    CASE
      WHEN NEW.raw_user_meta_data->>'location_ccaa_id' IS NOT NULL
      THEN (NEW.raw_user_meta_data->>'location_ccaa_id')::uuid
      ELSE NULL
    END,
    CASE
      WHEN NEW.raw_user_meta_data->>'location_provincia_id' IS NOT NULL
      THEN (NEW.raw_user_meta_data->>'location_provincia_id')::uuid
      ELSE NULL
    END,
    NOW(),
    NOW()
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), users.full_name),
    avatar_url = COALESCE(EXCLUDED.avatar_url, users.avatar_url),
    updated_at = NOW();

  RETURN NEW;
END;
$$;

-- Asegurar que el trigger existe
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Política para permitir que el sistema inserte usuarios (para el trigger SECURITY DEFINER)
-- No es estrictamente necesaria si usamos SECURITY DEFINER, pero es buena práctica
DROP POLICY IF EXISTS "Service role can insert users" ON users;
CREATE POLICY "Service role can insert users" ON users
  FOR INSERT TO service_role
  WITH CHECK (true);

-- Política para que usuarios autenticados puedan ver su propio registro después de crearse
DROP POLICY IF EXISTS "Users can view own profile" ON users;
CREATE POLICY "Users can view own profile" ON users
  FOR SELECT TO authenticated
  USING (auth.uid() = id);
-- ==========================================
-- FIX: Corregir handle_new_user para crear calendario por defecto
-- Fecha: 2024-12-19
--
-- PROBLEMA: La migración 20241219_fix_user_creation.sql eliminó
-- la creación del calendario por defecto que estaba en 03_users.sql
--
-- SOLUCIÓN: Actualizar la función para incluir la creación del calendario
-- ==========================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- 1. Crear registro en public.users
  INSERT INTO public.users (
    id,
    email,
    full_name,
    avatar_url,
    birth_date,
    gender,
    location_ccaa_id,
    location_provincia_id,
    created_at,
    updated_at
  )
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
    COALESCE(NEW.raw_user_meta_data->>'avatar_url', NEW.raw_user_meta_data->>'picture', NULL),
    CASE
      WHEN NEW.raw_user_meta_data->>'birth_date' IS NOT NULL
      THEN (NEW.raw_user_meta_data->>'birth_date')::date
      ELSE NULL
    END,
    NEW.raw_user_meta_data->>'gender',
    CASE
      WHEN NEW.raw_user_meta_data->>'location_ccaa_id' IS NOT NULL
      THEN (NEW.raw_user_meta_data->>'location_ccaa_id')::uuid
      ELSE NULL
    END,
    CASE
      WHEN NEW.raw_user_meta_data->>'location_provincia_id' IS NOT NULL
      THEN (NEW.raw_user_meta_data->>'location_provincia_id')::uuid
      ELSE NULL
    END,
    NOW(),
    NOW()
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), users.full_name),
    avatar_url = COALESCE(EXCLUDED.avatar_url, users.avatar_url),
    updated_at = NOW();

  -- 2. Crear calendario personal por defecto (si no existe)
  INSERT INTO public.calendars (
    user_id,
    name,
    description,
    color,
    is_default,
    is_public,
    created_at,
    updated_at
  )
  VALUES (
    NEW.id,
    'Mi Calendario',
    'Tu calendario personal de eventos',
    '#C4704C',  -- terracotta
    true,
    false,
    NOW(),
    NOW()
  )
  ON CONFLICT DO NOTHING;  -- No hacer nada si ya existe

  RETURN NEW;
END;
$$;

-- Asegurar que el trigger existe
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ==========================================
-- Crear calendarios para usuarios existentes que no tienen ninguno
-- ==========================================
INSERT INTO public.calendars (user_id, name, description, color, is_default, is_public, created_at, updated_at)
SELECT
  u.id,
  'Mi Calendario',
  'Tu calendario personal de eventos',
  '#C4704C',
  true,
  false,
  NOW(),
  NOW()
FROM public.users u
WHERE NOT EXISTS (
  SELECT 1 FROM public.calendars c WHERE c.user_id = u.id
);

-- ==========================================
-- Verificación (ejecutar manualmente para confirmar)
-- ==========================================
-- SELECT u.id, u.email, c.id as calendar_id, c.name as calendar_name
-- FROM public.users u
-- LEFT JOIN public.calendars c ON c.user_id = u.id AND c.is_default = true
-- ORDER BY u.created_at DESC;
-- Migración: Crear ENUM para tipos de organizador
-- Fecha: 2024-12-22

-- 1. Crear el ENUM
DO $$ BEGIN
  CREATE TYPE organizer_type AS ENUM (
    'asociacion',
    'institucion',
    'empresa',
    'particular',
    'ayuntamiento',
    'ong',
    'fundacion',
    'universidad',
    'otro'
  );
EXCEPTION
  WHEN duplicate_object THEN null;
END $$;

-- 2. Convertir el campo type de text a enum
-- Primero renombrar la columna antigua
ALTER TABLE event_organizers
  RENAME COLUMN type TO type_old;

-- Añadir la nueva columna con el ENUM
ALTER TABLE event_organizers
  ADD COLUMN type organizer_type DEFAULT 'otro';

-- Migrar datos existentes
UPDATE event_organizers SET type =
  CASE
    WHEN type_old = 'asociacion' THEN 'asociacion'::organizer_type
    WHEN type_old = 'institucion' THEN 'institucion'::organizer_type
    WHEN type_old = 'empresa' THEN 'empresa'::organizer_type
    WHEN type_old = 'particular' THEN 'particular'::organizer_type
    WHEN type_old = 'ayuntamiento' THEN 'ayuntamiento'::organizer_type
    WHEN type_old = 'ong' THEN 'ong'::organizer_type
    WHEN type_old = 'fundacion' THEN 'fundacion'::organizer_type
    WHEN type_old = 'universidad' THEN 'universidad'::organizer_type
    ELSE 'otro'::organizer_type
  END;

-- Eliminar la columna antigua
ALTER TABLE event_organizers DROP COLUMN type_old;
-- Migración: Añadir campo type_other para cuando el tipo es "otro"
-- Fecha: 2024-12-22

ALTER TABLE event_organizers
  ADD COLUMN IF NOT EXISTS type_other TEXT;

-- Comentario para documentar
COMMENT ON COLUMN event_organizers.type_other IS 'Texto personalizado cuando type = otro';
-- ============================================================
-- MIGRACIÓN: Sistema de Historial y KPIs de Eventos
-- Fecha: 2024-12-24
--
-- Este sistema guarda estadísticas históricas de eventos
-- incluso después de que sean eliminados por caducidad
-- ============================================================

-- ==========================================
-- TABLA: event_archive (eventos archivados)
-- Guarda una copia de los eventos cuando se eliminan
-- ==========================================
CREATE TABLE IF NOT EXISTS event_archive (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  original_event_id UUID NOT NULL,

  -- Datos básicos del evento
  title TEXT NOT NULL,
  description TEXT,
  category_id UUID,
  category_name TEXT,

  -- Fechas del evento
  start_date DATE NOT NULL,
  end_date DATE,
  start_time TIME,
  end_time TIME,

  -- Ubicación
  location_type TEXT, -- 'physical', 'online', 'hybrid'
  venue_name TEXT,
  address TEXT,
  city TEXT,
  province TEXT,
  comunidad_autonoma TEXT,
  country TEXT DEFAULT 'España',

  -- Organizador
  organizer_name TEXT,
  organizer_type TEXT,

  -- Metadatos
  is_published BOOLEAN DEFAULT true,
  is_featured BOOLEAN DEFAULT false,
  source TEXT, -- 'manual', 'import', 'api'
  external_id TEXT,

  -- Tags como array
  tags TEXT[],

  -- Calendarios asociados
  calendar_ids UUID[],
  calendar_names TEXT[],

  -- Fechas de auditoría
  original_created_at TIMESTAMPTZ,
  original_updated_at TIMESTAMPTZ,
  archived_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_reason TEXT DEFAULT 'expired', -- 'expired', 'manual', 'duplicate'

  -- Usuario que creó el evento original
  created_by UUID
);

-- Índices para búsquedas eficientes
CREATE INDEX IF NOT EXISTS idx_event_archive_dates ON event_archive(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_event_archive_archived_at ON event_archive(archived_at);
CREATE INDEX IF NOT EXISTS idx_event_archive_category ON event_archive(category_id);
CREATE INDEX IF NOT EXISTS idx_event_archive_location ON event_archive(city, province, comunidad_autonoma);
CREATE INDEX IF NOT EXISTS idx_event_archive_source ON event_archive(source);

-- ==========================================
-- TABLA: event_stats_daily (estadísticas diarias)
-- Agregaciones diarias para KPIs
-- ==========================================
CREATE TABLE IF NOT EXISTS event_stats_daily (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date DATE NOT NULL UNIQUE,

  -- Contadores de eventos
  total_events_active INTEGER DEFAULT 0,
  total_events_published INTEGER DEFAULT 0,
  events_created_today INTEGER DEFAULT 0,
  events_deleted_today INTEGER DEFAULT 0,
  events_expired_today INTEGER DEFAULT 0,

  -- Por tipo de ubicación
  events_physical INTEGER DEFAULT 0,
  events_online INTEGER DEFAULT 0,
  events_hybrid INTEGER DEFAULT 0,

  -- Por fuente
  events_from_import INTEGER DEFAULT 0,
  events_from_manual INTEGER DEFAULT 0,
  events_from_api INTEGER DEFAULT 0,

  -- Metadatos
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_stats_daily_date ON event_stats_daily(date);

-- ==========================================
-- TABLA: event_stats_monthly (estadísticas mensuales)
-- Agregaciones mensuales para reportes
-- ==========================================
CREATE TABLE IF NOT EXISTS event_stats_monthly (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,

  -- Totales del mes
  total_events_created INTEGER DEFAULT 0,
  total_events_deleted INTEGER DEFAULT 0,
  total_events_expired INTEGER DEFAULT 0,

  -- Por categoría (JSON para flexibilidad)
  events_by_category JSONB DEFAULT '{}',

  -- Por ubicación geográfica
  events_by_province JSONB DEFAULT '{}',
  events_by_comunidad JSONB DEFAULT '{}',

  -- Por tipo
  events_physical INTEGER DEFAULT 0,
  events_online INTEGER DEFAULT 0,
  events_hybrid INTEGER DEFAULT 0,

  -- Por fuente
  events_from_import INTEGER DEFAULT 0,
  events_from_manual INTEGER DEFAULT 0,
  events_from_api INTEGER DEFAULT 0,

  -- Metadatos
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(year, month)
);

CREATE INDEX IF NOT EXISTS idx_event_stats_monthly_date ON event_stats_monthly(year, month);

-- ==========================================
-- FUNCIÓN: archive_event_before_delete
-- Archiva el evento antes de eliminarlo
-- ==========================================
CREATE OR REPLACE FUNCTION archive_event_before_delete()
RETURNS TRIGGER AS $$
DECLARE
  v_category_name TEXT;
  v_tags TEXT[];
  v_calendar_ids UUID[];
  v_calendar_names TEXT[];
  v_location_type TEXT;
  v_venue_name TEXT;
  v_address TEXT;
  v_city TEXT;
  v_province TEXT;
  v_comunidad TEXT;
  v_organizer_name TEXT;
  v_organizer_type TEXT;
BEGIN
  -- Obtener nombre de categoría
  SELECT name INTO v_category_name
  FROM categories WHERE id = OLD.category_id;

  -- Obtener tags
  SELECT ARRAY_AGG(t.name) INTO v_tags
  FROM event_tags et
  JOIN tags t ON t.id = et.tag_id
  WHERE et.event_id = OLD.id;

  -- Obtener calendarios
  SELECT ARRAY_AGG(ec.calendar_id), ARRAY_AGG(c.name)
  INTO v_calendar_ids, v_calendar_names
  FROM event_calendars ec
  JOIN calendars c ON c.id = ec.calendar_id
  WHERE ec.event_id = OLD.id;

  -- Obtener ubicación
  SELECT
    el.venue_name,
    el.address,
    el.city,
    p.nombre,
    ca.nombre
  INTO v_venue_name, v_address, v_city, v_province, v_comunidad
  FROM event_locations el
  LEFT JOIN provincias p ON p.id = el.province_id
  LEFT JOIN comunidades_autonomas ca ON ca.id = el.comunidad_autonoma_id
  WHERE el.event_id = OLD.id
  LIMIT 1;

  -- Determinar tipo de ubicación
  IF EXISTS (SELECT 1 FROM event_online WHERE event_id = OLD.id) THEN
    IF v_venue_name IS NOT NULL THEN
      v_location_type := 'hybrid';
    ELSE
      v_location_type := 'online';
    END IF;
  ELSE
    v_location_type := 'physical';
  END IF;

  -- Obtener organizador
  SELECT name, type INTO v_organizer_name, v_organizer_type
  FROM event_organizers
  WHERE event_id = OLD.id
  LIMIT 1;

  -- Insertar en archivo
  INSERT INTO event_archive (
    original_event_id,
    title,
    description,
    category_id,
    category_name,
    start_date,
    end_date,
    start_time,
    end_time,
    location_type,
    venue_name,
    address,
    city,
    province,
    comunidad_autonoma,
    organizer_name,
    organizer_type,
    is_published,
    is_featured,
    source,
    external_id,
    tags,
    calendar_ids,
    calendar_names,
    original_created_at,
    original_updated_at,
    deleted_reason,
    created_by
  ) VALUES (
    OLD.id,
    OLD.title,
    OLD.description,
    OLD.category_id,
    v_category_name,
    OLD.start_date,
    OLD.end_date,
    OLD.start_time,
    OLD.end_time,
    v_location_type,
    v_venue_name,
    v_address,
    v_city,
    v_province,
    v_comunidad,
    v_organizer_name,
    v_organizer_type,
    OLD.is_published,
    OLD.is_featured,
    OLD.source,
    OLD.external_id,
    v_tags,
    v_calendar_ids,
    v_calendar_names,
    OLD.created_at,
    OLD.updated_at,
    CASE
      WHEN OLD.end_date < CURRENT_DATE - INTERVAL '7 days' THEN 'expired'
      ELSE 'manual'
    END,
    OLD.created_by
  );

  -- Actualizar estadísticas diarias
  INSERT INTO event_stats_daily (date, events_deleted_today)
  VALUES (CURRENT_DATE, 1)
  ON CONFLICT (date) DO UPDATE
  SET events_deleted_today = event_stats_daily.events_deleted_today + 1,
      updated_at = NOW();

  -- Si es por expiración, también contar
  IF OLD.end_date < CURRENT_DATE - INTERVAL '7 days' THEN
    UPDATE event_stats_daily
    SET events_expired_today = events_expired_today + 1
    WHERE date = CURRENT_DATE;
  END IF;

  RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- FUNCIÓN: update_daily_stats_on_insert
-- Actualiza estadísticas cuando se crea un evento
-- ==========================================
CREATE OR REPLACE FUNCTION update_daily_stats_on_insert()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO event_stats_daily (
    date,
    events_created_today,
    events_from_import,
    events_from_manual,
    events_from_api
  )
  VALUES (
    CURRENT_DATE,
    1,
    CASE WHEN NEW.source = 'import' THEN 1 ELSE 0 END,
    CASE WHEN NEW.source = 'manual' OR NEW.source IS NULL THEN 1 ELSE 0 END,
    CASE WHEN NEW.source = 'api' THEN 1 ELSE 0 END
  )
  ON CONFLICT (date) DO UPDATE
  SET
    events_created_today = event_stats_daily.events_created_today + 1,
    events_from_import = event_stats_daily.events_from_import +
      CASE WHEN NEW.source = 'import' THEN 1 ELSE 0 END,
    events_from_manual = event_stats_daily.events_from_manual +
      CASE WHEN NEW.source = 'manual' OR NEW.source IS NULL THEN 1 ELSE 0 END,
    events_from_api = event_stats_daily.events_from_api +
      CASE WHEN NEW.source = 'api' THEN 1 ELSE 0 END,
    updated_at = NOW();

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- FUNCIÓN: calculate_monthly_stats
-- Calcula y actualiza estadísticas mensuales
-- ==========================================
CREATE OR REPLACE FUNCTION calculate_monthly_stats(p_year INTEGER, p_month INTEGER)
RETURNS VOID AS $$
DECLARE
  v_events_by_category JSONB;
  v_events_by_province JSONB;
  v_events_by_comunidad JSONB;
BEGIN
  -- Calcular eventos por categoría
  SELECT COALESCE(jsonb_object_agg(category_name, cnt), '{}')
  INTO v_events_by_category
  FROM (
    SELECT category_name, COUNT(*) as cnt
    FROM event_archive
    WHERE EXTRACT(YEAR FROM archived_at) = p_year
      AND EXTRACT(MONTH FROM archived_at) = p_month
      AND category_name IS NOT NULL
    GROUP BY category_name
  ) sub;

  -- Calcular eventos por provincia
  SELECT COALESCE(jsonb_object_agg(province, cnt), '{}')
  INTO v_events_by_province
  FROM (
    SELECT province, COUNT(*) as cnt
    FROM event_archive
    WHERE EXTRACT(YEAR FROM archived_at) = p_year
      AND EXTRACT(MONTH FROM archived_at) = p_month
      AND province IS NOT NULL
    GROUP BY province
  ) sub;

  -- Calcular eventos por comunidad
  SELECT COALESCE(jsonb_object_agg(comunidad_autonoma, cnt), '{}')
  INTO v_events_by_comunidad
  FROM (
    SELECT comunidad_autonoma, COUNT(*) as cnt
    FROM event_archive
    WHERE EXTRACT(YEAR FROM archived_at) = p_year
      AND EXTRACT(MONTH FROM archived_at) = p_month
      AND comunidad_autonoma IS NOT NULL
    GROUP BY comunidad_autonoma
  ) sub;

  -- Insertar o actualizar estadísticas mensuales
  INSERT INTO event_stats_monthly (
    year,
    month,
    total_events_created,
    total_events_deleted,
    total_events_expired,
    events_by_category,
    events_by_province,
    events_by_comunidad,
    events_physical,
    events_online,
    events_hybrid,
    events_from_import,
    events_from_manual,
    events_from_api
  )
  SELECT
    p_year,
    p_month,
    COALESCE(SUM(events_created_today), 0),
    COALESCE(SUM(events_deleted_today), 0),
    COALESCE(SUM(events_expired_today), 0),
    v_events_by_category,
    v_events_by_province,
    v_events_by_comunidad,
    (SELECT COUNT(*) FROM event_archive
     WHERE EXTRACT(YEAR FROM archived_at) = p_year
       AND EXTRACT(MONTH FROM archived_at) = p_month
       AND location_type = 'physical'),
    (SELECT COUNT(*) FROM event_archive
     WHERE EXTRACT(YEAR FROM archived_at) = p_year
       AND EXTRACT(MONTH FROM archived_at) = p_month
       AND location_type = 'online'),
    (SELECT COUNT(*) FROM event_archive
     WHERE EXTRACT(YEAR FROM archived_at) = p_year
       AND EXTRACT(MONTH FROM archived_at) = p_month
       AND location_type = 'hybrid'),
    COALESCE(SUM(events_from_import), 0),
    COALESCE(SUM(events_from_manual), 0),
    COALESCE(SUM(events_from_api), 0)
  FROM event_stats_daily
  WHERE EXTRACT(YEAR FROM date) = p_year
    AND EXTRACT(MONTH FROM date) = p_month
  ON CONFLICT (year, month) DO UPDATE
  SET
    total_events_created = EXCLUDED.total_events_created,
    total_events_deleted = EXCLUDED.total_events_deleted,
    total_events_expired = EXCLUDED.total_events_expired,
    events_by_category = EXCLUDED.events_by_category,
    events_by_province = EXCLUDED.events_by_province,
    events_by_comunidad = EXCLUDED.events_by_comunidad,
    events_physical = EXCLUDED.events_physical,
    events_online = EXCLUDED.events_online,
    events_hybrid = EXCLUDED.events_hybrid,
    events_from_import = EXCLUDED.events_from_import,
    events_from_manual = EXCLUDED.events_from_manual,
    events_from_api = EXCLUDED.events_from_api,
    updated_at = NOW();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- VISTA: kpi_summary (resumen de KPIs)
-- ==========================================
CREATE OR REPLACE VIEW kpi_summary AS
SELECT
  -- Totales históricos
  (SELECT COUNT(*) FROM event_archive) as total_events_historico,
  (SELECT COUNT(*) FROM events) as total_events_activos,
  (SELECT COUNT(*) FROM events WHERE is_published = true) as total_events_publicados,

  -- Este mes
  (SELECT COALESCE(SUM(events_created_today), 0)
   FROM event_stats_daily
   WHERE EXTRACT(YEAR FROM date) = EXTRACT(YEAR FROM CURRENT_DATE)
     AND EXTRACT(MONTH FROM date) = EXTRACT(MONTH FROM CURRENT_DATE)
  ) as eventos_creados_este_mes,

  -- Esta semana
  (SELECT COALESCE(SUM(events_created_today), 0)
   FROM event_stats_daily
   WHERE date >= CURRENT_DATE - INTERVAL '7 days'
  ) as eventos_creados_esta_semana,

  -- Hoy
  (SELECT COALESCE(events_created_today, 0)
   FROM event_stats_daily
   WHERE date = CURRENT_DATE
  ) as eventos_creados_hoy,

  -- Expirados
  (SELECT COUNT(*) FROM event_archive WHERE deleted_reason = 'expired') as total_eventos_expirados,

  -- Por tipo de ubicación (histórico)
  (SELECT COUNT(*) FROM event_archive WHERE location_type = 'physical') as eventos_fisicos_historico,
  (SELECT COUNT(*) FROM event_archive WHERE location_type = 'online') as eventos_online_historico,
  (SELECT COUNT(*) FROM event_archive WHERE location_type = 'hybrid') as eventos_hibridos_historico,

  -- Por fuente (histórico)
  (SELECT COUNT(*) FROM event_archive WHERE source = 'import') as eventos_importados_historico,
  (SELECT COUNT(*) FROM event_archive WHERE source = 'manual' OR source IS NULL) as eventos_manuales_historico,
  (SELECT COUNT(*) FROM event_archive WHERE source = 'api') as eventos_api_historico;

-- ==========================================
-- TRIGGERS
-- ==========================================

-- Trigger para archivar evento antes de eliminar
DROP TRIGGER IF EXISTS trigger_archive_event ON events;
CREATE TRIGGER trigger_archive_event
  BEFORE DELETE ON events
  FOR EACH ROW
  EXECUTE FUNCTION archive_event_before_delete();

-- Trigger para actualizar stats al insertar
DROP TRIGGER IF EXISTS trigger_stats_on_insert ON events;
CREATE TRIGGER trigger_stats_on_insert
  AFTER INSERT ON events
  FOR EACH ROW
  EXECUTE FUNCTION update_daily_stats_on_insert();

-- ==========================================
-- RLS para las nuevas tablas
-- ==========================================
ALTER TABLE event_archive ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_stats_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_stats_monthly ENABLE ROW LEVEL SECURITY;

-- Solo admins pueden ver el archivo y estadísticas
CREATE POLICY "Admins can read event_archive" ON event_archive
  FOR SELECT USING (public.is_admin());

CREATE POLICY "Admins can read event_stats_daily" ON event_stats_daily
  FOR SELECT USING (public.is_admin());

CREATE POLICY "Admins can read event_stats_monthly" ON event_stats_monthly
  FOR SELECT USING (public.is_admin());

-- ==========================================
-- GRANT permisos a la vista
-- ==========================================
GRANT SELECT ON kpi_summary TO authenticated;

-- ==========================================
-- COMENTARIOS
-- ==========================================
COMMENT ON TABLE event_archive IS 'Archivo histórico de eventos eliminados';
COMMENT ON TABLE event_stats_daily IS 'Estadísticas diarias de eventos';
COMMENT ON TABLE event_stats_monthly IS 'Estadísticas mensuales agregadas';
COMMENT ON VIEW kpi_summary IS 'Resumen de KPIs principales de eventos';
COMMENT ON FUNCTION archive_event_before_delete() IS 'Archiva evento antes de eliminarlo';
COMMENT ON FUNCTION update_daily_stats_on_insert() IS 'Actualiza estadísticas diarias al crear evento';
COMMENT ON FUNCTION calculate_monthly_stats(INTEGER, INTEGER) IS 'Calcula estadísticas mensuales';
-- ============================================================
-- MIGRACIÓN: Corregir trigger de archivado (v2)
-- Fecha: 2024-12-26
--
-- Correcciones:
-- 1. Eliminar JOINs a tablas 'provincias' y 'comunidades_autonomas'
-- 2. Eliminar referencias a campos 'source' y 'external_id' que no existen en events
-- ============================================================

-- ==========================================
-- FUNCIÓN CORREGIDA: archive_event_before_delete
-- Archiva el evento antes de eliminarlo
-- ==========================================
CREATE OR REPLACE FUNCTION archive_event_before_delete()
RETURNS TRIGGER AS $$
DECLARE
  v_category_name TEXT;
  v_tags TEXT[];
  v_calendar_ids UUID[];
  v_calendar_names TEXT[];
  v_location_type TEXT;
  v_venue_name TEXT;
  v_address TEXT;
  v_city TEXT;
  v_province TEXT;
  v_comunidad TEXT;
  v_organizer_name TEXT;
  v_organizer_type TEXT;
BEGIN
  -- Obtener nombre de categoría
  SELECT name INTO v_category_name
  FROM categories WHERE id = OLD.category_id;

  -- Obtener tags
  SELECT ARRAY_AGG(t.name) INTO v_tags
  FROM event_tags et
  JOIN tags t ON t.id = et.tag_id
  WHERE et.event_id = OLD.id;

  -- Obtener calendarios
  SELECT ARRAY_AGG(ec.calendar_id), ARRAY_AGG(c.name)
  INTO v_calendar_ids, v_calendar_names
  FROM event_calendars ec
  JOIN calendars c ON c.id = ec.calendar_id
  WHERE ec.event_id = OLD.id;

  -- Obtener ubicación - usar campos TEXT directamente
  SELECT
    el.name,
    el.address,
    el.city,
    el.province,
    el.comunidad_autonoma
  INTO v_venue_name, v_address, v_city, v_province, v_comunidad
  FROM event_locations el
  WHERE el.event_id = OLD.id
  LIMIT 1;

  -- Determinar tipo de ubicación
  IF EXISTS (SELECT 1 FROM event_online WHERE event_id = OLD.id) THEN
    IF v_venue_name IS NOT NULL THEN
      v_location_type := 'hybrid';
    ELSE
      v_location_type := 'online';
    END IF;
  ELSE
    v_location_type := 'physical';
  END IF;

  -- Obtener organizador
  SELECT name, type INTO v_organizer_name, v_organizer_type
  FROM event_organizers
  WHERE event_id = OLD.id
  LIMIT 1;

  -- Insertar en archivo (sin source ni external_id que no existen en events)
  INSERT INTO event_archive (
    original_event_id,
    title,
    description,
    category_id,
    category_name,
    start_date,
    end_date,
    start_time,
    end_time,
    location_type,
    venue_name,
    address,
    city,
    province,
    comunidad_autonoma,
    organizer_name,
    organizer_type,
    is_published,
    is_featured,
    tags,
    calendar_ids,
    calendar_names,
    original_created_at,
    original_updated_at,
    deleted_reason,
    created_by
  ) VALUES (
    OLD.id,
    OLD.title,
    OLD.description,
    OLD.category_id,
    v_category_name,
    OLD.start_date,
    OLD.end_date,
    OLD.start_time,
    OLD.end_time,
    v_location_type,
    v_venue_name,
    v_address,
    v_city,
    v_province,
    v_comunidad,
    v_organizer_name,
    v_organizer_type,
    OLD.is_published,
    OLD.is_featured,
    v_tags,
    v_calendar_ids,
    v_calendar_names,
    OLD.created_at,
    OLD.updated_at,
    CASE
      WHEN OLD.end_date IS NOT NULL AND OLD.end_date < CURRENT_DATE - INTERVAL '7 days' THEN 'expired'
      ELSE 'manual'
    END,
    OLD.created_by
  );

  -- Actualizar estadísticas diarias
  INSERT INTO event_stats_daily (date, events_deleted_today)
  VALUES (CURRENT_DATE, 1)
  ON CONFLICT (date) DO UPDATE
  SET events_deleted_today = event_stats_daily.events_deleted_today + 1,
      updated_at = NOW();

  -- Si es por expiración, también contar
  IF OLD.end_date IS NOT NULL AND OLD.end_date < CURRENT_DATE - INTERVAL '7 days' THEN
    UPDATE event_stats_daily
    SET events_expired_today = events_expired_today + 1
    WHERE date = CURRENT_DATE;
  END IF;

  RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Recrear el trigger
DROP TRIGGER IF EXISTS trigger_archive_event ON events;
CREATE TRIGGER trigger_archive_event
  BEFORE DELETE ON events
  FOR EACH ROW
  EXECUTE FUNCTION archive_event_before_delete();

-- También corregir el trigger de insert que referencia source
CREATE OR REPLACE FUNCTION update_daily_stats_on_insert()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO event_stats_daily (
    date,
    events_created_today
  )
  VALUES (
    CURRENT_DATE,
    1
  )
  ON CONFLICT (date) DO UPDATE
  SET
    events_created_today = event_stats_daily.events_created_today + 1,
    updated_at = NOW();

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- COMENTARIOS
-- ==========================================
COMMENT ON FUNCTION archive_event_before_delete() IS 'Archiva evento antes de eliminarlo (v3 - sin campos source/external_id)';
COMMENT ON FUNCTION update_daily_stats_on_insert() IS 'Actualiza estadísticas diarias al crear evento (v2 - sin campo source)';
-- ============================================================
-- MIGRACIÓN: Corregir trigger de archivado (v3)
-- Fecha: 2024-12-26
--
-- Correcciones:
-- 1. Eliminar JOINs a tablas 'provincias' y 'comunidades_autonomas'
-- 2. Eliminar referencias a campos 'source' y 'external_id' que no existen en events
-- ============================================================

-- ==========================================
-- FUNCIÓN CORREGIDA: archive_event_before_delete
-- Archiva el evento antes de eliminarlo
-- ==========================================
CREATE OR REPLACE FUNCTION archive_event_before_delete()
RETURNS TRIGGER AS $$
DECLARE
  v_category_name TEXT;
  v_tags TEXT[];
  v_calendar_ids UUID[];
  v_calendar_names TEXT[];
  v_location_type TEXT;
  v_venue_name TEXT;
  v_address TEXT;
  v_city TEXT;
  v_province TEXT;
  v_comunidad TEXT;
  v_organizer_name TEXT;
  v_organizer_type TEXT;
BEGIN
  -- Obtener nombre de categoría
  SELECT name INTO v_category_name
  FROM categories WHERE id = OLD.category_id;

  -- Obtener tags
  SELECT ARRAY_AGG(t.name) INTO v_tags
  FROM event_tags et
  JOIN tags t ON t.id = et.tag_id
  WHERE et.event_id = OLD.id;

  -- Obtener calendarios
  SELECT ARRAY_AGG(ec.calendar_id), ARRAY_AGG(c.name)
  INTO v_calendar_ids, v_calendar_names
  FROM event_calendars ec
  JOIN calendars c ON c.id = ec.calendar_id
  WHERE ec.event_id = OLD.id;

  -- Obtener ubicación - usar campos TEXT directamente
  SELECT
    el.name,
    el.address,
    el.city,
    el.province,
    el.comunidad_autonoma
  INTO v_venue_name, v_address, v_city, v_province, v_comunidad
  FROM event_locations el
  WHERE el.event_id = OLD.id
  LIMIT 1;

  -- Determinar tipo de ubicación
  IF EXISTS (SELECT 1 FROM event_online WHERE event_id = OLD.id) THEN
    IF v_venue_name IS NOT NULL THEN
      v_location_type := 'hybrid';
    ELSE
      v_location_type := 'online';
    END IF;
  ELSE
    v_location_type := 'physical';
  END IF;

  -- Obtener organizador
  SELECT name, type INTO v_organizer_name, v_organizer_type
  FROM event_organizers
  WHERE event_id = OLD.id
  LIMIT 1;

  -- Insertar en archivo (sin source ni external_id que no existen en events)
  INSERT INTO event_archive (
    original_event_id,
    title,
    description,
    category_id,
    category_name,
    start_date,
    end_date,
    start_time,
    end_time,
    location_type,
    venue_name,
    address,
    city,
    province,
    comunidad_autonoma,
    organizer_name,
    organizer_type,
    is_published,
    is_featured,
    tags,
    calendar_ids,
    calendar_names,
    original_created_at,
    original_updated_at,
    deleted_reason,
    created_by
  ) VALUES (
    OLD.id,
    OLD.title,
    OLD.description,
    OLD.category_id,
    v_category_name,
    OLD.start_date,
    OLD.end_date,
    OLD.start_time,
    OLD.end_time,
    v_location_type,
    v_venue_name,
    v_address,
    v_city,
    v_province,
    v_comunidad,
    v_organizer_name,
    v_organizer_type,
    OLD.is_published,
    OLD.is_featured,
    v_tags,
    v_calendar_ids,
    v_calendar_names,
    OLD.created_at,
    OLD.updated_at,
    CASE
      WHEN OLD.end_date IS NOT NULL AND OLD.end_date < CURRENT_DATE - INTERVAL '7 days' THEN 'expired'
      ELSE 'manual'
    END,
    OLD.created_by
  );

  -- Actualizar estadísticas diarias
  INSERT INTO event_stats_daily (date, events_deleted_today)
  VALUES (CURRENT_DATE, 1)
  ON CONFLICT (date) DO UPDATE
  SET events_deleted_today = event_stats_daily.events_deleted_today + 1,
      updated_at = NOW();

  -- Si es por expiración, también contar
  IF OLD.end_date IS NOT NULL AND OLD.end_date < CURRENT_DATE - INTERVAL '7 days' THEN
    UPDATE event_stats_daily
    SET events_expired_today = events_expired_today + 1
    WHERE date = CURRENT_DATE;
  END IF;

  RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Recrear el trigger
DROP TRIGGER IF EXISTS trigger_archive_event ON events;
CREATE TRIGGER trigger_archive_event
  BEFORE DELETE ON events
  FOR EACH ROW
  EXECUTE FUNCTION archive_event_before_delete();

-- También corregir el trigger de insert que referencia source
CREATE OR REPLACE FUNCTION update_daily_stats_on_insert()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO event_stats_daily (
    date,
    events_created_today
  )
  VALUES (
    CURRENT_DATE,
    1
  )
  ON CONFLICT (date) DO UPDATE
  SET
    events_created_today = event_stats_daily.events_created_today + 1,
    updated_at = NOW();

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- COMENTARIOS
-- ==========================================
COMMENT ON FUNCTION archive_event_before_delete() IS 'Archiva evento antes de eliminarlo (v3 - sin campos source/external_id)';
COMMENT ON FUNCTION update_daily_stats_on_insert() IS 'Actualiza estadísticas diarias al crear evento (v2 - sin campo source)';
-- ============================================================
-- MIGRACIÓN CONSOLIDADA: Políticas RLS para panel de administración
-- Fecha: 2024-12-29
--
-- Esta migración reemplaza y consolida todas las políticas RLS anteriores
-- para evitar conflictos y garantizar que el CRUD funcione correctamente.
--
-- PRINCIPIO: Cualquier usuario autenticado puede realizar CRUD completo
-- en el panel de administración. La protección de acceso al panel se
-- hace a nivel de aplicación (middleware/auth).
-- ============================================================

-- ==========================================
-- FUNCIONES AUXILIARES (mantener para compatibilidad)
-- ==========================================
CREATE OR REPLACE FUNCTION public.is_authenticated()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN auth.uid() IS NOT NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- TABLA: categories
-- ==========================================
ALTER TABLE IF EXISTS categories ENABLE ROW LEVEL SECURITY;

-- Eliminar TODAS las políticas existentes
DROP POLICY IF EXISTS "Public read categories" ON categories;
DROP POLICY IF EXISTS "Authenticated insert categories" ON categories;
DROP POLICY IF EXISTS "Authenticated update categories" ON categories;
DROP POLICY IF EXISTS "Authenticated delete categories" ON categories;
DROP POLICY IF EXISTS "Admins can insert categories" ON categories;
DROP POLICY IF EXISTS "Admins can update categories" ON categories;
DROP POLICY IF EXISTS "Admins can delete categories" ON categories;
DROP POLICY IF EXISTS "Authenticated can insert categories" ON categories;

-- Crear políticas limpias
CREATE POLICY "Anyone can read categories" ON categories
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert categories" ON categories
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update categories" ON categories
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete categories" ON categories
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: tags
-- ==========================================
ALTER TABLE IF EXISTS tags ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read tags" ON tags;
DROP POLICY IF EXISTS "Authenticated insert tags" ON tags;
DROP POLICY IF EXISTS "Authenticated update tags" ON tags;
DROP POLICY IF EXISTS "Authenticated delete tags" ON tags;
DROP POLICY IF EXISTS "Staff can insert tags" ON tags;
DROP POLICY IF EXISTS "Staff can update tags" ON tags;
DROP POLICY IF EXISTS "Admins can delete tags" ON tags;
DROP POLICY IF EXISTS "Authenticated can insert tags" ON tags;

CREATE POLICY "Anyone can read tags" ON tags
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert tags" ON tags
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update tags" ON tags
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete tags" ON tags
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: calendars
-- ==========================================
ALTER TABLE IF EXISTS calendars ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read calendars" ON calendars;
DROP POLICY IF EXISTS "Authenticated insert calendars" ON calendars;
DROP POLICY IF EXISTS "Authenticated update calendars" ON calendars;
DROP POLICY IF EXISTS "Authenticated delete calendars" ON calendars;
DROP POLICY IF EXISTS "Admins can insert calendars" ON calendars;
DROP POLICY IF EXISTS "Admins can update calendars" ON calendars;
DROP POLICY IF EXISTS "Admins can delete calendars" ON calendars;

CREATE POLICY "Anyone can read calendars" ON calendars
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert calendars" ON calendars
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update calendars" ON calendars
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete calendars" ON calendars
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: events
-- ==========================================
ALTER TABLE IF EXISTS events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read events" ON events;
DROP POLICY IF EXISTS "Public read published events" ON events;
DROP POLICY IF EXISTS "Staff can read all events" ON events;
DROP POLICY IF EXISTS "Authenticated insert events" ON events;
DROP POLICY IF EXISTS "Authenticated update events" ON events;
DROP POLICY IF EXISTS "Authenticated delete events" ON events;
DROP POLICY IF EXISTS "Staff can insert events" ON events;
DROP POLICY IF EXISTS "Staff can update events" ON events;
DROP POLICY IF EXISTS "Admins can delete events" ON events;
DROP POLICY IF EXISTS "Moderators can insert events" ON events;
DROP POLICY IF EXISTS "Moderators can update events" ON events;
DROP POLICY IF EXISTS "Authenticated can insert events" ON events;

CREATE POLICY "Anyone can read events" ON events
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert events" ON events
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update events" ON events
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete events" ON events
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_calendars
-- ==========================================
ALTER TABLE IF EXISTS event_calendars ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated insert event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated update event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated delete event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Staff can insert event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Staff can update event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Staff can delete event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated can insert event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated can delete event_calendars" ON event_calendars;

CREATE POLICY "Anyone can read event_calendars" ON event_calendars
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert event_calendars" ON event_calendars
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update event_calendars" ON event_calendars
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete event_calendars" ON event_calendars
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_tags
-- ==========================================
ALTER TABLE IF EXISTS event_tags ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated insert event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated update event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated delete event_tags" ON event_tags;
DROP POLICY IF EXISTS "Staff can insert event_tags" ON event_tags;
DROP POLICY IF EXISTS "Staff can update event_tags" ON event_tags;
DROP POLICY IF EXISTS "Staff can delete event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated can insert event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated can delete event_tags" ON event_tags;

CREATE POLICY "Anyone can read event_tags" ON event_tags
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert event_tags" ON event_tags
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update event_tags" ON event_tags
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete event_tags" ON event_tags
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_locations
-- ==========================================
ALTER TABLE IF EXISTS event_locations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated insert event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated update event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated delete event_locations" ON event_locations;
DROP POLICY IF EXISTS "Staff can insert event_locations" ON event_locations;
DROP POLICY IF EXISTS "Staff can update event_locations" ON event_locations;
DROP POLICY IF EXISTS "Staff can delete event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated can insert event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated can delete event_locations" ON event_locations;

CREATE POLICY "Anyone can read event_locations" ON event_locations
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert event_locations" ON event_locations
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update event_locations" ON event_locations
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete event_locations" ON event_locations
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_online
-- ==========================================
ALTER TABLE IF EXISTS event_online ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated insert event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated update event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated delete event_online" ON event_online;
DROP POLICY IF EXISTS "Staff can insert event_online" ON event_online;
DROP POLICY IF EXISTS "Staff can update event_online" ON event_online;
DROP POLICY IF EXISTS "Staff can delete event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated can insert event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated can delete event_online" ON event_online;

CREATE POLICY "Anyone can read event_online" ON event_online
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert event_online" ON event_online
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update event_online" ON event_online
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete event_online" ON event_online
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_organizers
-- ==========================================
ALTER TABLE IF EXISTS event_organizers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated insert event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated update event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated delete event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Staff can insert event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Staff can update event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Staff can delete event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated can insert event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated can delete event_organizers" ON event_organizers;

CREATE POLICY "Anyone can read event_organizers" ON event_organizers
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert event_organizers" ON event_organizers
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update event_organizers" ON event_organizers
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete event_organizers" ON event_organizers
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_contact
-- ==========================================
ALTER TABLE IF EXISTS event_contact ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated insert event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated update event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated delete event_contact" ON event_contact;
DROP POLICY IF EXISTS "Staff can insert event_contact" ON event_contact;
DROP POLICY IF EXISTS "Staff can update event_contact" ON event_contact;
DROP POLICY IF EXISTS "Staff can delete event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated can insert event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated can delete event_contact" ON event_contact;

CREATE POLICY "Anyone can read event_contact" ON event_contact
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert event_contact" ON event_contact
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update event_contact" ON event_contact
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete event_contact" ON event_contact
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_registration
-- ==========================================
ALTER TABLE IF EXISTS event_registration ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated insert event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated update event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated delete event_registration" ON event_registration;
DROP POLICY IF EXISTS "Staff can insert event_registration" ON event_registration;
DROP POLICY IF EXISTS "Staff can update event_registration" ON event_registration;
DROP POLICY IF EXISTS "Staff can delete event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated can insert event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated can delete event_registration" ON event_registration;

CREATE POLICY "Anyone can read event_registration" ON event_registration
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert event_registration" ON event_registration
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update event_registration" ON event_registration
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete event_registration" ON event_registration
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_accessibility
-- ==========================================
ALTER TABLE IF EXISTS event_accessibility ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated insert event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated update event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated delete event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Staff can insert event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Staff can update event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Staff can delete event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated can insert event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated can delete event_accessibility" ON event_accessibility;

CREATE POLICY "Anyone can read event_accessibility" ON event_accessibility
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert event_accessibility" ON event_accessibility
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update event_accessibility" ON event_accessibility
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete event_accessibility" ON event_accessibility
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_resources
-- ==========================================
ALTER TABLE IF EXISTS event_resources ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated insert event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated update event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated delete event_resources" ON event_resources;
DROP POLICY IF EXISTS "Staff can insert event_resources" ON event_resources;
DROP POLICY IF EXISTS "Staff can update event_resources" ON event_resources;
DROP POLICY IF EXISTS "Staff can delete event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated can insert event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated can delete event_resources" ON event_resources;

CREATE POLICY "Anyone can read event_resources" ON event_resources
  FOR SELECT USING (true);

CREATE POLICY "Authenticated can insert event_resources" ON event_resources
  FOR INSERT TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated can update event_resources" ON event_resources
  FOR UPDATE TO authenticated
  USING (true) WITH CHECK (true);

CREATE POLICY "Authenticated can delete event_resources" ON event_resources
  FOR DELETE TO authenticated
  USING (true);

-- ==========================================
-- TABLA: event_stats_daily (para triggers)
-- ==========================================
ALTER TABLE IF EXISTS event_stats_daily ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Trigger can insert event_stats_daily" ON event_stats_daily;
DROP POLICY IF EXISTS "Service role insert event_stats_daily" ON event_stats_daily;
DROP POLICY IF EXISTS "System can insert event_stats_daily" ON event_stats_daily;
DROP POLICY IF EXISTS "Anyone can read event_stats_daily" ON event_stats_daily;

CREATE POLICY "Anyone can read event_stats_daily" ON event_stats_daily
  FOR SELECT USING (true);

CREATE POLICY "System can insert event_stats_daily" ON event_stats_daily
  FOR INSERT
  WITH CHECK (true);

CREATE POLICY "System can update event_stats_daily" ON event_stats_daily
  FOR UPDATE
  USING (true) WITH CHECK (true);

-- ==========================================
-- TABLA: event_archive (para triggers)
-- ==========================================
ALTER TABLE IF EXISTS event_archive ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Trigger can insert event_archive" ON event_archive;
DROP POLICY IF EXISTS "System can insert event_archive" ON event_archive;
DROP POLICY IF EXISTS "Anyone can read event_archive" ON event_archive;

CREATE POLICY "Anyone can read event_archive" ON event_archive
  FOR SELECT USING (true);

CREATE POLICY "System can insert event_archive" ON event_archive
  FOR INSERT
  WITH CHECK (true);

-- ==========================================
-- TABLA: users (mantener restricciones)
-- ==========================================
ALTER TABLE IF EXISTS users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can read own profile" ON users;
DROP POLICY IF EXISTS "Users can update own profile" ON users;
DROP POLICY IF EXISTS "Admins can read all users" ON users;
DROP POLICY IF EXISTS "Admins can update all users" ON users;
DROP POLICY IF EXISTS "Admins can delete users" ON users;
DROP POLICY IF EXISTS "Authenticated can read users" ON users;

-- Cualquier autenticado puede leer usuarios (necesario para verificar roles, etc.)
CREATE POLICY "Authenticated can read users" ON users
  FOR SELECT TO authenticated
  USING (true);

-- Solo el propio usuario puede actualizar su perfil (excepto el rol)
CREATE POLICY "Users can update own profile" ON users
  FOR UPDATE TO authenticated
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

-- ==========================================
-- TABLAS ADICIONALES QUE PUEDAN EXISTIR
-- ==========================================

-- user_saved_events
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_saved_events') THEN
    ALTER TABLE user_saved_events ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "Users can manage own saved events" ON user_saved_events;
    DROP POLICY IF EXISTS "Authenticated can read user_saved_events" ON user_saved_events;
    DROP POLICY IF EXISTS "Authenticated can insert user_saved_events" ON user_saved_events;
    DROP POLICY IF EXISTS "Authenticated can delete user_saved_events" ON user_saved_events;

    CREATE POLICY "Authenticated can read user_saved_events" ON user_saved_events
      FOR SELECT TO authenticated USING (true);
    CREATE POLICY "Authenticated can insert user_saved_events" ON user_saved_events
      FOR INSERT TO authenticated WITH CHECK (true);
    CREATE POLICY "Authenticated can delete user_saved_events" ON user_saved_events
      FOR DELETE TO authenticated USING (true);
  END IF;
END $$;

-- reminders
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'reminders') THEN
    ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "Authenticated can read reminders" ON reminders;
    DROP POLICY IF EXISTS "Authenticated can insert reminders" ON reminders;
    DROP POLICY IF EXISTS "Authenticated can delete reminders" ON reminders;

    CREATE POLICY "Authenticated can read reminders" ON reminders
      FOR SELECT TO authenticated USING (true);
    CREATE POLICY "Authenticated can insert reminders" ON reminders
      FOR INSERT TO authenticated WITH CHECK (true);
    CREATE POLICY "Authenticated can delete reminders" ON reminders
      FOR DELETE TO authenticated USING (true);
  END IF;
END $$;

-- event_invitations
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'event_invitations') THEN
    ALTER TABLE event_invitations ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "Authenticated can read event_invitations" ON event_invitations;
    DROP POLICY IF EXISTS "Authenticated can insert event_invitations" ON event_invitations;
    DROP POLICY IF EXISTS "Authenticated can delete event_invitations" ON event_invitations;

    CREATE POLICY "Authenticated can read event_invitations" ON event_invitations
      FOR SELECT TO authenticated USING (true);
    CREATE POLICY "Authenticated can insert event_invitations" ON event_invitations
      FOR INSERT TO authenticated WITH CHECK (true);
    CREATE POLICY "Authenticated can delete event_invitations" ON event_invitations
      FOR DELETE TO authenticated USING (true);
  END IF;
END $$;

-- ==========================================
-- COMENTARIOS
-- ==========================================
COMMENT ON POLICY "Anyone can read categories" ON categories IS 'Lectura pública de categorías';
COMMENT ON POLICY "Authenticated can insert categories" ON categories IS 'Usuarios autenticados pueden crear categorías';
COMMENT ON POLICY "Authenticated can update categories" ON categories IS 'Usuarios autenticados pueden actualizar categorías';
COMMENT ON POLICY "Authenticated can delete categories" ON categories IS 'Usuarios autenticados pueden eliminar categorías';
-- Tabla de logs de auditoría para acciones de administradores
CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  user_email TEXT,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT,
  entity_name TEXT,
  details JSONB,
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para búsquedas eficientes
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_entity_type ON audit_logs(entity_type);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- RLS: Solo admins pueden ver los logs
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can view audit logs"
  ON audit_logs FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND users.role IN ('admin', 'superadmin')
    )
  );

CREATE POLICY "System can insert audit logs"
  ON audit_logs FOR INSERT
  TO authenticated
  WITH CHECK (true);

-- Comentarios
COMMENT ON TABLE audit_logs IS 'Registro de auditoría de acciones administrativas';
COMMENT ON COLUMN audit_logs.action IS 'Tipo de acción: create, update, delete, login, etc.';
COMMENT ON COLUMN audit_logs.entity_type IS 'Tipo de entidad: event, user, category, tag, calendar, etc.';
COMMENT ON COLUMN audit_logs.entity_id IS 'ID de la entidad afectada';
COMMENT ON COLUMN audit_logs.entity_name IS 'Nombre/título de la entidad para referencia rápida';
COMMENT ON COLUMN audit_logs.details IS 'Detalles adicionales en JSON (cambios, valores anteriores, etc.)';
-- Migración: Eventos personales del usuario
-- Fecha: 2024-12-30
-- Descripción: Permite a los usuarios crear sus propios eventos privados en sus calendarios

-- ============================================================================
-- 1. TABLA PRINCIPAL: user_personal_events
-- ============================================================================
-- Diseño normalizado: Solo campos esenciales para eventos personales
-- Los eventos públicos usan la tabla 'events' con todas sus relaciones complejas
-- Los eventos personales son más simples pero el usuario tiene control total

CREATE TABLE IF NOT EXISTS user_personal_events (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,

  -- Relaciones
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  calendar_id UUID NOT NULL REFERENCES calendars(id) ON DELETE CASCADE,

  -- Datos del evento
  title VARCHAR(200) NOT NULL,
  description TEXT,

  -- Fechas y horarios
  start_date DATE NOT NULL,
  end_date DATE,  -- NULL = mismo día que start_date
  start_time TIME,  -- NULL = todo el día
  end_time TIME,
  all_day BOOLEAN DEFAULT false,

  -- Ubicación (simplificada - solo texto libre)
  location_name VARCHAR(200),
  location_address TEXT,

  -- Personalización
  color VARCHAR(7),  -- Hex color, si NULL usa el del calendario

  -- Recordatorio
  reminder_minutes INTEGER,  -- NULL = sin recordatorio, ej: 30, 60, 1440 (1 día)

  -- Metadatos
  notes TEXT,  -- Notas privadas del usuario
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

  -- Constraints
  CONSTRAINT valid_dates CHECK (end_date IS NULL OR end_date >= start_date),
  CONSTRAINT valid_times CHECK (
    (all_day = true AND start_time IS NULL AND end_time IS NULL) OR
    (all_day = false)
  ),
  CONSTRAINT valid_color CHECK (color IS NULL OR color ~ '^#[0-9A-Fa-f]{6}$')
);

-- ============================================================================
-- 2. ÍNDICES PARA RENDIMIENTO
-- ============================================================================

-- Índice principal: usuario + calendario para listar eventos
CREATE INDEX IF NOT EXISTS idx_user_personal_events_user_calendar
  ON user_personal_events(user_id, calendar_id);

-- Índice para búsquedas por fecha (crucial para vistas de calendario)
CREATE INDEX IF NOT EXISTS idx_user_personal_events_dates
  ON user_personal_events(start_date, end_date);

-- Índice para ordenar por fecha de creación
CREATE INDEX IF NOT EXISTS idx_user_personal_events_created
  ON user_personal_events(created_at DESC);

-- Índice compuesto para consultas típicas: mis eventos de un calendario en un rango de fechas
CREATE INDEX IF NOT EXISTS idx_user_personal_events_calendar_dates
  ON user_personal_events(calendar_id, start_date, end_date);

-- ============================================================================
-- 3. TRIGGER PARA updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION update_user_personal_events_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_user_personal_events_updated_at ON user_personal_events;
CREATE TRIGGER trigger_user_personal_events_updated_at
  BEFORE UPDATE ON user_personal_events
  FOR EACH ROW
  EXECUTE FUNCTION update_user_personal_events_updated_at();

-- ============================================================================
-- 4. ROW LEVEL SECURITY (RLS)
-- ============================================================================

ALTER TABLE user_personal_events ENABLE ROW LEVEL SECURITY;

-- Política: Los usuarios solo pueden ver sus propios eventos
CREATE POLICY "Users can view own personal events"
  ON user_personal_events
  FOR SELECT
  USING (auth.uid() = user_id);

-- Política: Los usuarios solo pueden crear eventos en sus propios calendarios
CREATE POLICY "Users can create personal events in own calendars"
  ON user_personal_events
  FOR INSERT
  WITH CHECK (
    auth.uid() = user_id AND
    EXISTS (
      SELECT 1 FROM calendars
      WHERE calendars.id = calendar_id
      AND calendars.user_id = auth.uid()
    )
  );

-- Política: Los usuarios solo pueden actualizar sus propios eventos
CREATE POLICY "Users can update own personal events"
  ON user_personal_events
  FOR UPDATE
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Política: Los usuarios solo pueden eliminar sus propios eventos
CREATE POLICY "Users can delete own personal events"
  ON user_personal_events
  FOR DELETE
  USING (auth.uid() = user_id);

-- ============================================================================
-- 5. COMENTARIOS PARA DOCUMENTACIÓN
-- ============================================================================

COMMENT ON TABLE user_personal_events IS 'Eventos personales creados por usuarios en sus calendarios privados';
COMMENT ON COLUMN user_personal_events.user_id IS 'Usuario propietario del evento';
COMMENT ON COLUMN user_personal_events.calendar_id IS 'Calendario donde está el evento';
COMMENT ON COLUMN user_personal_events.start_date IS 'Fecha de inicio (requerida)';
COMMENT ON COLUMN user_personal_events.end_date IS 'Fecha de fin (NULL = mismo día)';
COMMENT ON COLUMN user_personal_events.all_day IS 'Si es true, start_time y end_time deben ser NULL';
COMMENT ON COLUMN user_personal_events.color IS 'Color hex para el evento, si NULL usa color del calendario';
COMMENT ON COLUMN user_personal_events.reminder_minutes IS 'Minutos antes del evento para recordatorio (NULL = sin recordatorio)';
-- ============================================================================
-- Tabla de preferencias de usuario - Añadir columnas faltantes
-- ============================================================================

-- Añadir columnas si no existen
ALTER TABLE public.user_preferences
  ADD COLUMN IF NOT EXISTS default_calendar_view TEXT NOT NULL DEFAULT 'month',
  ADD COLUMN IF NOT EXISTS week_start_day TEXT NOT NULL DEFAULT 'monday',
  ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS push_notifications BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS default_reminder_minutes INTEGER DEFAULT 60;

-- Añadir constraint para default_calendar_view si no existe
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'user_preferences_default_calendar_view_check'
  ) THEN
    ALTER TABLE public.user_preferences
      ADD CONSTRAINT user_preferences_default_calendar_view_check
      CHECK (default_calendar_view IN ('month', 'week', 'day'));
  END IF;
END $$;

-- Añadir constraint para week_start_day si no existe
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'user_preferences_week_start_day_check'
  ) THEN
    ALTER TABLE public.user_preferences
      ADD CONSTRAINT user_preferences_week_start_day_check
      CHECK (week_start_day IN ('monday', 'sunday'));
  END IF;
END $$;
-- ============================================================
-- MIGRACIÓN: Políticas RLS para notificaciones y Realtime
-- Fecha: 2025-01-22
--
-- Habilita RLS en la tabla notifications y configura permisos
-- para que los usuarios solo puedan ver/modificar sus propias
-- notificaciones. También habilita Realtime para la tabla.
-- ============================================================

-- Habilitar RLS en notifications
ALTER TABLE IF EXISTS notifications ENABLE ROW LEVEL SECURITY;

-- Eliminar políticas existentes si las hay
DROP POLICY IF EXISTS "Users can view own notifications" ON notifications;
DROP POLICY IF EXISTS "Users can update own notifications" ON notifications;
DROP POLICY IF EXISTS "Users can delete own notifications" ON notifications;
DROP POLICY IF EXISTS "System can insert notifications" ON notifications;

-- Política: Los usuarios solo pueden ver sus propias notificaciones
CREATE POLICY "Users can view own notifications" ON notifications
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

-- Política: Los usuarios solo pueden actualizar sus propias notificaciones
-- (para marcar como leídas)
CREATE POLICY "Users can update own notifications" ON notifications
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Política: Los usuarios solo pueden eliminar sus propias notificaciones
CREATE POLICY "Users can delete own notifications" ON notifications
  FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

-- Política: El sistema puede insertar notificaciones para cualquier usuario
-- (necesario para triggers y funciones del sistema)
CREATE POLICY "System can insert notifications" ON notifications
  FOR INSERT
  WITH CHECK (true);

-- Habilitar Realtime para la tabla notifications
-- Nota: Esto se hace desde el dashboard de Supabase o con:
ALTER PUBLICATION supabase_realtime ADD TABLE notifications;

-- Comentarios
COMMENT ON POLICY "Users can view own notifications" ON notifications IS 'Usuarios solo ven sus notificaciones';
COMMENT ON POLICY "Users can update own notifications" ON notifications IS 'Usuarios solo actualizan sus notificaciones';
COMMENT ON POLICY "Users can delete own notifications" ON notifications IS 'Usuarios solo eliminan sus notificaciones';
COMMENT ON POLICY "System can insert notifications" ON notifications IS 'Sistema puede crear notificaciones';
-- ============================================================================
-- MIGRACIÓN: Sistema de notificaciones automáticas
-- Fecha: 2025-01-24
--
-- Incluye:
-- 1. Campo preferred_categories en user_preferences
-- 2. Trigger: notificar usuarios cuando un evento se actualiza
-- 3. Trigger: notificar usuarios cuando un evento se cancela
-- 4. Trigger: notificar usuarios cuando se crea evento en categoría de interés
-- ============================================================================

-- ===========================================
-- 1. AÑADIR CAMPO DE CATEGORÍAS PREFERIDAS
-- ===========================================

ALTER TABLE public.user_preferences
ADD COLUMN IF NOT EXISTS preferred_categories TEXT[] DEFAULT '{}';

COMMENT ON COLUMN public.user_preferences.preferred_categories IS
'Array de IDs de categorías de interés para el usuario';

-- Crear índice GIN para búsquedas eficientes en el array
CREATE INDEX IF NOT EXISTS idx_user_preferences_categories
ON public.user_preferences USING GIN (preferred_categories);

-- ===========================================
-- 2. FUNCIÓN: Notificar cuando evento se actualiza
-- ===========================================

CREATE OR REPLACE FUNCTION notify_event_updated()
RETURNS TRIGGER AS $$
DECLARE
  changes_made TEXT := '';
BEGIN
  -- Solo notificar si hay cambios relevantes y el evento está publicado
  IF NEW.is_published = true AND (
     (OLD.start_date IS DISTINCT FROM NEW.start_date) OR
     (OLD.end_date IS DISTINCT FROM NEW.end_date) OR
     (OLD.start_time IS DISTINCT FROM NEW.start_time) OR
     (OLD.end_time IS DISTINCT FROM NEW.end_time)
  ) THEN

    changes_made := 'fecha/hora';

    -- Insertar notificación para usuarios que tienen el evento guardado
    INSERT INTO public.notifications (user_id, type, title, message, action_url, reference_id, reference_type)
    SELECT
      use.user_id,
      'update'::notification_type,
      'Evento actualizado',
      'El evento "' || NEW.title || '" ha cambiado su ' || changes_made,
      '/eventos/' || NEW.slug,
      NEW.id::text,
      'event'
    FROM public.user_saved_events use
    WHERE use.event_id = NEW.id;

  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Crear trigger para actualizaciones
DROP TRIGGER IF EXISTS trigger_event_updated ON public.events;
CREATE TRIGGER trigger_event_updated
  AFTER UPDATE ON public.events
  FOR EACH ROW
  EXECUTE FUNCTION notify_event_updated();

-- ===========================================
-- 3. FUNCIÓN: Notificar cuando evento se cancela
-- ===========================================

CREATE OR REPLACE FUNCTION notify_event_cancelled()
RETURNS TRIGGER AS $$
BEGIN
  -- Solo notificar si cambia de no cancelado a cancelado
  IF OLD.is_cancelled IS DISTINCT FROM NEW.is_cancelled AND NEW.is_cancelled = true THEN

    -- Insertar notificación para usuarios que tienen el evento guardado
    INSERT INTO public.notifications (user_id, type, title, message, action_url, reference_id, reference_type)
    SELECT
      use.user_id,
      'system'::notification_type,
      'Evento cancelado',
      'El evento "' || NEW.title || '" ha sido cancelado' ||
      CASE WHEN NEW.cancellation_reason IS NOT NULL AND NEW.cancellation_reason != ''
        THEN ': ' || NEW.cancellation_reason
        ELSE ''
      END,
      '/eventos/' || NEW.slug,
      NEW.id::text,
      'event'
    FROM public.user_saved_events use
    WHERE use.event_id = NEW.id;

  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Crear trigger para cancelaciones
DROP TRIGGER IF EXISTS trigger_event_cancelled ON public.events;
CREATE TRIGGER trigger_event_cancelled
  AFTER UPDATE ON public.events
  FOR EACH ROW
  EXECUTE FUNCTION notify_event_cancelled();

-- ===========================================
-- 4. FUNCIÓN: Notificar nuevo evento por categoría
-- ===========================================

CREATE OR REPLACE FUNCTION notify_new_event_by_category()
RETURNS TRIGGER AS $$
DECLARE
  category_name_val TEXT;
BEGIN
  -- Solo notificar si el evento está publicado y tiene categoría
  IF NEW.is_published = true AND NEW.category_id IS NOT NULL THEN

    -- Obtener nombre de la categoría
    SELECT name INTO category_name_val
    FROM public.categories
    WHERE id = NEW.category_id;

    -- Insertar notificación para usuarios interesados en esta categoría
    -- que NO sean el creador del evento
    INSERT INTO public.notifications (user_id, type, title, message, action_url, reference_id, reference_type)
    SELECT
      up.user_id,
      'update'::notification_type,
      'Nuevo evento de ' || COALESCE(category_name_val, 'tu interés'),
      NEW.title,
      '/eventos/' || NEW.slug,
      NEW.id::text,
      'event'
    FROM public.user_preferences up
    WHERE NEW.category_id::text = ANY(up.preferred_categories)
      AND up.user_id != COALESCE(NEW.created_by, '00000000-0000-0000-0000-000000000000'::uuid);

  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Crear trigger para nuevos eventos publicados
DROP TRIGGER IF EXISTS trigger_new_event_category ON public.events;
CREATE TRIGGER trigger_new_event_category
  AFTER INSERT ON public.events
  FOR EACH ROW
  WHEN (NEW.is_published = true)
  EXECUTE FUNCTION notify_new_event_by_category();

-- También notificar cuando un evento cambia a publicado
DROP TRIGGER IF EXISTS trigger_event_published ON public.events;
CREATE TRIGGER trigger_event_published
  AFTER UPDATE ON public.events
  FOR EACH ROW
  WHEN (OLD.is_published = false AND NEW.is_published = true)
  EXECUTE FUNCTION notify_new_event_by_category();

-- ===========================================
-- 5. COMENTARIOS Y DOCUMENTACIÓN
-- ===========================================

COMMENT ON FUNCTION notify_event_updated() IS
'Notifica a usuarios suscritos cuando un evento cambia fecha/hora';

COMMENT ON FUNCTION notify_event_cancelled() IS
'Notifica a usuarios suscritos cuando un evento es cancelado';

COMMENT ON FUNCTION notify_new_event_by_category() IS
'Notifica a usuarios cuando se publica un evento en sus categorías de interés';
-- ============================================================================
-- FIX: Corregir triggers de notificaciones
-- Fecha: 2025-01-25
--
-- El campo reference_id es UUID, no TEXT. Corregir los triggers para usar UUID.
-- ============================================================================

-- ===========================================
-- 1. FUNCIÓN: Notificar cuando evento se actualiza (CORREGIDA)
-- ===========================================

CREATE OR REPLACE FUNCTION notify_event_updated()
RETURNS TRIGGER AS $$
DECLARE
  changes_made TEXT := '';
BEGIN
  -- Solo notificar si hay cambios relevantes y el evento está publicado
  IF NEW.is_published = true AND (
     (OLD.start_date IS DISTINCT FROM NEW.start_date) OR
     (OLD.end_date IS DISTINCT FROM NEW.end_date) OR
     (OLD.start_time IS DISTINCT FROM NEW.start_time) OR
     (OLD.end_time IS DISTINCT FROM NEW.end_time)
  ) THEN

    changes_made := 'fecha/hora';

    -- Insertar notificación para usuarios que tienen el evento guardado
    INSERT INTO public.notifications (user_id, type, title, message, action_url, reference_id, reference_type)
    SELECT
      use.user_id,
      'update'::notification_type,
      'Evento actualizado',
      'El evento "' || NEW.title || '" ha cambiado su ' || changes_made,
      '/eventos/' || NEW.slug,
      NEW.id,  -- UUID directamente, sin ::text
      'event'
    FROM public.user_saved_events use
    WHERE use.event_id = NEW.id;

  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ===========================================
-- 2. FUNCIÓN: Notificar cuando evento se cancela (CORREGIDA)
-- ===========================================

CREATE OR REPLACE FUNCTION notify_event_cancelled()
RETURNS TRIGGER AS $$
BEGIN
  -- Solo notificar si cambia de no cancelado a cancelado
  IF OLD.is_cancelled IS DISTINCT FROM NEW.is_cancelled AND NEW.is_cancelled = true THEN

    -- Insertar notificación para usuarios que tienen el evento guardado
    INSERT INTO public.notifications (user_id, type, title, message, action_url, reference_id, reference_type)
    SELECT
      use.user_id,
      'system'::notification_type,
      'Evento cancelado',
      'El evento "' || NEW.title || '" ha sido cancelado' ||
      CASE WHEN NEW.cancellation_reason IS NOT NULL AND NEW.cancellation_reason != ''
        THEN ': ' || NEW.cancellation_reason
        ELSE ''
      END,
      '/eventos/' || NEW.slug,
      NEW.id,  -- UUID directamente, sin ::text
      'event'
    FROM public.user_saved_events use
    WHERE use.event_id = NEW.id;

  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ===========================================
-- 3. FUNCIÓN: Notificar nuevo evento por categoría (CORREGIDA)
-- ===========================================

CREATE OR REPLACE FUNCTION notify_new_event_by_category()
RETURNS TRIGGER AS $$
DECLARE
  category_name_val TEXT;
BEGIN
  -- Solo notificar si el evento está publicado y tiene categoría
  IF NEW.is_published = true AND NEW.category_id IS NOT NULL THEN

    -- Obtener nombre de la categoría
    SELECT name INTO category_name_val
    FROM public.categories
    WHERE id = NEW.category_id;

    -- Insertar notificación para usuarios interesados en esta categoría
    -- que NO sean el creador del evento
    INSERT INTO public.notifications (user_id, type, title, message, action_url, reference_id, reference_type)
    SELECT
      up.user_id,
      'update'::notification_type,
      'Nuevo evento de ' || COALESCE(category_name_val, 'tu interés'),
      NEW.title,
      '/eventos/' || NEW.slug,
      NEW.id,  -- UUID directamente, sin ::text
      'event'
    FROM public.user_preferences up
    WHERE NEW.category_id::text = ANY(up.preferred_categories)
      AND up.user_id != COALESCE(NEW.created_by, '00000000-0000-0000-0000-000000000000'::uuid);

  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
-- ============================================================================
-- FIX: Trigger de categoría también en UPDATE
-- Fecha: 2025-01-26
--
-- El trigger notify_new_event_by_category solo se disparaba en INSERT.
-- Ahora también se dispara cuando:
-- 1. Se crea un evento nuevo en una categoría de interés
-- 2. Se actualiza un evento cambiando su categoría a una de interés
-- 3. Se publica un evento (is_published pasa a true) en una categoría de interés
-- ============================================================================

-- Eliminar trigger antiguo si existe
DROP TRIGGER IF EXISTS trigger_new_event_category ON public.events;

-- Función mejorada para notificar por categoría (INSERT y UPDATE)
CREATE OR REPLACE FUNCTION notify_event_by_category()
RETURNS TRIGGER AS $$
DECLARE
  category_name_val TEXT;
  should_notify BOOLEAN := false;
BEGIN
  -- Determinar si debemos notificar
  IF TG_OP = 'INSERT' THEN
    -- Nuevo evento: notificar si está publicado y tiene categoría
    should_notify := NEW.is_published = true AND NEW.category_id IS NOT NULL;
  ELSIF TG_OP = 'UPDATE' THEN
    -- Actualización: notificar si:
    -- 1. Cambió la categoría a una nueva (y está publicado)
    -- 2. Se acaba de publicar (is_published cambió a true) y tiene categoría
    should_notify := NEW.is_published = true AND NEW.category_id IS NOT NULL AND (
      -- Categoría cambió
      (OLD.category_id IS DISTINCT FROM NEW.category_id) OR
      -- Se acaba de publicar
      (OLD.is_published = false AND NEW.is_published = true)
    );
  END IF;

  IF should_notify THEN
    -- Obtener nombre de la categoría
    SELECT name INTO category_name_val
    FROM public.categories
    WHERE id = NEW.category_id;

    -- Insertar notificación para usuarios interesados en esta categoría
    INSERT INTO public.notifications (user_id, type, title, message, action_url, reference_id, reference_type)
    SELECT
      up.user_id,
      'update'::notification_type,
      CASE
        WHEN TG_OP = 'INSERT' THEN 'Nuevo evento de ' || COALESCE(category_name_val, 'tu interés')
        ELSE 'Evento en ' || COALESCE(category_name_val, 'tu interés')
      END,
      NEW.title,
      '/eventos/' || NEW.slug,
      NEW.id,
      'event'
    FROM public.user_preferences up
    WHERE NEW.category_id::text = ANY(up.preferred_categories)
      AND up.user_id != COALESCE(NEW.created_by, '00000000-0000-0000-0000-000000000000'::uuid);

  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Crear trigger para INSERT y UPDATE
CREATE TRIGGER trigger_event_by_category
  AFTER INSERT OR UPDATE ON public.events
  FOR EACH ROW
  EXECUTE FUNCTION notify_event_by_category();
-- ============================================================================
-- Re-aplicar políticas RLS para tablas de eventos
-- Fecha: 2025-01-27
-- ============================================================================

-- EVENTS
DROP POLICY IF EXISTS "Anyone can read events" ON events;
DROP POLICY IF EXISTS "Authenticated can insert events" ON events;
DROP POLICY IF EXISTS "Authenticated can update events" ON events;
DROP POLICY IF EXISTS "Authenticated can delete events" ON events;

CREATE POLICY "Anyone can read events" ON events FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert events" ON events FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update events" ON events FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete events" ON events FOR DELETE TO authenticated USING (true);

-- EVENT_LOCATIONS
DROP POLICY IF EXISTS "Anyone can read event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated can insert event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated can update event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated can delete event_locations" ON event_locations;

CREATE POLICY "Anyone can read event_locations" ON event_locations FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert event_locations" ON event_locations FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update event_locations" ON event_locations FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete event_locations" ON event_locations FOR DELETE TO authenticated USING (true);

-- EVENT_ONLINE
DROP POLICY IF EXISTS "Anyone can read event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated can insert event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated can update event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated can delete event_online" ON event_online;

CREATE POLICY "Anyone can read event_online" ON event_online FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert event_online" ON event_online FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update event_online" ON event_online FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete event_online" ON event_online FOR DELETE TO authenticated USING (true);

-- EVENT_ORGANIZERS
DROP POLICY IF EXISTS "Anyone can read event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated can insert event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated can update event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated can delete event_organizers" ON event_organizers;

CREATE POLICY "Anyone can read event_organizers" ON event_organizers FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert event_organizers" ON event_organizers FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update event_organizers" ON event_organizers FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete event_organizers" ON event_organizers FOR DELETE TO authenticated USING (true);

-- EVENT_CONTACT
DROP POLICY IF EXISTS "Anyone can read event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated can insert event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated can update event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated can delete event_contact" ON event_contact;

CREATE POLICY "Anyone can read event_contact" ON event_contact FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert event_contact" ON event_contact FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update event_contact" ON event_contact FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete event_contact" ON event_contact FOR DELETE TO authenticated USING (true);

-- EVENT_REGISTRATION
DROP POLICY IF EXISTS "Anyone can read event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated can insert event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated can update event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated can delete event_registration" ON event_registration;

CREATE POLICY "Anyone can read event_registration" ON event_registration FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert event_registration" ON event_registration FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update event_registration" ON event_registration FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete event_registration" ON event_registration FOR DELETE TO authenticated USING (true);

-- EVENT_ACCESSIBILITY
DROP POLICY IF EXISTS "Anyone can read event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated can insert event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated can update event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated can delete event_accessibility" ON event_accessibility;

CREATE POLICY "Anyone can read event_accessibility" ON event_accessibility FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert event_accessibility" ON event_accessibility FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update event_accessibility" ON event_accessibility FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete event_accessibility" ON event_accessibility FOR DELETE TO authenticated USING (true);

-- EVENT_TAGS
DROP POLICY IF EXISTS "Anyone can read event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated can insert event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated can update event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated can delete event_tags" ON event_tags;

CREATE POLICY "Anyone can read event_tags" ON event_tags FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert event_tags" ON event_tags FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update event_tags" ON event_tags FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete event_tags" ON event_tags FOR DELETE TO authenticated USING (true);

-- EVENT_CALENDARS
DROP POLICY IF EXISTS "Anyone can read event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated can insert event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated can update event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated can delete event_calendars" ON event_calendars;

CREATE POLICY "Anyone can read event_calendars" ON event_calendars FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert event_calendars" ON event_calendars FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update event_calendars" ON event_calendars FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete event_calendars" ON event_calendars FOR DELETE TO authenticated USING (true);

-- EVENT_RESOURCES
DROP POLICY IF EXISTS "Anyone can read event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated can insert event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated can update event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated can delete event_resources" ON event_resources;

CREATE POLICY "Anyone can read event_resources" ON event_resources FOR SELECT USING (true);
CREATE POLICY "Authenticated can insert event_resources" ON event_resources FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Authenticated can update event_resources" ON event_resources FOR UPDATE TO authenticated USING (true) WITH CHECK (true);
CREATE POLICY "Authenticated can delete event_resources" ON event_resources FOR DELETE TO authenticated USING (true);
-- ============================================================================
-- Limpieza automática de notificaciones
-- Fecha: 2025-01-28
--
-- 1. Elimina notificaciones > 30 días
-- 2. Mantiene máximo 50 notificaciones por usuario
-- ============================================================================

-- Función para limpiar notificaciones antiguas de un usuario
CREATE OR REPLACE FUNCTION cleanup_old_notifications()
RETURNS TRIGGER AS $$
BEGIN
  -- Eliminar notificaciones mayores a 30 días para este usuario
  DELETE FROM public.notifications
  WHERE user_id = NEW.user_id
    AND created_at < NOW() - INTERVAL '30 days';

  -- Mantener solo las últimas 50 notificaciones por usuario
  DELETE FROM public.notifications
  WHERE id IN (
    SELECT id FROM public.notifications
    WHERE user_id = NEW.user_id
    ORDER BY created_at DESC
    OFFSET 50
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger que se ejecuta después de insertar una nueva notificación
DROP TRIGGER IF EXISTS trigger_cleanup_notifications ON public.notifications;
CREATE TRIGGER trigger_cleanup_notifications
  AFTER INSERT ON public.notifications
  FOR EACH ROW
  EXECUTE FUNCTION cleanup_old_notifications();

-- Función para limpieza manual/programada de todas las notificaciones antiguas
CREATE OR REPLACE FUNCTION cleanup_all_old_notifications()
RETURNS INTEGER AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  -- Eliminar notificaciones mayores a 30 días
  WITH deleted AS (
    DELETE FROM public.notifications
    WHERE created_at < NOW() - INTERVAL '30 days'
    RETURNING id
  )
  SELECT COUNT(*) INTO deleted_count FROM deleted;

  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Comentario para documentación
COMMENT ON FUNCTION cleanup_old_notifications() IS 'Limpia notificaciones antiguas (>30 días) y mantiene máximo 50 por usuario';
COMMENT ON FUNCTION cleanup_all_old_notifications() IS 'Limpieza manual de todas las notificaciones antiguas. Llamar periódicamente via cron.';
-- ============================================================
-- MIGRACIÓN: Re-aplicar políticas RLS para notifications
-- Fecha: 2025-01-29
-- ============================================================

-- Habilitar RLS en notifications
ALTER TABLE IF EXISTS public.notifications ENABLE ROW LEVEL SECURITY;

-- Eliminar políticas existentes
DROP POLICY IF EXISTS "Users can view own notifications" ON public.notifications;
DROP POLICY IF EXISTS "Users can update own notifications" ON public.notifications;
DROP POLICY IF EXISTS "Users can delete own notifications" ON public.notifications;
DROP POLICY IF EXISTS "System can insert notifications" ON public.notifications;

-- Política: Los usuarios pueden ver sus propias notificaciones
CREATE POLICY "Users can view own notifications" ON public.notifications
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

-- Política: Los usuarios pueden actualizar sus propias notificaciones
CREATE POLICY "Users can update own notifications" ON public.notifications
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Política: Los usuarios pueden eliminar sus propias notificaciones
CREATE POLICY "Users can delete own notifications" ON public.notifications
  FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

-- Política: El sistema puede insertar notificaciones (para triggers)
CREATE POLICY "System can insert notifications" ON public.notifications
  FOR INSERT
  WITH CHECK (true);
-- ============================================================================
-- Migración: Políticas RLS para eliminación de cuenta de usuario
-- Fecha: 2025-12-23
-- Descripción: Asegura que los usuarios puedan eliminar sus propios datos
-- ============================================================================

-- ==========================================
-- 1. TABLA: user_saved_events
-- ==========================================
-- Ya tiene política de DELETE en 20241229_consolidated_rls_policies.sql
-- Pero asegurémonos de que esté configurada correctamente

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'user_saved_events') THEN
    -- Habilitar RLS
    ALTER TABLE public.user_saved_events ENABLE ROW LEVEL SECURITY;

    -- Eliminar política existente si existe
    DROP POLICY IF EXISTS "Users can delete own saved events" ON public.user_saved_events;

    -- Crear política que permite a usuarios eliminar sus propios eventos guardados
    CREATE POLICY "Users can delete own saved events"
      ON public.user_saved_events
      FOR DELETE
      TO authenticated
      USING (auth.uid() = user_id);
  END IF;
END $$;

-- ==========================================
-- 2. TABLA: user_personal_events
-- ==========================================
-- Ya tiene política en 20250119_user_personal_events.sql pero la verificamos

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'user_personal_events') THEN
    ALTER TABLE public.user_personal_events ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "Users can delete own personal events v2" ON public.user_personal_events;

    -- La política original ya existe, pero creamos una versión alternativa si es necesario
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE tablename = 'user_personal_events'
      AND policyname = 'Users can delete own personal events'
    ) THEN
      CREATE POLICY "Users can delete own personal events v2"
        ON public.user_personal_events
        FOR DELETE
        TO authenticated
        USING (auth.uid() = user_id);
    END IF;
  END IF;
END $$;

-- ==========================================
-- 3. TABLA: notifications
-- ==========================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'notifications') THEN
    ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

    -- La política ya existe por 20250123_notifications_rls.sql
    -- Solo verificamos que esté
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE tablename = 'notifications'
      AND cmd = 'DELETE'
    ) THEN
      CREATE POLICY "Users can delete own notifications for account"
        ON public.notifications
        FOR DELETE
        TO authenticated
        USING (auth.uid() = user_id);
    END IF;
  END IF;
END $$;

-- ==========================================
-- 4. TABLA: calendars
-- ==========================================
-- Los calendarios de usuario tienen user_id, aseguramos que puedan eliminarlos
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'calendars') THEN
    ALTER TABLE public.calendars ENABLE ROW LEVEL SECURITY;

    -- Verificar si existe política de delete restrictiva por user_id
    DROP POLICY IF EXISTS "Users can delete own calendars" ON public.calendars;

    -- Crear política que permite a usuarios eliminar solo SUS calendarios
    CREATE POLICY "Users can delete own calendars"
      ON public.calendars
      FOR DELETE
      TO authenticated
      USING (auth.uid() = user_id);
  END IF;
END $$;

-- ==========================================
-- 5. TABLA: user_preferences
-- ==========================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'user_preferences') THEN
    ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "Users can delete own preferences" ON public.user_preferences;

    CREATE POLICY "Users can delete own preferences"
      ON public.user_preferences
      FOR DELETE
      TO authenticated
      USING (auth.uid() = user_id);
  END IF;
END $$;

-- ==========================================
-- 6. TABLA: profiles
-- ==========================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'profiles') THEN
    ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

    DROP POLICY IF EXISTS "Users can delete own profile" ON public.profiles;

    CREATE POLICY "Users can delete own profile"
      ON public.profiles
      FOR DELETE
      TO authenticated
      USING (auth.uid() = id);
  END IF;
END $$;

-- ==========================================
-- COMENTARIOS (dentro de bloques condicionales)
-- ==========================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete own saved events' AND tablename = 'user_saved_events') THEN
    COMMENT ON POLICY "Users can delete own saved events" ON public.user_saved_events IS
      'Permite a usuarios eliminar sus eventos guardados al borrar su cuenta';
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete own calendars' AND tablename = 'calendars') THEN
    COMMENT ON POLICY "Users can delete own calendars" ON public.calendars IS
      'Permite a usuarios eliminar sus calendarios al borrar su cuenta';
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete own preferences' AND tablename = 'user_preferences') THEN
    COMMENT ON POLICY "Users can delete own preferences" ON public.user_preferences IS
      'Permite a usuarios eliminar sus preferencias al borrar su cuenta';
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete own profile' AND tablename = 'profiles') THEN
    COMMENT ON POLICY "Users can delete own profile" ON public.profiles IS
      'Permite a usuarios eliminar su perfil al borrar su cuenta';
  END IF;
END $$;
-- ============================================================
-- MIGRACIÓN: Mejora de seguridad en políticas RLS
-- Fecha: 2026-01-07
--
-- Esta migración refuerza las políticas RLS para requerir rol
-- de admin/staff para operaciones de escritura en tablas críticas.
--
-- NOTA: Esta migración es complementaria a la validación existente
-- en las rutas API. Proporciona defensa en profundidad.
-- ============================================================

-- ==========================================
-- FUNCIÓN AUXILIAR: Verificar si el usuario es admin/staff
-- ==========================================
CREATE OR REPLACE FUNCTION public.is_admin_or_staff()
RETURNS BOOLEAN AS $$
BEGIN
  -- Verificar si el usuario actual tiene rol admin, superadmin, o moderator
  RETURN EXISTS (
    SELECT 1 FROM public.users
    WHERE id = auth.uid()
    AND role IN ('admin', 'superadmin', 'moderator')
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

COMMENT ON FUNCTION public.is_admin_or_staff() IS
  'Verifica si el usuario autenticado tiene rol de admin, superadmin o moderator';

-- ==========================================
-- TABLA: events - Solo admins pueden modificar
-- ==========================================

-- Eliminar políticas de escritura permisivas
DROP POLICY IF EXISTS "Authenticated can insert events" ON events;
DROP POLICY IF EXISTS "Authenticated can update events" ON events;
DROP POLICY IF EXISTS "Authenticated can delete events" ON events;

-- Crear políticas de escritura restringidas a admins
CREATE POLICY "Admin can insert events" ON events
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update events" ON events
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete events" ON events
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- ==========================================
-- TABLA: categories - Solo admins pueden modificar
-- ==========================================

DROP POLICY IF EXISTS "Authenticated can insert categories" ON categories;
DROP POLICY IF EXISTS "Authenticated can update categories" ON categories;
DROP POLICY IF EXISTS "Authenticated can delete categories" ON categories;

CREATE POLICY "Admin can insert categories" ON categories
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update categories" ON categories
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete categories" ON categories
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- ==========================================
-- TABLA: calendars - Solo admins pueden modificar
-- ==========================================

DROP POLICY IF EXISTS "Authenticated can insert calendars" ON calendars;
DROP POLICY IF EXISTS "Authenticated can update calendars" ON calendars;
DROP POLICY IF EXISTS "Authenticated can delete calendars" ON calendars;

CREATE POLICY "Admin can insert calendars" ON calendars
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update calendars" ON calendars
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete calendars" ON calendars
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- ==========================================
-- TABLA: tags - Solo admins pueden modificar
-- ==========================================

DROP POLICY IF EXISTS "Authenticated can insert tags" ON tags;
DROP POLICY IF EXISTS "Authenticated can update tags" ON tags;
DROP POLICY IF EXISTS "Authenticated can delete tags" ON tags;

CREATE POLICY "Admin can insert tags" ON tags
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update tags" ON tags
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete tags" ON tags
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- ==========================================
-- TABLAS RELACIONADAS CON EVENTOS - Solo admins
-- ==========================================

-- event_calendars
DROP POLICY IF EXISTS "Authenticated can insert event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated can update event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Authenticated can delete event_calendars" ON event_calendars;

CREATE POLICY "Admin can insert event_calendars" ON event_calendars
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update event_calendars" ON event_calendars
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete event_calendars" ON event_calendars
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- event_tags
DROP POLICY IF EXISTS "Authenticated can insert event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated can update event_tags" ON event_tags;
DROP POLICY IF EXISTS "Authenticated can delete event_tags" ON event_tags;

CREATE POLICY "Admin can insert event_tags" ON event_tags
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update event_tags" ON event_tags
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete event_tags" ON event_tags
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- event_locations
DROP POLICY IF EXISTS "Authenticated can insert event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated can update event_locations" ON event_locations;
DROP POLICY IF EXISTS "Authenticated can delete event_locations" ON event_locations;

CREATE POLICY "Admin can insert event_locations" ON event_locations
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update event_locations" ON event_locations
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete event_locations" ON event_locations
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- event_online
DROP POLICY IF EXISTS "Authenticated can insert event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated can update event_online" ON event_online;
DROP POLICY IF EXISTS "Authenticated can delete event_online" ON event_online;

CREATE POLICY "Admin can insert event_online" ON event_online
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update event_online" ON event_online
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete event_online" ON event_online
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- event_organizers
DROP POLICY IF EXISTS "Authenticated can insert event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated can update event_organizers" ON event_organizers;
DROP POLICY IF EXISTS "Authenticated can delete event_organizers" ON event_organizers;

CREATE POLICY "Admin can insert event_organizers" ON event_organizers
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update event_organizers" ON event_organizers
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete event_organizers" ON event_organizers
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- event_contact
DROP POLICY IF EXISTS "Authenticated can insert event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated can update event_contact" ON event_contact;
DROP POLICY IF EXISTS "Authenticated can delete event_contact" ON event_contact;

CREATE POLICY "Admin can insert event_contact" ON event_contact
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update event_contact" ON event_contact
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete event_contact" ON event_contact
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- event_registration
DROP POLICY IF EXISTS "Authenticated can insert event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated can update event_registration" ON event_registration;
DROP POLICY IF EXISTS "Authenticated can delete event_registration" ON event_registration;

CREATE POLICY "Admin can insert event_registration" ON event_registration
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update event_registration" ON event_registration
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete event_registration" ON event_registration
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- event_accessibility
DROP POLICY IF EXISTS "Authenticated can insert event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated can update event_accessibility" ON event_accessibility;
DROP POLICY IF EXISTS "Authenticated can delete event_accessibility" ON event_accessibility;

CREATE POLICY "Admin can insert event_accessibility" ON event_accessibility
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update event_accessibility" ON event_accessibility
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete event_accessibility" ON event_accessibility
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- event_resources
DROP POLICY IF EXISTS "Authenticated can insert event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated can update event_resources" ON event_resources;
DROP POLICY IF EXISTS "Authenticated can delete event_resources" ON event_resources;

CREATE POLICY "Admin can insert event_resources" ON event_resources
  FOR INSERT TO authenticated
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can update event_resources" ON event_resources
  FOR UPDATE TO authenticated
  USING (is_admin_or_staff())
  WITH CHECK (is_admin_or_staff());

CREATE POLICY "Admin can delete event_resources" ON event_resources
  FOR DELETE TO authenticated
  USING (is_admin_or_staff());

-- ==========================================
-- TABLA: users - Restringir actualización de roles
-- ==========================================

-- Solo superadmins pueden cambiar roles de usuarios
DROP POLICY IF EXISTS "Users can update own profile" ON users;

-- El usuario puede actualizar su propio perfil EXCEPTO el rol
CREATE POLICY "Users can update own profile" ON users
  FOR UPDATE TO authenticated
  USING (auth.uid() = id)
  WITH CHECK (
    auth.uid() = id
    -- El rol no puede ser cambiado por el propio usuario
    AND (role = (SELECT role FROM users WHERE id = auth.uid()))
  );

-- Superadmins pueden actualizar cualquier usuario incluyendo roles
CREATE POLICY "Superadmin can update all users" ON users
  FOR UPDATE TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE id = auth.uid()
      AND role = 'superadmin'
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM users
      WHERE id = auth.uid()
      AND role = 'superadmin'
    )
  );

-- ==========================================
-- COMENTARIOS DE DOCUMENTACIÓN
-- ==========================================
COMMENT ON POLICY "Admin can insert events" ON events IS
  'Solo usuarios con rol admin/staff pueden crear eventos';
COMMENT ON POLICY "Admin can update events" ON events IS
  'Solo usuarios con rol admin/staff pueden actualizar eventos';
COMMENT ON POLICY "Admin can delete events" ON events IS
  'Solo usuarios con rol admin/staff pueden eliminar eventos';

COMMENT ON POLICY "Users can update own profile" ON users IS
  'Usuarios pueden actualizar su perfil pero no su rol';
COMMENT ON POLICY "Superadmin can update all users" ON users IS
  'Solo superadmins pueden modificar otros usuarios y roles';
-- ============================================================
-- MIGRACIÓN: Optimización de rendimiento en políticas RLS
-- Fecha: 2026-01-08
--
-- PROBLEMA: Las políticas RLS que usan auth.uid() directamente
-- re-evalúan la función para cada fila, causando degradación de
-- rendimiento significativa en tablas grandes.
--
-- SOLUCIÓN: Envolver auth.uid() en una subquery (select auth.uid())
-- hace que PostgreSQL evalúe el valor una sola vez y lo reutilice.
--
-- Ver: https://supabase.com/docs/guides/database/postgres/row-level-security#use-security-definer-functions
-- ============================================================

-- ==========================================
-- PASO 1: ACTUALIZAR FUNCIONES AUXILIARES
-- ==========================================

-- Función is_admin_or_staff() optimizada
-- Antes: WHERE id = auth.uid() se evaluaba por cada fila
-- Ahora: (select auth.uid()) se evalúa una sola vez
CREATE OR REPLACE FUNCTION public.is_admin_or_staff()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM public.users
    WHERE id = (select auth.uid())
    AND role IN ('admin', 'superadmin', 'moderator')
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

COMMENT ON FUNCTION public.is_admin_or_staff() IS
  'Verifica si el usuario autenticado tiene rol de admin, superadmin o moderator. Optimizado para evaluación única.';

-- Función is_authenticated() optimizada
CREATE OR REPLACE FUNCTION public.is_authenticated()
RETURNS BOOLEAN AS $$
BEGIN
  RETURN (select auth.uid()) IS NOT NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

COMMENT ON FUNCTION public.is_authenticated() IS
  'Verifica si hay un usuario autenticado. Optimizado para evaluación única.';

-- ==========================================
-- PASO 2: RECREAR POLÍTICAS DE TABLA users
-- ==========================================

-- Eliminar políticas existentes
DROP POLICY IF EXISTS "Users can update own profile" ON users;
DROP POLICY IF EXISTS "Superadmin can update all users" ON users;
DROP POLICY IF EXISTS "users_select_own" ON users;
DROP POLICY IF EXISTS "users_update_own" ON users;
DROP POLICY IF EXISTS "users_delete_own" ON users;

-- Política SELECT: Mantener acceso a todos los usuarios autenticados
-- (no usa auth.uid() directamente, usa is_authenticated() que ya está optimizada)

-- Política UPDATE: Usuario puede actualizar su propio perfil (excepto rol)
CREATE POLICY "Users can update own profile" ON users
  FOR UPDATE TO authenticated
  USING ((select auth.uid()) = id)
  WITH CHECK (
    (select auth.uid()) = id
    AND (role = (SELECT role FROM users WHERE id = (select auth.uid())))
  );

-- Política: Superadmins pueden actualizar cualquier usuario
CREATE POLICY "Superadmin can update all users" ON users
  FOR UPDATE TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE id = (select auth.uid())
      AND role = 'superadmin'
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM users
      WHERE id = (select auth.uid())
      AND role = 'superadmin'
    )
  );

-- Política DELETE: Usuario puede eliminar su propia cuenta
DROP POLICY IF EXISTS "Users can delete own account" ON users;
CREATE POLICY "Users can delete own account" ON users
  FOR DELETE TO authenticated
  USING ((select auth.uid()) = id);

-- ==========================================
-- PASO 3: RECREAR POLÍTICAS DE user_personal_events
-- ==========================================

-- Eliminar políticas existentes
DROP POLICY IF EXISTS "Users can view own personal events" ON user_personal_events;
DROP POLICY IF EXISTS "Users can create personal events in own calendars" ON user_personal_events;
DROP POLICY IF EXISTS "Users can update own personal events" ON user_personal_events;
DROP POLICY IF EXISTS "Users can delete own personal events" ON user_personal_events;

-- Recrear con subquery optimizada
CREATE POLICY "Users can view own personal events"
  ON user_personal_events
  FOR SELECT
  USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can create personal events in own calendars"
  ON user_personal_events
  FOR INSERT
  WITH CHECK (
    (select auth.uid()) = user_id AND
    EXISTS (
      SELECT 1 FROM calendars
      WHERE calendars.id = calendar_id
      AND calendars.user_id = (select auth.uid())
    )
  );

CREATE POLICY "Users can update own personal events"
  ON user_personal_events
  FOR UPDATE
  USING ((select auth.uid()) = user_id)
  WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can delete own personal events"
  ON user_personal_events
  FOR DELETE
  USING ((select auth.uid()) = user_id);

-- ==========================================
-- PASO 4: RECREAR POLÍTICAS DE notifications
-- ==========================================

-- Eliminar políticas existentes
DROP POLICY IF EXISTS "Users can view own notifications" ON notifications;
DROP POLICY IF EXISTS "Users can update own notifications" ON notifications;
DROP POLICY IF EXISTS "Users can delete own notifications" ON notifications;

-- Recrear con subquery optimizada
CREATE POLICY "Users can view own notifications"
  ON notifications
  FOR SELECT TO authenticated
  USING ((select auth.uid()) = user_id);

CREATE POLICY "Users can update own notifications"
  ON notifications
  FOR UPDATE TO authenticated
  USING ((select auth.uid()) = user_id)
  WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users can delete own notifications"
  ON notifications
  FOR DELETE TO authenticated
  USING ((select auth.uid()) = user_id);

-- ==========================================
-- PASO 5: RECREAR POLÍTICAS DE user_preferences (si existe)
-- ==========================================

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_preferences') THEN
    -- Eliminar políticas existentes (todas las variantes posibles, incluyendo las que vamos a crear)
    DROP POLICY IF EXISTS "Users can view own preferences" ON user_preferences;
    DROP POLICY IF EXISTS "Users can update own preferences" ON user_preferences;
    DROP POLICY IF EXISTS "Users can insert own preferences" ON user_preferences;
    DROP POLICY IF EXISTS "Users can delete own preferences" ON user_preferences;
    DROP POLICY IF EXISTS "user_preferences_select_own" ON user_preferences;
    DROP POLICY IF EXISTS "user_preferences_update_own" ON user_preferences;
    DROP POLICY IF EXISTS "user_preferences_insert_own" ON user_preferences;
    DROP POLICY IF EXISTS "user_preferences_delete_own" ON user_preferences;

    -- Recrear con subquery optimizada
    CREATE POLICY "Users can view own preferences"
      ON user_preferences
      FOR SELECT TO authenticated
      USING ((select auth.uid()) = user_id);

    CREATE POLICY "Users can insert own preferences"
      ON user_preferences
      FOR INSERT TO authenticated
      WITH CHECK ((select auth.uid()) = user_id);

    CREATE POLICY "Users can update own preferences"
      ON user_preferences
      FOR UPDATE TO authenticated
      USING ((select auth.uid()) = user_id)
      WITH CHECK ((select auth.uid()) = user_id);

    CREATE POLICY "Users can delete own preferences"
      ON user_preferences
      FOR DELETE TO authenticated
      USING ((select auth.uid()) = user_id);
  END IF;
END $$;

-- ==========================================
-- PASO 6: RECREAR POLÍTICAS DE user_saved_events (si existe)
-- ==========================================

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_saved_events') THEN
    -- Eliminar políticas existentes (todas las variantes posibles)
    DROP POLICY IF EXISTS "Users can manage own saved events" ON user_saved_events;
    DROP POLICY IF EXISTS "Authenticated can read user_saved_events" ON user_saved_events;
    DROP POLICY IF EXISTS "Authenticated can insert user_saved_events" ON user_saved_events;
    DROP POLICY IF EXISTS "Authenticated can delete user_saved_events" ON user_saved_events;
    DROP POLICY IF EXISTS "user_saved_events_select_own" ON user_saved_events;
    DROP POLICY IF EXISTS "user_saved_events_insert_own" ON user_saved_events;
    DROP POLICY IF EXISTS "user_saved_events_delete_own" ON user_saved_events;
    -- Incluir las políticas que vamos a crear (por si ya existen)
    DROP POLICY IF EXISTS "Users can view own saved events" ON user_saved_events;
    DROP POLICY IF EXISTS "Users can insert own saved events" ON user_saved_events;
    DROP POLICY IF EXISTS "Users can delete own saved events" ON user_saved_events;

    -- Recrear con subquery optimizada (restricción por usuario)
    CREATE POLICY "Users can view own saved events"
      ON user_saved_events
      FOR SELECT TO authenticated
      USING ((select auth.uid()) = user_id);

    CREATE POLICY "Users can insert own saved events"
      ON user_saved_events
      FOR INSERT TO authenticated
      WITH CHECK ((select auth.uid()) = user_id);

    CREATE POLICY "Users can delete own saved events"
      ON user_saved_events
      FOR DELETE TO authenticated
      USING ((select auth.uid()) = user_id);
  END IF;
END $$;

-- ==========================================
-- PASO 7: RECREAR POLÍTICAS DE reminders (si existe)
-- ==========================================

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'reminders') THEN
    -- Eliminar políticas existentes (todas las variantes posibles)
    DROP POLICY IF EXISTS "Authenticated can read reminders" ON reminders;
    DROP POLICY IF EXISTS "Authenticated can insert reminders" ON reminders;
    DROP POLICY IF EXISTS "Authenticated can delete reminders" ON reminders;
    DROP POLICY IF EXISTS "reminders_select_own" ON reminders;
    DROP POLICY IF EXISTS "reminders_insert_own" ON reminders;
    DROP POLICY IF EXISTS "reminders_delete_own" ON reminders;
    -- Incluir las políticas que vamos a crear (por si ya existen)
    DROP POLICY IF EXISTS "Users can view own reminders" ON reminders;
    DROP POLICY IF EXISTS "Users can insert own reminders" ON reminders;
    DROP POLICY IF EXISTS "Users can update own reminders" ON reminders;
    DROP POLICY IF EXISTS "Users can delete own reminders" ON reminders;

    -- Recrear con subquery optimizada (restricción por usuario)
    CREATE POLICY "Users can view own reminders"
      ON reminders
      FOR SELECT TO authenticated
      USING ((select auth.uid()) = user_id);

    CREATE POLICY "Users can insert own reminders"
      ON reminders
      FOR INSERT TO authenticated
      WITH CHECK ((select auth.uid()) = user_id);

    CREATE POLICY "Users can update own reminders"
      ON reminders
      FOR UPDATE TO authenticated
      USING ((select auth.uid()) = user_id)
      WITH CHECK ((select auth.uid()) = user_id);

    CREATE POLICY "Users can delete own reminders"
      ON reminders
      FOR DELETE TO authenticated
      USING ((select auth.uid()) = user_id);
  END IF;
END $$;

-- ==========================================
-- NOTA: Tablas calendar_shares y event_invitations
-- Se omiten en esta migración porque pueden no existir o tener
-- estructura diferente. Si existen, crear migración específica.

-- ==========================================
-- DOCUMENTACIÓN
-- ==========================================

COMMENT ON FUNCTION public.is_admin_or_staff() IS
  'Verifica rol de admin/staff. Optimizado con (select auth.uid()) para evaluación única por query.';

COMMENT ON FUNCTION public.is_authenticated() IS
  'Verifica autenticación. Optimizado con (select auth.uid()) para evaluación única por query.';

-- ==========================================
-- NOTAS DE RENDIMIENTO
-- ==========================================
--
-- ANTES (ineficiente):
--   auth.uid() = user_id
--   Ejecuta auth.uid() para CADA fila de la tabla
--
-- DESPUÉS (optimizado):
--   (select auth.uid()) = user_id
--   PostgreSQL evalúa la subquery UNA vez y reutiliza el resultado
--
-- Mejora esperada: 10-100x en tablas con muchas filas
-- ==========================================
-- ============================================================
-- MIGRACIÓN: Limpieza de políticas duplicadas en tabla users
-- Fecha: 2026-01-08
--
-- Elimina políticas antiguas/duplicadas y consolida las políticas
-- de la tabla users para mayor claridad y seguridad.
-- ============================================================

-- ==========================================
-- PASO 1: ELIMINAR POLÍTICAS PROBLEMÁTICAS
-- ==========================================

-- Estas políticas con rol 'public' son un riesgo de seguridad
DROP POLICY IF EXISTS "users_all_admin" ON users;
DROP POLICY IF EXISTS "users_select_admin" ON users;

-- Políticas duplicadas o antiguas
DROP POLICY IF EXISTS "Admins can update users" ON users;
DROP POLICY IF EXISTS "Admins can view all users" ON users;
DROP POLICY IF EXISTS "Users can view own profile" ON users;

-- ==========================================
-- PASO 2: VERIFICAR POLÍTICAS CORRECTAS
-- ==========================================

-- Las políticas que deben quedar son:
-- 1. "Authenticated can read users" - SELECT para autenticados
-- 2. "Users can update own profile" - UPDATE propio perfil (optimizada)
-- 3. "Superadmin can update all users" - UPDATE para superadmins (optimizada)
-- 4. "Users can delete own account" - DELETE propia cuenta (optimizada)
-- 5. "Service role can insert users" - INSERT para service_role (triggers)

-- ==========================================
-- COMENTARIOS
-- ==========================================

COMMENT ON POLICY "Authenticated can read users" ON users IS
  'Usuarios autenticados pueden leer perfiles (necesario para verificar roles)';

COMMENT ON POLICY "Users can update own profile" ON users IS
  'Usuario puede actualizar su perfil pero no su rol. Optimizado con (select auth.uid())';

COMMENT ON POLICY "Superadmin can update all users" ON users IS
  'Solo superadmins pueden modificar otros usuarios y cambiar roles. Optimizado con (select auth.uid())';

COMMENT ON POLICY "Users can delete own account" ON users IS
  'Usuario puede eliminar su propia cuenta. Optimizado con (select auth.uid())';

COMMENT ON POLICY "Service role can insert users" ON users IS
  'Service role puede crear usuarios (usado por triggers de auth)';
-- ============================================================
-- MIGRACIÓN: Limpieza de políticas RLS duplicadas
-- Fecha: 2026-01-10
--
-- Elimina políticas antiguas/duplicadas que coexisten con las
-- nuevas políticas optimizadas. Mantiene solo las políticas
-- con nombres consistentes y optimizadas.
-- ============================================================

-- ==========================================
-- TABLA: calendars
-- Mantener: "Admin can *", "Anyone can read calendars", "Users can delete own calendars"
-- Eliminar: políticas antiguas con prefijo "calendars_*"
-- ==========================================

DROP POLICY IF EXISTS "calendars_all_admin" ON calendars;
DROP POLICY IF EXISTS "calendars_delete_own" ON calendars;
DROP POLICY IF EXISTS "calendars_insert_own" ON calendars;
DROP POLICY IF EXISTS "calendars_select_own" ON calendars;
DROP POLICY IF EXISTS "calendars_select_public" ON calendars;
DROP POLICY IF EXISTS "calendars_select_shared" ON calendars;
DROP POLICY IF EXISTS "calendars_update_own" ON calendars;

-- ==========================================
-- TABLA: categories
-- Mantener: "Admin can *", "Anyone can read categories"
-- Eliminar: políticas antiguas
-- ==========================================

DROP POLICY IF EXISTS "categories_all_admin" ON categories;
DROP POLICY IF EXISTS "categories_select_all" ON categories;

-- ==========================================
-- TABLA: tags
-- Mantener: "Admin can *", "Anyone can read tags"
-- Eliminar: políticas antiguas que permiten a cualquiera insertar
-- ==========================================

DROP POLICY IF EXISTS "tags_all_admin" ON tags;
DROP POLICY IF EXISTS "tags_insert_auth" ON tags;
DROP POLICY IF EXISTS "tags_select_all" ON tags;

-- ==========================================
-- TABLA: events
-- Mantener: "Admin can *", "Anyone can read events"
-- Eliminar: políticas antiguas de usuarios propios
-- (Los eventos públicos son gestionados solo por admins)
-- ==========================================

DROP POLICY IF EXISTS "events_all_moderator" ON events;
DROP POLICY IF EXISTS "events_delete_own" ON events;
DROP POLICY IF EXISTS "events_insert_own" ON events;
DROP POLICY IF EXISTS "events_select_own" ON events;
DROP POLICY IF EXISTS "events_select_public" ON events;
DROP POLICY IF EXISTS "events_select_shared" ON events;
DROP POLICY IF EXISTS "events_update_own" ON events;
DROP POLICY IF EXISTS "events_update_shared" ON events;

-- ==========================================
-- TABLA: event_calendars
-- Mantener: "Admin can *", "Anyone can read event_calendars"
-- Eliminar: políticas duplicadas
-- ==========================================

DROP POLICY IF EXISTS "Admins full access event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Lectura pública event_calendars" ON event_calendars;
DROP POLICY IF EXISTS "Users manage own calendars event_calendars" ON event_calendars;

-- ==========================================
-- TABLA: event_tags
-- Mantener: "Admin can *", "Anyone can read event_tags"
-- Eliminar: políticas duplicadas
-- ==========================================

DROP POLICY IF EXISTS "event_tags_manage_moderator" ON event_tags;
DROP POLICY IF EXISTS "event_tags_manage_own" ON event_tags;
DROP POLICY IF EXISTS "event_tags_select" ON event_tags;

-- ==========================================
-- TABLA: event_locations
-- Mantener: "Admin can *", "Anyone can read event_locations"
-- Eliminar: políticas duplicadas
-- ==========================================

DROP POLICY IF EXISTS "event_locations_manage_moderator" ON event_locations;
DROP POLICY IF EXISTS "event_locations_manage_own" ON event_locations;
DROP POLICY IF EXISTS "event_locations_select" ON event_locations;

-- ==========================================
-- TABLA: event_online
-- Mantener: "Admin can *", "Anyone can read event_online"
-- Eliminar: políticas duplicadas
-- ==========================================

DROP POLICY IF EXISTS "event_online_manage_moderator" ON event_online;
DROP POLICY IF EXISTS "event_online_manage_own" ON event_online;
DROP POLICY IF EXISTS "event_online_select" ON event_online;

-- ==========================================
-- TABLA: event_contact
-- Mantener: "Admin can *", "Anyone can read event_contact"
-- Eliminar: políticas duplicadas
-- ==========================================

DROP POLICY IF EXISTS "event_contact_manage_moderator" ON event_contact;
DROP POLICY IF EXISTS "event_contact_manage_own" ON event_contact;
DROP POLICY IF EXISTS "event_contact_select" ON event_contact;

-- ==========================================
-- TABLA: event_registration
-- Mantener: "Admin can *", "Anyone can read event_registration"
-- Eliminar: políticas duplicadas
-- ==========================================

DROP POLICY IF EXISTS "event_registration_manage_moderator" ON event_registration;
DROP POLICY IF EXISTS "event_registration_manage_own" ON event_registration;
DROP POLICY IF EXISTS "event_registration_select" ON event_registration;

-- ==========================================
-- TABLA: event_accessibility
-- Mantener: "Admin can *", "Anyone can read event_accessibility"
-- Eliminar: políticas duplicadas
-- ==========================================

DROP POLICY IF EXISTS "event_accessibility_manage_moderator" ON event_accessibility;
DROP POLICY IF EXISTS "event_accessibility_manage_own" ON event_accessibility;
DROP POLICY IF EXISTS "event_accessibility_select" ON event_accessibility;

-- ==========================================
-- TABLA: event_resources
-- Mantener: "Admin can *", "Anyone can read event_resources"
-- Eliminar: políticas duplicadas
-- ==========================================

DROP POLICY IF EXISTS "event_resources_manage_moderator" ON event_resources;
DROP POLICY IF EXISTS "event_resources_manage_own" ON event_resources;
DROP POLICY IF EXISTS "event_resources_select" ON event_resources;

-- ==========================================
-- TABLA: event_archive
-- Mantener: "Anyone can read", "System can insert"
-- Eliminar: duplicada de admin
-- ==========================================

DROP POLICY IF EXISTS "Admins can read event_archive" ON event_archive;

-- ==========================================
-- TABLA: event_stats_daily
-- Mantener: "Anyone can read", "System can *"
-- Eliminar: duplicada de admin
-- ==========================================

DROP POLICY IF EXISTS "Admins can read event_stats_daily" ON event_stats_daily;

-- ==========================================
-- TABLA: event_stats_monthly
-- Eliminar política redundante (solo admin, pero la tabla es para stats públicos)
-- ==========================================

DROP POLICY IF EXISTS "Admins can read event_stats_monthly" ON event_stats_monthly;

-- ==========================================
-- TABLA: notifications
-- Mantener: "Users can *" (optimizadas), "System can insert"
-- Eliminar: política antigua con rol public
-- ==========================================

DROP POLICY IF EXISTS "notifications_own" ON notifications;

-- ==========================================
-- TABLA: reminders
-- Mantener: "Users can *" (optimizadas)
-- Eliminar: política antigua con rol public
-- ==========================================

DROP POLICY IF EXISTS "reminders_own" ON reminders;

-- ==========================================
-- TABLA: user_preferences
-- Mantener: "Users can *" (optimizadas)
-- Eliminar: política antigua con rol public
-- ==========================================

DROP POLICY IF EXISTS "user_preferences_own" ON user_preferences;

-- ==========================================
-- TABLA: user_saved_events
-- Mantener: "Users can *" (optimizadas)
-- Eliminar: política antigua con rol public
-- ==========================================

DROP POLICY IF EXISTS "user_saved_events_own" ON user_saved_events;

-- ==========================================
-- TABLA: event_invitations
-- Las políticas con "Authenticated can *" son muy permisivas
-- Mantener las específicas que validan ownership
-- ==========================================

DROP POLICY IF EXISTS "Authenticated can delete event_invitations" ON event_invitations;
DROP POLICY IF EXISTS "Authenticated can insert event_invitations" ON event_invitations;
DROP POLICY IF EXISTS "Authenticated can read event_invitations" ON event_invitations;

-- ==========================================
-- RESUMEN DE POLÍTICAS FINALES POR TABLA
-- ==========================================
--
-- calendars:
--   - "Anyone can read calendars" (SELECT, public)
--   - "Admin can insert/update/delete calendars" (authenticated, is_admin_or_staff)
--   - "Users can delete own calendars" (authenticated, own)
--
-- categories, tags:
--   - "Anyone can read *" (SELECT, public)
--   - "Admin can insert/update/delete *" (authenticated, is_admin_or_staff)
--
-- events:
--   - "Anyone can read events" (SELECT, public)
--   - "Admin can insert/update/delete events" (authenticated, is_admin_or_staff)
--
-- event_*:
--   - "Anyone can read *" (SELECT, public)
--   - "Admin can insert/update/delete *" (authenticated, is_admin_or_staff)
--
-- notifications:
--   - "Users can view/update/delete own notifications" (authenticated, own)
--   - "System can insert notifications" (public - necesario para triggers)
--
-- reminders, user_preferences, user_saved_events:
--   - "Users can *" (authenticated, own)
--
-- user_personal_events:
--   - "Users can *" (public, own) - gestión completa del usuario
--
-- users:
--   - "Authenticated can read users" (authenticated)
--   - "Users can update own profile" (authenticated, own, no puede cambiar rol)
--   - "Superadmin can update all users" (authenticated, superadmin)
--   - "Users can delete own account" (authenticated, own)
--   - "Service role can insert users" (service_role)
--
-- event_invitations:
--   - "event_invitations_select_sent" (SELECT, sent by user)
--   - "event_invitations_select_received" (SELECT, received)
--   - "event_invitations_insert" (INSERT, only for own calendar events)
--   - "event_invitations_update_received" (UPDATE, only received)
--   - "event_invitations_delete_sent" (DELETE, only sent)
--
-- calendar_shares:
--   - "calendar_shares_manage_owner" (ALL, owner)
--   - "calendar_shares_select_owner" (SELECT, owner)
--   - "calendar_shares_select_shared" (SELECT, shared with)
-- ==========================================
-- Función RPC para crear notificación de calendario compartido
-- Esta función se ejecuta con SECURITY DEFINER para poder insertar
-- notificaciones para otros usuarios de forma segura

CREATE OR REPLACE FUNCTION create_share_notification(
  p_recipient_id UUID,
  p_sharer_name TEXT,
  p_calendar_name TEXT,
  p_permission TEXT,
  p_share_id UUID
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_notification_id UUID;
BEGIN
  -- Validar que el recipient existe
  IF NOT EXISTS (SELECT 1 FROM users WHERE id = p_recipient_id) THEN
    RAISE EXCEPTION 'Usuario destinatario no existe';
  END IF;

  -- Validar que el share existe
  IF NOT EXISTS (SELECT 1 FROM calendar_shares WHERE id = p_share_id) THEN
    RAISE EXCEPTION 'El share no existe';
  END IF;

  -- Validar que el caller es el owner del share
  IF NOT EXISTS (
    SELECT 1 FROM calendar_shares
    WHERE id = p_share_id
    AND owner_id = auth.uid()
  ) THEN
    RAISE EXCEPTION 'No tienes permiso para crear esta notificación';
  END IF;

  -- Crear la notificación
  INSERT INTO notifications (
    user_id,
    type,
    title,
    message,
    action_url,
    reference_id,
    reference_type,
    read
  ) VALUES (
    p_recipient_id,
    'share',
    p_sharer_name || ' ha compartido un calendario contigo',
    'Ahora tienes acceso ' ||
      CASE WHEN p_permission = 'edit' THEN 'para editar' ELSE 'de solo lectura' END ||
      ' al calendario "' || p_calendar_name || '"',
    '/mi-calendario',
    p_share_id,
    'calendar_share',
    false
  )
  RETURNING id INTO v_notification_id;

  RETURN v_notification_id;
END;
$$;

-- Dar permisos para ejecutar la función a usuarios autenticados
GRANT EXECUTE ON FUNCTION create_share_notification(UUID, TEXT, TEXT, TEXT, UUID) TO authenticated;

COMMENT ON FUNCTION create_share_notification IS 'Crea una notificación de calendario compartido de forma segura. Solo el owner del share puede llamar esta función.';
-- Corregir políticas RLS para tabla calendars
-- Los usuarios deben poder crear, actualizar y eliminar sus propios calendarios personales
-- Límite: 5 calendarios por usuario

-- Eliminar TODAS las políticas que puedan existir
DROP POLICY IF EXISTS "Users can create own calendars" ON calendars;
DROP POLICY IF EXISTS "Users can update own calendars" ON calendars;
DROP POLICY IF EXISTS "Users can delete own calendars" ON calendars;

-- Eliminar políticas restrictivas de admin
DROP POLICY IF EXISTS "Admin can insert calendars" ON calendars;
DROP POLICY IF EXISTS "Admin can update calendars" ON calendars;
DROP POLICY IF EXISTS "Admin can delete calendars" ON calendars;

-- También eliminar posibles políticas antiguas
DROP POLICY IF EXISTS "Authenticated can insert calendars" ON calendars;
DROP POLICY IF EXISTS "Authenticated can update calendars" ON calendars;
DROP POLICY IF EXISTS "Authenticated can delete calendars" ON calendars;

-- ============================================================================
-- NUEVAS POLÍTICAS PARA CALENDARIOS DE USUARIO
-- ============================================================================

-- INSERT: Usuarios pueden crear calendarios propios (máximo 5 por usuario)
CREATE POLICY "Users can create own calendars" ON calendars
  FOR INSERT TO authenticated
  WITH CHECK (
    -- El calendario debe pertenecer al usuario actual
    user_id = auth.uid()
    -- Y no debe exceder el límite de 5 calendarios
    AND (
      SELECT COUNT(*) FROM calendars c WHERE c.user_id = auth.uid()
    ) < 5
  );

-- UPDATE: Usuarios pueden actualizar sus propios calendarios
CREATE POLICY "Users can update own calendars" ON calendars
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- DELETE: Usuarios pueden eliminar sus propios calendarios (excepto el default)
CREATE POLICY "Users can delete own calendars" ON calendars
  FOR DELETE TO authenticated
  USING (
    user_id = auth.uid()
    AND is_default = false  -- No se puede eliminar el calendario por defecto
  );

-- COMENTARIOS
COMMENT ON POLICY "Users can create own calendars" ON calendars IS 'Usuarios pueden crear hasta 5 calendarios propios';
COMMENT ON POLICY "Users can update own calendars" ON calendars IS 'Usuarios pueden actualizar sus propios calendarios';
COMMENT ON POLICY "Users can delete own calendars" ON calendars IS 'Usuarios pueden eliminar sus calendarios excepto el default';
-- Función RPC para obtener eventos de un calendario compartido
-- Esta función permite a usuarios con acceso compartido ver los eventos

-- Primero eliminar las funciones existentes para poder cambiar el tipo de retorno
DROP FUNCTION IF EXISTS get_shared_calendar_events(UUID);
DROP FUNCTION IF EXISTS get_shared_calendar_personal_events(UUID);

CREATE OR REPLACE FUNCTION get_shared_calendar_events(
  p_calendar_id UUID
)
RETURNS TABLE (
  id UUID,
  event_id UUID,
  calendar_id UUID,
  user_id UUID,
  notes TEXT,
  saved_at TIMESTAMPTZ,
  event_title TEXT,
  event_description TEXT,
  event_start_date DATE,
  event_start_time TIME,
  event_end_date DATE,
  event_end_time TIME,
  event_slug TEXT,
  event_image_url TEXT,
  location_city TEXT,
  location_venue TEXT,
  category_name TEXT,
  category_slug TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_has_access BOOLEAN := FALSE;
BEGIN
  -- Verificar si el usuario actual tiene acceso al calendario
  -- Es dueño del calendario
  SELECT EXISTS (
    SELECT 1 FROM calendars cal
    WHERE cal.id = p_calendar_id AND cal.user_id = auth.uid()
  ) INTO v_has_access;

  -- O tiene acceso compartido
  IF NOT v_has_access THEN
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = p_calendar_id AND cs.shared_with_id = auth.uid()
    ) INTO v_has_access;
  END IF;

  IF NOT v_has_access THEN
    RAISE EXCEPTION 'No tienes acceso a este calendario';
  END IF;

  -- Devolver los eventos del calendario
  RETURN QUERY
  SELECT
    use.id,
    use.event_id,
    use.calendar_id,
    use.user_id,
    use.notes,
    use.saved_at,
    e.title::TEXT as event_title,
    e.description as event_description,
    e.start_date as event_start_date,
    e.start_time as event_start_time,
    e.end_date as event_end_date,
    e.end_time as event_end_time,
    e.slug::TEXT as event_slug,
    e.image_url as event_image_url,
    el.city::TEXT as location_city,
    el.name::TEXT as location_venue,
    cat.name::TEXT as category_name,
    cat.slug::TEXT as category_slug
  FROM user_saved_events use
  LEFT JOIN events e ON e.id = use.event_id
  LEFT JOIN event_locations el ON el.event_id = e.id
  LEFT JOIN categories cat ON cat.id = e.category_id
  WHERE use.calendar_id = p_calendar_id
  ORDER BY use.saved_at DESC;
END;
$$;

-- Función para obtener eventos personales de un calendario compartido
CREATE OR REPLACE FUNCTION get_shared_calendar_personal_events(
  p_calendar_id UUID
)
RETURNS TABLE (
  id UUID,
  calendar_id UUID,
  user_id UUID,
  title TEXT,
  description TEXT,
  start_date DATE,
  start_time TIME,
  end_date DATE,
  end_time TIME,
  location_name TEXT,
  notes TEXT,
  color TEXT,
  created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_has_access BOOLEAN := FALSE;
BEGIN
  -- Verificar acceso
  SELECT EXISTS (
    SELECT 1 FROM calendars cal
    WHERE cal.id = p_calendar_id AND cal.user_id = auth.uid()
  ) INTO v_has_access;

  IF NOT v_has_access THEN
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = p_calendar_id AND cs.shared_with_id = auth.uid()
    ) INTO v_has_access;
  END IF;

  IF NOT v_has_access THEN
    RAISE EXCEPTION 'No tienes acceso a este calendario';
  END IF;

  -- Devolver eventos personales
  RETURN QUERY
  SELECT
    upe.id,
    upe.calendar_id,
    upe.user_id,
    upe.title::TEXT,
    upe.description,
    upe.start_date,
    upe.start_time,
    upe.end_date,
    upe.end_time,
    upe.location_name::TEXT,
    upe.notes,
    upe.color::TEXT,
    upe.created_at
  FROM user_personal_events upe
  WHERE upe.calendar_id = p_calendar_id
  ORDER BY upe.start_date, upe.start_time;
END;
$$;

-- Permisos
GRANT EXECUTE ON FUNCTION get_shared_calendar_events(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION get_shared_calendar_personal_events(UUID) TO authenticated;

COMMENT ON FUNCTION get_shared_calendar_events IS 'Obtiene eventos guardados de un calendario al que el usuario tiene acceso (propio o compartido)';
COMMENT ON FUNCTION get_shared_calendar_personal_events IS 'Obtiene eventos personales de un calendario al que el usuario tiene acceso (propio o compartido)';
-- Funciones RPC para CRUD en calendarios compartidos con permiso de edición
-- Estas funciones verifican que el usuario tenga permiso 'edit' antes de operar

-- Eliminar funciones existentes para recrearlas
DROP FUNCTION IF EXISTS create_shared_calendar_personal_event(UUID, TEXT, TEXT, DATE, DATE, TIME, TIME, BOOLEAN, TEXT, TEXT, TEXT, INTEGER, TEXT);
DROP FUNCTION IF EXISTS update_shared_calendar_personal_event(UUID, TEXT, TEXT, DATE, DATE, TIME, TIME, BOOLEAN, TEXT, TEXT, TEXT, INTEGER, TEXT);
DROP FUNCTION IF EXISTS delete_shared_calendar_personal_event(UUID);

-- ============================================================================
-- CREAR EVENTO PERSONAL EN CALENDARIO COMPARTIDO
-- ============================================================================

CREATE OR REPLACE FUNCTION create_shared_calendar_personal_event(
  p_calendar_id UUID,
  p_title TEXT,
  p_description TEXT,
  p_start_date DATE,
  p_end_date DATE,
  p_start_time TIME,
  p_end_time TIME,
  p_all_day BOOLEAN,
  p_location_name TEXT,
  p_location_address TEXT,
  p_color TEXT,
  p_reminder_minutes INTEGER,
  p_notes TEXT
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id UUID := auth.uid();
  v_has_edit_access BOOLEAN := FALSE;
  v_event_id UUID;
  v_event_count INTEGER;
BEGIN
  -- Verificar si es dueño del calendario
  SELECT EXISTS (
    SELECT 1 FROM calendars cal
    WHERE cal.id = p_calendar_id AND cal.user_id = v_user_id
  ) INTO v_has_edit_access;

  -- Si no es dueño, verificar si tiene permiso de edición compartido
  IF NOT v_has_edit_access THEN
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = p_calendar_id
        AND cs.shared_with_id = v_user_id
        AND cs.permission = 'edit'
    ) INTO v_has_edit_access;
  END IF;

  IF NOT v_has_edit_access THEN
    RAISE EXCEPTION 'No tienes permiso para crear eventos en este calendario';
  END IF;

  -- Verificar límite de eventos (200 por calendario)
  SELECT COUNT(*) INTO v_event_count
  FROM user_personal_events
  WHERE calendar_id = p_calendar_id;

  IF v_event_count >= 200 THEN
    RAISE EXCEPTION 'Este calendario ha alcanzado el límite de 200 eventos personales';
  END IF;

  -- Crear el evento
  INSERT INTO user_personal_events (
    user_id,
    calendar_id,
    title,
    description,
    start_date,
    end_date,
    start_time,
    end_time,
    all_day,
    location_name,
    location_address,
    color,
    reminder_minutes,
    notes
  ) VALUES (
    v_user_id,
    p_calendar_id,
    p_title,
    p_description,
    p_start_date,
    p_end_date,
    CASE WHEN p_all_day THEN NULL ELSE p_start_time END,
    CASE WHEN p_all_day THEN NULL ELSE p_end_time END,
    p_all_day,
    p_location_name,
    p_location_address,
    p_color,
    p_reminder_minutes,
    p_notes
  )
  RETURNING id INTO v_event_id;

  RETURN v_event_id;
END;
$$;

-- ============================================================================
-- ACTUALIZAR EVENTO PERSONAL EN CALENDARIO COMPARTIDO
-- ============================================================================

CREATE OR REPLACE FUNCTION update_shared_calendar_personal_event(
  p_event_id UUID,
  p_title TEXT,
  p_description TEXT,
  p_start_date DATE,
  p_end_date DATE,
  p_start_time TIME,
  p_end_time TIME,
  p_all_day BOOLEAN,
  p_location_name TEXT,
  p_location_address TEXT,
  p_color TEXT,
  p_reminder_minutes INTEGER,
  p_notes TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id UUID := auth.uid();
  v_calendar_id UUID;
  v_has_edit_access BOOLEAN := FALSE;
BEGIN
  -- Obtener el calendar_id del evento
  SELECT calendar_id INTO v_calendar_id
  FROM user_personal_events
  WHERE id = p_event_id;

  IF v_calendar_id IS NULL THEN
    RAISE EXCEPTION 'Evento no encontrado';
  END IF;

  -- Verificar si es dueño del calendario
  SELECT EXISTS (
    SELECT 1 FROM calendars cal
    WHERE cal.id = v_calendar_id AND cal.user_id = v_user_id
  ) INTO v_has_edit_access;

  -- Si no es dueño, verificar permiso de edición compartido
  IF NOT v_has_edit_access THEN
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = v_calendar_id
        AND cs.shared_with_id = v_user_id
        AND cs.permission = 'edit'
    ) INTO v_has_edit_access;
  END IF;

  IF NOT v_has_edit_access THEN
    RAISE EXCEPTION 'No tienes permiso para editar eventos en este calendario';
  END IF;

  -- Actualizar el evento (solo campos no NULL)
  UPDATE user_personal_events
  SET
    title = COALESCE(p_title, title),
    description = COALESCE(p_description, description),
    start_date = COALESCE(p_start_date, start_date),
    end_date = COALESCE(p_end_date, end_date),
    start_time = CASE
      WHEN p_all_day = TRUE THEN NULL
      WHEN p_start_time IS NOT NULL THEN p_start_time
      ELSE start_time
    END,
    end_time = CASE
      WHEN p_all_day = TRUE THEN NULL
      WHEN p_end_time IS NOT NULL THEN p_end_time
      ELSE end_time
    END,
    all_day = COALESCE(p_all_day, all_day),
    location_name = COALESCE(p_location_name, location_name),
    location_address = COALESCE(p_location_address, location_address),
    color = COALESCE(p_color, color),
    reminder_minutes = COALESCE(p_reminder_minutes, reminder_minutes),
    notes = COALESCE(p_notes, notes),
    updated_at = NOW()
  WHERE id = p_event_id;

  RETURN TRUE;
END;
$$;

-- ============================================================================
-- ELIMINAR EVENTO PERSONAL EN CALENDARIO COMPARTIDO
-- ============================================================================

CREATE OR REPLACE FUNCTION delete_shared_calendar_personal_event(
  p_event_id UUID
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id UUID := auth.uid();
  v_calendar_id UUID;
  v_event_user_id UUID;
  v_has_edit_access BOOLEAN := FALSE;
BEGIN
  -- Obtener el calendar_id y user_id del evento
  SELECT calendar_id, user_id INTO v_calendar_id, v_event_user_id
  FROM user_personal_events
  WHERE id = p_event_id;

  IF v_calendar_id IS NULL THEN
    RAISE EXCEPTION 'Evento no encontrado';
  END IF;

  -- El creador del evento siempre puede eliminarlo
  IF v_event_user_id = v_user_id THEN
    v_has_edit_access := TRUE;
  ELSE
    -- Verificar si es dueño del calendario
    SELECT EXISTS (
      SELECT 1 FROM calendars cal
      WHERE cal.id = v_calendar_id AND cal.user_id = v_user_id
    ) INTO v_has_edit_access;

    -- Si no es dueño, verificar permiso de edición compartido
    IF NOT v_has_edit_access THEN
      SELECT EXISTS (
        SELECT 1 FROM calendar_shares cs
        WHERE cs.calendar_id = v_calendar_id
          AND cs.shared_with_id = v_user_id
          AND cs.permission = 'edit'
      ) INTO v_has_edit_access;
    END IF;
  END IF;

  IF NOT v_has_edit_access THEN
    RAISE EXCEPTION 'No tienes permiso para eliminar este evento';
  END IF;

  -- Eliminar el evento
  DELETE FROM user_personal_events WHERE id = p_event_id;

  RETURN TRUE;
END;
$$;

-- Permisos
GRANT EXECUTE ON FUNCTION create_shared_calendar_personal_event(UUID, TEXT, TEXT, DATE, DATE, TIME, TIME, BOOLEAN, TEXT, TEXT, TEXT, INTEGER, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION update_shared_calendar_personal_event(UUID, TEXT, TEXT, DATE, DATE, TIME, TIME, BOOLEAN, TEXT, TEXT, TEXT, INTEGER, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION delete_shared_calendar_personal_event(UUID) TO authenticated;

COMMENT ON FUNCTION create_shared_calendar_personal_event IS 'Crea un evento personal en un calendario propio o compartido con permiso de edición';
COMMENT ON FUNCTION update_shared_calendar_personal_event IS 'Actualiza un evento personal en un calendario propio o compartido con permiso de edición';
COMMENT ON FUNCTION delete_shared_calendar_personal_event IS 'Elimina un evento personal en un calendario propio o compartido con permiso de edición';
-- Añadir campo updated_by para saber quién editó el evento por última vez
-- También actualizar las funciones RPC para que guarden esta información

-- ============================================================================
-- 1. AÑADIR COLUMNA updated_by
-- ============================================================================

ALTER TABLE user_personal_events
ADD COLUMN IF NOT EXISTS updated_by UUID REFERENCES auth.users(id) ON DELETE SET NULL;

-- Comentario
COMMENT ON COLUMN user_personal_events.updated_by IS 'Usuario que realizó la última edición del evento';

-- ============================================================================
-- 2. ACTUALIZAR FUNCIÓN DE CREAR EVENTO
-- ============================================================================

CREATE OR REPLACE FUNCTION create_shared_calendar_personal_event(
  p_calendar_id UUID,
  p_title TEXT,
  p_description TEXT,
  p_start_date DATE,
  p_end_date DATE,
  p_start_time TIME,
  p_end_time TIME,
  p_all_day BOOLEAN,
  p_location_name TEXT,
  p_location_address TEXT,
  p_color TEXT,
  p_reminder_minutes INTEGER,
  p_notes TEXT
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id UUID := auth.uid();
  v_has_edit_access BOOLEAN := FALSE;
  v_event_id UUID;
  v_event_count INTEGER;
BEGIN
  -- Verificar si es dueño del calendario
  SELECT EXISTS (
    SELECT 1 FROM calendars cal
    WHERE cal.id = p_calendar_id AND cal.user_id = v_user_id
  ) INTO v_has_edit_access;

  -- Si no es dueño, verificar si tiene permiso de edición compartido
  IF NOT v_has_edit_access THEN
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = p_calendar_id
        AND cs.shared_with_id = v_user_id
        AND cs.permission = 'edit'
    ) INTO v_has_edit_access;
  END IF;

  IF NOT v_has_edit_access THEN
    RAISE EXCEPTION 'No tienes permiso para crear eventos en este calendario';
  END IF;

  -- Verificar límite de eventos (200 por calendario)
  SELECT COUNT(*) INTO v_event_count
  FROM user_personal_events
  WHERE calendar_id = p_calendar_id;

  IF v_event_count >= 200 THEN
    RAISE EXCEPTION 'Este calendario ha alcanzado el límite de 200 eventos personales';
  END IF;

  -- Crear el evento (updated_by = creador al crear)
  INSERT INTO user_personal_events (
    user_id,
    calendar_id,
    title,
    description,
    start_date,
    end_date,
    start_time,
    end_time,
    all_day,
    location_name,
    location_address,
    color,
    reminder_minutes,
    notes,
    updated_by
  ) VALUES (
    v_user_id,
    p_calendar_id,
    p_title,
    p_description,
    p_start_date,
    p_end_date,
    CASE WHEN p_all_day THEN NULL ELSE p_start_time END,
    CASE WHEN p_all_day THEN NULL ELSE p_end_time END,
    p_all_day,
    p_location_name,
    p_location_address,
    p_color,
    p_reminder_minutes,
    p_notes,
    v_user_id  -- El creador es también el último editor
  )
  RETURNING id INTO v_event_id;

  RETURN v_event_id;
END;
$$;

-- ============================================================================
-- 3. ACTUALIZAR FUNCIÓN DE EDITAR EVENTO
-- ============================================================================

CREATE OR REPLACE FUNCTION update_shared_calendar_personal_event(
  p_event_id UUID,
  p_title TEXT,
  p_description TEXT,
  p_start_date DATE,
  p_end_date DATE,
  p_start_time TIME,
  p_end_time TIME,
  p_all_day BOOLEAN,
  p_location_name TEXT,
  p_location_address TEXT,
  p_color TEXT,
  p_reminder_minutes INTEGER,
  p_notes TEXT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id UUID := auth.uid();
  v_calendar_id UUID;
  v_has_edit_access BOOLEAN := FALSE;
BEGIN
  -- Obtener el calendar_id del evento
  SELECT calendar_id INTO v_calendar_id
  FROM user_personal_events
  WHERE id = p_event_id;

  IF v_calendar_id IS NULL THEN
    RAISE EXCEPTION 'Evento no encontrado';
  END IF;

  -- Verificar si es dueño del calendario
  SELECT EXISTS (
    SELECT 1 FROM calendars cal
    WHERE cal.id = v_calendar_id AND cal.user_id = v_user_id
  ) INTO v_has_edit_access;

  -- Si no es dueño, verificar permiso de edición compartido
  IF NOT v_has_edit_access THEN
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = v_calendar_id
        AND cs.shared_with_id = v_user_id
        AND cs.permission = 'edit'
    ) INTO v_has_edit_access;
  END IF;

  IF NOT v_has_edit_access THEN
    RAISE EXCEPTION 'No tienes permiso para editar eventos en este calendario';
  END IF;

  -- Actualizar el evento (guardar quién editó)
  UPDATE user_personal_events
  SET
    title = COALESCE(p_title, title),
    description = COALESCE(p_description, description),
    start_date = COALESCE(p_start_date, start_date),
    end_date = COALESCE(p_end_date, end_date),
    start_time = CASE
      WHEN p_all_day = TRUE THEN NULL
      WHEN p_start_time IS NOT NULL THEN p_start_time
      ELSE start_time
    END,
    end_time = CASE
      WHEN p_all_day = TRUE THEN NULL
      WHEN p_end_time IS NOT NULL THEN p_end_time
      ELSE end_time
    END,
    all_day = COALESCE(p_all_day, all_day),
    location_name = COALESCE(p_location_name, location_name),
    location_address = COALESCE(p_location_address, location_address),
    color = COALESCE(p_color, color),
    reminder_minutes = COALESCE(p_reminder_minutes, reminder_minutes),
    notes = COALESCE(p_notes, notes),
    updated_at = NOW(),
    updated_by = v_user_id  -- Guardar quién editó
  WHERE id = p_event_id;

  RETURN TRUE;
END;
$$;

-- ============================================================================
-- 4. ACTUALIZAR FUNCIÓN DE OBTENER EVENTOS PERSONALES
-- ============================================================================

DROP FUNCTION IF EXISTS get_shared_calendar_personal_events(UUID);

CREATE OR REPLACE FUNCTION get_shared_calendar_personal_events(
  p_calendar_id UUID
)
RETURNS TABLE (
  id UUID,
  calendar_id UUID,
  user_id UUID,
  title TEXT,
  description TEXT,
  start_date DATE,
  start_time TIME,
  end_date DATE,
  end_time TIME,
  all_day BOOLEAN,
  location_name TEXT,
  notes TEXT,
  color TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  updated_by UUID,
  creator_name TEXT,
  creator_email TEXT,
  creator_avatar TEXT,
  editor_name TEXT,
  editor_email TEXT,
  editor_avatar TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_has_access BOOLEAN := FALSE;
BEGIN
  -- Verificar acceso
  SELECT EXISTS (
    SELECT 1 FROM calendars cal
    WHERE cal.id = p_calendar_id AND cal.user_id = auth.uid()
  ) INTO v_has_access;

  IF NOT v_has_access THEN
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = p_calendar_id AND cs.shared_with_id = auth.uid()
    ) INTO v_has_access;
  END IF;

  IF NOT v_has_access THEN
    RAISE EXCEPTION 'No tienes acceso a este calendario';
  END IF;

  -- Devolver eventos personales con info de creador y editor
  RETURN QUERY
  SELECT
    upe.id,
    upe.calendar_id,
    upe.user_id,
    upe.title::TEXT,
    upe.description,
    upe.start_date,
    upe.start_time,
    upe.end_date,
    upe.end_time,
    upe.all_day,
    upe.location_name::TEXT,
    upe.notes,
    upe.color::TEXT,
    upe.created_at,
    upe.updated_at,
    upe.updated_by,
    COALESCE(NULLIF(creator.full_name, ''), creator.email)::TEXT as creator_name,
    creator.email::TEXT as creator_email,
    creator.avatar_url::TEXT as creator_avatar,
    COALESCE(NULLIF(editor.full_name, ''), editor.email)::TEXT as editor_name,
    editor.email::TEXT as editor_email,
    editor.avatar_url::TEXT as editor_avatar
  FROM user_personal_events upe
  LEFT JOIN users creator ON creator.id = upe.user_id
  LEFT JOIN users editor ON editor.id = upe.updated_by
  WHERE upe.calendar_id = p_calendar_id
  ORDER BY upe.start_date, upe.start_time;
END;
$$;

-- Permisos
GRANT EXECUTE ON FUNCTION get_shared_calendar_personal_events(UUID) TO authenticated;

COMMENT ON FUNCTION get_shared_calendar_personal_events IS 'Obtiene eventos personales con info de creador y editor';
-- Función RPC para guardar eventos del sistema en calendarios compartidos con permiso de edición
-- Esta función usa SECURITY DEFINER para bypassear RLS

DROP FUNCTION IF EXISTS save_event_to_shared_calendar(UUID, UUID, TEXT, TEXT);

CREATE OR REPLACE FUNCTION save_event_to_shared_calendar(
  p_event_id UUID,
  p_calendar_id UUID,
  p_color TEXT DEFAULT NULL,
  p_notes TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id UUID := auth.uid();
  v_calendar_owner_id UUID;
  v_has_access BOOLEAN := FALSE;
  v_event_count INTEGER;
  v_max_events INTEGER := 200;
  v_existing_id UUID;
  v_new_id UUID;
BEGIN
  -- Verificar que el usuario está autenticado
  IF v_user_id IS NULL THEN
    RETURN json_build_object('success', false, 'error', 'Usuario no autenticado');
  END IF;

  -- Obtener el dueño del calendario
  SELECT user_id INTO v_calendar_owner_id
  FROM calendars
  WHERE id = p_calendar_id;

  IF v_calendar_owner_id IS NULL THEN
    RETURN json_build_object('success', false, 'error', 'Calendario no encontrado');
  END IF;

  -- Verificar si es dueño del calendario
  IF v_calendar_owner_id = v_user_id THEN
    v_has_access := TRUE;
  ELSE
    -- Verificar si tiene permiso de edición compartido
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = p_calendar_id
        AND cs.shared_with_id = v_user_id
        AND cs.permission = 'edit'
    ) INTO v_has_access;
  END IF;

  IF NOT v_has_access THEN
    RETURN json_build_object('success', false, 'error', 'No tienes permiso para guardar eventos en este calendario');
  END IF;

  -- Verificar límite de eventos
  SELECT COUNT(*) INTO v_event_count
  FROM user_saved_events
  WHERE calendar_id = p_calendar_id;

  IF v_event_count >= v_max_events THEN
    RETURN json_build_object('success', false, 'error', 'Este calendario ha alcanzado el límite de ' || v_max_events || ' eventos');
  END IF;

  -- Verificar si ya está guardado en este calendario
  SELECT id INTO v_existing_id
  FROM user_saved_events
  WHERE event_id = p_event_id AND calendar_id = p_calendar_id;

  IF v_existing_id IS NOT NULL THEN
    RETURN json_build_object('success', false, 'error', 'Este evento ya está guardado en este calendario');
  END IF;

  -- Insertar el evento guardado (usar el owner del calendario como user_id)
  INSERT INTO user_saved_events (
    user_id,
    event_id,
    calendar_id,
    color,
    notes
  ) VALUES (
    v_calendar_owner_id,
    p_event_id,
    p_calendar_id,
    p_color,
    p_notes
  )
  RETURNING id INTO v_new_id;

  RETURN json_build_object('success', true, 'id', v_new_id);
EXCEPTION
  WHEN OTHERS THEN
    RETURN json_build_object('success', false, 'error', SQLERRM);
END;
$$;

-- Permisos
GRANT EXECUTE ON FUNCTION save_event_to_shared_calendar(UUID, UUID, TEXT, TEXT) TO authenticated;

COMMENT ON FUNCTION save_event_to_shared_calendar IS 'Guarda un evento del sistema en un calendario propio o compartido con permiso de edición';
-- Función RPC para eliminar eventos de calendarios compartidos con permiso de edición
-- Esta función usa SECURITY DEFINER para bypasear RLS en calendarios compartidos

DROP FUNCTION IF EXISTS delete_event_from_shared_calendar(UUID, UUID);

CREATE OR REPLACE FUNCTION delete_event_from_shared_calendar(
  p_event_id UUID,
  p_calendar_id UUID
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id UUID := auth.uid();
  v_calendar_owner_id UUID;
  v_has_access BOOLEAN := FALSE;
  v_deleted_count INTEGER;
BEGIN
  -- Verificar que el usuario está autenticado
  IF v_user_id IS NULL THEN
    RETURN json_build_object('success', false, 'error', 'Usuario no autenticado');
  END IF;

  -- Obtener el dueño del calendario
  SELECT user_id INTO v_calendar_owner_id
  FROM calendars
  WHERE id = p_calendar_id;

  IF v_calendar_owner_id IS NULL THEN
    RETURN json_build_object('success', false, 'error', 'Calendario no encontrado');
  END IF;

  -- Verificar si es dueño del calendario
  IF v_calendar_owner_id = v_user_id THEN
    v_has_access := TRUE;
  ELSE
    -- Verificar si tiene permiso de edición compartido
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = p_calendar_id
        AND cs.shared_with_id = v_user_id
        AND cs.permission = 'edit'
    ) INTO v_has_access;
  END IF;

  IF NOT v_has_access THEN
    RETURN json_build_object('success', false, 'error', 'No tienes permiso para eliminar eventos de este calendario');
  END IF;

  -- Eliminar el evento (el evento pertenece al dueño del calendario)
  DELETE FROM user_saved_events
  WHERE event_id = p_event_id
    AND calendar_id = p_calendar_id
    AND user_id = v_calendar_owner_id;

  GET DIAGNOSTICS v_deleted_count = ROW_COUNT;

  IF v_deleted_count = 0 THEN
    RETURN json_build_object('success', false, 'error', 'El evento no existe en este calendario');
  END IF;

  RETURN json_build_object('success', true, 'deleted_count', v_deleted_count);
EXCEPTION
  WHEN OTHERS THEN
    RETURN json_build_object('success', false, 'error', SQLERRM);
END;
$$;

-- Permisos
GRANT EXECUTE ON FUNCTION delete_event_from_shared_calendar(UUID, UUID) TO authenticated;

COMMENT ON FUNCTION delete_event_from_shared_calendar IS 'Elimina un evento guardado de un calendario propio o compartido con permiso de edición';
-- Añadir campo saved_by para trackear quién guardó el evento
-- Esto es útil en calendarios compartidos donde el user_id es del dueño del calendario

-- Añadir columna saved_by (quien guardó el evento, puede ser diferente al dueño del calendario)
ALTER TABLE user_saved_events
ADD COLUMN IF NOT EXISTS saved_by UUID REFERENCES auth.users(id);

-- Actualizar registros existentes: el saved_by es el mismo user_id
UPDATE user_saved_events SET saved_by = user_id WHERE saved_by IS NULL;

-- Comentario
COMMENT ON COLUMN user_saved_events.saved_by IS 'Usuario que guardó el evento (puede ser diferente al dueño del calendario en calendarios compartidos)';

-- Actualizar la función save_event_to_shared_calendar para usar saved_by
DROP FUNCTION IF EXISTS save_event_to_shared_calendar(UUID, UUID, TEXT, TEXT);

CREATE OR REPLACE FUNCTION save_event_to_shared_calendar(
  p_event_id UUID,
  p_calendar_id UUID,
  p_color TEXT DEFAULT NULL,
  p_notes TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id UUID := auth.uid();
  v_calendar_owner_id UUID;
  v_has_access BOOLEAN := FALSE;
  v_event_count INTEGER;
  v_max_events INTEGER := 200;
  v_existing_id UUID;
  v_new_id UUID;
BEGIN
  -- Verificar que el usuario está autenticado
  IF v_user_id IS NULL THEN
    RETURN json_build_object('success', false, 'error', 'Usuario no autenticado');
  END IF;

  -- Obtener el dueño del calendario
  SELECT user_id INTO v_calendar_owner_id
  FROM calendars
  WHERE id = p_calendar_id;

  IF v_calendar_owner_id IS NULL THEN
    RETURN json_build_object('success', false, 'error', 'Calendario no encontrado');
  END IF;

  -- Verificar si es dueño del calendario
  IF v_calendar_owner_id = v_user_id THEN
    v_has_access := TRUE;
  ELSE
    -- Verificar si tiene permiso de edición compartido
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = p_calendar_id
        AND cs.shared_with_id = v_user_id
        AND cs.permission = 'edit'
    ) INTO v_has_access;
  END IF;

  IF NOT v_has_access THEN
    RETURN json_build_object('success', false, 'error', 'No tienes permiso para guardar eventos en este calendario');
  END IF;

  -- Verificar límite de eventos
  SELECT COUNT(*) INTO v_event_count
  FROM user_saved_events
  WHERE calendar_id = p_calendar_id;

  IF v_event_count >= v_max_events THEN
    RETURN json_build_object('success', false, 'error', 'Este calendario ha alcanzado el límite de ' || v_max_events || ' eventos');
  END IF;

  -- Verificar si ya está guardado en este calendario
  SELECT id INTO v_existing_id
  FROM user_saved_events
  WHERE event_id = p_event_id AND calendar_id = p_calendar_id;

  IF v_existing_id IS NOT NULL THEN
    RETURN json_build_object('success', false, 'error', 'Este evento ya está guardado en este calendario');
  END IF;

  -- Insertar el evento guardado
  -- user_id = dueño del calendario (para RLS)
  -- saved_by = usuario que lo guardó (para tracking)
  INSERT INTO user_saved_events (
    user_id,
    event_id,
    calendar_id,
    color,
    notes,
    saved_by
  ) VALUES (
    v_calendar_owner_id,
    p_event_id,
    p_calendar_id,
    p_color,
    p_notes,
    v_user_id  -- Quien lo guardó
  )
  RETURNING id INTO v_new_id;

  RETURN json_build_object('success', true, 'id', v_new_id);
EXCEPTION
  WHEN OTHERS THEN
    RETURN json_build_object('success', false, 'error', SQLERRM);
END;
$$;

-- Permisos
GRANT EXECUTE ON FUNCTION save_event_to_shared_calendar(UUID, UUID, TEXT, TEXT) TO authenticated;

-- Actualizar la función get_shared_calendar_events para incluir info de quien guardó
DROP FUNCTION IF EXISTS get_shared_calendar_events(UUID);

CREATE OR REPLACE FUNCTION get_shared_calendar_events(
  p_calendar_id UUID
)
RETURNS TABLE (
  id UUID,
  event_id UUID,
  calendar_id UUID,
  user_id UUID,
  notes TEXT,
  saved_at TIMESTAMPTZ,
  saved_by UUID,
  saved_by_name TEXT,
  saved_by_email TEXT,
  saved_by_avatar TEXT,
  event_title TEXT,
  event_description TEXT,
  event_start_date DATE,
  event_start_time TIME,
  event_end_date DATE,
  event_end_time TIME,
  event_slug TEXT,
  event_image_url TEXT,
  location_city TEXT,
  location_venue TEXT,
  category_name TEXT,
  category_slug TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_has_access BOOLEAN := FALSE;
BEGIN
  -- Verificar si el usuario actual tiene acceso al calendario
  SELECT EXISTS (
    SELECT 1 FROM calendars cal
    WHERE cal.id = p_calendar_id AND cal.user_id = auth.uid()
  ) INTO v_has_access;

  IF NOT v_has_access THEN
    SELECT EXISTS (
      SELECT 1 FROM calendar_shares cs
      WHERE cs.calendar_id = p_calendar_id AND cs.shared_with_id = auth.uid()
    ) INTO v_has_access;
  END IF;

  IF NOT v_has_access THEN
    RAISE EXCEPTION 'No tienes acceso a este calendario';
  END IF;

  -- Devolver los eventos del calendario con info de quien guardó
  RETURN QUERY
  SELECT
    use.id,
    use.event_id,
    use.calendar_id,
    use.user_id,
    use.notes,
    use.saved_at,
    use.saved_by,
    saver.full_name::TEXT as saved_by_name,
    saver.email::TEXT as saved_by_email,
    saver.avatar_url::TEXT as saved_by_avatar,
    e.title::TEXT as event_title,
    e.description as event_description,
    e.start_date as event_start_date,
    e.start_time as event_start_time,
    e.end_date as event_end_date,
    e.end_time as event_end_time,
    e.slug::TEXT as event_slug,
    e.image_url as event_image_url,
    el.city::TEXT as location_city,
    el.name::TEXT as location_venue,
    cat.name::TEXT as category_name,
    cat.slug::TEXT as category_slug
  FROM user_saved_events use
  LEFT JOIN events e ON e.id = use.event_id
  LEFT JOIN event_locations el ON el.event_id = e.id
  LEFT JOIN categories cat ON cat.id = e.category_id
  LEFT JOIN users saver ON saver.id = COALESCE(use.saved_by, use.user_id)
  WHERE use.calendar_id = p_calendar_id
  ORDER BY use.saved_at DESC;
END;
$$;

-- Permisos
GRANT EXECUTE ON FUNCTION get_shared_calendar_events(UUID) TO authenticated;

COMMENT ON FUNCTION save_event_to_shared_calendar IS 'Guarda un evento del sistema en un calendario propio o compartido con permiso de edición, trackea quien lo guardó';
COMMENT ON FUNCTION get_shared_calendar_events IS 'Obtiene eventos guardados de un calendario al que el usuario tiene acceso (propio o compartido), incluye info de quien guardó';
-- =============================================
-- Migración: Cambio seguro de contraseña
-- Fecha: 2026-01-15
-- Descripción: Crea una función RPC que verifica la contraseña actual
--              antes de permitir el cambio a una nueva contraseña.
-- =============================================

-- Función para verificar la contraseña actual del usuario
CREATE OR REPLACE FUNCTION verify_user_password(password text)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = auth, public
AS $$
DECLARE
  user_id uuid;
BEGIN
  -- Obtener el ID del usuario autenticado
  user_id := auth.uid();

  IF user_id IS NULL THEN
    RETURN false;
  END IF;

  -- Verificar si la contraseña coincide usando crypt
  RETURN EXISTS (
    SELECT 1
    FROM auth.users
    WHERE id = user_id
      AND encrypted_password = crypt(password, encrypted_password)
  );
END;
$$;

-- Función para cambiar la contraseña de forma segura
-- Verifica la contraseña actual antes de actualizarla
CREATE OR REPLACE FUNCTION change_user_password(
  current_password text,
  new_password text
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = auth, public
AS $$
DECLARE
  user_id uuid;
  password_valid boolean;
BEGIN
  -- Obtener el ID del usuario autenticado
  user_id := auth.uid();

  IF user_id IS NULL THEN
    RETURN json_build_object(
      'success', false,
      'error', 'Usuario no autenticado'
    );
  END IF;

  -- Verificar que la nueva contraseña tiene al menos 8 caracteres
  IF length(new_password) < 8 THEN
    RETURN json_build_object(
      'success', false,
      'error', 'La nueva contraseña debe tener al menos 8 caracteres'
    );
  END IF;

  -- Verificar la contraseña actual
  SELECT EXISTS (
    SELECT 1
    FROM auth.users
    WHERE id = user_id
      AND encrypted_password = crypt(current_password, encrypted_password)
  ) INTO password_valid;

  IF NOT password_valid THEN
    RETURN json_build_object(
      'success', false,
      'error', 'La contraseña actual es incorrecta'
    );
  END IF;

  -- Actualizar la contraseña
  UPDATE auth.users
  SET
    encrypted_password = crypt(new_password, gen_salt('bf')),
    updated_at = now()
  WHERE id = user_id;

  RETURN json_build_object(
    'success', true,
    'message', 'Contraseña actualizada correctamente'
  );
END;
$$;

-- Otorgar permisos para ejecutar las funciones
GRANT EXECUTE ON FUNCTION verify_user_password(text) TO authenticated;
GRANT EXECUTE ON FUNCTION change_user_password(text, text) TO authenticated;

-- Comentarios para documentación
COMMENT ON FUNCTION verify_user_password(text) IS 'Verifica si la contraseña proporcionada coincide con la del usuario autenticado';
COMMENT ON FUNCTION change_user_password(text, text) IS 'Cambia la contraseña del usuario después de verificar la contraseña actual';
-- ============================================================
-- MIGRACIÓN: Hardening de seguridad
-- Fecha: 2026-01-19
--
-- Soluciona las siguientes vulnerabilidades del scan de Supabase:
-- 1. [MEDIUM] OTP Timing Attack - Cooldown entre peticiones
-- 2. [HIGH] OTP Brute Force - Lockout tras intentos fallidos
-- 3. [HIGH] Password Reset Flow Abuse - Rate limiting
-- 4. [LOW] API Version Information Disclosure - Revocación de permisos
--
-- NOTA: Las vulnerabilidades de TLS, Content-Type y Realtime Token
-- se configuran en el Dashboard de Supabase, no en SQL.
-- ============================================================

-- ==========================================
-- EXTENSIÓN REQUERIDA
-- ==========================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- ==========================================
-- 1. RATE LIMITING PARA PASSWORD RESET
-- ==========================================

-- Tabla para tracking de solicitudes de reset
CREATE TABLE IF NOT EXISTS public.password_reset_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email citext NOT NULL,
  ip_address text,
  requested_at timestamptz NOT NULL DEFAULT now(),

  -- Índice para búsquedas rápidas
  CONSTRAINT password_reset_requests_recent CHECK (requested_at <= now())
);

-- Índices para queries eficientes
CREATE INDEX IF NOT EXISTS idx_password_reset_email_time
  ON public.password_reset_requests(email, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_password_reset_ip_time
  ON public.password_reset_requests(ip_address, requested_at DESC);

-- RLS: Solo service_role puede acceder
ALTER TABLE public.password_reset_requests ENABLE ROW LEVEL SECURITY;

-- No políticas para anon/authenticated = no acceso directo

-- Función para verificar y registrar solicitud de reset
-- Máximo 3 solicitudes por email cada 15 minutos
CREATE OR REPLACE FUNCTION public.check_password_reset_rate_limit(
  p_email text,
  p_ip_address text DEFAULT NULL,
  p_window_seconds int DEFAULT 900,  -- 15 minutos
  p_max_requests int DEFAULT 3
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  recent_count int;
BEGIN
  -- Contar solicitudes recientes para este email
  SELECT COUNT(*) INTO recent_count
  FROM public.password_reset_requests
  WHERE email = p_email::citext
    AND requested_at >= now() - make_interval(secs => p_window_seconds);

  -- Si excede el límite, rechazar
  IF recent_count >= p_max_requests THEN
    RETURN json_build_object(
      'allowed', false,
      'error', 'Demasiadas solicitudes. Intenta de nuevo en 15 minutos.',
      'retry_after_seconds', p_window_seconds
    );
  END IF;

  -- Registrar la solicitud
  INSERT INTO public.password_reset_requests (email, ip_address)
  VALUES (p_email::citext, p_ip_address);

  RETURN json_build_object(
    'allowed', true,
    'remaining', p_max_requests - recent_count - 1
  );
END;
$$;

-- Solo service_role puede ejecutar (se llama desde el backend)
REVOKE EXECUTE ON FUNCTION public.check_password_reset_rate_limit(text, text, int, int) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_password_reset_rate_limit(text, text, int, int) TO service_role;

-- Limpiar registros antiguos (ejecutar periódicamente con pg_cron si está disponible)
CREATE OR REPLACE FUNCTION public.cleanup_password_reset_requests()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  DELETE FROM public.password_reset_requests
  WHERE requested_at < now() - interval '24 hours';
END;
$$;

REVOKE EXECUTE ON FUNCTION public.cleanup_password_reset_requests() FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cleanup_password_reset_requests() TO service_role;

-- ==========================================
-- 2. OTP RATE LIMITING Y LOCKOUT
-- ==========================================

-- Tabla para cooldown entre peticiones OTP
CREATE TABLE IF NOT EXISTS public.auth_otp_cooldowns (
  user_email citext PRIMARY KEY,
  next_allowed_at timestamptz NOT NULL DEFAULT now()
);

-- RLS: Solo service_role
ALTER TABLE public.auth_otp_cooldowns ENABLE ROW LEVEL SECURITY;

-- Tabla para intentos fallidos de OTP
CREATE TABLE IF NOT EXISTS public.auth_otp_attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_email citext NOT NULL,
  ip_address text,
  attempted_at timestamptz NOT NULL DEFAULT now(),
  success boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_otp_attempts_email_time
  ON public.auth_otp_attempts(user_email, attempted_at DESC);

ALTER TABLE public.auth_otp_attempts ENABLE ROW LEVEL SECURITY;

-- Tabla para lockouts
CREATE TABLE IF NOT EXISTS public.auth_otp_lockouts (
  user_email citext PRIMARY KEY,
  locked_until timestamptz NOT NULL,
  failure_count int NOT NULL DEFAULT 0
);

ALTER TABLE public.auth_otp_lockouts ENABLE ROW LEVEL SECURITY;

-- Función para verificar cooldown de OTP (mínimo 30s entre peticiones)
CREATE OR REPLACE FUNCTION public.check_otp_cooldown(
  p_email text,
  p_cooldown_seconds int DEFAULT 30
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  next_allowed timestamptz;
  wait_seconds int;
BEGIN
  -- Verificar si hay cooldown activo
  SELECT next_allowed_at INTO next_allowed
  FROM public.auth_otp_cooldowns
  WHERE user_email = p_email::citext;

  IF next_allowed IS NOT NULL AND now() < next_allowed THEN
    wait_seconds := EXTRACT(EPOCH FROM (next_allowed - now()))::int;
    RETURN json_build_object(
      'allowed', false,
      'error', 'Espera antes de solicitar otro código.',
      'retry_after_seconds', wait_seconds
    );
  END IF;

  -- Actualizar/insertar cooldown
  INSERT INTO public.auth_otp_cooldowns (user_email, next_allowed_at)
  VALUES (p_email::citext, now() + make_interval(secs => p_cooldown_seconds))
  ON CONFLICT (user_email) DO UPDATE
    SET next_allowed_at = now() + make_interval(secs => p_cooldown_seconds);

  RETURN json_build_object('allowed', true);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.check_otp_cooldown(text, int) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_otp_cooldown(text, int) TO service_role;

-- Función para verificar lockout y registrar intentos
CREATE OR REPLACE FUNCTION public.check_otp_lockout(
  p_email text,
  p_ip_address text DEFAULT NULL,
  p_max_failures int DEFAULT 5,
  p_window_seconds int DEFAULT 600,    -- 10 minutos
  p_lockout_seconds int DEFAULT 900    -- 15 minutos lockout
)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  lockout_until timestamptz;
  recent_failures int;
  wait_seconds int;
BEGIN
  -- Verificar si hay lockout activo
  SELECT locked_until INTO lockout_until
  FROM public.auth_otp_lockouts
  WHERE user_email = p_email::citext;

  IF lockout_until IS NOT NULL AND now() < lockout_until THEN
    wait_seconds := EXTRACT(EPOCH FROM (lockout_until - now()))::int;
    RETURN json_build_object(
      'allowed', false,
      'locked', true,
      'error', 'Cuenta temporalmente bloqueada por demasiados intentos fallidos.',
      'retry_after_seconds', wait_seconds
    );
  END IF;

  -- Si el lockout expiró, limpiarlo
  IF lockout_until IS NOT NULL THEN
    DELETE FROM public.auth_otp_lockouts WHERE user_email = p_email::citext;
  END IF;

  -- Contar fallos recientes
  SELECT COUNT(*) INTO recent_failures
  FROM public.auth_otp_attempts
  WHERE user_email = p_email::citext
    AND success = false
    AND attempted_at >= now() - make_interval(secs => p_window_seconds);

  -- Si excede el límite, crear lockout
  IF recent_failures >= p_max_failures THEN
    INSERT INTO public.auth_otp_lockouts (user_email, locked_until, failure_count)
    VALUES (p_email::citext, now() + make_interval(secs => p_lockout_seconds), recent_failures)
    ON CONFLICT (user_email) DO UPDATE
      SET locked_until = now() + make_interval(secs => p_lockout_seconds),
          failure_count = public.auth_otp_lockouts.failure_count + 1;

    RETURN json_build_object(
      'allowed', false,
      'locked', true,
      'error', 'Cuenta temporalmente bloqueada por demasiados intentos fallidos.',
      'retry_after_seconds', p_lockout_seconds
    );
  END IF;

  RETURN json_build_object(
    'allowed', true,
    'attempts_remaining', p_max_failures - recent_failures
  );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.check_otp_lockout(text, text, int, int, int) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.check_otp_lockout(text, text, int, int, int) TO service_role;

-- Función para registrar intento de OTP
CREATE OR REPLACE FUNCTION public.record_otp_attempt(
  p_email text,
  p_success boolean,
  p_ip_address text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.auth_otp_attempts (user_email, ip_address, success)
  VALUES (p_email::citext, p_ip_address, p_success);

  -- Si fue exitoso, limpiar lockout
  IF p_success THEN
    DELETE FROM public.auth_otp_lockouts WHERE user_email = p_email::citext;
  END IF;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.record_otp_attempt(text, boolean, text) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_otp_attempt(text, boolean, text) TO service_role;

-- Limpieza de registros antiguos
CREATE OR REPLACE FUNCTION public.cleanup_otp_records()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  -- Limpiar intentos de más de 24 horas
  DELETE FROM public.auth_otp_attempts
  WHERE attempted_at < now() - interval '24 hours';

  -- Limpiar lockouts expirados
  DELETE FROM public.auth_otp_lockouts
  WHERE locked_until < now();

  -- Limpiar cooldowns expirados
  DELETE FROM public.auth_otp_cooldowns
  WHERE next_allowed_at < now();
END;
$$;

REVOKE EXECUTE ON FUNCTION public.cleanup_otp_records() FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cleanup_otp_records() TO service_role;

-- ==========================================
-- 3. AUDIT LOG (para tracking de seguridad)
-- ==========================================

CREATE TABLE IF NOT EXISTS public.security_audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  action text NOT NULL,
  ip_address text,
  user_agent text,
  details jsonb,

  -- Para búsquedas
  CONSTRAINT security_audit_log_action_check CHECK (action IN (
    'login_success',
    'login_failed',
    'logout',
    'password_change',
    'password_reset_request',
    'otp_request',
    'otp_verify_success',
    'otp_verify_failed',
    'account_locked',
    'suspicious_activity'
  ))
);

CREATE INDEX IF NOT EXISTS idx_security_audit_user
  ON public.security_audit_log(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_audit_action
  ON public.security_audit_log(action, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_audit_ip
  ON public.security_audit_log(ip_address, created_at DESC);

ALTER TABLE public.security_audit_log ENABLE ROW LEVEL SECURITY;

-- Solo admins pueden leer el audit log
CREATE POLICY "Admins can read security audit log"
  ON public.security_audit_log
  FOR SELECT TO authenticated
  USING (is_admin_or_staff());

-- Función para registrar eventos de seguridad
CREATE OR REPLACE FUNCTION public.log_security_event(
  p_action text,
  p_user_id uuid DEFAULT NULL,
  p_ip_address text DEFAULT NULL,
  p_user_agent text DEFAULT NULL,
  p_details jsonb DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.security_audit_log (user_id, action, ip_address, user_agent, details)
  VALUES (COALESCE(p_user_id, auth.uid()), p_action, p_ip_address, p_user_agent, p_details);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.log_security_event(text, uuid, text, text, jsonb) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.log_security_event(text, uuid, text, text, jsonb) TO service_role;

-- ==========================================
-- 4. REVOCAR PERMISOS INNECESARIOS
-- ==========================================

-- Revocar capacidad de crear objetos en schema public
REVOKE CREATE ON SCHEMA public FROM public;

-- Asegurar que anon y authenticated solo tienen lo necesario
GRANT USAGE ON SCHEMA public TO anon, authenticated;

-- ==========================================
-- 5. FUNCIÓN PARA VERIFICAR ORIGEN HTTPS
-- ==========================================

CREATE OR REPLACE FUNCTION public.require_https_origin(p_origin text)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
  -- Permitir localhost en desarrollo
  IF p_origin LIKE 'http://localhost%' OR p_origin LIKE 'http://127.0.0.1%' THEN
    RETURN true;
  END IF;

  -- En producción, requiere HTTPS
  RETURN p_origin IS NOT NULL AND p_origin LIKE 'https://%';
END;
$$;

-- ==========================================
-- COMENTARIOS DE DOCUMENTACIÓN
-- ==========================================

COMMENT ON TABLE public.password_reset_requests IS
  'Tracking de solicitudes de reset de contraseña para rate limiting';

COMMENT ON TABLE public.auth_otp_cooldowns IS
  'Cooldowns entre peticiones OTP para prevenir timing attacks';

COMMENT ON TABLE public.auth_otp_attempts IS
  'Registro de intentos de verificación OTP';

COMMENT ON TABLE public.auth_otp_lockouts IS
  'Lockouts de cuentas tras múltiples intentos fallidos';

COMMENT ON TABLE public.security_audit_log IS
  'Log de eventos de seguridad para auditoría';

COMMENT ON FUNCTION public.check_password_reset_rate_limit IS
  'Verifica y registra solicitudes de reset - máx 3/15min por email';

COMMENT ON FUNCTION public.check_otp_cooldown IS
  'Verifica cooldown de OTP - mínimo 30s entre peticiones';

COMMENT ON FUNCTION public.check_otp_lockout IS
  'Verifica lockout de cuenta - bloqueo tras 5 fallos en 10min';

COMMENT ON FUNCTION public.log_security_event IS
  'Registra eventos de seguridad en el audit log';

-- ==========================================
-- NOTAS DE IMPLEMENTACIÓN
-- ==========================================
--
-- Para usar estas funciones desde tu API de Next.js:
--
-- 1. Password Reset:
--    const { data } = await supabase.rpc('check_password_reset_rate_limit', {
--      p_email: email,
--      p_ip_address: req.ip
--    })
--    if (!data.allowed) return error(429, data.error)
--
-- 2. OTP Request:
--    const { data: cooldown } = await supabase.rpc('check_otp_cooldown', { p_email: email })
--    if (!cooldown.allowed) return error(429, cooldown.error)
--    const { data: lockout } = await supabase.rpc('check_otp_lockout', { p_email: email })
--    if (!lockout.allowed) return error(423, lockout.error)
--
-- 3. OTP Verify (después de verificar):
--    await supabase.rpc('record_otp_attempt', {
--      p_email: email,
--      p_success: wasSuccessful
--    })
--
-- 4. Logging:
--    await supabase.rpc('log_security_event', {
--      p_action: 'login_success',
--      p_ip_address: req.ip,
--      p_user_agent: req.headers['user-agent']
--    })
--
-- ==========================================
