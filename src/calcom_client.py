"""
Cal.com API v2 client.
Manages bookings for property viewings.

Setup:
  1. Create a Cal.com account at cal.com
  2. Go to Settings → API Keys → Create key
  3. Set CALCOM_API_KEY=<your key> in .env
  4. Create an Event Type (e.g. "Immobilienbesichtigung")
  5. Set CALCOM_EVENT_TYPE_ID=<event type ID> in .env

API docs: https://cal.com/docs/api-reference/v2
"""

import logging
from typing import Optional

import requests

from .config import CALCOM_API_KEY, CALCOM_BASE_URL, CALCOM_EVENT_TYPE_ID

logger = logging.getLogger(__name__)


class CalcomError(Exception):
    pass


def _headers() -> dict:
    if not CALCOM_API_KEY:
        raise CalcomError("CALCOM_API_KEY not set in .env")
    return {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13",
    }


def _raise_for_status(resp: requests.Response, action: str) -> None:
    if not resp.ok:
        raise CalcomError(
            f"Cal.com {action} failed: {resp.status_code} — {resp.text[:300]}"
        )


# ── Bookings ──────────────────────────────────────────────────────────────────

def create_booking(
    start_time: str,
    attendee_name: str,
    attendee_email: str,
    property_address: str,
    notes: Optional[str] = None,
    event_type_id: Optional[str] = None,
) -> dict:
    """
    Create a Cal.com booking.

    Args:
        start_time: ISO 8601 datetime string (e.g. "2025-06-15T10:00:00Z")
        attendee_name: Lead full name
        attendee_email: Lead email address
        property_address: Used as meeting title context
        notes: Optional additional notes
        event_type_id: Override the default event type

    Returns:
        Cal.com booking response dict containing uid, status, etc.
    """
    etype = event_type_id or CALCOM_EVENT_TYPE_ID
    if not etype:
        raise CalcomError("CALCOM_EVENT_TYPE_ID not set in .env")

    payload = {
        "eventTypeId": int(etype),
        "start": start_time,
        "attendee": {
            "name": attendee_name,
            "email": attendee_email,
            "timeZone": "Europe/Berlin",
            "language": "de",
        },
        "metadata": {
            "property_address": property_address,
        },
    }
    if notes:
        payload["notes"] = notes

    resp = requests.post(
        f"{CALCOM_BASE_URL}/bookings",
        json=payload,
        headers=_headers(),
        timeout=15,
    )
    _raise_for_status(resp, "create_booking")
    data = resp.json()
    booking_uid = data.get("data", {}).get("uid") or data.get("uid", "")
    logger.info("Cal.com booking created: uid=%s for %s", booking_uid, attendee_email)
    return data.get("data", data)


def get_booking(booking_uid: str) -> dict:
    resp = requests.get(
        f"{CALCOM_BASE_URL}/bookings/{booking_uid}",
        headers=_headers(),
        timeout=10,
    )
    _raise_for_status(resp, "get_booking")
    data = resp.json()
    return data.get("data", data)


def cancel_booking(booking_uid: str, reason: str = "Abgesagt durch Makler") -> None:
    resp = requests.delete(
        f"{CALCOM_BASE_URL}/bookings/{booking_uid}",
        json={"cancellationReason": reason},
        headers=_headers(),
        timeout=10,
    )
    _raise_for_status(resp, "cancel_booking")
    logger.info("Cal.com booking cancelled: uid=%s", booking_uid)


def list_upcoming_bookings(attendee_email: Optional[str] = None) -> list[dict]:
    params: dict = {"status": "upcoming"}
    if attendee_email:
        params["attendeeEmail"] = attendee_email

    resp = requests.get(
        f"{CALCOM_BASE_URL}/bookings",
        params=params,
        headers=_headers(),
        timeout=10,
    )
    _raise_for_status(resp, "list_bookings")
    data = resp.json()
    return data.get("data", {}).get("bookings", [])
