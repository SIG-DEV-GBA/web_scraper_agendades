# Comandos de Inserción de Eventos

## Fuentes Disponibles

### Gold (APIs/RSS/iCal) - Alta calidad
| Slug | CCAA | Fuente |
|------|------|--------|
| catalunya_agenda | Catalunya | Agenda Cultural Generalitat |
| euskadi_kulturklik | País Vasco | Kulturklik |
| castilla_leon_agenda | Castilla y León | Agenda Cultural JCyL |
| andalucia_agenda | Andalucía | Junta de Andalucía |
| madrid_datos_abiertos | Madrid | Datos Abiertos Madrid |
| valencia_ivc | Comunidad Valenciana | Institut Valencià de Cultura |
| zaragoza_cultura | Aragón | Ayuntamiento de Zaragoza |
| cantabria_turismo | Cantabria | Turismo Cantabria (iCal) |

### Bronze (Scraping) - Requiere más procesamiento
| Slug | CCAA | Fuente |
|------|------|--------|
| clm_agenda | Castilla-La Mancha | Agenda Cultural CLM |
| canarias_lagenda | Canarias | Lagenda.org (Tenerife) |
| canarias_grancanaria | Canarias | Cabildo Gran Canaria |
| teruel_ayuntamiento | Aragón | Ayuntamiento de Teruel |
| navarra_cultura | Navarra | Cultura Navarra |
| asturias_turismo | Asturias | Turismo Asturias |
| larioja_agenda | La Rioja | Agenda La Rioja (LARIOJA.COM) |

---

## Comandos Individuales

### Gold
```bash
python insert_gold_events.py --source catalunya_agenda --limit 50
python insert_gold_events.py --source euskadi_kulturklik --limit 50
python insert_gold_events.py --source castilla_leon_agenda --limit 50
python insert_gold_events.py --source andalucia_agenda --limit 50
python insert_gold_events.py --source madrid_datos_abiertos --limit 50
python insert_gold_events.py --source valencia_ivc --limit 50
python insert_gold_events.py --source zaragoza_cultura --limit 50

# Cantabria (iCal - script separado)
python scripts/insert/insert_cantabria_events.py --limit 50
```

### Bronze
```bash
python insert_bronze_events.py --source clm_agenda --limit 50
python insert_bronze_events.py --source canarias_lagenda --limit 50
python insert_bronze_events.py --source canarias_grancanaria --limit 50
python insert_bronze_events.py --source teruel_ayuntamiento --limit 50
python insert_bronze_events.py --source navarra_cultura --limit 50
python insert_bronze_events.py --source asturias_turismo --limit 50
python insert_bronze_events.py --source larioja_agenda --limit 50
```

---

## Comandos Batch (Todas las fuentes)

### Ejecutar todas las Gold
```bash
python insert_gold_events.py --limit 50
```

### Ejecutar todas las Bronze
```bash
python insert_bronze_events.py --limit 50
```

### Ejecutar todo (Gold + Bronze)
```bash
python insert_gold_events.py --limit 50 && python insert_bronze_events.py --limit 50
```

---

## Opciones Disponibles

| Opción | Descripción |
|--------|-------------|
| `--source <slug>` | Procesar solo esta fuente |
| `--limit <n>` | Máximo de eventos por fuente (default: 20) |
| `--dry-run` | Probar sin insertar en base de datos |
| `--upsert` | Actualizar eventos existentes |
| `--no-details` | (Bronze) Skip páginas de detalle (más rápido) |

### Ejemplos
```bash
# Dry run para probar
python insert_gold_events.py --dry-run --limit 10

# Actualizar eventos existentes
python insert_bronze_events.py --source navarra_cultura --upsert --limit 50

# Rápido sin detalles
python insert_bronze_events.py --source asturias_turismo --no-details --limit 30
```

---

## CCAAs Pendientes (sin fuente configurada)
- Baleares - sin fuente encontrada
- Extremadura - sin fuente encontrada
- Murcia - sin fuente actual encontrada (404)
