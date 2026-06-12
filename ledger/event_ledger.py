"""Write helpers for the event_ledger table."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from db.connection import qmark


def record_event(conn, signal_id: int, ticker: str, contribution: dict, event_date: str | None = None) -> None:
    """
    Insert one event_ledger row. `contribution` is a dict produced by
    event.raw_score.compute_event_contributions(), with keys:
        mechanism_type, affects_feature, direction, base_strength,
        confidence, reliability, exposure, half_life_days, raw_contribution
    `event_date` defaults to today (UTC, ISO date).
    """
    event_date = event_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ph = qmark(conn)
    conn.execute(
        f"""
        INSERT INTO event_ledger
            (signal_id, ticker, mechanism_type, affects_feature, direction,
             base_strength, confidence, reliability, exposure,
             half_life_days, event_date, raw_contribution)
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """,
        (
            signal_id,
            ticker,
            contribution["mechanism_type"],
            contribution["affects_feature"],
            contribution["direction"],
            contribution["base_strength"],
            contribution["confidence"],
            contribution["reliability"],
            contribution["exposure"],
            contribution["half_life_days"],
            event_date,
            contribution["raw_contribution"],
        ),
    )


def get_active_events(conn, ticker: str, lookback_days: int = 365) -> list[dict]:
    """
    Return event_ledger rows for `ticker` from the last `lookback_days`
    (anything older has effectively decayed to ~0 for any reasonable
    half-life and can be ignored for snapshot computation).
    """
    ph = qmark(conn)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    cur = conn.execute(
        f"SELECT * FROM event_ledger WHERE ticker = {ph} AND event_date >= {ph}",
        (ticker, cutoff),
    )
    return [dict(r) for r in cur.fetchall()]
