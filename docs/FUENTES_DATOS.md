# Mapa de Fuentes de Datos - Agendades Scraper

> Documento generado: 2026-01-21
> **Última actualización**: 2026-01-21 (URLs verificadas)
> Objetivo: Recopilar eventos culturales a nivel provincial/CCAA

## ⚠️ IMPORTANTE: datos.gob.es NO federa las agendas culturales

La API de datos.gob.es tiene ~50,000 datasets pero **solo 2** son de agenda cultural:
- Institut Valencià de Cultura (IVC)
- Oficina de Congresos (Granada)

**Conclusión**: Las fuentes de Nivel Oro están **directamente en los portales de cada CCAA**.

---

## Estrategia: Pirámide de Datos

```
                    ┌─────────────┐
       Nivel 1      │  NACIONAL   │  ← Máxima cobertura, mínimo esfuerzo
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
       Nivel 2│         CCAA            │  ← Complementa nacional
              └────────────┬────────────┘
                           │
         ┌─────────────────┴─────────────────┐
       Nivel 3            PROVINCIAL         │  ← Llena huecos
         └─────────────────┬─────────────────┘
                           │
                    ┌──────┴──────┐
       Nivel 4      │  MUNICIPAL  │  ← Futuro, casos específicos
                    └─────────────┘
```

**Prioridad**: Empezar por arriba, bajar solo donde haya huecos.

---

## NIVEL 1: FUENTES NACIONALES

| Fuente | URL | Tipo | Formato | Cobertura | Estado |
|--------|-----|------|---------|-----------|--------|
| **Ministerio de Cultura** | https://agendacultural.cultura.gob.es/listado/ | Web | HTML | Museos nacionales | 🟡 Evaluar |
| **datos.gob.es** | https://datos.gob.es/es/catalogo?theme_id=cultura-ocio | Agregador | API | Agregador de datasets CCAA | ✅ Usar como índice |
| **España es Cultura** | https://www.españaescultura.es/ | Web | HTML | Patrimonio cultural | 🟡 Evaluar |

### API datos.gob.es
```
Base URL: https://datos.gob.es/apidata
Documentación: https://datos.gob.es/es/apidata
Formato: JSON-LD, RDF
```

---

## NIVEL 2: FUENTES POR CCAA

### Resumen Rápido

| # | CCAA | Fuente Principal | Tipo | Formato | Prioridad |
|---|------|------------------|------|---------|-----------|
| 1 | Andalucía | Junta de Andalucía | API | JSON/CSV | 🔴 Alta |
| 2 | Aragón | Aragón Open Data | API | JSON | 🟡 Media |
| 3 | Asturias | Turismo Asturias | Web | HTML | 🟡 Media |
| 4 | Baleares | GOIB Datos Abiertos | API | JSON | 🟡 Media |
| 5 | Canarias | Canarias Datos Abiertos | API | JSON/CSV | 🟡 Media |
| 6 | Cantabria | Web turismo | Web | HTML | 🟢 Baja |
| 7 | Castilla-La Mancha | Datos Abiertos CLM | API | JSON | 🟡 Media |
| 8 | Castilla y León | Datos Abiertos JCyL | API | CSV | 🔴 Alta |
| 9 | Cataluña | Generalitat + BCN | API | JSON | 🔴 Alta |
| 10 | C. Valenciana | IVC + GVA | API | JSON | 🔴 Alta |
| 11 | Extremadura | Junta Extremadura | Web | HTML | 🟢 Baja |
| 12 | Galicia | Xunta (cultura.gal) | API | RSS/ICS | 🔴 Alta |
| 13 | Madrid | datos.madrid.es | API | JSON | ✅ Implementado |
| 14 | Murcia | Región de Murcia | Web | HTML | 🟡 Media |
| 15 | Navarra | Gobierno Navarra | Web | HTML | 🟢 Baja |
| 16 | País Vasco | Kulturklik | API | JSON | 🔴 Alta |
| 17 | La Rioja | Gobierno La Rioja | Web | HTML | 🟢 Baja |

---

### Detalle por CCAA

