"""
Google Calendar client.
Creates and updates calendar events for property viewings.
Uses the same service account credentials as sheets_client.py.

The service account must be granted access to the target calendar:
  Google Calendar → Settings → Share with specific people → add service account email.
Or use "primary" calendar of the service account (less common for business use).

Set GCAL_CALENDAR_ID=<calendar ID> in .env (e.g. "user@domain.com" or "primary").
"""

import logging
import os
from typing import Optional

from .config import (
    GCAL_CALENDAR_ID,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SERVICE_ACCOUNT_JSON,
)

logger = logging.getLogger(__name__)


def _parse_service_account_json(raw: str) -> dict:
    import json as _json
    import re as _re

    # Strategy 1: parse as-is
    try:
        return _json.loads(raw)
    except _json.JSONDecodeError:
        pass

    # Strategy 2: re-escape newlines (Vercel converts \n to real newlines in env vars)
    fixed = _re.sub(r'(?<!\\)\n', r'\\n', raw)
    try:
        return _json.loads(fixed)
    except _json.JSONDecodeError:
        pass

    # Strategy 3: extra data after the JSON object — extract only the first object
    try:
        obj, _ = _json.JSONDecoder().raw_decode(raw)
        return obj
    except _json.JSONDecodeError:
        pass

    # Strategy 4: combine newline-fix and raw_decode
    try:
        obj, _ = _json.JSONDecoder().raw_decode(fixed)
        return obj
    except _json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse GOOGLE_SERVICE_ACCOUNT_JSON: {exc}") from exc


def _get_calendar_service():
    import json as _json
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/calendar"]

    if GOOGLE_SERVICE_ACCOUNT_JSON:
        raw = GOOGLE_SERVICE_ACCOUNT_JSON.strip()
        info = _parse_service_account_json(raw)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    elif GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes)
    else:
        raise EnvironmentError(
            "Google service account not configured. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON in .env"
        )

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_event(
    title: str,
    start_dt: str,
    end_dt: str,
    description: str = "",
    location: str = "",
    attendee_emails: Optional[list[str]] = None,
    appointment_id: Optional[str] = None,
    calendar_id: Optional[str] = None,
) -> str:
    """
    Create a Google Calendar event.

    Args:
        start_dt / end_dt: ISO 8601 with timezone (e.g. "2025-06-15T10:00:00+02:00")
        attendee_emails: List of email addresses to invite
        appointment_id: Used as extended property for lookup

    Returns:
        Google Calendar event ID
    """
    service = _get_calendar_service()

    event_body: dict = {
        "summary": title,
        "location": location,
        "description": description,
        "start": {"dateTime": start_dt, "timeZone": "Europe/Berlin"},
        "end": {"dateTime": end_dt, "timeZone": "Europe/Berlin"},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
            ],
        },
    }

    # Note: service accounts cannot add attendees to external calendars
    # Contact info is included in the description instead

    if appointment_id:
        event_body["extendedProperties"] = {
            "private": {"immoai_appointment_id": appointment_id}
        }

    cal_id = calendar_id or GCAL_CALENDAR_ID
    created = service.events().insert(
        calendarId=cal_id,
        body=event_body,
        sendUpdates="none",
    ).execute()

    event_id = created["id"]
    logger.info("GCal event created: %s (id=%s)", title, event_id)
    return event_id


def update_event_status(gcal_event_id: str, status: str) -> None:
    """
    Update the status of a calendar event.
    status: 'confirmed' | 'tentative' | 'cancelled'
    """
    service = _get_calendar_service()
    event = service.events().get(
        calendarId=GCAL_CALENDAR_ID,
        eventId=gcal_event_id,
    ).execute()

    event["status"] = status
    service.events().update(
        calendarId=GCAL_CALENDAR_ID,
        eventId=gcal_event_id,
        body=event,
        sendUpdates="all",
    ).execute()
    logger.info("GCal event %s updated to status=%s", gcal_event_id, status)


def delete_event(gcal_event_id: str) -> None:
    service = _get_calendar_service()
    service.events().delete(
        calendarId=GCAL_CALENDAR_ID,
        eventId=gcal_event_id,
        sendUpdates="all",
    ).execute()
    logger.info("GCal event deleted: %s", gcal_event_id)


def sync_appointment_to_gcal(termin: dict) -> str:
    """
    Convenience wrapper: build event from a Termine-sheet row dict and create it.
    Returns the new gcal_event_id.
    """
    from datetime import datetime, timedelta, timezone

    start_str = termin.get("datetime_start", "")
    end_str = termin.get("datetime_end", "")

    # If no end time, default to 1 hour after start
    if not end_str and start_str:
        try:
            dt = datetime.fromisoformat(start_str)
            end_str = (dt + timedelta(hours=1)).isoformat()
        except ValueError:
            end_str = start_str

    title = f"Besichtigung — {termin.get('property_address', 'Objekt')}"
    description = (
        f"Lead: {termin.get('lead_id', '')}\n"
        f"Makler: {termin.get('agent_name', '')} ({termin.get('agent_email', '')})\n"
        f"Adresse: {termin.get('property_address', '')}\n"
        f"Termin-ID: {termin.get('appointment_id', '')}"
    )

    attendees = []
    if termin.get("agent_email"):
        attendees.append(termin["agent_email"])

    return create_event(
        title=title,
        start_dt=start_str,
        end_dt=end_str,
        description=description,
        location=termin.get("property_address", ""),
        attendee_emails=attendees,
        appointment_id=termin.get("appointment_id"),
    )
