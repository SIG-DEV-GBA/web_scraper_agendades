# Cobertura de Fuentes de Datos - agendades.es

> Fichero de seguimiento de todas las fuentes de datos por CCAA y provincia.
> Actualizado: 2026-01-26

## Resumen General

| Nivel | CCAAs | Provincias cubiertas | Estado |
|-------|-------|---------------------|--------|
| **ORO** (API/JSON) | 6 | 28 | Implementado |
| **PLATA** (Firecrawl/HTML) | 11 | 22 restantes | Pendiente |
| **TOTAL** | 17 | 50 | En progreso |

---

## NIVEL ORO - APIs/JSON Estructurado

### Implementado (6 CCAAs)

| # | CCAA | Slug | Fuente | URL API | Provincias | Estado |
|---|------|------|--------|---------|------------|--------|
| 1 | **Catalunya** | `catalunya_agenda` | Transparencia Catalunya | `analisi.transparenciacatalunya.cat/resource/rhpv-yr4f.json` | Barcelona, Girona, Lleida, Tarragona (4) | OK |
| 2 | **Euskadi** | `euskadi_kulturklik` | Kulturklik API | `api.euskadi.eus/culture/events/v1.0/events/upcoming` | Araba, Bizkaia, Gipuzkoa (3) | OK |
| 3 | **Castilla y Leon** | `castilla_leon_agenda` | CKAN Datos Abiertos | `analisis.datosabiertos.jcyl.es/api/explore/v2.1/...` | 9 provincias | OK |
| 4 | **Andalucia** | `andalucia_agenda` | Junta Andalucia | `datos.juntadeandalucia.es/api/v0/schedule/all` | 8 provincias | OK |
| 5 | **Madrid** | `madrid_datos_abiertos` | Datos Abiertos Madrid | `datos.madrid.es/.../agenda-eventos-culturales-100.json` | Madrid (1) | OK |
| 6 | **C. Valenciana** | `valencia_ivc` | GVA IVC | `dadesobertes.gva.es/.../lista-de-actividades-culturales...json` | Alicante, Castellon, Valencia (3) | OK (datos 2025) |

**Subtotal Oro implementado: 6 CCAAs, 28 provincias**

### Candidatas a Oro - DESCARTADAS (verificado 2026-01-26)

| # | CCAA | Portal Open Data | Resultado | Motivo |
|---|------|-----------------|-----------|--------|
| ~~7~~ | **Aragon** | opendata.aragon.es (CKAN) | **PLATA** | Solo ferias comerciales y patrimonio. 0 datasets de eventos culturales. |
| ~~8~~ | **Castilla-La Mancha** | datosabiertos.castillalamancha.es | **PLATA** | Metadatos apuntan a web HTML. RSS solo 6 items. Drupal sin JSON:API. |
| ~~9~~ | **Navarra** | datosabiertos.navarra.es (CKAN) | **PLATA** | 22 datasets cultura pero solo museos/bibliotecas. 0 agenda de eventos. |

> Las 3 candidatas fueron verificadas y descartadas. Se mantienen como Plata.
> **El Oro se queda en 6 CCAAs, 28 provincias (~61% poblacion).**

---

## NIVEL PLATA - HTML/Firecrawl

### Prioridad ALTA

| # | CCAA | Fuente | URL | Tecnologia | Datos 2026 | Notas |
|---|------|--------|-----|------------|------------|-------|
| 1 | **Galicia** | Cultura.gal (RSS) | `cultura.gal/es/rssaxenda` | Drupal / RSS 2.0 | SI (399+ eventos) | RSS estructurado, CC BY-SA 4.0 |
| 2 | **Galicia** | Deput. Pontevedra | `depo.gal/es/axenda-de-actividades` | Liferay | SI | Schema.org JSON-LD |
| 3 | **Galicia** | Deput. Lugo | `cultura.deputacionlugo.gal/es` | Drupal | SI | Programas Agora, Buxiganga |
| 4 | **Valencia** | Ayto. Valencia | `valencia.es/cas/cultura/agenda` | Liferay | SI | Agenda ciudad |
| 5 | **Valencia** | Visit Valencia | `visitvalencia.com/agenda-valencia` | Drupal AJAX | SI | Turismo + filtros |
| 6 | **Valencia** | Diput. Alicante | `agendacultural.diputacionalicante.es/eventos/mes/` | WordPress Divi | SI (35 ene-2026) | **JSON-LD** (casi Oro!) |
| 7 | **Valencia** | Cultural Valencia | `cultural.valencia.es` | WordPress Elementor | SI | Cultura municipal |

### Prioridad MEDIA

