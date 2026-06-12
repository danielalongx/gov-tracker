"""
Technical indicator layer — volume-confirmed support/resistance levels.

Per Wayne's investment-psychology framing: "放量的支撑位对我来说是很重要的指标"
(a support level formed on heavy volume is an important indicator to me) —
a price level where a large amount of volume previously changed hands leaves
a stronger "memory" in the market. More participants have a cost basis at
that price, so it tends to act as support (on the way down) or resistance
(on the way up) the next time price revisits it. A level touched on
below-average volume is a weaker, more easily broken memory.

Implementation (Phase 1):
  1. Pull ~6 months of daily OHLCV per ticker via yfinance.
  2. Detect swing pivots — local lows are candidate support touches, local
     highs are candidate resistance touches — using a rolling window.
  3. Cluster nearby pivots (within CLUSTER_TOLERANCE of each other) into
     "levels". A level's strength is the sum of each pivot's volume relative
     to the ticker's average volume over the window: repeated touches and
     high-volume ("放量") touches both raise strength.
  4. For the current price, find the strongest support level below it and
     the strongest resistance level above it, within PROXIMITY_RANGE.
     Each level's "pull" on the score is its strength scaled down linearly
     by how far away it is — close + strong pulls hardest, far or weak
     pulls toward zero.
  5. raw_technical = support_pull - resistance_pull
       > 0  → price sits near a strong, volume-confirmed floor (bullish:
              a level where buyers have historically stepped in)
       < 0  → price sits near a strong, volume-confirmed ceiling (bearish:
              a level where sellers have historically stepped in)
  6. Cross-sectional z-score across the tracked universe, then tanh-bound
     to (-1, 1) — same pattern as event/narrative_sensitivity.py and
     event/industry_heat.py, and consistent with Wayne's "continuous,
     no discrete buckets" constraint on the scoring engine.

Network/data failures degrade gracefully: any ticker whose price history
can't be fetched gets score 0.0 (neutral) and is excluded from the
cross-sectional z-score, rather than crashing the pipeline.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

LOOKBACK_PERIOD = "6mo"     # ~6 months of daily bars
PIVOT_WINDOW = 5            # bars on each side to confirm a swing pivot
CLUSTER_TOLERANCE = 0.015   # group pivots within 1.5% of each other into one level
PROXIMITY_RANGE = 0.08      # only levels within 8% of current price pull on the score


def _fetch_history(ticker: str):
    """Fetch ~6 months of daily OHLCV. Returns None on any failure."""
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period=LOOKBACK_PERIOD, interval="1d")
        if df is None or df.empty or len(df) < 2 * PIVOT_WINDOW + 1:
            return None
        return df
    except Exception as e:
        logger.warning("technical: history fetch failed for %s: %s", ticker, e)
        return None


def _find_pivots(df) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """
    Returns (support_pivots, resistance_pivots), each a list of
    (price, volume_ratio) tuples. volume_ratio = bar volume / average volume
    over the window (>1 means "放量" / above-average volume at that touch).
    """
    lows = df["Low"].values
    highs = df["High"].values
    volumes = df["Volume"].values
    avg_volume = volumes.mean() if len(volumes) else 0.0

    support: list[tuple[float, float]] = []
    resistance: list[tuple[float, float]] = []
    n = len(df)
    w = PIVOT_WINDOW

    for i in range(w, n - w):
        window_lo = lows[i - w:i + w + 1]
        window_hi = highs[i - w:i + w + 1]
        vol_ratio = float(volumes[i] / avg_volume) if avg_volume > 0 else 1.0

        if lows[i] == window_lo.min():
            support.append((float(lows[i]), vol_ratio))
        if highs[i] == window_hi.max():
            resistance.append((float(highs[i]), vol_ratio))

    return support, resistance


def _cluster_levels(pivots: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """
    Group pivots within CLUSTER_TOLERANCE of each other into levels.
    Returns a list of (level_price, strength), where level_price is the
    volume-weighted average price of its pivots and strength is the sum of
    volume_ratio across pivots in the cluster — repeated touches and
    high-volume ("放量") touches both raise strength.
    """
    if not pivots:
        return []

    pivots_sorted = sorted(pivots, key=lambda p: p[0])
    clusters: list[list[tuple[float, float]]] = []
    current = [pivots_sorted[0]]

    for price, vol_ratio in pivots_sorted[1:]:
        anchor = current[0][0]
        if anchor > 0 and abs(price - anchor) / anchor <= CLUSTER_TOLERANCE:
            current.append((price, vol_ratio))
        else:
            clusters.append(current)
            current = [(price, vol_ratio)]
    clusters.append(current)

    levels: list[tuple[float, float]] = []
    for cluster in clusters:
        total_weight = sum(v for _, v in cluster)
        if total_weight > 0:
            level_price = sum(p * v for p, v in cluster) / total_weight
        else:
            level_price = sum(p for p, _ in cluster) / len(cluster)
        levels.append((level_price, total_weight))

    return levels


def _level_pull(levels: list[tuple[float, float]], price: float, direction: str) -> float:
    """
    direction: "support"    -> only consider levels at or below price
               "resistance" -> only consider levels at or above price

    Returns the strongest nearby level's "pull": its strength scaled
    linearly toward 0 as distance approaches PROXIMITY_RANGE.
    """
    if price <= 0:
        return 0.0

    best = 0.0
    for level_price, strength in levels:
        if direction == "support" and level_price > price:
            continue
        if direction == "resistance" and level_price < price:
            continue
        distance = abs(price - level_price) / price
        if distance > PROXIMITY_RANGE:
            continue
        proximity = 1.0 - (distance / PROXIMITY_RANGE)
        pull = strength * proximity
        best = max(best, pull)
    return best


def _ticker_raw_technical(ticker: str) -> Optional[dict]:
    """
    Returns a dict with the raw (pre-z-score) technical signal and the
    supporting level detail, or None if price history is unavailable.
    """
    df = _fetch_history(ticker)
    if df is None:
        return None

    support_pivots, resistance_pivots = _find_pivots(df)
    support_levels = _cluster_levels(support_pivots)
    resistance_levels = _cluster_levels(resistance_pivots)

    price = float(df["Close"].iloc[-1])

    support_pull = _level_pull(support_levels, price, "support")
    resistance_pull = _level_pull(resistance_levels, price, "resistance")

    return {
        "raw": support_pull - resistance_pull,
        "price": price,
        "support_pull": support_pull,
        "resistance_pull": resistance_pull,
        "support_levels": sorted(support_levels, key=lambda lv: -lv[1])[:3],
        "resistance_levels": sorted(resistance_levels, key=lambda lv: -lv[1])[:3],
    }


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


def compute_technical_scores(conn) -> dict[str, dict]:
    """
    Returns {ticker: {"score": float, "detail": {...}}} for every ticker in
    company_profiles.

    score is tanh-bounded in (-1, 1):
      > 0  → price sits near a strong, volume-confirmed support level
             (bullish per Wayne's framing: 放量支撑位)
      < 0  → price sits near a strong, volume-confirmed resistance level
             (bearish: 放量阻力位)
      0    → no nearby high-conviction level, or price history unavailable

    detail carries the underlying levels/price for transparency
    (components_json in daily_score_snapshot).
    """
    tickers = [row["ticker"] for row in conn.execute("SELECT ticker FROM company_profiles")]

    raw: dict[str, float] = {}
    details: dict[str, dict] = {}

    for ticker in tickers:
        info = _ticker_raw_technical(ticker)
        if info is None:
            details[ticker] = {"available": False}
            continue

        raw[ticker] = info["raw"]
        details[ticker] = {
            "available": True,
            "price": info["price"],
            "support_pull": info["support_pull"],
            "resistance_pull": info["resistance_pull"],
            "support_levels": [{"price": p, "strength": s} for p, s in info["support_levels"]],
            "resistance_levels": [{"price": p, "strength": s} for p, s in info["resistance_levels"]],
        }

    z = _zscore(raw)

    result: dict[str, dict] = {}
    for ticker in tickers:
        score = math.tanh(z.get(ticker, 0.0))
        detail = details.get(ticker, {"available": False})
        detail["raw_zscore"] = z.get(ticker, 0.0)
        result[ticker] = {"score": score, "detail": detail}

    return result
