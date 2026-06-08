"""
Weekly digest generator — sends a structured summary of the past 7 days.

Schedule: add to GitHub Actions as a separate workflow (runs on Monday 08:30 UTC+8).
Or trigger manually: python -m reports.weekly_digest

Covers:
- Top signals by relevance score
- Breakdown by source/region
- Most-mentioned companies
- Guru trade activity
- Sector heat map
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()

from db.init_db import get_connection
from notifier.ntfy import _post_ntfy


def _qmark(conn):
    return "%s" if getattr(conn, "_is_postgres", False) else "?"


def generate_weekly_digest():
    conn = get_connection()
    q = _qmark(conn)
    channel = os.getenv("NTFY_CHANNEL", "US-gov-invest-update")

    # Date range: last 7 days
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()

    cur = conn.cursor()
    cur.execute(f"""
        SELECT p.source, p.source_name, p.article_published_at,
               a.sentiment, a.relevance_score, a.summary,
               a.companies, a.tickers, a.industries,
               a.score_capital_flows, a.score_regulatory
        FROM analysis a
        JOIN posts p ON p.id = a.post_id
        WHERE a.is_relevant = 1
          AND a.relevance_score >= 7
          AND p.fetched_at >= {q}
        ORDER BY a.relevance_score DESC
    """, (since,))

    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("No high-relevance signals this week — skipping digest.")
        return

    # Parse rows
    signals = []
    for r in rows:
        if hasattr(r, 'keys'):
            row = dict(r)
        else:
            keys = ['source', 'source_name', 'article_published_at',
                    'sentiment', 'relevance_score', 'summary', 'companies',
                    'tickers', 'industries', 'score_capital_flows', 'score_regulatory']
            row = dict(zip(keys, r))

        try:
            row['companies_parsed'] = json.loads(row.get('companies') or '[]')
            row['tickers_parsed'] = json.loads(row.get('tickers') or '[]')
        except Exception:
            row['companies_parsed'] = []
            row['tickers_parsed'] = []
        signals.append(row)

    total = len(signals)
    bullish = sum(1 for s in signals if s.get('sentiment') in ('利多', 'bullish'))
    bearish = sum(1 for s in signals if s.get('sentiment') in ('利空', 'bearish'))
    neutral_mixed = total - bullish - bearish

    # Most-mentioned companies
    company_counter: Counter = Counter()
    for s in signals:
        for c in s['companies_parsed']:
            name = c.get('name') or c.get('ticker', '')
            if name:
                company_counter[name] += 1
    top_companies = company_counter.most_common(5)

    # Guru activity
    guru_signals = [s for s in signals if
                    s.get('source', '').startswith('guru_') or
                    'ark' in s.get('source', '').lower()]

    # Source breakdown
    source_counter: Counter = Counter(s.get('source_name') or s.get('source') for s in signals)
    top_sources = source_counter.most_common(3)

    # Top 3 signals
    top_3 = signals[:3]

    # Build the digest message
    lines = [
        f"📊 周报 · {datetime.utcnow().strftime('%m月%d日')}",
        "",
        f"过去7天共 {total} 条高相关信号",
        f"📈 利多 {bullish}  📉 利空 {bearish}  ↕️ 其他 {neutral_mixed}",
        "",
        "── 本周最受关注公司 ──",
    ]
    for name, count in top_companies:
        lines.append(f"  {name}  {count}次提及")

    if guru_signals:
        lines.append("")
        lines.append(f"── 大佬动向 · {len(guru_signals)}条 ──")
        for g in guru_signals[:3]:
            src = g.get('source', '')
            guru_map = {
                'guru_buffett': '巴菲特', 'guru_burry': 'Michael Burry',
                'guru_dalio': 'Ray Dalio', 'guru_ackman': 'Bill Ackman',
                'arkk_trade': 'ARK ARKK', 'arkw_trade': 'ARK ARKW',
            }
            name = guru_map.get(src, src)
            lines.append(f"  {name}: {(g.get('summary') or '')[:60]}...")

    lines.append("")
    lines.append("── 本周最高评分信号 ──")
    for s in top_3:
        score = s.get('relevance_score', 0)
        sentiment = {'利多': '📈', '利空': '📉', '混合': '↕️', '中性': '➡️'}.get(
            s.get('sentiment', ''), '↕️')
        lines.append(f"{sentiment} {score}/10 · {(s.get('summary') or '')[:70]}...")

    lines.append("")
    lines.append("⚠️ 仅供参考，非投资建议。风险自担。")

    body = "\n".join(lines)
    title = f"📊 Signal 周报 · {total}条信号"

    print("Sending weekly digest...")
    print(body)
    _post_ntfy(channel, title, body, click_url=None)
    print("Done.")


if __name__ == "__main__":
    generate_weekly_digest()
