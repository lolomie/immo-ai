"""
Plan definitions for Immo AI.
Used for feature gating, limit enforcement, and pricing display.
"""

PLANS: dict = {
    "admin": {
        "name": "Admin",
        "setup_fee": 0,
        "monthly_price": 0,
        "monthly_expose_limit": 999999,
        "max_users": 999999,
        "priority": 99,
        "features": {
            "generator":          True,
            "sheets_integration": True,
            "review_interface":   True,
            "calendar":           True,
            "reminders":          True,
            "whatsapp":           True,
            "multi_user":         True,
            "custom_tone":        True,
            "priority_support":   True,
            "drive_export":       True,
            "email_notifications":True,
        },
    },
    "starter": {
        "name": "Starter",
        "setup_fee": 299,
        "monthly_price": 49,
        "monthly_expose_limit": 30,
        "max_users": 1,
        "priority": 1,
        "features": {
            "generator":          True,
            "sheets_integration": True,
            "review_interface":   True,
            "calendar":           False,
            "reminders":          False,
            "whatsapp":           False,
            "multi_user":         False,
            "custom_tone":        False,
            "priority_support":   False,
            "drive_export":       True,
            "email_notifications":True,
        },
    },
    "pro": {
        "name": "Pro",
        "setup_fee": 499,
        "monthly_price": 99,
        "monthly_expose_limit": 60,
        "max_users": 1,
        "priority": 2,
        "features": {
            "generator":          True,
            "sheets_integration": True,
            "review_interface":   True,
            "calendar":           True,
            "reminders":          True,
            "whatsapp":           True,
            "multi_user":         False,
            "custom_tone":        False,
            "priority_support":   False,
            "drive_export":       True,
            "email_notifications":True,
        },
    },
    "business": {
        "name": "Business",
        "setup_fee": 999,
        "monthly_price": 199,
        "monthly_expose_limit": 150,
        "max_users": 5,
        "priority": 3,
        "features": {
            "generator":          True,
            "sheets_integration": True,
            "review_interface":   True,
            "calendar":           True,
            "reminders":          True,
            "whatsapp":           True,
            "multi_user":         True,
            "custom_tone":        True,
            "priority_support":   True,
            "drive_export":       True,
            "email_notifications":True,
        },
    },
}

DEFAULT_PLAN = "pro"


def get_plan(plan_key: str) -> dict:
    return PLANS.get(plan_key.lower(), PLANS[DEFAULT_PLAN])


def has_feature(plan_key: str, feature: str) -> bool:
    if plan_key == "admin":
        return True
    plan = get_plan(plan_key)
    return bool(plan["features"].get(feature, False))


def get_monthly_limit(plan_key: str) -> int:
    if plan_key == "admin":
        return 999999
    return get_plan(plan_key)["monthly_expose_limit"]


def check_expose_limit(plan_key: str, used_this_month: int) -> tuple[bool, str]:
    """
    Returns (allowed: bool, reason: str).
    Plug in real usage counting when billing is implemented.
    """
    limit = get_monthly_limit(plan_key)
    if used_this_month >= limit:
        return False, (
            f"Monatliches Limit von {limit} Exposés erreicht "
            f"(Plan: {get_plan(plan_key)['name']}). "
            "Bitte upgraden oder nächsten Monat abwarten."
        )
    return True, ""
