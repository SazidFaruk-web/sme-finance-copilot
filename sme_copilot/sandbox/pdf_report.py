"""Loan-readiness report PDF (reportlab + a matplotlib forecast chart).

Everything in the report comes from deterministic tools; every page carries the disclaimer.
"""
from __future__ import annotations

import hashlib
import io
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from sme_copilot.tools.money import format_bdt  # noqa: E402

DISCLAIMER = ("Prepared by Ascent Copilot from the business's own records. Decision support only - not licensed "
              "financial advice, not a credit score, and not a lending decision. Financing terms are illustrative "
              "and must be verified with the lender. Forecasts are estimates.")


def _money(v: float | None) -> str:
    # reportlab's built-in fonts lack the Taka glyph; use "BDT" in the PDF.
    return "BDT " + format_bdt(v, symbol=False) if v is not None else "-"


def _chart(series: list[dict[str, Any]], threshold: float) -> bytes:
    fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=130)
    xs = [p["date"] for p in series]
    ax.fill_between(range(len(xs)), [p["low"] for p in series], [p["high"] for p in series], alpha=0.18,
                    color="#2563eb", label="80% range")
    ax.plot(range(len(xs)), [p["balance"] for p in series], color="#1d4ed8", linewidth=1.8, label="Forecast balance")
    ax.axhline(threshold, color="#d97706", linestyle="--", linewidth=1, label="Safety level")
    ax.axhline(0, color="#991b1b", linewidth=0.8)
    ticks = list(range(0, len(xs), max(1, len(xs) // 6)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(xs[i])[5:] for i in ticks], fontsize=7)
    ax.tick_params(axis="y", labelsize=7)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1e5:.1f}L"))
    ax.legend(fontsize=7, loc="best", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _table(rows: list[list[str]], widths: list[float] | None = None) -> Table:
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edff")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c7cdd8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
    ]))
    return t


def build_pdf(path: Path, *, business: Any, as_of: date, amount: float | None, purpose: str,
              profit: Any, monthly: list[Any], forecast: Any, aging: Any, readiness: Any, matches: Any) -> str:
    """Write the PDF to ``path`` and return its sha256."""
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=17, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=4,
                        textColor=colors.HexColor("#1e3a8a"))
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=8.8, leading=11.5)
    small = ParagraphStyle("s", parent=body, fontSize=7.4, leading=9.5, textColor=colors.HexColor("#555555"))
    story: list[Any] = []

    story += [Paragraph("Loan-Readiness Report", h1),
              Paragraph(f"<b>{business.name}</b> &middot; {business.sector} &middot; {business.district} &middot; "
                        f"as of {as_of.isoformat()}", body),
              Paragraph(f"Requested: {_money(amount) if amount else 'not specified'} for {purpose.replace('_', ' ')}",
                        body), Spacer(1, 6), Paragraph(DISCLAIMER, small)]

    story.append(Paragraph("1. Summary", h2))
    s30 = next((s for s in forecast.summaries if s.days == 30), forecast.summaries[0])
    story.append(_table([
        ["Metric", "Value", "Basis"],
        ["Loan-readiness score", f"{readiness.score:g} / 100 ({readiness.band.replace('_', ' ')})", "8 components, see section 5"],
        ["Revenue (last 6 months)", _money(profit.revenue), profit.period],
        ["Gross margin", f"{profit.gross_margin_pct}%" if profit.gross_margin_pct is not None else "-", "cash basis"],
        ["Net operating margin", f"{profit.net_margin_pct}%" if profit.net_margin_pct is not None else "-",
         "before loan repayments"],
        ["Cash balance now", _money(forecast.start_balance), "opening balance + recorded flows"],
        ["Lowest balance next 30 days", _money(s30.min_balance), str(s30.min_balance_date)],
        ["Receivables overdue", _money(aging.overdue_total if aging else 0), f"{aging.overdue_count if aging else 0} invoice(s)"],
    ], [5.2 * cm, 4.6 * cm, 6.8 * cm]))

    story.append(Paragraph("2. Monthly income and expenses", h2))
    rows = [["Month", "Income", "Expenses", "Net"]] + [[m.month, _money(m.income), _money(m.expense), _money(m.net)]
                                                        for m in monthly[-12:]]
    story.append(_table(rows, [3 * cm, 4 * cm, 4 * cm, 4 * cm]))

    story.append(Paragraph("3. Profitability (last 6 complete months)", h2))
    story.append(_table([
        ["Line", "Amount"], ["Revenue", _money(profit.revenue)], ["Cost of goods (purchases)", _money(profit.cogs)],
        ["Gross profit", _money(profit.gross_profit)], ["Variable operating costs", _money(profit.variable_opex)],
        ["Fixed operating costs", _money(profit.fixed_opex)], ["Operating profit", _money(profit.operating_profit)],
        ["Loan repayments (shown separately)", _money(profit.excluded.get("loan_repayments_and_financing_out"))],
    ], [7 * cm, 5 * cm]))

    story.append(Paragraph("4. 90-day cash-flow forecast", h2))
    series = [{"date": p.date.isoformat(), "balance": p.balance, "low": p.low, "high": p.high} for p in forecast.series]
    story.append(Image(io.BytesIO(_chart(series, forecast.low_balance_threshold)), width=17 * cm, height=6.1 * cm))
    story.append(Paragraph(" ".join(forecast.notes[:3]) or "Model: baseline from the last 90 days plus scheduled "
                           "collections, payables and recurring obligations.", small))

    story.append(Paragraph("5. Loan-readiness components", h2))
    story.append(_table([["Component", "Points", "Evidence"]] +
                        [[c.name, f"{c.points:g} / {c.max_points:g}", Paragraph(c.value, small)]
                         for c in readiness.components], [4.5 * cm, 2.3 * cm, 9.8 * cm]))
    if readiness.top_tips:
        story.append(Paragraph("<b>How to improve:</b> " + " ".join(f"&bull; {t}" for t in readiness.top_tips), body))

    story.append(Paragraph("6. Financing options (illustrative - verify with lender)", h2))
    rec_rows = [["Option", "Offer", "EMI (mid rate)", "Total cost of credit", "Why"]]
    for m in matches.recommendations[:5]:
        cm_ = m.cost_mid
        rec_rows.append([Paragraph(m.name, small), _money(m.offered_amount), _money(cm_.emi if cm_ else None),
                         _money(cm_.total_cost_of_credit if cm_ else None), Paragraph("; ".join(m.reasons[:2]), small)])
    story.append(_table(rec_rows, [4.2 * cm, 2.6 * cm, 2.5 * cm, 2.8 * cm, 4.6 * cm]))
    if matches.rejected:
        story.append(Paragraph("<b>Not a fit now:</b> " + "; ".join(f"{r.name} ({r.reasons[0]})"
                                                                    for r in matches.rejected[:4]), small))

    story.append(Paragraph("7. Data sources", h2))
    story.append(Paragraph("Figures are computed from: " + "; ".join(profit.trace.sources[:6]) +
                           f". {profit.trace.row_count} transaction rows used for profitability.", small))
    story += [Spacer(1, 8), Paragraph(DISCLAIMER, small)]

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, title=f"Loan-readiness report - {business.name}",
                            author="Ascent Copilot")
    doc.build(story)
    return hashlib.sha256(path.read_bytes()).hexdigest()
