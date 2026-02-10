# Fuentes Pendientes para Scraper

## Fuentes Nacionales (Alta Prioridad)
| Fuente | URL | Tipo | Notas |
|--------|-----|------|-------|
| Agenda Cultural Ministerio | cultura.gob.es | Oficial | Museos estatales, eventos nacionales |
| Spain.info Agenda | spain.info/es/agenda | Turismo | Festivales, eventos internacionales |
| Viral Agenda | viralagenda.com | Colaborativa | Multi-provincia, cultura urbana (403 bloqueado) |
| España en Libertad | - | Institucional | Actos solemnes, exposiciones históricas |
| Time Out | timeout.es | Lifestyle | Madrid/Barcelona, sin API |

## Por CCAA - Oficiales
| CCAA | Fuente Oficial | URL | Estado |
|------|----------------|-----|--------|
| Asturias | Cultura Asturias | culturaasturias.es | DNS fail |
| Baleares | Agenda Illes Balears | cultura.caib.es | DNS fail |
| Cantabria | Itinerario Cantabria | itinerariocantabria.com | DNS fail |
| Extremadura | Planex Extremadura | turismoextremadura.com | Sin agenda clara |
| Murcia | Cultura Región de Murcia | carm.es | Redirect, sin agenda |
| La Rioja | La Rioja Cultura | larioja.org/cultura | Sin agenda centralizada |
| Navarra | Cultura Navarra | culturanavarra.es/es/agenda | 11 eventos, Bronze |

## Por CCAA - Alternativas Locales
| CCAA | Fuente | URL | Tipo |
|------|--------|-----|------|
| Andalucía | La Guía GO! | laguiago.com | Sevilla, Málaga, Granada |
| Aragón | RedAragón | redaragon.com | Cert error |
| Asturias | Agitador Cultural | agitadorcultural.com | DNS fail |
| Cantabria | La Guía GO! | laguiago.com/cantabria | - |
| Murcia | La Guía GO! Murcia | laguiago.com/murcia | Custom JS |
| Navarra | Pamplona es Cultura | pamplonaescultura.es | WordPress, no MEC |

## Próximos Pasos Recomendados
1. **Prioridad Alta**: Añadir más ciudades a Andalucía (ya funciona el adapter)
2. **Prioridad Media**: Implementar Navarra Bronze (11 eventos + Baluarte ~10)
3. **Investigar**: APIs de datos abiertos de ayuntamientos grandes
4. **Futuro**: Viral Agenda si se puede bypasear el 403

## Notas Técnicas
- Muchas webs gubernamentales usan Liferay (sin API pública)
- WordPress con MEC tiene RSS en /eventos/feed/
- LaGuiaGO usa JavaScript custom, requiere Firecrawl
