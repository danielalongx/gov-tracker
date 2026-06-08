"""Classify a signal into one of the app's display categories."""

_MACRO_KEYWORDS = [
    'fed', 'federal reserve', '美联储', 'interest rate', '利率', 'inflation', '通胀',
    'cpi', 'gdp', 'unemployment', '就业', 'jobs report', 'payroll', 'fomc',
    '降息', '加息', '降准', 'monetary policy', '货币政策', 'rate cut', 'rate hike',
    'yield curve', 'treasury', '国债', 'recession', '衰退', 'ecb', '欧央行',
    'bank of england', 'pboc', '人民银行', 'boj', '日银',
]

_GURU_SOURCES = frozenset({
    'guru_buffett', 'guru_burry', 'guru_ackman', 'guru_dalio',
    'guru_druckenmiller', 'guru_tepper', 'guru_other',
    'arkk_trade', 'arkw_trade',
})

_INSTITUTIONAL_SOURCES = frozenset({
    'arkk_trade', 'arkw_trade',
})


def classify_signal(source: str, summary: str, industries: list, relevance_score: float) -> str:
    """
    Return one of: 'guru' | 'institutional' | 'macro' | 'sector' | 'hot_topic' | 'general'
    Priority: guru > institutional > macro > sector > hot_topic > general
    """
    source_lower = source.lower()
    summary_lower = (summary or '').lower()

    if source_lower.startswith('guru_'):
        return 'guru'

    if source_lower.startswith('ark') or source_lower in _INSTITUTIONAL_SOURCES:
        return 'institutional'

    if any(kw in summary_lower for kw in _MACRO_KEYWORDS):
        return 'macro'

    if industries and len(industries) > 0:
        return 'sector'

    if relevance_score >= 8:
        return 'hot_topic'

    return 'general'
