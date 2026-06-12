"""
Composite — final score combination layer (Phase 3, NOT YET IMPLEMENTED).

Per the v2.0 spec, once event-layer (event/, ledger/) and structural-layer
(pillars/) scores both exist, this layer combines them into a single
FinalScore_i per company:

    Channel tilt:        S_i = tanh(NE_i) × tanh(AP_i)
    Industry correction: M_pos / M_neg, derived from industry_heat +
                          Credibility/Crowd terms, hard-clipped to [0.6, 1.6]
    Composite_i =  structural_score_i
                 + (event_raw_score_i × S_i × industry_correction_i)
    FinalScore_i = Composite_i, after risk-gate adjustments

Risk gates (Phase 3/4, also deferred):
    - Liquidity gate (avoid illiquid names dominating the ranking)
    - Concentration gate (single-mechanism dominance flag)
    - Data-quality gate (minimum event_ledger / snapshot history required
      before a ticker's composite score is considered reliable)

Why deferred: this layer's coefficients (the [0.6, 1.6] clip bounds, the
industry correction weights, the neutrality-at-market-mean calibration) are
meant to be fit via Fama-MacBeth regression against realized returns
(validation/), which requires daily_score_snapshot history to accumulate
first. event_raw_score, narrative_sensitivity, and industry_heat are already
being written to daily_score_snapshot every run (see ledger/snapshot.py) —
once enough history exists, this module can be implemented and calibrated.

Phase 3 entry point:
    compute_composite_score(conn, ticker, snapshot_date) -> float | None
to be written into daily_score_snapshot.composite_score.
"""
