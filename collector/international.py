"""
International news collector — Denmark and EU economic/business headlines.

Fetches the top 3 most recent articles (within the last hour) from Google News
RSS for each region and inserts them into the posts table.
"""

import hashlib
import logging
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

from collector.truth_social import _GOOGLE_NEWS_BASE, _is_recent, _iso

logger = logging.getLogger(__name__)

SOURCE_DENMARK    = "denmark_news"
SOURCE_EU         = "eu_news"
SOURCE_CHINA      = "china_news"
SOURCE_REUTERS    = "reuters_news"
SOURCE_US_CORP    = "us_corporate_news"
SOURCE_MARKETWATCH = "marketwatch_news"
SOURCE_FT         = "ft_news"
SOURCE_CNBC       = "cnbc_news"
SOURCE_BLOOMBERG  = "bloomberg_news"
SOURCE_CLS        = "cls_news"      # 财联社
SOURCE_SINA       = "sina_finance"  # 新浪财经

_DENMARK_QUERY     = "Denmark economy OR business OR market OR trade"
_EU_QUERY          = "European Union economy OR policy OR market OR trade"
_CHINA_QUERY       = "中国 经济 OR 股市 OR 贸易 OR 科技 OR 金融"
_REUTERS_QUERY     = "site:reuters.com economy OR markets OR trade OR Federal Reserve OR tariffs"
_US_CORP_QUERY     = "earnings OR quarterly results OR revenue guidance OR CEO OR merger acquisition"
_MARKETWATCH_QUERY = "site:marketwatch.com markets OR stocks OR economy"
_FT_QUERY          = "site:ft.com markets OR economy OR trade OR investment"
_CNBC_QUERY        = "site:cnbc.com markets OR stocks OR fed OR earnings"
_BLOOMBERG_QUERY   = "site:bloomberg.com markets OR economy OR Fed OR tariffs"
_CLS_QUERY         = "财联社 股市 OR 经济 OR 板块"
_SINA_QUERY        = "新浪财经 A股 OR 港股 OR 美股"

_TOP_N = 3  # max articles per source per run


def _fetch_google_news(query: str, source: str) -> list[dict]:
    """Return up to _TOP_N recent articles from Google News RSS matching query."""
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
        logger.warning("Google News RSS error (source=%s, q=%r): %s", source, query, e)
        return []

    posts: list[dict] = []
    for item in root.findall(".//item"):
        if len(posts) >= _TOP_N:
            break

        link = item.findtext("link") or ""
        title = item.findtext("title") or ""
        if not link or not title:
            continue

        posted_at: Optional[datetime] = None
        pub = item.findtext("pubDate")
        if pub:
            try:
                posted_at = parsedate_to_datetime(pub)
            except Exception:
                pass

        if not _is_recent(posted_at):
            continue

        uid = hashlib.md5(link.encode()).hexdigest()[:16]
        source_el = item.find("source")
        outlet = source_el.text if source_el is not None else "news"

        posts.append({
            "source": source,
            "post_id": uid,
            "content": f"{title} [{outlet}]",
            "author": outlet,
            "source_name": outlet,
            "article_url": link,
            "article_published_at": _iso(posted_at),
            "posted_at": posted_at,
        })

    return posts


def _persist(conn: sqlite3.Connection, posts: list[dict]) -> list[int]:
    new_ids: list[int] = []
    for post in posts:
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
    return new_ids


def fetch_denmark_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent Denmark economy articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_DENMARK_QUERY, SOURCE_DENMARK)
    new_ids = _persist(conn, posts)
    logger.info("Denmark news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_eu_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent EU economy articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_EU_QUERY, SOURCE_EU)
    new_ids = _persist(conn, posts)
    logger.info("EU news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_china_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent China financial/economic articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_CHINA_QUERY, SOURCE_CHINA)
    new_ids = _persist(conn, posts)
    logger.info("China news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_reuters_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent Reuters macro articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_REUTERS_QUERY, SOURCE_REUTERS)
    new_ids = _persist(conn, posts)
    logger.info("Reuters news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_us_corporate_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent US earnings/corporate articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_US_CORP_QUERY, SOURCE_US_CORP)
    new_ids = _persist(conn, posts)
    logger.info("US corporate news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_marketwatch_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent MarketWatch articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_MARKETWATCH_QUERY, SOURCE_MARKETWATCH)
    new_ids = _persist(conn, posts)
    logger.info("MarketWatch news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_ft_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent Financial Times articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_FT_QUERY, SOURCE_FT)
    new_ids = _persist(conn, posts)
    logger.info("FT news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_cnbc_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent CNBC articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_CNBC_QUERY, SOURCE_CNBC)
    new_ids = _persist(conn, posts)
    logger.info("CNBC news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_bloomberg_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent Bloomberg articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_BLOOMBERG_QUERY, SOURCE_BLOOMBERG)
    new_ids = _persist(conn, posts)
    logger.info("Bloomberg news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_cls_news(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent 财联社 articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_CLS_QUERY, SOURCE_CLS)
    new_ids = _persist(conn, posts)
    logger.info("财联社 news: %d new article(s)", len(new_ids))
    return new_ids


def fetch_sina_finance(conn: sqlite3.Connection) -> list[int]:
    """Fetch top 3 recent 新浪财经 articles. Returns new DB row IDs."""
    posts = _fetch_google_news(_SINA_QUERY, SOURCE_SINA)
    new_ids = _persist(conn, posts)
    logger.info("新浪财经 news: %d new article(s)", len(new_ids))
    return new_ids
