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
    hold_for_digest BOOLEAN DEFAULT FALSE,
    category TEXT DEFAULT NULL
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
    reported_at TIMESTAMPTZ,
    UNIQUE (ticker, period)
);

CREATE TABLE IF NOT EXISTS insider_trades (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    person_name TEXT,
    role TEXT,
    action TEXT,
    shares REAL,
    price REAL,
    filed_at TIMESTAMPTZ,
    UNIQUE (ticker, person_name, filed_at, action)
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

-- Stage 2: Signal Scoring Engine

ALTER TABLE analysis ADD COLUMN IF NOT EXISTS score REAL DEFAULT NULL;

CREATE TABLE IF NOT EXISTS mechanisms (
    id             SERIAL PRIMARY KEY,
    signal_id      INTEGER REFERENCES analysis(id) ON DELETE CASCADE,
    mechanism_type TEXT    NOT NULL,
    description    TEXT,
    direction      INTEGER DEFAULT 0,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_profiles (
    ticker                TEXT PRIMARY KEY,
    company_name          TEXT,
    sector                TEXT,
    listed_market         TEXT,
    pricing_currency      TEXT DEFAULT 'USD',
    geo_exposure_json     JSONB,
    revenue_segments_json JSONB,
    characteristics_json  JSONB,
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signal_company_links (
    id               SERIAL PRIMARY KEY,
    signal_id        INTEGER REFERENCES analysis(id) ON DELETE CASCADE,
    ticker           TEXT,
    impact_direction INTEGER DEFAULT 0,
    impact_magnitude REAL    DEFAULT 0.5,
    price_in_ratio   REAL    DEFAULT 0.0,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_company_links_ticker ON signal_company_links(ticker);
CREATE INDEX IF NOT EXISTS idx_mechanisms_signal_id ON mechanisms(signal_id);

-- Seed company profiles (mock data for Stage 2 scoring engine)
INSERT INTO company_profiles (ticker, company_name, sector, listed_market, pricing_currency, geo_exposure_json, revenue_segments_json, characteristics_json) VALUES
('NVDA',  'NVIDIA Corporation',                  'Technology/Semiconductors',       'NASDAQ', 'USD', '{"US": 0.50, "Taiwan": 0.10, "Europe": 0.20, "Asia": 0.20}',  '{"datacenter": 0.82, "gaming": 0.12, "automotive": 0.03, "professional_viz": 0.03}', '{"rate_sensitive": false, "ai_exposed": true, "semiconductor": true, "export_controlled": true}'),
('AAPL',  'Apple Inc.',                          'Technology/Consumer Electronics', 'NASDAQ', 'USD', '{"US": 0.42, "China": 0.19, "Europe": 0.24, "Rest": 0.15}',   '{"iphone": 0.52, "services": 0.22, "mac": 0.10, "wearables": 0.10, "ipad": 0.06}', '{"rate_sensitive": true, "ai_exposed": true, "china_exposed": true, "consumer_discretionary": true}'),
('TSLA',  'Tesla Inc.',                          'Consumer Discretionary/Automotive','NASDAQ','USD', '{"US": 0.48, "China": 0.22, "Europe": 0.25, "Rest": 0.05}',   '{"automotive": 0.84, "energy_storage": 0.08, "services": 0.08}', '{"rate_sensitive": true, "ai_exposed": true, "china_exposed": true, "ev": true}'),
('MSFT',  'Microsoft Corporation',              'Technology/Software',              'NASDAQ', 'USD', '{"US": 0.52, "Europe": 0.25, "Asia": 0.15, "Rest": 0.08}',    '{"cloud": 0.43, "productivity": 0.33, "gaming": 0.09, "linkedin": 0.07, "other": 0.08}', '{"rate_sensitive": false, "ai_exposed": true, "cloud": true, "enterprise": true}'),
('GOOGL', 'Alphabet Inc.',                       'Technology/Internet',             'NASDAQ', 'USD', '{"US": 0.47, "Europe": 0.28, "Asia": 0.15, "Rest": 0.10}',    '{"search_ads": 0.57, "youtube": 0.10, "cloud": 0.11, "other_bets": 0.01, "other": 0.21}', '{"rate_sensitive": false, "ai_exposed": true, "advertising": true, "cloud": true}'),
('AMZN',  'Amazon.com Inc.',                     'Consumer Discretionary/E-commerce','NASDAQ','USD', '{"US": 0.62, "Europe": 0.25, "Rest": 0.13}',                  '{"aws": 0.17, "retail_us": 0.44, "retail_intl": 0.24, "advertising": 0.08, "other": 0.07}', '{"rate_sensitive": true, "ai_exposed": true, "cloud": true, "consumer_cyclical": true}'),
('META',  'Meta Platforms Inc.',                 'Technology/Social Media',         'NASDAQ', 'USD', '{"US": 0.44, "Europe": 0.25, "Asia": 0.20, "Rest": 0.11}',    '{"advertising": 0.97, "reality_labs": 0.02, "other": 0.01}', '{"rate_sensitive": false, "ai_exposed": true, "advertising": true, "vr_ar": true}'),
('BRKB',  'Berkshire Hathaway Inc.',             'Financials/Conglomerate',         'NYSE',   'USD', '{"US": 0.87, "International": 0.13}',                          '{"insurance": 0.28, "railroad": 0.14, "utilities": 0.10, "manufacturing": 0.20, "equities": 0.28}', '{"rate_sensitive": true, "insurance": true, "value": true, "conglomerate": true}'),
('JPM',   'JPMorgan Chase & Co.',                'Financials/Banking',              'NYSE',   'USD', '{"US": 0.65, "Europe": 0.18, "Asia": 0.17}',                  '{"consumer_banking": 0.35, "investment_banking": 0.30, "commercial_banking": 0.15, "asset_management": 0.20}', '{"rate_sensitive": true, "banking": true, "yield_curve": true, "credit_cycle": true}'),
('TSM',   'Taiwan Semiconductor Manufacturing', 'Technology/Semiconductors',       'NYSE',   'USD', '{"Taiwan": 0.80, "Asia": 0.15, "US": 0.05}',                  '{"advanced_node": 0.53, "specialty": 0.30, "mature_node": 0.17}', '{"rate_sensitive": false, "ai_exposed": true, "semiconductor": true, "geopolitical_risk": true, "export_controlled": true}')
ON CONFLICT (ticker) DO NOTHING;

-- User watchlist (per-user stock tracking + dimension weights)
CREATE TABLE IF NOT EXISTS user_watchlist (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    ticker     TEXT    NOT NULL,
    name       TEXT,
    sector     TEXT,
    added_at   TIMESTAMPTZ DEFAULT NOW(),
    weights    JSONB,
    UNIQUE (user_id, ticker)
);

-- Mechanism rules (Stage 2 Scoring Engine)
CREATE TABLE IF NOT EXISTS mechanism_rules (
    id              SERIAL PRIMARY KEY,
    mechanism_type  TEXT    NOT NULL,
    affects_feature TEXT    NOT NULL,
    direction       INTEGER NOT NULL,
    base_strength   REAL    DEFAULT 1.0,
    confidence      TEXT    DEFAULT 'moderate',
    notes           TEXT,
    UNIQUE (mechanism_type, affects_feature)
);

INSERT INTO mechanism_rules (mechanism_type, affects_feature, direction, base_strength, confidence, notes) VALUES
('rate_high', 'high_debt_ratio', -1, 2.5, 'consensus', 'High rates → debt service burden kills leveraged names'),
('rate_high', 'low_interest_coverage', -1, 2.0, 'consensus', 'Thin coverage crushed when rates stay elevated'),
('rate_high', 'high_forward_pe', -1, 1.5, 'moderate', 'Duration compression: high multiples de-rate'),
('rate_high', 'high_net_cash', 1, 2.0, 'consensus', 'Cash earns more; net-cash companies benefit directly'),
('rate_high', 'strong_fcf', 1, 1.5, 'moderate', 'Strong FCF companies self-fund without expensive debt'),
('rate_falling', 'high_debt_ratio', 1, 2.0, 'consensus', 'Rate relief eases debt service for leveraged names'),
('rate_falling', 'high_forward_pe', 1, 1.5, 'moderate', 'Duration expansion: growth multiples re-rate upward'),
('rate_falling', 'high_net_cash', -1, 0.5, 'situational', 'Cash earns less; relative disadvantage vs levered peers'),
('supply_chain_cost_rise', 'high_import_material_pct', -1, 2.0, 'consensus', 'Import-heavy inputs → margin pressure directly'),
('supply_chain_cost_rise', 'low_gross_margin', -1, 1.5, 'moderate', 'Thin margins have no buffer for cost spikes'),
('supply_chain_cost_rise', 'domestic_supply_chain', 1, 1.5, 'moderate', 'Domestic sourcing insulates from import cost rises'),
('supply_chain_cost_rise', 'pricing_power', 1, 2.0, 'moderate', 'Pricing power allows pass-through of higher costs'),
('ai_capex_rising', 'high_cloud_datacenter_revenue_pct', 1, 3.0, 'consensus', 'Datacenter/cloud revenue surges with AI infra spend'),
('ai_capex_rising', 'high_ai_exposure', 1, 2.5, 'consensus', 'Direct AI product exposure captures capex wave'),
('usd_strengthening', 'high_overseas_revenue_pct', -1, 2.0, 'consensus', 'FX headwind on repatriated overseas earnings'),
('usd_strengthening', 'high_usd_debt', -1, 1.5, 'moderate', 'Non-US borrowers face heavier USD debt burden'),
('usd_strengthening', 'domestic_focused', 1, 1.0, 'situational', 'Purely domestic revenue insulated from FX drag')
ON CONFLICT (mechanism_type, affects_feature) DO NOTHING;
