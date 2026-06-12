"""
Daily score snapshot — aggregates the event ledger (with time decay),
narrative sensitivity, and industry heat into one row per
(ticker, snapshot_date) in daily_score_snapshot.

    event_raw_score = Σ_e [ raw_contribution_e × exp(-days_since_event_e / half_life_e) ]

structural_score and composite_score are left NULL — those belong to the
pillars/ and composite/ layers (Phase 2/3, not yet implemented). Per Wayne's
spec emphasis on starting accumulation early, this is designed to run on
every pipeline execution so history builds up from day one even while those
layers are still placeholders.

components_json stores the per-event breakdown (mechanism_type,
affects_feature, contribution at this date) for transparency/debugging.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone

from db.connection import is_postgres, qmark
from event.industry_heat import company_heat, compute_sector_heat
from event.narrative_sensitivity import compute_narrative_sensitivity
from ledger.event_ledger import get_active_events
from technical.support_resistance import compute_technical_scores

logger = logging.getLogger(__name__)


def _days_since(event_date: str, snapshot_date: date) -> float:
    try:
        ed = datetime.strptime(event_date[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return 0.0
    return max((snapshot_date - ed).days, 0)


def _compute_event_raw_score(conn, ticker: str, snapshot_date: date) -> tuple[float, list[dict]]:
    events = get_active_events(conn, ticker)
    total = 0.0
    components = []
    for ev in events:
        half_life = float(ev.get("half_life_days") or 90)
        days = _days_since(ev["event_date"], snapshot_date)
        decay = math.exp(-days / half_life) if half_life > 0 else 0.0
        contribution = float(ev["raw_contribution"]) * decay
        total += contribution
        components.append({
            "mechanism_type": ev["mechanism_type"],
            "affects_feature": ev["affects_feature"],
            "event_date": ev["event_date"],
            "days_since": days,
            "decay": decay,
            "raw_contribution_t0": ev["raw_contribution"],
            "contribution_now": contribution,
        })
    return total, components


def _upsert_snapshot(conn, row: dict) -> None:
    cols = (
        "ticker", "snapshot_date", "event_raw_score", "narrative_sensitivity",
        "industry_heat", "technical_score", "structural_score", "composite_score",
        "components_json",
    )
    values = tuple(row[c] for c in cols)
    ph = qmark(conn)
    placeholders = ", ".join([ph] * len(cols))
    if is_postgres(conn):
        update_cols = ", ".join(
            f"{c}=EXCLUDED.{c}" for c in cols if c not in ("ticker", "snapshot_date")
        )
        sql = (
            f"INSERT INTO daily_score_snapshot ({', '.join(cols)}) VALUES ({placeholders})"
            f" ON CONFLICT (ticker, snapshot_date) DO UPDATE SET {update_cols}"
        )
    else:
        sql = f"INSERT OR REPLACE INTO daily_score_snapshot ({', '.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, values)


def write_daily_snapshot(conn, snapshot_date: str | None = None) -> int:
    """
    Compute and upsert one daily_score_snapshot row per ticker in
    company_profiles. Returns the number of rows written.
    """
    if snapshot_date is None:
        snap_date = datetime.now(timezone.utc).date()
        snapshot_date = snap_date.isoformat()
    else:
        snap_date = datetime.strptime(snapshot_date[:10], "%Y-%m-%d").date()

    profiles = {row["ticker"]: dict(row) for row in conn.execute("SELECT * FROM company_profiles")}
    if not profiles:
        return 0

    narrative = compute_narrative_sensitivity(conn)
    sector_heat = compute_sector_heat(conn)

    # Technical layer (volume-confirmed support/resistance) — does one
    # yfinance history fetch per ticker, so compute once up front rather
    # than per-ticker inside the loop below.
    try:
        technical = compute_technical_scores(conn)
    except Exception:
        logger.exception("Technical layer failed (non-fatal); defaulting to neutral")
        technical = {}

    written = 0
    for ticker, profile in profiles.items():
        event_raw_score, components = _compute_event_raw_score(conn, ticker, snap_date)
        heat = company_heat(profile, sector_heat)
        tech = technical.get(ticker, {"score": 0.0, "detail": {"available": False}})

        row = {
            "ticker": ticker,
            "snapshot_date": snapshot_date,
            "event_raw_score": event_raw_score,
            "narrative_sensitivity": narrative.get(ticker, 0.0),
            "industry_heat": heat,
            "technical_score": tech["score"],
            "structural_score": None,
            "composite_score": None,
            "components_json": json.dumps(
                {"events": components, "technical": tech["detail"]},
                ensure_ascii=False,
            ),
        }
        _upsert_snapshot(conn, row)
        written += 1

    conn.commit()
    return written
