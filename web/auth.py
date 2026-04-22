import json
import logging
import os
from functools import wraps

import bcrypt
from flask import redirect, session, url_for

logger = logging.getLogger(__name__)

# ── Primary admin ─────────────────────────────────────────────────────────────
_DEFAULT_HASH = b"$2b$12$98vol7EU./4uSdedSnTT7OCpXP0KZhBAj8OW8f.N.L/MSH/NnteP."
_STORED_HASH  = os.environ.get("ADMIN_PASSWORD_HASH", "").encode() or _DEFAULT_HASH
ADMIN_USER    = os.environ.get("ADMIN_USERNAME", "admin")

# ── Users file ────────────────────────────────────────────────────────────────
_on_vercel  = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
_USERS_FILE = "/tmp/users.json" if _on_vercel else os.path.join(
    os.path.dirname(__file__), "..", "config", "users.json"
)

# users.json format: {username: {hash: str, plan: str, phone: str}}
# backward compat: if value is a bare string → treat as hash, plan=starter


def _load_users() -> dict:
    try:
        if os.path.exists(_USERS_FILE):
            with open(_USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error("Failed to load users file: %s", e)
    return {}


def _save_users(users: dict) -> None:
    os.makedirs(os.path.dirname(_USERS_FILE), exist_ok=True)
    with open(_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def _get_user_record(username: str) -> dict:
    """Return normalised user record dict. Returns {} if not found."""
    users = _load_users()
    raw = users.get(username)
    if raw is None:
        return {}
    if isinstance(raw, str):
        return {"hash": raw, "plan": "starter", "phone": ""}
    return raw


# ── Credentials ───────────────────────────────────────────────────────────────

def check_credentials(username: str, password: str) -> bool:
    if username == ADMIN_USER:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), _STORED_HASH)
        except Exception:
            return False
    record = _get_user_record(username)
    if not record:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), record["hash"].encode())
    except Exception:
        return False


# ── Plan helpers ──────────────────────────────────────────────────────────────

def get_user_plan(username: str) -> str:
    if username == ADMIN_USER:
        return os.environ.get("ADMIN_PLAN", "admin").lower()
    return _get_user_record(username).get("plan", "starter").lower()


def get_user_phone(username: str) -> str:
    if username == ADMIN_USER:
        return os.environ.get("ADMIN_PHONE", "")
    return _get_user_record(username).get("phone", "")


def get_user_email(username: str) -> str:
    if username == ADMIN_USER:
        return os.environ.get("ADMIN_EMAIL", os.environ.get("SMTP_USER", ""))
    return _get_user_record(username).get("email", "")


def get_user_gcal_id(username: str) -> str:
    """Return the user's personal Google Calendar ID (their email or custom ID)."""
    if username == ADMIN_USER:
        return os.environ.get("GCAL_CALENDAR_ID", "")
    rec = _get_user_record(username)
    # Fall back to their email address as calendar ID if no explicit gcal_id set
    return rec.get("gcal_calendar_id", "") or rec.get("email", "")


def set_user_gcal_id(username: str, gcal_id: str) -> None:
    if username == ADMIN_USER:
        raise ValueError("Admin-Kalender über GCAL_CALENDAR_ID in .env setzen.")
    users = _load_users()
    if username not in users:
        raise ValueError("Benutzer nicht gefunden.")
    rec = users[username]
    if isinstance(rec, str):
        rec = {"hash": rec, "plan": "starter", "phone": "", "email": "", "gcal_calendar_id": gcal_id}
    else:
        rec["gcal_calendar_id"] = gcal_id
    users[username] = rec
    _save_users(users)


def set_user_plan(username: str, plan: str) -> None:
    if username == ADMIN_USER:
        raise ValueError("Admin-Plan über ADMIN_PLAN in .env setzen.")
    users = _load_users()
    if username not in users:
        raise ValueError("Benutzer nicht gefunden.")
    rec = users[username]
    if isinstance(rec, str):
        rec = {"hash": rec, "plan": plan, "phone": ""}
    else:
        rec["plan"] = plan
    users[username] = rec
    _save_users(users)


def set_user_phone(username: str, phone: str) -> None:
    users = _load_users()
    if username == ADMIN_USER:
        return
    if username not in users:
        raise ValueError("Benutzer nicht gefunden.")
    rec = users[username]
    if isinstance(rec, str):
        rec = {"hash": rec, "plan": "starter", "phone": phone, "email": ""}
    else:
        rec["phone"] = phone
    users[username] = rec
    _save_users(users)


def set_user_email(username: str, email: str) -> None:
    if username == ADMIN_USER:
        raise ValueError("Admin-E-Mail über ADMIN_EMAIL in .env setzen.")
    users = _load_users()
    if username not in users:
        raise ValueError("Benutzer nicht gefunden.")
    rec = users[username]
    if isinstance(rec, str):
        rec = {"hash": rec, "plan": "starter", "phone": "", "email": email}
    else:
        rec["email"] = email
    users[username] = rec
    _save_users(users)


# ── User management ───────────────────────────────────────────────────────────

def add_user(username: str, password: str, plan: str = "starter", phone: str = "", email: str = "", gcal_calendar_id: str = "") -> None:
    if not username or not password:
        raise ValueError("Benutzername und Passwort dürfen nicht leer sein.")
    if username == ADMIN_USER:
        raise ValueError("Dieser Benutzername ist reserviert.")
    if len(password) < 8:
        raise ValueError("Passwort muss mindestens 8 Zeichen haben.")
    users = _load_users()
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()
    users[username] = {"hash": hashed, "plan": plan, "phone": phone, "email": email, "gcal_calendar_id": gcal_calendar_id}
    _save_users(users)
    logger.info("User added: %s (plan=%s, email=%s)", username, plan, email)


def delete_user(username: str) -> None:
    if username == ADMIN_USER:
        raise ValueError("Den Hauptadmin kann man nicht löschen.")
    users = _load_users()
    if username not in users:
        raise ValueError("Benutzer nicht gefunden.")
    del users[username]
    _save_users(users)
    logger.info("User deleted: %s", username)


def list_users() -> list:
    users = _load_users()
    result = [{"username": ADMIN_USER, "role": "admin",
               "plan": get_user_plan(ADMIN_USER), "phone": get_user_phone(ADMIN_USER)}]
    for u, data in users.items():
        rec = data if isinstance(data, dict) else {"hash": data, "plan": "starter", "phone": ""}
        result.append({
            "username": u,
            "role": "agent",
            "plan": rec.get("plan", "starter"),
            "phone": rec.get("phone", ""),
            "email": rec.get("email", ""),
            "gcal_calendar_id": rec.get("gcal_calendar_id", ""),
        })
    return result


def count_non_admin_users() -> int:
    return len(_load_users())


def is_admin(username: str) -> bool:
    return username == ADMIN_USER


# ── Decorators ────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        if not is_admin(session.get("username", "")):
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated


def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            from flask import jsonify
            return jsonify({"error": "Nicht eingeloggt"}), 401
        return f(*args, **kwargs)
    return decorated
