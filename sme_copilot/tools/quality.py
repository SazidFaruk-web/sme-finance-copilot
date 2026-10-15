"""Data-quality checks: duplicate detection and anomaly flagging (deterministic)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from statistics import median

from .textnorm import normalize


@dataclass
class TxnKey:
    """Minimal view of a transaction for comparisons (new rows have id=None)."""
    id: int | None
    txn_date: date
    amount: float
    direction: str
    description: str = ""
    reference: str = ""
    counterparty: str = ""
    category: str = ""


def _desc(t: TxnKey) -> str:
    return normalize(f"{t.counterparty} {t.description}")[:80]


def duplicate_reason(new: TxnKey, old: TxnKey) -> str | None:
    if new.direction != old.direction or abs(new.amount - old.amount) > 0.005:
        return None
    if new.reference and old.reference and new.reference.strip().lower() == old.reference.strip().lower():
        return f"same reference '{new.reference}'"
    day_gap = abs((new.txn_date - old.txn_date).days)
    if day_gap == 0 and _desc(new) == _desc(old):
        return "same date, amount, direction and description"
    if day_gap <= 1:
        a, b = _desc(new), _desc(old)
        if a and b and SequenceMatcher(None, a, b).ratio() >= 0.85:
            return f"same amount within {day_gap} day(s) and near-identical description"
    return None


def find_duplicates(new_rows: list[TxnKey], existing: list[TxnKey]) -> dict[int, tuple[str, str]]:
    """Return {index_in_new_rows: (duplicate_of, reason)}; duplicate_of is 'txn:<id>' or 'row:<i>'.

    New rows are compared with already-stored rows using every rule in duplicate_reason. Within one
    import, identical rows are separate real transactions (two "iPhone cover 200" sold on one day are
    two lines in the khata), so rows of the same batch only duplicate each other when they share a
    reference such as a Trx ID. Existing rows are bucketed by (direction, rounded amount) so this stays ~O(n).
    """
    buckets: dict[tuple[str, int], list[tuple[str, TxnKey]]] = {}
    for t in existing:
        buckets.setdefault((t.direction, round(t.amount * 100)), []).append((f"txn:{t.id}", t))
    batch_refs: dict[tuple[str, int, str], int] = {}
    out: dict[int, tuple[str, str]] = {}
    for i, t in enumerate(new_rows):
        key = (t.direction, round(t.amount * 100))
        bucket = buckets.get(key, [])
        for j, (ref, old) in enumerate(bucket):
            reason = duplicate_reason(t, old)
            if reason:
                out[i] = (ref, reason)
                del bucket[j]  # one stored row stands for one new row: 3 covers vs 2 stored -> 1 is new
                break
        if i in out:
            continue
        ref_key = (*key, (t.reference or "").strip().lower())
        if ref_key[2] and ref_key in batch_refs:
            out[i] = (f"row:{batch_refs[ref_key]}", f"same reference '{t.reference}'")
        elif ref_key[2]:
            batch_refs[ref_key] = i
    return out


def _mad(values: list[float], med: float) -> float:
    return median([abs(v - med) for v in values]) if values else 0.0


def detect_anomalies(txns: list[TxnKey], *, min_samples: int = 6, z_threshold: float = 3.5) -> dict[int, str]:
    """Flag unusual outflows. Returns {txn id: plain-language reason}.

    * Per category with >= min_samples history: robust z-score (median / MAD), flagged when
      z > 3.5 and the amount is more than 2x the category median.
    * Thin categories: compared with the median of all outflows (> 5x and > ৳50,000).
    * A first-ever payment to a new counterparty above the 90th percentile of outflows.
    """
    outs = [t for t in txns if t.direction == "out" and t.id is not None]
    if not outs:
        return {}
    flags: dict[int, str] = {}
    by_cat: dict[str, list[TxnKey]] = {}
    for t in outs:
        by_cat.setdefault(t.category or "uncategorized", []).append(t)
    all_amounts = sorted(t.amount for t in outs)
    overall_med = median(all_amounts)
    p90 = all_amounts[int(0.9 * (len(all_amounts) - 1))]

    for cat, items in by_cat.items():
        amounts = [t.amount for t in items]
        if len(items) >= min_samples:
            med = median(amounts)
            mad = _mad(amounts, med)
            for t in items:
                if mad > 0:
                    z = 0.6745 * (t.amount - med) / mad
                    if z > z_threshold and t.amount > 2 * med:
                        flags[t.id] = (f"{t.amount:,.0f} is {t.amount / med:.1f}x your usual {cat} payment "
                                       f"(median {med:,.0f}, robust z={z:.1f})")
                elif t.amount > 3 * med:
                    flags[t.id] = f"{t.amount:,.0f} is {t.amount / med:.1f}x your usual {cat} payment (median {med:,.0f})"
        else:
            for t in items:
                if overall_med > 0 and t.amount > 5 * overall_med and t.amount > 50_000:
                    flags[t.id] = (f"{t.amount:,.0f} is {t.amount / overall_med:.1f}x your typical outflow "
                                   f"(median {overall_med:,.0f}) in a rarely used category '{cat}'")

    # New-counterparty check only for recent activity: the first-ever payment to every supplier
    # a year ago is not news.
    latest = max(t.txn_date for t in outs)
    seen: set[str] = set()
    for t in sorted(outs, key=lambda x: (x.txn_date, x.id or 0)):
        cp = normalize(t.counterparty)
        if not cp:
            continue
        recent = (latest - t.txn_date).days <= 60
        if recent and cp not in seen and t.amount >= p90 and len(outs) >= 20 and t.id not in flags \
                and t.category not in ("rent", "salary", "utilities", "loan_repayment", "tax_vat"):
            flags[t.id] = f"first payment to new counterparty '{t.counterparty}' and in your top 10% of outflows"
        seen.add(cp)
    return flags
