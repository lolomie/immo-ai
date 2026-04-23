"""
Word document (.docx) creator for validated exposés.
Produces a professionally formatted document using python-docx.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Optional

from .models import PropertyInput

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "Dieses Exposé wurde mit Unterstützung von KI-Technologie erstellt und durch "
    "einen menschlichen Makler geprüft. Alle Angaben sind nach bestem Wissen und "
    "Gewissen, jedoch ohne Gewähr. Irrtümer und Zwischenverkauf vorbehalten."
)


def create_expose_docx_bytes(
    property_data: PropertyInput,
    expose_text: str,
    agent_email: Optional[str] = None,
    target_group: Optional[str] = None,
) -> bytes:
    """
    Build the .docx in memory and return the raw bytes.
    The caller is responsible for saving or uploading.
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor, Inches
    except ImportError as e:
        raise ImportError("python-docx not installed. Run: pip install python-docx") from e

    doc = Document()

    # ── Page margins ──────────────────────────────────────────────────────────
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.2)
        section.right_margin = Inches(1.2)

    # ── Header: Branding ──────────────────────────────────────────────────────
    header = doc.add_heading("IMMO AI — Immobilien-Exposé", level=0)
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in header.runs:
        run.font.color.rgb = RGBColor(0x1A, 0x3A, 0x5C)  # navy

    doc.add_paragraph()

    # ── Property title ────────────────────────────────────────────────────────
    title = f"{property_data.property_type} · {property_data.address}, {property_data.zip_code} {property_data.city}"
    h = doc.add_heading(title, level=1)
    h.alignment = WD_ALIGN_PARAGRAPH.LEFT

    doc.add_paragraph()

    # ── Details table ─────────────────────────────────────────────────────────
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    _use_first_row = [True]

    def add_row(label: str, value: str) -> None:
        if _use_first_row[0]:
            row = table.rows[0].cells
            _use_first_row[0] = False
        else:
            row = table.add_row().cells
        row[0].text = label
        if row[0].paragraphs[0].runs:
            row[0].paragraphs[0].runs[0].bold = True
        row[1].text = value

    add_row("Immobilientyp", property_data.property_type)
    add_row("Adresse", f"{property_data.address}, {property_data.zip_code} {property_data.city}")
    add_row("Wohnfläche", f"{property_data.size_sqm} m²")
    add_row("Zimmer", str(property_data.rooms))

    if property_data.year_built:
        add_row("Baujahr", str(property_data.year_built))
    if property_data.energy_class:
        add_row("Energieklasse", property_data.energy_class)
    if property_data.purchase_price:
        add_row("Kaufpreis", f"{property_data.purchase_price:,.0f} €")
    if property_data.monthly_rent:
        add_row("Kaltmiete", f"{property_data.monthly_rent:,.0f} €/Monat")
    if property_data.features:
        add_row("Ausstattung", " · ".join(property_data.features))
    if target_group:
        add_row("Zielgruppe", target_group)

    # ── Exposé text ───────────────────────────────────────────────────────────
    doc.add_paragraph()
    doc.add_heading("Objektbeschreibung", level=2)
    doc.add_paragraph()

    for paragraph in expose_text.split("\n\n"):
        p = paragraph.strip()
        if p:
            doc.add_paragraph(p)

    # ── Footer: meta ─────────────────────────────────────────────────────────
    doc.add_paragraph()
    doc.add_paragraph("─" * 60)

    meta_lines = [
        f"Erstellt: {datetime.now(timezone.utc).strftime('%d.%m.%Y')}",
        f"Objekt-ID: {property_data.property_id}",
    ]
    if agent_email:
        meta_lines.append(f"Zuständig: {agent_email}")

    for line in meta_lines:
        p = doc.add_paragraph(line)
        p.runs[0].font.size = Pt(9)
        p.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    doc.add_paragraph()
    disc = doc.add_paragraph(_DISCLAIMER)
    disc.runs[0].font.size = Pt(8)
    disc.runs[0].font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)
    disc.runs[0].font.italic = True

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def expose_filename(property_data: PropertyInput) -> str:
    """Generate a clean filename for the exposé document."""
    safe_id = property_data.property_id.replace("/", "-").replace(" ", "_")
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"Expose_{safe_id}_{date_str}.docx"
