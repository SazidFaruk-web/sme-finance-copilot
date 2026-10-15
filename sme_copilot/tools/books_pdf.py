"""Small printable PDFs for bookkeeping: invoices and tabular reports (reportlab, no external fonts)."""
from __future__ import annotations

import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sme_copilot.tools.money import format_bdt


def pdf_money(v: float | None, style: str = "lakh") -> str:
    # reportlab's built-in fonts lack the Taka glyph; use "BDT" in the PDF.
    return "BDT " + format_bdt(v, style=style, symbol=False, decimals=2) if v is not None else "-"


def _table(rows: list[list[Any]], col_widths: list[float] | None = None, right_cols: tuple[int, ...] = ()) -> Table:
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    style = [("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
             ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#1c5cab")),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fa")]),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    style += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in right_cols]
    t.setStyle(TableStyle(style))
    return t


def table_pdf(title: str, subtitle: str, header: list[str], rows: list[list[Any]], *,
              right_cols: tuple[int, ...] = (), notes: list[str] | None = None) -> bytes:
    buf = io.BytesIO()
    ss = getSampleStyleSheet()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.4 * cm,
                            bottomMargin=1.4 * cm, title=title)
    story = [Paragraph(escape(title), ss["Title"]), Paragraph(escape(subtitle), ss["Normal"]), Spacer(1, 10),
             _table([header, *rows], right_cols=right_cols)]
    for n in notes or []:
        story += [Spacer(1, 6), Paragraph(escape(n), ss["Italic"])]
    doc.build(story)
    return buf.getvalue()


def invoice_pdf(*, business: dict[str, Any], invoice: dict[str, Any], lines: list[dict[str, Any]],
                payments: list[dict[str, Any]], style: str = "lakh") -> bytes:
    buf = io.BytesIO()
    ss = getSampleStyleSheet()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, title=f"Invoice {invoice['invoice_no']}")
    m = lambda v: pdf_money(v, style)  # noqa: E731
    label = "INVOICE" if invoice["kind"] == "receivable" else "SUPPLIER BILL"
    biz = f"<b>{escape(business['name'])}</b><br/>{escape(business.get('district', ''))}"
    meta = (f"<b>{label}</b><br/>No. {escape(invoice['invoice_no'])}<br/>Date {invoice['issue_date']}<br/>"
            f"Due {invoice['due_date']}")
    head = Table([[Paragraph(biz, ss["Normal"]), Paragraph(meta, ss["Normal"])]], colWidths=[10 * cm, 7 * cm])
    who = "Bill to" if invoice["kind"] == "receivable" else "From"
    to = Paragraph(f"<b>{who}:</b> {escape(invoice['counterparty'])}", ss["Normal"])
    rows = [["#", "Description", "Qty", "Rate", "Amount"]]
    for n, ln in enumerate(lines, 1):
        rows.append([n, ln["description"], f"{ln['quantity']:g}", m(ln["rate"]), m(ln["quantity"] * ln["rate"])])
    rows += [["", "", "", "Total", m(invoice["amount"])], ["", "", "", "Paid", m(invoice["amount_paid"])],
             ["", "", "", "Balance due", m(invoice["amount"] - invoice["amount_paid"])]]
    items = _table(rows, [1 * cm, 8 * cm, 1.6 * cm, 3.2 * cm, 3.4 * cm], right_cols=(2, 3, 4))
    items.setStyle(TableStyle([("FONTNAME", (3, -3), (-1, -1), "Helvetica-Bold")]))
    story = [head, Spacer(1, 14), to, Spacer(1, 12), items]
    if payments:
        story += [Spacer(1, 12), Paragraph("<b>Payments received</b>" if invoice["kind"] == "receivable"
                                           else "<b>Payments made</b>", ss["Normal"]),
                  _table([["Date", "Channel", "Amount"],
                          *[[p["date"], p["channel"], m(p["amount"])] for p in payments]], right_cols=(2,))]
    if invoice.get("notes"):
        story += [Spacer(1, 12), Paragraph(escape(invoice["notes"]), ss["Italic"])]
    story += [Spacer(1, 18), Paragraph(f"Status: {invoice['status'].upper()}", ss["Normal"])]
    doc.build(story)
    return buf.getvalue()
