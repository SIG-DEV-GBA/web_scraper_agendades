# Guia de Seguridad del Agente - AGENDADES Web Scrapper

> **ESTE DOCUMENTO ES OBLIGATORIO** para cualquier agente que trabaje en este proyecto.
> Debe leerse ANTES de hacer cambios en codigo.

---

## 0. Protocolo de Inicio (OBLIGATORIO)

Antes de cualquier tarea, el agente DEBE ejecutar estos pasos en orden:

### Paso 1: Cargar contexto
```
mind_recall()
```

### Paso 2: Cargar skills de seguridad
El agente debe tener disponibles y consultar estas skills instaladas:

| Skill | Ruta | Cuando usar |
|-------|------|-------------|
| **owasp-security-check** | `~/.agents/skills/owasp-security-check/SKILL.md` | Auditar cualquier endpoint o modulo web |
| **api-security-hardening** | `~/.agents/skills/api-security-hardening/SKILL.md` | Al modificar/crear rutas FastAPI |
| **sql-injection-prevention** | `~/.agents/skills/sql-injection-prevention/SKILL.md` | Al tocar queries a Supabase/Postgres |
| **security-fastapi** | `~/.agents/skills/security-fastapi/SKILL.md` | Hardening especifico de FastAPI |
| **code-refactoring** | `~/.agents/skills/code-refactoring/SKILL.md` | Antes de refactorizar cualquier modulo |
| **python-code-style** | `~/.agents/skills/python-code-style/SKILL.md` | Convenciones de codigo Python |

**Skills ya disponibles en el proyecto (pre-instaladas):**
- `supabase-postgres-best-practices` - Optimizacion y seguridad Postgres/Supabase
- `systematic-debugging` - Debugging sistematico
- `async-python-patterns` - Patrones async Python

### Paso 3: Leer este documento completo

---

## 1. Audit de Seguridad Actual (Estado: 2026-03-02)

### 1.1 Hallazgos Positivos (ya implementado correctamente)

| Area | Estado | Detalle |
|------|--------|---------|
| SQL Injection | SEGURO | Todas las queries usan Supabase SDK parametrizado (.eq(), .in_(), .insert(), etc.) |
| String interpolation en DB | SEGURO | CERO instancias de f-strings o .format() en queries |
| Validacion de tipos | PARCIAL | Pydantic models en POST requests, Query params con tipos |
| Range validation | PARCIAL | Algunos params tienen ge/le (limit, days), otros no |
| Audit logging | SEGURO | Tabla audit_logs para tracking de cambios |
| Content hashing | SEGURO | SHA256 para deduplicacion de eventos |
| Secrets management | SEGURO | Variables de entorno, no hardcoded |

### 1.2 Vulnerabilidades Encontradas

#### CRITICA: CORS Permisivo + Credenciales
- **Archivo**: `src/api/main.py:46`
- **Problema**: `allow_origins=["*"]` con `allow_credentials=True`
- **Riesgo**: Cualquier sitio web puede hacer requests autenticados a la API
- **Solucion**:
```python
# ANTES (VULNERABLE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DESPUES (SEGURO)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://agendades.es,https://www.agendades.es").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)
```

#### CRITICA: Endpoints Administrativos Sin Autenticacion
- **Archivos afectados**:
  - `src/api/routes/scheduler.py:23,30,37` — pause/resume/trigger
  - `src/api/routes/dev.py:18` — cache revalidation
  - `src/api/routes/scrape.py:265` — crear scrape jobs
  - `src/api/routes/scrape.py:399` — borrar jobs
- **Riesgo**: DoS, creacion masiva de jobs, eliminacion de datos
- **Solucion**: Implementar API Key auth:
```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
import secrets

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def require_api_key(api_key: str = Security(API_KEY_HEADER)):
    expected = os.getenv("SCRAPER_API_KEY")
    if not expected or not secrets.compare_digest(api_key or "", expected):
        raise HTTPException(status_code=403, detail="Forbidden")
    return api_key

# Uso en endpoints administrativos:
@router.post("/pause")
async def pause_scheduler(_: str = Depends(require_api_key)):
    ...
```

#### MEDIA: Fuga de Informacion en Errores
- **Archivos afectados**:
  - `src/api/routes/sources.py:154` — `detail=str(e)`
  - `src/api/routes/scrape.py:536` — `error=str(e)`
  - `src/api/routes/dev.py:47,56` — errores externos expuestos
  - `src/api/main.py:82` — errores DB en /health
- **Riesgo**: Expone schema DB, rutas internas, claves API en mensajes de error
- **Solucion**:
```python
# ANTES (VULNERABLE)
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))

# DESPUES (SEGURO)
except Exception as e:
    logger.error("operation_failed", error=str(e), exc_info=True)
    raise HTTPException(status_code=500, detail="Error interno del servidor")
```

