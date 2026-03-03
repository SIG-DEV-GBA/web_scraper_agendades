# AGENDADES Web Scraper

Sistema de scraping multi-fuente para eventos culturales de España. Recopila, enriquece con IA y almacena eventos de las 17 Comunidades Autónomas en Supabase.

**Producción:** https://api-scraper.si-erp.cloud
**Swagger:** https://api-scraper.si-erp.cloud/docs
**Dashboard:** https://scraper.agendades.es

---

## Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│                      AGENDADES SCRAPER                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐      │
│  │   GOLD (9)   │  │  SILVER (3)  │  │  BRONZE (69)  │      │
│  │  APIs REST   │  │  RSS/iCal    │  │  Web Scraping │      │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘      │
│         └─────────────────┼───────────────────┘              │
│                           ▼                                  │
│              ┌─────────────────────┐                         │
│              │  Unified Pipeline   │                         │
│              │  (InsertionPipeline)│                         │
│              └──────────┬──────────┘                         │
│                         │                                    │
│         ┌───────────────┼───────────────┐                    │
│         ▼               ▼               ▼                    │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │ LLM Enricher│ │   Image     │ │  Dedup +    │            │
│  │ (Groq/OAI)  │ │  Resolver   │ │  Geocoding  │            │
│  └─────────────┘ │ (Unsplash)  │ └──────┬──────┘            │
│                  └─────────────┘        │                    │
│                                         ▼                    │
│                               ┌─────────────────┐           │
│                               │    SUPABASE      │           │
│                               │   (PostgreSQL)   │           │
│                               └─────────────────┘           │
│                                                              │
│  ┌──────────────────────────────────────────────────┐        │
│  │  FastAPI + Security (CORS, Auth, Rate Limiting)  │        │
│  └──────────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────────┘
```

### Tiers de Fuentes

| Tier | Fuentes | Método | Ejemplo |
|------|---------|--------|---------|
| **Gold** (9) | APIs REST oficiales | httpx directo | Catalunya, Euskadi, Madrid, CyL |
| **Silver** (3) | Feeds semi-estructurados | RSS/iCal/Tavily | Galicia, Huesca, Barcelona Activa |
| **Bronze** (69) | Web scraping | Firecrawl/BeautifulSoup/Playwright | Viralagenda (44 provincias), CLM, Navarra |

**Total: 81 fuentes activas — 17 CCAAs — ~2500+ eventos en DB**

---

## Estructura del Proyecto

```
AGENDADES_WEB_SCRAPPER/
├── src/
│   ├── adapters/                     # Adaptadores por tier
│   │   ├── __init__.py               # Registry (list_adapters, get_adapter)
│   │   ├── gold_api_adapter.py       # 9 fuentes Gold (APIs REST)
│   │   ├── silver_rss_adapter.py     # 3 fuentes Silver (RSS/iCal)
│   │   ├── bronze_scraper_adapter.py # Scraper genérico Bronze
│   │   ├── eventbrite_adapter.py     # Eventbrite
│   │   └── bronze/                   # 21 adaptadores Bronze individuales
│   │       ├── viralagenda/          #   Viralagenda (44 provincias)
│   │       ├── cnt_agenda.py         #   CNT Agenda
│   │       ├── defensor_pueblo.py    #   Defensor del Pueblo
│   │       ├── segib.py              #   SEGIB
│   │       ├── horizonte_europa.py   #   Horizonte Europa
│   │       ├── la_moncloa.py         #   La Moncloa
│   │       └── ...                   #   +15 más
│   │
│   ├── api/                          # API REST (FastAPI)
│   │   ├── main.py                   # App + CORS + Rate Limiting + Security
│   │   ├── auth.py                   # API Key authentication
│   │   └── routes/
│   │       ├── sources.py            # GET /sources/*
│   │       ├── scrape.py             # POST /scrape, batch endpoints
│   │       ├── runs.py               # GET /runs/stats, quality, recent
│   │       ├── scheduler.py          # POST /scheduler/pause,resume,trigger
│   │       └── dev.py                # POST /dev/revalidate
│   │
│   ├── core/                         # Núcleo del sistema
│   │   ├── base_adapter.py           # Clase base adaptadores
│   │   ├── pipeline.py               # InsertionPipeline (unificado)
│   │   ├── event_model.py            # Modelos Pydantic
│   │   ├── db/                       # Cliente Supabase (modular)
│   │   │   ├── client.py             # Facade principal
│   │   │   ├── event_store.py        # CRUD eventos
│   │   │   ├── relations.py          # Locations, organizers, etc.
│   │   │   ├── event_builder.py      # Preparación de datos
│   │   │   └── audit.py              # Hash + audit log
│   │   ├── supabase_client.py        # Re-export shim (retrocompat)
│   │   ├── llm_enricher.py           # Enriquecimiento LLM
│   │   ├── image_resolver.py         # Unsplash API
│   │   ├── geocoder.py               # Geocodificación
│   │   └── embeddings.py             # Embeddings vectoriales
│   │
│   ├── config/
│   │   ├── settings.py               # Configuración (.env)
│   │   └── sources/                  # SourceRegistry centralizado
│   │       ├── __init__.py            # BronzeSourceConfig, SourceRegistry
│   │       ├── gold_sources.py
│   │       ├── silver_sources.py
│   │       └── bronze_sources.py
│   │
│   ├── utils/                        # Utilidades
│   │   ├── text.py                   # Limpieza de texto
│   │   ├── date_parser.py            # Parseo fechas españolas + MONTHS_ES
│   │   ├── ids.py                    # make_external_id() centralizado
│   │   ├── urls.py                   # Manejo URLs
│   │   ├── locations.py              # Provincias/CCAA
│   │   └── cross_source_dedup.py     # Deduplicación cross-source
│   │
│   ├── cli/                          # CLI (Typer)
│   │   └── main.py
│   │
│   └── scheduler/                    # Scheduler (APScheduler)
│       └── cron.py
│
├── tests/                            # Tests (273 passing)
│   ├── test_external_ids.py          # 71 tests: ID generation
│   ├── test_date_formats.py          # 100 tests: date parsing
│   ├── test_pipeline_unit.py         # 44 tests: pipeline logic
│   ├── test_adapters.py              # Adapter registry
│   ├── test_cross_source_dedup.py    # Deduplication
│   └── fixtures/bronze/              # 9 HTML fixtures
│
├── Dockerfile                        # Producción (python:3.11-slim)
├── requirements.txt
├── SECURITY_GUIDELINES.md            # Guía de seguridad del proyecto
└── CLAUDE.md                         # Instrucciones para agentes IA
```

---

## Instalación

### Requisitos

- Python 3.11+
- Supabase account
- API Keys: Groq, Unsplash, Firecrawl

### Setup

```bash
git clone https://github.com/SIG-DEV-GBA/web_scraper_agendades.git
cd AGENDADES_WEB_SCRAPPER

