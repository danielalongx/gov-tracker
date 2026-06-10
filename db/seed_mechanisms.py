"""Seed mechanism_rules with the initial set of macro/rate mechanisms."""

from db.init_db import get_connection, init_db

_RULES = [
    # mechanism_type, affects_feature, direction, base_strength, confidence, notes
    # rate_high — 利率维持高位
    ("rate_high", "high_debt_ratio",         -1, 2.5, "consensus",   "High rates → debt service burden kills leveraged names"),
    ("rate_high", "low_interest_coverage",   -1, 2.0, "consensus",   "Thin coverage crushed when rates stay elevated"),
    ("rate_high", "high_forward_pe",         -1, 1.5, "moderate",    "Duration compression: high multiples de-rate"),
    ("rate_high", "high_net_cash",           +1, 2.0, "consensus",   "Cash earns more; net-cash companies benefit directly"),
    ("rate_high", "strong_fcf",              +1, 1.5, "moderate",    "Strong FCF companies self-fund without expensive debt"),

    # rate_falling — 利率下行
    ("rate_falling", "high_debt_ratio",      +1, 2.0, "consensus",   "Rate relief eases debt service for leveraged names"),
    ("rate_falling", "high_forward_pe",      +1, 1.5, "moderate",    "Duration expansion: growth multiples re-rate upward"),
    ("rate_falling", "high_net_cash",        -1, 0.5, "situational", "Cash earns less; relative disadvantage vs levered peers"),

    # supply_chain_cost_rise — 供应链成本上升
    ("supply_chain_cost_rise", "high_import_material_pct", -1, 2.0, "consensus", "Import-heavy inputs → margin pressure directly"),
    ("supply_chain_cost_rise", "low_gross_margin",         -1, 1.5, "moderate",  "Thin margins have no buffer for cost spikes"),
    ("supply_chain_cost_rise", "domestic_supply_chain",    +1, 1.5, "moderate",  "Domestic sourcing insulates from import cost rises"),
    ("supply_chain_cost_rise", "pricing_power",            +1, 2.0, "moderate",  "Pricing power allows pass-through of higher costs"),

    # ai_capex_rising — AI基建需求上升
    ("ai_capex_rising", "high_cloud_datacenter_revenue_pct", +1, 3.0, "consensus", "Datacenter/cloud revenue surges with AI infra spend"),
    ("ai_capex_rising", "high_ai_exposure",                  +1, 2.5, "consensus", "Direct AI product exposure captures capex wave"),

    # usd_strengthening — 美元走强
    ("usd_strengthening", "high_overseas_revenue_pct", -1, 2.0, "consensus",   "FX headwind on repatriated overseas earnings"),
    ("usd_strengthening", "high_usd_debt",             -1, 1.5, "moderate",    "Non-US borrowers face heavier USD debt burden"),
    ("usd_strengthening", "domestic_focused",          +1, 1.0, "situational", "Purely domestic revenue insulated from FX drag"),
]


def seed():
    init_db()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM mechanism_rules").fetchone()[0]
        if count > 0:
            print(f"Already seeded ({count} rows). Skipping.")
            return

        conn.executemany(
            """INSERT INTO mechanism_rules
               (mechanism_type, affects_feature, direction, base_strength, confidence, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            _RULES,
        )
        conn.commit()
        print(f"Seeded {len(_RULES)} mechanism rules.")


if __name__ == "__main__":
    seed()
