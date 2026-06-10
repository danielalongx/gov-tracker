import logging
import os
import sqlite3
from pathlib import Path

from db.schema import (
    CREATE_ANALYSIS, CREATE_POSTS, CREATE_SUBSCRIPTIONS, CREATE_USERS,
    CREATE_STOCK_SNAPSHOTS, CREATE_EARNINGS, CREATE_INSIDER_TRADES,
    CREATE_MECHANISM_RULES, CREATE_MECHANISMS, CREATE_COMPANY_PROFILES,
    CREATE_SIGNAL_COMPANY_LINKS,
)

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
        ("analysis", "hold_for_digest",       "ALTER TABLE analysis ADD COLUMN hold_for_digest      INTEGER DEFAULT 0"),
        ("analysis", "notified_at",           "ALTER TABLE analysis ADD COLUMN notified_at          DATETIME"),
        ("analysis", "score_news",            "ALTER TABLE analysis ADD COLUMN score_news            REAL DEFAULT 0"),
        ("analysis", "score_financial",       "ALTER TABLE analysis ADD COLUMN score_financial       REAL DEFAULT 0"),
        ("analysis", "score_pipeline",        "ALTER TABLE analysis ADD COLUMN score_pipeline        REAL DEFAULT 0"),
        ("analysis", "score_regulatory",      "ALTER TABLE analysis ADD COLUMN score_regulatory      REAL DEFAULT 0"),
        ("analysis", "score_capital_flows",   "ALTER TABLE analysis ADD COLUMN score_capital_flows   REAL DEFAULT 0"),
        ("analysis", "score",                 "ALTER TABLE analysis ADD COLUMN score                 REAL DEFAULT NULL"),
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
        conn.execute(CREATE_STOCK_SNAPSHOTS)
        conn.execute(CREATE_EARNINGS)
        conn.execute(CREATE_INSIDER_TRADES)
        conn.execute(CREATE_MECHANISM_RULES)
        conn.execute(CREATE_MECHANISMS)
        conn.execute(CREATE_COMPANY_PROFILES)
        conn.execute(CREATE_SIGNAL_COMPANY_LINKS)

        # Stage 2 indexes
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signal_company_links_ticker "
            "ON signal_company_links(ticker)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mechanisms_signal_id "
            "ON mechanisms(signal_id)"
        )

        try:
            conn.execute("ALTER TABLE analysis ADD COLUMN signal_class TEXT DEFAULT 'A'")
        except Exception:
            pass

        ntfy_channel = os.getenv("NTFY_CHANNEL", "gov-tracker-default")
        if conn.execute("SELECT id FROM users LIMIT 1").fetchone() is None:
            conn.execute(
                "INSERT INTO users (name, ntfy_channel, risk_profile) VALUES (?, ?, ?)",
                ("default", ntfy_channel, "moderate"),
            )

        _seed_company_profiles(conn)
        conn.commit()

    # Run migrations against the live DB after tables exist
    with get_connection() as conn:
        _migrate(conn)


