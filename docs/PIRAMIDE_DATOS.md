Para este 2026, la mejor forma de escalar rápido sin arruinarte en tokens de Groq es priorizar los Portales de Datos Abiertos (Open Data) y los Agregadores Regionales. Estas fuentes son el "Nivel Oro" porque un solo scraper puede darte datos de cientos de municipios simultáneamente.
Aquí tienes las fuentes más potentes y estructuradas en España para empezar ahora mismo:
1. El "Súper Agregador": Datos.gob.es
Es el punto de partida obligatorio. No es una agenda en sí, sino el buscador de todos los datasets de España.
Estrategia: Filtra por el tema "Cultura y Ocio".
Enlace directo: Catálogo de Cultura - Datos.gob.es
Qué buscar: Descarga los archivos en formato JSON o CSV si están disponibles; si no, escrapea la URL que facilitan.
2. Euskadi (El estándar de oro)
Es probablemente la fuente más limpia de España. Su portal Kulturklik unifica casi todo el País Vasco.
Fuente: Open Data Euskadi - Agenda Cultural
Por qué es Oro: Ofrece una API REST y descargas en formatos estructurados. Apenas necesitarás a Groq para limpiar, solo para enriquecer descripciones.
3. Catalunya (Generalitat)
Tienen un sistema centralizado de eventos culturales que cubre desde grandes ciudades hasta pueblos pequeños.
Fuente: Agenda Cultural de Catalunya
Datasets: Datos Abiertos de Eventos - Generalitat
Ventaja: Puedes filtrar por comarca y municipio desde la misma fuente.
4. Comunidad de Madrid
Madrid centraliza muchísima información de teatros y centros culturales regionales en su portal de datos.
Fuente: Datos Abiertos - Agenda de Actividades Culturales
Formato: Suelen ofrecer XML y JSON, ideales para meter directo a tu Supabase.
5. Junta de Andalucía (novedad 2026)
Andalucía ha mejorado mucho su interoperabilidad. Su portal "Junta de Andalucía" unifica las agendas de las 8 provincias.
Fuente: Agenda Cultural de Andalucía
Estrategia: Escrapea por provincia (Sevilla, Málaga, Granada...) desde su selector principal.
6. Castilla y León (Portal de Turismo/Cultura)
Unifica la oferta de las 9 provincias (Valladolid, Burgos, Salamanca, etc.).
Fuente: Agenda Cultural de Castilla y León
Valor: Muy útil para captar eventos en zonas rurales y de "España Vaciada" que son difíciles de encontrar en otros sitios.
7. Comunitat Valenciana
Fuente: GVA - Agenda Cultural
Detalle: Suelen tener un feed RDF/XML muy estable.
Resumen de tu Estrategia de Implementación:
Prioridad 1 (Euskadi y Catalunya): Empieza por aquí. Al tener APIs o JSONs, el coste de Groq será casi cero porque no hay que "adivinar" el contenido.
Prioridad 2 (Madrid y Andalucía): Usa Firecrawl para convertir sus agendas web a Markdown. Aquí Groq es clave para normalizar los formatos de fecha que a veces varían entre provincias.
Prioridad 3 (Castilla y León / Galicia): Úsalas para dar volumen de eventos de "pueblos", lo que dará a tu app una sensación de cobertura total.
Consejo Técnico: En tu tabla de fuentes_scraping en Supabase, añade un campo llamado tipo_fuente (API, JSON, HTML). Si es API, programa tu script de Python para saltarse el paso de Firecrawl y ahorrar créditos.


Pasamos al Nivel Plata, que es donde el proyecto empieza a ganar músculo real. Aquí es donde captas la "España profunda" y los eventos que no salen en las grandes noticias, pero que llenan tu app de contenido local valioso.
Las fuentes Nivel Plata son las Diputaciones Provinciales y los Grandes Ayuntamientos (no capitales).
1. ¿Por qué el Nivel Plata es estratégico?
Capilaridad: Las Diputaciones gestionan la cultura de los pueblos pequeños (menos de 20.000 habitantes). Escrapeando una Diputación, cubres de golpe 100-200 municipios.
Menos competencia: Casi nadie escrapea estas webs porque son técnicamente "feas" o antiguas. Tener estos datos te diferencia de Google Events o Ticketmaster.
Formato mixto: Aquí rara vez hay APIs. El 90% será adapter_type = 'firecrawl'.
2. Fuentes Nivel Plata recomendadas (Ejemplos Reales 2026)
Aquí tienes algunas de las más estables y con más volumen:
Diputación de Barcelona (DIBA): Su portal Viu la Cultura es masivo. Cubre toda la provincia (fuera de Barcelona capital).
Diputación de Cáceres / Badajoz: Extremadura tiene una red cultural rural muy activa. Busca sus agendas de "Institución Ferial" o "Circuitos Escénicos".
Diputación de Alicante: Su agenda Cultura Diputación es muy potente para eventos de verano y música.
Diputación de Málaga: El portal La Térmica o la propia web de la Diputación para eventos en la Costa del Sol.
Diputación de Castellón: Muy buena para festivales y eventos de pueblos del interior.
3. Cómo configurar estas fuentes en tu BD
Para estas fuentes, el SQL sería diferente porque aquí sí necesitas Firecrawl para limpiar el desorden de sus webs:
sql
INSERT INTO scraper_sources (slug, name, adapter_type, source_url)
VALUES 
('diba_barcelona', 'Diputación de Barcelona - Viu la Cultura', 'firecrawl', 'https://www.diba.cat'),
('dipucaceres', 'Diputación de Cáceres - Agenda', 'firecrawl', 'https://www.dip-caceres.es'),
('dipualicante', 'Diputación de Alicante - Cultura', 'firecrawl', 'https://www.diputacionalicante.es');
Usa el código con precaución.