#### 1. ANDALUCÍA 🔴 ⭐⭐⭐⭐
```yaml
fuente_principal:
  nombre: "Agenda de eventos - Junta de Andalucía"
  # URLs VERIFICADAS:
  url_portal: "https://www.juntadeandalucia.es/datosabiertos/portal/dataset/agenda-de-eventos-organizados-por-la-junta-de-andalucia"
  url_xml_atom: "https://www.juntadeandalucia.es/datosabiertos/portal/dataset/agenda-de-eventos-organizados-por-la-junta-de-andalucia/resource/9107236a-85fc-4efd-8db4-df29e008bdeb"
  formatos: [JSON, CSV, XML/Atom, RDF]
  tipo: API
  adapter_type: api
  actualización: Diaria
  notas: "Portal con +600 datasets. Descarga diaria disponible."

fuente_secundaria:
  nombre: "Agenda Cultural de Andalucía (participativa)"
  url: "https://www.juntadeandalucia.es/cultura/agendaculturaldeandalucia/"
  tipo: Web (HTML)
  adapter_type: firecrawl
  notas: "Abierta a cualquiera que quiera publicar eventos culturales en Andalucía"

fuente_municipal:
  - nombre: "Sevilla Ayuntamiento"
    url: "https://www.sevilla.org/actualidad/eventos"
    tipo: Web (HTML)
  - nombre: "ICAS Sevilla"
    url: "https://icas.sevilla.org/agenda"
    tipo: Web (HTML)
```

#### 2. ARAGÓN 🟡
```yaml
fuente_principal:
  nombre: "Aragón Open Data"
  url: "https://opendata.aragon.es/"
  url_eventos: "https://opendata.aragon.es/informacion/eventos"
  tipo: API
  formatos: [JSON]
  notas: "Portal muy completo, incluye Aragopedia"
```

#### 3. ASTURIAS 🟡
```yaml
fuente_principal:
  nombre: "Turismo Asturias - Agenda"
  url: "https://www.turismoasturias.es/es/agenda-de-asturias"
  tipo: Web (HTML)

datos_abiertos:
  nombre: "Datos abiertos turísticos"
  url: "https://www.turismoasturiasprofesional.es/es/open-data"
  notas: "Principalmente turismo, no eventos culturales específicos"
```

#### 4. BALEARES 🟡
```yaml
fuente_principal:
  nombre: "GOIB Datos Abiertos"
  url: "https://www.caib.es/sites/dadesobertes/"
  tipo: API
  formatos: [JSON]
  notas: "~350 datasets, buscar culturales"
```

#### 5. CANARIAS 🟡
```yaml
fuente_principal:
  nombre: "Canarias Datos Abiertos"
  url: "https://datos.canarias.es/portal/"
  url_api: "https://datos.canarias.es/portal/reutilizacion/api/"
  tipo: API
  formatos: [JSON, CSV, ICS]
  ejemplo_api: "https://www3.gobiernodecanarias.org/aplicaciones/agendascargospublicos/api/public/altoscargos/eventos"
```

#### 6. CANTABRIA 🟢
```yaml
fuente_principal:
  nombre: "Turismo Cantabria"
  url: "https://www.turismodecantabria.com/agenda"
  tipo: Web (HTML)
  notas: "Sin API conocida, scraping necesario"
```

#### 7. CASTILLA-LA MANCHA 🟡
```yaml
fuente_principal:
  nombre: "Datos Abiertos CLM"
  url: "https://datosabiertos.castillalamancha.es/"
  tipo: API
  notas: "Buscar datasets de cultura/eventos"
```

#### 8. CASTILLA Y LEÓN 🔴 ⭐⭐⭐⭐⭐
```yaml
fuente_principal:
  nombre: "Agenda Cultural JCyL"
  # URL DIRECTA API (VERIFICADA):
  url_api: "https://analisis.datosabiertos.jcyl.es/api/explore/v2.1/catalog/datasets/eventos-de-la-agenda-cultural-categorizados-y-geolocalizados/records"
  url_catalogo: "https://datosabiertos.jcyl.es/web/jcyl/set/es/cultura-ocio/agenda_cultural/1284806871500"
  tipo: API
  formato: JSON
  adapter_type: api
  actualizacion: "Cada 4 horas"
  campos: [titulo, fecha, categoria, coordenadas_geo]
  notas: "Paginación con limit y offset. Incluye geolocalización."

app_movil:
  nombre: "CyLac"
  descripcion: "App con eventos de las 9 provincias"
```

