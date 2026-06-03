CREATE_POSTS = """
CREATE TABLE IF NOT EXISTS posts (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source               TEXT    NOT NULL,
    post_id              TEXT    NOT NULL,
    content              TEXT,
    author               TEXT,
    source_name          TEXT,    -- human-readable outlet / platform name
    article_url          TEXT,    -- canonical article / post URL
    article_published_at TEXT,    -- ISO datetime from the article itself
    posted_at            DATETIME,
    fetched_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed            INTEGER  DEFAULT 0,
    UNIQUE(source, post_id)
)
"""

CREATE_ANALYSIS = """
CREATE TABLE IF NOT EXISTS analysis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER NOT NULL REFERENCES posts(id),
    is_relevant     INTEGER DEFAULT 0,
    sentiment       TEXT,
    tickers         TEXT,    -- JSON array of ticker strings
    companies       TEXT,    -- JSON array of {name, ticker, impact}
    industries      TEXT,    -- JSON array of industry strings
    relevance_score REAL     DEFAULT 0,
    summary         TEXT,
    source_name     TEXT,    -- LLM-extracted outlet name
    analyzed_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    notified        INTEGER  DEFAULT 0,
    hold_for_digest INTEGER  DEFAULT 0,  -- 1 = pending digest, not yet pushed
    notified_at     DATETIME             -- when the push was actually sent
)
"""

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    ntfy_channel TEXT NOT NULL,
    risk_profile TEXT DEFAULT 'moderate'
)
"""

CREATE_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    topic   TEXT    NOT NULL
)
"""

CREATE_STOCK_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS stock_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT    NOT NULL,
    fetched_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    price        REAL,
    pe_ratio     REAL,
    market_cap   REAL,
    target_price REAL,
    eps_ttm      REAL,
    week52_high  REAL,
    week52_low   REAL,
    volume       INTEGER
)
"""

CREATE_EARNINGS = """
CREATE TABLE IF NOT EXISTS earnings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT    NOT NULL,
    period        TEXT    NOT NULL,
    revenue       REAL,
    net_income    REAL,
    eps_actual    REAL,
    eps_estimate  REAL,
    surprise_pct  REAL,
    reported_at   TEXT,
    UNIQUE(ticker, period)
)
"""

CREATE_INSIDER_TRADES = """
CREATE TABLE IF NOT EXISTS insider_trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    person_name TEXT,
    role        TEXT,
    action      TEXT,
    shares      REAL,
    price       REAL,
    filed_at    TEXT,
    UNIQUE(ticker, person_name, filed_at, action)
)
"""
