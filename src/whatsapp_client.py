"""
WhatsApp push notifications via Twilio (Pro + Business plans).
Silently skips if not configured — zero breaking changes.

Setup:
  1. twilio.com → Account erstellen → WhatsApp Sandbox aktivieren
  2. .env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
  3. Pro Nutzer: Telefonnummer im Profil hinterlegen (users.json: phone field)
  4. pip install twilio
"""
import logging
import os

logger = logging.getLogger(__name__)

_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_FROM  = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")


def _ready() -> bool:
    return bool(_SID and _TOKEN)


def send(to_phone: str, message: str) -> bool:
    if not _ready():
        logger.debug("WhatsApp not configured — skipped.")
        return False
    if not to_phone or not to_phone.strip():
        return False
    try:
        from twilio.rest import Client
        to = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone
        Client(_SID, _TOKEN).messages.create(from_=_FROM, to=to, body=message)
        logger.info("WhatsApp → %s", to_phone)
        return True
    except ImportError:
        logger.warning("twilio not installed. Run: pip install twilio")
        return False
    except Exception as e:
        logger.error("WhatsApp failed: %s", e)
        return False


def notify_expose_ready(phone: str, address: str, doc_url: str) -> bool:
    return send(phone, (
        f"✅ *Immo AI* — Exposé fertig!\n\n"
        f"📍 {address}\n"
        f"📄 {doc_url}\n\n"
        f"Im Review-Interface prüfen und freigeben."
    ))


def notify_appointment(phone: str, lead_name: str, address: str, dt_str: str) -> bool:
    return send(phone, (
        f"📅 *Immo AI* — Neuer Termin!\n\n"
        f"👤 {lead_name}\n"
        f"📍 {address}\n"
        f"🕐 {dt_str}\n\n"
        f"In Google Calendar eingetragen."
    ))


def notify_expose_invalid(phone: str, address: str, details: str) -> bool:
    return send(phone, (
        f"⚠️ *Immo AI* — Exposé ungültig!\n\n"
        f"📍 {address}\n"
        f"Problem: {details[:200]}\n\n"
        f"Bitte Eingabedaten korrigieren."
    ))
