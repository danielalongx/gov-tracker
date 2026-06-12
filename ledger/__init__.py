"""
Ledger — persistent accumulation layer for the scoring engine.

Two tables:
  - event_ledger        : one row per (signal, ticker, mechanism channel)
                           contribution, written once when a signal is
                           classified (event/pipeline.py).
  - daily_score_snapshot: one row per (ticker, date) with the aggregated
                           event-layer score, narrative sensitivity, and
                           industry heat for that day (snapshot.py).
                           structural_score / composite_score columns exist
                           but are left NULL until pillars/ and composite/
                           are implemented (Phase 2+).

Per the v2.0 spec's emphasis on starting data collection early
("越晚开始积累，Phase 3的统计校准就越晚才能做"), this module is designed to run on
every pipeline execution (see main.py) so history accumulates from day one,
even while the composite/structural layers are still placeholders.
"""
