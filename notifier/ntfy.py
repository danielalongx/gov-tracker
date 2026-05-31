import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

NTFY_BASE = "https://ntfy.sh"

_SENTIMENT_EMOJI = {
    "利多": "📈",
    "利空": "📉",
    "中性": "➡️",
    "混合": "↕️",
    # English fallback for legacy rows
    "bullish": "📈",
    "bearish": "📉",
    "neutral": "➡️",
    "mixed":   "↕️",
}

_IMPACT_ARROW = {
    "利多": "⬆️",
    "利空": "⬇️",
    # English fallback for legacy rows
    "bullish": "⬆️",
    "bearish": "⬇️",
}


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _format_date(raw: Optional[str]) -> str:
    """Return '05月29日 15:21' style string, empty string if unparseable."""
    dt = _parse_dt(raw)
    if not dt:
        return ""
    return dt.strftime("%m月%d日 %H:%M")


def _format_notification(row: sqlite3.Row) -> tuple[str, str]:
    """Return (ntfy_title, ntfy_body) for an analysis row."""
    sentiment = row["sentiment"] or "中性"
    signal_emoji = _SENTIMENT_EMOJI.get(sentiment, "📊")
    score = int(row["relevance_score"] or 0)

    # Header: outlet + date
    source_name = (
        row["analysis_source_name"]
        or row["post_source_name"]
        or str(row["source"]).replace("_", " ").title()
    )
    date_str = _format_date(row["article_published_at"])
    header = f"📰 {source_name} · {date_str}" if date_str else f"📰 {source_name}"

    # Companies block
    companies: list[dict] = json.loads(row["companies"] or "[]")
    company_lines: list[str] = []
    for c in companies[:7]:
        name = c.get("name", "")
        ticker = c.get("ticker")
        arrow = _IMPACT_ARROW.get(c.get("impact", ""), "")
        label = f"{name}（{ticker}）" if ticker else name
        company_lines.append(f"{label} {arrow}".strip())

    # Assemble body
    parts: list[str] = [header, "", row["summary"] or ""]
    if company_lines:
        parts += ["", "影响公司："] + company_lines
    parts += ["", f"相关度：{score}/10 · {sentiment}"]
    url = row["article_url"] or ""
    if url:
        parts += ["", f"🔗 {url}"]

    title = f"{signal_emoji} {sentiment} {score}/10"
    body = "\n".join(parts)
    return title, body, url


def _post_ntfy(channel: str, title: str, body: str, click_url: str = "") -> bool:
    payload: dict = {
        "topic": channel,
        "title": title[:250],
        "message": body,
        "priority": 3,
        "tags": ["chart_with_upwards_trend", "us", "government"],
    }
    if click_url:
        payload["click"] = click_url
    try:
        resp = requests.post(f"{NTFY_BASE}/", json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error("ntfy POST failed: %s", e)
        return False


def send_pending_notifications(
    conn: sqlite3.Connection,
    ntfy_channel: str,
    relevance_threshold: float = 6.0,
) -> int:
    """Send ntfy pushes for all pending relevant analyses. Returns count sent."""
    pending = conn.execute(
        """
        SELECT a.id              AS analysis_id,
               a.sentiment,
               a.tickers,
               a.companies,
               a.industries,
               a.relevance_score,
               a.summary,
               a.source_name     AS analysis_source_name,
               p.source,
               p.source_name     AS post_source_name,
               p.article_url,
               p.article_published_at,
               p.author,
               p.posted_at
        FROM   analysis a
        JOIN   posts p ON p.id = a.post_id
        WHERE  a.is_relevant = 1
          AND  a.relevance_score >= ?
          AND  a.notified = 0
        ORDER  BY a.analyzed_at ASC
        """,
        (relevance_threshold,),
    ).fetchall()

    sent = 0
    for row in pending:
        title, body, url = _format_notification(row)
        if _post_ntfy(ntfy_channel, title, body, url):
            conn.execute(
                "UPDATE analysis SET notified = 1 WHERE id = ?",
                (row["analysis_id"],),
            )
            conn.commit()
            sent += 1
            logger.info("Notified: %s", title)
        else:
            logger.warning(
                "Failed to notify analysis_id=%d — will retry next run",
                row["analysis_id"],
            )

    logger.info("Notifications: %d/%d sent", sent, len(pending))
    return sent