#### 9. CATALUÑA 🔴 ⭐⭐⭐⭐⭐
```yaml
fuente_ccaa:
  nombre: "Agenda Cultural de Catalunya"
  # URLs DIRECTAS API SOCRATA (VERIFICADAS):
  url_api_localitzacions: "https://analisi.transparenciacatalunya.cat/resource/rhpv-yr4f.json"
  url_api_organitzadors: "https://analisi.transparenciacatalunya.cat/resource/2n2k-gg9s.json"
  tipo: API (Socrata/SODA - estándar)
  formato: JSON
  adapter_type: api
  notas: "API SODA permite filtrar por comarca, municipio, fecha. Paginación con $limit y $offset"

fuente_barcelona:
  nombre: "Open Data BCN"
  url: "https://opendata-ajuntament.barcelona.cat/"
  url_agenda: "https://datos.gob.es/es/catalogo/l01080193-agenda-cultural-de-la-ciudad-de-barcelona"
  tipo: API
  datasets: 583

observatori:
  nombre: "Observatori de dades culturals"
  url: "https://barcelonadadescultura.bcn.cat/dades-obertes/"
```

#### 10. COMUNIDAD VALENCIANA 🔴
```yaml
fuente_principal:
  nombre: "Institut Valencià de Cultura (IVC)"
  url_datos_gob: "https://datos.gob.es/es/catalogo/a10002983-agenda-cultural-del-institut-valencia-de-cultura-ivc-2023-2024"
  tipo: API

portal_gva:
  nombre: "GVA Dades Obertes"
  url: "https://dadesobertes.gva.es/"

fuente_valencia_ciudad:
  nombre: "Agenda Valencia Ayuntamiento"
  url: "https://www.valencia.es/cas/cultura/agenda"
  tipo: Web (HTML)
```

#### 11. EXTREMADURA 🟢
```yaml
fuente_principal:
  nombre: "Junta de Extremadura - Cultura"
  url: "https://www.juntaex.es/cultura"
  tipo: Web (HTML)
  notas: "Sin API conocida"

datos_abiertos:
  url: "https://gobiernoabierto.juntaex.es/datos-abiertos"
```

#### 12. GALICIA 🔴 ⭐⭐⭐⭐
```yaml
fuente_principal:
  nombre: "Agenda de Cultura de Galicia"
  url: "https://www.cultura.gal/es/axenda"
  url_datos_gob: "https://datos.gob.es/es/catalogo/a12002994-agenda-de-cultura-de-galicia1"
  portal_abiertos: "https://abertos.xunta.gal/"
  tipo: API
  formatos: [JSON (servicio web), RSS, ICS, Widget configurable]
  adapter_type: api
  notas: "Servicio web JSON permite integrar en apps/webs con personalización"

app_movil:
  nombre: "Axenda Cultura"
  plataformas: [Android, iOS]

turismo:
  url: "https://www.turismo.gal/axenda-cultural"
```

#### 13. MADRID ✅ IMPLEMENTADO
```yaml
fuente_principal:
  nombre: "Madrid Datos Abiertos"
  url: "https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json"
  tipo: API
  formato: JSON
  eventos: ~1000 (próximos 100 días)
  estado: IMPLEMENTADO
  adapter: "src/adapters/madrid_datos_abiertos.py"
```

#### 14. MURCIA 🟡
```yaml
fuente_principal:
  nombre: "Región de Murcia Digital"
  url: "https://www.regmurcia.com/eventos.html"
  tipo: Web (HTML)

datos_abiertos:
  url: "https://datosabiertos.regiondemurcia.es/"

ayuntamiento:
  url: "https://eventos.murcia.es/"
```

#### 15. NAVARRA 🟢
```yaml
fuente_principal:
  nombre: "Gobierno de Navarra - Cultura"
  url: "https://www.navarra.es/es/cultura"
  tipo: Web (HTML)
  notas: "Sin API conocida"
```

#### 16. PAÍS VASCO 🔴 ⭐⭐⭐⭐⭐
```yaml
fuente_principal:
  nombre: "Kulturklik - Agenda Cultural Euskadi"
  # URL DIRECTA CATÁLOGO (VERIFICADA):
  url_catalogo: "https://opendata.euskadi.eus/catalogo/-/kulturklik-agenda-cultural/"
  url_proximos: "https://opendata.euskadi.eus/catalogo/-/agenda-cultural-proximos-eventos/"
  tipo: API
  formatos: [JSONP (5.79 MB), GEOJSON (4.78 MB)]
  adapter_type: api
  actualizacion: Diaria
  idiomas: [Euskera, Castellano]
  contenido: "conciertos, teatro, exposiciones, danza, bertsolarismo, festivales, infantil"
  libreria_python: "https://pypi.org/project/eventos-euskadi/"

fuente_vitoria:
  nombre: "Agenda Vitoria-Gasteiz"
  url: "https://datos.gob.es/es/catalogo/l01010590-agenda-de-actividades-culturales-de-la-ciudad"
  tipo: API
```

