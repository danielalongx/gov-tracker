"""
Event layer — mechanism transmission chain.

Implements the "Raw_i,t" event-score component from the 综合打分系统 v2.0 spec:

    Raw_i,t = Σ_e [ Direction_e × MechanismStrength_e × Exposure_i,e × Reliability_e × TimeDecay_e ]

Where, for each detected mechanism `e` triggered by a signal:
  - mechanism_type   : which macro/sector mechanism is in play (rate_high, ai_capex_rising, ...)
  - affects_feature  : which company-level feature the mechanism transmits through
  - direction        : +1 / -1, from mechanism_rules (does this feature help or hurt
                        a company under this mechanism)
  - base_strength    : 0-3, from mechanism_rules — how strong this channel is in general
  - reliability      : derived from mechanism_rules.confidence (consensus/moderate/situational)
  - exposure (Exposure_i,e) : 0-1, how exposed company i is to `affects_feature`
                        (see exposure.py)
  - half_life_days / TimeDecay_e : exp(-days_since_event / half_life) — applied at
                        snapshot time, not stored pre-computed (so it can be
                        recomputed for any date).

This module only covers the *event layer*. The structural (5-pillar) layer,
composite formula, risk gates, and statistical calibration are out of scope
for this pass — see pillars/, composite/, validation/ for placeholders.
"""
