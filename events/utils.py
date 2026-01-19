from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from django.conf import settings


def generate_pdf_ticket(registration):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontSize=24,
        alignment=1,
        spaceAfter=20
    )
    elements.append(Paragraph(registration.event.title, title_style))
    elements.append(Spacer(1, 12))

    data = [
        ["Date:", registration.event.start_time.strftime("%d %B %Y, %H:%M")],
        ["Location:", registration.event.location or "Online Event"],
        ["Type:", registration.event.get_event_type_display()],
        ["Attendee:", registration.user.get_full_name() or registration.user.username],
        ["Ticket ID:", str(registration.ticket_id)[:8].upper()]
    ]

    t = Table(data, colWidths=[100, 300])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 30))

    if registration.ticket_qr_code:
        try:
            if not settings.USE_S3:
                qr_img = Image(registration.ticket_qr_code.path, width=150, height=150)
                elements.append(qr_img)
        except Exception:
            pass

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Please present this QR code at the entrance.", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer