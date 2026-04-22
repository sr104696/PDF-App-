"""Tiny migration runner. Schema version is stored in `meta`."""
from __future__ import annotations

import sqlite3
from .schema import DDL, SCHEMA_VERSION


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
    row = cur.fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
    conn.commit()


def open_db(path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=-20000")  # ~20 MB page cache
    init_db(conn)
    return conn
