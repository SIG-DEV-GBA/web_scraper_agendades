# Calidad de Datos por Nivel

**Fecha:** 2026-01-29
**Versión:** 1.0

---

## Niveles de Fuentes

| Nivel | Descripción | LLM Model | Calidad |
|-------|-------------|-----------|---------|
| **ORO** | APIs JSON estructuradas | gpt-oss-120b (rápido) | 95-100% |
| **PLATA** | RSS + HTML semi-estructurado | llama-3.3-70b | 90-99% |
| **BRONCE** | Webs dinámicas/caóticas | kimi-k2 (deep reasoning) | 70-90% |

---

## Cobertura de Campos UI

### Nivel ORO (APIs)

| Campo | Madrid | Catalunya | Euskadi | CyL | Andalucía | Valencia |
|-------|--------|-----------|---------|-----|-----------|----------|
| title | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| description | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| summary | LLM | LLM | LLM | LLM | LLM | LLM |
| start_date | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| start_time | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | ⚠️ |
| venue_name | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| city | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| province | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| coordinates | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| image | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| external_url | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| categories | LLM | ✅ | ✅ | ✅ | ✅ | ✅ |
| is_free | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| price_info | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| organizer | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ |
| accessibility | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Leyenda:** ✅ Disponible | ⚠️ Parcial | ❌ No disponible | LLM Enriquecido

### Nivel PLATA (RSS + LLM)

| Campo | Galicia | Cobertura |
|-------|---------|-----------|
| title | ✅ | 100% |
| description | ✅ | 100% |
| summary | LLM | 100% |
| start_date | ✅ | 100% |
| start_time | ✅ | 100% |
| venue_name | ✅ | 100% |
| city | ✅ | 100% |
| province | ✅ | 100% |
| coordinates | Geocoder | ~95% |
| image | ✅ | 100% |
| external_url | ✅ | 100% |
| categories | LLM | 100% |
| is_free | LLM | ~87% |
| price_info | LLM+default | 100% |
| organizer | ❌ | 0% |
| accessibility | ❌ | 0% |

---

## Procesamiento de Datos

### Pipeline Gold (API → DB)

```
API JSON → Parse → Field Mapping → Price Detection → Category Mapping
    → Organizer Extraction → Accessibility Extraction → Geocoding → DB
```

### Pipeline Plata (RSS → DB)

```
RSS Feed → Parse HTML → Extract Fields → LLM Enrichment (batch)
    → Price Detection → Category Classification → Geocoding → DB
```

---

## Mejoras Implementadas (2026-01-29)

1. **price_info siempre con texto** - Nunca queda vacío
   - `is_free=True` → "Entrada gratuita"
   - `is_free=False` → precio o "Consultar precio en web del organizador"
   - `is_free=None` → "Consultar en web del organizador"

2. **Detección de precios mejorada**
   - Detecta símbolo € → `is_free=False`
   - Detecta "gratuito/gratis/libre" → `is_free=True`

3. **Organizador mejorado**
   - Detecta tipo: persona, empresa, institución
   - Keywords expandidos para instituciones culturales

4. **Accesibilidad Madrid**
   - Mapeo de códigos numéricos a campos booleanos
   - Tabla separada `event_accessibility`

---

## Métricas de Test

### Galicia RSS (15 eventos sample)

```
Raw RSS Field Coverage:     100% (9/9 campos)
LLM Summary:               100%
LLM Categories:            100% (avg 1.2 cats/evento)
LLM Price Detection:        87% (is_free determinado)
Final Model Coverage:       99%
```
