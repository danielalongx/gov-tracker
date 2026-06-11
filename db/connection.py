"""
Database connection abstraction.
- Local dev / fallback: SQLite at data/gov_tracker.db
- Production: PostgreSQL via DATABASE_URL environment variable (Supabase)

Set DATABASE_URL=postgresql://... in .env to use Supabase.
Leave empty to use local SQLite (no persistence between GitHub Actions runs).
"""
import os
import sqlite3
from pathlib import Path


def _sqlite_path() -> str:
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    return str(data_dir / "gov_tracker.db")


class _SQLiteConnection(sqlite3.Connection):
    """Subclass so we can stash a custom attribute (sqlite3.Connection itself
    doesn't support arbitrary attribute assignment)."""
    pass


def get_connection():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgresql") or db_url.startswith("postgres"):
        try:
            import psycopg2
            conn = psycopg2.connect(db_url, connect_timeout=10)
            conn._is_postgres = True  # type: ignore[attr-defined]
            return conn
        except ImportError:
            print("psycopg2 not installed — falling back to SQLite")
    conn = sqlite3.connect(_sqlite_path(), factory=_SQLiteConnection)
    conn._is_postgres = False  # type: ignore[attr-defined]
    conn.row_factory = sqlite3.Row
    return conn


def qmark(conn) -> str:
    """Return the correct parameter placeholder for this connection type."""
    return "%s" if getattr(conn, "_is_postgres", False) else "?"


def is_postgres(conn) -> bool:
    return getattr(conn, "_is_postgres", False)