| # | CCAA | Fuente | URL | Tecnologia | Datos 2026 | Notas |
|---|------|--------|-----|------------|------------|-------|
| 8 | **Asturias** | Agenda Principado | `actualidad.asturias.es/agenda_principado` | CMS propio | SI | Opera, conciertos |
| 9 | **Cantabria** | Cultura Cantabria | `culturadecantabria.com/agenda` | Liferay | SI | Posible JSONWS API |
| 10 | **Canarias** | Gobierno Canarias | `gobiernodecanarias.org/cultura` | Multi-portal | SI (FIMC 2026) | Necesita portales por isla |
| 11 | **Canarias** | Cabildo Gran Canaria | `cultura.grancanaria.com/en/agenda` | CMS propio | SI | Isla principal |
| 12 | **Baleares** | GOIB | `caib.cat/sites/opendatacaib` | Portal CAIB | SI | Fragmentado por isla |

### Prioridad BAJA

| # | CCAA | Fuente | URL | Tecnologia | Datos 2026 | Notas |
|---|------|--------|-----|------------|------------|-------|
| 13 | **Extremadura** | Turismo Extremadura | `turismoextremadura.juntaex.es/es/recursos-turisticos/evento` | CMS propio | SI | Fiestas/festivales |
| 14 | **La Rioja** | Turismo La Rioja | `lariojaturismo.com/agenda` | GNOSS (semantico) | SI (13 eventos) | Plataforma GNOSS atipica |
| 15 | **Murcia** | EnClave Cultura | `enclavecultura.com/agenda/agenda-centros-culturales.php` | PHP custom | SI | Centros culturales regionales |

---

## COBERTURA POR PROVINCIA (50 provincias)

### Leyenda
- `ORO` = API/JSON implementado
- `ORO?` = Candidata a Oro (pendiente verificar API)
- `PLATA-A` = Plata prioridad Alta (pendiente)
- `PLATA-M` = Plata prioridad Media (pendiente)
- `PLATA-B` = Plata prioridad Baja (pendiente)
- `--` = Sin fuente identificada aun

### Andalucia (8 provincias) - ORO
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Almeria | ORO | -- | Pendiente investigar diputacion |
| Cadiz | ORO | -- | |
| Cordoba | ORO | -- | |
| Granada | ORO | -- | |
| Huelva | ORO | -- | |
| Jaen | ORO | -- | |
| Malaga | ORO | -- | La Termica (diputacion) |
| Sevilla | ORO | -- | ICAS Sevilla |

### Aragon (3 provincias) - PLATA-M
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Huesca | PLATA-M | -- | |
| Teruel | PLATA-M | -- | |
| Zaragoza | PLATA-M | -- | aragon.es (Liferay) |

### Asturias (1 provincia) - PLATA-M
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Asturias | PLATA-M | (uniprovincial) | actualidad.asturias.es |

### Baleares (1 provincia) - PLATA-M
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Illes Balears | PLATA-M | (uniprovincial) | caib.cat + portales insulares |

### Canarias (2 provincias) - PLATA-M
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Las Palmas | PLATA-M | -- | cultura.grancanaria.com |
| S.C. Tenerife | PLATA-M | -- | |

### Cantabria (1 provincia) - PLATA-M
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Cantabria | PLATA-M | (uniprovincial) | culturadecantabria.com |

### Castilla-La Mancha (5 provincias) - PLATA-M
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Albacete | PLATA-M | -- | |
| Ciudad Real | PLATA-M | -- | |
| Cuenca | PLATA-M | -- | |
| Guadalajara | PLATA-M | -- | |
| Toledo | PLATA-M | -- | |

### Castilla y Leon (9 provincias) - ORO
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Avila | ORO | -- | |
| Burgos | ORO | -- | |
| Leon | ORO | -- | |
| Palencia | ORO | -- | |
| Salamanca | ORO | -- | |
| Segovia | ORO | -- | |
| Soria | ORO | -- | |
| Valladolid | ORO | -- | |
| Zamora | ORO | -- | |

### Catalunya (4 provincias) - ORO
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Barcelona | ORO | -- | DIBA Viu la Cultura (futuro Plata) |
| Girona | ORO | -- | |
| Lleida | ORO | -- | |
| Tarragona | ORO | -- | |

### Comunitat Valenciana (3 provincias) - ORO + PLATA-A
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Alicante | ORO | PLATA-A | agendacultural.diputacionalicante.es (JSON-LD!) |
| Castellon | ORO | -- | dipcas.es (vacio actualmente) |
| Valencia | ORO | PLATA-A | valencia.es + visitvalencia.com + cultural.valencia.es |

