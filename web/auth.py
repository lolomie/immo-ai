import json
import logging
import os
from functools import wraps

import bcrypt
from flask import redirect, session, url_for

logger = logging.getLogger(__name__)

# ── Primary admin (env-backed, never in DB) ───────────────────────────────────
_DEFAULT_HASH = b"$2b$12$98vol7EU./4uSdedSnTT7OCpXP0KZhBAj8OW8f.N.L/MSH/NnteP."
_STORED_HASH  = os.environ.get("ADMIN_PASSWORD_HASH", "").encode() or _DEFAULT_HASH
ADMIN_USER    = os.environ.get("ADMIN_USERNAME", "admin")

# ── Legacy JSON path (for one-time migration) ─────────────────────────────────
_on_vercel  = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
_JSON_FILE  = "/tmp/users.json" if _on_vercel else os.path.join(
    os.path.dirname(__file__), "..", "config", "users.json"
)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _db():
    from src.db import fetchone, fetchall, execute
    return fetchone, fetchall, execute


def _get_user(username: str) -> dict:
    fetchone, _, _ = _db()
    return fetchone("SELECT * FROM users WHERE username = ?", (username,)) or {}


# ── One-time JSON → DB migration ──────────────────────────────────────────────

def migrate_json_to_db() -> None:
    """Import users.json into the DB on first run. Idempotent."""
    if not os.path.exists(_JSON_FILE):
        return
    try:
        with open(_JSON_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.warning("JSON migration: could not read %s: %s", _JSON_FILE, e)
        return

    _, _, execute = _db()
    migrated = 0
    for username, data in raw.items():
        if username == ADMIN_USER:
            continue
        if isinstance(data, str):
            rec = {"hash": data, "plan": "starter", "phone": "", "email": ""}
        else:
            rec = data
        existing = _get_user(username)
        if existing:
            continue
        try:
            execute(
                """INSERT INTO users (username, password_hash, plan, phone, email)
                   VALUES (?, ?, ?, ?, ?)""",
                (username, rec.get("hash", ""), rec.get("plan", "starter"),
                 rec.get("phone", ""), rec.get("email", "")),
            )
            migrated += 1
        except Exception as e:
            logger.warning("Migration: skipping %s: %s", username, e)

    if migrated:
        logger.info("Migrated %d users from JSON → DB", migrated)


# ── Credentials ───────────────────────────────────────────────────────────────

def check_credentials(username: str, password: str) -> bool:
    if username == ADMIN_USER:
        try:
            return bcrypt.checkpw(password.encode(), _STORED_HASH)
        except Exception:
            return False
    rec = _get_user(username)
    if not rec:
        return False
    try:
        return bcrypt.checkpw(password.encode(), rec["password_hash"].encode())
    except Exception:
        return False


# ── Plan / profile helpers ────────────────────────────────────────────────────

def get_user_plan(username: str) -> str:
    if username == ADMIN_USER:
        return os.environ.get("ADMIN_PLAN", "admin").lower()
    return (_get_user(username).get("plan") or "starter").lower()


def get_user_phone(username: str) -> str:
    if username == ADMIN_USER:
        return os.environ.get("ADMIN_PHONE", "")
    return _get_user(username).get("phone") or ""


def get_user_email(username: str) -> str:
    if username == ADMIN_USER:
        return os.environ.get("ADMIN_EMAIL", os.environ.get("SMTP_USER", ""))
    return _get_user(username).get("email") or ""


def get_user_gcal_id(username: str) -> str:
    if username == ADMIN_USER:
        return os.environ.get("GCAL_CALENDAR_ID", "")
    rec = _get_user(username)
    return rec.get("gcal_calendar_id") or rec.get("email") or ""


def set_user_gcal_id(username: str, gcal_id: str) -> None:
    if username == ADMIN_USER:
        raise ValueError("Admin-Kalender über GCAL_CALENDAR_ID in .env setzen.")
    _, _, execute = _db()
    execute("UPDATE users SET gcal_calendar_id=?, updated_at=datetime('now') WHERE username=?",
            (gcal_id, username))


def set_user_plan(username: str, plan: str) -> None:
    if username == ADMIN_USER:
        raise ValueError("Admin-Plan über ADMIN_PLAN in .env setzen.")
    _, _, execute = _db()
    execute("UPDATE users SET plan=?, updated_at=datetime('now') WHERE username=?",
            (plan, username))


def set_user_phone(username: str, phone: str) -> None:
    if username == ADMIN_USER:
        return
    _, _, execute = _db()
    execute("UPDATE users SET phone=?, updated_at=datetime('now') WHERE username=?",
            (phone, username))


def set_user_email(username: str, email: str) -> None:
    if username == ADMIN_USER:
        raise ValueError("Admin-E-Mail über ADMIN_EMAIL in .env setzen.")
    _, _, execute = _db()
    execute("UPDATE users SET email=?, updated_at=datetime('now') WHERE username=?",
            (email, username))


# ── User management ───────────────────────────────────────────────────────────

def add_user(username: str, password: str, plan: str = "starter",
             phone: str = "", email: str = "", gcal_calendar_id: str = "",
             full_name: str = "", company: str = "",
             gdpr_consent: bool = False) -> None:
    if not username or not password:
        raise ValueError("Benutzername und Passwort dürfen nicht leer sein.")
    if username == ADMIN_USER:
        raise ValueError("Dieser Benutzername ist reserviert.")
    if len(password) < 8:
        raise ValueError("Passwort muss mindestens 8 Zeichen haben.")
    if _get_user(username):
        raise ValueError(f"Benutzername '{username}' ist bereits vergeben.")
    _, _, execute = _db()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    from datetime import datetime, timezone
    consent_at = datetime.now(timezone.utc).isoformat() if gdpr_consent else None
    execute(
        """INSERT INTO users
               (username, password_hash, full_name, email, phone, company,
                plan, gcal_calendar_id, gdpr_consent, gdpr_consent_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (username, hashed, full_name, email, phone, company,
         plan, gcal_calendar_id, int(gdpr_consent), consent_at),
    )
    logger.info("User created: %s (plan=%s, email=%s)", username, plan, email)


def delete_user(username: str) -> None:
    if username == ADMIN_USER:
        raise ValueError("Den Hauptadmin kann man nicht löschen.")
    if not _get_user(username):
        raise ValueError("Benutzer nicht gefunden.")
    _, _, execute = _db()
    execute("DELETE FROM users WHERE username = ?", (username,))
    logger.info("User deleted: %s", username)


def gdpr_delete_user(username: str) -> dict:
    """
    DSGVO Art. 17 — Recht auf Löschung.
    Deletes user + anonymises their calendar events and usage logs.
    Returns a summary of what was deleted.
    """
    if username == ADMIN_USER:
        raise ValueError("Admin-Account kann nicht gelöscht werden.")
    fetchone, _, execute = _db()

    user = _get_user(username)
    if not user:
        raise ValueError("Benutzer nicht gefunden.")

    # Anonymise calendar events (keep for audit, remove PII)
    execute(
        "UPDATE calendar_events SET client_name='[gelöscht]', client_contact='' WHERE username=?",
        (username,),
    )
    # Delete usage records
    execute("DELETE FROM usage WHERE username = ?", (username,))
    # Delete user record
    execute("DELETE FROM users WHERE username = ?", (username,))

    logger.info("GDPR delete completed for: %s", username)
    return {"deleted_user": username, "anonymised_events": True, "deleted_usage": True}


def list_users() -> list:
    _, fetchall, _ = _db()
    rows = fetchall("SELECT username, full_name, email, phone, company, plan, gcal_calendar_id, created_at FROM users ORDER BY created_at")
    result = [{"username": ADMIN_USER, "role": "admin",
               "plan": get_user_plan(ADMIN_USER),
               "phone": get_user_phone(ADMIN_USER),
               "email": get_user_email(ADMIN_USER)}]
    for r in rows:
        result.append({**r, "role": "agent"})
    return result


# ── Google OAuth ──────────────────────────────────────────────────────────────

def get_or_create_google_user(google_id: str, email: str, full_name: str) -> str:
    """
    Find an existing user by Google ID or email and link their Google account.
    Does NOT auto-create new users — admin must create accounts first.
    Raises ValueError if no matching account exists.
    """
    fetchone, _, execute = _db()

    # 1. Already linked by google_id
    row = fetchone("SELECT username FROM users WHERE google_id = ?", (google_id,))
    if row:
        return row["username"]

    # 2. Email matches an existing account → link google_id
    row = fetchone("SELECT username FROM users WHERE email = ?", (email,))
    if row:
        execute(
            "UPDATE users SET google_id=?, updated_at=datetime('now') WHERE username=?",
            (google_id, row["username"]),
        )
        logger.info("Google OAuth: linked google_id to existing user %s", row["username"])
        return row["username"]

    # 3. No account found → reject
    raise ValueError(
        f"Kein Konto für {email} gefunden. "
        "Bitte wende dich an den Administrator."
    )


def count_non_admin_users() -> int:
    fetchone, _, _ = _db()
    row = fetchone("SELECT COUNT(*) AS n FROM users")
    return (row or {}).get("n", 0)


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
