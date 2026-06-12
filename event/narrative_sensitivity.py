"""
Narrative sensitivity (NE_i) — continuous, per-company score for "how much
does this stock move on news/sentiment vs. fundamentals". Used as the
channel-tilt input (S_i = tanh(NE_i) × tanh(AP_i) in the v2.0 spec) so that,
e.g., TSLA and PLTR can get different weightings between narrative and
fundamental signals even though both are "high-beta growth" names — per
Wayne's explicit requirement for continuous, non-grouped scores.

Reduced-scope implementation (Phase 1) — built only from data we already
collect, no new API integrations:

  - valuation premium proxy: trailing-PE percentile rank within the tracked
    universe (from stock_snapshots, latest reading per ticker)
  - price-range volatility proxy: (52w_high - 52w_low) / price — wide range
    relative to price suggests a more sentiment-driven name
  - AI/semiconductor/hype-sector flag from company_profiles.characteristics_json
    (ai_exposed / semiconductor) as a categorical tilt

These three z-scored components are averaged and passed through tanh to
bound the result to (-1, 1), per the spec's "no unbounded coefficients"
principle.

TODO(Phase 2+): replace/extend with the full proxy set from the v2.0 spec
once available — short interest %, options OI/market cap, analyst forecast
dispersion, and news-mention growth rate (industry_heat.py already computes
mention growth at the sector level; a per-company version could feed in here).
"""
from __future__ import annotations

import json
import math

from db.connection import qmark


def _load_json(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _zscore(values: dict[str, float]) -> dict[str, float]:
    if len(values) < 2:
        return {k: 0.0 for k in values}
    xs = list(values.values())
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    std = math.sqrt(var)
    if std == 0:
        return {k: 0.0 for k in values}
    return {k: (v - mean) / std for k, v in values.items()}


def _latest_snapshots(conn) -> dict[str, dict]:
    """Most recent stock_snapshots row per ticker."""
    cur = conn.execute(
        """
        SELECT s.* FROM stock_snapshots s
        INNER JOIN (
            SELECT ticker, MAX(fetched_at) AS max_fetched
            FROM stock_snapshots GROUP BY ticker
        ) latest ON s.ticker = latest.ticker AND s.fetched_at = latest.max_fetched
        """
    )
    return {row["ticker"]: dict(row) for row in cur.fetchall()}


def compute_narrative_sensitivity(conn) -> dict[str, float]:
    """
    Returns {ticker: NE_i} for every ticker in company_profiles, NE_i in
    roughly (-1, 1) via tanh. Tickers with insufficient snapshot data fall
    back to the categorical (ai/semiconductor flag) component only.
    """
    profiles = {row["ticker"]: dict(row) for row in conn.execute("SELECT * FROM company_profiles")}
    if not profiles:
        return {}

    snapshots = _latest_snapshots(conn)

    pe_values: dict[str, float] = {}
    range_values: dict[str, float] = {}
    flag_values: dict[str, float] = {}

    for ticker, profile in profiles.items():
        ch = _load_json(profile.get("characteristics_json"))
        flag_values[ticker] = (
            1.0 if ch.get("ai_exposed") else 0.0
        ) + (
            1.0 if ch.get("semiconductor") else 0.0
        )

        snap = snapshots.get(ticker)
        if not snap:
            continue
        pe = snap.get("pe_ratio")
        if pe and pe > 0:
            pe_values[ticker] = pe

        price = snap.get("price")
        hi = snap.get("week52_high")
        lo = snap.get("week52_low")
        if price and hi and lo and price > 0:
            range_values[ticker] = (hi - lo) / price

    pe_z = _zscore(pe_values)
    range_z = _zscore(range_values)
    flag_z = _zscore(flag_values)

    result: dict[str, float] = {}
    for ticker in profiles:
        components = []
        if ticker in pe_z:
            components.append(pe_z[ticker])
        if ticker in range_z:
            components.append(range_z[ticker])
        components.append(flag_z.get(ticker, 0.0))

        avg = sum(components) / len(components) if components else 0.0
        result[ticker] = math.tanh(avg)

    return result
