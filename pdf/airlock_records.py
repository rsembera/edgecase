"""PDF records of AirLock submissions: the completed intake and the signed
consent, attached to the client's Upload entry on import.

The letterhead is the statement header (pdf/generator.py), so these read as
the practice's own documents. Every submitted string is escaped before it
reaches ReportLab's mini-markup; the consent text is rendered from a small,
safe subset of Markdown (headings, bullets, paragraphs) and nothing else.
"""
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from pdf.generator import StatementPDFGenerator, esc

INTAKE_LABELS = [
    ("first_name", "First Name"),
    ("middle_name", "Middle Name"),
    ("last_name", "Last Name"),
    ("date_of_birth", "Date of Birth"),
    ("gender", "Gender"),
    ("address", "Address"),
    ("phone", "Cell"),
    ("home_phone", "Home Phone"),
    ("work_phone", "Work Phone"),
    ("email", "Email"),
    ("preferred_contact", "Preferred Contact Method"),
    ("ok_to_leave_message", "OK to Leave Message?"),
    ("emergency_contact_name", "Emergency Contact Name"),
    ("emergency_contact_relationship", "Emergency Contact Relationship"),
    ("emergency_contact_phone", "Emergency Contact Phone"),
    ("referral_source", "How did you hear about this practice?"),
    ("additional_info", "Additional Information"),
]
CHOICE_LABELS = {
    "email": "Email", "call_cell": "Call Cell", "call_home": "Call Home",
    "call_work": "Call Work", "text": "Text Message", "yes": "Yes", "no": "No",
}


def _stamp(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _multiline(text):
    return esc(text).replace("\n", "<br/>")


def _doc(db, title, assets_path):
    gen = StatementPDFGenerator(db)
    styles = gen.styles
    styles.add(ParagraphStyle(name="ALTitle", parent=styles["Normal"], fontSize=14,
                              fontName="Helvetica-Bold", spaceAfter=10))
    styles.add(ParagraphStyle(name="ALHeading", parent=styles["Normal"], fontSize=11,
                              fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4))
    styles.add(ParagraphStyle(name="ALBody", parent=styles["Normal"], fontSize=10,
                              leading=13, spaceAfter=6))
    styles.add(ParagraphStyle(name="ALBullet", parent=styles["ALBody"], leftIndent=14,
                              bulletIndent=4, spaceAfter=2))
    styles.add(ParagraphStyle(name="ALSmall", parent=styles["Normal"], fontSize=8.5,
                              textColor=colors.HexColor("#555555"), leading=11))
    story = gen._build_header(gen._get_settings(), assets_path)
    story.append(Paragraph(esc(title), styles["ALTitle"]))
    return styles, story


def _build(story):
    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.75 * inch,
                      rightMargin=0.75 * inch, topMargin=0.6 * inch,
                      bottomMargin=0.6 * inch).build(story)
    return buf.getvalue()


def _signature_block(styles, attestation, received_at, invitation, extra=()):
    rows = [
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#999999")),
        Spacer(1, 6),
        Paragraph(f"<b>Signed electronically</b> by typing their full name: "
                  f"{esc(attestation['typed_name'])}", styles["ALBody"]),
        Paragraph("Agreement box ticked: Yes", styles["ALBody"]),
        Paragraph(f"Received: {_stamp(received_at)}", styles["ALSmall"]),
        Paragraph(f"Submitted through AirLock, invitation #{invitation['id']} "
                  f"(issued {_stamp(invitation['issued_at'])}).", styles["ALSmall"]),
    ]
    rows += [Paragraph(esc(line), styles["ALSmall"]) for line in extra]
    return rows


def render_intake_pdf(db, intake, invitation, received_at, assets_path) -> bytes:
    styles, story = _doc(db, "Client Intake", assets_path)
    f = intake["fields"]
    rows = []
    for key, label in INTAKE_LABELS:
        value = f.get(key, "")
        if not value:
            continue
        value = CHOICE_LABELS.get(value, value) if key in ("preferred_contact",
                                                            "ok_to_leave_message") else value
        rows.append([Paragraph(esc(label), styles["ALSmall"]),
                     Paragraph(_multiline(value), styles["ALBody"])])
    if rows:
        table = Table(rows, colWidths=[1.9 * inch, 5.1 * inch])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)

    for i, g in enumerate(intake["guardians"], 1):
        story.append(Paragraph(f"Parent / Guardian {i}", styles["ALHeading"]))
        for key, label in (("name", "Name"), ("email", "Email"), ("phone", "Phone"),
                           ("address", "Address")):
            if g.get(key):
                story.append(Paragraph(f"{label}: {_multiline(g[key])}", styles["ALBody"]))

    if intake["questions"]:
        story.append(Paragraph("Additional Questions", styles["ALHeading"]))
        for qa in intake["questions"]:
            story.append(Paragraph(f"<b>{esc(qa['question'])}</b>", styles["ALBody"]))
            story.append(Paragraph(_multiline(qa["answer"]) or "<i>(no answer)</i>",
                                   styles["ALBody"]))

    story += _signature_block(styles, intake["attestation"], received_at, invitation)
    return _build(story)


def _markdown_flowables(text, styles):
    """Headings (#, ##, ###), bullets (- or *), blank-line paragraphs. All
    text escaped; no inline markup, links or HTML."""
    out = []
    para = []

    def flush():
        if para:
            out.append(Paragraph(esc(" ".join(para)), styles["ALBody"]))
            para.clear()

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("#"):
            flush()
            out.append(Paragraph(esc(stripped.lstrip("#").strip()), styles["ALHeading"]))
        elif stripped[:2] in ("- ", "* "):
            flush()
            out.append(Paragraph(esc(stripped[2:].strip()), styles["ALBullet"],
                                 bulletText="•"))
        else:
            para.append(stripped)
    flush()
    return out


def render_consent_pdf(db, consent, invitation, received_at, versions,
                       assets_path) -> bytes:
    title = "Consent to Treatment"
    if invitation.get("is_minor"):
        title += " (signed by parent / guardian)"
    styles, story = _doc(db, title, assets_path)
    story += _markdown_flowables(consent["consent_text"], styles)
    story += _signature_block(
        styles, consent["attestation"], received_at, invitation,
        extra=[f"Consent version: {versions.get('consent_version') or 'n/a'}"])
    return _build(story)
