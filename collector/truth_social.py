"""
Truth Social collector — two-tier design:

Tier 1 (preferred): Mastodon-compatible API at truthsocial.com
  Requires TRUTH_SOCIAL_BEARER_TOKEN env var.
  How to get a token (30 sec):
    1. Log into truthsocial.com in Chrome
    2. Open DevTools → Network → filter for "/api/"
    3. Click any request, copy "Authorization: Bearer <token>" header value
    4. Add TRUTH_SOCIAL_BEARER_TOKEN=<token> to .env
  Trump's account ID (107780257626128497) is hardcoded so we never need a
  lookup call. Change TRUMP_ACCOUNT_ID if it ever differs.

Tier 2 (fallback, no credentials): Google News RSS
  Captures Trump's economic and policy statements as reported by major outlets.
  Source stored as "trump_news" (distinct from "truth_social") in the DB.
"""

import hashlib
import logging
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TRUTH_SOCIAL_BASE = "https://truthsocial.com"
TRUMP_ACCOUNT_ID = "107780257626128497"  # @realDonaldTrump — stable since account creation
SOURCE_DIRECT = "truth_social"
SOURCE_NEWS = "trump_news"

_GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"
_NEWS_QUERIES = [
    '"Trump" tariff OR trade OR sanction OR deal',
    '"Trump" market OR economy OR tax OR rate',
    '"Trump" energy OR pharma OR tech OR defense OR infrastructure',
]


# ── HTML stripping ────────────────────────────────────────────────────────────

class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def _strip_html(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html)
    return s.get_text()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


_MAX_AGE = timedelta(hours=1)


def _is_recent(posted_at: Optional[datetime]) -> bool:
    """Return True only if posted_at is within the last 6 hours. None → False."""
    if posted_at is None:
        return False
    now = datetime.now(timezone.utc)
    # Normalise naive datetimes to UTC before comparing
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    return (now - posted_at) <= _MAX_AGE


# ── Tier 1: Mastodon API ──────────────────────────────────────────────────────

def _fetch_via_mastodon_api(bearer_token: str) -> list[dict]:
    try:
        resp = requests.get(
            f"{TRUTH_SOCIAL_BASE}/api/v1/accounts/{TRUMP_ACCOUNT_ID}/statuses",
            headers={
                "Authorization": f"Bearer {bearer_token}",
                "User-Agent": "gov-tracker/1.0",
                "Accept": "application/json",
            },
            params={"limit": 40, "exclude_reblogs": "false"},
            timeout=30,
        )
        resp.raise_for_status()
        statuses = resp.json()
    except requests.RequestException as e:
        logger.error("Truth Social Mastodon API error: %s", e)
        return []

    posts: list[dict] = []
    for s in statuses:
        raw_html = (
            s.get("content")
            or (s.get("reblog") or {}).get("content")
            or ""
        )
        content = _strip_html(raw_html)
        if not content:
            continue

        posted_at: Optional[datetime] = None
        ts = s.get("created_at")
        if ts:
            try:
                posted_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                pass

        posts.append({
            "source": SOURCE_DIRECT,
            "post_id": str(s["id"]),
            "content": content,
            "author": "realDonaldTrump",
            "source_name": "Truth Social",
            "article_url": s.get("url") or f"https://truthsocial.com/@realDonaldTrump/{s['id']}",
            "article_published_at": _iso(posted_at),
            "posted_at": posted_at,
        })

    logger.info("Truth Social Mastodon API: %d posts fetched", len(posts))
    return posts


# ── Tier 2: Google News RSS fallback ─────────────────────────────────────────

def _fetch_via_news_rss() -> list[dict]:
    seen: set[str] = set()
    posts: list[dict] = []

    for query in _NEWS_QUERIES:
        try:
            resp = requests.get(
                _GOOGLE_NEWS_BASE,
                params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
        except Exception as e:
            logger.warning("Google News RSS error (q=%r): %s", query, e)
            continue

        for item in root.findall(".//item"):
            link = item.findtext("link") or ""
            title = item.findtext("title") or ""
            if not link or not title:
                continue

            uid = hashlib.md5(link.encode()).hexdigest()[:16]
            if uid in seen:
                continue
            seen.add(uid)

            posted_at: Optional[datetime] = None
            pub = item.findtext("pubDate")
            if pub:
                try:
                    posted_at = parsedate_to_datetime(pub)
                except Exception:
                    pass

            source_el = item.find("source")
            outlet = source_el.text if source_el is not None else "news"

            posts.append({
                "source": SOURCE_NEWS,
                "post_id": uid,
                "content": f"{title} [{outlet}]",
                "author": outlet,
                "source_name": outlet,
                "article_url": link,
                "article_published_at": _iso(posted_at),
                "posted_at": posted_at,
            })

    logger.info("News RSS fallback: %d articles fetched", len(posts))
    return posts


# ── Public entry point ────────────────────────────────────────────────────────

def fetch_new_posts(
    conn: sqlite3.Connection,
    bearer_token: Optional[str] = None,
) -> list[int]:
    """Fetch new posts/articles and persist to DB. Returns DB row IDs of new rows."""
    if bearer_token:
        raw_posts = _fetch_via_mastodon_api(bearer_token)
    else:
        logger.warning(
            "TRUTH_SOCIAL_BEARER_TOKEN not set. "
            "Truth Social blocks unauthenticated server requests via Cloudflare. "
            "Falling back to Google News RSS for Trump economic/policy statements. "
            "See collector/truth_social.py docstring for how to get a bearer token."
        )
        raw_posts = _fetch_via_news_rss()

    before = len(raw_posts)
    raw_posts = [p for p in raw_posts if _is_recent(p.get("posted_at"))]
    skipped = before - len(raw_posts)
    if skipped:
        logger.info("Date filter: dropped %d article(s) older than 6 hours", skipped)

    new_ids: list[int] = []
    for post in raw_posts:
        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO posts
                    (source, post_id, content, author, source_name,
                     article_url, article_published_at, posted_at)
                VALUES
                    (:source, :post_id, :content, :author, :source_name,
                     :article_url, :article_published_at, :posted_at)
                """,
                post,
            )
            conn.commit()
            if cur.rowcount > 0:
                new_ids.append(cur.lastrowid)
        except Exception as e:
            logger.error("DB insert error for post %s: %s", post.get("post_id"), e)

    logger.info("Truth Social collector: %d new items persisted", len(new_ids))
    return new_ids
