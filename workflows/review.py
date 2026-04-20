"""
Usage: python workflows/review.py
Lists all pending jobs and prompts human to approve or reject each one.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")


def load_pending() -> list:
    if not os.path.isdir(LOGS_DIR):
        return []
    jobs = []
    for fname in os.listdir(LOGS_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(LOGS_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            job = json.load(f)
        if job.get("status") == "pending":
            jobs.append((path, job))
    return jobs


def save_job(path: str, job: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)


def review() -> None:
    pending = load_pending()

    if not pending:
        print("No pending jobs found.")
        return

    print(f"Found {len(pending)} pending job(s).\n")

    for path, job in pending:
        print("=" * 60)
        print(f"Job ID:     {job['job_id']}")
        print(f"Property:   {job['property_id']}")
        print(f"Created:    {job['timestamp']}")
        print(f"Hallucination: {'⚠ YES — ' + job['hallucination_details'] if job['hallucination_detected'] else '✓ None detected'}")
        print()
        print("--- EXPOSÉ ---")
        print(job["expose_text"])
        print("--------------")
        print()

        while True:
            choice = input("[a]pprove / [r]eject / [s]kip: ").strip().lower()
            if choice in ("a", "r", "s"):
                break
            print("Invalid input. Enter a, r, or s.")

        if choice == "s":
            print("Skipped.\n")
            continue

        reviewer = input("Your name (for audit): ").strip() or "anonymous"

        if choice == "a":
            job["status"] = "approved"
            job["reviewed_by"] = reviewer
            job["review_note"] = None
            save_job(path, job)

            # Save clean exposé text alongside the job file
            export_path = path.replace(".json", "_approved.txt")
            with open(export_path, "w", encoding="utf-8") as f:
                f.write(job["expose_text"])

            print(f"✓ Approved. Exposé saved to {export_path}\n")

        elif choice == "r":
            reason = input("Rejection reason: ").strip() or "No reason given"
            job["status"] = "rejected"
            job["reviewed_by"] = reviewer
            job["review_note"] = reason
            save_job(path, job)
            print(f"✗ Rejected: {reason}\n")

    print("Review complete.")


if __name__ == "__main__":
    review()
