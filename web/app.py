import json
import logging
import os
import secrets
import sys
import uuid
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, redirect, render_template, request, session, stream_with_context, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))  # project root → src.*
sys.path.insert(0, _here)                       # web/ → auth

from src.db import init_db
from src.calendar_service import create_appointment, delete_appointment, get_appointments, update_appointment
from src.generator import generate_expose, stream_expose
from src.models import JobResult, PropertyInput
from src.validator import validate_expose
from src.plans import PLANS, has_feature, get_monthly_limit, get_plan
from src.usage_tracker import check_limit, increment, get_usage
try:
    from .auth import (api_login_required, check_credentials, login_required,
                       admin_required, add_user, delete_user, list_users,
                       get_user_plan, get_user_phone, get_user_email,
                       get_user_gcal_id, set_user_plan, set_user_phone,
                       set_user_email, set_user_gcal_id, count_non_admin_users,
                       migrate_json_to_db, gdpr_delete_user)
except ImportError:
    from auth import (api_login_required, check_credentials, login_required,
                      admin_required, add_user, delete_user, list_users,
                      get_user_plan, get_user_phone, get_user_email,
                      get_user_gcal_id, set_user_plan, set_user_phone,
                      set_user_email, set_user_gcal_id, count_non_admin_users,
                      migrate_json_to_db, gdpr_delete_user)


def _is_admin() -> bool:
    from auth import is_admin
    return is_admin(session.get("username", ""))

def _plan() -> str:
    if _is_admin():
        return "admin"
    username = session.get("username", "")
    if username:
        return get_user_plan(username)
    return "starter"


def _username() -> str:
    return session.get("username", "anonymous")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

if not os.environ.get("SECRET_KEY"):
    app.logger.warning("SECRET_KEY not set — sessions will reset on restart. Set SECRET_KEY env var in production.")

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

from src.config import LOGS_DIR

# ── DB init + JSON migration (runs once at startup) ───────────────────────────
try:
    init_db()
    migrate_json_to_db()
except Exception as _db_err:
    app.logger.error("DB init failed: %s", _db_err)


def _parse_property(data: dict):
    if not data.get("property_id"):
        data["property_id"] = "WEB-" + str(uuid.uuid4())[:6].upper()
    if isinstance(data.get("features"), str):
        data["features"] = [f.strip() for f in data["features"].split(",") if f.strip()]
    for field in ("purchase_price", "monthly_rent", "year_built"):
        if data.get(field) in ("", None, 0):
            data[field] = None
    return PropertyInput(**data)


