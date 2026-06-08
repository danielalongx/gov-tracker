"""
Shared keyword pre-filter for all collectors.

Purpose: cheaply reject articles that are clearly not investment-relevant
before spending LLM tokens on them.

Two-stage approach:
1. HARD REJECT: articles matching these patterns go straight to trash
2. SOFT REQUIRE: articles must contain at least one positive signal keyword
   to be sent to the LLM (configurable — some sources bypass this check)

Usage:
    from collector.keyword_filter import should_process
    if not should_process(title, content, source):
        continue  # skip this article
"""

import re
from typing import Optional

# ── Hard reject patterns ──────────────────────────────────────────────────────
# These patterns indicate content with zero investment relevance.
# Tested against: title + first 200 chars of content.

_HARD_REJECT_PATTERNS = [
    # Pure sports
    r'\b(super bowl|nfl|nba|mlb|nhl|fifa|premier league|champions league|f1 race|grand prix)\b',
    # Celebrity / entertainment
    r'\b(kardashian|beyoncé|taylor swift|justin bieber|oscar ceremony|grammys|emmys|golden globe)\b',
    # Weather/natural disaster (unless causing market disruption — caught by soft require)
    r'^(hurricane|tornado|earthquake|flood|wildfire) (hit|strikes|batters|devastates)',
    # Purely political personal attacks with no policy content
    r'\b(melania|ivanka|trump jr|jared kushner) (wore|wore|attended|posted|said|shared)\b',
    # Social media drama
    r'\b(twitter beef|instagram post|tiktok viral|youtube video went viral)\b',
    # Crime/courts unrelated to financial fraud
    r'\b(murder|shooting|stabbing|robbery|kidnapping|missing person)\b',
    # Religious/cultural with no economic dimension
    r'\b(baptism|wedding ceremony|funeral|religious holiday|church service)\b',
]

_HARD_REJECT_RE = [re.compile(p, re.IGNORECASE) for p in _HARD_REJECT_PATTERNS]

# ── Soft require: at least one of these terms must appear ─────────────────────
# Sources that bypass this check: guru_*, ark*, federal_register (always relevant)

_INVEST_KEYWORDS = [
    # Markets / prices
    'stock', 'market', 'shares', 'equity', 'bond', 'yield', 'rate', 'inflation',
    'gdp', 'recession', 'rally', 'selloff', 'correction', 'bull', 'bear',
    # Corporate
    'earnings', 'revenue', 'profit', 'loss', 'guidance', 'merger', 'acquisition',
    'ipo', 'spinoff', 'buyback', 'dividend', 'eps', 'margin',
    'ceo', 'cfo', 'executive', 'board', 'investor', 'analyst',
    # Policy
    'tariff', 'trade', 'sanction', 'tax', 'regulation', 'deregulation',
    'federal reserve', 'fed ', ' fed ', 'interest rate', 'monetary',
    'fiscal', 'stimulus', 'budget', 'deficit', 'debt ceiling',
    # Sectors
    'semiconductor', 'chip', 'ai ', ' ai ', 'artificial intelligence',
    'energy', 'oil', 'gas', 'pharma', 'biotech', 'bank', 'finance',
    'tech', 'software', 'cloud', 'defense', 'aerospace',
    'real estate', 'retail', 'consumer', 'automotive', 'electric vehicle',
    # Companies (most common tickers/names)
    'nvidia', 'apple', 'microsoft', 'amazon', 'google', 'alphabet', 'meta',
    'tesla', 'tsmc', 'asml', 'samsung', 'intel', 'amd',
    'jpmorgan', 'goldman', 'exxon', 'chevron',
    '英伟达', '苹果', '微软', '亚马逊', '特斯拉', '腾讯', '阿里',
    # Chinese financial terms
    'a股', '港股', '美股', '上证', '纳斯达克', '道琼斯', '标普',
    '人民币', '美元', '利率', '通胀', '经济', '贸易', '关税',
    '股市', '基金', '债券', '期货', '原油', '黄金',
]

_INVEST_KEYWORD_RE = re.compile(
    '|'.join(re.escape(k) for k in _INVEST_KEYWORDS),
    re.IGNORECASE
)

# Sources that are always investment-relevant (skip soft require check)
_ALWAYS_RELEVANT_SOURCES = {
    'federal_register', 'truth_social',  # policy sources
}
_ALWAYS_RELEVANT_PREFIXES = ('guru_', 'ark')


def _always_relevant(source: str) -> bool:
    if source in _ALWAYS_RELEVANT_SOURCES:
        return True
    return any(source.startswith(p) for p in _ALWAYS_RELEVANT_PREFIXES)


def should_process(
    title: str,
    content: Optional[str],
    source: str = '',
    strict: bool = False,
) -> bool:
    """
    Return True if this article should be sent to the LLM for analysis.

    Args:
        title: Article headline
        content: Article body (may be None)
        source: Source identifier (e.g. 'reuters_news', 'guru_buffett')
        strict: If True, require investment keyword even for normally-bypassed sources
    """
    text = (title + ' ' + (content or '')[:300]).lower()

    # 1. Hard reject
    for pattern in _HARD_REJECT_RE:
        if pattern.search(text):
            return False

    # 2. Bypass soft-require for high-signal sources
    if not strict and _always_relevant(source):
        return True

    # 3. Soft require
    return bool(_INVEST_KEYWORD_RE.search(text))


def filter_batch(
    articles: list[dict],
    source: str = '',
    title_key: str = 'content',
    content_key: Optional[str] = None,
) -> tuple[list[dict], int]:
    """
    Filter a batch of article dicts.
    Returns (kept_articles, skipped_count).
    """
    kept = []
    skipped = 0
    for article in articles:
        title = article.get(title_key, '') or ''
        body = article.get(content_key, '') if content_key else None
        if should_process(title, body, source):
            kept.append(article)
        else:
            skipped += 1
    return kept, skipped
