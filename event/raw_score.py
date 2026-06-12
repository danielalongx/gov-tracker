"""
Computes event-layer raw-score contributions for a single (signal, ticker)
pair, by joining the signal's detected mechanism_type(s) against
mechanism_rules and the target company's profile.

Each contribution corresponds to one row that will be written to
event_ledger (see ledger/event_ledger.py). The stored `raw_contribution` is
the value at t=0 (TimeDecay_e = 1, i.e. exp(0) = 1); daily snapshots
(ledger/snapshot.py) re-apply exp(-days_since/half_life) for the current
date so the decay can be recomputed for any point in time without
re-deriving the original components.

    contribution_t0 = Direction_e × MechanismStrength_e × Exposure_i,e × Reliability_e
    contribution_t  = contribution_t0 × exp(-days_since_event / half_life_days)
"""
from __future__ import annotations

from db.connection import qmark
from event.exposure import compute_exposure

# mechanism_rules.confidence -> Reliability_e
RELIABILITY = {
    "consensus": 1.0,
    "moderate": 0.7,
    "situational": 0.4,
}


def _get_company_profile(conn, ticker: str) -> dict | None:
    ph = qmark(conn)
    cur = conn.execute(
        f"SELECT * FROM company_profiles WHERE ticker = {ph}", (ticker,)
    )
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def _get_mechanism_rules(conn, mechanism_type: str) -> list[dict]:
    ph = qmark(conn)
    cur = conn.execute(
        f"SELECT * FROM mechanism_rules WHERE mechanism_type = {ph}",
        (mechanism_type,),
    )
    return [dict(r) for r in cur.fetchall()]


def compute_event_contributions(
    conn,
    mechanism_types: list[str],
    ticker: str,
    pe_percentile: float | None = None,
) -> list[dict]:
    """
    Returns a list of dicts, one per (mechanism_type, affects_feature) pair
    that has non-zero exposure for `ticker`, with keys matching the
    event_ledger columns:
        mechanism_type, affects_feature, direction, base_strength,
        confidence, reliability, exposure, half_life_days, raw_contribution
    (raw_contribution is the t=0 value; signal_id/ticker/event_date/
    created_at are filled in by the caller).

    Returns [] if the company has no profile (not yet in company_profiles —
    company_profiles currently covers ~10 seeded mega-caps; expanding this
    table is a prerequisite for broader coverage).
    """
    profile = _get_company_profile(conn, ticker)
    if profile is None:
        return []

    contributions: list[dict] = []
    for mech_type in mechanism_types:
        rules = _get_mechanism_rules(conn, mech_type)
        for rule in rules:
            exposure = compute_exposure(profile, rule["affects_feature"], pe_percentile)
            if exposure <= 0:
                continue

            reliability = RELIABILITY.get(rule.get("confidence"), 0.5)
            base_strength = float(rule.get("base_strength") or 0)
            direction = int(rule.get("direction") or 0)
            half_life = float(rule.get("half_life_days") or 90)

            raw_t0 = direction * base_strength * exposure * reliability

            contributions.append({
                "mechanism_type": mech_type,
                "affects_feature": rule["affects_feature"],
                "direction": direction,
                "base_strength": base_strength,
                "confidence": rule.get("confidence") or "moderate",
                "reliability": reliability,
                "exposure": exposure,
                "half_life_days": half_life,
                "raw_contribution": raw_t0,
            })

    return contributions
