# Deprecated Scripts

These scripts have been replaced by the unified CLI.

## Migration Guide

Instead of running individual scripts like:
```bash
python scripts/insert/insert_galicia_20.py --limit 20
python scripts/insert/insert_cyl_events.py --dry-run
python insert_gold_events.py --source catalunya_agenda
```

Use the new unified CLI:
```bash
# Single source
python -m src.cli insert --source galicia_cultura --limit 20

# By tier
python -m src.cli insert --tier gold --dry-run
python -m src.cli insert --tier bronze --limit 10

# By CCAA
python -m src.cli insert --tier eventbrite --ccaa "Cataluña"

# List available sources
python -m src.cli sources --tier gold
python -m src.cli sources --ccaa "Madrid"
```

## Old vs New Equivalents

| Old Script | New CLI Command |
|------------|-----------------|
| `insert_gold_events.py` | `python -m src.cli insert --tier gold` |
| `insert_bronze_events.py` | `python -m src.cli insert --tier bronze` |
| `insert_eventbrite_events.py` | `python -m src.cli insert --tier eventbrite` |
| `insert_galicia_20.py` | `python -m src.cli insert --source galicia_cultura` |
| `insert_cyl_events.py` | `python -m src.cli insert --tier bronze --ccaa "Castilla y León"` |

## Benefits of New CLI

1. Single entry point for all sources
2. Unified options (--limit, --dry-run, --upsert, --no-enrich, --no-images)
3. Consistent output format with rich tables
4. Source discovery via `sources` command
5. Reusable pipeline for API integration
