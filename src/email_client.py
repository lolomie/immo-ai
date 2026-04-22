"""
SMTP email client.
Handles three email types:
  1. Exposé-Fertigstellung (Makler bekommt Drive-Link)
  2. Terminbestätigung (Lead + Makler)
  3. 24h-Terminerinnerung (Lead + Makler)

Configuration via .env:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM, EMAIL_FROM_NAME
"""

import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from .config import (
    EMAIL_FROM,
    EMAIL_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


class EmailError(Exception):
    pass


def _build_message(to: str, subject: str, body_html: str, body_text: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    msg["To"] = to
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    return msg


def _send(to: str, msg: MIMEMultipart) -> None:
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("SMTP not configured — email to %s skipped.", to)
        return

    context = ssl.create_default_context()
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(EMAIL_FROM, to, msg.as_bytes())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(EMAIL_FROM, to, msg.as_bytes())
        logger.info("Email sent to %s: %s", to, msg["Subject"])
    except smtplib.SMTPException as e:
        raise EmailError(f"SMTP error sending to {to}: {e}") from e


# ── Exposé ready notification ─────────────────────────────────────────────────

def send_expose_ready(
    agent_email: str,
    property_address: str,
    property_id: str,
    doc_url: str,
    job_id: str,
) -> None:
    import html as _html

    # Validate URL — never send a broken link
    if not doc_url or not doc_url.startswith("http"):
        logger.error("send_expose_ready: invalid doc_url=%r — email not sent", doc_url)
        raise ValueError(f"Ungültige doc_url: {doc_url!r}")

    safe_url = _html.escape(doc_url, quote=True)

    subject = f"✅ Exposé fertig — {property_address}"
    body_html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif; color:#1e293b; max-width:600px; margin:auto; padding:24px;">
  <h2 style="color:#1a3a5c;">Exposé erfolgreich generiert</h2>
  <p>Das KI-Exposé für <strong>{_html.escape(property_address)}</strong> wurde erstellt und validiert.</p>
  <table style="border-collapse:collapse; width:100%; margin:16px 0;">
    <tr>
      <td style="padding:8px; background:#f1f5f9; font-weight:600; width:120px;">Objekt-ID</td>
      <td style="padding:8px;">{_html.escape(property_id)}</td>
    </tr>
    <tr>
      <td style="padding:8px; background:#f1f5f9; font-weight:600;">Job-ID</td>
      <td style="padding:8px;">{_html.escape(job_id)}</td>
    </tr>
  </table>

  <!-- Primary CTA button -->
  <table role="presentation" cellspacing="0" cellpadding="0" border="0">
    <tr>
      <td style="border-radius:6px; background:#1a3a5c;">
        <a href="{safe_url}"
           target="_blank"
           style="display:inline-block; background:#1a3a5c; color:#ffffff;
                  font-family:sans-serif; font-size:15px; font-weight:600;
                  padding:14px 28px; border-radius:6px; text-decoration:none;
                  mso-padding-alt:0; -webkit-text-size-adjust:none;">
          &#128196;&nbsp; Exposé öffnen (Google Drive)
        </a>
      </td>
    </tr>
  </table>

  <!-- Fallback plain link (shown in clients that strip buttons) -->
  <p style="margin-top:16px; font-size:13px; color:#64748b;">
    Link funktioniert nicht? Direkt öffnen:<br>
    <a href="{safe_url}" style="color:#2563eb; word-break:break-all;">{safe_url}</a>
  </p>

  <p style="margin-top:24px; font-size:12px; color:#94a3b8;">
    Dieses Exposé wurde KI-generiert und automatisch auf Halluzinationen geprüft.
    Bitte Inhalt vor Weitergabe an Interessenten prüfen.
  </p>
</body></html>"""
    body_text = (
        f"Exposé fertig: {property_address}\n"
        f"Objekt-ID: {property_id} | Job-ID: {job_id}\n\n"
        f"Exposé öffnen:\n{doc_url}\n\n"
        "Bitte Inhalt vor Weitergabe prüfen."
    )
    _send(agent_email, _build_message(agent_email, subject, body_html, body_text))


def send_expose_approved(
    agent_email: str,
    job_id: str,
    property_id: str,
    expose_text: str,
    docx_bytes: bytes,
    app_url: str = "",
) -> None:
    """
    Send approval notification for web-generated exposés (no Drive upload).
    Attaches the .docx directly to the email.
    """
    import html as _html
    from email.mime.base import MIMEBase
    from email.mime.application import MIMEApplication
    from email import encoders

    safe_text = _html.escape(expose_text)
    download_section = ""
    if app_url:
        dl_url = _html.escape(f"{app_url.rstrip('/')}/api/jobs/{job_id}/download", quote=True)
        download_section = f"""
  <p style="margin-top:16px;">
    <a href="{dl_url}"
       style="display:inline-block;background:#1a3a5c;color:#fff;
              padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:600;">
      &#128196;&nbsp; Exposé herunterladen (.docx)
    </a>
  </p>
  <p style="margin-top:8px;font-size:13px;color:#64748b;">
    Link funktioniert nicht?
    <a href="{dl_url}" style="color:#2563eb;word-break:break-all;">{dl_url}</a>
  </p>"""

    preview = expose_text[:600].replace("\n", "<br>")
    if len(expose_text) > 600:
        preview += "<br><em style='color:#94a3b8;'>[… vollständiges Exposé im Anhang]</em>"

    subject = f"✅ Exposé freigegeben — {property_id}"
    body_html = f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;color:#1e293b;max-width:620px;margin:auto;padding:24px;">
  <h2 style="color:#1a3a5c;">Exposé freigegeben</h2>
  <table style="border-collapse:collapse;width:100%;margin:16px 0;">
    <tr><td style="padding:8px;background:#f1f5f9;font-weight:600;width:110px;">Objekt-ID</td>
        <td style="padding:8px;">{_html.escape(property_id)}</td></tr>
    <tr><td style="padding:8px;background:#f1f5f9;font-weight:600;">Job-ID</td>
        <td style="padding:8px;font-family:monospace;font-size:.875rem;">{_html.escape(job_id)}</td></tr>
  </table>
  {download_section}
  <div style="margin-top:24px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
              padding:16px;font-size:.9rem;line-height:1.7;color:#334155;">
    <strong style="font-size:.75rem;text-transform:uppercase;letter-spacing:.07em;
                   color:#64748b;display:block;margin-bottom:8px;">Exposé-Vorschau</strong>
    {preview}
  </div>
  <p style="margin-top:24px;font-size:12px;color:#94a3b8;">
    Das vollständige Exposé ist als .docx-Datei im Anhang beigefügt.<br>
    Bitte Inhalt vor Weitergabe an Interessenten nochmals prüfen.
  </p>
</body></html>"""
    body_text = (
        f"Exposé freigegeben\nObjekt: {property_id} | Job: {job_id}\n\n"
        f"{expose_text}\n\n"
        "Das Exposé ist auch als .docx im Anhang.\n"
        "Bitte Inhalt vor Weitergabe prüfen."
    )

    msg = _build_message(agent_email, subject, body_html, body_text)

    # Attach the .docx
    filename = f"Expose_{property_id}_{job_id}.docx"
    part = MIMEApplication(docx_bytes, Name=filename)
    part["Content-Disposition"] = f'attachment; filename="{filename}"'
    msg.attach(part)

    _send(agent_email, msg)


def send_expose_invalid(
    agent_email: str,
    property_address: str,
    property_id: str,
    hallucination_details: str,
) -> None:
    subject = f"⚠️ Exposé ungültig — {property_address}"
    body_html = f"""
<html><body style="font-family:sans-serif; color:#1e293b; max-width:600px; margin:auto; padding:24px;">
  <h2 style="color:#b91c1c;">Exposé-Validierung fehlgeschlagen</h2>
  <p>Das generierte Exposé für <strong>{property_address}</strong> wurde als ungültig markiert.</p>
  <div style="background:#fef2f2; border-left:4px solid #b91c1c; padding:12px 16px; margin:16px 0;">
    <strong>Gefundene Probleme:</strong><br>
    {hallucination_details}
  </div>
  <p>Bitte überprüfen Sie die Eingabedaten im Google Sheet (Exposé-Inputs, Status: invalid)
     und korrigieren Sie fehlerhafte oder fehlende Felder, dann setzen Sie den Status
     wieder auf <strong>pending</strong> für eine erneute Generierung.</p>
</body></html>
"""
    body_text = (
        f"Exposé UNGÜLTIG: {property_address}\n"
        f"Objekt-ID: {property_id}\n"
        f"Probleme: {hallucination_details}\n\n"
        "Eingabedaten korrigieren und Status auf 'pending' zurücksetzen."
    )
    _send(agent_email, _build_message(agent_email, subject, body_html, body_text))


# ── Appointment emails ────────────────────────────────────────────────────────

def send_appointment_confirmation(
    lead_email: str,
    lead_name: str,
    agent_name: str,
    property_address: str,
    datetime_start: str,
    appointment_id: str,
) -> None:
    try:
        dt = datetime.fromisoformat(datetime_start)
        dt_formatted = dt.strftime("%A, %d. %B %Y um %H:%M Uhr")
    except ValueError:
        dt_formatted = datetime_start

    subject = f"Terminbestätigung — {property_address}"
    body_html = f"""
<html><body style="font-family:sans-serif; color:#1e293b; max-width:600px; margin:auto; padding:24px;">
  <h2 style="color:#1a3a5c;">Ihr Besichtigungstermin ist bestätigt</h2>
  <p>Guten Tag {lead_name},</p>
  <p>Ihr Besichtigungstermin wurde erfolgreich gebucht.</p>
  <table style="border-collapse:collapse; width:100%; margin:16px 0;">
    <tr><td style="padding:8px; background:#f1f5f9; font-weight:600;">Objekt</td>
        <td style="padding:8px;">{property_address}</td></tr>
    <tr><td style="padding:8px; background:#f1f5f9; font-weight:600;">Datum & Uhrzeit</td>
        <td style="padding:8px;">{dt_formatted}</td></tr>
    <tr><td style="padding:8px; background:#f1f5f9; font-weight:600;">Ihr Makler</td>
        <td style="padding:8px;">{agent_name}</td></tr>
    <tr><td style="padding:8px; background:#f1f5f9; font-weight:600;">Termin-ID</td>
        <td style="padding:8px;">{appointment_id}</td></tr>
  </table>
  <p>Wir freuen uns auf Ihren Besuch!</p>
  <p style="margin-top:24px; font-size:12px; color:#94a3b8;">Immo AI — Powered by KI, geprüft durch Menschen.</p>
</body></html>
"""
    body_text = (
        f"Terminbestätigung\nObjekt: {property_address}\n"
        f"Datum: {dt_formatted}\nMakler: {agent_name}\n"
        f"Termin-ID: {appointment_id}"
    )
    _send(lead_email, _build_message(lead_email, subject, body_html, body_text))


def send_appointment_reminder(
    lead_email: str,
    lead_name: str,
    agent_name: str,
    property_address: str,
    datetime_start: str,
) -> None:
    try:
        dt = datetime.fromisoformat(datetime_start)
        dt_formatted = dt.strftime("%A, %d. %B %Y um %H:%M Uhr")
    except ValueError:
        dt_formatted = datetime_start

    subject = f"⏰ Erinnerung: Besichtigung morgen — {property_address}"
    body_html = f"""
<html><body style="font-family:sans-serif; color:#1e293b; max-width:600px; margin:auto; padding:24px;">
  <h2 style="color:#1a3a5c;">Ihr Termin ist morgen</h2>
  <p>Guten Tag {lead_name},</p>
  <p>Wir erinnern Sie an Ihren Besichtigungstermin morgen.</p>
  <table style="border-collapse:collapse; width:100%; margin:16px 0;">
    <tr><td style="padding:8px; background:#fffbeb; font-weight:600;">Objekt</td>
        <td style="padding:8px;">{property_address}</td></tr>
    <tr><td style="padding:8px; background:#fffbeb; font-weight:600;">Datum & Uhrzeit</td>
        <td style="padding:8px;">{dt_formatted}</td></tr>
    <tr><td style="padding:8px; background:#fffbeb; font-weight:600;">Ihr Makler</td>
        <td style="padding:8px;">{agent_name}</td></tr>
  </table>
  <p>Bei Fragen oder falls Sie absagen möchten, antworten Sie bitte auf diese E-Mail.</p>
</body></html>
"""
    body_text = (
        f"Terminerinnerung\nObjekt: {property_address}\n"
        f"Morgen: {dt_formatted}\nMakler: {agent_name}"
    )
    _send(lead_email, _build_message(lead_email, subject, body_html, body_text))
