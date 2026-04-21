"""
Google Sheets client.
Reads/writes the three tabs: Leads, Termine, Exposé-Inputs.
Uses a service account for server-to-server authentication.

Setup:
  1. Create a Google Cloud project.
  2. Enable Google Sheets API + Google Drive API.
  3. Create a service account, download the JSON key.
  4. Set GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/key.json in .env
     OR set GOOGLE_SERVICE_ACCOUNT_JSON=<inline JSON string>.
  5. Share your spreadsheet with the service account email (Editor).
  6. Set SHEETS_SPREADSHEET_ID=<your spreadsheet ID> in .env.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from .config import (
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    SHEETS_SPREADSHEET_ID,
)

logger = logging.getLogger(__name__)

# ── Column indices (0-based) for Exposé-Inputs sheet ─────────────────────────
COL = {
    "expose_id":       0,   # A
    "lead_id":         1,   # B
    "property_id":     2,   # C
    "property_address":3,   # D
    "city":            4,   # E
    "zip_code":        5,   # F
    "property_type":   6,   # G
    "size_sqm":        7,   # H
    "rooms":           8,   # I
    "year_built":      9,   # J
    "energy_class":    10,  # K
    "features":        11,  # L
    "purchase_price":  12,  # M
    "monthly_rent":    13,  # N
    "target_group":    14,  # O
    "agent_email":     15,  # P
    "status":          16,  # Q
    "job_id":          17,  # R
    "doc_url":         18,  # S
    "email_sent":      19,  # T
}

EXPOSE_HEADERS = [
    "expose_id", "lead_id", "property_id", "property_address", "city",
    "zip_code", "property_type", "size_sqm", "rooms", "year_built",
    "energy_class", "features", "purchase_price", "monthly_rent",
    "target_group", "agent_email", "status", "job_id", "doc_url", "email_sent",
]

TERMINE_HEADERS = [
    "appointment_id", "lead_id", "agent_name", "agent_email",
    "datetime_start", "datetime_end", "property_address", "status",
    "cal_event_id", "gcal_event_id", "confirmation_sent", "reminder_sent",
]

LEADS_HEADERS = [
    "lead_id", "name", "email", "phone", "address",
    "status", "created_at", "agent_email", "notes", "gdpr_consent",
]


def _get_client():
    """Return an authenticated gspread client."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        raise ImportError(
            "Google libraries not installed. Run: pip install gspread google-auth"
        ) from e

    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    if GOOGLE_SERVICE_ACCOUNT_JSON:
        info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    elif GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes)
    else:
        raise EnvironmentError(
            "Google service account not configured. Set GOOGLE_SERVICE_ACCOUNT_FILE "
            "or GOOGLE_SERVICE_ACCOUNT_JSON in .env"
        )

    return gspread.authorize(creds)


def _get_spreadsheet():
    if not SHEETS_SPREADSHEET_ID:
        raise EnvironmentError("SHEETS_SPREADSHEET_ID not set in .env")
    client = _get_client()
    return client.open_by_key(SHEETS_SPREADSHEET_ID)


def _row_to_dict(headers: list[str], row: list) -> dict:
    """Pad row to header length and zip into dict."""
    padded = row + [""] * max(0, len(headers) - len(row))
    return dict(zip(headers, padded))


# ── Exposé-Inputs ─────────────────────────────────────────────────────────────

def get_pending_expose_rows() -> list[dict]:
    """
    Return all rows in 'Exposé-Inputs' with status == 'pending'.
    Each dict also contains '_row_index' (1-based, including header).
    """
    sheet = _get_spreadsheet().worksheet("Exposé-Inputs")
    all_rows = sheet.get_all_values()
    if not all_rows:
        return []

    headers = all_rows[0]
    result = []
    for i, row in enumerate(all_rows[1:], start=2):
        data = _row_to_dict(headers, row)
        if data.get("status", "").strip().lower() == "pending":
            data["_row_index"] = i
            result.append(data)
    return result


def update_expose_status(row_index: int, status: str) -> None:
    """Update the status column (Q) of a given row."""
    sheet = _get_spreadsheet().worksheet("Exposé-Inputs")
    status_col = COL["status"] + 1  # gspread is 1-based
    sheet.update_cell(row_index, status_col, status)