_COMPANY_PROFILES_SEED = [
    (
        "NVDA", "NVIDIA Corporation", "Technology/Semiconductors", "NASDAQ", "USD",
        '{"US": 0.50, "Taiwan": 0.10, "Europe": 0.20, "Asia": 0.20}',
        '{"datacenter": 0.82, "gaming": 0.12, "automotive": 0.03, "professional_viz": 0.03}',
        '{"rate_sensitive": false, "ai_exposed": true, "semiconductor": true, "export_controlled": true}',
    ),
    (
        "AAPL", "Apple Inc.", "Technology/Consumer Electronics", "NASDAQ", "USD",
        '{"US": 0.42, "China": 0.19, "Europe": 0.24, "Rest": 0.15}',
        '{"iphone": 0.52, "services": 0.22, "mac": 0.10, "wearables": 0.10, "ipad": 0.06}',
        '{"rate_sensitive": true, "ai_exposed": true, "china_exposed": true, "consumer_discretionary": true}',
    ),
    (
        "TSLA", "Tesla Inc.", "Consumer Discretionary/Automotive", "NASDAQ", "USD",
        '{"US": 0.48, "China": 0.22, "Europe": 0.25, "Rest": 0.05}',
        '{"automotive": 0.84, "energy_storage": 0.08, "services": 0.08}',
        '{"rate_sensitive": true, "ai_exposed": true, "china_exposed": true, "ev": true}',
    ),
    (
        "MSFT", "Microsoft Corporation", "Technology/Software", "NASDAQ", "USD",
        '{"US": 0.52, "Europe": 0.25, "Asia": 0.15, "Rest": 0.08}',
        '{"cloud": 0.43, "productivity": 0.33, "gaming": 0.09, "linkedin": 0.07, "other": 0.08}',
        '{"rate_sensitive": false, "ai_exposed": true, "cloud": true, "enterprise": true}',
    ),
    (
        "GOOGL", "Alphabet Inc.", "Technology/Internet", "NASDAQ", "USD",
        '{"US": 0.47, "Europe": 0.28, "Asia": 0.15, "Rest": 0.10}',
        '{"search_ads": 0.57, "youtube": 0.10, "cloud": 0.11, "other_bets": 0.01, "other": 0.21}',
        '{"rate_sensitive": false, "ai_exposed": true, "advertising": true, "cloud": true}',
    ),
    (
        "AMZN", "Amazon.com Inc.", "Consumer Discretionary/E-commerce", "NASDAQ", "USD",
        '{"US": 0.62, "Europe": 0.25, "Rest": 0.13}',
        '{"aws": 0.17, "retail_us": 0.44, "retail_intl": 0.24, "advertising": 0.08, "other": 0.07}',
        '{"rate_sensitive": true, "ai_exposed": true, "cloud": true, "consumer_cyclical": true}',
    ),
    (
        "META", "Meta Platforms Inc.", "Technology/Social Media", "NASDAQ", "USD",
        '{"US": 0.44, "Europe": 0.25, "Asia": 0.20, "Rest": 0.11}',
        '{"advertising": 0.97, "reality_labs": 0.02, "other": 0.01}',
        '{"rate_sensitive": false, "ai_exposed": true, "advertising": true, "vr_ar": true}',
    ),
    (
        "BRKB", "Berkshire Hathaway Inc.", "Financials/Conglomerate", "NYSE", "USD",
        '{"US": 0.87, "International": 0.13}',
        '{"insurance": 0.28, "railroad": 0.14, "utilities": 0.10, "manufacturing": 0.20, "equities": 0.28}',
        '{"rate_sensitive": true, "insurance": true, "value": true, "conglomerate": true}',
    ),
    (
        "JPM", "JPMorgan Chase & Co.", "Financials/Banking", "NYSE", "USD",
        '{"US": 0.65, "Europe": 0.18, "Asia": 0.17}',
        '{"consumer_banking": 0.35, "investment_banking": 0.30, "commercial_banking": 0.15, "asset_management": 0.20}',
        '{"rate_sensitive": true, "banking": true, "yield_curve": true, "credit_cycle": true}',
    ),
    (
        "TSM", "Taiwan Semiconductor Manufacturing", "Technology/Semiconductors", "NYSE", "USD",
        '{"Taiwan": 0.80, "Asia": 0.15, "US": 0.05}',
        '{"advanced_node": 0.53, "specialty": 0.30, "mature_node": 0.17}',
        '{"rate_sensitive": false, "ai_exposed": true, "semiconductor": true, "geopolitical_risk": true, "export_controlled": true}',
    ),
]


def _seed_company_profiles(conn: sqlite3.Connection) -> None:
    """Insert mock company profiles if they don't already exist."""
    for row in _COMPANY_PROFILES_SEED:
        conn.execute(
            """INSERT OR IGNORE INTO company_profiles
               (ticker, company_name, sector, listed_market, pricing_currency,
                geo_exposure_json, revenue_segments_json, characteristics_json)
               VALUES (?,?,?,?,?,?,?,?)""",
            row,
        )