def _save_job(job: JobResult, property_data=None):
    data = job.model_dump()
    if property_data is not None:
        for k, v in property_data.model_dump().items():
            if k not in data:
                data[k] = v
    json_str = json.dumps(data, ensure_ascii=False)
    try:
        from src.db import execute as _db_exec
        _db_exec(
            "INSERT OR REPLACE INTO jobs (job_id, timestamp, status, created_by, data, updated_at)"
            " VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (job.job_id, job.timestamp, job.status, job.created_by or '', json_str),
        )
    except Exception as _e:
        app.logger.warning("DB job save failed: %s", _e)
    # filesystem backup (local dev + backward compat)
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(os.path.join(LOGS_DIR, f"{job.job_id}.json"), "w", encoding="utf-8") as _f:
            json.dump(data, _f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_job(job_id: str) -> dict | None:
    """Load a job from DB (preferred) or filesystem (fallback)."""
    try:
        from src.db import fetchone as _db_fetch
        row = _db_fetch("SELECT data FROM jobs WHERE job_id = ?", (job_id,))
        if row:
            return json.loads(row["data"])
    except Exception:
        pass
    path = os.path.join(LOGS_DIR, f"{job_id}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _update_job_in_db(job_id: str, fields: dict):
    """Update indexed columns + data blob for a job."""
    try:
        from src.db import fetchone as _db_fetch, execute as _db_exec
        row = _db_fetch("SELECT data FROM jobs WHERE job_id = ?", (job_id,))
        if not row:
            return
        data = json.loads(row["data"])
        data.update(fields)
        sets = ", ".join(f"{k}=?" for k in fields if k in ("status", "created_by"))
        params = [fields[k] for k in fields if k in ("status", "created_by")]
        params += [json.dumps(data, ensure_ascii=False), job_id]
        _db_exec(
            f"UPDATE jobs SET {sets + ', ' if sets else ''}data=?, updated_at=datetime('now') WHERE job_id=?",
            tuple(params),
        )
    except Exception as _e:
        app.logger.warning("DB job update failed: %s", _e)


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/") or request.path.startswith("/calendar/"):
        return jsonify({"error": "Nicht gefunden"}), 404
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.error("500 error: %s", e)
    if request.path.startswith("/api/") or request.path.startswith("/calendar/"):
        return jsonify({"error": "Interner Serverfehler"}), 500
    return render_template("500.html"), 500


@app.errorhandler(429)
def rate_limited(e):
    return jsonify({"error": "Zu viele Anfragen — bitte kurz warten."}), 429


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if session.get("logged_in"):
        return redirect(url_for("generate_page"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if check_credentials(username, password):
            session["logged_in"] = True
            session["username"] = username
            session["plan"] = get_user_plan(username)
            app.logger.info("Login: %s (plan=%s)", username, session["plan"])
            return redirect(request.args.get("next") or url_for("generate_page"))
        app.logger.warning("Failed login attempt for user: %s", username)
        return render_template("login.html", error="Falsche Zugangsdaten", username=username)

    return render_template("login.html", error=None, username="")


@app.route("/logout")
def logout():
    username = session.get("username", "unknown")
    session.clear()
    app.logger.info("Logout: %s", username)
    return redirect(url_for("login_page"))


# ── Google OAuth ──────────────────────────────────────────────────────────────

_GOOGLE_AUTH_URL    = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL   = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL= "https://www.googleapis.com/oauth2/v2/userinfo"

def _google_client_id():
    from src.config import GOOGLE_CLIENT_ID
    return GOOGLE_CLIENT_ID

def _google_client_secret():
    from src.config import GOOGLE_CLIENT_SECRET
    return GOOGLE_CLIENT_SECRET

def _google_redirect_uri():
    from src.config import APP_URL
    return APP_URL.rstrip("/") + "/auth/google/callback"


@app.route("/auth/google")
def google_login():
    client_id = _google_client_id()
    if not client_id:
        return render_template("login.html", error="Google-Login nicht konfiguriert (GOOGLE_CLIENT_ID fehlt).", username="")

    import urllib.parse, secrets as _sec
    state = _sec.token_urlsafe(16)
    session["oauth_state"] = state

    params = {
        "client_id":     client_id,
        "redirect_uri":  _google_redirect_uri(),
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
        "prompt":        "select_account",
    }
    url = _GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return redirect(url)


# ── Billing / Stripe ──────────────────────────────────────────────────────────

@app.route("/billing/checkout", methods=["POST"])
@limiter.limit("10 per minute")
def billing_checkout():
    """
    Create a Stripe Checkout Session and redirect the user to it.
    Works in all modes: placeholder (simulated), test (Stripe sandbox), live.
    """
    from src.stripe_client import create_checkout_session, get_config
    data     = request.get_json() or {}
    plan_key = data.get("plan", "pro").strip().lower()
    billing  = data.get("billing", "monthly").strip().lower()
    email    = data.get("email", "").strip()
    username = _username()

    if plan_key not in ("starter", "pro", "business"):
        return jsonify({"error": "Ungültiger Plan."}), 400
    if billing not in ("monthly", "annual"):
        return jsonify({"error": "Ungültige Abrechnungsperiode."}), 400

    base = request.host_url.rstrip("/")
    try:
        result = create_checkout_session(
            plan_key=plan_key,
            billing=billing,
            email=email or (get_user_email(username) if session.get("logged_in") else ""),
            username=username,
            success_url=f"{base}/billing/success",
            cancel_url=f"{base}/billing/cancel",
        )
        return jsonify(result)
    except Exception as e:
        app.logger.error("Checkout session error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/billing/placeholder-checkout")
def billing_placeholder_checkout():
    """Simulated checkout page shown only in placeholder mode."""
    from src.stripe_client import is_placeholder
    if not is_placeholder():
        return redirect(url_for("index"))
    plan_key   = request.args.get("plan", "pro")
    billing    = request.args.get("billing", "monthly")
    session_id = request.args.get("session_id", "")
    success_url= request.args.get("success_url", "/billing/success")
    cancel_url = request.args.get("cancel_url", "/billing/cancel")
    return render_template(
        "billing_placeholder.html",
        plan_key=plan_key, billing=billing,
        session_id=session_id,
        success_url=success_url, cancel_url=cancel_url,
        auth_required=False,
    )


@app.route("/billing/success")
def billing_success():
    """Post-checkout success page. Activates subscription."""
    from src.stripe_client import verify_checkout_session, _upsert_subscription, _sync_user_plan
    session_id = request.args.get("session_id", "")
    plan_key   = request.args.get("plan", "")
    billing    = request.args.get("billing", "monthly")

    subscription = None
    error = None

    if session_id:
        try:
            sub_data = verify_checkout_session(session_id)
            username = sub_data.get("username") or _username()
            if not sub_data.get("plan_key") and plan_key:
                sub_data["plan_key"] = plan_key
            if username and username != "anonymous":
                from src.stripe_client import _upsert_subscription as _upsert
                _upsert(username, {
                    "stripe_customer_id":     sub_data.get("stripe_customer_id", ""),
                    "stripe_subscription_id": sub_data.get("stripe_subscription_id", ""),
                    "stripe_price_id":        sub_data.get("stripe_price_id", ""),
                    "plan_key":               sub_data.get("plan_key", plan_key),
                    "billing":                billing,
                    "status":                 "active",
                })
                from src.stripe_client import _sync_user_plan as _sync
                _sync(username, sub_data.get("plan_key", plan_key))
                if session.get("logged_in"):
                    session["plan"] = sub_data.get("plan_key", plan_key)
            subscription = sub_data
        except Exception as e:
            app.logger.error("Success page verification error: %s", e)
            error = str(e)

    return render_template(
        "billing_success.html",
        session_id=session_id,
        plan_key=plan_key or (subscription or {}).get("plan_key", "pro"),
        billing=billing,
        subscription=subscription,
        error=error,
        auth_required=False,
    )


@app.route("/billing/cancel")
def billing_cancel():
    return render_template("billing_cancel.html", auth_required=False)


@app.route("/billing/portal")
@login_required
def billing_portal():
    """Redirect to Stripe Customer Portal for subscription management."""
    from src.stripe_client import create_portal_session
    from src.db import fetchone
    username = _username()
    sub = fetchone("SELECT stripe_customer_id FROM subscriptions WHERE username = ?", (username,))
    customer_id = (sub or {}).get("stripe_customer_id", "")
    return_url = request.host_url.rstrip("/") + "/generate"
    try:
        url = create_portal_session(customer_id, return_url)
        return redirect(url)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/billing/status")
@api_login_required
def api_billing_status():
    """Return the current user's subscription status."""
    from src.db import fetchone
    from src.stripe_client import get_config
    username = _username()
    sub = fetchone(
        "SELECT plan_key, billing, status, current_period_end, cancel_at_period_end, "
        "stripe_subscription_id, updated_at FROM subscriptions WHERE username = ?",
        (username,),
    )
    return jsonify({
        "username":    username,
        "plan":        _plan(),
        "subscription": sub,
        "stripe_mode": get_config()["mode"],
    })


@app.route("/api/billing/webhook", methods=["POST"])
def billing_webhook():
    """
    Stripe webhook endpoint.
    Register this URL in Stripe Dashboard → Webhooks:
      https://yourdomain.com/api/billing/webhook
    """
    from src.stripe_client import verify_webhook, handle_webhook_event
    payload    = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event  = verify_webhook(payload, sig_header)
        result = handle_webhook_event(event)
        app.logger.info("Webhook: %s → %s", event.get("type"), result)
        return jsonify({"received": True, "result": result})
    except ValueError as e:
        app.logger.warning("Webhook rejected: %s", e)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error("Webhook error: %s", e)
        return jsonify({"error": "internal error"}), 500


@app.route("/api/billing/config")
def api_billing_config():
    """Return non-sensitive Stripe config for the frontend."""
    from src.stripe_client import get_config
    return jsonify(get_config())


@app.route("/auth/google/callback")
def google_callback():
    error = request.args.get("error")
    if error:
        return render_template("login.html", error=f"Google-Login abgebrochen: {error}", username="")

    if request.args.get("state") != session.pop("oauth_state", None):
        return render_template("login.html", error="Ungültiger OAuth-State. Bitte erneut versuchen.", username="")

    code = request.args.get("code")
    if not code:
        return render_template("login.html", error="Kein Autorisierungscode erhalten.", username="")

    # Exchange code for token
    import requests as _req
    token_resp = _req.post(_GOOGLE_TOKEN_URL, data={
        "code":          code,
        "client_id":     _google_client_id(),
        "client_secret": _google_client_secret(),
        "redirect_uri":  _google_redirect_uri(),
        "grant_type":    "authorization_code",
    }, timeout=10)

    if not token_resp.ok:
        app.logger.error("Google token exchange failed: %s", token_resp.text)
        return render_template("login.html", error="Google-Authentifizierung fehlgeschlagen.", username="")

    access_token = token_resp.json().get("access_token")

    # Get user info
    userinfo_resp = _req.get(_GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"}, timeout=10)

    if not userinfo_resp.ok:
        return render_template("login.html", error="Google-Nutzerdaten konnten nicht abgerufen werden.", username="")

    info      = userinfo_resp.json()
    google_id = info.get("id", "")
    email     = info.get("email", "")
    full_name = info.get("name", "")

    if not email:
        return render_template("login.html", error="Keine E-Mail von Google erhalten.", username="")

    try:
        try:
            from .auth import get_or_create_google_user
        except ImportError:
            from auth import get_or_create_google_user
        username = get_or_create_google_user(google_id, email, full_name)
    except ValueError as e:
        app.logger.warning("Google OAuth rejected: %s (%s)", email, e)
        return render_template("login.html", error=str(e), username="")
    except Exception as e:
        app.logger.error("Google OAuth failed: %s", e)
        return render_template("login.html", error="Google-Anmeldung fehlgeschlagen. Bitte erneut versuchen.", username="")

    session["logged_in"] = True
    session["username"]  = username
    session["plan"]      = get_user_plan(username)
    app.logger.info("Google login: %s (%s)", username, email)
    return redirect(url_for("generate_page"))


# ── Pages (protected) ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", auth_required=False)


@app.route("/generate")
@login_required
def generate_page():
    plan = _plan()
    used = get_usage(_username())
    limit = get_monthly_limit(plan)
    return render_template(
        "generate.html",
        auth_required=False,
        user_plan=plan,
        plan_info=get_plan(plan),
        can_custom_tone=has_feature(plan, "custom_tone"),
        monthly_limit=limit,
        monthly_used=used,
        limit_reached=(used >= limit),
    )


@app.route("/review")
@login_required
def review_page():
    return render_template("review.html", auth_required=False, user_plan=_plan())


@app.route("/calendar")
@login_required
def calendar_page():
    plan = _plan()
    if not has_feature(plan, "calendar"):
        return render_template("upgrade.html", auth_required=False,
                               feature="Kalendersystem",
                               feature_key="calendar",
                               current_plan=plan,
                               required_plan="pro"), 403
    return render_template("calendar.html", auth_required=False, user_plan=plan)


@app.route("/about")
def about_page():
    return render_template("about.html", auth_required=False)


@app.route("/impressum")
def impressum_page():
    return render_template("impressum.html", auth_required=False)


@app.route("/signup")
def signup_page():
    from src.plans import PLANS, get_plan
    plan_key = request.args.get("plan", "pro").lower()
    plan = get_plan(plan_key)
    return render_template("signup.html", plan=plan, plan_key=plan_key,
                           all_plans=PLANS, auth_required=False)


@app.route("/api/signup", methods=["POST"])
@limiter.limit("5 per minute")
def api_signup():
    data = request.get_json() or {}
    name         = data.get("name", "").strip()
    email        = data.get("email", "").strip()
    company      = data.get("company", "").strip()
    phone        = data.get("phone", "").strip()
    plan_key     = data.get("plan", "pro").strip()
    message      = data.get("message", "").strip()
    gdpr_consent = bool(data.get("gdpr_consent", False))

    if not name or not email:
        return jsonify({"error": "Name und E-Mail sind Pflichtfelder."}), 400
    if not gdpr_consent:
        return jsonify({"error": "Bitte stimmen Sie der Datenschutzerklärung zu."}), 400

    # ── 1. Persist to DB (primary, never loses data) ──────────────────────────
    try:
        from src.db import execute
        ip = request.remote_addr or ""
        execute(
            """INSERT INTO signup_requests
                   (full_name, email, company, phone, plan_key, message, gdpr_consent, ip_address)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, email, company, phone, plan_key, message, int(gdpr_consent), ip),
        )
        app.logger.info("Signup saved to DB: %s (%s), plan=%s", name, email, plan_key)
    except Exception as e:
        app.logger.error("Signup DB write failed: %s", e)
        return jsonify({"error": "Registrierung konnte nicht gespeichert werden. Bitte erneut versuchen."}), 500

    # ── 2. Notify admin via email (best-effort) ───────────────────────────────
    try:
        from src.email_client import _build_message, _send
        plan = get_plan(plan_key)
        subject = f"🆕 Demo-Anfrage: {name} — {plan['name']}-Plan"
        body_html = f"""
<html><body style="font-family:sans-serif;color:#1e293b;max-width:560px;margin:auto;padding:24px;">
  <h2 style="color:#1a3a5c;">Neue Demo-Anfrage über Immo AI</h2>
  <table style="border-collapse:collapse;width:100%;margin:16px 0;">
    <tr><td style="padding:8px;background:#f1f5f9;font-weight:600;width:140px;">Name</td><td style="padding:8px;">{name}</td></tr>
    <tr><td style="padding:8px;background:#f1f5f9;font-weight:600;">E-Mail</td><td style="padding:8px;">{email}</td></tr>
    <tr><td style="padding:8px;background:#f1f5f9;font-weight:600;">Unternehmen</td><td style="padding:8px;">{company or '—'}</td></tr>
    <tr><td style="padding:8px;background:#f1f5f9;font-weight:600;">Telefon</td><td style="padding:8px;">{phone or '—'}</td></tr>
    <tr><td style="padding:8px;background:#f1f5f9;font-weight:600;">Plan</td><td style="padding:8px;font-weight:700;color:#2563eb;">{plan['name']} ({plan['monthly_price']} €/Monat)</td></tr>
    <tr><td style="padding:8px;background:#f1f5f9;font-weight:600;">DSGVO</td><td style="padding:8px;color:#16a34a;">✓ Zugestimmt</td></tr>
  </table>
  {f'<p><strong>Nachricht:</strong> {message}</p>' if message else ''}
</body></html>"""
        body_text = f"Demo-Anfrage\nName: {name}\nEmail: {email}\nPlan: {plan['name']}"
        from src.config import EMAIL_FROM
        _send(EMAIL_FROM, _build_message(EMAIL_FROM, subject, body_html, body_text))
    except Exception as e:
        app.logger.warning("Signup email notification failed (data saved): %s", e)

    return jsonify({"ok": True, "message": "Vielen Dank! Wir melden uns innerhalb von 24 Stunden."})


# ── DSGVO / GDPR endpoints ────────────────────────────────────────────────────

@app.route("/api/gdpr/export", methods=["GET"])
@api_login_required
def api_gdpr_export():
    """DSGVO Art. 20 — Datenportabilität: eigene Daten als JSON exportieren."""
    username = _username()
    from src.db import fetchone, fetchall
    user = fetchone("SELECT username, full_name, email, phone, company, plan, created_at FROM users WHERE username = ?", (username,))
    events = fetchall("SELECT * FROM calendar_events WHERE username = ?", (username,))
    from src.usage_tracker import get_all_usage
    return jsonify({
        "export_date": datetime.now(timezone.utc).isoformat(),
        "user": user,
        "calendar_events": events,
        "note": "Exportiert gemäß DSGVO Art. 20 (Recht auf Datenübertragbarkeit).",
    })


@app.route("/api/gdpr/delete", methods=["POST"])
@api_login_required
def api_gdpr_delete():
    """DSGVO Art. 17 — Recht auf Löschung."""
    username = _username()
    data = request.get_json() or {}
    confirm = data.get("confirm", "").strip()
    if confirm != username:
        return jsonify({"error": "Bitte Benutzernamen zur Bestätigung eingeben."}), 400
    try:
        result = gdpr_delete_user(username)
        session.clear()
        app.logger.info("GDPR delete: %s", username)
        return jsonify({"ok": True, **result})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/admin/signups", methods=["GET"])
@admin_required
def api_admin_signups():
    """Admin: alle Signup-Anfragen abrufen."""
    from src.db import fetchall
    rows = fetchall(
        "SELECT id, full_name, email, company, phone, plan_key, status, gdpr_consent, created_at FROM signup_requests ORDER BY created_at DESC"
    )
    return jsonify({"signups": rows, "total": len(rows)})


@app.route("/api/admin/signups/<int:signup_id>", methods=["PATCH"])
@admin_required
def api_admin_signup_status(signup_id):
    """Admin: Signup-Status ändern (pending → contacted / converted / rejected)."""
    data = request.get_json() or {}
    status = data.get("status", "").strip()
    valid = {"pending", "contacted", "converted", "rejected"}
    if status not in valid:
        return jsonify({"error": f"Status muss einer von {valid} sein."}), 400
    from src.db import execute
    execute("UPDATE signup_requests SET status = ? WHERE id = ?", (status, signup_id))
    return jsonify({"ok": True})


@app.route("/admin/users")
@admin_required
def admin_users_page():
    users = list_users()
    return render_template("admin_users.html", users=users, auth_required=False,
                           can_add_users=True,
                           all_plans=PLANS)


# ── Admin User API ────────────────────────────────────────────────────────────

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def api_admin_list_users():
    return jsonify({"users": list_users()})


@app.route("/api/admin/users", methods=["POST"])
@admin_required
def api_admin_add_user():
    if not has_feature(_plan(), "multi_user"):
        return jsonify({"error": "Multi-User erfordert den Business-Plan. Bitte upgraden."}), 403
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    plan_key = data.get("plan", "starter").strip()
    phone    = data.get("phone", "").strip()
    email    = data.get("email", "").strip()
    try:
        add_user(username, password, plan=plan_key, phone=phone, email=email)
        app.logger.info("User created: %s (plan=%s) by %s", username, plan_key, _username())
        return jsonify({"ok": True, "username": username})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/admin/users/<username>", methods=["PATCH"])
@admin_required
def api_admin_patch_user(username):
    data = request.get_json() or {}
    try:
        if "plan" in data:
            plan_key = data["plan"].strip().lower()
            if plan_key not in PLANS:
                return jsonify({"error": f"Unbekannter Plan: {plan_key}"}), 400
            set_user_plan(username, plan_key)
        if "phone" in data:
            set_user_phone(username, data["phone"].strip())
        if "email" in data:
            set_user_email(username, data["email"].strip())
        if "gcal_calendar_id" in data:
            set_user_gcal_id(username, data["gcal_calendar_id"].strip())
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/admin/users/<username>", methods=["DELETE"])
@admin_required
def api_admin_delete_user(username):
    try:
        delete_user(username)
        app.logger.info("User deleted: %s by %s", username, _username())
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/admin/users/<username>/plan", methods=["PATCH"])
@admin_required
def api_admin_set_plan(username):
    data = request.get_json() or {}
    plan_key = data.get("plan", "").strip().lower()
    if plan_key not in PLANS:
        return jsonify({"error": f"Unbekannter Plan: {plan_key}"}), 400
    try:
        set_user_plan(username, plan_key)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/admin/users/<username>/phone", methods=["PATCH"])
@admin_required
def api_admin_set_phone(username):
    data = request.get_json() or {}
    phone = data.get("phone", "").strip()
    try:
        set_user_phone(username, phone)
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/profile", methods=["GET"])
@api_login_required
def api_profile_get():
    username = _username()
    return jsonify({
        "email":            get_user_email(username),
        "gcal_calendar_id": get_user_gcal_id(username),
    })


@app.route("/api/profile", methods=["PATCH"])
@api_login_required
def api_profile_patch():
    username = _username()
    if username == "admin":
        return jsonify({"error": "Admin-Einstellungen über .env setzen"}), 400
    data = request.get_json() or {}
    try:
        if "gcal_calendar_id" in data:
            set_user_gcal_id(username, data["gcal_calendar_id"].strip())
        if "email" in data:
            set_user_email(username, data["email"].strip())
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/usage")
@api_login_required
def api_usage():
    plan = _plan()
    used = get_usage(_username())
    limit = get_monthly_limit(plan)
    return jsonify({
        "plan": plan,
        "plan_name": get_plan(plan)["name"],
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "percent": round(used / limit * 100) if limit else 0,
    })


# ── Calendar API ──────────────────────────────────────────────────────────────

@app.route("/calendar/create", methods=["POST"])
@api_login_required
def calendar_create():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Kein JSON erhalten"}), 400
    try:
        username_now = _username()
        appt = create_appointment(data, username=username_now)

        _appt_dict = appt.to_dict()
        agent_email = get_user_email(username_now)
        agent_name  = username_now

        # GCal sync — synchronous so the result can be shown in the UI
        gcal_synced = False
        gcal_configured = False
        gcal_error = None
        try:
            from src.gcal_client import create_event as _gcal_create
            from src.config import GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SERVICE_ACCOUNT_JSON
            user_gcal_id = get_user_gcal_id(username_now)
            gcal_configured = bool(user_gcal_id and (GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON))
            if gcal_configured:
                from datetime import datetime as _dt, timedelta as _td
                dt_start = f"{_appt_dict['date']}T{_appt_dict['time']}:00"
                dt_end = (_dt.fromisoformat(dt_start) + _td(hours=1)).isoformat()
                title = f"{_appt_dict['type']} – {_appt_dict['client_name']}"
                if _appt_dict.get("property_id"):
                    title += f" ({_appt_dict['property_id']})"
                desc = f"Makler: {agent_name}"
                if agent_email:
                    desc += f" ({agent_email})"
                desc += f"\nKunde: {_appt_dict['client_name']}"
                if _appt_dict.get("client_contact"):
                    desc += f"\nKontakt: {_appt_dict['client_contact']}"
                if _appt_dict.get("notes"):
                    desc += f"\nNotizen: {_appt_dict['notes']}"
                _gcal_id = _gcal_create(
                    title=title,
                    start_dt=dt_start,
                    end_dt=dt_end,
                    description=desc,
                    location=_appt_dict.get("property_id", ""),
                    appointment_id=_appt_dict["appointment_id"],
                    calendar_id=user_gcal_id,
                )
                gcal_synced = True
                app.logger.info("GCal event created: %s for appt %s", _gcal_id, _appt_dict["appointment_id"])
            else:
                app.logger.info("GCal sync skipped for %s: not configured", username_now)
        except Exception as e:
            gcal_error = str(e)
            app.logger.error("GCal sync failed for %s: %s", username_now, e, exc_info=True)

        def _post_create():
            # 1. Google Sheets
            try:
                from src.sheets_client import append_termin_row
                append_termin_row(_appt_dict, agent_email, agent_name)
            except Exception as e:
                app.logger.warning("Sheets termin sync failed: %s", e)

            # 2. Bestätigungs-E-Mail an Makler
            if agent_email:
                try:
                    from src.email_client import send_appointment_confirmation_agent
                    send_appointment_confirmation_agent(
                        agent_email=agent_email,
                        agent_name=agent_name,
                        client_name=_appt_dict["client_name"],
                        client_contact=_appt_dict.get("client_contact", ""),
                        appointment_type=_appt_dict["type"],
                        date=_appt_dict["date"],
                        time=_appt_dict["time"],
                        property_id=_appt_dict.get("property_id", ""),
                        notes=_appt_dict.get("notes", ""),
                        appointment_id=_appt_dict["appointment_id"],
                    )
                    app.logger.info("Agent confirmation email sent to %s", agent_email)
                except Exception as e:
                    app.logger.warning("Agent confirmation email failed: %s", e)

            # 3. Bestätigungs-E-Mail an Kunde (nur wenn client_contact eine E-Mail ist)
            client_contact = _appt_dict.get("client_contact", "")
            if "@" in client_contact:
                try:
                    from src.email_client import send_appointment_confirmation
                    dt_iso = f"{_appt_dict['date']}T{_appt_dict['time']}:00"
                    send_appointment_confirmation(
                        lead_email=client_contact,
                        lead_name=_appt_dict["client_name"],
                        agent_name=agent_name,
                        property_address=_appt_dict.get("property_id", ""),
                        datetime_start=dt_iso,
                        appointment_id=_appt_dict["appointment_id"],
                    )
                    app.logger.info("Client confirmation email sent to %s", client_contact)
                except Exception as e:
                    app.logger.warning("Client confirmation email failed: %s", e)

        import threading
        threading.Thread(target=_post_create, daemon=True).start()

        return jsonify({
            "ok": True,
            "appointment": appt.to_dict(),
            "gcal_synced": gcal_synced,
            "gcal_configured": gcal_configured,
            "gcal_error": gcal_error,
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error("Calendar create failed: %s", e, exc_info=True)
        return jsonify({"error": "Interner Fehler"}), 500


@app.route("/calendar/all", methods=["GET"])
@api_login_required
def calendar_all():
    appointments = [a.to_dict() for a in get_appointments()]
    return jsonify({"appointments": appointments, "total": len(appointments)})


@app.route("/calendar/delete", methods=["POST"])
@api_login_required
def calendar_delete():
    data = request.get_json()
    appt_id = (data or {}).get("appointment_id", "").strip()
    if not appt_id:
        return jsonify({"error": "appointment_id fehlt"}), 400
    removed = delete_appointment(appt_id)
    if not removed:
        return jsonify({"error": "Termin nicht gefunden"}), 404
    return jsonify({"ok": True})


@app.route("/calendar/update", methods=["POST"])
@api_login_required
def calendar_update():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Kein JSON erhalten"}), 400
    appt_id = data.pop("appointment_id", "").strip()
    if not appt_id:
        return jsonify({"error": "appointment_id fehlt"}), 400
    try:
        appt = update_appointment(appt_id, data)
        if not appt:
            return jsonify({"error": "Termin nicht gefunden"}), 404
        return jsonify({"ok": True, "appointment": appt.to_dict()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error("Calendar update failed: %s", e, exc_info=True)
        return jsonify({"error": "Interner Fehler"}), 500


# ── API: Generate ─────────────────────────────────────────────────────────────

@app.route("/api/generate", methods=["POST"])
@limiter.limit("10 per minute")
@api_login_required
def api_generate():
    # ── Plan limit check ──────────────────────────────────────────────────────
    allowed, reason = check_limit(_username(), _plan())
    if not allowed:
        return jsonify({"error": reason}), 429

    data = request.get_json()
    if not data:
        return jsonify({"error": "Kein JSON erhalten"}), 400
    tone = data.pop("tone", None) if has_feature(_plan(), "custom_tone") else None
    try:
        property_data = _parse_property(data)
    except Exception as e:
        return jsonify({"error": f"Ungültige Eingabe: {e}"}), 400
    try:
        expose_text = generate_expose(property_data, tone=tone)
        validation = validate_expose(property_data, expose_text)
    except Exception as e:
        app.logger.error("Generation failed: %s", e)
        return jsonify({"error": f"Generierung fehlgeschlagen: {e}"}), 500
    job = JobResult(
        job_id=str(uuid.uuid4())[:8],
        timestamp=datetime.now(timezone.utc).isoformat(),
        status="pending",
        property_id=property_data.property_id,
        expose_text=expose_text,
        hallucination_detected=validation["hallucinated"],
        hallucination_details=validation["details"],
    )
    _save_job(job, property_data)
    increment(_username())
    app.logger.info("Job created: %s for %s (plan=%s)", job.job_id, property_data.property_id, _plan())
    return jsonify(job.model_dump())


@app.route("/api/generate/stream", methods=["POST"])
@limiter.limit("10 per minute")
@api_login_required
def api_generate_stream():
    # ── Plan limit check ──────────────────────────────────────────────────────
    allowed, reason = check_limit(_username(), _plan())
    if not allowed:
        return jsonify({"error": reason}), 429

    data = request.get_json()
    if not data:
        return jsonify({"error": "Kein JSON erhalten"}), 400
    tone = data.pop("tone", None) if has_feature(_plan(), "custom_tone") else None
    try:
        property_data = _parse_property(data)
    except Exception as e:
        return jsonify({"error": f"Ungültige Eingabe: {e}"}), 400

    job_id   = str(uuid.uuid4())[:8]
    username = _username()
    plan     = _plan()
    phone    = get_user_phone(username)

    def generate():
        full_text = []
        try:
            for chunk in stream_expose(property_data, tone=tone):
                full_text.append(chunk)
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'validating'})}\n\n"

            expose_text = "".join(full_text)
            validation = validate_expose(property_data, expose_text)

            job = JobResult(
                job_id=job_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                status="pending",
                property_id=property_data.property_id,
                expose_text=expose_text,
                hallucination_detected=validation["hallucinated"],
                hallucination_details=validation["details"],
                created_by=username,
            )
            _save_job(job, property_data)
            increment(username)
            app.logger.info("Stream job: %s for %s (plan=%s)", job_id, property_data.property_id, plan)

            # Write to Google Sheets (non-blocking)
            def _sync_to_sheets(j=job.model_dump(), e=get_user_email(username)):
                try:
                    from src.sheets_client import append_expose_row_from_job
                    append_expose_row_from_job(j, e)
                except Exception as _e:
                    app.logger.warning("Sheets sync failed: %s", _e)
            import threading as _t
            _t.Thread(target=_sync_to_sheets, daemon=True).start()

            # WhatsApp push for Pro/Business
            if has_feature(plan, "whatsapp") and phone:
                try:
                    from src.whatsapp_client import notify_expose_ready
                    notify_expose_ready(phone, property_data.address, f"/review#{job_id}")
                except Exception as e:
                    app.logger.warning("WhatsApp notify failed: %s", e)

            yield f"data: {json.dumps({'type': 'done', 'job': job.model_dump()})}\n\n"
        except Exception as e:
            app.logger.error("Stream failed: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── API: Jobs ─────────────────────────────────────────────────────────────────

@app.route("/api/jobs")
@api_login_required
def api_jobs():
    try:
        status_filter = request.args.get("status", "pending")
        try:
            page = max(1, int(request.args.get("page", 1)))
            limit = min(100, max(1, int(request.args.get("limit", 20))))
        except (ValueError, TypeError):
            page, limit = 1, 20

        # Primary: read from DB
        jobs = []
        try:
            from src.db import fetchall as _db_all
            if status_filter == "all":
                rows = _db_all("SELECT data FROM jobs ORDER BY timestamp DESC")
            else:
                rows = _db_all("SELECT data FROM jobs WHERE status=? ORDER BY timestamp DESC", (status_filter,))
            jobs = [json.loads(r["data"]) for r in rows]
        except Exception as _e:
            app.logger.warning("DB jobs read failed, falling back to filesystem: %s", _e)

        # Fallback: filesystem (for jobs created before DB migration)
        if not jobs and os.path.isdir(LOGS_DIR):
            for fname in os.listdir(LOGS_DIR):
                if not fname.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(LOGS_DIR, fname), "r", encoding="utf-8") as f:
                        job = json.load(f)
                except Exception:
                    continue
                if isinstance(job, dict) and (status_filter == "all" or job.get("status") == status_filter):
                    jobs.append(job)
            jobs.sort(key=lambda j: j.get("timestamp", "") or "", reverse=True)

        total = len(jobs)
        start = (page - 1) * limit
        return jsonify({"jobs": jobs[start: start + limit], "total": total, "page": page, "limit": limit})
    except Exception as e:
        app.logger.error("api_jobs error: %s", e, exc_info=True)
        return jsonify({"error": "Fehler beim Laden der Jobs"}), 500


@app.route("/api/jobs/<job_id>/download")
@api_login_required
def api_job_download(job_id):
    """Download a single approved job as .docx."""
    job = _load_job(job_id)
    if not job:
        return jsonify({"error": "Job nicht gefunden"}), 404

    # Return cached DOCX if available
    docx_path = os.path.join(LOGS_DIR, f"{job_id}.docx")
    if os.path.exists(docx_path):
        with open(docx_path, "rb") as f:
            docx_bytes = f.read()
    else:
        try:
            from src.docx_creator import create_expose_docx_bytes
            from src.models import PropertyInput
            prop = PropertyInput(
                property_id=job.get("property_id", job_id),
                address=job.get("address", job.get("property_id", "")),
                city=job.get("city", ""),
                zip_code=job.get("zip_code", ""),
                property_type=job.get("property_type", "Immobilie"),
                size_sqm=float(job.get("size_sqm") or 0),
                rooms=float(job.get("rooms") or 0),
                purchase_price=job.get("purchase_price") or None,
                monthly_rent=job.get("monthly_rent") or None,
                year_built=job.get("year_built") or None,
                energy_class=job.get("energy_class") or None,
                features=job.get("features") or [],
            )
            docx_bytes = create_expose_docx_bytes(
                property_data=prop,
                expose_text=job.get("expose_text", ""),
            )
        except Exception as e:
            app.logger.error("DOCX generation for download failed: %s", e)
            return jsonify({"error": f"DOCX konnte nicht erstellt werden: {e}"}), 500


    filename = f"Expose_{job_id}.docx"
    return Response(
        docx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/jobs/export")
@api_login_required
def api_jobs_export():
    """Export all approved jobs as a ZIP of DOCX files."""
    import zipfile
    import io as _io
    try:
        status_filter = request.args.get("status", "approved")
        fmt = request.args.get("format", "zip")

        jobs = []
        try:
            from src.db import fetchall as _db_all
            if status_filter == "all":
                rows = _db_all("SELECT data FROM jobs ORDER BY timestamp DESC")
            else:
                rows = _db_all("SELECT data FROM jobs WHERE status=? ORDER BY timestamp DESC", (status_filter,))
            jobs = [json.loads(r["data"]) for r in rows]
        except Exception as _e:
            app.logger.warning("DB export fallback: %s", _e)

        if not jobs and os.path.isdir(LOGS_DIR):
            for fname in os.listdir(LOGS_DIR):
                if not fname.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(LOGS_DIR, fname), "r", encoding="utf-8") as f:
                        job = json.load(f)
                    if isinstance(job, dict) and (status_filter == "all" or job.get("status") == status_filter):
                        jobs.append(job)
                except Exception:
                    continue
            jobs.sort(key=lambda j: j.get("timestamp", "") or "", reverse=True)

        if not jobs:
            return jsonify({"error": f"Keine Jobs mit Status '{status_filter}' gefunden"}), 404

        if fmt == "json":
            return Response(
                json.dumps(jobs, ensure_ascii=False, indent=2),
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename=immo-ai-{status_filter}.json"},
            )

        # Build ZIP with DOCX per job
        from src.docx_creator import create_expose_docx_bytes
        from src.models import PropertyInput
        zip_buf = _io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for job in jobs:
                job_id = job.get("job_id", "unknown")
                prop_id = job.get("property_id", job_id)

                # Use cached DOCX if available
                cached = os.path.join(LOGS_DIR, f"{job_id}.docx")
                if os.path.exists(cached):
                    with open(cached, "rb") as f:
                        docx_bytes = f.read()
                else:
                    try:
                        prop = PropertyInput(
                            property_id=prop_id,
                            address=job.get("address", prop_id),
                            city=job.get("city", ""),
                            zip_code=job.get("zip_code", ""),
                            property_type=job.get("property_type", "Immobilie"),
                            size_sqm=float(job.get("size_sqm") or 0),
                            rooms=float(job.get("rooms") or 0),
                            purchase_price=job.get("purchase_price") or None,
                            monthly_rent=job.get("monthly_rent") or None,
                            year_built=job.get("year_built") or None,
                            energy_class=job.get("energy_class") or None,
                            features=job.get("features") or [],
                        )
                        docx_bytes = create_expose_docx_bytes(
                            property_data=prop,
                            expose_text=job.get("expose_text", ""),
                        )
                    except Exception as e:
                        app.logger.warning("DOCX failed for %s: %s", job_id, e)
                        continue

                safe_name = f"Expose_{prop_id}_{job_id}.docx".replace("/", "-").replace(" ", "_")
                zf.writestr(safe_name, docx_bytes)

        zip_buf.seek(0)
        return Response(
            zip_buf.read(),
            mimetype="application/zip",
            headers={"Content-Disposition": f"attachment; filename=immo-ai-expose-{status_filter}.zip"},
        )
    except Exception as e:
        app.logger.error("api_jobs_export error: %s", e, exc_info=True)
        return jsonify({"error": "Export fehlgeschlagen"}), 500


@app.route("/api/jobs/<job_id>", methods=["PATCH"])
@api_login_required
def api_patch_job(job_id):
    data = request.get_json()
    job = _load_job(job_id)
    if not job:
        return jsonify({"error": "Job nicht gefunden"}), 404
    if "expose_text" in data:
        job["expose_text"] = str(data["expose_text"])
    _update_job_in_db(job_id, {"expose_text": job["expose_text"]})
    try:
        path = os.path.join(LOGS_DIR, f"{job_id}.json")
        if os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/review/<job_id>", methods=["POST"])
@limiter.limit("30 per minute")
@api_login_required
def api_review(job_id):
    data = request.get_json()
    action = data.get("action")
    reviewer = data.get("reviewer", "").strip() or session.get("username", "Anonym")
    note = data.get("note", "").strip()

    job = _load_job(job_id)
    if not job:
        return jsonify({"error": "Job nicht gefunden"}), 404

    if action == "approve":
        job["status"] = "approved"
        job["reviewed_by"] = reviewer
        job["review_note"] = None

        # Resolve recipient email
        from src.config import SMTP_USER, SMTP_PASSWORD, ADMIN_EMAIL
        creator = job.get("created_by") or ""
        agent_email = (get_user_email(creator) if creator else "") or ADMIN_EMAIL
        if not agent_email and "@" in reviewer:
            agent_email = reviewer
        email_configured = bool(SMTP_USER and SMTP_PASSWORD)

        # Build DOCX for attachment and download
        docx_bytes = b""
        try:
            from src.docx_creator import create_expose_docx_bytes
            from src.models import PropertyInput
            prop = PropertyInput(
                property_id=job.get("property_id", job_id),
                address=job.get("address", job.get("property_id", "")),
                city=job.get("city", ""),
                zip_code=job.get("zip_code", ""),
                property_type=job.get("property_type", "Immobilie"),
                size_sqm=float(job.get("size_sqm") or 0),
                rooms=float(job.get("rooms") or 0),
                purchase_price=job.get("purchase_price") or None,
                monthly_rent=job.get("monthly_rent") or None,
                year_built=job.get("year_built") or None,
                energy_class=job.get("energy_class") or None,
                features=job.get("features") or [],
            )
            docx_bytes = create_expose_docx_bytes(
                property_data=prop,
                expose_text=job.get("expose_text", ""),
                agent_email=agent_email or None,
            )
            # Cache DOCX in logs dir for later downloads (best-effort)
            try:
                docx_path = os.path.join(LOGS_DIR, f"{job_id}.docx")
                with open(docx_path, "wb") as f:
                    f.write(docx_bytes)
            except Exception:
                pass
        except Exception as e:
            app.logger.warning("DOCX generation failed for job %s: %s", job_id, e)

        # Send approval email with DOCX attachment
        email_sent = False
        email_error = ""
        if email_configured and agent_email:
            try:
                from src.email_client import send_expose_approved
                app_url = request.host_url.rstrip("/")
                send_expose_approved(
                    agent_email=agent_email,
                    job_id=job_id,
                    property_id=job.get("property_id", job_id),
                    expose_text=job.get("expose_text", ""),
                    docx_bytes=docx_bytes,
                    app_url=app_url,
                )
                email_sent = True
                app.logger.info("Approval email sent to %s for job %s", agent_email, job_id)
            except Exception as e:
                email_error = str(e)
                app.logger.error("Email send failed for job %s: %s", job_id, e)
        else:
            if not email_configured:
                email_error = "SMTP nicht konfiguriert (SMTP_USER/SMTP_PASSWORD in .env setzen)"
            elif not agent_email:
                email_error = "Keine E-Mail-Adresse gefunden (ADMIN_EMAIL in .env setzen)"

    elif action == "reject":
        job["status"] = "rejected"
        job["reviewed_by"] = reviewer
        job["review_note"] = note or "Kein Grund angegeben"
    else:
        return jsonify({"error": "Ungültige Aktion"}), 400

    _update_job_in_db(job_id, {"status": job["status"]})
    try:
        path = os.path.join(LOGS_DIR, f"{job_id}.json")
        if os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    app.logger.info("Job %s %sd by %s", job_id, action, reviewer)

    response = {"ok": True, "status": job["status"]}
    if action == "approve":
        response["email_sent"] = email_sent
        response["email_to"] = agent_email if email_sent else ""
        response["email_error"] = email_error
    return jsonify(response)


# ── Automation webhook ────────────────────────────────────────────────────────

@app.route("/api/automation/trigger", methods=["POST"])
@api_login_required
def api_automation_trigger():
    """
    Webhook endpoint for Google Apps Script to trigger the automation pipeline.
    Runs one poll cycle synchronously (suitable for small batches).
    For production, use run_automation.py daemon instead.
    """
    import threading

    secret = request.headers.get("X-Webhook-Secret", "")
    from src.config import AUTOMATION_WEBHOOK_SECRET
    if AUTOMATION_WEBHOOK_SECRET and secret != AUTOMATION_WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    def _run():
        try:
            from src.automation import poll_and_process
            n = poll_and_process()
            app.logger.info("Webhook-triggered cycle complete: %d rows", n)
        except Exception as e:
            app.logger.error("Webhook automation error: %s", e, exc_info=True)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "Automation pipeline gestartet."})


@app.route("/api/pipeline/logs")
@api_login_required
def api_pipeline_logs():
    """Return recent pipeline log entries for monitoring dashboard."""
    try:
        from src.pipeline_logger import get_recent_logs
        n_days = min(30, max(1, int(request.args.get("days", 7))))
        entries = get_recent_logs(n_days=n_days)
        return jsonify({"entries": entries, "total": len(entries)})
    except Exception as e:
        app.logger.error("Pipeline logs error: %s", e)
        return jsonify({"error": "Logs nicht verfügbar"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.logger.info("Starting Immo AI on port %d, LOGS_DIR=%s", port, LOGS_DIR)
    app.run(debug=False, host="0.0.0.0", port=port)
