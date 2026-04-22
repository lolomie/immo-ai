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

from src.calendar_service import create_appointment, delete_appointment, get_appointments
from src.generator import generate_expose, stream_expose
from src.models import JobResult, PropertyInput
from src.validator import validate_expose
try:
    from .auth import api_login_required, check_credentials, login_required, admin_required, add_user, delete_user, list_users
except ImportError:
    from auth import api_login_required, check_credentials, login_required, admin_required, add_user, delete_user, list_users

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


def _parse_property(data: dict):
    if not data.get("property_id"):
        data["property_id"] = "WEB-" + str(uuid.uuid4())[:6].upper()
    if isinstance(data.get("features"), str):
        data["features"] = [f.strip() for f in data["features"].split(",") if f.strip()]
    for field in ("purchase_price", "monthly_rent", "year_built"):
        if data.get(field) in ("", None, 0):
            data[field] = None
    return PropertyInput(**data)


def _save_job(job: JobResult):
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, f"{job.job_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job.model_dump(), f, ensure_ascii=False, indent=2)


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
            app.logger.info("Login: %s", username)
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


# ── Pages (protected) ─────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", auth_required=False)


@app.route("/generate")
@login_required
def generate_page():
    return render_template("generate.html", auth_required=False)


@app.route("/review")
@login_required
def review_page():
    return render_template("review.html", auth_required=False)


@app.route("/calendar")
@login_required
def calendar_page():
    return render_template("calendar.html", auth_required=False)


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
    name     = data.get("name", "").strip()
    email    = data.get("email", "").strip()
    company  = data.get("company", "").strip()
    phone    = data.get("phone", "").strip()
    plan_key = data.get("plan", "pro").strip()

    if not name or not email:
        return jsonify({"error": "Name und E-Mail sind Pflichtfelder."}), 400

    # Notify admin of new signup request
    try:
        from src.email_client import _build_message, _send
        from src.plans import get_plan
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
    <tr><td style="padding:8px;background:#f1f5f9;font-weight:600;">Gewünschter Plan</td><td style="padding:8px;font-weight:700;color:#2563eb;">{plan['name']} ({plan['monthly_price']} €/Monat)</td></tr>
  </table>
