#!/usr/bin/env python3
"""
gov-tracker orchestrator
Pipeline: collector → analyzer → notifier
"""
import logging
import os
import sys
from typing import Optional

from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("main")

_REQUIRED_ENV = ["ANTHROPIC_API_KEY", "NTFY_CHANNEL"]


def main() -> None:
    missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
    if missing:
        logger.error("Missing required environment variables: %s", missing)
        sys.exit(1)

    # Optional — enables direct Truth Social API; falls back to Google News RSS if absent
    truth_social_token: Optional[str] = os.getenv("TRUTH_SOCIAL_BEARER_TOKEN") or None
    anthropic_key: str = os.environ["ANTHROPIC_API_KEY"]
    ntfy_channel: str = os.environ["NTFY_CHANNEL"]
    relevance_threshold: float = float(os.getenv("RELEVANCE_THRESHOLD", "5"))

    # Late imports so env vars are loaded before any module-level config
    import anthropic as anthropic_sdk

    from db.init_db import get_connection, init_db
    from collector.truth_social import fetch_new_posts
    from collector.federal_register import fetch_new_documents
    from collector.international import (
        fetch_denmark_news, fetch_eu_news,
        fetch_china_news, fetch_reuters_news, fetch_us_corporate_news,
        fetch_marketwatch_news, fetch_ft_news, fetch_cnbc_news,
        fetch_bloomberg_news, fetch_cls_news, fetch_sina_finance,
    )
    from collector.guru_trades import fetch_guru_trades
    from analyzer.llm import analyze_unprocessed
    from notifier.ntfy import send_pending_notifications
    from db.sync_to_supabase import sync_to_supabase

    init_db()

    conn = get_connection()
    try:
        # ── Collector ────────────────────────────────────────────────
        logger.info("=== Collector ===")
        ts_ids  = fetch_new_posts(conn, truth_social_token)
        fr_ids  = fetch_new_documents(conn)
        dk_ids  = fetch_denmark_news(conn)
        eu_ids  = fetch_eu_news(conn)
        cn_ids  = fetch_china_news(conn)
        rt_ids  = fetch_reuters_news(conn)
        usc_ids = fetch_us_corporate_news(conn)
        mw_ids  = fetch_marketwatch_news(conn)
        ft_ids  = fetch_ft_news(conn)
        cb_ids  = fetch_cnbc_news(conn)
        bl_ids  = fetch_bloomberg_news(conn)
        cls_ids = fetch_cls_news(conn)
        sf_ids  = fetch_sina_finance(conn)
        guru_ids = fetch_guru_trades(conn)
        total = (
            len(ts_ids) + len(fr_ids) + len(dk_ids) + len(eu_ids) + len(cn_ids)
            + len(rt_ids) + len(usc_ids) + len(mw_ids) + len(ft_ids) + len(cb_ids)
            + len(bl_ids) + len(cls_ids) + len(sf_ids) + len(guru_ids)
        )
        logger.info(
            "New items: %d total | Trump %d | FedReg %d | Denmark %d | EU %d | "
            "China %d | Reuters %d | USCorp %d | MarketWatch %d | FT %d | "
            "CNBC %d | Bloomberg %d | 财联社 %d | 新浪 %d | Guru/ARK %d",
            total, len(ts_ids), len(fr_ids), len(dk_ids), len(eu_ids),
            len(cn_ids), len(rt_ids), len(usc_ids), len(mw_ids), len(ft_ids),
            len(cb_ids), len(bl_ids), len(cls_ids), len(sf_ids), len(guru_ids),
        )

        # ── Analyzer ─────────────────────────────────────────────────
        logger.info("=== Analyzer ===")
        client = anthropic_sdk.Anthropic(api_key=anthropic_key)
        analysis_ids = analyze_unprocessed(conn, client)

        # ── Notifier ─────────────────────────────────────────────────
        logger.info("=== Notifier ===")
        sent = send_pending_notifications(conn, ntfy_channel, relevance_threshold)

        # ── Sync to Supabase (production DB read by the Railway API) ──
        logger.info("=== Supabase sync ===")
        try:
            sync_to_supabase(conn)
        except Exception:
            logger.exception("Supabase sync failed (non-fatal)")

        logger.info(
            "Run complete — new posts: %d, analyses: %d, notifications: %d",
            total,
            len(analysis_ids),
            sent,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
