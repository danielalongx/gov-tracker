"""
Exposure_i,e — how exposed company i is to a given mechanism `affects_feature`,
on a continuous 0-1 scale (per Wayne's requirement: no discrete archetype
buckets — every company gets its own number, even within the same sector).

Data sources currently available:
  - company_profiles.geo_exposure_json      ({"US": 0.5, "China": 0.2, ...})
  - company_profiles.revenue_segments_json  ({"datacenter": 0.82, ...})
  - company_profiles.characteristics_json   (boolean flags, e.g. ai_exposed)
  - stock_snapshots.pe_ratio                (for valuation-based features,
                                              via percentile rank across the
                                              tracked universe)

Where the underlying fundamentals don't exist yet (net cash, debt ratio,
interest coverage, FCF, gross margin, import-cost %, pricing power —
all of which need real balance-sheet/income-statement data), we fall back to
the boolean `characteristics_json` flag (1.0 / 0.0). This is a known
placeholder — flagged with TODO(fundamentals) — and should be replaced once
collector/financials.py (or a dedicated fundamentals API) provides real
ratios. Until then these features contribute, but only as a binary signal.
"""
from __future__ import annotations

import json
from typing import Optional


def _load_json(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def _flag(characteristics: dict, key: str) -> float:
    """TODO(fundamentals): binary placeholder until real ratios are available."""
    return 1.0 if characteristics.get(key) else 0.0


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


# affects_feature -> computation function
# Each function receives (geo, revenue_segments, characteristics, pe_percentile)
# and returns a float in [0, 1].
_FEATURE_FNS = {
    # --- continuous, derived from real profile data ---
    "high_cloud_datacenter_revenue_pct": lambda geo, rev, ch, pe: _clip01(
        rev.get("datacenter", 0.0) + rev.get("cloud", 0.0)
    ),
    "high_overseas_revenue_pct": lambda geo, rev, ch, pe: _clip01(
        1.0 - geo.get("US", 0.0)
    ),
    "domestic_focused": lambda geo, rev, ch, pe: _clip01(geo.get("US", 0.0)),
    "high_ai_exposure": lambda geo, rev, ch, pe: _clip01(
        0.5 * _flag(ch, "ai_exposed")
        + 0.5 * (rev.get("datacenter", 0.0) + rev.get("ai", 0.0))
    ),
    "high_forward_pe": lambda geo, rev, ch, pe: _clip01(pe) if pe is not None else _flag(ch, "rate_sensitive"),

    # --- TODO(fundamentals): binary placeholders pending real ratio data ---
    "high_debt_ratio":          lambda geo, rev, ch, pe: _flag(ch, "high_debt_ratio"),
    "low_interest_coverage":    lambda geo, rev, ch, pe: _flag(ch, "low_interest_coverage"),
    "high_net_cash":            lambda geo, rev, ch, pe: _flag(ch, "high_net_cash"),
    "strong_fcf":               lambda geo, rev, ch, pe: _flag(ch, "strong_fcf"),
    "high_import_material_pct": lambda geo, rev, ch, pe: _flag(ch, "high_import_material_pct") or _flag(ch, "china_exposed"),
    "low_gross_margin":         lambda geo, rev, ch, pe: _flag(ch, "low_gross_margin"),
    "domestic_supply_chain":    lambda geo, rev, ch, pe: _flag(ch, "domestic_supply_chain"),
    "pricing_power":            lambda geo, rev, ch, pe: _flag(ch, "pricing_power"),
    "high_usd_debt":            lambda geo, rev, ch, pe: _flag(ch, "high_usd_debt"),
}


def compute_exposure(
    company_profile: dict,
    affects_feature: str,
    pe_percentile: Optional[float] = None,
) -> float:
    """
    company_profile: a row (dict-like) from company_profiles, with
        geo_exposure_json / revenue_segments_json / characteristics_json
        as raw JSON strings (or already-parsed dicts).
    affects_feature: one of mechanism_rules.affects_feature.
    pe_percentile: this company's trailing-PE percentile rank (0-1) within
        the tracked universe, or None if unavailable.

    Returns a float in [0, 1]. Unknown affects_feature values return 0.0
    (no exposure assumed) rather than raising, so new mechanism rules can be
    added without immediately breaking scoring.
    """
    geo = _load_json(company_profile.get("geo_exposure_json"))
    rev = _load_json(company_profile.get("revenue_segments_json"))
    ch = _load_json(company_profile.get("characteristics_json"))

    fn = _FEATURE_FNS.get(affects_feature)
    if fn is None:
        return 0.0
    try:
        return _clip01(float(fn(geo, rev, ch, pe_percentile)))
    except Exception:
        return 0.0


def compute_pe_percentiles(profiles_with_pe: list[tuple[str, Optional[float]]]) -> dict[str, float]:
    """
    Given [(ticker, pe_ratio_or_None), ...] for the tracked universe, return
    {ticker: percentile_rank} where percentile is in [0, 1] (1.0 = highest PE
    = most "expensive"/duration-sensitive). Tickers with no PE data are
    omitted (caller should fall back to the binary flag for them).
    """
    valid = [(t, pe) for t, pe in profiles_with_pe if pe is not None and pe > 0]
    if len(valid) < 2:
        return {}

    sorted_pes = sorted(pe for _, pe in valid)
    n = len(sorted_pes)
    result = {}
    for ticker, pe in valid:
        # rank = fraction of universe with PE <= this company's PE
        rank = sum(1 for x in sorted_pes if x <= pe) / n
        result[ticker] = rank
    return result
