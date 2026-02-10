"""Pytest configuration and shared fixtures."""

import sys

import pytest

# Fix encoding for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment before each test."""
    yield
    # Cleanup after test