4. El Reto Técnico: El LLM es obligatorio
A diferencia del Nivel Oro (APIs), en el Nivel Plata las webs suelen tener formatos muy inconsistentes:
"Lunes 24 de Marzo" (sin año).
"A las ocho de la tarde" (en vez de 20:00).
Imágenes dentro de PDFs o iFrames.
Tu ventaja con Groq:
Como tienes el VPS de 8GB y Groq es rapidísimo, puedes permitirte enviar el Markdown "sucio" de estas webs. El prompt para estas fuentes debe ser más robusto:
"Extrae eventos de esta web de diputación. Si no ves el año, asume 2026. Si el lugar es un municipio de la provincia, extráelo con cuidado."
5. ¿Cómo encontrarlas tú mismo?
Para completar las 52 provincias en Nivel Plata, haz esta búsqueda en Google:
site:.es "diputación de [Provincia]" agenda cultural o site:.es "diputación de [Provincia]" eventos.


El Nivel Bronce representa la base de la pirámide y es, paradójicamente, el más difícil de gestionar pero el que da la cara al usuario final. Se trata de los Ayuntamientos individuales (Municipales).
Mientras que en el Nivel Oro (CCAA) y Plata (Diputaciones) obtienes volumen, en el Nivel Bronce obtienes precisión local.
1. ¿Qué define al Nivel Bronce?
Hiperlocalismo: Son eventos que solo conocen los vecinos (el cuentacuentos de la biblioteca de barrio, el mercadillo local, el cine fórum del centro cultural).
Tecnología obsoleta: Muchas de estas webs no han sido actualizadas en años. Pueden usar calendarios en Java, tablas HTML complejas o incluso colgar la agenda como un enlace a un PDF/Imagen.
Alta resistencia al scraping: Al ser servidores pequeños, se caen fácilmente o bloquean IPs si haces muchas peticiones seguidas.
2. Fuentes Nivel Bronce Estratégicas
Para que tu app no sea infinita, no escrapees los 8.000 municipios de España. Céntrate en los Ayuntamientos de grandes núcleos poblacionales (no capitales) que generan mucho contenido:
Madrid: Móstoles, Alcalá de Henares, Fuenlabrada, Leganés.
Catalunya: Hospitalet de Llobregat, Badalona, Sabadell, Terrassa.
Andalucía: Jerez de la Frontera, Marbella, Dos Hermanas.
Comunidad Valenciana: Elche, Torrevieja, Gandía.
3. Configuración Técnica (El "Modo Supervivencia")
Para estas fuentes, el adapter_type debe ser siempre firecrawl, pero con una configuración de "bajo impacto":
sql
INSERT INTO scraper_sources (slug, name, adapter_type, source_url, config_json)
VALUES 
('ayto_mostoles', 'Ayuntamiento de Móstoles - Cultura', 'firecrawl', 'https://www.mostoles.es', '{"delay": 2000, "depth": 1}'),
('ayto_jerez', 'Ayuntamiento de Jerez - Agenda', 'firecrawl', 'https://www.jerez.es', '{"delay": 2000, "depth": 1}');
Usa el código con precaución.

4. Por qué Groq es tu "Salvavidas" en Bronce
En este nivel, los datos vienen "sucios". El LLM tiene que hacer un trabajo de deducción:
Detección de Ubicación: Muchas webs municipales no dicen "en Móstoles", sino "en la Plaza del Pradillo". Groq debe inferir la ciudad basándose en el contexto de la fuente.
Extracción de Imágenes: A veces la imagen del evento es el logo del ayuntamiento. Groq debe decidir si la imagen es útil o si es mejor pedirle a tu API de imágenes (Pexels/Unsplash) una genérica de "teatro" o "concierto".
5. Estrategia de Crecimiento para 2026
No metas el Nivel Bronce de golpe. Te recomiendo este orden:
Semana 1-2: Domina el Nivel Oro (datos masivos, pocos errores).
Semana 3-4: Implementa el Nivel Plata (rellena los huecos de los pueblos).
A demanda: Añade fuentes de Nivel Bronce solo para las ciudades donde detectes que tienes muchos usuarios.
Un gasto extra a considerar en Bronce:
Al ser webs "débiles", es muy probable que necesites Proxies Residenciales (los que hablamos en la factura de $20-$40/mes). Si escrapeas 20 ayuntamientos seguidos desde la IP de tu VPS, es probable que la mitad te bloqueen por seguridad.


