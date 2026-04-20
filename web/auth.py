import logging
from functools import wraps

import bcrypt
from flask import redirect, session, url_for

logger = logging.getLogger(__name__)

# MVP: single hardcoded user with bcrypt-hashed password
# Password: securepassword123  — change via env var ADMIN_PASSWORD_HASH in production
_DEFAULT_HASH = b"$2b$12$98vol7EU./4uSdedSnTT7OCpXP0KZhBAj8OW8f.N.L/MSH/NnteP."

import os
_STORED_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "").encode() or _DEFAULT_HASH
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")


def check_credentials(username: str, password: str) -> bool:
    if username != ADMIN_USER:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), _STORED_HASH)
    except Exception:
        return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
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
