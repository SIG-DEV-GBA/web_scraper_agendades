# Arquitectura Definitiva - Agendades Web Scraper

## 1. Objetivo Principal

Maximizar la calidad de datos para rellenar el **100% de los campos** de la base de datos, manteniendo una arquitectura limpia, escalable y lista para exportar a microservicio/API.

---

## 2. Esquema de Base de Datos - Campos a Rellenar

### 2.1 Tabla Principal: `events`

| Campo | Tipo | Fuente de Datos | Prioridad |
|-------|------|-----------------|-----------|
| `title` | varchar | Scraper (directo) | **Requerido** |
| `slug` | varchar | Auto-generado desde title | Auto |
| `description` | text | Scraper + LLM enriquecimiento | Alta |
| `summary` | varchar | LLM (genera resumen corto) | Media |
| `start_date` | date | Scraper (directo) | **Requerido** |
| `end_date` | date | Scraper (directo) | Alta |
| `start_time` | time | Scraper (parsear de texto) | Media |
| `end_time` | time | Scraper (parsear de texto) | Baja |
| `modality` | enum | Scraper (presencial/online/hibrido) | Alta |
| `is_free` | boolean | Scraper + LLM inferencia | Alta |
| `price` | numeric | Scraper (extraer de texto) | Media |
| `price_info` | text | Scraper (texto completo) | Alta |
| `image_url` | text | Scraper + Unsplash fallback | Alta |
| `source_image_url` | text | Scraper (URL original) | Alta |
| `external_url` | text | Scraper (directo) | Alta |
| `external_id` | varchar | Scraper (para deduplicacion) | **Requerido** |
| `source_id` | uuid | Resuelto de scraper_sources | **Requerido** |

### 2.2 Tabla: `event_locations` (1:1 con events)

| Campo | Tipo | Fuente de Datos | Prioridad |
|-------|------|-----------------|-----------|
| `name` | varchar | Scraper (venue_name) | Alta |
| `address` | text | Scraper (direccion completa) | Media |
| `city` | varchar | Scraper + Geocoder | **Requerido** |
| `municipio` | varchar | Scraper o = city | Media |
| `province` | varchar | Scraper + CCAA mapping | Alta |
| `comunidad_autonoma` | text | Desde adapter.ccaa | **Requerido** |
| `postal_code` | varchar | Scraper | Baja |
| `country` | varchar | Default "Espana" | Auto |
| `latitude` | numeric | Geocoder (Nominatim) | Alta |
| `longitude` | numeric | Geocoder (Nominatim) | Alta |
| `details` | text | Scraper (parking, acceso, etc) | Baja |

### 2.3 Tabla: `event_organizers` (1:1 con events)

| Campo | Tipo | Fuente de Datos | Prioridad |
|-------|------|-----------------|-----------|
| `name` | varchar | Scraper | Alta |
| `type` | enum | LLM inferencia (empresa/asociacion/institucion/otro) | Media |
| `url` | text | Scraper | Baja |
| `logo_url` | text | Scraper | Baja |

### 2.4 Tabla: `event_contact` (1:1 con events)

| Campo | Tipo | Fuente de Datos | Prioridad |
|-------|------|-----------------|-----------|
| `name` | varchar | Scraper (persona de contacto) | Baja |
| `email` | varchar | Scraper (extraer de texto) | Media |
| `phone` | varchar | Scraper (extraer de texto) | Media |
| `info` | text | Scraper (horarios contacto, etc) | Baja |

### 2.5 Tabla: `event_registration` (1:1 con events)

| Campo | Tipo | Fuente de Datos | Prioridad |
|-------|------|-----------------|-----------|
| `requires_registration` | boolean | Scraper/LLM | Media |
| `registration_url` | text | Scraper (URL entradas/reserva) | Alta |
| `registration_info` | text | Scraper (como inscribirse si no hay URL) | Media |
| `registration_deadline` | timestamp | Scraper (fecha limite) | Baja |
| `max_attendees` | integer | Scraper | Baja |

### 2.6 Tabla: `event_accessibility` (1:1 con events)

| Campo | Tipo | Fuente de Datos | Prioridad |
|-------|------|-----------------|-----------|
| `wheelchair_accessible` | boolean | Scraper/LLM | Media |
| `sign_language` | boolean | Scraper/LLM | Baja |
| `hearing_loop` | boolean | Scraper/LLM | Baja |
| `braille_materials` | boolean | Scraper/LLM | Baja |
| `other_facilities` | text | Scraper | Baja |
| `notes` | text | Scraper | Baja |

### 2.7 Tabla: `event_categories` (N:M con events)

| Campo | Tipo | Fuente de Datos | Prioridad |
|-------|------|-----------------|-----------|
| `category_id` | uuid | LLM asigna slugs -> resolve a UUID | Alta |
| `is_primary` | boolean | Primera categoria = primaria | Auto |

---

## 3. Arquitectura de Adapters

### 3.1 Estructura de Carpetas

