import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import List, Optional

CALENDAR_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "calendar.json")

APPOINTMENT_TYPES = ("Besichtigung", "Call")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@dataclass
class Appointment:
    appointment_id: str
    property_id: str
    client_name: str
    client_contact: str
    date: str        # YYYY-MM-DD
    time: str        # HH:MM
    type: str        # "Besichtigung" | "Call"
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Appointment":
        return Appointment(
            appointment_id=d["appointment_id"],
            property_id=d.get("property_id", ""),
            client_name=d["client_name"],
            client_contact=d.get("client_contact", ""),
            date=d["date"],
            time=d["time"],
            type=d["type"],
            notes=d.get("notes", ""),
        )


# ── Storage (swap this layer for Google Calendar API later) ───────────────────

def _load_all() -> List[dict]:
    if not os.path.exists(CALENDAR_FILE):
        return []
    with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []


def _save_all(appointments: List[dict]) -> None:
    os.makedirs(os.path.dirname(CALENDAR_FILE), exist_ok=True)
    with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
        json.dump(appointments, f, ensure_ascii=False, indent=2)


# ── Validation ────────────────────────────────────────────────────────────────

def _validate(data: dict) -> None:
    errors = []
    if not data.get("client_name", "").strip():
        errors.append("client_name ist erforderlich")
    if not _DATE_RE.match(data.get("date", "")):
        errors.append("date muss im Format YYYY-MM-DD sein")
    else:
        try:
            datetime.strptime(data["date"], "%Y-%m-%d")
        except ValueError:
            errors.append(f"Ungültiges Datum: {data['date']}")
    if not _TIME_RE.match(data.get("time", "")):
        errors.append("time muss im Format HH:MM sein")
    else:
        h, m = map(int, data["time"].split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            errors.append(f"Ungültige Uhrzeit: {data['time']}")
    if data.get("type") not in APPOINTMENT_TYPES:
        errors.append(f"type muss einer von {APPOINTMENT_TYPES} sein")
    if errors:
        raise ValueError("; ".join(errors))


# ── Conflict check (placeholder for future logic) ─────────────────────────────

def check_conflicts(date: str, time: str, exclude_id: Optional[str] = None) -> List[Appointment]:
    """Returns appointments at the same date+time. No blocking in MVP — just informational."""
    return [
        a for a in get_appointments()
        if a.date == date and a.time == time and a.appointment_id != exclude_id
    ]


# ── Core CRUD ─────────────────────────────────────────────────────────────────

def create_appointment(data: dict) -> Appointment:
    _validate(data)
    appointment = Appointment(
        appointment_id=str(uuid.uuid4())[:8],
        property_id=data.get("property_id", ""),
        client_name=data["client_name"].strip(),
        client_contact=data.get("client_contact", "").strip(),
        date=data["date"],
        time=data["time"],
        type=data["type"],
        notes=data.get("notes", "").strip(),
    )
    all_appointments = _load_all()
    all_appointments.append(appointment.to_dict())
    _save_all(all_appointments)
    return appointment


def get_appointments() -> List[Appointment]:
    return [Appointment.from_dict(d) for d in _load_all()]


def get_appointments_by_date(target_date: str) -> List[Appointment]:
    if not _DATE_RE.match(target_date):
        raise ValueError(f"date muss im Format YYYY-MM-DD sein, erhalten: {target_date}")
    return [a for a in get_appointments() if a.date == target_date]


def get_upcoming_appointments(from_date: Optional[str] = None) -> List[Appointment]:
    """Returns appointments from today onwards, sorted by date+time."""
    cutoff = from_date or date.today().isoformat()
    upcoming = [a for a in get_appointments() if a.date >= cutoff]
    return sorted(upcoming, key=lambda a: (a.date, a.time))


def get_todays_appointments() -> List[Appointment]:
    return get_appointments_by_date(date.today().isoformat())


def delete_appointment(appointment_id: str) -> bool:
    all_appointments = _load_all()
    filtered = [a for a in all_appointments if a["appointment_id"] != appointment_id]
    if len(filtered) == len(all_appointments):
        return False
    _save_all(filtered)
    return True


def get_appointment_by_id(appointment_id: str) -> Optional[Appointment]:
    for d in _load_all():
        if d["appointment_id"] == appointment_id:
            return Appointment.from_dict(d)
    return None
