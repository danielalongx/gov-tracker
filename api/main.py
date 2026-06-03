import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

DB_PATH = Path(__file__).parent.parent / "data" / "gov_tracker.db"

app = FastAPI(title="Gov Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# LLM writes Chinese sentiments; map them to English for the API response.
_SENTIMENT_MAP = {
    "利多": "bullish",
    "利空": "bearish",
    "中性": "neutral",
    "混合": "mixed",
}
_SENTIMENT_MAP_REVERSE = {v: k for k, v in _SENTIMENT_MAP.items()}

_IMPACT_MAP = {
    "利多": "bullish",
    "利空": "bearish",
}

_GURU_SOURCES = frozenset({
    "arkk_trade", "arkw_trade",
    "guru_buffett", "guru_burry", "guru_ackman",
    "guru_dalio", "guru_druckenmiller", "guru_tepper", "guru_other",
})
_GURU_DISCLAIMER = (
    "本信息来源于公开监管文件（SEC 13F）或 ARK 官方公开披露，"
    "仅供参考，不构成投资建议。投资者需自行承担投资风险。"
)


@contextmanager
def _conn():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


def _row_to_signal(row: sqlite3.Row) -> dict:
    tickers = json.loads(row["tickers"] or "[]")
    industries = json.loads(row["industries"] or "[]")
    companies_raw = json.loads(row["companies"] or "[]")

    companies = [
        {
            "name": c.get("name", ""),
            "ticker": c.get("ticker"),
            "impact": _IMPACT_MAP.get(c.get("impact", ""), c.get("impact", "")),
        }
        for c in companies_raw
    ]

    # Prefer LLM-extracted outlet name over the collector-supplied one.
    display_source = (
        row["analysis_source_name"]
        or row["post_source_name"]
        or row["source"]
    )

    source = row["source"] or ""
    result: dict = {
        "id": row["post_id"],
        "source": source,
        "source_name": display_source,
        "content": row["content"],
        "article_url": row["article_url"],
        "published_at": row["article_published_at"] or row["posted_at"],
        "fetched_at": row["fetched_at"],
        "analysis": {
            "sentiment": _SENTIMENT_MAP.get(
                row["sentiment"], row["sentiment"] or "neutral"
            ),
            "relevance_score": int(row["relevance_score"] or 0),
            "summary": row["summary"] or "",
            "tickers": tickers,
            "industries": industries,
            "companies": companies,
        },
    }
    result["dimension_scores"] = {
        "news": int(row["score_news"] or 0),
        "financial": int(row["score_financial"] or 0),
        "pipeline": int(row["score_pipeline"] or 0),
        "regulatory": int(row["score_regulatory"] or 0),
        "capital_flows": int(row["score_capital_flows"] or 0),
        "technical": 0,
    }

    if source in _GURU_SOURCES:
        result["disclaimer"] = _GURU_DISCLAIMER
    return result


_SELECT = """
    SELECT
        p.id          AS post_id,
        p.source,
        p.source_name AS post_source_name,
        p.content,
        p.article_url,
        p.article_published_at,
        p.posted_at,
        p.fetched_at,
        a.sentiment,
        a.relevance_score,
        a.summary,
        a.tickers,
        a.companies,
        a.industries,
        a.source_name AS analysis_source_name,
        a.score_news,
        a.score_financial,
        a.score_pipeline,
        a.score_regulatory,
        a.score_capital_flows
    FROM posts p
    JOIN analysis a ON a.post_id = p.id
"""


@app.get("/health")
def health():
    with _conn() as con:
        count = con.execute(
            "SELECT COUNT(*) FROM analysis WHERE is_relevant = 1"
        ).fetchone()[0]
    return {"status": "ok", "db_path": str(DB_PATH), "signal_count": count}


@app.get("/signals")
def list_signals(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: Optional[str] = None,
    sentiment: Optional[str] = None,
    min_score: int = Query(6, ge=0, le=10),
):
    conditions = ["a.is_relevant = 1", "a.relevance_score >= ?"]
    params: list = [min_score]

    if source:
        conditions.append("p.source = ?")
        params.append(source)

    if sentiment:
        db_sentiment = _SENTIMENT_MAP_REVERSE.get(sentiment, sentiment)
        conditions.append("a.sentiment = ?")
        params.append(db_sentiment)

    where = " AND ".join(conditions)

    with _conn() as con:
        rows = con.execute(
            f"{_SELECT} WHERE {where}"
            " ORDER BY COALESCE(p.article_published_at, p.posted_at) DESC"
            " LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return [_row_to_signal(r) for r in rows]


@app.get("/stocks/{ticker}/snapshot")
def get_stock_snapshot(ticker: str):
    ticker = ticker.upper()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM stock_snapshots WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {ticker}")
    return dict(row)


@app.get("/stocks/{ticker}/earnings")
def get_stock_earnings(ticker: str):
    ticker = ticker.upper()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM earnings WHERE ticker = ? ORDER BY period DESC LIMIT 4",
            (ticker,),
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No earnings found for {ticker}")
    return [dict(r) for r in rows]


@app.get("/stocks/{ticker}/signals")
def get_ticker_signals(
    ticker: str,
    limit: int = Query(20, ge=1, le=100),
    min_score: int = Query(6, ge=0, le=10),
):
    ticker = ticker.upper()
    with _conn() as con:
        rows = con.execute(
            f"{_SELECT} WHERE a.is_relevant = 1 AND a.relevance_score >= ?"
            " AND (a.tickers LIKE ? OR p.content LIKE ?)"
            " ORDER BY COALESCE(p.article_published_at, p.posted_at) DESC"
            " LIMIT ?",
            (min_score, f'%"{ticker}"%', f"%{ticker}%", limit),
        ).fetchall()
    return [_row_to_signal(r) for r in rows]


@app.get("/signals/{signal_id}")
def get_signal(signal_id: int):
    with _conn() as con:
        row = con.execute(
            f"{_SELECT} WHERE p.id = ?",
            (signal_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")

    return _row_to_signal(row)