```
src/adapters/
├── __init__.py              # Registry y auto-import
├── gold/
│   ├── __init__.py
│   ├── base_gold_adapter.py # Clase base para APIs Gold
│   └── configs/
│       ├── madrid.py        # GoldSourceConfig para Madrid
│       ├── catalunya.py
│       ├── euskadi.py
│       ├── castilla_leon.py
│       ├── andalucia.py
│       ├── valencia.py
│       └── zaragoza.py
├── silver/
│   ├── __init__.py
│   ├── base_silver_adapter.py # Clase base para RSS/iCal
│   └── configs/
│       ├── galicia.py       # RSSSourceConfig
│       ├── huesca.py
│       └── cantabria.py
└── bronze/
    ├── __init__.py
    ├── base_bronze_adapter.py # Clase base para scraping HTML
    ├── navarra.py            # Adapter completo (ya migrado)
    ├── viralagenda/
    │   ├── __init__.py
    │   ├── base.py           # ViralAgendaAdapter base
    │   └── configs/          # Config por CCAA
    │       ├── andalucia.py
    │       ├── aragon.py
    │       └── ...
    └── otros/
        └── eventbrite.py
```

### 3.2 Jerarquia de Clases

```
BaseAdapter (abstracta)
├── GoldAPIAdapter
│   ├── MadridAdapter (config-driven)
│   ├── CatalunyaAdapter (config-driven)
│   └── ...
├── SilverRSSAdapter
│   ├── GaliciaAdapter (config-driven)
│   └── ...
└── BronzeScraperAdapter
    ├── NavarraAdapter (custom)
    ├── ViralAgendaAdapter (base para todas las CCAA)
    └── EventbriteAdapter (custom)
```

### 3.3 BaseAdapter - Metodos Requeridos

```python
class BaseAdapter(ABC):
    # Identificacion
    source_id: str          # e.g., "madrid_datos_abiertos"
    source_name: str        # e.g., "Madrid Datos Abiertos"
    source_url: str         # URL principal
    ccaa: str               # "Comunidad de Madrid"
    ccaa_code: str          # "MD"
    adapter_type: AdapterType  # API, RSS, STATIC, DYNAMIC

    @abstractmethod
    async def fetch_events(self, **kwargs) -> list[dict]:
        """Obtener eventos raw del origen."""
        pass

    @abstractmethod
    def parse_event(self, raw_data: dict) -> EventCreate | None:
        """Convertir evento raw a EventCreate."""
        pass
```

---

## 4. Pipeline de Procesamiento

### 4.1 Flujo Completo

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐
│   SCRAPE    │───▸│    PARSE     │───▸│   ENRICH     │───▸│   INSERT    │
│  (Adapter)  │    │ (EventCreate)│    │  (LLM+Geo)   │    │ (Supabase)  │
└─────────────┘    └──────────────┘    └──────────────┘    └─────────────┘
      │                   │                   │                   │
      ▼                   ▼                   ▼                   ▼
 Raw dicts           Eventos           Eventos con:        - events
 del origen          validados         - Categorias        - event_locations
                                       - Summary           - event_organizers
                                       - Precio            - event_categories
                                       - Coords            - event_contact
                                       - Imagen            - event_registration
```

### 4.2 Modulo: LLM Enricher

**Responsabilidades:**
1. Asignar `category_slugs` (1-3 categorias de las 8 disponibles)
2. Generar `summary` (2-3 frases)
3. Inferir `is_free` / `price` del texto
4. Generar `image_keywords` para Unsplash
5. Inferir `organizer_type`

**Modelo por Tier:**
- **Gold**: groq/llama-3.3-70b (datos limpios, batch grande)
- **Silver**: groq/llama-3.3-70b (semi-estructurado)
- **Bronze**: groq/llama-3.3-70b o kimi-k2 (datos caoticos)

### 4.3 Modulo: Geocoder

**Responsabilidades:**
1. Convertir `venue_name + city + province` -> `latitude, longitude`
2. Validar/corregir `comunidad_autonoma`
3. Cache en SQLite para evitar llamadas repetidas

**Proveedor:** Nominatim (OpenStreetMap) - gratuito, rate-limited

### 4.4 Modulo: Image Resolver

**Responsabilidades:**
1. Si evento no tiene imagen -> buscar en Unsplash
2. Usar `image_keywords` del LLM + `category_name`
3. Guardar atribucion (`image_author`, `image_author_url`, `image_source_url`)

---

## 5. Extraccion de Datos por Campo

### 5.1 Campos de Texto Libre

Para maximizar datos de texto libre (description, price_info, etc):

1. **Gold APIs**: Usar `clean_html()` para limpiar HTML y preservar estructura
2. **RSS/iCal**: Parsear HTML del `summary` o `content:encoded`
3. **Bronze HTML**: Scrape de paginas de detalle

### 5.2 Extraccion de Contacto

```python
def extract_contact(text: str) -> EventContact:
    """Extraer email y telefono de texto libre."""
    email = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
    phone = re.search(r'(?:\+34\s?)?(?:9[0-9]{2}[\s.-]?[0-9]{3}[\s.-]?[0-9]{3})', text)
    return EventContact(email=email, phone=phone)
