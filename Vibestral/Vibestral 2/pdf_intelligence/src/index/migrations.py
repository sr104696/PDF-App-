# src/index/migrations.py
# Changes: Thin wrapper that re-exports open_db from schema.py for backward compat.
"""Migration runner -- thin wrapper around schema.open_db."""
from __future__ import annotations

from .schema import open_db

__all__ = ["open_db"]
