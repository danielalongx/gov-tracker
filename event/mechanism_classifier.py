"""
Mechanism classifier — maps a signal (LLM analysis summary + industries) to
zero or more `mechanism_type`s from mechanism_rules.

This is a keyword/rule-based first pass (no extra LLM calls — keeps cost at
zero). It is intentionally conservative: a signal can match multiple
mechanism types, or none at all (most "general"/"hot_topic" company-specific
news won't match any macro mechanism, and that's fine — it just won't
contribute to the event-layer raw score for now).

Future upgrade path (Phase 2+): replace/augment with an LLM classification
call once we have enough event_ledger history to check whether keyword
matches correlate with the mechanism actually being "live".
"""
from __future__ import annotations

import re

# Each mechanism_type maps to a list of (regex pattern, flags) checked against
# the lower-cased summary text. Patterns are deliberately specific to avoid
# false positives (e.g. "interest" alone is too broad).
_PATTERNS: dict[str, list[str]] = {
    "rate_high": [
        r"加息", r"维持高利率", r"利率维持高位", r"鹰派", r"hawkish",
        r"rate hike", r"rates? (?:remain|stay|staying)? ?high",
        r"higher for longer", r"no rate cuts?", r"延迟降息",
        r"加征关税.*利率",  # rare combined phrasing, harmless if unmatched
    ],
    "rate_falling": [
        r"降息", r"鸽派", r"dovish", r"rate cuts?", r"cutting rates?",
        r"lower(?:ing)? interest rates?", r"宽松货币政策", r"货币宽松",
        r"easing cycle",
    ],
    "supply_chain_cost_rise": [
        r"关税", r"加征.*税", r"tariff", r"supply chain (?:disruption|cost|crunch)",
        r"供应链(?:中断|成本|紧张)", r"shipping costs?", r"运费", r"原材料.*涨价",
        r"export controls?", r"出口管制", r"进口限制", r"import restrictions?",
    ],
    "ai_capex_rising": [
        r"ai.{0,6}(?:capex|infrastructure|spending|investment|build[- ]?out)",
        r"data ?center.{0,10}(?:spending|investment|capex|expansion|build)",
        r"数据中心.{0,6}(?:投资|建设|扩建|支出)", r"ai基建", r"算力.{0,6}(?:投资|需求|扩张)",
        r"gpu.{0,6}(?:demand|orders|shortage)", r"chip demand",
        r"芯片需求", r"人工智能.{0,6}(?:投资|资本开支)",
    ],
    "usd_strengthening": [
        r"美元走强", r"美元(?:指数)?上涨", r"dollar (?:strength|strengthen|rally|surge)",
        r"strong(?:er)? dollar", r"dxy", r"美元升值",
    ],
}

_COMPILED: dict[str, list[re.Pattern]] = {
    mech: [re.compile(p, re.IGNORECASE) for p in patterns]
    for mech, patterns in _PATTERNS.items()
}


def classify_mechanisms(summary: str, industries: list | None = None) -> list[str]:
    """
    Return the list of mechanism_types (keys of mechanism_rules.mechanism_type)
    whose keyword patterns match the given signal summary.

    `industries` is currently unused for matching but accepted for future use
    (e.g. industry-specific mechanism variants).
    """
    text = (summary or "").lower()
    if not text:
        return []

    matched: list[str] = []
    for mech_type, patterns in _COMPILED.items():
        if any(p.search(text) for p in patterns):
            matched.append(mech_type)

    return matched