#### MEDIA: Sin Rate Limiting
- **Problema**: Ningun endpoint tiene rate limiting
- **Riesgo**: DoS, abuso de scraping, sobrecarga de DB
- **Solucion**:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Endpoints publicos
@router.get("/sources")
@limiter.limit("60/minute")
async def list_sources(request: Request): ...

# Endpoints administrativos (ya protegidos por API key)
@router.post("/scrape")
@limiter.limit("10/minute")
async def create_scrape(request: Request): ...
```

#### BAJA: Validacion Laxa de Parametros
- **Archivos**: `sources.py:69` (tier), `scrape.py:283` (province/ccaa)
- **Problema**: Acepta cualquier string, matching parcial
- **Riesgo**: Menor — solo matchea contra registry, no va a DB directamente
- **Solucion**: Validar contra enum/lista conocida

---

## 2. Reglas de Seguridad para Refactorizacion

### Regla 1: Nunca introducir SQL injection
Al refactorizar queries de Supabase:
- **SIEMPRE** usar metodos parametrizados del SDK: `.eq()`, `.in_()`, `.like()`, `.gte()`, `.insert()`, `.update()`
- **NUNCA** construir queries con f-strings, .format(), o concatenacion
- **NUNCA** pasar input de usuario directamente a `.rpc()` sin validar
- Si necesitas query dinamica (column name variable), usar whitelist:
```python
ALLOWED_COLUMNS = {"start_date", "title", "source", "comunidad_autonoma"}
if column not in ALLOWED_COLUMNS:
    raise ValueError(f"Column not allowed: {column}")
```

### Regla 2: Validar toda entrada externa
- Requests HTTP: Pydantic BaseModel con Field(ge=, le=, max_length=, regex=)
- Path params: Validar contra enum o lista conocida
- Query params: Tipos explicitos + rangos
```python
# CORRECTO
limit: int = Query(20, ge=1, le=100, description="Max results")
tier: SourceTier = Query(..., description="Source tier")  # Enum validation

# INCORRECTO
limit: int = Query(20)  # Sin rango
tier: str = Query(...)  # Sin validacion
```

### Regla 3: Proteger endpoints de escritura
Todo endpoint que modifique estado DEBE tener:
1. Autenticacion (API Key via header, NUNCA query param)
2. Rate limiting
3. Validacion de input con Pydantic
4. Error handling que NO exponga detalles internos

### Regla 4: Error handling seguro
```python
# Patron estandar para TODOS los endpoints
try:
    result = await do_operation()
    return result
except ValidationError as e:
    # Errores de validacion: OK mostrar al usuario
    raise HTTPException(status_code=422, detail=str(e))
except NotFoundException:
    raise HTTPException(status_code=404, detail="Recurso no encontrado")
except Exception as e:
    # Errores internos: NUNCA exponer
    logger.error("operation_failed", error=str(e), exc_info=True)
    raise HTTPException(status_code=500, detail="Error interno del servidor")
```

### Regla 5: CORS estricto
- Origenes explicitos desde variable de entorno
- Solo metodos necesarios
- Solo headers necesarios
- `allow_credentials=True` SOLO con origenes explicitos (nunca con `*`)

### Regla 6: Middleware de seguridad
Al refactorizar `src/api/main.py`, asegurar que incluye:
```python
from starlette.middleware.trustedhost import TrustedHostMiddleware

# En produccion
if not settings.debug:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["agendades.es", "www.agendades.es", "api.agendades.es"]
    )
