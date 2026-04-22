"""
Monthly exposé usage tracking per user — stored in DB.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def get_usage(username: str) -> int:
    from src.db import fetchone
    row = fetchone(
        "SELECT count FROM usage WHERE username = ? AND year_month = ?",
        (username, _month()),
    )
    return (row or {}).get("count", 0)


def increment(username: str) -> int:
    from src.db import execute, fetchone
    month = _month()
    # Upsert: increment if exists, insert if not
    existing = fetchone(
        "SELECT count FROM usage WHERE username = ? AND year_month = ?",
        (username, month),
    )
    if existing:
        execute(
            "UPDATE usage SET count = count + 1 WHERE username = ? AND year_month = ?",
            (username, month),
        )
    else:
        execute(
            "INSERT INTO usage (username, year_month, count) VALUES (?, ?, 1)",
            (username, month),
        )
    new_count = get_usage(username)
    logger.info("Usage: %s → %d this month", username, new_count)
    return new_count


def check_limit(username: str, plan_key: str) -> tuple:
    from .plans import check_expose_limit
    return check_expose_limit(plan_key, get_usage(username))


def get_all_usage() -> dict:
    from src.db import fetchall
    rows = fetchall(
        "SELECT username, count FROM usage WHERE year_month = ?",
        (_month(),),
    )
    return {r["username"]: r["count"] for r in rows}
