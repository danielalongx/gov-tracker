import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from db.connection import get_connection, is_postgres

DB_PATH = Path(__file__).parent.parent / "data" / "gov_tracker.db"

app = FastAPI(title="Gov Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _ensure_db_ready() -> None:
    """Create the SQLite file/tables on first boot (e.g. fresh Railway deploys
    where data/ is gitignored and doesn't exist yet)."""
    from db.init_db import init_db

    init_db()

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
    con = get_connection()
    try:
        yield con
    finally:
        con.close()


def _exec(con, sql: str, params=()):
    """Execute SQL portably across SQLite and Postgres connections.

    Translates '?' placeholders to '%s' for Postgres and returns a cursor
    whose rows support both dict-style (row["col"]) and dict() access for
    either backend.
    """
    if is_postgres(con):
        import psycopg2.extras

        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql.replace("?", "%s"), params)
        return cur
    return con.execute(sql, params)


def _maybe_json(val, default):
    """JSONB columns come back already-parsed from Postgres; SQLite stores them as TEXT."""
    if val is None:
        return default
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except (TypeError, ValueError):
        return default


def _row_to_signal(row) -> dict:
    tickers = _maybe_json(row["tickers"], [])
    industries = _maybe_json(row["industries"], [])
    companies_raw = _maybe_json(row["companies"], [])

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
    result["category"] = row["category"] or "general"

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
        a.score_capital_flows,
        a.category
    FROM posts p
    JOIN analysis a ON a.post_id = p.id
"""


@app.get("/health")
def health():
    with _conn() as con:
        pg = is_postgres(con)
        count = _exec(
            con, "SELECT COUNT(*) AS cnt FROM analysis WHERE is_relevant"
        ).fetchone()["cnt"]
    return {
        "status": "ok",
        "db": "postgres" if pg else str(DB_PATH),
        "signal_count": count,
    }


@app.get("/signals")
def list_signals(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source: Optional[str] = None,
    sentiment: Optional[str] = None,
    min_score: int = Query(6, ge=0, le=10),
    category: Optional[str] = None,
):
    conditions = ["a.is_relevant", "a.relevance_score >= ?"]
    params: list = [min_score]

    if source:
        conditions.append("p.source = ?")
        params.append(source)

    if sentiment:
        db_sentiment = _SENTIMENT_MAP_REVERSE.get(sentiment, sentiment)
        conditions.append("a.sentiment = ?")
        params.append(db_sentiment)

    if category:
        conditions.append("a.category = ?")
        params.append(category)

    where = " AND ".join(conditions)

    with _conn() as con:
        rows = _exec(
            con,
            f"{_SELECT} WHERE {where}"
            " ORDER BY COALESCE(p.article_published_at, p.posted_at) DESC"
            " LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return [_row_to_signal(r) for r in rows]


@app.get("/stocks/{ticker}")
def get_stock(ticker: str):
    """Return snapshot from DB; auto-fetches fresh data if cached entry is >1 hour old."""
    from datetime import timedelta
    from collector.financials import fetch_stock_snapshot

    ticker = ticker.upper()
    with _conn() as con:
        row = _exec(
            con,
            "SELECT * FROM stock_snapshots WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 1",
            (ticker,),
        ).fetchone()

        stale = True
        if row:
            try:
                fetched = datetime.fromisoformat(str(row["fetched_at"]).replace(" ", "T"))
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
                stale = (datetime.now(timezone.utc) - fetched) > timedelta(hours=1)
            except Exception:
                stale = True

        if stale:
            snap = fetch_stock_snapshot(ticker, con)
            if snap is None and row is None:
                raise HTTPException(status_code=404, detail=f"Could not fetch data for {ticker}")
            if snap:
                row = _exec(
                    con,
                    "SELECT * FROM stock_snapshots WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 1",
                    (ticker,),
                ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"No snapshot found for {ticker}")
    return dict(row)


@app.get("/stocks/{ticker}/snapshot")
def get_stock_snapshot(ticker: str):
    ticker = ticker.upper()
    with _conn() as con:
        row = _exec(
            con,
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
        rows = _exec(
            con,
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
        # JSONB columns need an explicit text cast for LIKE on Postgres;
        # SQLite stores them as TEXT already and doesn't support `::text`.
        tickers_col = "a.tickers::text" if is_postgres(con) else "a.tickers"
        rows = _exec(
            con,
            f"{_SELECT} WHERE a.is_relevant AND a.relevance_score >= ?"
            f" AND ({tickers_col} LIKE ? OR p.content LIKE ?)"
            " ORDER BY COALESCE(p.article_published_at, p.posted_at) DESC"
            " LIMIT ?",
            (min_score, f'%"{ticker}"%', f"%{ticker}%", limit),
        ).fetchall()
    return [_row_to_signal(r) for r in rows]


@app.get("/signals/{signal_id}")
def get_signal(signal_id: int):
    with _conn() as con:
        row = _exec(
            con,
            f"{_SELECT} WHERE p.id = ?",
            (signal_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Signal not found")

    return _row_to_signal(row)


# ---------------------------------------------------------------------------
# Subscription / payment endpoints
# ---------------------------------------------------------------------------

from fastapi import Request, Body
from fastapi.responses import JSONResponse

@app.get("/tiers")
@app.get("/subscription/tiers")
def get_tiers():
    """Return all available tiers and their limits — no auth required."""
    from api.payments import TIER_LIMITS
    return {
        "tiers": [
            {
                "id": tier_id,
                "name": {"free": "免费版", "pro": "Pro", "analyst": "Analyst"}[tier_id],
                "price_monthly": limits["price_monthly"],
                "max_stocks": limits["max_stocks"],
                "custom_weights": limits["custom_weights"],
                "digest_count": limits["digest_count"],
                "api_access": limits["api_access"],
            }
            for tier_id, limits in TIER_LIMITS.items()
        ]
    }


@app.post("/checkout/{tier}")
def create_checkout_path(
    tier: str,
    user_id: int = Body(...),
    success_url: str = Body(...),
    cancel_url: str = Body(...),
):
    """Create a Stripe checkout session (tier in path)."""
    return create_checkout(user_id=user_id, tier=tier, success_url=success_url, cancel_url=cancel_url)


@app.post("/subscription/checkout")
def create_checkout(
    user_id: int = Body(...),
    tier: str = Body(...),
    success_url: str = Body(...),
    cancel_url: str = Body(...),
):
    """Create a Stripe checkout session. Returns {checkout_url} or {error}."""
    from api.payments import create_checkout_session
    if tier not in ("pro", "analyst"):
        raise HTTPException(status_code=400, detail="Invalid tier")
    url = create_checkout_session(user_id, tier, success_url, cancel_url)
    if not url:
        return JSONResponse(
            status_code=503,
            content={"error": "Stripe not configured. Set STRIPE_SECRET_KEY in .env."}
        )
    return {"checkout_url": url}


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events (subscription activated/cancelled)."""
    from api.payments import handle_webhook
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    with _conn() as con:
        result = handle_webhook(payload, sig, con)
    return result


