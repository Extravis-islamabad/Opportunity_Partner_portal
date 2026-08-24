"""
Export service — generates PDF and Excel files for list endpoints.

Uses reportlab for PDFs and openpyxl for Excel. Returns raw bytes so endpoints
can wrap them in a StreamingResponse without touching the filesystem.
"""
from datetime import datetime
from io import BytesIO
from typing import Iterable, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.company import Company
from app.models.customer_license import CustomerLicense
from app.models.deal_registration import DealRegistration
from app.models.opportunity import Opportunity
from app.models.poc import POC_STAGE_KEYS, POC_STAGE_LABELS, Poc

BRAND_COLOR = colors.HexColor("#1a237e")
HEADER_BG = "1A237E"  # openpyxl expects RGB hex without '#'


# ------------------------------ PDF helpers ----------------------------------

def _make_pdf_doc(buf: BytesIO, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=title,
        author="Extravis Partner Portal",
    )


def _pdf_header_elements(title: str, subtitle: str | None = None) -> list:
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "PortalH1",
        parent=styles["Heading1"],
        textColor=BRAND_COLOR,
        fontSize=18,
        spaceAfter=4,
    )
    meta = ParagraphStyle(
        "PortalMeta",
        parent=styles["Normal"],
        textColor=colors.grey,
        fontSize=9,
    )
    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    elements: list = [Paragraph(title, h1)]
    if subtitle:
        elements.append(Paragraph(subtitle, meta))
    elements.append(Paragraph(f"Generated {generated}", meta))
    elements.append(Spacer(1, 8))
    return elements


def _pdf_table(headers: Sequence[str], rows: Sequence[Sequence[str]], col_widths: Sequence[float]) -> Table:
    cell_style = ParagraphStyle(
        "Cell",
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        wordWrap="CJK",
    )
    header_style = ParagraphStyle(
        "CellHeader",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.white,
        leading=11,
    )

    data = [[Paragraph(str(h), header_style) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(cell) if cell is not None else "", cell_style) for cell in row])

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_COLOR),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6fb")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


# ------------------------------ XLSX helpers ---------------------------------

def _xlsx_write_header(ws, headers: Sequence[str]) -> None:
    header_font = Font(color="FFFFFFFF", bold=True)
    header_fill = PatternFill("solid", fgColor=HEADER_BG)
    for idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="left", vertical="center")