#### 17. LA RIOJA 🟢
```yaml
fuente_principal:
  nombre: "Gobierno de La Rioja - Cultura"
  url: "https://www.larioja.org/cultura"
  tipo: Web (HTML)
  notas: "Sin API conocida"

datos_abiertos:
  url: "https://www.larioja.org/gobierno-abierto/datos-abiertos"
```

---

## NIVEL 3: FUENTES PROVINCIALES/MUNICIPALES DESTACADAS

| Provincia/Ciudad | Fuente | Tipo | Prioridad |
|------------------|--------|------|-----------|
| **Madrid capital** | datos.madrid.es | API ✅ | Implementado |
| **Barcelona** | Open Data BCN | API | Alta |
| **Valencia** | valencia.es/agenda | Web | Alta |
| **Sevilla** | sevilla.org/eventos | Web | Alta |
| **Málaga** | datos.gob.es (CSV) | API | Media |
| **Bilbao** | bilbao.eus | Web | Media |
| **Vitoria-Gasteiz** | datos.gob.es | API | Media |
| **A Coruña** | Smart Coruña | API | Media |

---

## RESUMEN: PLAN DE IMPLEMENTACIÓN

### Fase 1: APIs Prioritarias (Alta cobertura, bajo esfuerzo) - ✅ COMPLETADA

| CCAA | Adaptador | Eventos | Estado |
|------|-----------|---------|--------|
| ✅ Madrid | `madrid_datos_abiertos` | ~1000 | Implementado (dedicado) |
| ✅ Catalunya | `catalunya_agenda` | ~1000 (732 con fechas) | Implementado (genérico) |
| ✅ País Vasco | `euskadi_kulturklik` | ~3400 | Implementado (genérico) |
| ✅ Castilla y León | `castilla_leon_agenda` | ~100+ | Implementado (genérico) |
| ✅ Andalucía | `andalucia_agenda` | ~839 | Implementado (genérico) |
| 🟡 Galicia | Pendiente | - | Requiere investigar API |

**Código**: `src/adapters/gold_api_adapter.py` (adaptador genérico para todas las fuentes Nivel Oro)

### Fase 2: APIs Secundarias
7. 🟡 Comunidad Valenciana (IVC)
8. 🟡 Canarias
9. 🟡 Aragón
10. 🟡 Baleares

### Fase 3: Web Scraping (Firecrawl)
11. 🟡 Sevilla (sevilla.org) - Ya analizado
12. 🟡 Valencia ciudad
13. 🟡 Murcia
14. 🟢 Asturias, Cantabria, Navarra, La Rioja, Extremadura

---

## ARQUITECTURA PROPUESTA

```
┌─────────────────────────────────────────────────────────┐
│                    GenericAdapter                        │
│  - Configuración en DB (scraper_sources)                │
│  - Parsers: API (JSON/CSV/RSS) + HTML (Firecrawl)       │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐        ┌─────────┐        ┌─────────┐
   │API Parser│        │CSV Parser│        │HTML Parser│
   │  (JSON)  │        │         │        │(Firecrawl)│
   └─────────┘        └─────────┘        └─────────┘
```

### Tabla scraper_sources (ya creada en Supabase)
```sql
- slug: identificador único
- source_type: 'api_json' | 'api_csv' | 'api_rss' | 'html'
- config: JSON con selectores/mapeos específicos
- ccaa, ccaa_code, provincia
- is_active, last_run_at, etc.
```

---

## NOTAS TÉCNICAS

### Formatos encontrados:
- **JSON**: Madrid, País Vasco, Cataluña, Andalucía
- **CSV**: Castilla y León, Málaga, Andalucía
- **RSS/ICS**: Galicia
- **XML/Atom**: Andalucía
- **HTML**: Sevilla, Valencia, Murcia, y CCAAs sin API

### Rate Limiting por fuente:
- APIs oficiales: generalmente sin límite estricto
- Web scraping: usar delays 2-5s entre requests
- Firecrawl: rate limiting por dominio configurado

### Campos comunes a extraer:
- título, descripción, resumen
- fecha_inicio, fecha_fin, hora
- lugar (venue), dirección, coordenadas
- categoría, tags
- precio, es_gratis
- url_fuente, imagen
- organizador
