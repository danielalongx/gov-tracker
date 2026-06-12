"""
Industry "Heat" index — continuous, time-varying, sector-level measure of how
much buzz a sector (AI, semiconductors, storage, etc.) is getting in the
collected news flow. Per Wayne's request: "现在的AI，半导体，存储等领域也是要加一个
hype的指标".

Reduced-scope implementation (Phase 1) — derived purely from
`analysis.industries` (LLM-extracted industry tags) + `analysis.analyzed_at`,
which we already collect on every run, no new data sources needed:

    heat(sector) = (mentions in last WINDOW_DAYS - mentions in the
                    WINDOW_DAYS before that) / max(prior_mentions, 1)

A positive value means mention frequency is accelerating (sector "heating
up"); negative means cooling. This is a raw, unbounded ratio — bounding
(tanh) and combination with Credibility/Crowd terms (M_pos/M_neg from the
v2.0 spec) belongs to the composite layer (composite/), not here.

TODO(Phase 2+): add sector ETF price momentum and search-trend momentum as
additional inputs once those data sources exist.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

WINDOW_DAYS = 14

# Heat "sectors" we track, each with keyword patterns matched (case-insensitive,
# substring) against the LLM-extracted `industries` list. A sector here is a
# narrative theme, not necessarily a GICS sector.
_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "ai": ["ai", "人工智能", "大模型", "生成式", "machine learning", "llm"],
    "semiconductor": ["半导体", "芯片", "semiconductor", "chip", "foundry", "晶圆"],
    "storage": ["存储", "memory", "storage", "hbm", "dram", "nand"],
    "cloud_datacenter": ["云计算", "数据中心", "cloud", "data center", "datacenter"],
    "ev": ["电动车", "新能源车", "ev", "electric vehicle", "新能源汽车"],
    "energy": ["能源", "石油", "oil", "natural gas", "天然气", "新能源"],
    "banking": ["银行", "bank", "银行业"],
}

# company_profiles.sector (free-text, e.g. "Technology/Semiconductors") ->
# which heat sector(s) apply. Matched by substring on the lower-cased sector
# string, plus characteristics_json flags as a fallback (handled by caller).
_PROFILE_SECTOR_MAP: dict[str, list[str]] = {
    "semiconductor": ["semiconductor", "ai", "cloud_datacenter"],
    "consumer electronics": ["ai"],
    "software": ["ai", "cloud_datacenter"],
    "internet": ["ai", "cloud_datacenter"],
    "e-commerce": ["cloud_datacenter"],
    "social media": ["ai"],
    "automotive": ["ev"],
    "banking": ["banking"],
}


def _load_json(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def compute_sector_heat(conn, now: datetime | None = None) -> dict[str, float]:
    """
    Returns {heat_sector_key: heat_value} for each key in _SECTOR_KEYWORDS.
    """
    now = now or datetime.now(timezone.utc)
    recent_start = now - timedelta(days=WINDOW_DAYS)
    prior_start = now - timedelta(days=2 * WINDOW_DAYS)

    cur = conn.execute(
        "SELECT industries, analyzed_at FROM analysis WHERE analyzed_at >= ?",
        (prior_start.isoformat(),),
    )

    recent_counts = {k: 0 for k in _SECTOR_KEYWORDS}
    prior_counts = {k: 0 for k in _SECTOR_KEYWORDS}

    for row in cur.fetchall():
        industries = _load_json(row["industries"])
        if not industries:
            continue
        analyzed_at_raw = row["analyzed_at"]
        try:
            analyzed_at = datetime.fromisoformat(str(analyzed_at_raw).replace("Z", "+00:00"))
            if analyzed_at.tzinfo is None:
                analyzed_at = analyzed_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue

        is_recent = analyzed_at >= recent_start
        bucket = recent_counts if is_recent else prior_counts

        text = " ".join(str(i).lower() for i in industries)
        for sector_key, keywords in _SECTOR_KEYWORDS.items():
            if any(kw.lower() in text for kw in keywords):
                bucket[sector_key] += 1

    heat: dict[str, float] = {}
    for sector_key in _SECTOR_KEYWORDS:
        recent = recent_counts[sector_key]
        prior = prior_counts[sector_key]
        heat[sector_key] = (recent - prior) / max(prior, 1)

    return heat


def company_heat(company_profile: dict, sector_heat: dict[str, float]) -> float:
    """
    Map a company_profiles row to a single heat value by averaging the heat
    of every heat-sector its profile sector / characteristics flags belong to.
    Returns 0.0 if no mapping found (most non-tech/non-energy companies).
    """
    sector = (company_profile.get("sector") or "").lower()
    matched_keys: set[str] = set()

    for profile_key, heat_keys in _PROFILE_SECTOR_MAP.items():
        if profile_key in sector:
            matched_keys.update(heat_keys)

    ch_raw = company_profile.get("characteristics_json")
    ch = {}
    if ch_raw:
        try:
            ch = ch_raw if isinstance(ch_raw, dict) else json.loads(ch_raw)
        except (TypeError, ValueError):
            ch = {}
    if ch.get("ai_exposed"):
        matched_keys.add("ai")
    if ch.get("semiconductor"):
        matched_keys.add("semiconductor")
    if ch.get("ev"):
        matched_keys.add("ev")

    if not matched_keys:
        return 0.0

    return sum(sector_heat.get(k, 0.0) for k in matched_keys) / len(matched_keys)