python -m venv .venv
source .venv/bin/activate    # Linux/Mac
.venv\Scripts\activate       # Windows

pip install -r requirements.txt
cp .env.example .env         # Editar con tus API keys
```

---

## Configuración

### Variables de Entorno

```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# LLM
GROQ_API_KEY=gsk_...
OPENAI_API_KEY=sk-...

# Imágenes
UNSPLASH_ACCESS_KEY=...

# Scraping
FIRECRAWL_API_KEY=fc-...
TAVILY_API_KEY=tvly-...

# Seguridad API
SCRAPER_API_KEY=...                    # API key para endpoints admin
ALLOWED_ORIGINS=https://scraper.agendades.es,http://localhost:3000
ALLOWED_HOSTS=                         # TrustedHost (vacío = desactivado)

# Opcionales
PUBLIC_CALENDAR_ID=...                 # UUID calendario público (tiene fallback)
SCRAPER_BOT_USER_ID=...               # UUID bot (tiene fallback)
```

---

## API REST

### Iniciar servidor

```bash
uvicorn src.api.main:app --reload --port 8000
```

### Seguridad

- **CORS**: Solo orígenes permitidos (configurable via `ALLOWED_ORIGINS`)
- **Auth**: Endpoints POST/DELETE requieren header `X-API-Key`
- **Rate Limiting**: 120 requests/minuto por IP (slowapi)
- **Security Headers**: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy

### Endpoints Públicos (sin API key)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Health check básico |
| GET | `/health` | Health detallado (DB status, event count) |
| GET | `/sources` | Listar las 81 fuentes |
| GET | `/sources/by-tier/{tier}` | Filtrar por tier (gold/silver/bronze) |
| GET | `/sources/by-ccaa/{ccaa}` | Filtrar por CCAA |
| GET | `/sources/{slug}` | Detalle de fuente + events_in_db |
| GET | `/scrape/ccaas` | 17 CCAAs con sus fuentes |
| GET | `/scrape/provinces` | Provincias con sus fuentes |
| GET | `/scrape/tiers` | Tiers con counts |
| GET | `/scrape/preview/{slug}?limit=N` | Preview sin insertar |
| GET | `/scrape/status/{job_id}` | Estado completo del job + logs |
| GET | `/scrape/status/{job_id}/logs?since=N` | Logs incrementales (polling) |
| GET | `/scrape/jobs?limit=20` | Historial de jobs |
| GET | `/runs/stats` | Estadísticas globales |
| GET | `/runs/quality?limit=100` | Métricas de calidad |
| GET | `/runs/recent?limit=20&source=slug` | Eventos recientes |
| GET | `/runs/by-date?days=7` | Eventos por fecha de inserción |
| GET | `/scheduler` | Estado del scheduler |
| GET | `/scheduler/last-run` | Último run |

### Endpoints Protegidos (requieren `X-API-Key`)

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| POST | `/scrape` | `{sources?, tier?, province?, ccaa?, limit: 1-100, dry_run}` | Lanzar scrape job |
| DELETE | `/scrape/jobs/{job_id}` | — | Borrar job completado |
| POST | `/scrape/batch/full` | `{limit: 1-200, dry_run, tier?}` | Scrape completo (todas las fuentes) |
| POST | `/scrape/batch/viralagenda` | `{limit: 1-100, min_events, dry_run}` | Batch viralagenda |
| POST | `/scheduler/pause` | — | Pausar scheduler |
| POST | `/scheduler/resume` | — | Reanudar scheduler |
| POST | `/scheduler/trigger` | — | Trigger manual |
| POST | `/dev/revalidate` | — | Invalidar cache web |

### Ejemplo de uso

```bash
# Scrape de una fuente (con API key)
curl -X POST https://api-scraper.si-erp.cloud/scrape \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SCRAPER_API_KEY" \
  -d '{"sources": ["segib"], "limit": 10, "dry_run": true}'

