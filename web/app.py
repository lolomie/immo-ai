import json
import os
import sys
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.generator import generate_expose
from src.models import JobResult, PropertyInput
from src.validator import validate_expose

app = Flask(__name__)

LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate")
def generate_page():
    return render_template("generate.html")


@app.route("/review")
def review_page():
    return render_template("review.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Kein JSON erhalten"}), 400

    if not data.get("property_id"):
        data["property_id"] = "WEB-" + str(uuid.uuid4())[:6].upper()

    if isinstance(data.get("features"), str):
        data["features"] = [f.strip() for f in data["features"].split(",") if f.strip()]

    for field in ("purchase_price", "monthly_rent", "year_built"):
        if data.get(field) in ("", None, 0):
            data[field] = None

    try:
        property_data = PropertyInput(**data)
    except Exception as e:
        return jsonify({"error": f"Ungültige Eingabe: {e}"}), 400

    try:
        expose_text = generate_expose(property_data)
        validation = validate_expose(property_data, expose_text)
    except Exception as e:
        return jsonify({"error": f"Generierung fehlgeschlagen: {e}"}), 500

    job_id = str(uuid.uuid4())[:8]
    job = JobResult(
        job_id=job_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status="pending",
        property_id=property_data.property_id,
        expose_text=expose_text,
        hallucination_detected=validation["hallucinated"],
        hallucination_details=validation["details"],
    )

    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f"{job_id}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(job.model_dump(), f, ensure_ascii=False, indent=2)

    return jsonify(job.model_dump())


@app.route("/api/jobs")
def api_jobs():
    if not os.path.isdir(LOGS_DIR):
        return jsonify([])
    jobs = []
    for fname in os.listdir(LOGS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(LOGS_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            job = json.load(f)
        if job.get("status") == "pending":
            jobs.append(job)
    jobs.sort(key=lambda j: j.get("timestamp", ""), reverse=True)
    return jsonify(jobs)


@app.route("/api/review/<job_id>", methods=["POST"])
def api_review(job_id):
    data = request.get_json()
    action = data.get("action")
    reviewer = data.get("reviewer", "").strip() or "Anonym"
    note = data.get("note", "").strip()

    log_path = os.path.join(LOGS_DIR, f"{job_id}.json")
    if not os.path.exists(log_path):
        return jsonify({"error": "Job nicht gefunden"}), 404

    with open(log_path, "r", encoding="utf-8") as f:
        job = json.load(f)

    if action == "approve":
        job["status"] = "approved"
        job["reviewed_by"] = reviewer
        job["review_note"] = None
        export_path = log_path.replace(".json", "_approved.txt")
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(job["expose_text"])
    elif action == "reject":
        job["status"] = "rejected"
        job["reviewed_by"] = reviewer
        job["review_note"] = note or "Kein Grund angegeben"
    else:
        return jsonify({"error": "Ungültige Aktion"}), 400

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "status": job["status"]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
