"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> bytes:
    """Return a recorded ``/api/status`` body, byte for byte as the firmware formats it."""
    return (FIXTURES / name).read_bytes()
