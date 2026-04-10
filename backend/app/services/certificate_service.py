from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch, cm
from reportlab.pdfgen import canvas


def generate_certificate_pdf(
    partner_name: str,
    company_name: str,
    course_title: str,
    completion_date: datetime,
    certificate_id: str,
) -> bytes:
    """Generate a certificate of completion PDF and return raw bytes."""
    buffer = BytesIO()
    width, height = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=landscape(A4))

    # Border
    border_color = HexColor("#1a365d")
    c.setStrokeColor(border_color)
    c.setLineWidth(4)
    c.rect(30, 30, width - 60, height - 60)
    c.setLineWidth(1.5)
    c.rect(40, 40, width - 80, height - 80)

    # Title
    c.setFont("Helvetica-Bold", 36)
    c.setFillColor(HexColor("#1a365d"))
    c.drawCentredString(width / 2, height - 120, "CERTIFICATE OF COMPLETION")

    # Decorative line
    c.setStrokeColor(HexColor("#c4a35a"))
    c.setLineWidth(2)
    c.line(width / 2 - 150, height - 135, width / 2 + 150, height - 135)

    # "This is to certify that"
    c.setFont("Helvetica", 16)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(width / 2, height - 180, "This is to certify that")

    # Partner name
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(HexColor("#1a365d"))
    c.drawCentredString(width / 2, height - 220, partner_name)

    # Company
    c.setFont("Helvetica", 14)
    c.setFillColor(HexColor("#555555"))
    c.drawCentredString(width / 2, height - 250, f"from {company_name}")

    # "has successfully completed"
    c.setFont("Helvetica", 16)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(width / 2, height - 290, "has successfully completed the course")

    # Course title
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(HexColor("#1a365d"))
    c.drawCentredString(width / 2, height - 325, course_title)

    # Date
    date_str = completion_date.strftime("%B %d, %Y") if completion_date else "N/A"
    c.setFont("Helvetica", 14)
    c.setFillColor(HexColor("#555555"))
    c.drawCentredString(width / 2, height - 370, f"Completed on: {date_str}")

    # Signature line - left side
    sig_y = 100
    c.setStrokeColor(HexColor("#333333"))
    c.setLineWidth(1)
    c.line(width / 2 - 200, sig_y, width / 2 - 40, sig_y)
    c.setFont("Helvetica", 11)
    c.setFillColor(HexColor("#333333"))
    c.drawCentredString(width / 2 - 120, sig_y - 18, "Extravis PVT LTD")
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2 - 120, sig_y - 32, "Authorized Signature")

    # Certificate ID - right side
    c.line(width / 2 + 40, sig_y, width / 2 + 200, sig_y)
    c.setFont("Helvetica", 11)
    c.drawCentredString(width / 2 + 120, sig_y - 18, f"ID: {certificate_id}")
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2 + 120, sig_y - 32, "Certificate ID")

    c.save()
    return buffer.getvalue()
