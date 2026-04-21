"""
Main automation orchestrator.
Processes pending rows from Google Sheets through the full pipeline:
  Sheets → Groq (generation) → Claude (validation) → Drive (.docx) → Email

Also handles Termine sync to Google Calendar and 24h reminders.

Design principles:
- Never fail silently: every error is logged and written back to the sheet
- Idempotency: status is set to "processing" before any API call to avoid
  double-processing if the daemon restarts mid-run
- Claude always validates regardless of LLM_PROVIDER (quality gate)
"""

import logging
import time
import uuid
from typing import Optional

from .config import ANTHROPIC_API_KEY, AUTOMATION_MAX_RETRIES
from .models import PropertyInput
from .pipeline_logger import PipelineLogger

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _retry(fn, retries: int = AUTOMATION_MAX_RETRIES, backoff: float = 2.0):
    """Call fn() up to `retries` times with exponential backoff."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                sleep_for = backoff ** attempt
                logger.warning("Attempt %d/%d failed (%s) — retrying in %.0fs", attempt, retries, exc, sleep_for)
                time.sleep(sleep_for)
    raise last_exc


def _build_property_input(row: dict) -> PropertyInput:
    """Parse a Google Sheets row dict into a PropertyInput model."""
    def _float(v) -> Optional[float]:
        try:
            return float(str(v).replace(",", ".")) if str(v).strip() else None
        except ValueError:
            return None

    def _int(v) -> Optional[int]:
        try:
            return int(str(v).strip()) if str(v).strip() else None
        except ValueError:
            return None

    features_raw = str(row.get("features", "")).strip()
    features = [f.strip() for f in features_raw.split(",") if f.strip()] if features_raw else []

    prop_id = str(row.get("property_id", "")).strip() or ("WEB-" + str(uuid.uuid4())[:6].upper())

    return PropertyInput(
        property_id=prop_id,
        address=str(row.get("property_address", "")).strip(),
        city=str(row.get("city", "")).strip(),
        zip_code=str(row.get("zip_code", "")).strip(),
        property_type=str(row.get("property_type", "Wohnung")).strip(),
        size_sqm=_float(row.get("size_sqm")) or 0.0,
        rooms=_float(row.get("rooms")) or 0.0,
        purchase_price=_float(row.get("purchase_price")),
        monthly_rent=_float(row.get("monthly_rent")),
        year_built=_int(row.get("year_built")),
        energy_class=str(row.get("energy_class", "")).strip() or None,
        features=features,
    )


def _validate_required_fields(row: dict) -> Optional[str]:
    """Return an error message if required fields are missing, else None."""
    required = ["property_address", "city", "zip_code", "property_type", "size_sqm", "rooms", "agent_email"]
    missing = [f for f in required if not str(row.get(f, "")).strip()]
    if missing:
        return f"Pflichtfelder fehlen: {', '.join(missing)}"
    return None


# ── Exposé pipeline ───────────────────────────────────────────────────────────

def process_expose_row(row: dict) -> None:
    """
    Process a single pending Exposé-Inputs row through the full pipeline.
    All state changes are written back to the sheet immediately.
    """
    from . import sheets_client, drive_client, docx_creator, email_client
    from .generator import generate_expose
    from .validator import validate_expose_with_claude

    expose_id = str(row.get("expose_id", "")).strip() or str(uuid.uuid4())
    run_id = str(uuid.uuid4())[:8]
    row_index = row["_row_index"]
    agent_email = str(row.get("agent_email", "")).strip()

    log = PipelineLogger(expose_id=expose_id, run_id=run_id)

    try:
        # Step 0: validate required fields
        field_error = _validate_required_fields(row)
        if field_error:
            log.step("field_validation", "error", error=field_error)
            sheets_client.update_expose_row(row_index, {"status": "error"})
            if agent_email:
                email_client.send_expose_invalid(
                    agent_email=agent_email,
                    property_address=row.get("property_address", "?"),
                    property_id=row.get("property_id", expose_id),
                    hallucination_details=field_error,
                )
            return

        # Step 1: mark as processing (idempotency guard)
        sheets_client.update_expose_status(row_index, "processing")
        log.start({k: v for k, v in row.items() if not k.startswith("_")})

        # Step 2: build model
        prop = _build_property_input(row)
        log.step("model_build", "ok", detail={"property_id": prop.property_id})

        # Step 3: generate exposé via Groq (or configured provider)
        log.step("generation_start", "ok")
        expose_text = _retry(lambda: generate_expose(prop))
        log.step("generation_done", "ok", detail={"chars": len(expose_text)})
        sheets_client.update_expose_status(row_index, "generated")

        # Step 4: validate via Claude ALWAYS (quality gate — force anthropic)
        log.step("validation_start", "ok")
        if not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set — skipping Claude validation (RISK: no quality gate)")
            validation = {"hallucinated": False, "details": "Validation skipped: no Anthropic key"}
        else:
            validation = _retry(lambda: validate_expose_with_claude(prop, expose_text))

        log.step(
            "validation_done",
            "ok" if not validation["hallucinated"] else "hallucination",
            detail=validation,
        )

        if validation["hallucinated"]:
            sheets_client.update_expose_row(row_index, {"status": "invalid"})
            if agent_email:
                email_client.send_expose_invalid(
                    agent_email=agent_email,
                    property_address=prop.address,
                    property_id=prop.property_id,
                    hallucination_details=validation["details"],
                )
            log.finish("invalid")
            return

        sheets_client.update_expose_status(row_index, "validated")

        # Step 5: create .docx
        log.step("docx_create", "ok")
        target_group = str(row.get("target_group", "")).strip() or None
        docx_bytes = docx_creator.create_expose_docx_bytes(
            property_data=prop,
            expose_text=expose_text,
            agent_email=agent_email,
            target_group=target_group,
        )
        filename = docx_creator.expose_filename(prop)

        # Step 6: upload to Google Drive
        log.step("drive_upload_start", "ok")
        doc_url = _retry(lambda: drive_client.upload_docx_bytes(docx_bytes, filename))
        log.step("drive_upload_done", "ok", detail={"url": doc_url})

        # Step 7: send email notification to agent
        job_id = run_id
        if agent_email:
            try:
                email_client.send_expose_ready(
                    agent_email=agent_email,
                    property_address=prop.address,
                    property_id=prop.property_id,
                    doc_url=doc_url,
                    job_id=job_id,
                )
                log.step("email_sent", "ok", detail={"to": agent_email})
                email_sent = "TRUE"
            except Exception as e:
                log.error("email_send", e)
                email_sent = "FALSE"
        else:
            log.step("email_sent", "skipped", detail="no agent_email")
            email_sent = "FALSE"

        # Step 8: write final state back to sheet
        sheets_client.update_expose_row(row_index, {
            "status": "completed",
            "job_id": job_id,
            "doc_url": doc_url,
            "email_sent": email_sent,
        })
        log.finish("completed", doc_url=doc_url)
        logger.info("Pipeline completed for expose_id=%s", expose_id)

    except Exception as exc:
        log.error("pipeline_fatal", exc)
        try:
            sheets_client.update_expose_row(row_index, {"status": "error"})
        except Exception:
            pass
        logger.error("Pipeline failed for expose_id=%s: %s", expose_id, exc, exc_info=True)


# ── Termine / calendar sync ───────────────────────────────────────────────────

def sync_pending_termine() -> None:
    """
    Sync all 'scheduled' Termine rows that have no gcal_event_id yet
    to Google Calendar, then send confirmation emails.
    """
    from . import sheets_client, gcal_client, email_client

    try:
        pending = sheets_client.get_pending_termine()
    except Exception as e:
        logger.error("Failed to fetch pending Termine: %s", e)
        return

    for termin in pending:
        row_index = termin["_row_index"]
        appointment_id = termin.get("appointment_id", "")
        try:
            gcal_id = gcal_client.sync_appointment_to_gcal(termin)
            updates: dict = {"gcal_event_id": gcal_id, "status": "confirmed"}

            # Send confirmation email if lead email available via Leads sheet
            lead = None
            lead_id = termin.get("lead_id", "").strip()
            if lead_id:
                try:
                    lead = sheets_client.get_lead_by_id(lead_id)
                except Exception:
                    pass

            if lead and lead.get("email") and not termin.get("confirmation_sent", "").upper() in ("TRUE", "1"):
                try:
                    email_client.send_appointment_confirmation(
                        lead_email=lead["email"],
                        lead_name=lead.get("name", "Interessent"),
                        agent_name=termin.get("agent_name", "Ihr Makler"),
                        property_address=termin.get("property_address", ""),
                        datetime_start=termin.get("datetime_start", ""),
                        appointment_id=appointment_id,
                    )
                    updates["confirmation_sent"] = "TRUE"
                except Exception as e:
                    logger.error("Confirmation email failed for %s: %s", appointment_id, e)

            sheets_client.update_termin_row(row_index, updates)
            logger.info("Termin %s synced to GCal: %s", appointment_id, gcal_id)

        except Exception as e:
            logger.error("GCal sync failed for appointment %s: %s", appointment_id, e)


def send_pending_reminders() -> None:
    """Send 24h reminders for appointments due tomorrow."""
    from . import sheets_client, email_client

    try:
        due = sheets_client.get_termine_needing_reminder()
    except Exception as e:
        logger.error("Failed to fetch reminder Termine: %s", e)
        return

    for termin in due:
        row_index = termin["_row_index"]
        lead_id = termin.get("lead_id", "").strip()
        lead = None
        if lead_id:
            try:
                lead = sheets_client.get_lead_by_id(lead_id)
            except Exception:
                pass

        if not lead or not lead.get("email"):
            continue

        try:
            email_client.send_appointment_reminder(
                lead_email=lead["email"],
                lead_name=lead.get("name", "Interessent"),
                agent_name=termin.get("agent_name", "Ihr Makler"),
                property_address=termin.get("property_address", ""),
                datetime_start=termin.get("datetime_start", ""),
            )
            sheets_client.update_termin_row(row_index, {"reminder_sent": "TRUE"})
            logger.info("Reminder sent for appointment %s", termin.get("appointment_id"))
        except Exception as e:
            logger.error("Reminder email failed for %s: %s", termin.get("appointment_id"), e)


# ── Main poll cycle ───────────────────────────────────────────────────────────

def poll_and_process() -> int:
    """
    Run one complete poll cycle:
    - Process pending exposé rows
    - Sync pending Termine to GCal
    - Send 24h reminders

    Returns number of rows processed.
    """
    from . import sheets_client

    processed = 0

    # Process exposé pipeline
    try:
        pending = sheets_client.get_pending_expose_rows()
        logger.info("Poll cycle: %d pending exposé rows found", len(pending))
        for row in pending:
            process_expose_row(row)
            processed += 1
    except Exception as e:
        logger.error("Error fetching pending expose rows: %s", e, exc_info=True)

    # Calendar sync
    try:
        sync_pending_termine()
    except Exception as e:
        logger.error("Calendar sync error: %s", e, exc_info=True)

    # Reminders
    try:
        send_pending_reminders()
    except Exception as e:
        logger.error("Reminder send error: %s", e, exc_info=True)

    return processed
