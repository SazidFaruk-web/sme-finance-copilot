"""What the owner's own records say about their capacity to save.

Every figure a roadmap shows starts here, from recorded transactions, invoices and obligations.
Nothing in this module asks a model anything, and nothing is invented: where the records are too
short to support a figure, the figure is None and the roadmap says so.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from sme_copilot.pilot.calculations import money
from sme_copilot.tools.analysis import add_months, month_start


@dataclass
class MonthFact:
    month: str          # YYYY-MM
    money_in: float
    money_out: float
    surplus: float
    index: float        # this month's money in, against the average month (1.0 = average)
    label: str          # peak | normal | low
    events: list[str] = field(default_factory=list)


@dataclass
class Facts:
    """A business's saving capacity, as recorded."""

    today: str
    months_of_history: int
    record_count: int
    cash_now: float
    monthly_in: float | None = None
    monthly_out: float | None = None
    monthly_surplus: float | None = None       # average money left over in a month
    best_month_surplus: float | None = None
    worst_month_surplus: float | None = None
    reserve: float = 0.0                       # money held back for a quiet month
    spare_cash: float = 0.0                    # cash that could start the goal today
    owed_to_you: float = 0.0
    bills_to_pay: float = 0.0
    committed_monthly: float = 0.0             # recurring obligations already promised
    months: list[MonthFact] = field(default_factory=list)
    season_known: bool = False
    confidence: str = "low"                    # low | medium | good
    gaps: list[str] = field(default_factory=list)   # reviewed ids, not sentences

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def stamp(self) -> str:
        return hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True, default=str).encode()).hexdigest()[:32]


def _month_rows(txns, start: date, end: date) -> list[tuple[str, float, float]]:
    """(month, money in, money out) for every month between start and end, including empty ones."""
    if txns is None or getattr(txns, "empty", True):
        return []
    df = txns[(txns["date"] >= str(start)) & (txns["date"] <= str(end))].copy()
    if df.empty:
        return []
    df["month"] = df["date"].dt.strftime("%Y-%m")
    rows = []
    cursor = month_start(start)
    while cursor <= end:
        key = cursor.strftime("%Y-%m")
        block = df[df["month"] == key]
        rows.append((key,
                     float(block[block["direction"] == "in"]["amount"].sum()),
                     float(block[block["direction"] == "out"]["amount"].sum())))
        cursor = add_months(cursor, 1)
    return rows


def gather(db, business, today: date, *, reserve: float | None = None, lookback_months: int = 18) -> Facts:
    """Read the records and work out what this business can realistically put aside each month."""
    from sme_copilot.tools import repo
    from sme_copilot.tools.analysis import events_for_month

    txns = repo.load_transactions(db, business.id, end=today)
    invoices = repo.load_invoices(db, business.id)
    obligations = repo.load_obligations(db, business.id)
    cash_now, _ = repo.cash_position(business, txns, today)

    # Whole months only: the current, part-finished month would understate a monthly average.
    last_complete = month_start(today) - timedelta(days=1)
    first = add_months(month_start(today), -lookback_months)
    rows = [r for r in _month_rows(txns, first, last_complete)]
    # Drop leading empty months before the business started recording.
    while rows and rows[0][1] == 0 and rows[0][2] == 0:
        rows.pop(0)

    facts = Facts(today=today.isoformat(), months_of_history=len(rows),
                  record_count=0 if txns is None or txns.empty else int(len(txns)),
                  cash_now=money(cash_now))

    if not invoices.empty:
        receivable = invoices[(invoices["kind"] == "receivable") & (~invoices["status"].isin(["draft", "paid", "written_off"]))]
        payable = invoices[(invoices["kind"] == "payable") & (~invoices["status"].isin(["draft", "paid", "written_off"]))]
        facts.owed_to_you = money(max(0.0, float((receivable["amount"] - receivable["amount_paid"]).sum())))
        facts.bills_to_pay = money(max(0.0, float((payable["amount"] - payable["amount_paid"]).sum())))
    facts.committed_monthly = money(sum(float(o.amount) for o in obligations if o.frequency == "monthly"))

    if rows:
        average_in = sum(r[1] for r in rows) / len(rows)
        surpluses = []
        for key, money_in, money_out in rows:
            year, mon = int(key[:4]), int(key[5:])
            surpluses.append(money_in - money_out)
            index = money_in / average_in if average_in else 0.0
            facts.months.append(MonthFact(
                month=key, money_in=money(money_in), money_out=money(money_out),
                surplus=money(money_in - money_out), index=round(index, 2),
                label="peak" if index >= 1.2 else "low" if index <= 0.8 else "normal",
                events=events_for_month(year, mon)))
        facts.monthly_in = money(average_in)
        facts.monthly_out = money(sum(r[2] for r in rows) / len(rows))
        facts.monthly_surplus = money(sum(surpluses) / len(surpluses))
        facts.best_month_surplus = money(max(surpluses))
        facts.worst_month_surplus = money(min(surpluses))
        facts.season_known = len(rows) >= 6 and any(m.label != "normal" for m in facts.months)

    # One quiet month of running costs stays untouched unless the owner sets their own reserve.
    default_reserve = facts.monthly_out or 0.0
    facts.reserve = money(reserve if reserve is not None else default_reserve)
    facts.spare_cash = money(max(0.0, facts.cash_now - facts.reserve - facts.bills_to_pay))

    facts.confidence = ("good" if facts.months_of_history >= 6 else
                        "medium" if facts.months_of_history >= 3 else "low")
    if facts.months_of_history < 3:
        facts.gaps.append("short_history")
    if facts.monthly_surplus is not None and facts.monthly_surplus <= 0:
        facts.gaps.append("no_surplus")
    if not facts.season_known:
        facts.gaps.append("season_unknown")
    if facts.bills_to_pay > facts.cash_now:
        facts.gaps.append("bills_exceed_cash")
    return facts