</body></html>"""
        body_text = f"Demo-Anfrage\nName: {name}\nEmail: {email}\nPlan: {plan['name']}"
        from src.config import EMAIL_FROM
        _send(EMAIL_FROM, _build_message(EMAIL_FROM, subject, body_html, body_text))
        app.logger.info("Signup request from %s (%s), plan=%s", name, email, plan_key)
    except Exception as e:
        app.logger.error("Signup notification failed: %s", e)

    return jsonify({"ok": True, "message": "Vielen Dank! Wir melden uns innerhalb von 24 Stunden."})


@app.route("/admin/users")
@admin_required
def admin_users_page():
    users = list_users()
    return render_template("admin_users.html", users=users, auth_required=False)


# ── Admin User API ────────────────────────────────────────────────────────────

@app.route("/api/admin/users", methods=["GET"])
@admin_required
def api_admin_list_users():
    return jsonify({"users": list_users()})


@app.route("/api/admin/users", methods=["POST"])
@admin_required
def api_admin_add_user():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    try:
        add_user(username, password)
        app.logger.info("User created: %s by %s", username, session.get("username"))
        return jsonify({"ok": True, "username": username})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/admin/users/<username>", methods=["DELETE"])
@admin_required
def api_admin_delete_user(username):
    try:
        delete_user(username)
        app.logger.info("User deleted: %s by %s", username, session.get("username"))
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ── Calendar API ──────────────────────────────────────────────────────────────

@app.route("/calendar/create", methods=["POST"])
@api_login_required
def calendar_create():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Kein JSON erhalten"}), 400
    try:
        appt = create_appointment(data)

        # Send confirmation email + sync to Google Calendar in background
        def _post_create():
            try:
                from src.email_client import send_appointment_confirmation
                lead_email = data.get("lead_email", "").strip()
                if lead_email:
                    send_appointment_confirmation(
                        lead_email=lead_email,
                        lead_name=data.get("lead_name", "Interessent"),
                        agent_name=data.get("agent_name", session.get("username", "Ihr Makler")),
                        property_address=data.get("property_address", data.get("title", "")),
                        datetime_start=data.get("start_time", ""),
                        appointment_id=appt.appointment_id,
                    )
                    app.logger.info("Confirmation email sent for %s", appt.appointment_id)
            except Exception as e:
                app.logger.error("Post-create calendar task failed: %s", e)

        import threading
        threading.Thread(target=_post_create, daemon=True).start()

        return jsonify({"ok": True, "appointment": appt.to_dict()})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        app.logger.error("Calendar create failed: %s", e)
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


# ── API: Generate ─────────────────────────────────────────────────────────────

@app.route("/api/generate", methods=["POST"])
@limiter.limit("10 per minute")
@api_login_required
def api_generate():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Kein JSON erhalten"}), 400
    try:
        property_data = _parse_property(data)
    except Exception as e:
        return jsonify({"error": f"Ungültige Eingabe: {e}"}), 400
    try:
        expose_text = generate_expose(property_data)
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
    _save_job(job)
    app.logger.info("Job created: %s for %s", job.job_id, property_data.property_id)
    return jsonify(job.model_dump())


@app.route("/api/generate/stream", methods=["POST"])
@limiter.limit("10 per minute")
@api_login_required
def api_generate_stream():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Kein JSON erhalten"}), 400
    try:
        property_data = _parse_property(data)
    except Exception as e:
        return jsonify({"error": f"Ungültige Eingabe: {e}"}), 400

    job_id = str(uuid.uuid4())[:8]

    def generate():
        full_text = []
        try:
            for chunk in stream_expose(property_data):
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
            )
            _save_job(job)
            app.logger.info("Stream job: %s for %s", job_id, property_data.property_id)
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
        if not os.path.isdir(LOGS_DIR):
            return jsonify({"jobs": [], "total": 0, "page": 1, "limit": 20})

        status_filter = request.args.get("status", "pending")
        try:
            page = max(1, int(request.args.get("page", 1)))
            limit = min(100, max(1, int(request.args.get("limit", 20))))
        except (ValueError, TypeError):
            page, limit = 1, 20

        jobs = []
        for fname in os.listdir(LOGS_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(LOGS_DIR, fname), "r", encoding="utf-8") as f:
                    job = json.load(f)
            except Exception:
                continue
            if not isinstance(job, dict):
                continue
            if status_filter == "all" or job.get("status") == status_filter:
                jobs.append(job)

        jobs.sort(key=lambda j: j.get("timestamp", "") or "", reverse=True)
        total = len(jobs)
        start = (page - 1) * limit
        return jsonify({"jobs": jobs[start: start + limit], "total": total, "page": page, "limit": limit})
    except Exception as e:
        app.logger.error("api_jobs error: %s", e, exc_info=True)
        return jsonify({"error": "Fehler beim Laden der Jobs"}), 500


@app.route("/api/jobs/export")
@api_login_required
def api_jobs_export():
    try:
        if not os.path.isdir(LOGS_DIR):
            return Response("[]", mimetype="application/json")

        status_filter = request.args.get("status", "approved")
        jobs = []
        for fname in os.listdir(LOGS_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(LOGS_DIR, fname), "r", encoding="utf-8") as f:
                    job = json.load(f)
            except Exception:
                continue
            if not isinstance(job, dict):
                continue
            if status_filter == "all" or job.get("status") == status_filter:
                jobs.append(job)

        jobs.sort(key=lambda j: j.get("timestamp", "") or "", reverse=True)
        return Response(
            json.dumps(jobs, ensure_ascii=False, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename=immo-ai-{status_filter}.json"},
        )
    except Exception as e:
        app.logger.error("api_jobs_export error: %s", e, exc_info=True)
        return jsonify({"error": "Export fehlgeschlagen"}), 500


@app.route("/api/jobs/<job_id>", methods=["PATCH"])
@api_login_required
def api_patch_job(job_id):
    data = request.get_json()
    path = os.path.join(LOGS_DIR, f"{job_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Job nicht gefunden"}), 404
    with open(path, "r", encoding="utf-8") as f:
        job = json.load(f)
    if "expose_text" in data:
        job["expose_text"] = str(data["expose_text"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


@app.route("/api/review/<job_id>", methods=["POST"])
@limiter.limit("30 per minute")
@api_login_required
def api_review(job_id):
    data = request.get_json()
    action = data.get("action")
    reviewer = data.get("reviewer", "").strip() or session.get("username", "Anonym")
    note = data.get("note", "").strip()

    path = os.path.join(LOGS_DIR, f"{job_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Job nicht gefunden"}), 404

    with open(path, "r", encoding="utf-8") as f:
        job = json.load(f)

    if action == "approve":
        job["status"] = "approved"
        job["reviewed_by"] = reviewer
        job["review_note"] = None

        # Generate .docx + upload to Drive + send email in background
        def _deliver():
            try:
                from src.docx_creator import create_expose_docx_bytes, expose_filename
                from src.drive_client import upload_docx_bytes
                from src.email_client import send_expose_ready
                from src.models import PropertyInput

                prop = PropertyInput(
                    property_id=job.get("property_id", job_id),
                    address=job.get("property_id", ""),
                    city="", zip_code="", property_type="Wohnung",
                    size_sqm=0, rooms=0,
                )
                docx_bytes = create_expose_docx_bytes(prop, job["expose_text"], reviewer)
                fname = expose_filename(prop)
                doc_url = upload_docx_bytes(docx_bytes, fname)

                # save URL back to job file
                job["doc_url"] = doc_url
                with open(path, "w", encoding="utf-8") as _f:
                    json.dump(job, _f, ensure_ascii=False, indent=2)

                # notify reviewer by email
                send_expose_ready(
                    agent_email=reviewer if "@" in reviewer else "",
                    property_address=job.get("property_id", job_id),
                    property_id=job.get("property_id", job_id),
                    doc_url=doc_url,
                    job_id=job_id,
                )
                app.logger.info("Approved job %s delivered: %s", job_id, doc_url)
            except Exception as e:
                app.logger.error("Delivery after approval failed for %s: %s", job_id, e, exc_info=True)

        import threading
        threading.Thread(target=_deliver, daemon=True).start()

    elif action == "reject":
        job["status"] = "rejected"
        job["reviewed_by"] = reviewer
        job["review_note"] = note or "Kein Grund angegeben"
    else:
        return jsonify({"error": "Ungültige Aktion"}), 400

    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)

    app.logger.info("Job %s %sd by %s", job_id, action, reviewer)
    return jsonify({"ok": True, "status": job["status"]})


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
