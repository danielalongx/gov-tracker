"""
Financial data collector using yfinance.

Fetches stock snapshots, recent earnings, and insider trades.
"""
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

import yfinance as yf

from db.connection import is_postgres

logger = logging.getLogger(__name__)


def _run(conn, sql: str, params=()):
    """Execute SQL portably across SQLite and Postgres connections."""
    if is_postgres(conn):
        cur = conn.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        return cur
    return conn.execute(sql, params)


def _upsert_earnings(conn, record: dict):
    """INSERT OR REPLACE (SQLite) / upsert on (ticker, period) (Postgres)."""
    cols = ("ticker", "period", "revenue", "net_income",
            "eps_actual", "eps_estimate", "surprise_pct", "reported_at")
    values = tuple(record[c] for c in cols)
    if is_postgres(conn):
        update_cols = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ("ticker", "period"))
        sql = (
            f"INSERT INTO earnings ({', '.join(cols)}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            f" ON CONFLICT (ticker, period) DO UPDATE SET {update_cols}"
        )
    else:
        sql = f"INSERT OR REPLACE INTO earnings ({', '.join(cols)}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    _run(conn, sql, values)


def _insert_ignore_insider_trade(conn, record: dict):
    """INSERT OR IGNORE (SQLite) / ON CONFLICT DO NOTHING on
    (ticker, person_name, filed_at, action) (Postgres)."""
    cols = ("ticker", "person_name", "role", "action", "shares", "price", "filed_at")
    values = tuple(record[c] for c in cols)
    if is_postgres(conn):
        sql = (
            f"INSERT INTO insider_trades ({', '.join(cols)}) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (ticker, person_name, filed_at, action) DO NOTHING"
        )
    else:
        sql = f"INSERT OR IGNORE INTO insider_trades ({', '.join(cols)}) VALUES (?, ?, ?, ?, ?, ?, ?)"
    _run(conn, sql, values)


