import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

NTFY_BASE = "https://ntfy.sh"

# UTC+8 digest windows: (hour, minute) pairs
UTC8 = timezone(timedelta(hours=8))
_DIGEST_WINDOWS = {(8, 30), (15, 30)}   # 08:30 and 15:30 UTC+8
_DIGEST_PERIOD  = {8: "今日上午", 15: "今日下午"}

_GURU_DISCLAIMER = (
    "\n\n⚠️ 仅供参考，非投资建议\n"
    "以上信息来源于公开监管申报文件（SEC 13F）或 ARK 官方公开披露。\n"
    "投资有风险，决策需谨慎。本平台不提供投资建议，不承担任何投资损失责任。"
)

_GURU_SOURCES = frozenset({
    "arkk_trade", "arkw_trade",
    "guru_buffett", "guru_burry", "guru_ackman",
    "guru_dalio", "guru_druckenmiller", "guru_tepper", "guru_other",
})


def _is_guru(source: str) -> bool:
    return source in _GURU_SOURCES


_SENTIMENT_EMOJI = {
    "利多": "📈", "利空": "📉", "中性": "➡️", "混合": "↕️",
    "bullish": "📈", "bearish": "📉", "neutral": "➡️", "mixed": "↕️",
}
_IMPACT_ARROW = {
    "利多": "⬆️", "利空": "⬇️",
    "bullish": "⬆️", "bearish": "⬇️",
}


def _is_digest_hour() -> tuple[bool, datetime]:
    """Return (is_digest, now_utc8). Matches at 08:30 and 15:30 UTC+8."""
    now = datetime.now(UTC8)
    return (now.hour, now.minute) in _DIGEST_WINDOWS, now


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _format_date(raw: Optional[str]) -> str:
    dt = _parse_dt(raw)
    if not dt:
        return ""
    return dt.strftime("%m月%d日 %H:%M")


def _format_notification(row: sqlite3.Row) -> tuple[str, str, str]:
    """Return (title, body, click_url) for one signal row."""
    sentiment = row["sentiment"] or "中性"
    signal_emoji = _SENTIMENT_EMOJI.get(sentiment, "📊")
    score = int(row["relevance_score"] or 0)

    source_name = (
        row["analysis_source_name"]
        or row["post_source_name"]
        or str(row["source"]).replace("_", " ").title()
    )
    date_str = _format_date(row["article_published_at"])
    header = f"📰 {source_name} · {date_str}" if date_str else f"📰 {source_name}"

    companies: list[dict] = json.loads(row["companies"] or "[]")
    company_lines: list[str] = []
    for c in companies[:7]:
        name = c.get("name", "")
        ticker = c.get("ticker")
        arrow = _IMPACT_ARROW.get(c.get("impact", ""), "")
        label = f"{name}（{ticker}）" if ticker else name
        company_lines.append(f"{label} {arrow}".strip())

    parts: list[str] = [header, "", row["summary"] or ""]
    if company_lines:
        parts += ["", "影响公司："] + company_lines
    parts += ["", f"相关度：{score}/10 · {sentiment}"]

    url = row["article_url"] or ""
    if url:
        parts += ["", f"🔗 {url}"]

    source = row["source"] or ""
    if _is_guru(source):
        parts.append(_GURU_DISCLAIMER)
        title = f"[参考] {signal_emoji} {sentiment} {score}/10"
    else:
        title = f"{signal_emoji} {sentiment} {score}/10"

    return title, "\n".join(parts), url


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


def _send_digest_summary(channel: str, period_label: str, time_str: str, rows: list) -> None:
    """Push a single summary card listing signal counts by sentiment."""
    counts: dict[str, int] = {}
    for row in rows:
        s = row["sentiment"] or "中性"
        counts[s] = counts.get(s, 0) + 1

    parts = []
    for sentiment, emoji in [("利多", "📈"), ("利空", "📉"), ("混合", "↕️"), ("中性", "➡️")]:
        if counts.get(sentiment):
            parts.append(f"{counts[sentiment]}{sentiment}")

    body = f"今日{period_label}共 {len(rows)} 条信号 · {'、'.join(parts)}"
    _post_ntfy(channel, f"📊 Signal Digest · {time_str}", body)


def send_pending_notifications(
    conn: sqlite3.Connection,
    ntfy_channel: str,
    relevance_threshold: float = 6.0,
) -> int:
    """Core notification dispatcher.

    - Non-digest hours: flag qualifying signals as hold_for_digest=1, send nothing.
    - Digest hours (08/12/20 UTC+8): send ALL pending signals ordered by score,
      preceded by a summary card if there are 3 or more.
    """
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
        ORDER  BY a.relevance_score DESC
        """,
        (relevance_threshold,),
    ).fetchall()

    if not pending:
        logger.info("Notifications: 0 pending signals")
        return 0

    is_digest, now_utc8 = _is_digest_hour()

    # ── Non-digest hour: hold signals ────────────────────────────────────────
    if not is_digest:
        ids = [row["analysis_id"] for row in pending]
        conn.execute(
            f"UPDATE analysis SET hold_for_digest = 1 WHERE id IN ({','.join('?' * len(ids))})",
            ids,
        )
        conn.commit()
        next_windows = sorted(
            f"{h:02d}:{m:02d}" for h, m in _DIGEST_WINDOWS
            if h > now_utc8.hour or (h == now_utc8.hour and m > now_utc8.minute)
        )
        logger.info(
            "Notifications: held %d signal(s) (UTC+8 %02d:%02d — next digest at %s)",
            len(pending),
            now_utc8.hour, now_utc8.minute,
            ", ".join(next_windows) or "08:30 tomorrow",
        )
        return 0

    # ── Digest hour: send everything pending ─────────────────────────────────
    period_label = _DIGEST_PERIOD.get(now_utc8.hour, "")
    time_str = now_utc8.strftime("%H:%M")

    if len(pending) >= 3:
        _send_digest_summary(ntfy_channel, period_label, time_str, pending)

    notified_at = datetime.now(timezone.utc).isoformat()
    sent = 0
    for row in pending:
        title, body, url = _format_notification(row)
        if _post_ntfy(ntfy_channel, title, body, url):
            conn.execute(
                "UPDATE analysis SET notified = 1, notified_at = ? WHERE id = ?",
                (notified_at, row["analysis_id"]),
            )
            conn.commit()
            sent += 1
            logger.info("Digest sent: %s", title)
        else:
            logger.warning(
                "Failed to push analysis_id=%d — will retry next digest",
                row["analysis_id"],
            )

    logger.info(
        "Digest complete: %d/%d signals sent at UTC+8 %s%s",
        sent, len(pending), period_label, time_str,
    )
    return sent
