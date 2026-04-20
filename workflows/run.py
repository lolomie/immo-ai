"""
Usage: python workflows/run.py --input docs/example_property.json
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import PropertyInput, JobResult
from src.generator import generate_expose
from src.validator import validate_expose


LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")


def run(input_path: str) -> None:
    # Load and validate input
    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    property_data = PropertyInput(**raw)

    print(f"[1/3] Generating exposé for property {property_data.property_id}...")
    expose_text = generate_expose(property_data)
    print("      Done.\n")

    print("[2/3] Validating for hallucinations...")
    validation = validate_expose(property_data, expose_text)
    if validation["hallucinated"]:
        print(f"      ⚠ Hallucination detected: {validation['details']}")
    else:
        print("      ✓ No hallucinations detected.")
    print()

    # Save job to logs/
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

    print(f"[3/3] Saved to {log_path}")
    print(f"\nJob ID: {job_id}  |  Status: pending  |  Run review.py to approve or reject.\n")

    if validation["hallucinated"]:
        print("NOTE: Hallucination was detected. Please review carefully before approving.\n")

    print("--- EXPOSÉ PREVIEW ---")
    print(expose_text)
    print("----------------------")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and validate an exposé.")
    parser.add_argument("--input", required=True, help="Path to property JSON file")
    args = parser.parse_args()
    run(args.input)
