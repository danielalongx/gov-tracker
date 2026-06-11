"""
Incremental sync: push newly-collected posts/analysis rows from the local
SQLite working DB to Supabase PostgreSQL.

Why this exists: the collector/analyzer/notifier pipeline (main.py) is written
against sqlite3's API (conn.execute with '?' placeholders, row_factory, etc.)
and continues to run against the local SQLite file in GitHub Actions (cached
between runs). The FastAPI service on Railway reads from Supabase Postgres
(see db/connection.py). This module bridges the two: after each pipeline run,
copy any rows newer than what's already in Postgres, so the public API stays
up to date without rewriting the whole pipeline to be Postgres-native.

Safe to call every run:
- No-op if DATABASE_URL isn't set to a postgres:// URL.
- No-op (logs and returns) if the Postgres connection fails.
- Uses MAX(id) in Postgres + ON CONFLICT DO NOTHING, so re-running never
  duplicates rows.
"""
import json
import logging
import os
import sqlite3

logger = logging.getLogger(__name__)


def _to_jsonb(val):
    if val is None:
        return json.dumps([])
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)


def sync_to_supabase(sqlite_conn: sqlite3.Connection) -> None:
    db_url = os.getenv("DATABASE_URL", "")
    if not (db_url.startswith("postgresql") or db_url.startswith("postgres")):
        return

    try:
        import psycopg2
    except ImportError:
        logger.warning("Supabase sync: psycopg2 not installed, skipping")
        return

    try:
        pg = psycopg2.connect(db_url, connect_timeout=10)
    except Exception as e:
        logger.error("Supabase sync: connection failed: %s", e)
        return

    try:
        pgc = pg.cursor()

        # Columns added after the original schema_pg.sql — keep idempotent.
        pgc.execute("ALTER TABLE analysis ADD COLUMN IF NOT EXISTS signal_class TEXT DEFAULT 'A'")

        # --- posts ---
        pgc.execute("SELECT COALESCE(MAX(id), 0) FROM posts")
        max_post_id = pgc.fetchone()[0]
        post_rows = sqlite_conn.execute(
            "SELECT * FROM posts WHERE id > ? ORDER BY id", (max_post_id,)
        ).fetchall()
        for r in post_rows:
            pgc.execute("""
                INSERT INTO posts (id, source, post_id, content, author, source_name,
                    article_published_at, article_url, posted_at, fetched_at, processed)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (source, post_id) DO NOTHING
            """, (r["id"], r["source"], r["post_id"], r["content"], r["author"],
                  r["source_name"], r["article_published_at"], r["article_url"],
                  r["posted_at"], r["fetched_at"], bool(r["processed"])))

        # --- analysis ---
        pgc.execute("SELECT COALESCE(MAX(id), 0) FROM analysis")
        max_analysis_id = pgc.fetchone()[0]
        analysis_rows = sqlite_conn.execute(
            "SELECT * FROM analysis WHERE id > ? ORDER BY id", (max_analysis_id,)
        ).fetchall()
        for r in analysis_rows:
            cols = r.keys()
            category = r["category"] if "category" in cols else None
            signal_class = r["signal_class"] if "signal_class" in cols else "A"
            pgc.execute("""
                INSERT INTO analysis (id, post_id, is_relevant, sentiment, tickers, industries,
                    companies, relevance_score, summary, source_name,
                    score_news, score_financial, score_pipeline, score_regulatory, score_capital_flows,
                    analyzed_at, notified, notified_at, hold_for_digest, category, signal_class)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """, (r["id"], r["post_id"], bool(r["is_relevant"]), r["sentiment"],
                  _to_jsonb(r["tickers"]), _to_jsonb(r["industries"]), _to_jsonb(r["companies"]),
                  r["relevance_score"], r["summary"], r["source_name"],
                  r["score_news"] or 0, r["score_financial"] or 0,
                  r["score_pipeline"] or 0, r["score_regulatory"] or 0,
                  r["score_capital_flows"] or 0,
                  r["analyzed_at"], bool(r["notified"]), r["notified_at"],
                  bool(r["hold_for_digest"] or 0), category, signal_class))

        # Keep SERIAL sequences in sync since we inserted explicit ids.
        for table in ("posts", "analysis"):
            pgc.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )

        pg.commit()
        logger.info(
            "Supabase sync: %d new post(s), %d new analysis row(s)",
            len(post_rows), len(analysis_rows),
        )
    except Exception as e:
        logger.error("Supabase sync error: %s", e)
        pg.rollback()
    finally:
        pg.close()
