#!/usr/bin/env python3
"""
CLI for Immo AI Calendar
Usage:
  python workflows/calendar.py add
  python workflows/calendar.py list [--date YYYY-MM-DD] [--today] [--upcoming]
  python workflows/calendar.py delete <appointment_id>
  python workflows/calendar.py show <appointment_id>
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.calendar_service import (
    create_appointment,
    delete_appointment,
    get_appointment_by_id,
    get_appointments,
    get_appointments_by_date,
    get_todays_appointments,
    get_upcoming_appointments,
    check_conflicts,
    APPOINTMENT_TYPES,
)


def _fmt(a) -> str:
    conflict_marker = ""
    conflicts = check_conflicts(a.date, a.time, exclude_id=a.appointment_id)
    if conflicts:
        conflict_marker = "  !KONFLIKT"
    return (
        f"  [{a.appointment_id}]  {a.date} {a.time}  "
        f"{a.type:<14}  {a.client_name:<20}  "
        f"Objekt: {a.property_id or '—'}"
        f"{conflict_marker}"
    )


def cmd_add():
    print("\n--Neuen Termin anlegen ----------------------")
    data = {}
    data["client_name"]    = input("Kundenname:            ").strip()
    data["client_contact"] = input("Kontakt (Tel/Email):   ").strip()
    data["property_id"]    = input("Objekt-ID (optional):  ").strip()

    print(f"Typ ({' / '.join(APPOINTMENT_TYPES)}): ", end="")
    data["type"] = input().strip()

    data["date"] = input("Datum (YYYY-MM-DD):    ").strip()
    data["time"] = input("Uhrzeit (HH:MM):       ").strip()
    data["notes"] = input("Notizen (optional):    ").strip()

    try:
        appt = create_appointment(data)
        conflicts = check_conflicts(appt.date, appt.time, exclude_id=appt.appointment_id)
        print(f"\nOKTermin gespeichert  [ID: {appt.appointment_id}]")
        if conflicts:
            print(f"  !Hinweis: Zeitkonflikt mit {len(conflicts)} anderen Termin(en) um {appt.time}")
    except ValueError as e:
        print(f"\nFEHLER:Fehler: {e}")
        sys.exit(1)


def cmd_list(date_filter=None, today=False, upcoming=False):
    if today:
        appointments = get_todays_appointments()
        title = f"Termine heute"
    elif upcoming:
        appointments = get_upcoming_appointments()
        title = "Bevorstehende Termine"
    elif date_filter:
        appointments = get_appointments_by_date(date_filter)
        title = f"Termine am {date_filter}"
    else:
        appointments = sorted(get_appointments(), key=lambda a: (a.date, a.time))
        title = "Alle Termine"

    print(f"\n--{title} ({len(appointments)}) ----------------------")
    if not appointments:
        print("  Keine Termine gefunden.")
        return
    for a in appointments:
        print(_fmt(a))
        if a.notes:
            print(f"     Notiz: {a.notes}")
    print()


def cmd_delete(appointment_id: str):
    appt = get_appointment_by_id(appointment_id)
    if not appt:
        print(f"FEHLER:Termin [{appointment_id}] nicht gefunden.")
        sys.exit(1)
    print(f"\n  {_fmt(appt)}")
    confirm = input("Termin löschen? (j/N): ").strip().lower()
    if confirm == "j":
        delete_appointment(appointment_id)
        print("OKTermin gelöscht.")
    else:
        print("Abgebrochen.")


def cmd_show(appointment_id: str):
    appt = get_appointment_by_id(appointment_id)
    if not appt:
        print(f"FEHLER:Termin [{appointment_id}] nicht gefunden.")
        sys.exit(1)
    print(f"\n--Termin {appt.appointment_id} ----------------------")
    print(f"  Kunde:    {appt.client_name}")
    print(f"  Kontakt:  {appt.client_contact or '—'}")
    print(f"  Objekt:   {appt.property_id or '—'}")
    print(f"  Datum:    {appt.date}  {appt.time}")
    print(f"  Typ:      {appt.type}")
    print(f"  Notizen:  {appt.notes or '—'}")
    conflicts = check_conflicts(appt.date, appt.time, exclude_id=appt.appointment_id)
    if conflicts:
        print(f"  !Konflikt mit: {', '.join(c.appointment_id for c in conflicts)}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Immo AI Kalender")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("add", help="Neuen Termin anlegen")

    ls = sub.add_parser("list", help="Termine anzeigen")
    ls.add_argument("--date", help="Filter nach Datum (YYYY-MM-DD)")
    ls.add_argument("--today", action="store_true", help="Nur heutige Termine")
    ls.add_argument("--upcoming", action="store_true", help="Nur bevorstehende Termine")

    dl = sub.add_parser("delete", help="Termin löschen")
    dl.add_argument("appointment_id")

    sh = sub.add_parser("show", help="Termin-Details anzeigen")
    sh.add_argument("appointment_id")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add()
    elif args.command == "list":
        cmd_list(date_filter=args.date, today=args.today, upcoming=args.upcoming)
    elif args.command == "delete":
        cmd_delete(args.appointment_id)
    elif args.command == "show":
        cmd_show(args.appointment_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
