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
