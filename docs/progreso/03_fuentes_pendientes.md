# Fuentes Pendientes de Implementar

**Fecha:** 2026-01-29
**Versión:** 1.0

---

## Alta Prioridad

### 1. Canarias ✅ LISTA PARA IMPLEMENTAR

| Campo | Valor |
|-------|-------|
| **Estado** | API JSON encontrada y verificada |
| **Nivel** | ORO |
| **Portal** | https://datos.canarias.es/catalogos/general/dataset/agenda-cultural |
| **API** | CKAN Datastore |
| **Endpoint** | `https://datos.canarias.es/catalogos/general/api/3/action/datastore_search?resource_id=d179079c-a2ed-40dc-a748-7b64d093c342` |

**Campos disponibles:**
| Campo API | Mapeo EventCreate |
|-----------|-------------------|
| FECHA_INICIO | start_date |
| FECHA_FIN | end_date |
| DURACION_DIAS | - |
| TIPO_EVENTO | category_name |
| ISLA | province (Las Palmas / Sta. Cruz Tenerife) |
| MUNICIPIO | city |
| DENOMINACION_ESPACIO | venue_name |
| TITULO | title |
| DESCRIPCION | description |

**Siguiente paso:** Añadir configuración a `gold_api_adapter.py`

---

### 2. Aragón ⚠️ REQUIERE SCRAPING

| Campo | Valor |
|-------|-------|
| **Estado** | Sin API de datos abiertos |
| **Nivel** | BRONCE (scraping) |
| **Problema** | opendata.aragon.es no tiene dataset de agenda cultural |

**Alternativas encontradas:**

1. **Gobierno de Aragón** (oficial)
   - URL: https://www.aragon.es/-/actividades-culturales
   - Tipo: Web dinámica
   - Requiere: Playwright/Firecrawl

2. **Aragón Cultura (CARTV)**
   - URL: https://www.cartv.es/aragoncultura/agenda
   - Tipo: Web estática
   - Posible: BeautifulSoup + requests

3. **Aragón Digital** (medio)
   - URL: https://www.aragondigital.es/agenda-cultural/
   - Tipo: Web con posible RSS
   - Investigar: Feed RSS

**Siguiente paso:** Verificar si aragondigital.es tiene RSS funcional

---

### 3. Islas Baleares ⚠️ REQUIERE SCRAPING

| Campo | Valor |
|-------|-------|
| **Estado** | Sin API, solo PDFs y webs |
| **Nivel** | BRONCE (scraping) |
| **Problema** | No hay datos abiertos estructurados |

**Alternativas encontradas:**

1. **Consell de Mallorca**
   - URL: https://www.conselldemallorca.es/es/agenda
   - Tipo: Web dinámica
   - Requiere: Playwright/Firecrawl

2. **mallorca.es** (turismo)
   - URL: https://www.mallorca.es
   - Tipo: PDFs mensuales
   - Problema: No automatizable fácilmente

3. **illesbalears.travel** (turismo oficial)
   - URL: https://www.illesbalears.travel/en/illes-balears/agenda
   - Tipo: Web dinámica
   - Requiere: Playwright/Firecrawl

**Siguiente paso:** Evaluar complejidad de scraping con Firecrawl

---

## Media Prioridad (Pendiente Investigar)

| CCAA | Provincias | URL a investigar |
|------|------------|------------------|
| Asturias | 1 | datos.asturias.es, turismoasturias.es |
| Cantabria | 1 | datos.cantabria.es, culturadecantabria.com |
| Navarra | 1 | datosabiertos.navarra.es, culturanavarra.es |
| Murcia | 1 | datosabiertos.carm.es, murciaturistica.es |
| Extremadura | 2 | gobex.es, turismoextremadura.com |
| Castilla-La Mancha | 5 | datosabiertos.castillalamancha.es |

---

## Baja Prioridad

| CCAA | Provincias | URL a investigar |
|------|------------|------------------|
| La Rioja | 1 | datos.larioja.org, lariojaturismo.com |

---

## Notas Técnicas

### Para implementar fuente Gold (API)

1. Añadir config en `GOLD_SOURCES` dict en `gold_api_adapter.py`
2. Definir `field_mappings` para cada campo
3. Configurar paginación si aplica
4. Añadir SQL en `sql/insert_gold_sources.sql`
5. Test con `test_gold_sources.py`

### Para implementar fuente Plata (RSS)

1. Añadir config en `SILVER_RSS_SOURCES` dict en `silver_rss_adapter.py`
2. Mapear ciudades a provincias si necesario
3. Test con `test_plata_quality.py`

### Para implementar fuente Bronce (Scraping)

1. Crear adapter en `src/adapters/bronze_scraper_adapter.py`
2. Configurar Firecrawl o Playwright
3. Definir selectores CSS/XPath
4. Implementar parsing de HTML
5. Enriquecer con LLM (kimi-k2)

---

## Historial de Cambios

| Fecha | Cambio |
|-------|--------|
| 2026-01-29 | Documento inicial con investigación de Canarias, Aragón, Baleares |