### Extremadura (2 provincias) - PLATA-B
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Badajoz | PLATA-B | -- | |
| Caceres | PLATA-B | -- | dip-caceres.es |

### Galicia (4 provincias) - PLATA-A
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| A Coruna | PLATA-A | PLATA-A | coruna.gal/cultura/es/agenda |
| Lugo | PLATA-A | PLATA-A | cultura.deputacionlugo.gal |
| Ourense | PLATA-A | -- | depourense.es (404 - rota) |
| Pontevedra | PLATA-A | PLATA-A | depo.gal/es/axenda-de-actividades |

### La Rioja (1 provincia) - PLATA-B
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| La Rioja | PLATA-B | (uniprovincial) | lariojaturismo.com/agenda |

### Madrid (1 provincia) - ORO
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Madrid | ORO | (uniprovincial) | datos.madrid.es |

### Murcia (1 provincia) - PLATA-B
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Murcia | PLATA-B | (uniprovincial) | enclavecultura.com |

### Navarra (1 provincia) - PLATA-B
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Navarra | PLATA-B | (uniprovincial) | culturanavarra.es/es/agenda (PHP custom) |

### Pais Vasco / Euskadi (3 provincias) - ORO
| Provincia | Nivel CCAA | Nivel Provincial | Fuente Provincial |
|-----------|------------|-----------------|-------------------|
| Araba/Alava | ORO | -- | |
| Bizkaia | ORO | -- | |
| Gipuzkoa | ORO | -- | |

---

## ESTADISTICAS DE COBERTURA

### Por nivel (CCAA)
| Nivel | CCAAs | % |
|-------|-------|---|
| ORO (implementado) | 6 | 35% |
| ORO (candidatas) | 3 | 18% |
| PLATA Alta | 2 | 12% |
| PLATA Media | 4 | 24% |
| PLATA Baja | 3 | 18% |
| **TOTAL** | **17** | **100%** |

### Por nivel (provincias)
| Nivel | Provincias | % |
|-------|-----------|---|
| ORO (implementado) | 28 | 56% |
| ORO (candidatas) | 9 | 18% |
| PLATA (identificadas) | 7 | 14% |
| Sin fuente provincial | 6 | 12% |
| **TOTAL** | **50** | **100%** |

### Poblacion cubierta (aprox.)
| Nivel | Poblacion (M) | % Espana |
|-------|--------------|----------|
| ORO implementado | ~29M | ~61% |
| + ORO candidatas | ~34M | ~72% |
| + PLATA Alta | ~38M | ~80% |
| + PLATA Media | ~43M | ~91% |
| + PLATA Baja | ~47M | ~100% |

---

## PLAN DE IMPLEMENTACION

### Fase 1 - Verificar candidatas Oro (SIGUIENTE)
1. Aragon: Buscar dataset cultura en opendata.aragon.es
2. Castilla-La Mancha: Verificar endpoint JSON en datosabiertos.castillalamancha.es
3. Navarra: Buscar agenda cultural en datosabiertos.navarra.es

### Fase 2 - Plata Alta prioridad
4. Galicia: cultura.gal RSS (Drupal) - fuente principal
5. Valencia complementaria: Diput. Alicante (JSON-LD), Visit Valencia, Ayto. Valencia

### Fase 3 - Plata Media prioridad
6. Asturias, Cantabria, Canarias, Baleares
7. Implementar FirecrawlAdapter base reutilizable

### Fase 4 - Plata Baja prioridad
8. Extremadura, La Rioja, Murcia
9. Completar cobertura 100% CCAAs

---

## NOTAS TECNICAS

### Descubrimientos clave de la investigacion
- **Aragon, CLM, Navarra** pueden ser Oro (tienen portales Open Data con APIs)
- **Diput. Alicante** tiene JSON-LD en la pagina (Schema.org) - casi Oro
- **Galicia** tiene RSS oficial con licencia CC BY-SA 4.0 - muy limpio
- **Cantabria** usa Liferay con posible API JSONWS accesible
- **Diput. Ourense** tiene la agenda rota (404)
- **Diput. Castellon** existe pero sin datos actualmente (0 eventos)
- **La Rioja** usa GNOSS (plataforma semantica atipica)

### Tecnologias detectadas en fuentes Plata
| Tecnologia | CCAAs | Complejidad scraping |
|-----------|-------|---------------------|
| Drupal | Galicia, CLM | Media (AJAX views) |
| WordPress | Valencia (Alicante, Cultural) | Baja-Media |
| Liferay | Valencia (Ayto), Cantabria | Media-Alta |
| CMS propio | Asturias, Extremadura, Canarias | Alta |
| PHP custom | Murcia, Navarra | Media |
| GNOSS | La Rioja | Alta (semantico) |
