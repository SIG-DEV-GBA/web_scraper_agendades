# Cobertura por CCAA - Estado Actual

**Fecha:** 2026-01-29
**Versión:** 1.0

---

## Resumen Ejecutivo

| Métrica | Valor |
|---------|-------|
| CCAA cubiertas | 7 / 17 (41%) |
| Provincias cubiertas | 33 / 52 (63%) |
| Fuentes Gold (API) | 6 |
| Fuentes Plata (RSS) | 1 |
| Calidad promedio | 95%+ campos UI |

---

## NIVEL ORO (Gold) - APIs Estructuradas

Fuentes con APIs JSON estructuradas. Máxima calidad de datos.

### 1. Comunidad de Madrid
| Campo | Valor |
|-------|-------|
| **Source ID** | `madrid_datos_abiertos` |
| **API** | https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json |
| **Formato** | JSON-LD |
| **Provincias** | Madrid |
| **Eventos est.** | ~400/100 días |
| **Campos especiales** | Coordenadas, Organizador, Accesibilidad |
| **Calidad** | ⭐⭐⭐⭐⭐ |

### 2. Catalunya
| Campo | Valor |
|-------|-------|
| **Source ID** | `catalunya_agenda` |
| **API** | https://analisi.transparenciacatalunya.cat/resource/rhpv-yr4f.json |
| **Formato** | Socrata/SODA |
| **Provincias** | Barcelona, Tarragona, Lleida, Girona |
| **Eventos est.** | ~3000+ |
| **Campos especiales** | Coordenadas, Precio, Categorías |
| **Calidad** | ⭐⭐⭐⭐ |

### 3. País Vasco (Euskadi)
| Campo | Valor |
|-------|-------|
| **Source ID** | `euskadi_kulturklik` |
| **API** | https://api.euskadi.eus/culture/events/v1.0/events/upcoming |
| **Formato** | REST API paginada |
| **Provincias** | Álava, Gipuzkoa, Bizkaia |
| **Eventos est.** | ~500 |
| **Campos especiales** | Organizador, Imágenes múltiples |
| **Calidad** | ⭐⭐⭐⭐ |

### 4. Castilla y León
| Campo | Valor |
|-------|-------|
| **Source ID** | `castilla_leon_agenda` |
| **API** | https://analisis.datosabiertos.jcyl.es/api/explore/v2.1/catalog/datasets/eventos-de-la-agenda-cultural-categorizados-y-geolocalizados/records |
| **Formato** | CKAN OData |
| **Provincias** | Ávila, Burgos, León, Palencia, Salamanca, Segovia, Soria, Valladolid, Zamora |
| **Eventos est.** | ~1500+ |
| **Campos especiales** | Coordenadas, Temática, Destinatarios |
| **Calidad** | ⭐⭐⭐⭐⭐ |

### 5. Andalucía
| Campo | Valor |
|-------|-------|
| **Source ID** | `andalucia_agenda` |
| **API** | https://datos.juntadeandalucia.es/api/v0/schedule/all?format=json |
| **Formato** | CKAN |
| **Provincias** | Almería, Cádiz, Córdoba, Granada, Huelva, Jaén, Málaga, Sevilla |
| **Eventos est.** | ~500+ |
| **Campos especiales** | Organizador, Coordenadas |
| **Calidad** | ⭐⭐⭐⭐ |

### 6. Comunidad Valenciana
| Campo | Valor |
|-------|-------|
| **Source ID** | `valencia_ivc` |
| **API** | https://dadesobertes.gva.es/dataset/.../lista-de-actividades-culturales-programadas-por-el-ivc.json |
| **Formato** | JSON flat array |
| **Provincias** | Valencia, Castellón, Alicante |
| **Eventos est.** | ~200+ |
| **Campos especiales** | Coordenadas |
| **Calidad** | ⭐⭐⭐⭐ |

---

## NIVEL PLATA (Silver) - RSS + LLM

Fuentes RSS enriquecidas con LLM para categorización y detección de precios.

### 1. Galicia
| Campo | Valor |
|-------|-------|
| **Source ID** | `galicia_cultura` |
| **RSS** | https://www.cultura.gal/es/rssaxenda |
| **Formato** | RSS 2.0 con HTML embebido |
| **Provincias** | A Coruña, Lugo, Ourense, Pontevedra |
| **Eventos** | ~50/actualización |
| **Enriquecimiento LLM** | Summary, Categorías, Precio |
| **Calidad** | ⭐⭐⭐⭐ (99% campos UI) |

---

## CCAA SIN COBERTURA

### Alta Prioridad (población/turismo)

| CCAA | Provincias | Estado investigación |
|------|------------|---------------------|
| **Canarias** | Las Palmas, Sta. Cruz Tenerife | ✅ API encontrada: datos.canarias.es |
| **Aragón** | Zaragoza, Huesca, Teruel | ⚠️ Sin API, requiere scraping |
| **Islas Baleares** | Baleares | ⚠️ Sin API, solo PDFs |

### Media Prioridad

| CCAA | Provincias | Notas |
|------|------------|-------|
| Asturias | Asturias | Pendiente investigar |
| Cantabria | Cantabria | Pendiente investigar |
| Navarra | Navarra | Pendiente investigar |
| Murcia | Murcia | Pendiente investigar |
| Extremadura | Cáceres, Badajoz | Pendiente investigar |
| Castilla-La Mancha | Toledo, Ciudad Real, Cuenca, Guadalajara, Albacete | Pendiente investigar |

### Baja Prioridad

| CCAA | Provincias | Notas |
|------|------------|-------|
| La Rioja | La Rioja | Pendiente investigar |

---

## Próximos Pasos

1. **Implementar Canarias** - API CKAN lista para integrar
2. **Evaluar Aragón** - Scraping web (nivel Bronce)
3. **Evaluar Baleares** - Scraping web (nivel Bronce)
4. **Investigar CCAs media prioridad** - Buscar APIs/RSS

---

## Archivos Relacionados

- `src/adapters/gold_api_adapter.py` - Configuraciones Gold
- `src/adapters/silver_rss_adapter.py` - Configuraciones Plata
- `sql/insert_gold_sources.sql` - SQL para insertar fuentes