def _xlsx_autosize(ws, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    for idx, header in enumerate(headers, start=1):
        max_len = len(str(header))
        for row in rows:
            if idx - 1 < len(row):
                val = row[idx - 1]
                if val is not None:
                    max_len = max(max_len, len(str(val)))
        ws.column_dimensions[get_column_letter(idx)].width = min(max_len + 2, 42)


def _xlsx_to_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ------------------------------ Opportunities --------------------------------

OPP_HEADERS = [
    "ID", "Name", "Customer", "Company", "Country", "Region",
    "Worth (USD)", "Closing Date", "Status", "Submitted By", "Created",
]


def _opportunity_row(opp: Opportunity) -> list[str]:
    return [
        opp.id,
        opp.name,
        opp.customer_name,
        opp.company.name if opp.company else "",
        opp.country,
        opp.region,
        f"{float(opp.worth):,.2f}" if opp.worth is not None else "",
        opp.closing_date.strftime("%Y-%m-%d") if opp.closing_date else "",
        opp.status.value.replace("_", " ").title() if opp.status else "",
        opp.submitted_by_user.full_name if opp.submitted_by_user else "",
        opp.created_at.strftime("%Y-%m-%d") if opp.created_at else "",
    ]


def build_opportunity_pdf(opportunities: Iterable[Opportunity], subtitle: str | None = None) -> bytes:
    buf = BytesIO()
    doc = _make_pdf_doc(buf, "Opportunities Report")
    elements = _pdf_header_elements("Opportunities Report", subtitle)

    rows = [_opportunity_row(opp) for opp in opportunities]
    if not rows:
        styles = getSampleStyleSheet()
        elements.append(Paragraph("No opportunities match the current filters.", styles["Italic"]))
    else:
        col_widths = [14 * mm, 44 * mm, 40 * mm, 40 * mm, 22 * mm, 22 * mm, 24 * mm, 22 * mm, 24 * mm, 30 * mm, 22 * mm]
        elements.append(_pdf_table(OPP_HEADERS, rows, col_widths))

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


def build_opportunity_xlsx(opportunities: Iterable[Opportunity]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Opportunities"

    _xlsx_write_header(ws, OPP_HEADERS)
    rows = [_opportunity_row(opp) for opp in opportunities]
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    _xlsx_autosize(ws, OPP_HEADERS, rows)
    ws.freeze_panes = "A2"
    return _xlsx_to_bytes(wb)


# ------------------------------ Deals ----------------------------------------

DEAL_HEADERS = [
    "ID", "Customer", "Company", "Description", "Value (USD)", "Expected Close",
    "Status", "Exclusivity Start", "Exclusivity End", "Created",
]


def _deal_row(deal: DealRegistration) -> list[str]:
    return [
        deal.id,
        deal.customer_name,
        deal.company.name if deal.company else "",
        (deal.deal_description or "")[:200],
        f"{float(deal.estimated_value):,.2f}" if deal.estimated_value is not None else "",
        deal.expected_close_date.strftime("%Y-%m-%d") if deal.expected_close_date else "",
        deal.status.value.title() if deal.status else "",
        deal.exclusivity_start.strftime("%Y-%m-%d") if deal.exclusivity_start else "",
        deal.exclusivity_end.strftime("%Y-%m-%d") if deal.exclusivity_end else "",
        deal.created_at.strftime("%Y-%m-%d") if deal.created_at else "",
    ]


def build_deal_pdf(deals: Iterable[DealRegistration], subtitle: str | None = None) -> bytes:
    buf = BytesIO()
    doc = _make_pdf_doc(buf, "Deal Registrations Report")
    elements = _pdf_header_elements("Deal Registrations Report", subtitle)

    rows = [_deal_row(d) for d in deals]
    if not rows:
        styles = getSampleStyleSheet()
        elements.append(Paragraph("No deals match the current filters.", styles["Italic"]))
    else:
        col_widths = [14 * mm, 40 * mm, 40 * mm, 60 * mm, 24 * mm, 24 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm]
        elements.append(_pdf_table(DEAL_HEADERS, rows, col_widths))

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


def build_deal_xlsx(deals: Iterable[DealRegistration]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Deals"

    _xlsx_write_header(ws, DEAL_HEADERS)
    rows = [_deal_row(d) for d in deals]
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    _xlsx_autosize(ws, DEAL_HEADERS, rows)
    ws.freeze_panes = "A2"
    return _xlsx_to_bytes(wb)


# ------------------------------ Companies ------------------------------------

COMPANY_HEADERS = [
    "ID", "Name", "Type", "Parent Distributor", "Country", "Region", "City",
    "Industry", "Contact Email", "Tier", "Status", "Created",
]


def _company_row(c: Company) -> list[str]:
    return [
        c.id,
        c.name,
        c.company_type.value.title() if c.company_type else "",
        # Blank unless this is a reseller sitting under a distributor. The
        # caller must eager-load the relationship (exports._fetch_companies) —
        # a lazy load here would fail outside the greenlet context.
        c.parent_distributor.name if c.parent_distributor else "",
        c.country,
        c.region,
        c.city,
        c.industry,
        c.contact_email,
        # Blank rather than "Silver" for a customer — it has no tier.
        c.tier.value.title() if (c.tier and c.is_channel_partner) else "",
        c.status.value.title() if c.status else "",
        c.created_at.strftime("%Y-%m-%d") if c.created_at else "",
    ]


def build_company_xlsx(companies: Iterable[Company]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Companies"

    _xlsx_write_header(ws, COMPANY_HEADERS)
    rows = [_company_row(c) for c in companies]
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    _xlsx_autosize(ws, COMPANY_HEADERS, rows)
    ws.freeze_panes = "A2"
    return _xlsx_to_bytes(wb)


def build_company_pdf(companies: Iterable[Company], subtitle: str | None = None) -> bytes:
    buf = BytesIO()
    doc = _make_pdf_doc(buf, "Partner Companies Report")
    elements = _pdf_header_elements("Partner Companies Report", subtitle)

    rows = [_company_row(c) for c in companies]
    if not rows:
        styles = getSampleStyleSheet()
        elements.append(Paragraph("No companies match the current filters.", styles["Italic"]))
    else:
        # 12 columns summing to 270mm, which fits the 273mm of content width
        # a landscape A4 page has left after its 12mm side margins. Adding a
        # column means taking the width out of the wider text fields.
        col_widths = [
            12 * mm, 36 * mm, 20 * mm, 32 * mm, 20 * mm, 18 * mm, 18 * mm,
            26 * mm, 34 * mm, 16 * mm, 18 * mm, 20 * mm,
        ]
        elements.append(_pdf_table(COMPANY_HEADERS, rows, col_widths))

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


# ------------------------------ POCs -----------------------------------------

# Per-stage completion date columns, generated from the canonical stage list
# so a new stage flows through to the export automatically.
POC_HEADERS = [
    "ID", "Customer", "Partner", "Country", "City", "Status",
    "Start Date", "Target End", "End Date", "Stages Done",
    *[POC_STAGE_LABELS[k] for k in POC_STAGE_KEYS],
    "Sales Rep", "Worth (USD)",
]


def _poc_row(p: Poc) -> list:
    opp = p.opportunity
    return [
        p.id,
        opp.customer_name if opp else "",
        opp.company.name if opp and opp.company else "",
        opp.country if opp else "",
        opp.city if opp else "",
        p.status.value.replace("_", " ").title() if p.status else "",
        p.start_date.strftime("%Y-%m-%d") if p.start_date else "",
        p.target_end_date.strftime("%Y-%m-%d") if p.target_end_date else "",
        p.end_date.strftime("%Y-%m-%d") if p.end_date else "",
        f"{p.completed_stage_count}/{len(POC_STAGE_KEYS)}",
        *[
            (getattr(p, f"{k}_completed_at").strftime("%Y-%m-%d")
             if getattr(p, f"{k}_completed_at") else "")
            for k in POC_STAGE_KEYS
        ],
        opp.sales_rep.full_name if opp and opp.sales_rep else "",
        f"{float(opp.worth):,.2f}" if opp and opp.worth is not None else "",
    ]


def build_poc_pdf(pocs: Iterable[Poc], subtitle: str | None = None) -> bytes:
    buf = BytesIO()
    doc = _make_pdf_doc(buf, "POC Report")
    elements = _pdf_header_elements("POC Report", subtitle)

    rows = [_poc_row(p) for p in pocs]
    if not rows:
        styles = getSampleStyleSheet()
        elements.append(Paragraph("No POCs match the current filters.", styles["Italic"]))
    else:
        # 17 columns; keep the five stage-date columns narrow.
        stage_w = [18 * mm] * len(POC_STAGE_KEYS)
        col_widths = [
            10 * mm, 34 * mm, 30 * mm, 18 * mm, 18 * mm, 20 * mm,
            20 * mm, 20 * mm, 20 * mm, 16 * mm, *stage_w, 26 * mm, 22 * mm,
        ]
        elements.append(_pdf_table(POC_HEADERS, rows, col_widths))

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


def build_poc_xlsx(pocs: Iterable[Poc]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "POCs"

    _xlsx_write_header(ws, POC_HEADERS)
    rows = [_poc_row(p) for p in pocs]
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    _xlsx_autosize(ws, POC_HEADERS, rows)
    ws.freeze_panes = "A2"
    return _xlsx_to_bytes(wb)


# ------------------------------ Licences (post-PO) ---------------------------

LICENSE_HEADERS = [
    "ID", "Customer", "Partner", "Country", "Status", "PO Number",
    "PO Received", "PO Value (USD)", "Devices", "Nodes",
    "Activated", "Expires", "Days To Expiry",
]


def _license_row(lic: CustomerLicense, status: str) -> list:
    """`status` is passed in derived (not lic.status, which is a stale cache —
    see poc_service.derive_license_status)."""
    opp = lic.opportunity
    return [
        lic.id,
        opp.customer_name if opp else "",
        opp.company.name if opp and opp.company else "",
        opp.country if opp else "",
        status.replace("_", " ").title(),
        lic.po_number or "",
        lic.po_received_date.strftime("%Y-%m-%d") if lic.po_received_date else "",
        f"{float(lic.po_value):,.2f}" if lic.po_value is not None else "",
        lic.device_count if lic.device_count is not None else "",
        lic.node_count if lic.node_count is not None else "",
        lic.license_activated_at.strftime("%Y-%m-%d") if lic.license_activated_at else "",
        lic.license_expires_at.strftime("%Y-%m-%d") if lic.license_expires_at else "",
        lic.days_until_expiry if lic.days_until_expiry is not None else "",
    ]


def build_license_pdf(rows_in: Iterable[tuple], subtitle: str | None = None) -> bytes:
    """rows_in: iterable of (CustomerLicense, derived_status_str)."""
    buf = BytesIO()
    doc = _make_pdf_doc(buf, "Customer Licences Report")
    elements = _pdf_header_elements("Customer Licences Report", subtitle)

    rows = [_license_row(lic, status) for lic, status in rows_in]
    if not rows:
        styles = getSampleStyleSheet()
        elements.append(Paragraph("No licences match the current filters.", styles["Italic"]))
    else:
        col_widths = [
            12 * mm, 40 * mm, 34 * mm, 22 * mm, 24 * mm, 24 * mm,
            24 * mm, 26 * mm, 18 * mm, 18 * mm, 22 * mm, 22 * mm, 22 * mm,
        ]
        elements.append(_pdf_table(LICENSE_HEADERS, rows, col_widths))

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


def build_license_xlsx(rows_in: Iterable[tuple]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Licences"

    _xlsx_write_header(ws, LICENSE_HEADERS)
    rows = [_license_row(lic, status) for lic, status in rows_in]
    for r_idx, row in enumerate(rows, start=2):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    _xlsx_autosize(ws, LICENSE_HEADERS, rows)
    ws.freeze_panes = "A2"
    return _xlsx_to_bytes(wb)
