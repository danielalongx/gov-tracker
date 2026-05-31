import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

FEDERAL_REGISTER_URL = "https://www.federalregister.gov/api/v1/documents.json"
SOURCE = "federal_register"

_ECONOMIC_TERMS = {
    "tariff", "trade", "sanction", "tax", "economy", "finance", "bank",
    "energy", "oil", "gas", "semiconductor", "agriculture", "healthcare",
    "pharmaceutical", "defense", "manufacturing", "import", "export",
    "investment", "securities", "currency", "inflation", "federal reserve",
    "interest rate", "technology", "telecom", "steel", "aluminum",
}


def _is_economically_relevant(title: str, abstract: Optional[str] = None) -> bool:
    text = (title + " " + (abstract or "")).lower()
    return any(term in text for term in _ECONOMIC_TERMS)


def fetch_new_documents(conn: sqlite3.Connection) -> list[int]:
    """Fetch recent Federal Register presidential docs and major rules.

    Returns DB row IDs for newly inserted documents.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    # requests handles list values as repeated params:
    # conditions[type][]=PRESDOC&conditions[type][]=RULE
    params = [
        ("conditions[type][]", "PRESDOC"),
        ("conditions[type][]", "RULE"),
        ("conditions[publication_date][gte]", since),
        ("per_page", 20),
        ("order", "newest"),
        ("fields[]", "title"),
        ("fields[]", "document_number"),
        ("fields[]", "type"),
        ("fields[]", "signing_date"),
        ("fields[]", "publication_date"),
        ("fields[]", "abstract"),
        ("fields[]", "html_url"),
        ("fields[]", "executive_order_number"),
    ]

    try:
        resp = requests.get(FEDERAL_REGISTER_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error("Federal Register API error: %s", e)
        return []

    documents = data.get("results", [])
    new_ids: list[int] = []

    for doc in documents:
        doc_id = doc.get("document_number")
        title = doc.get("title", "")
        abstract = doc.get("abstract")

        if not doc_id:
            continue
        if not _is_economically_relevant(title, abstract):
            continue

        eo_num = doc.get("executive_order_number")
        eo_prefix = f"[Executive Order {eo_num}] " if eo_num else ""
        url = doc.get("html_url", "")
        content = (
            f"[Federal Register {doc.get('type', '')}] {eo_prefix}{title}\n"
            f"{abstract or ''}\n{url}"
        ).strip()

        posted_at: Optional[datetime] = None
        raw_date = doc.get("signing_date") or doc.get("publication_date")
        if raw_date:
            try:
                posted_at = datetime.fromisoformat(raw_date)
            except ValueError:
                pass

        try:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO posts (source, post_id, content, author, posted_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (SOURCE, doc_id, content, "Federal Register", posted_at),
            )
            conn.commit()
            if cur.rowcount > 0:
                new_ids.append(cur.lastrowid)
        except Exception as e:
            logger.error("DB insert error for document %s: %s", doc_id, e)

    logger.info("Federal Register: %d new relevant documents", len(new_ids))
    return new_ids
