import re
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import List, Optional

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
    username: str = ""

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
            username=d.get("username", ""),
        )


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


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_appointment(data: dict, username: str = "") -> Appointment:
    _validate(data)
    from src.db import execute
    appt = Appointment(
        appointment_id=str(uuid.uuid4())[:8],
        property_id=data.get("property_id", ""),
        client_name=data["client_name"].strip(),
        client_contact=data.get("client_contact", "").strip(),
        date=data["date"],
        time=data["time"],
        type=data["type"],
        notes=data.get("notes", "").strip(),
        username=username,
    )
    execute(
        """INSERT INTO calendar_events
               (appointment_id, property_id, client_name, client_contact,
                date, time, type, notes, username)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (appt.appointment_id, appt.property_id, appt.client_name,
         appt.client_contact, appt.date, appt.time, appt.type,
         appt.notes, appt.username),
    )
    return appt


def get_appointments(username: str = "") -> List[Appointment]:
    from src.db import fetchall
    if username:
        rows = fetchall(
            "SELECT * FROM calendar_events WHERE username = ? ORDER BY date, time",
            (username,),
        )
    else:
        rows = fetchall("SELECT * FROM calendar_events ORDER BY date, time")
    return [Appointment.from_dict(r) for r in rows]


def get_appointments_by_date(target_date: str, username: str = "") -> List[Appointment]:
    if not _DATE_RE.match(target_date):
        raise ValueError(f"date muss im Format YYYY-MM-DD sein, erhalten: {target_date}")
    from src.db import fetchall
    if username:
        rows = fetchall(
            "SELECT * FROM calendar_events WHERE date = ? AND username = ? ORDER BY time",
            (target_date, username),
        )
    else:
        rows = fetchall(
            "SELECT * FROM calendar_events WHERE date = ? ORDER BY time",
            (target_date,),
        )
    return [Appointment.from_dict(r) for r in rows]


def get_upcoming_appointments(from_date: Optional[str] = None, username: str = "") -> List[Appointment]:
    cutoff = from_date or date.today().isoformat()
    from src.db import fetchall
    if username:
        rows = fetchall(
            "SELECT * FROM calendar_events WHERE date >= ? AND username = ? ORDER BY date, time",
            (cutoff, username),
        )
    else:
        rows = fetchall(
            "SELECT * FROM calendar_events WHERE date >= ? ORDER BY date, time",
            (cutoff,),
        )
    return [Appointment.from_dict(r) for r in rows]


def get_todays_appointments(username: str = "") -> List[Appointment]:
    return get_appointments_by_date(date.today().isoformat(), username)


def delete_appointment(appointment_id: str) -> bool:
    from src.db import fetchone, execute
    if not fetchone("SELECT 1 FROM calendar_events WHERE appointment_id = ?", (appointment_id,)):
        return False
    execute("DELETE FROM calendar_events WHERE appointment_id = ?", (appointment_id,))
    return True


def get_appointment_by_id(appointment_id: str) -> Optional[Appointment]:
    from src.db import fetchone
    row = fetchone("SELECT * FROM calendar_events WHERE appointment_id = ?", (appointment_id,))
    return Appointment.from_dict(row) if row else None


def check_conflicts(target_date: str, time: str, exclude_id: Optional[str] = None) -> List[Appointment]:
    from src.db import fetchall
    rows = fetchall(
        "SELECT * FROM calendar_events WHERE date = ? AND time = ?",
        (target_date, time),
    )
    appts = [Appointment.from_dict(r) for r in rows]
    return [a for a in appts if a.appointment_id != exclude_id]
