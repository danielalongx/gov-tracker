"""
Validation — statistical calibration & sanity checks (Phase 3/4, NOT YET
IMPLEMENTED).

Per the v2.0 spec, once daily_score_snapshot has enough history (suggested
minimum: several months of daily snapshots across the tracked universe),
this module is responsible for:

  - Fama-MacBeth cross-sectional regressions of forward returns on
    event_raw_score / narrative_sensitivity / industry_heat / structural
    pillar scores, to estimate real-world coefficient weights for
    composite/ (replacing the placeholder hard-coded weights).
  - Neutrality checks: confirming that at the market-mean level, composite
    coefficients converge to ~1.0 (i.e. the score doesn't have a structural
    long/short bias baked in).
  - Backtesting: turning daily_score_snapshot history into a simple
    long/short or rank-IC backtest to sanity-check that the composite score
    has predictive value before it's used for real signals.
  - Drift monitoring: flagging when a mechanism_rules weight or half-life
    assumption (event/, db/init_db.py:_HALF_LIFE_DAYS) looks stale relative
    to realized decay patterns in event_ledger.

Why deferred: all of the above requires daily_score_snapshot history that
doesn't exist yet. ledger/snapshot.py starts writing this history on every
pipeline run — this module becomes actionable once there's enough of it
(realistically months, not days).

Phase 3/4 entry points (sketch):
    run_fama_macbeth(conn, lookback_days) -> dict[str, float]   # coefficient weights
    check_neutrality(conn) -> dict                              # diagnostics
    backtest_composite(conn, lookback_days) -> dict             # IC / returns summary
"""
