"""Seed company_profiles with 50 companies. Uses INSERT OR REPLACE — safe to re-run."""

from db.init_db import get_connection, init_db

# (ticker, company_name, sector, listed_market, pricing_currency,
#  geo_exposure_json, revenue_segments_json, characteristics_json)
_COMPANIES = [
    # ── US Tech ─────────────────────────────────────────────────────────────
    (
        "NVDA", "NVIDIA Corporation", "Technology/Semiconductors", "NASDAQ", "USD",
        '{"US": 0.50, "Taiwan": 0.10, "Europe": 0.20, "Asia": 0.20}',
        '{"datacenter": 0.82, "gaming": 0.12, "automotive": 0.03, "professional_viz": 0.03}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": true, '
        '"high_ai_exposure": true, "semiconductor": true, "export_controlled": true, '
        '"pricing_power": true}',
    ),
    (
        "AAPL", "Apple Inc.", "Technology/Consumer Electronics", "NASDAQ", "USD",
        '{"US": 0.42, "China": 0.19, "Europe": 0.24, "Rest": 0.15}',
        '{"iphone": 0.52, "services": 0.22, "mac": 0.10, "wearables": 0.10, "ipad": 0.06}',
        '{"rate_sensitive": true, "ai_exposed": true, "china_exposed": true, '
        '"high_net_cash": true, "pricing_power": true, "high_overseas_revenue_pct": true, '
        '"consumer_discretionary": true}',
    ),
    (
        "TSLA", "Tesla Inc.", "Consumer Discretionary/Automotive", "NASDAQ", "USD",
        '{"US": 0.48, "China": 0.22, "Europe": 0.25, "Rest": 0.05}',
        '{"automotive": 0.84, "energy_storage": 0.08, "services": 0.08}',
        '{"rate_sensitive": true, "ai_exposed": true, "china_exposed": true, '
        '"high_overseas_revenue_pct": true, "ev": true}',
    ),
    (
        "MSFT", "Microsoft Corporation", "Technology/Software", "NASDAQ", "USD",
        '{"US": 0.52, "Europe": 0.25, "Asia": 0.15, "Rest": 0.08}',
        '{"cloud": 0.43, "productivity": 0.33, "gaming": 0.09, "linkedin": 0.07, "other": 0.08}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": true, '
        '"high_ai_exposure": true, "high_net_cash": true, "pricing_power": true, '
        '"high_overseas_revenue_pct": true, "cloud": true, "enterprise": true}',
    ),
    (
        "GOOGL", "Alphabet Inc.", "Technology/Internet", "NASDAQ", "USD",
        '{"US": 0.47, "Europe": 0.28, "Asia": 0.15, "Rest": 0.10}',
        '{"search_ads": 0.57, "youtube": 0.10, "cloud": 0.11, "other_bets": 0.01, "other": 0.21}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": true, '
        '"high_ai_exposure": true, "high_net_cash": true, "high_overseas_revenue_pct": true, '
        '"advertising": true, "cloud": true}',
    ),
    (
        "AMZN", "Amazon.com Inc.", "Consumer Discretionary/E-commerce", "NASDAQ", "USD",
        '{"US": 0.62, "Europe": 0.25, "Rest": 0.13}',
        '{"aws": 0.17, "retail_us": 0.44, "retail_intl": 0.24, "advertising": 0.08, "other": 0.07}',
        '{"rate_sensitive": true, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": true, '
        '"high_ai_exposure": true, "high_overseas_revenue_pct": true, '
        '"cloud": true, "consumer_cyclical": true}',
    ),
    (
        "META", "Meta Platforms Inc.", "Technology/Social Media", "NASDAQ", "USD",
        '{"US": 0.44, "Europe": 0.25, "Asia": 0.20, "Rest": 0.11}',
        '{"advertising": 0.97, "reality_labs": 0.02, "other": 0.01}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_ai_exposure": true, '
        '"high_net_cash": true, "high_overseas_revenue_pct": true, '
        '"advertising": true, "vr_ar": true}',
    ),
    (
        "NFLX", "Netflix Inc.", "Communication Services/Streaming", "NASDAQ", "USD",
        '{"US": 0.43, "Europe": 0.27, "LatAm": 0.15, "Asia": 0.10, "Rest": 0.05}',
        '{"streaming": 0.97, "advertising": 0.03}',
        '{"rate_sensitive": true, "ai_exposed": true, "high_overseas_revenue_pct": true, '
        '"high_debt_ratio": true, "consumer_discretionary": true}',
    ),
    (
        "AMD", "Advanced Micro Devices Inc.", "Technology/Semiconductors", "NASDAQ", "USD",
        '{"US": 0.30, "China": 0.22, "Europe": 0.18, "Asia": 0.30}',
        '{"datacenter": 0.52, "client": 0.25, "gaming": 0.12, "embedded": 0.11}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": true, '
        '"high_ai_exposure": true, "semiconductor": true, "export_controlled": true, '
        '"high_overseas_revenue_pct": true}',
    ),
    (
        "INTC", "Intel Corporation", "Technology/Semiconductors", "NASDAQ", "USD",
        '{"US": 0.28, "China": 0.26, "Europe": 0.20, "Taiwan": 0.08, "Rest": 0.18}',
        '{"client_computing": 0.52, "datacenter_ai": 0.27, "network": 0.08, "foundry": 0.08, "other": 0.05}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": true, '
        '"semiconductor": true, "export_controlled": true, "high_overseas_revenue_pct": true, '
        '"high_debt_ratio": true}',
    ),
    (
        "ORCL", "Oracle Corporation", "Technology/Software", "NYSE", "USD",
        '{"Americas": 0.54, "Europe": 0.24, "Asia": 0.22}',
        '{"cloud_services": 0.42, "license_support": 0.36, "license": 0.12, "hardware": 0.10}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": true, '
        '"high_overseas_revenue_pct": true, "enterprise": true, "pricing_power": true}',
    ),
    (
        "CRM", "Salesforce Inc.", "Technology/Software", "NYSE", "USD",
        '{"Americas": 0.65, "Europe": 0.21, "Asia": 0.14}',
        '{"sales_cloud": 0.25, "service_cloud": 0.23, "platform": 0.18, "marketing": 0.14, "other": 0.20}',
        '{"rate_sensitive": true, "ai_exposed": true, "high_ai_exposure": true, '
        '"high_overseas_revenue_pct": true, "high_debt_ratio": true, "saas": true, "enterprise": true}',
    ),
    (
        "ADBE", "Adobe Inc.", "Technology/Software", "NASDAQ", "USD",
        '{"Americas": 0.55, "Europe": 0.27, "Asia": 0.18}',
        '{"digital_media": 0.75, "digital_experience": 0.23, "publishing": 0.02}',
        '{"rate_sensitive": true, "ai_exposed": true, "high_ai_exposure": true, '
        '"high_net_cash": true, "high_overseas_revenue_pct": true, "saas": true, "pricing_power": true}',
    ),
    (
        "QCOM", "Qualcomm Inc.", "Technology/Semiconductors", "NASDAQ", "USD",
        '{"China": 0.66, "US": 0.12, "Europe": 0.10, "Rest": 0.12}',
        '{"handsets": 0.65, "automotive": 0.12, "iot": 0.12, "rf_front_end": 0.08, "other": 0.03}',
        '{"rate_sensitive": false, "ai_exposed": true, "semiconductor": true, '
        '"export_controlled": true, "high_overseas_revenue_pct": true, "china_exposed": true}',
    ),
    (
        "AVGO", "Broadcom Inc.", "Technology/Semiconductors", "NASDAQ", "USD",
        '{"US": 0.35, "China": 0.20, "Asia": 0.25, "Europe": 0.15, "Rest": 0.05}',
        '{"semiconductors": 0.60, "infrastructure_software": 0.40}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": true, '
        '"high_ai_exposure": true, "semiconductor": true, "high_debt_ratio": true, '
        '"high_overseas_revenue_pct": true, "export_controlled": true}',
    ),

    # ── US Financials ────────────────────────────────────────────────────────
    (
        "JPM", "JPMorgan Chase & Co.", "Financials/Banking", "NYSE", "USD",
        '{"US": 0.65, "Europe": 0.18, "Asia": 0.17}',
        '{"consumer_banking": 0.35, "investment_banking": 0.30, "commercial_banking": 0.15, "asset_management": 0.20}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": false, "banking": true, '
        '"yield_curve": true, "credit_cycle": true}',
    ),
    (
        "BAC", "Bank of America Corp.", "Financials/Banking", "NYSE", "USD",
        '{"US": 0.72, "Europe": 0.15, "Asia": 0.13}',
        '{"consumer_banking": 0.42, "global_markets": 0.22, "global_banking": 0.18, "wealth_management": 0.18}',
        '{"rate_sensitive": true, "high_debt_ratio": true, "banking": true, '
        '"yield_curve": true, "credit_cycle": true}',
    ),
    (
        "GS", "Goldman Sachs Group Inc.", "Financials/Investment Banking", "NYSE", "USD",
        '{"US": 0.55, "Europe": 0.25, "Asia": 0.20}',
        '{"investment_banking": 0.25, "global_markets": 0.45, "asset_management": 0.20, "consumer": 0.10}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": true, "banking": true, '
        '"investment_banking": true, "credit_cycle": true}',
    ),
    (
        "V", "Visa Inc.", "Financials/Payments", "NYSE", "USD",
        '{"US": 0.45, "Europe": 0.25, "Asia": 0.20, "Rest": 0.10}',
        '{"service_revenues": 0.38, "data_processing": 0.34, "international_transaction": 0.22, "other": 0.06}',
        '{"rate_sensitive": false, "high_net_cash": true, "high_overseas_revenue_pct": true, '
        '"pricing_power": true, "payments": true}',
    ),
    (
        "MA", "Mastercard Inc.", "Financials/Payments", "NYSE", "USD",
        '{"US": 0.33, "Europe": 0.28, "Asia": 0.22, "Rest": 0.17}',
        '{"domestic_assessments": 0.35, "cross_border": 0.32, "processing": 0.26, "other": 0.07}',
        '{"rate_sensitive": false, "high_net_cash": true, "high_overseas_revenue_pct": true, '
        '"pricing_power": true, "payments": true, "high_usd_debt": false}',
    ),

    # ── US Energy & Industrials ──────────────────────────────────────────────
    (
        "XOM", "Exxon Mobil Corporation", "Energy/Oil & Gas", "NYSE", "USD",
        '{"US": 0.35, "Europe": 0.10, "Asia": 0.25, "MiddleEast": 0.15, "Rest": 0.15}',
        '{"upstream": 0.55, "downstream": 0.30, "chemicals": 0.15}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "domestic_supply_chain": false, '
        '"high_debt_ratio": false, "strong_fcf": true, "energy": true, "commodity": true}',
    ),
    (
        "CVX", "Chevron Corporation", "Energy/Oil & Gas", "NYSE", "USD",
        '{"US": 0.40, "Asia": 0.25, "Australia": 0.15, "Africa": 0.10, "Rest": 0.10}',
        '{"upstream": 0.65, "downstream": 0.30, "chemicals": 0.05}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "domestic_supply_chain": false, '
        '"strong_fcf": true, "high_net_cash": false, "energy": true, "commodity": true}',
    ),
    (
        "CAT", "Caterpillar Inc.", "Industrials/Machinery", "NYSE", "USD",
        '{"US": 0.42, "EAME": 0.33, "AsiaPacific": 0.15, "LatAm": 0.10}',
        '{"construction": 0.45, "resource_industries": 0.25, "energy_transportation": 0.25, "financial": 0.05}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": true, "high_import_material_pct": true, '
        '"pricing_power": true, "industrial_cyclical": true}',
    ),
    (
        "BA", "Boeing Company", "Industrials/Aerospace & Defense", "NYSE", "USD",
        '{"US": 0.58, "Europe": 0.20, "Asia": 0.15, "Rest": 0.07}',
        '{"commercial_airplanes": 0.55, "defense": 0.28, "global_services": 0.17}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": true, "high_debt_ratio": true, '
        '"domestic_supply_chain": true, "aerospace_defense": true}',
    ),
    (
        "GE", "GE Aerospace", "Industrials/Aerospace", "NYSE", "USD",
        '{"US": 0.45, "Europe": 0.25, "Asia": 0.20, "Rest": 0.10}',
        '{"commercial_engines": 0.55, "defense_engines": 0.20, "services": 0.25}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "strong_fcf": true, '
        '"pricing_power": true, "aerospace_defense": true}',
    ),

    # ── US Healthcare ────────────────────────────────────────────────────────
    (
        "UNH", "UnitedHealth Group Inc.", "Healthcare/Insurance", "NYSE", "USD",
        '{"US": 0.93, "International": 0.07}',
        '{"unitedhealth_insurance": 0.55, "optum_health": 0.25, "optum_rx": 0.15, "optum_insight": 0.05}',
        '{"rate_sensitive": false, "domestic_focused": true, "pricing_power": true, '
        '"high_debt_ratio": true, "healthcare_insurance": true}',
    ),
    (
        "JNJ", "Johnson & Johnson", "Healthcare/Pharma & Devices", "NYSE", "USD",
        '{"US": 0.48, "Europe": 0.27, "Asia": 0.14, "Rest": 0.11}',
        '{"medtech": 0.55, "pharma": 0.45}',
        '{"rate_sensitive": false, "high_net_cash": true, "high_overseas_revenue_pct": true, '
        '"pricing_power": true, "strong_fcf": true, "pharma": true, "medtech": true}',
    ),
    (
        "PFE", "Pfizer Inc.", "Healthcare/Pharmaceuticals", "NYSE", "USD",
        '{"US": 0.42, "Europe": 0.32, "Asia": 0.14, "Rest": 0.12}',
        '{"oncology": 0.28, "internal_medicine": 0.22, "vaccines": 0.18, "hospital": 0.15, "other": 0.17}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "high_debt_ratio": true, '
        '"pricing_power": true, "pharma": true}',
    ),
    (
        "LLY", "Eli Lilly and Company", "Healthcare/Pharmaceuticals", "NYSE", "USD",
        '{"US": 0.48, "Europe": 0.28, "Japan": 0.07, "Rest": 0.17}',
        '{"diabetes": 0.40, "obesity": 0.25, "oncology": 0.15, "immunology": 0.12, "other": 0.08}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "high_net_cash": false, '
        '"pricing_power": true, "strong_fcf": true, "pharma": true, "high_forward_pe": true}',
    ),

    # ── US Consumer ──────────────────────────────────────────────────────────
    (
        "WMT", "Walmart Inc.", "Consumer Staples/Retail", "NYSE", "USD",
        '{"US": 0.70, "Mexico": 0.12, "China": 0.05, "Rest": 0.13}',
        '{"us_walmart": 0.68, "sams_club": 0.12, "international": 0.20}',
        '{"rate_sensitive": false, "domestic_focused": true, "high_import_material_pct": true, '
        '"pricing_power": false, "domestic_supply_chain": false, "consumer_staples": true}',
    ),
    (
        "COST", "Costco Wholesale Corporation", "Consumer Staples/Retail", "NYSE", "USD",
        '{"US": 0.73, "Canada": 0.13, "International": 0.14}',
        '{"merchandise": 0.85, "membership_fees": 0.02, "other": 0.13}',
        '{"rate_sensitive": false, "domestic_focused": true, "high_import_material_pct": true, '
        '"pricing_power": true, "strong_fcf": true, "consumer_staples": true}',
    ),
    (
        "MCD", "McDonald's Corporation", "Consumer Discretionary/Restaurants", "NYSE", "USD",
        '{"US": 0.40, "Europe": 0.30, "LatAm": 0.10, "Asia": 0.15, "Rest": 0.05}',
        '{"us_company_restaurants": 0.25, "international_operated": 0.55, "developmental_licensed": 0.20}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": true, "high_debt_ratio": true, '
        '"pricing_power": true, "strong_fcf": true, "restaurants": true}',
    ),
    (
        "NKE", "Nike Inc.", "Consumer Discretionary/Apparel", "NYSE", "USD",
        '{"North_America": 0.42, "Europe": 0.26, "China": 0.15, "Asia_Other": 0.10, "LatAm": 0.07}',
        '{"footwear": 0.65, "apparel": 0.29, "equipment": 0.06}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": true, "high_import_material_pct": true, '
        '"china_exposed": true, "pricing_power": true, "consumer_discretionary": true}',
    ),

    # ── Global ───────────────────────────────────────────────────────────────
    (
        "TSM", "Taiwan Semiconductor Manufacturing", "Technology/Semiconductors", "NYSE", "USD",
        '{"Taiwan": 0.80, "Asia": 0.15, "US": 0.05}',
        '{"advanced_node": 0.53, "specialty": 0.30, "mature_node": 0.17}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": true, '
        '"high_ai_exposure": true, "semiconductor": true, "geopolitical_risk": true, '
        '"export_controlled": true, "high_usd_debt": false}',
    ),
    (
        "ASML", "ASML Holding N.V.", "Technology/Semiconductor Equipment", "NASDAQ", "EUR",
        '{"Netherlands": 0.10, "Taiwan": 0.35, "Korea": 0.25, "US": 0.15, "China": 0.12, "Rest": 0.03}',
        '{"euv_systems": 0.55, "deep_uv_systems": 0.28, "metrology_inspection": 0.10, "services": 0.07}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_ai_exposure": true, '
        '"semiconductor": true, "export_controlled": true, "high_overseas_revenue_pct": true, '
        '"pricing_power": true, "high_forward_pe": true, "high_usd_debt": false}',
    ),
    (
        "BABA", "Alibaba Group Holding Ltd.", "Technology/E-commerce", "NYSE", "USD",
        '{"China": 0.72, "International": 0.20, "Rest": 0.08}',
        '{"china_commerce": 0.60, "cloud": 0.10, "digital_media": 0.08, "logistics": 0.12, "other": 0.10}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_ai_exposure": true, '
        '"china_exposed": true, "high_usd_debt": true, "regulatory_risk": true}',
    ),
    (
        "TCEHY", "Tencent Holdings Ltd.", "Technology/Internet", "OTC", "USD",
        '{"China": 0.88, "International": 0.12}',
        '{"value_added_services": 0.52, "marketing_services": 0.18, "fintech_business": 0.30}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_ai_exposure": true, '
        '"china_exposed": true, "regulatory_risk": true, "domestic_focused": true}',
    ),
    (
        "SONY", "Sony Group Corporation", "Technology/Consumer Electronics", "NYSE", "USD",
        '{"Japan": 0.25, "US": 0.30, "Europe": 0.25, "Asia": 0.15, "Rest": 0.05}',
        '{"gaming_network": 0.30, "electronics": 0.20, "entertainment": 0.25, "financial_services": 0.15, "other": 0.10}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "ai_exposed": true, '
        '"consumer_discretionary": true}',
    ),
    (
        "LVMH", "LVMH Moet Hennessy Louis Vuitton", "Consumer Discretionary/Luxury", "OTC", "EUR",
        '{"Asia": 0.30, "US": 0.26, "Europe": 0.27, "Japan": 0.08, "Rest": 0.09}',
        '{"fashion_leather": 0.47, "wines_spirits": 0.10, "perfumes_cosmetics": 0.11, "watches_jewelry": 0.13, "selective_retailing": 0.19}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": true, "pricing_power": true, '
        '"strong_fcf": true, "high_net_cash": false, "luxury": true, "high_forward_pe": true}',
    ),
    (
        "SAP", "SAP SE", "Technology/Enterprise Software", "NYSE", "EUR",
        '{"Europe": 0.40, "Americas": 0.35, "Asia": 0.25}',
        '{"cloud_software": 0.45, "software_support": 0.35, "services": 0.20}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_ai_exposure": true, '
        '"high_overseas_revenue_pct": true, "pricing_power": true, "enterprise": true, "saas": true}',
    ),
    (
        "HSBC", "HSBC Holdings plc", "Financials/Banking", "NYSE", "USD",
        '{"Asia": 0.55, "Europe": 0.25, "MiddleEast": 0.10, "Americas": 0.10}',
        '{"wealth_personal_banking": 0.40, "commercial_banking": 0.30, "global_banking_markets": 0.30}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": true, "high_usd_debt": true, '
        '"banking": true, "yield_curve": true, "china_exposed": true}',
    ),
    (
        "TM", "Toyota Motor Corporation", "Consumer Discretionary/Automotive", "NYSE", "USD",
        '{"Japan": 0.25, "North_America": 0.30, "Europe": 0.12, "Asia": 0.20, "Rest": 0.13}',
        '{"vehicles": 0.90, "financial_services": 0.08, "other": 0.02}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": true, "high_import_material_pct": false, '
        '"domestic_supply_chain": true, "ev": true, "pricing_power": true}',
    ),
    (
        "SHEL", "Shell plc", "Energy/Oil & Gas", "NYSE", "USD",
        '{"Europe": 0.25, "Asia": 0.35, "Americas": 0.15, "Africa": 0.10, "Rest": 0.15}',
        '{"integrated_gas": 0.35, "upstream": 0.30, "marketing": 0.25, "chemicals": 0.10}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "strong_fcf": true, '
        '"high_usd_debt": true, "energy": true, "commodity": true}',
    ),

    # ── Additional coverage fillers to reach 50 ──────────────────────────────
    (
        "BRKB", "Berkshire Hathaway Inc. (Class B)", "Financials/Conglomerate", "NYSE", "USD",
        '{"US": 0.87, "International": 0.13}',
        '{"insurance": 0.28, "railroad": 0.14, "utilities": 0.10, "manufacturing": 0.20, "equities": 0.28}',
        '{"rate_sensitive": true, "high_net_cash": true, "strong_fcf": true, '
        '"insurance": true, "value": true, "conglomerate": true}',
    ),
    (
        "LMT", "Lockheed Martin Corporation", "Industrials/Aerospace & Defense", "NYSE", "USD",
        '{"US": 0.75, "International": 0.25}',
        '{"aeronautics": 0.40, "missiles_fire_control": 0.17, "rotary_mission_systems": 0.25, "space": 0.18}',
        '{"rate_sensitive": false, "domestic_focused": false, "domestic_supply_chain": true, '
        '"pricing_power": true, "strong_fcf": true, "aerospace_defense": true}',
    ),
    (
        "PG", "Procter & Gamble Co.", "Consumer Staples/Personal Care", "NYSE", "USD",
        '{"North_America": 0.44, "Europe": 0.23, "Asia": 0.18, "LatAm": 0.09, "IMEA": 0.06}',
        '{"fabric_home_care": 0.35, "baby_feminine": 0.22, "beauty": 0.18, "health_care": 0.14, "grooming": 0.11}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "pricing_power": true, '
        '"strong_fcf": true, "high_net_cash": false, "consumer_staples": true}',
    ),
    (
        "KO", "Coca-Cola Company", "Consumer Staples/Beverages", "NYSE", "USD",
        '{"North_America": 0.35, "Europe": 0.22, "Asia": 0.22, "LatAm": 0.12, "Africa_MiddleEast": 0.09}',
        '{"sparkling_beverages": 0.70, "still_beverages": 0.20, "other": 0.10}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "pricing_power": true, '
        '"strong_fcf": true, "high_debt_ratio": true, "consumer_staples": true}',
    ),
    (
        "DIS", "Walt Disney Company", "Communication Services/Entertainment", "NYSE", "USD",
        '{"US": 0.72, "International": 0.28}',
        '{"entertainment": 0.45, "sports": 0.35, "experiences": 0.20}',
        '{"rate_sensitive": true, "high_overseas_revenue_pct": false, "high_debt_ratio": true, '
        '"ai_exposed": true, "consumer_discretionary": true}',
    ),
    (
        "ABBV", "AbbVie Inc.", "Healthcare/Pharmaceuticals", "NYSE", "USD",
        '{"US": 0.62, "Europe": 0.22, "Rest": 0.16}',
        '{"immunology": 0.50, "hematology_oncology": 0.25, "neuroscience": 0.12, "other": 0.13}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "high_debt_ratio": true, '
        '"pricing_power": true, "strong_fcf": true, "pharma": true}',
    ),
    (
        "NEE", "NextEra Energy Inc.", "Utilities/Renewable Energy", "NYSE", "USD",
        '{"US": 0.95, "Canada": 0.05}',
        '{"florida_power_light": 0.60, "next_era_energy_resources": 0.38, "other": 0.02}',
        '{"rate_sensitive": true, "domestic_focused": true, "high_debt_ratio": true, '
        '"high_forward_pe": true, "utilities": true, "renewables": true}',
    ),
    (
        "SPGI", "S&P Global Inc.", "Financials/Financial Services", "NYSE", "USD",
        '{"US": 0.55, "Europe": 0.28, "Asia": 0.12, "Rest": 0.05}',
        '{"market_intelligence": 0.30, "ratings": 0.35, "commodity_insights": 0.18, "indices": 0.17}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "high_net_cash": false, '
        '"pricing_power": true, "strong_fcf": true, "financial_services": true}',
    ),
    (
        "AMAT", "Applied Materials Inc.", "Technology/Semiconductor Equipment", "NASDAQ", "USD",
        '{"US": 0.15, "China": 0.30, "Taiwan": 0.20, "Korea": 0.18, "Japan": 0.10, "Rest": 0.07}',
        '{"semiconductor_systems": 0.75, "applied_global_services": 0.22, "display": 0.03}',
        '{"rate_sensitive": false, "ai_exposed": true, "high_cloud_datacenter_revenue_pct": false, '
        '"semiconductor": true, "export_controlled": true, "high_overseas_revenue_pct": true, '
        '"china_exposed": true}',
    ),
    (
        "RTX", "RTX Corporation", "Industrials/Aerospace & Defense", "NYSE", "USD",
        '{"US": 0.65, "International": 0.35}',
        '{"pratt_whitney": 0.40, "raytheon": 0.35, "collins_aerospace": 0.25}',
        '{"rate_sensitive": false, "high_overseas_revenue_pct": true, "domestic_supply_chain": true, '
        '"high_debt_ratio": true, "pricing_power": true, "aerospace_defense": true}',
    ),
]


def seed():
    init_db()
    with get_connection() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO company_profiles
               (ticker, company_name, sector, listed_market, pricing_currency,
                geo_exposure_json, revenue_segments_json, characteristics_json)
               VALUES (?,?,?,?,?,?,?,?)""",
            _COMPANIES,
        )
        conn.commit()
        print(f"Upserted {len(_COMPANIES)} company profiles.")


if __name__ == "__main__":
    seed()
