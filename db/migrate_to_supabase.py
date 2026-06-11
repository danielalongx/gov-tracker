"""
One-time migration script: copy all data from local SQLite to Supabase PostgreSQL.

Usage:
    DATABASE_URL=postgresql://postgres:[password]@[host]:5432/postgres python db/migrate_to_supabase.py

Steps:
1. Set DATABASE_URL to your Supabase connection string
2. Run this script once — it creates tables and copies all existing data
3. From then on, set DATABASE_URL in .env and GitHub Secrets — the pipeline uses Supabase automatically
"""
import os
import sys
import sqlite3
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

DATA_DIR = Path(__file__).parent.parent / "data"
SQLITE_PATH = DATA_DIR / "gov_tracker.db"
PG_SCHEMA = Path(__file__).parent / "schema_pg.sql"


def migrate():
    db_url = os.getenv("DATABASE_URL", "")
    if not (db_url.startswith("postgresql") or db_url.startswith("postgres")):
        print("ERROR: Set DATABASE_URL to your Supabase connection string first.")
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        print("ERROR: pip install psycopg2-binary first.")
        sys.exit(1)

    if not SQLITE_PATH.exists():
        print(f"SQLite DB not found at {SQLITE_PATH} — nothing to migrate.")
        sys.exit(0)

    print(f"Connecting to Supabase...")
    pg = psycopg2.connect(db_url)
    pg.autocommit = True
    pgc = pg.cursor()

    print("Creating tables from schema_pg.sql...")
    with open(PG_SCHEMA) as f:
        pgc.execute(f.read())
    print("Tables ready.")

    sq = sqlite3.connect(str(SQLITE_PATH))
    sq.row_factory = sqlite3.Row

    # --- posts ---
    rows = sq.execute("SELECT * FROM posts").fetchall()
    print(f"Migrating {len(rows)} posts...")
    for r in rows:
        pgc.execute("""
            INSERT INTO posts (id, source, post_id, content, author, source_name,
                article_published_at, article_url, posted_at, fetched_at, processed)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, post_id) DO NOTHING
        """, (r['id'], r['source'], r['post_id'], r['content'], r['author'],
              r['source_name'], r['article_published_at'], r['article_url'],
              r['posted_at'], r['fetched_at'], bool(r['processed'])))

    # --- analysis ---
    rows = sq.execute("SELECT * FROM analysis").fetchall()
    print(f"Migrating {len(rows)} analysis rows...")
    for r in rows:
        cols = r.keys()
        tickers = r['tickers'] if isinstance(r['tickers'], str) else json.dumps(r['tickers'] or [])
        industries = r['industries'] if isinstance(r['industries'], str) else json.dumps(r['industries'] or [])
        companies = r['companies'] if isinstance(r['companies'], str) else json.dumps(r['companies'] or [])
        category = r['category'] if 'category' in cols else None
        disclaimer = r['disclaimer'] if 'disclaimer' in cols else None
        pgc.execute("""
            INSERT INTO analysis (id, post_id, is_relevant, sentiment, tickers, industries,
                companies, relevance_score, summary, source_name, disclaimer,
                score_news, score_financial, score_pipeline, score_regulatory, score_capital_flows,
                analyzed_at, notified, notified_at, hold_for_digest, category)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
        """, (r['id'], r['post_id'], bool(r['is_relevant']), r['sentiment'],
              tickers, industries, companies, r['relevance_score'], r['summary'],
              r['source_name'], disclaimer,
              r['score_news'] or 0, r['score_financial'] or 0,
              r['score_pipeline'] or 0, r['score_regulatory'] or 0,
              r['score_capital_flows'] or 0,
              r['analyzed_at'], bool(r['notified']), r['notified_at'],
              bool(r['hold_for_digest'] or 0), category))

    # --- user_watchlist ---
    try:
        rows = sq.execute("SELECT * FROM user_watchlist").fetchall()
    except sqlite3.OperationalError:
        rows = []
    print(f"Migrating {len(rows)} user_watchlist rows...")
    for r in rows:
        weights = r['weights']
        if weights is not None and not isinstance(weights, str):
            weights = json.dumps(weights)
        pgc.execute("""
            INSERT INTO user_watchlist (id, user_id, ticker, name, sector, added_at, weights)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (user_id, ticker) DO NOTHING
        """, (r['id'], r['user_id'], r['ticker'], r['name'], r['sector'], r['added_at'], weights))

    # --- mechanisms ---
    try:
        rows = sq.execute("SELECT * FROM mechanisms").fetchall()
    except sqlite3.OperationalError:
        rows = []
    print(f"Migrating {len(rows)} mechanisms rows...")
    for r in rows:
        pgc.execute("""
            INSERT INTO mechanisms (id, signal_id, mechanism_type, description, direction, created_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
        """, (r['id'], r['signal_id'], r['mechanism_type'], r['description'], r['direction'], r['created_at']))

    # --- signal_company_links ---
    try:
        rows = sq.execute("SELECT * FROM signal_company_links").fetchall()
    except sqlite3.OperationalError:
        rows = []
    print(f"Migrating {len(rows)} signal_company_links rows...")
    for r in rows:
        pgc.execute("""
            INSERT INTO signal_company_links (id, signal_id, ticker, impact_direction, impact_magnitude, price_in_ratio, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
        """, (r['id'], r['signal_id'], r['ticker'], r['impact_direction'], r['impact_magnitude'], r['price_in_ratio'], r['created_at']))

    # Keep SERIAL sequences in sync with the migrated max ids, since we
    # inserted explicit ids above.
    for table in ("posts", "analysis", "user_watchlist", "mechanisms", "signal_company_links"):
        pgc.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
        )

    sq.close()
    pg.close()
    print("Migration complete!")
    print("\nNext steps:")
    print("1. Add DATABASE_URL to .env")
    print("2. Add DATABASE_URL to GitHub Secrets (repo Settings → Secrets → Actions)")
    print("3. Remove the cache steps from .github/workflows/poll.yml (no longer needed)")


if __name__ == "__main__":
    migrate()
