import json
import logging
import os
from functools import wraps

import bcrypt
from flask import redirect, session, url_for

logger = logging.getLogger(__name__)

# ── Primary admin (env-based) ─────────────────────────────────────────────────
_DEFAULT_HASH = b"$2b$12$98vol7EU./4uSdedSnTT7OCpXP0KZhBAj8OW8f.N.L/MSH/NnteP."
_STORED_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "").encode() or _DEFAULT_HASH
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")

# ── Additional users (stored in /tmp/users.json or config/users.json) ─────────
_on_vercel = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
_USERS_FILE = "/tmp/users.json" if _on_vercel else os.path.join(
    os.path.dirname(__file__), "..", "config", "users.json"
)


def _load_users() -> dict:
    """Return {username: bcrypt_hash_str} from users file."""
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


def check_credentials(username: str, password: str) -> bool:
    # Check primary admin
    if username == ADMIN_USER:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), _STORED_HASH)
        except Exception:
            return False

    # Check additional users
    users = _load_users()
    if username in users:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), users[username].encode())
        except Exception:
            return False

    return False


def is_admin(username: str) -> bool:
    return username == ADMIN_USER


def add_user(username: str, password: str) -> None:
    if not username or not password:
        raise ValueError("Benutzername und Passwort dürfen nicht leer sein.")
    if username == ADMIN_USER:
        raise ValueError("Dieser Benutzername ist reserviert.")
    if len(password) < 8:
        raise ValueError("Passwort muss mindestens 8 Zeichen haben.")
    users = _load_users()
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()
    users[username] = hashed
    _save_users(users)
    logger.info("User added: %s", username)


def delete_user(username: str) -> None:
    if username == ADMIN_USER:
        raise ValueError("Den Hauptadmin kann man nicht löschen.")
    users = _load_users()
    if username not in users:
        raise ValueError("Benutzer nicht gefunden.")
    del users[username]
    _save_users(users)
    logger.info("User deleted: %s", username)


def change_password(username: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise ValueError("Passwort muss mindestens 8 Zeichen haben.")
    if username == ADMIN_USER:
        raise ValueError("Admin-Passwort bitte über ADMIN_PASSWORD_HASH in .env ändern.")
    users = _load_users()
    if username not in users:
        raise ValueError("Benutzer nicht gefunden.")
    users[username] = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode()
    _save_users(users)


def list_users() -> list:
    users = _load_users()
    result = [{"username": ADMIN_USER, "role": "admin"}]
    for u in users:
        result.append({"username": u, "role": "agent"})
    return result


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
