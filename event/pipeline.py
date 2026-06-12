"""
Event-layer pipeline — turns newly analyzed signals (analysis rows with
event_processed = 0) into event_ledger rows.

For each unprocessed signal:
  1. Classify mechanism_type(s) from the summary (mechanism_classifier).
  2. For each ticker mentioned in the signal, compute per-mechanism
     contributions (raw_score.compute_event_contributions), using a
     cross-sectional PE percentile so the high_forward_pe feature is
     continuous rather than a binary flag.
  3. Record each contribution in event_ledger (ledger.event_ledger).
  4. Mark the signal as event_processed = 1, regardless of whether any
     contributions were produced (no mechanism match / ticker not in
     company_profiles are both valid "nothing to record" outcomes).

This keeps the event layer decoupled from the analyzer — it can run on
every pipeline execution and simply no-ops for signals that don't touch any
of the 5 tracked mechanism types or any of the ~10 profiled tickers.
"""
from __future__ import annotations

import json
import logging

from db.connection import qmark
from event.exposure import compute_pe_percentiles
from event.mechanism_classifier import classify_mechanisms
from event.raw_score import compute_event_contributions
from ledger.event_ledger import record_event

logger = logging.getLogger(__name__)


def _load_json_list(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def _pe_percentiles(conn) -> dict[str, float]:
    """Cross-sectional PE percentile for every ticker in company_profiles,
    using the latest stock_snapshots.pe_ratio."""
    cur = conn.execute(
        """
        SELECT cp.ticker AS ticker, s.pe_ratio AS pe_ratio
        FROM company_profiles cp
        LEFT JOIN (
            SELECT ticker, pe_ratio,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY fetched_at DESC) AS rn
            FROM stock_snapshots
        ) s ON s.ticker = cp.ticker AND s.rn = 1
        """
    )
    pairs = [(row["ticker"], row["pe_ratio"]) for row in cur.fetchall()]
    return compute_pe_percentiles(pairs)


def _fetch_unprocessed(conn) -> list[dict]:
    ph = qmark(conn)
    cur = conn.execute(
        f"SELECT id, tickers, industries, summary FROM analysis WHERE event_processed = {ph} OR event_processed IS NULL",
        (0,),
    )
    return [dict(r) for r in cur.fetchall()]


def _mark_processed(conn, signal_id: int) -> None:
    ph = qmark(conn)
    conn.execute(f"UPDATE analysis SET event_processed = {ph} WHERE id = {ph}", (1, signal_id))


def process_new_signals(conn) -> int:
    """
    Process all analysis rows with event_processed = 0 (or NULL).
    Returns the number of signals processed (not the number of event_ledger
    rows written — a signal can produce 0, 1, or many contributions).
    """
    rows = _fetch_unprocessed(conn)
    if not rows:
        return 0

    pe_percentiles = _pe_percentiles(conn)
    processed = 0

    for row in rows:
        signal_id = row["id"]
        try:
            tickers = _load_json_list(row.get("tickers"))
            industries = _load_json_list(row.get("industries"))
            summary = row.get("summary") or ""

            mechanism_types = classify_mechanisms(summary, industries)
            if mechanism_types:
                for ticker in tickers:
                    ticker = (ticker or "").strip().upper()
                    if not ticker:
                        continue
                    pe_pct = pe_percentiles.get(ticker)
                    contributions = compute_event_contributions(
                        conn, mechanism_types, ticker, pe_percentile=pe_pct
                    )
                    for contribution in contributions:
                        record_event(conn, signal_id, ticker, contribution)
        except Exception:
            logger.exception("Event pipeline failed for signal_id=%s (marking processed anyway)", signal_id)
        finally:
            _mark_processed(conn, signal_id)
            processed += 1

    conn.commit()
    return processed