# ---------------------------------------------------------------------------
# Watchlist endpoints (user stock tracking + dimension weights)
# ---------------------------------------------------------------------------

@app.get("/users/{user_id}/watchlist")
def get_watchlist(user_id: int):
    with _conn() as con:
        rows = _exec(
            con,
            "SELECT ticker, name, sector, added_at, weights FROM user_watchlist WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["weights"] = _maybe_json(d.get("weights"), None)
            result.append(d)
    return result


@app.post("/users/{user_id}/watchlist")
def add_to_watchlist(user_id: int, body: dict = Body(...)):
    ticker = body.get("ticker", "").upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    with _conn() as con:
        if is_postgres(con):
            sql = (
                "INSERT INTO user_watchlist (user_id, ticker, name, sector) VALUES (?,?,?,?)"
                " ON CONFLICT (user_id, ticker) DO NOTHING"
            )
        else:
            sql = "INSERT OR IGNORE INTO user_watchlist (user_id, ticker, name, sector) VALUES (?,?,?,?)"
        _exec(con, sql, (user_id, ticker, body.get("name"), body.get("sector")))
        con.commit()
    return {"status": "added", "ticker": ticker}


@app.put("/users/{user_id}/watchlist/{ticker}/weights")
def update_weights(user_id: int, ticker: str, body: dict = Body(...)):
    import json as _json
    ticker = ticker.upper()
    with _conn() as con:
        if is_postgres(con):
            import psycopg2.extras
            weights_param = psycopg2.extras.Json(body)
        else:
            weights_param = _json.dumps(body)
        _exec(
            con,
            "UPDATE user_watchlist SET weights = ? WHERE user_id = ? AND ticker = ?",
            (weights_param, user_id, ticker)
        )
        con.commit()
    return {"status": "updated", "ticker": ticker}


@app.delete("/users/{user_id}/watchlist/{ticker}")
def remove_from_watchlist(user_id: int, ticker: str):
    ticker = ticker.upper()
    with _conn() as con:
        _exec(
            con,
            "DELETE FROM user_watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, ticker)
        )
        con.commit()
    return {"status": "removed", "ticker": ticker}


# ---------------------------------------------------------------------------
# Company profile endpoints (Stage 2 Scoring Engine)
# ---------------------------------------------------------------------------

@app.get("/mechanisms")
def list_mechanisms():
    with _conn() as con:
        rows = _exec(
            con, "SELECT * FROM mechanism_rules ORDER BY mechanism_type, id"
        ).fetchall()
    grouped: dict = {}
    for row in rows:
        r = dict(row)
        mtype = r["mechanism_type"]
        grouped.setdefault(mtype, []).append(r)
    return grouped


@app.get("/company/{ticker}/profile")
def get_company_profile(ticker: str):
    ticker = ticker.upper()
    with _conn() as con:
        row = _exec(
            con,
            "SELECT * FROM company_profiles WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No profile found for {ticker}")
    result = dict(row)
    for field in ("geo_exposure_json", "revenue_segments_json", "characteristics_json"):
        result[field] = _maybe_json(result.get(field), result.get(field))
    return result
