"""
Guru trades collector — public filings and ARK daily ETF disclosures.

Sources
-------
ARK Invest daily CSV (official public disclosure):
  ARKK — ARK Innovation ETF
  ARKW — ARK Next Generation Internet ETF

Dataroma RSS (aggregates SEC 13F quarterly filings):
  Berkshire Hathaway / Warren Buffett
  Scion Asset Management / Michael Burry
  Pershing Square / Bill Ackman
  Bridgewater / Ray Dalio
  Duquesne / Stanley Druckenmiller
  Appaloosa / David Tepper

DISCLAIMER: SEC 13F filings are disclosed up to 45 days after quarter-end.
ARK holdings are published daily but reflect end-of-day positions.
All data is from official public regulatory filings or company disclosures.
This module does not constitute investment advice.
"""

import csv
import hashlib
import io
import logging
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── ARK ETF ───────────────────────────────────────────────────────────────────

_ARK_FUNDS: dict[str, str] = {
    "ARKK": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
    "ARKW": "https://ark-funds.com/wp-content/uploads/funds-etf-csv/ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
}
_ARK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/csv,text/plain,*/*",
}

# ── Dataroma ──────────────────────────────────────────────────────────────────

_DATAROMA_RSS = "https://www.dataroma.com/m/feeds/activity.php"

# Pattern → (source_tag, display_name)
_GURU_MAP: dict[str, tuple[str, str]] = {
    "Berkshire":      ("guru_buffett",        "巴菲特（Berkshire Hathaway）"),
    "Buffett":        ("guru_buffett",        "巴菲特（Berkshire Hathaway）"),
    "Burry":          ("guru_burry",          "迈克尔·伯里（Scion）"),
    "Scion":          ("guru_burry",          "迈克尔·伯里（Scion）"),
    "Ackman":         ("guru_ackman",         "比尔·阿克曼（Pershing Square）"),
    "Pershing":       ("guru_ackman",         "比尔·阿克曼（Pershing Square）"),
    "Dalio":          ("guru_dalio",          "瑞·达利欧（Bridgewater）"),
    "Bridgewater":    ("guru_dalio",          "瑞·达利欧（Bridgewater）"),
    "Druckenmiller":  ("guru_druckenmiller",  "斯坦利·德鲁肯米勒（Duquesne）"),
    "Duquesne":       ("guru_druckenmiller",  "斯坦利·德鲁肯米勒（Duquesne）"),
    "Tepper":         ("guru_tepper",         "戴维·泰珀（Appaloosa）"),
    "Appaloosa":      ("guru_tepper",         "戴维·泰珀（Appaloosa）"),
}


# ── Snapshot table (managed entirely within this module) ─────────────────────

def _ensure_snapshot_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ark_holdings_snapshot (
            fund          TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            company       TEXT,
            shares        REAL NOT NULL,
            snapshot_date TEXT NOT NULL,
            PRIMARY KEY (fund, ticker)
        )
    """)
    conn.commit()


# ── ARK CSV helpers ───────────────────────────────────────────────────────────

def _fetch_ark_csv(url: str) -> dict[str, dict]:
    """Download ARK holdings CSV → {ticker: {company, shares}}. {} on failure."""
    try:
        resp = requests.get(url, headers=_ARK_HEADERS, timeout=25)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("ARK CSV fetch error: %s", e)
        return {}

    holdings: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        norm = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        ticker = norm.get("ticker", "").strip()
        company = norm.get("company", "")
        if not ticker or ticker in ("-", ""):
            continue
        try:
            shares = float(norm.get("shares", "0").replace(",", ""))
        except ValueError:
            continue
        if shares > 0:
            holdings[ticker] = {"company": company, "shares": shares}
    return holdings


def _load_snapshot(conn: sqlite3.Connection, fund: str) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT ticker, company, shares FROM ark_holdings_snapshot WHERE fund = ?",
        (fund,),
    ).fetchall()
    return {r["ticker"]: {"company": r["company"], "shares": r["shares"]} for r in rows}


def _save_snapshot(conn: sqlite3.Connection, fund: str, holdings: dict) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute("DELETE FROM ark_holdings_snapshot WHERE fund = ?", (fund,))
    for ticker, data in holdings.items():
        conn.execute(
            "INSERT INTO ark_holdings_snapshot (fund, ticker, company, shares, snapshot_date)"
            " VALUES (?,?,?,?,?)",
            (fund, ticker, data["company"], data["shares"], today),
        )
    conn.commit()


def _compute_diff(prev: dict, curr: dict) -> list[dict]:
    """Return list of position changes; ignores moves < 0.5% of position size."""
    changes: list[dict] = []
    for ticker in sorted(set(prev) | set(curr)):
        p = prev.get(ticker)
        c = curr.get(ticker)
        if not p and c:
            changes.append({"type": "新建仓", "ticker": ticker,
                            "company": c["company"], "shares": c["shares"]})
        elif p and not c:
            changes.append({"type": "清仓",   "ticker": ticker,
                            "company": p["company"], "shares": 0})
        elif p and c:
            delta = c["shares"] - p["shares"]
            if abs(delta) / max(p["shares"], 1) < 0.005:
                continue  # < 0.5% rounding noise
            pct = delta / p["shares"] * 100
            changes.append({"type": "增持" if delta > 0 else "减持",
                            "ticker": ticker, "company": c["company"],
                            "pct": pct, "shares": c["shares"]})
    return changes


def _fmt_change(ch: dict) -> str:
    t, ticker, company = ch["type"], ch["ticker"], ch["company"]
    if t == "新建仓":
        return f"新建仓: {company}({ticker}) {ch['shares']:,.0f}股"
    if t == "清仓":
        return f"清仓: {company}({ticker})"
    return f"{t}: {company}({ticker}) {ch['pct']:+.1f}%"


def fetch_ark_fund(conn: sqlite3.Connection, fund: str) -> list[int]:
    """Diff today's ARK holdings against yesterday's snapshot; insert change post."""
    _ensure_snapshot_table(conn)
    url = _ARK_FUNDS.get(fund)
    if not url:
        return []

    curr = _fetch_ark_csv(url)
    if not curr:
        return []

    prev = _load_snapshot(conn, fund)
    if not prev:
        _save_snapshot(conn, fund, curr)
        logger.info("ARK %s: stored initial snapshot (%d holdings)", fund, len(curr))
        return []

    changes = _compute_diff(prev, curr)
    _save_snapshot(conn, fund, curr)

    if not changes:
        logger.info("ARK %s: no position changes detected", fund)
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    post_id = f"{fund}_{today}"
    summary = "; ".join(_fmt_change(c) for c in changes[:10])
    content = f"[{fund}持仓变动] {summary} [ARK Invest]"
    source_tag = f"{fund.lower()}_trade"

    try:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO posts
                (source, post_id, content, author, source_name,
                 article_url, article_published_at, posted_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                source_tag, post_id, content, "ARK Invest", "ARK Invest",
                f"https://ark-funds.com/funds/{fund.lower()}/",
                today, datetime.now(timezone.utc),
            ),
        )
        conn.commit()
    except Exception as e:
        logger.error("DB insert error for ARK %s: %s", fund, e)
        return []

    new_ids = [cur.lastrowid] if cur.rowcount > 0 else []
    logger.info("ARK %s: %d change(s) → %d new post(s)", fund, len(changes), len(new_ids))
    return new_ids


# ── Dataroma RSS ──────────────────────────────────────────────────────────────

def _identify_guru(text: str) -> tuple[str, str]:
    """Return (source_tag, display_name) by matching known guru patterns."""
    for pattern, (tag, display) in _GURU_MAP.items():
        if pattern.lower() in text.lower():
            return tag, display
    return "guru_other", "机构投资者"


def fetch_dataroma_trades(conn: sqlite3.Connection) -> list[int]:
    """Fetch Dataroma guru activity RSS; insert recent 13F changes as posts."""
    try:
        resp = requests.get(
            _DATAROMA_RSS,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=25,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as e:
        logger.warning("Dataroma RSS error: %s", e)
        return []

    new_ids: list[int] = []
    for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        link  = item.findtext("link") or ""
        desc  = item.findtext("description") or ""
        if not title or not link:
            continue

        posted_at: Optional[datetime] = None
        pub = item.findtext("pubDate")
        if pub:
            try:
                posted_at = parsedate_to_datetime(pub)
            except Exception:
                pass

        source_tag, guru_name = _identify_guru(title + " " + desc)
        uid = hashlib.md5(link.encode()).hexdigest()[:16]
        content = (
            f"[Guru持仓] {guru_name}: {title}. {desc[:300].strip()} "
            f"[Dataroma/SEC 13F]"
        )

        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO posts
                    (source, post_id, content, author, source_name,
                     article_url, article_published_at, posted_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    source_tag, uid, content, guru_name, "Dataroma",
                    link,
                    posted_at.isoformat() if posted_at else None,
                    posted_at,
                ),
            )
            conn.commit()
            if cur.rowcount > 0:
                new_ids.append(cur.lastrowid)
        except Exception as e:
            logger.error("DB insert error for Dataroma %s: %s", uid, e)

    logger.info("Dataroma: %d new guru trade(s)", len(new_ids))
    return new_ids


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_guru_trades(conn: sqlite3.Connection) -> list[int]:
    """Run all guru/ARK collectors. Returns combined new DB row IDs."""
    ids: list[int] = []
    for fund in _ARK_FUNDS:
        ids.extend(fetch_ark_fund(conn, fund))
    ids.extend(fetch_dataroma_trades(conn))
    return ids
