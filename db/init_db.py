import logging
import os
import sqlite3
from pathlib import Path

from db.schema import CREATE_ANALYSIS, CREATE_POSTS, CREATE_SUBSCRIPTIONS, CREATE_USERS

logger = logging.getLogger(__name__)
DB_PATH = Path("data/gov_tracker.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive schema changes idempotently (ignores duplicate column errors)."""
    migrations = [
        ("posts",    "source_name",          "ALTER TABLE posts    ADD COLUMN source_name          TEXT"),
        ("posts",    "article_url",            "ALTER TABLE posts    ADD COLUMN article_url          TEXT"),
        ("posts",    "article_published_at",  "ALTER TABLE posts    ADD COLUMN article_published_at TEXT"),
        ("analysis", "companies",             "ALTER TABLE analysis ADD COLUMN companies            TEXT"),
        ("analysis", "source_name",           "ALTER TABLE analysis ADD COLUMN source_name          TEXT"),
    ]
    for table, column, sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
            logger.info("Migration applied: %s.%s", table, column)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                pass  # already present — idempotent
            else:
                raise


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(CREATE_POSTS)
        conn.execute(CREATE_ANALYSIS)
        conn.execute(CREATE_USERS)
        conn.execute(CREATE_SUBSCRIPTIONS)

        ntfy_channel = os.getenv("NTFY_CHANNEL", "gov-tracker-default")
        if conn.execute("SELECT id FROM users LIMIT 1").fetchone() is None:
            conn.execute(
                "INSERT INTO users (name, ntfy_channel, risk_profile) VALUES (?, ?, ?)",
                ("default", ntfy_channel, "moderate"),
            )
        conn.commit()

    # Run migrations against the live DB after tables exist
    with get_connection() as conn:
        _migrate(conn)
