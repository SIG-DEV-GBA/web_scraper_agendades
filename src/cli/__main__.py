"""Entry point for running CLI as module.

Usage:
    python -m src.cli insert --source diba_barcelona
    python -m src.cli sources --tier gold
"""

from src.cli.main import main

if __name__ == "__main__":
    main()
