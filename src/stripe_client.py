"""
Stripe payment infrastructure.

Three operating modes, controlled by STRIPE_MODE in .env:

  placeholder  (default) — No Stripe calls. Simulates the full flow locally.
                            Use this until you're ready to go live.
  test         — Connects to Stripe's sandbox API with STRIPE_TEST_* keys.
                 Real Stripe API, fake money. Use test card 4242 4242 4242 4242.
  live         — Connects to Stripe's production API with STRIPE_LIVE_* keys.
                 Only set this when you're ready to charge real money.

To go live: set STRIPE_MODE=live and fill in STRIPE_LIVE_* vars in .env.
No code changes required.
"""
import hashlib
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Mode & key resolution ─────────────────────────────────────────────────────

STRIPE_MODE: str = os.environ.get("STRIPE_MODE", "placeholder").lower()

def _secret_key() -> str:
    if STRIPE_MODE == "live":
        k = os.environ.get("STRIPE_LIVE_SECRET_KEY", "")
        if not k:
            raise EnvironmentError("STRIPE_LIVE_SECRET_KEY not set. Add it to .env.")
        return k
    if STRIPE_MODE == "test":
        k = os.environ.get("STRIPE_TEST_SECRET_KEY", "")
        if not k:
            raise EnvironmentError("STRIPE_TEST_SECRET_KEY not set. Add it to .env.")
        return k
    return ""  # placeholder mode — no key needed


def _publishable_key() -> str:
    if STRIPE_MODE == "live":
        return os.environ.get("STRIPE_LIVE_PUBLISHABLE_KEY", "")
    if STRIPE_MODE == "test":
        return os.environ.get("STRIPE_TEST_PUBLISHABLE_KEY", "")
    return "pk_placeholder_immoai"


def _webhook_secret() -> str:
    if STRIPE_MODE == "live":
        return os.environ.get("STRIPE_LIVE_WEBHOOK_SECRET", "")
    if STRIPE_MODE == "test":
        return os.environ.get("STRIPE_TEST_WEBHOOK_SECRET", "")
    return ""


def is_placeholder() -> bool:
    return STRIPE_MODE == "placeholder"


def is_live() -> bool:
    return STRIPE_MODE == "live"


# ── Price ID mapping ──────────────────────────────────────────────────────────
# Replace these with your actual Stripe Price IDs from the Stripe dashboard.
# Test IDs: dashboard.stripe.com → Products → (create product) → copy Price ID
# Format:   price_test_XXXXXXXXXX  (test)  /  price_XXXXXXXXXX  (live)

PRICE_IDS: dict[str, dict[str, str]] = {
    "test": {
        "starter":      os.environ.get("STRIPE_TEST_PRICE_STARTER",      "price_test_PLACEHOLDER_STARTER"),
        "pro":          os.environ.get("STRIPE_TEST_PRICE_PRO",           "price_test_PLACEHOLDER_PRO"),
        "business":     os.environ.get("STRIPE_TEST_PRICE_BUSINESS",      "price_test_PLACEHOLDER_BUSINESS"),
        "starter_year": os.environ.get("STRIPE_TEST_PRICE_STARTER_YEAR",  "price_test_PLACEHOLDER_STARTER_Y"),
        "pro_year":     os.environ.get("STRIPE_TEST_PRICE_PRO_YEAR",      "price_test_PLACEHOLDER_PRO_Y"),
        "business_year":os.environ.get("STRIPE_TEST_PRICE_BUSINESS_YEAR", "price_test_PLACEHOLDER_BUSINESS_Y"),
    },
    "live": {
        "starter":      os.environ.get("STRIPE_LIVE_PRICE_STARTER",      ""),
        "pro":          os.environ.get("STRIPE_LIVE_PRICE_PRO",           ""),
        "business":     os.environ.get("STRIPE_LIVE_PRICE_BUSINESS",      ""),
        "starter_year": os.environ.get("STRIPE_LIVE_PRICE_STARTER_YEAR",  ""),
        "pro_year":     os.environ.get("STRIPE_LIVE_PRICE_PRO_YEAR",      ""),
        "business_year":os.environ.get("STRIPE_LIVE_PRICE_BUSINESS_YEAR", ""),
    },
}


