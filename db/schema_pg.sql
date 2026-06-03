-- PostgreSQL schema for gov-tracker (Supabase)
-- Run this once when setting up a new Supabase project.

CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    post_id TEXT NOT NULL,
    content TEXT,
    author TEXT,
    source_name TEXT,
    article_published_at TIMESTAMPTZ,
    article_url TEXT,
    posted_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    UNIQUE (source, post_id)
);

CREATE TABLE IF NOT EXISTS analysis (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES posts(id),
    is_relevant BOOLEAN DEFAULT FALSE,
    sentiment TEXT,
    tickers JSONB DEFAULT '[]',
    industries JSONB DEFAULT '[]',
    companies JSONB DEFAULT '[]',
    relevance_score INTEGER DEFAULT 0,
    summary TEXT,
    source_name TEXT,
    disclaimer TEXT,
    score_news REAL DEFAULT 0,
    score_financial REAL DEFAULT 0,
    score_pipeline REAL DEFAULT 0,
    score_regulatory REAL DEFAULT 0,
    score_capital_flows REAL DEFAULT 0,
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    notified BOOLEAN DEFAULT FALSE,
    notified_at TIMESTAMPTZ,
    hold_for_digest BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    ntfy_channel TEXT,
    risk_profile TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    topic TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_snapshots (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    price REAL,
    pe_ratio REAL,
    market_cap REAL,
    target_price REAL,
    eps_ttm REAL,
    week52_high REAL,
    week52_low REAL,
    volume BIGINT
);

CREATE TABLE IF NOT EXISTS earnings (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    period TEXT,
    revenue REAL,
    net_income REAL,
    eps_actual REAL,
    eps_estimate REAL,
    surprise_pct REAL,
    reported_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS insider_trades (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    person_name TEXT,
    role TEXT,
    action TEXT,
    shares REAL,
    price REAL,
    filed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ark_holdings (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    fund TEXT NOT NULL,
    ticker TEXT,
    company TEXT,
    shares REAL,
    weight REAL,
    UNIQUE (date, fund, ticker)
);

-- Default user
INSERT INTO users (name, ntfy_channel) VALUES ('default', 'US-gov-invest-update')
ON CONFLICT DO NOTHING;
