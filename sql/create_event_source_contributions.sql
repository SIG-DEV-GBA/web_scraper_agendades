-- Tabla para tracking de fuentes que contribuyeron a cada evento
-- Permite saber qué fuentes aportaron datos a un evento mergeado

CREATE TABLE IF NOT EXISTS event_source_contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES scraper_sources(id) ON DELETE CASCADE,
    external_id TEXT,  -- ID original del evento en esa fuente
    external_url TEXT,  -- URL original del evento en esa fuente
    contributed_at TIMESTAMPTZ DEFAULT NOW(),
    fields_contributed TEXT[] DEFAULT '{}',  -- campos que aportó: ['description', 'image_url']
    quality_score INTEGER DEFAULT 0,  -- score de calidad de esta contribución
    is_primary BOOLEAN DEFAULT FALSE,  -- si es la fuente principal (primera en insertar)

    UNIQUE(event_id, source_id)
);

-- Índices para queries frecuentes
CREATE INDEX IF NOT EXISTS idx_event_source_contributions_event
    ON event_source_contributions(event_id);

CREATE INDEX IF NOT EXISTS idx_event_source_contributions_source
    ON event_source_contributions(source_id);

CREATE INDEX IF NOT EXISTS idx_event_source_contributions_primary
    ON event_source_contributions(event_id) WHERE is_primary = TRUE;

-- Comentarios
COMMENT ON TABLE event_source_contributions IS
    'Tracking de qué fuentes contribuyeron datos a cada evento (para deduplicación cross-source)';

COMMENT ON COLUMN event_source_contributions.fields_contributed IS
    'Lista de campos que esta fuente aportó al evento: description, image_url, price_info, etc.';

COMMENT ON COLUMN event_source_contributions.is_primary IS
    'TRUE si esta fue la primera fuente que insertó el evento';
