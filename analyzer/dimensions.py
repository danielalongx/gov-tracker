"""
Dimension scoring — no LLM calls, derived from existing analysis fields.

Dimensions (0-10 each):
  news           — overall relevance/newsworthiness
  financial      — earnings/revenue/guidance signals
  pipeline       — product/R&D/launch/patent signals
  regulatory     — regulatory/government signals
  capital_flows  — institutional money-flow signals (gurus, ARK)
  technical      — always 0 (news cannot produce technical signals)
"""

_FINANCIAL_KEYWORDS = frozenset({
    "earnings", "revenue", "guidance", "eps", "profit", "loss",
    "margin", "beat", "miss", "forecast", "outlook", "quarter",
    "fiscal", "年报", "季报", "营收", "净利润", "盈利", "业绩",
    "每股收益", "指引",
})

_PIPELINE_KEYWORDS = frozenset({
    "product", "launch", "r&d", "pipeline", "patent", "fda",
    "approval", "drug", "clinical", "trial", "chip", "roadmap",
    "release", "shipping", "debut", "breakthrough", "research",
    "新产品", "发布", "研发", "专利", "批准", "上市", "临床",
})

_GURU_SOURCES = frozenset({
    "guru_buffett", "guru_burry", "guru_ackman",
    "guru_dalio", "guru_druckenmiller", "guru_tepper", "guru_other",
})

_REGULATORY_SOURCES = frozenset({
    "federal_register", "trump_news",
})


def score_dimensions(post: dict, analysis: dict) -> dict:
    """
    Compute dimension scores for a post+analysis pair.
    Returns dict with keys: news, financial, pipeline, regulatory, capital_flows, technical.
    """
    source: str = (post.get("source") or "").lower()
    summary: str = (analysis.get("summary") or "").lower()

    # capital_flows: guru sources or ARK funds
    if source in _GURU_SOURCES or source.startswith("guru_") or "ark" in source:
        capital_flows = 9
    else:
        capital_flows = 0

    # regulatory: federal register or trump news
    if source in _REGULATORY_SOURCES:
        regulatory = 8
    else:
        regulatory = 0

    # financial: summary mentions earnings-related keywords
    if any(kw in summary for kw in _FINANCIAL_KEYWORDS):
        financial = 7
    else:
        financial = 0

    # pipeline: summary mentions product/R&D-related keywords
    if any(kw in summary for kw in _PIPELINE_KEYWORDS):
        pipeline = 7
    else:
        pipeline = 0

    # news: use relevance_score from LLM analysis (already 0-10)
    news = int(analysis.get("relevance_score") or 0)

    return {
        "news": news,
        "financial": financial,
        "pipeline": pipeline,
        "regulatory": regulatory,
        "capital_flows": capital_flows,
        "technical": 0,
    }
