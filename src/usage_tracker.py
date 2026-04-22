"""
Monthly expose usage tracking per user.
Stored in logs/usage/YYYY-MM.json (or /tmp/usage/ on Vercel).
"""
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_on_vercel = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
_USAGE_DIR = "/tmp/usage" if _on_vercel else os.path.join(
    os.path.dirname(__file__), "..", "logs", "usage"
)


def _usage_path() -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return os.path.join(_USAGE_DIR, f"{month}.json")


def _load() -> dict:
    path = _usage_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(_USAGE_DIR, exist_ok=True)
    with open(_usage_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_usage(username: str) -> int:
    return _load().get(username, 0)


def increment(username: str) -> int:
    data = _load()
    data[username] = data.get(username, 0) + 1
    _save(data)
    logger.info("Usage: %s → %d this month", username, data[username])
    return data[username]


def check_limit(username: str, plan_key: str) -> tuple:
    from .plans import check_expose_limit
    used = get_usage(username)
    return check_expose_limit(plan_key, used)


def get_all_usage() -> dict:
    return _load()