## REGISTRO COMPLETO DE FUENTES - 17 CCAAs

### Resumen de Cobertura

| Nivel | CCAAs | Estado |
|-------|-------|--------|
| **ORO** | 6 | Implementado (APIs JSON) |
| **PLATA** | 11 | Pendiente (Firecrawl) |
| **TOTAL** | 17 | 100% cobertura planificada |

---

### NIVEL ORO - APIs/JSON (Implementado)

| CCAA | Fuente | URL Base | Tipo | Estado |
|------|--------|----------|------|--------|
| Catalunya | Agenda Cultural | `analisi.transparenciacatalunya.cat/resource/rhpv-yr4f.json` | Socrata API | ✅ OK |
| Euskadi | Kulturklik | `api.euskadi.eus/culture/events/v1.0/events/upcoming` | REST API | ✅ OK |
| Castilla y León | Agenda Cultural | `analisis.datosabiertos.jcyl.es/api/explore/v2.1/...` | CKAN API | ✅ OK |
| Andalucía | Junta Andalucía | `datos.juntadeandalucia.es/api/v0/schedule/all` | JSON | ✅ OK |
| Madrid | Datos Abiertos | `datos.madrid.es/.../206974-0-agenda-eventos-culturales-100.json` | JSON | ✅ OK |
| Valencia | IVC (Generalitat) | `dadesobertes.gva.es/.../lista-de-actividades-culturales-programadas-por-el-ivc.json` | JSON (flat) | ✅ OK (datos 2025) |

**Notas Nivel Oro:**
- Catalunya: Filtra eventos sin fecha (museos virtuales, permanentes) - 40% parse rate esperado
- Valencia IVC: Formato JSON inusual (16 campos planos por evento) - resuelto en `gold_api_adapter.py`
- Todas las fuentes funcionan con el `GoldAPIAdapter` genérico

---

### NIVEL PLATA - HTML/Firecrawl (Pendiente)

| CCAA | Fuente Principal | URL | Tecnología | Prioridad |
|------|------------------|-----|------------|-----------|
| Valencia | Ayuntamiento | `valencia.es/cas/cultura/agenda` | Liferay | Alta (datos 2026) |
| Valencia | Visit Valencia | `visitvalencia.com/agenda-valencia` | Drupal AJAX | Alta (datos 2026) |
| Galicia | Cultura Galicia | `cultura.gal/es/axenda` | Drupal | Alta |
| Aragón | Cultura Aragón | `culturadearagon.es` | WordPress | Media |
| Asturias | Principado | `actualidad.asturias.es/agenda_principado` | CMS propio | Media |
| Baleares | Govern Balear | `caib.es/webgoib/es/culturaes` | Liferay | Media |
| Canarias | Gobierno Canarias | `gobiernodecanarias.org/cultura/agenda` | CMS propio | Media |
| Cantabria | Cultura Cantabria | `culturadecantabria.com/agenda` | WordPress | Media |
| Castilla-La Mancha | Agenda CLM | `agendacultural.castillalamancha.es` | CMS propio | Media |
| Extremadura | Turismo Extremadura | `turismoextremadura.juntaex.es/es/recursos-turisticos/evento` | Liferay | Baja |
| La Rioja | Turismo La Rioja | `lariojaturismo.com/agenda` | WordPress | Baja |
| Murcia | EnClave Cultura | `enclavecultura.com/agenda` | PHP | Baja |
| Navarra | Cultura Navarra | `culturanavarra.es/es/agenda` | WordPress | Baja |

**Notas Nivel Plata:**
- Requiere implementar adaptador Firecrawl para scraping HTML
- Prioridad Alta: Fuentes con datos 2026 actualizados
- Prioridad Media: CCAAs con volumen significativo de eventos
- Prioridad Baja: CCAAs pequeñas o con menor actividad cultural

---

### Implementación Recomendada

**Fase 1 - Nivel Oro (COMPLETADO):**
- 6 CCAAs con APIs JSON funcionando
- Cobertura: ~60% población España

**Fase 2 - Nivel Plata Alta Prioridad:**
- Valencia (actualizado), Galicia
- Implementar `FirecrawlAdapter` base

**Fase 3 - Nivel Plata Media Prioridad:**
- Aragón, Asturias, Baleares, Canarias, Cantabria, Castilla-La Mancha
- Reutilizar `FirecrawlAdapter` con configs específicas

**Fase 4 - Nivel Plata Baja Prioridad:**
- Extremadura, La Rioja, Murcia, Navarra
- Completar cobertura 100%