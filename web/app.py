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

from src.generator import generate_expose, stream_expose
from src.models import JobResult, PropertyInput
from src.validator import validate_expose
try:
    from .auth import api_login_required, check_credentials, login_required
except ImportError:
    from auth import api_login_required, check_credentials, login_required

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

LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")


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
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.error("500 error: %s", e)
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
    if not os.path.isdir(LOGS_DIR):
        return jsonify({"jobs": [], "total": 0, "page": 1, "limit": 20})

    status_filter = request.args.get("status", "pending")
    page = max(1, int(request.args.get("page", 1)))
    limit = min(100, max(1, int(request.args.get("limit", 20))))

    jobs = []
    for fname in os.listdir(LOGS_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(LOGS_DIR, fname), "r", encoding="utf-8") as f:
                job = json.load(f)
        except Exception:
            continue
        if status_filter == "all" or job.get("status") == status_filter:
            jobs.append(job)

    jobs.sort(key=lambda j: j.get("timestamp", ""), reverse=True)
    total = len(jobs)
    start = (page - 1) * limit
    return jsonify({"jobs": jobs[start: start + limit], "total": total, "page": page, "limit": limit})


@app.route("/api/jobs/export")
@api_login_required
def api_jobs_export():
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
        if status_filter == "all" or job.get("status") == status_filter:
            jobs.append(job)

    jobs.sort(key=lambda j: j.get("timestamp", ""), reverse=True)
    return Response(
        json.dumps(jobs, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=immo-ai-{status_filter}.json"},
    )


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
        export_path = path.replace(".json", "_approved.txt")
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(job["expose_text"])
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.logger.info("Starting Immo AI on port %d, LOGS_DIR=%s", port, LOGS_DIR)
    app.run(debug=False, host="0.0.0.0", port=port)