def get_price_id(plan_key: str, billing: str = "monthly") -> str:
    """Return the Stripe Price ID for a plan + billing period."""
    env = "live" if is_live() else "test"
    key = plan_key if billing == "monthly" else f"{plan_key}_year"
    return PRICE_IDS[env].get(key, "")


# ── Checkout session ──────────────────────────────────────────────────────────

def create_checkout_session(
    plan_key: str,
    billing: str,           # "monthly" | "annual"
    email: str,
    username: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    """
    Create a Stripe Checkout Session.

    Returns:
        {
          "session_id": str,
          "checkout_url": str,
          "mode": "placeholder" | "test" | "live",
        }

    In placeholder mode: returns a fake session that works locally.
    In test/live mode: creates a real Stripe session.
    """
    if is_placeholder():
        return _placeholder_checkout(plan_key, billing, email, username, success_url, cancel_url)

    import stripe
    stripe.api_key = _secret_key()

    price_id = get_price_id(plan_key, billing)
    if not price_id or "PLACEHOLDER" in price_id:
        raise ValueError(
            f"Stripe Price ID for plan='{plan_key}' billing='{billing}' not configured. "
            "Set STRIPE_TEST_PRICE_* in .env."
        )

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"username": username, "plan_key": plan_key, "billing": billing},
        subscription_data={
            "metadata": {"username": username, "plan_key": plan_key},
        },
        allow_promotion_codes=True,
    )
    logger.info("Stripe checkout session created: %s (plan=%s, mode=%s)", session.id, plan_key, STRIPE_MODE)
    return {"session_id": session.id, "checkout_url": session.url, "mode": STRIPE_MODE}


def _placeholder_checkout(
    plan_key: str, billing: str, email: str, username: str,
    success_url: str, cancel_url: str,
) -> dict:
    """Generate a deterministic fake session for placeholder mode."""
    raw = f"{username}:{plan_key}:{billing}:{int(time.time() // 60)}"
    fake_id = "cs_test_placeholder_" + hashlib.md5(raw.encode()).hexdigest()[:16]
    # Encode plan info into the success URL so the success handler can activate the plan
    import urllib.parse
    params = urllib.parse.urlencode({
        "session_id": fake_id,
        "plan": plan_key,
        "billing": billing,
    })
    checkout_url = f"/billing/placeholder-checkout?{params}&success_url={urllib.parse.quote(success_url)}&cancel_url={urllib.parse.quote(cancel_url)}"
    logger.info("Placeholder checkout created: %s (plan=%s)", fake_id, plan_key)
    return {"session_id": fake_id, "checkout_url": checkout_url, "mode": "placeholder"}


# ── Session verification ──────────────────────────────────────────────────────

def verify_checkout_session(session_id: str) -> dict:
    """
    Retrieve and verify a completed checkout session.
    Returns subscription details extracted from the session.
    """
    if is_placeholder() or session_id.startswith("cs_test_placeholder_"):
        return _verify_placeholder_session(session_id)

    import stripe
    stripe.api_key = _secret_key()

    session = stripe.checkout.Session.retrieve(
        session_id,
        expand=["subscription", "customer"],
    )
    if session.payment_status not in ("paid", "no_payment_required"):
        raise ValueError(f"Session not paid: status={session.payment_status}")

    sub = session.subscription
    return {
        "username":             session.metadata.get("username", ""),
        "plan_key":             session.metadata.get("plan_key", ""),
        "billing":              session.metadata.get("billing", "monthly"),
        "stripe_customer_id":   session.customer.id if hasattr(session.customer, "id") else str(session.customer),
        "stripe_subscription_id": sub.id if sub else "",
        "stripe_price_id":      sub.items.data[0].price.id if sub else "",
        "status":               "active",
        "current_period_end":   sub.current_period_end if sub else None,
    }