# Scrape completo semanal
curl -X POST https://api-scraper.si-erp.cloud/scrape/batch/full \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SCRAPER_API_KEY" \
  -d '{"limit": 100}'

# Consultar estado del job
curl https://api-scraper.si-erp.cloud/scrape/status/{job_id}
```

---

## CLI

```bash
# Scrape por tier
python -m src.cli insert --tier gold --limit 50

# Por CCAA
python -m src.cli insert --ccaa "Castilla y León" --limit 30

# Fuente específica
python -m src.cli insert --source viralagenda_sevilla --limit 10

# Dry run
python -m src.cli insert --source segib --limit 5 --dry-run
```

---

## Pipeline de Procesamiento

```
Fuente → Adapter.fetch_events() → Raw Events
  → parse + filter (fecha >= hoy)
  → filter_existing (dedup por external_id)
  → LLM Enricher (categorías, summary, is_free, keywords)
  → Image Resolver (Unsplash si no tiene imagen)
  → Geocoding + Embeddings
  → Supabase INSERT/UPDATE
```

Cada fuente se procesa secuencialmente. Los jobs se ejecutan en background y se puede monitorizar en tiempo real via `GET /scrape/status/{id}/logs?since=N`.

---

## Deployment

### Docker (Producción)

```bash
docker build -t agendades-scraper .
docker run -p 8000:8000 --env-file .env agendades-scraper
```

### VPS (Dokploy)

El proyecto se despliega automáticamente via Dokploy al hacer push a `main`.

**Cron semanal** (Dokploy scheduled task):
```
Schedule: 0 1 * * 3 (miércoles 01:00)
Script: curl -s -X POST "https://api-scraper.si-erp.cloud/scrape/batch/full" -H "Content-Type: application/json" -H "X-API-Key: $SCRAPER_API_KEY" -d '{"limit": 100}'
```

---

## Tests

```bash
pytest tests/ -v
# 273 tests passing (IDs, fechas, pipeline)
```

---

## Seguridad

Ver [SECURITY_GUIDELINES.md](SECURITY_GUIDELINES.md) para:
- Audit de vulnerabilidades
- Reglas de código seguro
- Checklist por fase
- Patrones de referencia

---

## Licencia

MIT License - Ver [LICENSE](LICENSE)