def update_expose_row(row_index: int, updates: dict) -> None:
    """
    Write multiple fields back to the sheet.
    updates: {field_name: value, ...}
    """
    sheet = _get_spreadsheet().worksheet("Exposé-Inputs")
    for field, value in updates.items():
        if field not in COL:
            logger.warning("Unknown field '%s' — skipped", field)
            continue
        col = COL[field] + 1
        sheet.update_cell(row_index, col, str(value) if value is not None else "")


# ── Termine ───────────────────────────────────────────────────────────────────

def get_pending_termine() -> list[dict]:
    """Return Termine rows with status == 'scheduled' and no gcal_event_id."""
    sheet = _get_spreadsheet().worksheet("Termine")
    all_rows = sheet.get_all_values()
    if not all_rows:
        return []

    headers = all_rows[0]
    result = []
    for i, row in enumerate(all_rows[1:], start=2):
        data = _row_to_dict(headers, row)
        is_scheduled = data.get("status", "").strip().lower() == "scheduled"
        no_gcal = not data.get("gcal_event_id", "").strip()
        if is_scheduled and no_gcal:
            data["_row_index"] = i
            result.append(data)
    return result


def update_termin_row(row_index: int, updates: dict) -> None:
    TERMIN_COL = {h: i for i, h in enumerate(TERMINE_HEADERS)}
    sheet = _get_spreadsheet().worksheet("Termine")
    for field, value in updates.items():
        if field not in TERMIN_COL:
            continue
        sheet.update_cell(row_index, TERMIN_COL[field] + 1, str(value) if value is not None else "")


def get_termine_needing_reminder() -> list[dict]:
    """Return appointments where reminder_sent=FALSE and start is in ~24h."""
    from datetime import timedelta
    sheet = _get_spreadsheet().worksheet("Termine")
    all_rows = sheet.get_all_values()
    if not all_rows:
        return []

    headers = all_rows[0]
    now = datetime.now(timezone.utc)
    window_start = now + timedelta(hours=23)
    window_end = now + timedelta(hours=25)

    result = []
    for i, row in enumerate(all_rows[1:], start=2):
        data = _row_to_dict(headers, row)
        if data.get("reminder_sent", "").strip().upper() in ("TRUE", "1", "YES"):
            continue
        if data.get("status", "").strip().lower() not in ("scheduled", "confirmed"):
            continue
        dt_str = data.get("datetime_start", "").strip()
        if not dt_str:
            continue
        try:
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                from datetime import timezone as tz
                dt = dt.replace(tzinfo=tz.utc)
            if window_start <= dt <= window_end:
                data["_row_index"] = i
                result.append(data)
        except ValueError:
            pass
    return result


# ── Leads ─────────────────────────────────────────────────────────────────────

def get_lead_by_id(lead_id: str) -> Optional[dict]:
    sheet = _get_spreadsheet().worksheet("Leads")
    all_rows = sheet.get_all_values()
    if not all_rows:
        return None
    headers = all_rows[0]
    for row in all_rows[1:]:
        data = _row_to_dict(headers, row)
        if data.get("lead_id", "").strip() == lead_id.strip():
            return data
    return None


# ── Sheet initialization ──────────────────────────────────────────────────────

def ensure_sheet_headers() -> None:
    """
    Create the three tabs with correct headers if they don't exist.
    Safe to call repeatedly — skips tabs that already have headers.
    """
    ss = _get_spreadsheet()
    _ensure_tab(ss, "Leads", LEADS_HEADERS)
    _ensure_tab(ss, "Termine", TERMINE_HEADERS)
    _ensure_tab(ss, "Exposé-Inputs", EXPOSE_HEADERS)
    logger.info("Sheet headers verified.")


def _ensure_tab(ss, name: str, headers: list[str]) -> None:
    try:
        ws = ss.worksheet(name)
    except Exception:
        ws = ss.add_worksheet(title=name, rows=1000, cols=len(headers))

    existing = ws.row_values(1)
    if existing != headers:
        ws.update("A1", [headers])
        logger.info("Headers written to tab '%s'", name)
