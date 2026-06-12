"""
Pillars — 5-pillar structural layer (Phase 2/3, NOT YET IMPLEMENTED).

Per the v2.0 spec, each company's structural_score is a weighted blend of
five pillars, each itself a robust z-score normalized within the tracked
universe:

    1. Valuation       — PE/PB/EV-EBITDA percentile vs. sector & history
    2. Quality         — ROE, margin stability, balance-sheet strength
    3. Growth          — revenue/earnings growth trajectory & estimates
    4. Momentum        — price/earnings momentum, analyst revision trends
    5. Capital Flows   — institutional ownership changes, insider activity,
                          ARK/guru holdings deltas (we already collect
                          insider_trades and ark_holdings — these are the
                          natural Phase 2 starting point)

Why deferred: pillars 1/2/3 need real fundamentals data (balance sheet,
income statement, analyst estimates) which collector/financials.py does not
yet provide beyond a single point-in-time snapshot (price, PE, market cap,
target price, EPS-TTM, 52w range). Building this properly requires either a
fundamentals data API or a time series of stock_snapshots long enough to
derive growth/momentum — i.e. it benefits from the same "start accumulating
now" logic that motivated building ledger/ first.

Phase 2 entry point (once fundamentals data exists):
    compute_structural_score(conn, ticker) -> float | None
to be written into daily_score_snapshot.structural_score.
"""