def _verify_placeholder_session(session_id: str) -> dict:
    """Return fake verified data for placeholder sessions."""
    return {
        "username":               "",   # filled in by route from session
        "plan_key":               "",   # filled in from query params
        "billing":                "monthly",
        "stripe_customer_id":     f"cus_placeholder_{session_id[-8:]}",
        "stripe_subscription_id": f"sub_placeholder_{session_id[-8:]}",
        "stripe_price_id":        "price_placeholder",
        "status":                 "active",
        "current_period_end":     int(time.time()) + 30 * 24 * 3600,
    }


# ── Webhook processing ────────────────────────────────────────────────────────

HANDLED_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
}


def verify_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Verify and parse a Stripe webhook event.
    Raises ValueError on invalid signature.
    """
    if is_placeholder():
        import json
        return json.loads(payload)

    import stripe
    stripe.api_key = _secret_key()
    secret = _webhook_secret()
    if not secret:
        raise ValueError("Webhook secret not configured (STRIPE_*_WEBHOOK_SECRET).")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
        return event
    except stripe.error.SignatureVerificationError as e:
        raise ValueError(f"Invalid webhook signature: {e}") from e


def handle_webhook_event(event: dict) -> dict:
    """
    Process a verified Stripe webhook event.
    Updates the subscriptions table accordingly.
    Returns {"action": str, "username": str, "status": str}.
    """
    event_type = event.get("type", "")
    if event_type not in HANDLED_EVENTS:
        return {"action": "ignored", "event_type": event_type}

    data   = event.get("data", {}).get("object", {})
    result = {"event_type": event_type, "action": "noop"}

    if event_type == "checkout.session.completed":
        result = _handle_checkout_completed(data)

    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        result = _handle_subscription_upsert(data)

    elif event_type == "customer.subscription.deleted":
        result = _handle_subscription_deleted(data)

    elif event_type == "invoice.payment_succeeded":
        result = _handle_payment_succeeded(data)

    elif event_type == "invoice.payment_failed":
        result = _handle_payment_failed(data)

    logger.info("Webhook handled: %s → %s", event_type, result)
    return result


def _handle_checkout_completed(session: dict) -> dict:
    from src.db import execute, fetchone
    username = (session.get("metadata") or {}).get("username", "")
    plan_key = (session.get("metadata") or {}).get("plan_key", "")
    if not username:
        return {"action": "skipped", "reason": "no username in metadata"}

    sub_id   = session.get("subscription", "")
    cus_id   = session.get("customer", "")

    _upsert_subscription(username, {
        "stripe_customer_id":     cus_id,
        "stripe_subscription_id": sub_id,
        "plan_key":               plan_key,
        "status":                 "active",
    })
    _sync_user_plan(username, plan_key)
    return {"action": "activated", "username": username, "plan_key": plan_key}


def _handle_subscription_upsert(sub: dict) -> dict:
    from src.db import fetchone
    username = (sub.get("metadata") or {}).get("username", "")
    sub_id   = sub.get("id", "")

    # Try to find username by subscription ID if not in metadata
    if not username and sub_id:
        row = fetchone("SELECT username FROM subscriptions WHERE stripe_subscription_id = ?", (sub_id,))
        if row:
            username = row["username"]
    if not username:
        return {"action": "skipped", "reason": "username not found"}

    plan_key = _price_to_plan(sub.get("items", {}).get("data", [{}])[0].get("price", {}).get("id", ""))
    status   = _map_stripe_status(sub.get("status", ""))

    _upsert_subscription(username, {
        "stripe_subscription_id": sub_id,
        "stripe_customer_id":     sub.get("customer", ""),
        "plan_key":               plan_key or "",
        "status":                 status,
        "current_period_end":     sub.get("current_period_end"),
        "cancel_at_period_end":   int(sub.get("cancel_at_period_end", False)),
    })
    if status == "active" and plan_key:
        _sync_user_plan(username, plan_key)
    return {"action": "subscription_updated", "username": username, "status": status}


def _handle_subscription_deleted(sub: dict) -> dict:
    sub_id = sub.get("id", "")
    from src.db import execute, fetchone
    row = fetchone("SELECT username FROM subscriptions WHERE stripe_subscription_id = ?", (sub_id,))
    if not row:
        return {"action": "skipped", "reason": "subscription not found"}
    username = row["username"]
    execute(
        "UPDATE subscriptions SET status='canceled', updated_at=datetime('now') WHERE stripe_subscription_id=?",
        (sub_id,),
    )
    execute("UPDATE users SET plan='starter', updated_at=datetime('now') WHERE username=?", (username,))
    return {"action": "canceled", "username": username}


def _handle_payment_succeeded(invoice: dict) -> dict:
    sub_id = invoice.get("subscription", "")
    if not sub_id:
        return {"action": "noop"}
    from src.db import execute, fetchone
    row = fetchone("SELECT username FROM subscriptions WHERE stripe_subscription_id = ?", (sub_id,))
    if row:
        execute(
            "UPDATE subscriptions SET status='active', updated_at=datetime('now') WHERE stripe_subscription_id=?",
            (sub_id,),
        )
    return {"action": "payment_succeeded", "subscription": sub_id}


def _handle_payment_failed(invoice: dict) -> dict:
    sub_id = invoice.get("subscription", "")
    if not sub_id:
        return {"action": "noop"}
    from src.db import execute, fetchone
    row = fetchone("SELECT username FROM subscriptions WHERE stripe_subscription_id = ?", (sub_id,))
    if row:
        execute(
            "UPDATE subscriptions SET status='past_due', updated_at=datetime('now') WHERE stripe_subscription_id=?",
            (sub_id,),
        )
    return {"action": "payment_failed", "subscription": sub_id}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _upsert_subscription(username: str, fields: dict) -> None:
    from src.db import fetchone, execute
    existing = fetchone("SELECT id FROM subscriptions WHERE username = ?", (username,))
    if existing:
        sets   = ", ".join(f"{k}=?" for k in fields)
        vals   = list(fields.values()) + [username]
        execute(f"UPDATE subscriptions SET {sets}, updated_at=datetime('now') WHERE username=?", vals)
    else:
        cols = ", ".join(["username"] + list(fields.keys()))
        phs  = ", ".join(["?"] * (len(fields) + 1))
        vals = [username] + list(fields.values())
        execute(f"INSERT INTO subscriptions ({cols}) VALUES ({phs})", vals)


def _sync_user_plan(username: str, plan_key: str) -> None:
    """Keep users.plan in sync with the active subscription."""
    if not plan_key:
        return
    from src.db import execute
    execute("UPDATE users SET plan=?, updated_at=datetime('now') WHERE username=?", (plan_key, username))


def _map_stripe_status(stripe_status: str) -> str:
    mapping = {
        "active":            "active",
        "trialing":          "trialing",
        "past_due":          "past_due",
        "canceled":          "canceled",
        "unpaid":            "failed",
        "incomplete":        "pending",
        "incomplete_expired":"failed",
        "paused":            "paused",
    }
    return mapping.get(stripe_status, "pending")


def _price_to_plan(price_id: str) -> str:
    """Reverse-map a Stripe Price ID back to our plan key."""
    env = "live" if is_live() else "test"
    for key, pid in PRICE_IDS[env].items():
        if pid and pid == price_id:
            # Strip _year suffix to get base plan key
            return key.replace("_year", "")
    return ""


# ── Customer portal ───────────────────────────────────────────────────────────

def create_portal_session(customer_id: str, return_url: str) -> str:
    """Return URL for Stripe Customer Portal (manage subscription/cancel)."""
    if is_placeholder():
        return f"/billing/portal-placeholder?return_url={return_url}"
    import stripe
    stripe.api_key = _secret_key()
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


# ── Public info ───────────────────────────────────────────────────────────────

def get_config() -> dict:
    """Return non-sensitive Stripe config for the frontend."""
    return {
        "mode":            STRIPE_MODE,
        "publishable_key": _publishable_key(),
        "is_placeholder":  is_placeholder(),
        "is_live":         is_live(),
    }
