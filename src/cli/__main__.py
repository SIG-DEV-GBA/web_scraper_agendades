"""Entry point for running CLI as module.

Usage:
    python -m src.cli insert --source catalunya_agenda
    python -m src.cli sources --tier gold
"""

from src.cli.main import main

if __name__ == "__main__":
    main()
