"""
Stripe payment integration for Signal platform subscription tiers.

Setup:
1. Create a Stripe account at stripe.com
2. Get your API keys from Stripe Dashboard → Developers → API keys
3. Add to .env: STRIPE_SECRET_KEY=sk_live_... (or sk_test_... for testing)
4. Create products/prices in Stripe Dashboard or run setup_stripe_products()
5. Add STRIPE_WEBHOOK_SECRET=whsec_... from Stripe Dashboard → Webhooks

Tiers:
- free:    $0/month  — 3 stocks, fixed weights, 1x daily digest, 4hr delay
- pro:     $9.99/mo  — 20 stocks, custom weights, 3x daily, real-time
- analyst: $29.99/mo — unlimited, full API, CSV export, weekly reports
"""
import os
import json
import hashlib
import hmac
from datetime import datetime
from typing import Optional

try:
    import stripe
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_AVAILABLE = bool(stripe.api_key)
except ImportError:
    STRIPE_AVAILABLE = False
    stripe = None  # type: ignore

TIER_LIMITS = {
    "free": {
        "max_stocks": 3,
        "custom_weights": False,
        "digest_count": 1,
        "delay_hours": 4,
        "api_access": False,
        "csv_export": False,
        "price_monthly": 0,
    },
    "pro": {
        "max_stocks": 20,
        "custom_weights": True,
        "digest_count": 3,
        "delay_hours": 0,
        "api_access": False,
        "csv_export": False,
        "price_monthly": 9.99,
    },
    "analyst": {
        "max_stocks": None,  # unlimited
        "custom_weights": True,
        "digest_count": 3,
        "delay_hours": 0,
        "api_access": True,
        "csv_export": True,
        "price_monthly": 29.99,
    },
}


def get_user_tier(user_id: int, conn) -> str:
    """Return the active subscription tier for a user. Defaults to 'free'."""
    q = "?" if not getattr(conn, "_is_postgres", False) else "%s"
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT tier, expires_at FROM subscriptions WHERE user_id = {q} ORDER BY expires_at DESC LIMIT 1",
            (user_id,)
        )
        row = cur.fetchone()
        if row:
            tier = row[0] if isinstance(row, (list, tuple)) else row["tier"]
            expires = row[1] if isinstance(row, (list, tuple)) else row["expires_at"]
            if expires is None or datetime.fromisoformat(str(expires)) > datetime.utcnow():
                return tier
    except Exception:
        pass
    return "free"


def check_limit(user_id: int, conn, action: str) -> tuple[bool, str]:
    """
    Check if user is allowed to perform an action.
    Returns (allowed: bool, message: str)
    """
    tier = get_user_tier(user_id, conn)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

    if action == "add_stock":
        max_stocks = limits["max_stocks"]
        if max_stocks is None:
            return True, ""
        q = "?" if not getattr(conn, "_is_postgres", False) else "%s"
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM user_watchlist WHERE user_id = {q}", (user_id,))
        count = cur.fetchone()[0]
        if count >= max_stocks:
            return False, f"Free 层最多追踪 {max_stocks} 只股票。升级到 Pro 可追踪 20 只。"
        return True, ""

    if action == "custom_weights":
        if not limits["custom_weights"]:
            return False, "自定义维度权重需要 Pro 或以上订阅。"
        return True, ""

    if action == "api_access":
        if not limits["api_access"]:
            return False, "API 访问需要 Analyst 订阅。"
        return True, ""

    return True, ""


def create_checkout_session(user_id: int, tier: str, success_url: str, cancel_url: str) -> Optional[str]:
    """
    Create a Stripe Checkout session for upgrading to pro or analyst.
    Returns the checkout URL or None if Stripe is not configured.
    """
    if not STRIPE_AVAILABLE:
        return None

    price_map = {
        "pro": os.getenv("STRIPE_PRICE_PRO", ""),
        "analyst": os.getenv("STRIPE_PRICE_ANALYST", ""),
    }
    price_id = price_map.get(tier)
    if not price_id:
        return None

    try:
        session = stripe.checkout.Session.create(  # type: ignore
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user_id), "tier": tier},
        )
        return session.url
    except Exception as e:
        print(f"Stripe error: {e}")
        return None


def handle_webhook(payload: bytes, sig_header: str, conn) -> dict:
    """
    Process a Stripe webhook event.
    Called by the FastAPI /stripe/webhook endpoint.
    """
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not STRIPE_AVAILABLE or not secret:
        return {"status": "stripe not configured"}

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)  # type: ignore
    except Exception as e:
        return {"status": "invalid", "error": str(e)}

    if event["type"] == "checkout.session.completed":
        data = event["data"]["object"]
        user_id = int(data["metadata"].get("user_id", 0))
        tier = data["metadata"].get("tier", "pro")
        _activate_subscription(user_id, tier, data["subscription"], conn)

    elif event["type"] in ("customer.subscription.deleted", "customer.subscription.updated"):
        sub = event["data"]["object"]
        status = sub.get("status")
        if status in ("canceled", "unpaid", "past_due"):
            _deactivate_subscription(sub["id"], conn)

    return {"status": "ok"}


def _activate_subscription(user_id: int, tier: str, stripe_sub_id: str, conn):
    q = "?" if not getattr(conn, "_is_postgres", False) else "%s"
    cur = conn.cursor()
    cur.execute(
        f"INSERT OR REPLACE INTO subscriptions (user_id, tier, stripe_sub_id, activated_at) VALUES ({q},{q},{q},{q})",
        (user_id, tier, stripe_sub_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    print(f"Activated {tier} for user {user_id}")


def _deactivate_subscription(stripe_sub_id: str, conn):
    q = "?" if not getattr(conn, "_is_postgres", False) else "%s"
    cur = conn.cursor()
    cur.execute(
        f"UPDATE subscriptions SET tier = 'free', expires_at = {q} WHERE stripe_sub_id = {q}",
        (datetime.utcnow().isoformat(), stripe_sub_id)
    )
    conn.commit()