```

---

## 3. Checklist por Fase de Refactorizacion

### Fase 0: Tests de caracterizacion
- [ ] Los tests NO exponen secrets (no .env en fixtures)
- [ ] Los tests NO hacen llamadas reales a Supabase
- [ ] Fixtures HTML no contienen datos personales reales

### Fase 1: Extraer utilidades
- [ ] `make_external_id()` usa hashlib.md5 (no secrets, es para IDs no para seguridad)
- [ ] Verificar que IDs generados son deterministas e iguales a los existentes en DB
- [ ] `clean_text()` no introduce XSS (strip HTML tags)

### Fase 2: Estandarizar HTTP client
- [ ] `self.fetch_url()` tiene timeout configurado
- [ ] No se filtran headers de auth del scraper en logs
- [ ] Retry logic no causa DoS a sitios externos

### Fase 3: Dividir god classes
- [ ] SupabaseClient split mantiene TODAS las queries parametrizadas
- [ ] Ningun modulo nuevo expone el client de Supabase directamente
- [ ] Re-export shim no rompe imports existentes

### Fase 4: Unificar configuracion
- [ ] SourceRegistry no permite inyeccion via slugs
- [ ] Configs no contienen secrets hardcoded
- [ ] BronzeSourceConfig eliminada de bronze_scraper_adapter (una sola fuente de verdad)

### Fase 5: Unificar pipeline
- [ ] UUIDs movidos a env vars (PUBLIC_CALENDAR_ID, SCRAPER_BOT_USER_ID)
- [ ] Pipeline no logea datos sensibles de eventos
- [ ] Batch processing no causa memory leaks

### Fase 6: Estandarizar adapters
- [ ] Todos los adapters usan self.fetch_url() (con retry y rate limiting)
- [ ] external_id generado con make_external_id() centralizado
- [ ] No hay URLs hardcoded con tokens/API keys en adapters

### Fase 7: Limpiar codigo muerto
- [ ] Archivos borrados no contenian logica de seguridad necesaria
- [ ] .gitignore actualizado para prevenir commits de archivos sensibles
- [ ] No quedan scripts con credentials en texto plano

---

## 4. Inventario de Archivos Criticos de Seguridad

| Archivo | Lineas | Criticidad | Que proteger |
|---------|--------|------------|--------------|
| `src/api/main.py` | 92 | ALTA | CORS, middleware de seguridad |
| `src/api/routes/scrape.py` | 669 | ALTA | Auth en endpoints de escritura |
| `src/api/routes/scheduler.py` | 70 | ALTA | Auth en pause/resume/trigger |
| `src/api/routes/dev.py` | 69 | ALTA | Auth en revalidate |
| `src/core/supabase_client.py` | 1081 | ALTA | Queries parametrizadas |
| `src/core/job_store.py` | 350 | MEDIA | Queries parametrizadas |
| `src/api/routes/sources.py` | 155 | MEDIA | Error handling |
| `src/api/routes/runs.py` | 200 | MEDIA | Validacion de params |
| `src/utils/cross_source_dedup.py` | 400 | BAJA | Queries parametrizadas |

---

## 5. Implementacion de Seguridad Pendiente (Roadmap)

### Prioridad 1 — Hacer YA (antes/durante refactorizacion)
1. Corregir CORS en `src/api/main.py`
2. Implementar `require_api_key` dependency en FastAPI
3. Proteger endpoints: scheduler/*, dev/*, POST scrape, DELETE jobs
4. Sanitizar errores en responses (no exponer str(e))

### Prioridad 2 — Hacer durante refactorizacion
5. Anadir rate limiting con slowapi
6. Anadir TrustedHostMiddleware en produccion
7. Mover UUIDs hardcoded a env vars
8. Validar params con enums (tier, ccaa)

### Prioridad 3 — Hacer despues de refactorizacion
9. Anadir security headers (X-Content-Type-Options, X-Frame-Options, etc.)
10. Audit log de acciones administrativas (quien pauso scheduler, quien creo job)
11. Monitoring de patrones sospechosos (muchos 403, scraping agresivo)

---

## 6. Patrones de Codigo Seguro (Referencia Rapida)

### Query Supabase segura
```python
# CORRECTO - Parametrizado
result = client.table("events").select("*").eq("source", source_id).execute()

# INCORRECTO - String interpolation
result = client.table("events").select("*").eq("source", f"{user_input}").execute()
# Aunque el SDK parametriza, evitar f-strings innecesarios por claridad
```

### Endpoint FastAPI seguro
```python
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

class CreateJobRequest(BaseModel):
    source: str = Field(..., max_length=100, pattern=r"^[a-z0-9_]+$")
    limit: int = Field(10, ge=1, le=100)
    dry_run: bool = False

@router.post("/jobs")
@limiter.limit("10/minute")
async def create_job(
    request: Request,
    body: CreateJobRequest,
    _: str = Depends(require_api_key),
):
    try:
        job = await job_service.create(body)
        return {"job_id": job.id, "status": "created"}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.exception("Failed to create job")
        raise HTTPException(status_code=500, detail="Error interno")
```

### Validacion de path params
```python
from enum import Enum

class SourceTier(str, Enum):
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"

@router.get("/sources/by-tier/{tier}")
async def get_by_tier(tier: SourceTier):  # FastAPI valida automaticamente
    ...
```

---

## 7. Como Verificar Seguridad Despues de Cambios

Ejecutar estos comandos despues de cada fase de refactorizacion:

```bash
# 1. Buscar SQL injection potencial
grep -rn "f\".*table\|f\".*select\|f\".*insert\|f\".*update\|f\".*delete" src/
# Resultado esperado: 0 coincidencias

# 2. Buscar errores expuestos
grep -rn "detail=str(e)\|detail=f\"" src/api/
# Resultado esperado: 0 en produccion (solo en validacion)

# 3. Buscar CORS inseguro
grep -rn "allow_origins=\[\"\\*\"\]" src/
# Resultado esperado: 0 coincidencias

# 4. Buscar endpoints sin auth
grep -rn "@router\.\(post\|put\|delete\|patch\)" src/api/routes/
# Cada resultado debe tener Depends(require_api_key)

# 5. Tests
pytest tests/ -v
# Resultado esperado: todos green
```