```

### 5.3 Extraccion de Precio

```python
def extract_price(text: str) -> tuple[bool | None, float | None, str]:
    """Extraer is_free, precio numerico, y texto descriptivo."""
    # Detectar "gratuito", "gratis", etc -> is_free=True
    # Detectar "X€", "X euros" -> price=X, is_free=False
    # Detectar "entrada libre" -> ambiguo, usar LLM
```

### 5.4 Extraccion de Registro

```python
def extract_registration(text: str, urls: list[str]) -> dict:
    """Extraer info de registro/entradas."""
    # Buscar URLs de entradas (secutix, ticketmaster, eventbrite, etc)
    # Detectar "inscripcion previa", "reserva obligatoria"
    # Extraer fecha limite si existe
```

---

## 6. Deduplicacion

### 6.1 Dentro de la Misma Fuente

- Usar `external_id` unico por fuente
- Formato: `{source_id}_{id_original}` o `{source_id}_{hash_titulo_fecha}`

### 6.2 Cross-Source (Opcional)

- Buscar eventos similares por `title + city + start_date`
- Si match > 80%: mergear datos (llenar campos vacios)
- Registrar en `event_source_contributions` para tracking

---

## 7. Tabla: scraper_sources

Cada adapter debe tener un registro en `scraper_sources`:

```sql
INSERT INTO scraper_sources (slug, name, ccaa, ccaa_code, source_url, adapter_type)
VALUES
('madrid_datos_abiertos', 'Madrid Datos Abiertos', 'Comunidad de Madrid', 'MD', 'https://datos.madrid.es/...', 'api'),
('navarra_cultura', 'Cultura Navarra', 'Navarra', 'NA', 'https://www.culturanavarra.es/...', 'static'),
('viralagenda_andalucia', 'Viralagenda Andalucia', 'Andalucia', 'AN', 'https://www.viralagenda.com/es/andalucia', 'dynamic');
```

---

## 8. Configuracion de Fuentes Actual

### Gold (7 fuentes)
- `madrid_datos_abiertos` - JSON-LD
- `catalunya_agenda` - Socrata/SODA
- `euskadi_kulturklik` - REST API
- `castilla_leon_agenda` - CKAN OData
- `andalucia_agenda` - CKAN
- `valencia_ivc` - JSON (desactualizado 2025)
- `zaragoza_cultura` - JSON

### Silver (3 fuentes)
- `galicia_cultura` - RSS
- `huesca_radar` - MEC RSS
- `cantabria_turismo` - iCal

### Bronze (1 migrado + pendientes)
- `navarra_cultura` - HTML estatico (migrado)
- `viralagenda_*` - HTML dinamico (17 CCAA) - pendiente

---

## 9. Plan de Migracion

### Fase 1: Consolidar Bronze/Viralagenda
1. Crear `BronzeScraperAdapter` base
2. Migrar Viralagenda a nueva estructura
3. Testear con proxy Geonode

### Fase 2: Mejorar Extraccion de Datos
1. Implementar `extract_contact()` en todos los adapters
2. Implementar `extract_registration()`
3. Mejorar `extract_price()` para casos edge

### Fase 3: Completar Coverage
1. Asegurar que todos los adapters rellenan:
   - `event_contact` (email, phone)
   - `event_registration` (URL, info)
   - `event_organizers` (name, type)
2. Implementar fetch de detalles donde falte

### Fase 4: Exportar a API
1. Crear endpoints REST para:
   - GET /events
   - GET /events/{id}
   - GET /events/search
   - GET /sources
2. Documentar con OpenAPI/Swagger

---

## 10. Comandos de Ejecucion

```bash
# Pipeline unificado
python scripts/run_pipeline.py --source navarra_cultura --no-dry-run
python scripts/run_pipeline.py --tier gold --no-dry-run
python scripts/run_pipeline.py --ccaa madrid --no-dry-run --limit 50
python scripts/run_pipeline.py --all --dry-run

# Listar fuentes disponibles
python scripts/run_pipeline.py --list

# Opciones
--no-llm          # Deshabilitar enriquecimiento LLM
--no-images       # Deshabilitar Unsplash
--no-details      # No fetch paginas de detalle
--limit N         # Limitar eventos (testing)
```

---

## 11. Metricas de Calidad

Para cada batch de insercion, trackear:

| Metrica | Objetivo |
|---------|----------|
| % eventos con description | > 90% |
| % eventos con image_url | > 80% |
| % eventos con coordinates | > 70% |
| % eventos con category_slugs | > 95% |
| % eventos con organizer | > 50% |
| % eventos con contact | > 30% |
| % eventos con registration_url | > 20% |

---

## 12. Proximos Pasos Inmediatos

1. **Verificar proxy Geonode** funciona con Viralagenda
2. **Migrar Viralagenda** a nueva estructura bronze/
3. **Implementar extraccion de contacto** en parse_event()
4. **Crear script de auditoria** de coverage por fuente
5. **Documentar todas las fuentes** en scraper_sources
