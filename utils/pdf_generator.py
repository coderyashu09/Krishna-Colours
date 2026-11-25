"""
ReportLab PDF Generation Service for Krishna Colour - Asian Paints.
Produces professional, high-resolution printable invoices, customer statements, and reports.
"""
import io
from decimal import Decimal
from typing import Dict, Any, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)

from config.settings import settings
from database.models import Bill
from utils.helpers import format_currency, number_to_words_inr


def generate_bill_pdf(bill: Bill) -> bytes:
    """
    Generate professional printable PDF invoice for a given Bill.
    Returns PDF bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ShopTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor(settings.COLOR_ACCENT),
        alignment=0,
    )
    subtitle_style = ParagraphStyle(
        "ShopSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#DC2626"),  # Asian Paints signature red accent
        alignment=0,
    )
    address_style = ParagraphStyle(
        "ShopAddress",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor(settings.COLOR_TEXT_SECONDARY),
        alignment=0,
    )
    invoice_title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=18,
        textColor=colors.HexColor(settings.COLOR_TEXT_PRIMARY),
        alignment=2,
    )
    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor(settings.COLOR_TEXT_PRIMARY),
        alignment=2,
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor(settings.COLOR_TEXT_PRIMARY),
    )
    cell_style = ParagraphStyle(
        "CellText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor(settings.COLOR_TEXT_PRIMARY),
    )
    cell_bold = ParagraphStyle(
        "CellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor(settings.COLOR_TEXT_PRIMARY),
    )
    cell_right = ParagraphStyle(
        "CellRight",
        parent=cell_style,
        alignment=2,
    )
    cell_right_bold = ParagraphStyle(
        "CellRightBold",
        parent=cell_bold,
        alignment=2,
    )

    story = []

    # 1. Header: Shop Branding (Left) & Invoice Title/Meta (Right)
    left_header = [
        Paragraph(settings.APP_NAME, title_style),
        Paragraph(f"Authorized Dealer & Tinting Center – {settings.APP_TAGLINE}", subtitle_style),
        Spacer(1, 2 * mm),
        Paragraph(f"{settings.APP_ADDRESS} | Phone: {settings.APP_PHONE}", address_style),
        Paragraph(f"GSTIN: {settings.APP_GSTIN} | State: {settings.APP_STATE}", address_style),
    ]

    right_header = [
        Paragraph("TAX INVOICE", invoice_title_style),
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Bill Number:</b> {bill.bill_number}", meta_style),
        Paragraph(f"<b>Date:</b> {bill.bill_date.strftime('%d-%b-%Y')}", meta_style),
        Paragraph(f"<b>Status:</b> {bill.payment_status}", meta_style),
    ]

    header_table = Table(
        [[left_header, right_header]],
        colWidths=[105 * mm, 75 * mm]
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)

    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor(settings.COLOR_ACCENT), spaceAfter=10))

    # 2. Customer Information Block
    cust = bill.customer
    cust_info = [
        Paragraph("<b>Billed To:</b>", section_heading),
        Paragraph(f"<b>{cust.name}</b> (Code: {cust.customer_code})", cell_style),
        Paragraph(f"Phone: {cust.mobile}" + (f" / {cust.alternate_mobile}" if cust.alternate_mobile else ""), cell_style),
        Paragraph(f"Address: {cust.address or 'Local'}, {cust.city or ''}".strip(), cell_style),
    ]

    bill_details = [
        Paragraph("<b>Payment & Order Info:</b>", section_heading),
        Paragraph(f"Payment Status: <b>{bill.payment_status}</b>", cell_style),
        Paragraph(f"Bill Status: <b>{bill.bill_status}</b>", cell_style),
        Paragraph(f"Place of Supply: <b>{settings.APP_STATE}</b>", cell_style),
    ]

    customer_table = Table(
        [[cust_info, bill_details]],
        colWidths=[100 * mm, 80 * mm]
    )
    customer_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(settings.COLOR_BG)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(settings.COLOR_BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(customer_table)

    story.append(Spacer(1, 4 * mm))

    # 3. Product Line Items Table
    headers = [
        Paragraph("#", cell_bold),
        Paragraph("Product Description", cell_bold),
        Paragraph("Qty", cell_right_bold),
        Paragraph("Rate (₹)", cell_right_bold),
        Paragraph("Disc (₹)", cell_right_bold),
        Paragraph("Total (₹)", cell_right_bold),
    ]

    items_rows = [headers]
    for idx, item in enumerate(bill.items, start=1):
        items_rows.append([
            Paragraph(str(idx), cell_style),
            Paragraph(item.product_name, cell_style),
            Paragraph(f"{item.quantity:.2f}", cell_right),
            Paragraph(f"{item.unit_price:.2f}", cell_right),
            Paragraph(f"{item.discount_amount:.2f}", cell_right),
            Paragraph(f"{item.line_total:.2f}", cell_right),
        ])

    items_table = Table(
        items_rows,
        colWidths=[10 * mm, 75 * mm, 22 * mm, 24 * mm, 24 * mm, 25 * mm]
    )
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(settings.COLOR_ACCENT)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(settings.COLOR_BORDER)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(items_table)

    story.append(Spacer(1, 3 * mm))

    # 4. Financial Calculations & Summary Block
    words_text = number_to_words_inr(bill.grand_total)

    summary_left = [
        Paragraph("<b>Amount in Words:</b>", section_heading),
        Paragraph(words_text, cell_style),
        Spacer(1, 4 * mm),
        Paragraph("<b>Terms & Conditions:</b>", section_heading),
        Paragraph("1. Goods once sold will not be accepted without original invoice.<br/>"
                  "2. Colors are mixed on automated Asian Paints computerized dispenser.<br/>"
                  "3. Manufacturer warranty applies as per Asian Paints standard guidelines.<br/>"
                  "4. Subject to local jurisdiction.", address_style),
    ]

    summary_right = [
        [Paragraph("Subtotal:", cell_bold), Paragraph(format_currency(bill.subtotal), cell_right)],
        [Paragraph("Discount:", cell_bold), Paragraph(format_currency(bill.discount), cell_right)],
    ]
    if bill.tax_rate > Decimal("0.00"):
        summary_right.append([
            Paragraph(f"Tax ({bill.tax_rate}%):", cell_bold),
            Paragraph(format_currency(bill.tax_amount), cell_right)
        ])
    summary_right.extend([
        [Paragraph("<b>Grand Total:</b>", cell_bold), Paragraph(f"<b>{format_currency(bill.grand_total)}</b>", cell_right_bold)],
        [Paragraph("Amount Paid:", cell_bold), Paragraph(format_currency(bill.amount_received), cell_right)],
        [Paragraph("<b>Outstanding Balance:</b>", cell_bold), Paragraph(f"<b>{format_currency(bill.outstanding_amount)}</b>", cell_right_bold)],
    ])

    summary_table_right = Table(
        summary_right,
        colWidths=[40 * mm, 38 * mm]
    )
    summary_table_right.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 2), (-1, 2), 0.5, colors.HexColor(settings.COLOR_BORDER)),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#EFF6FF")),  # Soft blue highlight for grand total
    ]))

    bottom_block = Table(
        [[summary_left, summary_table_right]],
        colWidths=[102 * mm, 78 * mm]
    )
    bottom_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(bottom_block)

    # 5. Signature Footer
    story.append(Spacer(1, 10 * mm))
    sig_table = Table(
        [
            [
                Paragraph("Customer Signature", cell_style),
                Paragraph(f"For <b>{settings.APP_NAME}</b><br/><br/><br/>Authorized Signatory", cell_right)
            ]
        ],
        colWidths=[90 * mm, 90 * mm]
    )
    sig_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether(sig_table))

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_customer_statement_pdf(statement_data: Dict[str, Any]) -> bytes:
    """Generate printable customer ledger statement."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm
    )
    styles = getSampleStyleSheet()
    cust = statement_data["customer"]

    title = ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=18, textColor=colors.HexColor(settings.COLOR_ACCENT))
    bold = ParagraphStyle("B", fontName="Helvetica-Bold", fontSize=9)
    norm = ParagraphStyle("N", fontName="Helvetica", fontSize=8.5)
    r_bold = ParagraphStyle("RB", parent=bold, alignment=2)
    r_norm = ParagraphStyle("RN", parent=norm, alignment=2)

    story = [
        Paragraph(settings.APP_NAME, title),
        Paragraph("Customer Account Statement / Ledger", ParagraphStyle("Sub", fontName="Helvetica-Bold", fontSize=12, textColor=colors.HexColor("#64748B"))),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>Customer:</b> {cust.name} ({cust.customer_code}) | <b>Mobile:</b> {cust.mobile}", norm),
        Paragraph(f"<b>Address:</b> {cust.address or 'N/A'}, {cust.city or ''}".strip(), norm),
        Spacer(1, 3 * mm),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor(settings.COLOR_ACCENT), spaceAfter=8),
    ]

    # Ledger Table
    headers = [
        Paragraph("Date", bold),
        Paragraph("Type", bold),
        Paragraph("Ref #", bold),
        Paragraph("Description", bold),
        Paragraph("Debit (₹)", r_bold),
        Paragraph("Credit (₹)", r_bold),
        Paragraph("Balance (₹)", r_bold),
    ]
    rows = [headers]
    for row in statement_data["ledger"]:
        rows.append([
            Paragraph(row["date"].strftime("%Y-%m-%d"), norm),
            Paragraph(row["type"], norm),
            Paragraph(row["ref_number"], norm),
            Paragraph(row["description"], norm),
            Paragraph(f"{row['debit']:.2f}" if row['debit'] > 0 else "-", r_norm),
            Paragraph(f"{row['credit']:.2f}" if row['credit'] > 0 else "-", r_norm),
            Paragraph(f"{row['balance']:.2f}", r_bold),
        ])

    table = Table(rows, colWidths=[20 * mm, 18 * mm, 24 * mm, 50 * mm, 22 * mm, 22 * mm, 24 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(settings.COLOR_BORDER)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        f"<b>Total Billed:</b> {format_currency(statement_data['total_billed'])} | "
        f"<b>Total Paid:</b> {format_currency(statement_data['total_paid'])} | "
        f"<b>Net Outstanding Balance:</b> {format_currency(statement_data['net_outstanding'])}",
        ParagraphStyle("Summ", fontName="Helvetica-Bold", fontSize=10, textColor=colors.HexColor(settings.COLOR_ACCENT))
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