def fetch_stock_snapshot(ticker: str, conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    """Fetch current stock snapshot for ticker. Stores in DB if conn provided."""
    try:
        t = yf.Ticker(ticker)
        info = t.info

        snap = {
            "ticker": ticker.upper(),
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "pe_ratio": info.get("trailingPE"),
            "market_cap": info.get("marketCap"),
            "target_price": info.get("targetMeanPrice"),
            "eps_ttm": info.get("trailingEps"),
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "week52_low": info.get("fiftyTwoWeekLow"),
            "volume": info.get("regularMarketVolume"),
        }

        if conn is not None:
            _run(
                conn,
                """
                INSERT INTO stock_snapshots
                    (ticker, price, pe_ratio, market_cap, target_price,
                     eps_ttm, week52_high, week52_low, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap["ticker"], snap["price"], snap["pe_ratio"],
                    snap["market_cap"], snap["target_price"], snap["eps_ttm"],
                    snap["week52_high"], snap["week52_low"], snap["volume"],
                ),
            )
            conn.commit()
            logger.info("Stored snapshot for %s: price=%.2f", ticker, snap["price"] or 0)

        return snap

    except Exception as e:
        logger.error("fetch_stock_snapshot(%s) failed: %s", ticker, e)
        return None


def fetch_recent_earnings(ticker: str, conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """Fetch last 4 quarters of earnings. Stores in DB if conn provided."""
    try:
        t = yf.Ticker(ticker)
        # quarterly_financials: columns are period-end dates, rows are line items
        qf = t.quarterly_financials
        qe = t.quarterly_earnings  # has EPS actual/estimate columns

        results: list[dict] = []

        if qe is not None and not qe.empty:
            for i, (period, row) in enumerate(qe.iterrows()):
                if i >= 4:
                    break
                period_str = str(period)[:10] if hasattr(period, '__str__') else str(period)

                # Revenue from quarterly_financials
                revenue = None
                net_income = None
                if qf is not None and not qf.empty and str(period) in [str(c) for c in qf.columns]:
                    col = [c for c in qf.columns if str(c)[:10] == period_str]
                    if col:
                        rev_rows = [r for r in qf.index if 'revenue' in str(r).lower() or 'total revenue' in str(r).lower()]
                        ni_rows = [r for r in qf.index if 'net income' in str(r).lower()]
                        if rev_rows:
                            revenue = float(qf.loc[rev_rows[0], col[0]])
                        if ni_rows:
                            net_income = float(qf.loc[ni_rows[0], col[0]])

                eps_actual = float(row.get("Earnings", 0) or 0) if "Earnings" in row.index else None
                eps_estimate = float(row.get("Estimate", 0) or 0) if "Estimate" in row.index else None

                surprise_pct = None
                if eps_actual is not None and eps_estimate and eps_estimate != 0:
                    surprise_pct = round((eps_actual - eps_estimate) / abs(eps_estimate) * 100, 2)

                record = {
                    "ticker": ticker.upper(),
                    "period": period_str,
                    "revenue": revenue,
                    "net_income": net_income,
                    "eps_actual": eps_actual,
                    "eps_estimate": eps_estimate,
                    "surprise_pct": surprise_pct,
                    "reported_at": period_str,
                }
                results.append(record)

                if conn is not None:
                    try:
                        _upsert_earnings(conn, record)
                    except Exception as dbe:
                        logger.warning("Earnings DB insert %s/%s: %s", ticker, period_str, dbe)

        elif qf is not None and not qf.empty:
            # Fallback: use quarterly_financials only
            for i, col in enumerate(qf.columns[:4]):
                period_str = str(col)[:10]
                rev_rows = [r for r in qf.index if 'total revenue' in str(r).lower() or 'revenue' in str(r).lower()]
                ni_rows = [r for r in qf.index if 'net income' in str(r).lower()]
                revenue = float(qf.loc[rev_rows[0], col]) if rev_rows else None
                net_income = float(qf.loc[ni_rows[0], col]) if ni_rows else None
                record = {
                    "ticker": ticker.upper(),
                    "period": period_str,
                    "revenue": revenue,
                    "net_income": net_income,
                    "eps_actual": None,
                    "eps_estimate": None,
                    "surprise_pct": None,
                    "reported_at": period_str,
                }
                results.append(record)
                if conn is not None:
                    try:
                        _upsert_earnings(conn, record)
                    except Exception as dbe:
                        logger.warning("Earnings DB insert %s/%s: %s", ticker, period_str, dbe)

        if conn is not None:
            conn.commit()
        logger.info("Fetched %d earnings records for %s", len(results), ticker)
        return results

    except Exception as e:
        logger.error("fetch_recent_earnings(%s) failed: %s", ticker, e)
        return []


def fetch_insider_trades(ticker: str, conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """Fetch insider trades (Form 4 equivalent) from last 30 days via yfinance."""
    try:
        t = yf.Ticker(ticker)
        inst = t.insider_transactions

        if inst is None or inst.empty:
            logger.info("No insider trades found for %s", ticker)
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        results: list[dict] = []

        for _, row in inst.iterrows():
            start_date = row.get("startDate")
            if start_date is None:
                continue
            # startDate may be a Timestamp or string
            if hasattr(start_date, "tzinfo"):
                filed_dt = start_date if start_date.tzinfo else start_date.replace(tzinfo=timezone.utc)
            else:
                try:
                    filed_dt = datetime.fromisoformat(str(start_date)).replace(tzinfo=timezone.utc)
                except Exception:
                    continue

            if filed_dt < cutoff:
                continue

            shares = row.get("shares") or row.get("Shares")
            value = row.get("value") or row.get("Value")
            text = str(row.get("text") or row.get("Text") or "")
            insider = str(row.get("insider") or row.get("Insider") or "")
            position = str(row.get("position") or row.get("Position") or "")
            transaction = str(row.get("transaction") or row.get("Transaction") or "")

            # Determine buy/sell
            action = "buy" if any(w in transaction.lower() for w in ("purchase", "buy", "acquired")) else "sell"

            price = None
            if shares and value and float(shares or 0) != 0:
                try:
                    price = float(value) / float(shares)
                except Exception:
                    pass

            filed_str = filed_dt.strftime("%Y-%m-%d")
            record = {
                "ticker": ticker.upper(),
                "person_name": insider,
                "role": position,
                "action": action,
                "shares": float(shares) if shares else None,
                "price": price,
                "filed_at": filed_str,
            }
            results.append(record)

            if conn is not None:
                try:
                    _insert_ignore_insider_trade(conn, record)
                except Exception as dbe:
                    logger.warning("Insider trade DB insert %s: %s", ticker, dbe)

        if conn is not None:
            conn.commit()
        logger.info("Fetched %d insider trades for %s (last 30d)", len(results), ticker)
        return results

    except Exception as e:
        logger.error("fetch_insider_trades(%s) failed: %s", ticker, e)
        return []
