"""Business data ingestion: CSV / Excel / pasted text -> normalised transactions or invoices.

Supported layouts (auto-detected, or forced with ``doc_type``):
* sales / expense ledgers: date, description, amount (+ optional type/category/party)
* bank statements: date, narration, debit/withdrawal, credit/deposit, balance
* mobile-wallet statements (bKash / Nagad / Rocket style): date, trx id, transaction type,
  counterparty account, amount, fee, balance, status
* invoices (receivable or payable): invoice no, customer/supplier, amount, issue/due/paid date

Every stored row keeps ``batch_id`` + ``source_row`` (1-based spreadsheet row) so any number
the copilot reports can be traced back to the exact rows of the exact file.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from sme_copilot.models import ImportBatch, Invoice, Transaction
from sme_copilot.security.injection import scan
from sme_copilot.security.pii import mask_account

from .categorize import categories, categorize, category_config
from .money import parse_amount
from .nl_entry import ParsedEntry, parse_date_any
from .quality import TxnKey, detect_anomalies, find_duplicates
from .textnorm import normalize

DOC_TYPES = ("auto", "sales", "expenses", "bank", "wallet", "invoices", "ledger")

# canonical field -> header synonyms (normalised, English + Bangla)
SYNONYMS: dict[str, list[str]] = {
    "date": ["date", "txn date", "transaction date", "trx date", "value date", "posting date", "tran date",
             "তারিখ", "date & time", "date time", "datetime", "time"],
    "description": ["description", "details", "narration", "particulars", "remarks", "note", "notes", "memo",
                    "বিবরণ", "item", "items", "product", "purpose"],
    "amount": ["amount", "amt", "amount (bdt)", "amount(bdt)", "amount bdt", "taka", "tk", "bdt", "value", "total",
               "টাকা", "পরিমাণ", "invoice amount", "net amount"],
    "debit": ["debit", "withdrawal", "withdrawals", "dr", "debit amount", "paid out", "money out", "out", "খরচ"],
    "credit": ["credit", "deposit", "deposits", "cr", "credit amount", "paid in", "money in", "in", "জমা"],
    "type": ["type", "transaction type", "txn type", "trx type", "direction", "dr/cr", "in/out", "ধরন"],
    "category": ["category", "head", "account head", "expense head", "ক্যাটাগরি", "খাত"],
    "counterparty": ["counterparty", "party", "customer", "client", "buyer", "supplier", "vendor", "payee", "payer",
                     "name", "from/to", "to/from", "receiver", "sender", "account name", "ক্রেতা", "সরবরাহকারী"],
    "account": ["counterparty account", "account", "account no", "account number", "wallet", "wallet no",
                "mobile", "mobile no", "phone", "phone no", "number", "to account", "from account"],
    "reference": ["reference", "ref", "ref no", "trx id", "trxid", "transaction id", "txn id", "txnid",
                  "cheque no", "chq no", "voucher no", "receipt no"],
    "balance": ["balance", "running balance", "closing balance", "available balance", "ব্যালেন্স"],
    "fee": ["fee", "charge", "charges", "service charge", "fees"],
    "status": ["status", "state"],
    "channel": ["channel", "mode", "payment mode", "payment method", "method"],
    "quantity": ["qty", "quantity", "pcs", "units", "পরিমাণ (পিস)"],
    # invoice-specific
    "invoice_no": ["invoice no", "invoice", "invoice number", "inv no", "bill no", "challan no", "invoice #"],
    "issue_date": ["issue date", "invoice date", "bill date", "issued"],
    "due_date": ["due date", "due", "payment due", "due on"],
    "paid_date": ["paid date", "payment date", "paid on", "settled on"],
    "kind": ["kind", "invoice type", "receivable/payable"],
    "amount_paid": ["amount paid", "paid amount", "paid"],
}


@dataclass
class RowError:
    row: int
    reason: str


@dataclass
class NormalizedTxn:
    txn_date: date
    amount: float
    direction: str
    category: str
    description: str = ""
    counterparty: str = ""
    channel: str = "cash"
    account_ref: str | None = None
    reference: str = ""
    quantity: float | None = None
    source_row: int | None = None
    categorized_by: str = "rule"
    category_confidence: float = 1.0
    flags: list[str] = field(default_factory=list)


@dataclass
class NormalizedInvoice:
    kind: str
    counterparty: str
    amount: float
    issue_date: date
    due_date: date
    invoice_no: str = ""
    paid_date: date | None = None
    amount_paid: float = 0.0
    status: str = "open"
    phone: str | None = None
    notes: str = ""
    source_row: int | None = None
    flags: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    doc_type: str
    transactions: list[NormalizedTxn] = field(default_factory=list)
    invoices: list[NormalizedInvoice] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    rows_total: int = 0
    column_map: dict[str, str] = field(default_factory=dict)


# ----------------------------------------------------------------------------- reading
def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """Read CSV/TSV/XLSX into a DataFrame of strings, locating the real header row (bank
    statements often have a few lines of account info above the table)."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        raw = pd.read_excel(io.BytesIO(content), header=None, dtype=str)
    else:
        text = None
        for enc in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("could not decode file (use UTF-8 CSV or XLSX)")
        sep = "\t" if text.count("\t") > text.count(",") else ","
        # csv module rather than pandas: statements have ragged preamble lines (1 field) above
        # the real table, which makes pandas guess the wrong column count and drop rows.
        rows = list(csv.reader(io.StringIO(text), delimiter=sep))
        width = max((len(r) for r in rows), default=0)
        raw = pd.DataFrame([r + [""] * (width - len(r)) for r in rows], dtype=str)
    raw = raw.fillna("")
    header_idx = _find_header_row(raw)
    header = [str(h).strip() for h in raw.iloc[header_idx].tolist()]
    df = raw.iloc[header_idx + 1:].copy()
    df.columns = _dedupe_headers(header)
    df["__row__"] = [header_idx + 2 + i for i in range(len(df))]  # 1-based spreadsheet row numbers
    df = df[df.drop(columns="__row__").apply(lambda r: any(str(v).strip() for v in r), axis=1)]
    return df.reset_index(drop=True)


def _dedupe_headers(cols: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for c in cols:
        c = c or "col"
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out


def _find_header_row(raw: pd.DataFrame) -> int:
    all_syn = {s for syns in SYNONYMS.values() for s in syns}
    best_idx, best_score = 0, -1
    for i in range(min(15, len(raw))):
        cells = [normalize(str(v)) for v in raw.iloc[i].tolist()]
        score = sum(1 for c in cells if c in all_syn)
        if score > best_score:
            best_idx, best_score = i, score
        if score >= 3:
            break
    return best_idx


def map_columns(columns: list[str]) -> dict[str, str]:
    """canonical field -> actual column name. Exact synonym matches beat partial ones."""
    mapping: dict[str, str] = {}
    norm_cols = {c: normalize(c) for c in columns if c != "__row__"}
    # Pass 1: exact matches, in SYNONYMS order (so "invoice no" is not taken by "amount").
    for canon, syns in SYNONYMS.items():
        for col, nc in norm_cols.items():
            if col in mapping.values():
                continue
            if nc in syns:
                mapping.setdefault(canon, col)
                break
    # Pass 2: containment for anything still unmapped (e.g. "Amount (Tk.)").
    for canon, syns in SYNONYMS.items():
        if canon in mapping:
            continue
        for col, nc in norm_cols.items():
            if col in mapping.values():
                continue
            if any(len(s) > 2 and s in nc for s in syns):
                mapping[canon] = col
                break
    return mapping


def detect_doc_type(df: pd.DataFrame, mapping: dict[str, str]) -> str:
    if "due_date" in mapping or "invoice_no" in mapping:
        return "invoices"
    if "type" in mapping:
        values = {normalize(str(v)) for v in df[mapping["type"]].head(200)}
        wallet = set(category_config().get("wallet_types", {}).keys())
        if len(values & wallet) >= 1 and ("fee" in mapping or "reference" in mapping or "balance" in mapping):
            return "wallet"
    if "debit" in mapping and "credit" in mapping:
        return "bank"
    return "ledger"


# ----------------------------------------------------------------------------- normalising
def _get(row: pd.Series, mapping: dict[str, str], key: str) -> str:
    col = mapping.get(key)
    return str(row[col]).strip() if col is not None and col in row else ""


_NUMBER_LIKE = re.compile(r"\+?[\d][\d\s-]{8,}")

_CHANNEL_WORDS = {"bkash": "bkash", "nagad": "nagad", "rocket": "rocket", "bank": "bank", "cash": "cash",
                  "card": "card", "cheque": "bank", "check": "bank", "বিকাশ": "bkash", "নগদ": "cash"}


def _channel(text: str, default: str) -> str:
    n = normalize(text)
    for k, v in _CHANNEL_WORDS.items():
        if k in n:
            return v
    return default


def _direction_from_type(value: str) -> str | None:
    v = normalize(value)
    if not v:
        return None
    if v in ("in", "income", "credit", "cr", "sale", "sales", "receipt", "received", "deposit", "আয়", "জমা"):
        return "in"
    if v in ("out", "expense", "expenses", "debit", "dr", "payment", "purchase", "paid", "withdrawal", "খরচ", "ব্যয়"):
        return "out"
    wt = (category_config().get("wallet_types") or {}).get(v)
    return wt["direction"] if wt else None


def _resolve_category(file_cat: str, text: str, direction: str) -> tuple[str, str, float]:
    if file_cat:
        nc = normalize(file_cat).replace(" ", "_")
        if nc in categories():
            return nc, "file", 1.0
        m = categorize(file_cat, direction)
        if m.category != "uncategorized":
            return m.category, "file", max(0.7, m.confidence)
    m = categorize(text, direction)
    return m.category, "rule", m.confidence


def normalize_transactions(df: pd.DataFrame, mapping: dict[str, str], doc_type: str) -> ParseResult:
    res = ParseResult(doc_type=doc_type, rows_total=len(df), column_map=mapping)
    wallet_types = category_config().get("wallet_types") or {}
    default_channel = {"wallet": "bkash", "bank": "bank"}.get(doc_type, "cash")
    for _, row in df.iterrows():
        rn = int(row["__row__"])
        d = parse_date_any(_get(row, mapping, "date"))
        if d is None:
            res.errors.append(RowError(rn, f"unreadable date '{_get(row, mapping, 'date')}'"))
            continue
        status = normalize(_get(row, mapping, "status"))
        if status and status not in ("success", "successful", "completed", "complete", "done", "ok", "posted"):
            res.errors.append(RowError(rn, f"skipped: status '{status}'"))
            continue
        desc = _get(row, mapping, "description")
        party = _get(row, mapping, "counterparty")
        account = _get(row, mapping, "account") or None
        if _NUMBER_LIKE.fullmatch(party):
            # Wallet statements put the phone/account number in the counterparty column: keep it
            # only in the encrypted account_ref field and store a masked display name.
            account, party = account or party, f"acct {mask_account(re.sub(r'\D', '', party))}"
        typ = _get(row, mapping, "type")
        direction: str | None = None
        amount: float | None = None
        wallet_cat: str | None = None

        if "debit" in mapping or "credit" in mapping:
            dr = parse_amount(_get(row, mapping, "debit")) or 0.0
            cr = parse_amount(_get(row, mapping, "credit")) or 0.0
            if dr and not cr:
                direction, amount = "out", abs(dr)
            elif cr and not dr:
                direction, amount = "in", abs(cr)
        if amount is None:
            amount = parse_amount(_get(row, mapping, "amount"))
            if amount is None:
                res.errors.append(RowError(rn, "missing or unreadable amount"))
                continue
            wt = wallet_types.get(normalize(typ)) if typ else None
            if wt:
                direction, wallet_cat = wt["direction"], wt.get("category")
            elif typ:
                direction = _direction_from_type(typ)
            if direction is None and amount < 0:
                direction = "out"
            if direction is None:
                direction = {"sales": "in", "expenses": "out"}.get(doc_type)
            if direction is None:
                m = categorize(f"{desc} {party}")
                direction = m.direction or "out"
            amount = abs(amount)
        if amount == 0:
            res.errors.append(RowError(rn, "zero amount"))
            continue

        text = f"{desc} {party} {typ}"
        if wallet_cat and not _get(row, mapping, "category"):
            cat, by, conf = wallet_cat, "rule", 0.8
            m = categorize(f"{desc} {party}", direction)
            if m.category not in ("uncategorized",) and m.confidence > 0.6:
                cat, conf = m.category, m.confidence
        else:
            cat, by, conf = _resolve_category(_get(row, mapping, "category"), text, direction)

        flags: list[str] = []
        sc = scan(f"{desc} {party}")
        if sc.suspicious:
            flags.append("injection_suspect")
        qty = parse_amount(_get(row, mapping, "quantity"))
        res.transactions.append(NormalizedTxn(
            txn_date=d, amount=round(amount, 2), direction=direction, category=cat,
            description=desc[:500], counterparty=party[:200],
            channel=_channel(_get(row, mapping, "channel") or typ, default_channel),
            account_ref=account, reference=_get(row, mapping, "reference")[:120],
            quantity=qty, source_row=rn, categorized_by=by, category_confidence=conf, flags=flags))

        fee = parse_amount(_get(row, mapping, "fee")) or 0.0
        if fee > 0:
            res.transactions.append(NormalizedTxn(
                txn_date=d, amount=round(abs(fee), 2), direction="out", category="mobile_fees",
                description=f"Fee for {typ or 'transaction'} {_get(row, mapping, 'reference')}".strip(),
                channel=default_channel, reference=(_get(row, mapping, "reference") + "-fee")[:120],
                source_row=rn, categorized_by="rule", category_confidence=1.0))
    return res


def normalize_invoices(df: pd.DataFrame, mapping: dict[str, str]) -> ParseResult:
    res = ParseResult(doc_type="invoices", rows_total=len(df), column_map=mapping)
    party_col = (mapping.get("counterparty") or "").lower()
    for _, row in df.iterrows():
        rn = int(row["__row__"])
        amount = parse_amount(_get(row, mapping, "amount"))
        issue = parse_date_any(_get(row, mapping, "issue_date") or _get(row, mapping, "date"))
        due = parse_date_any(_get(row, mapping, "due_date"))
        party = _get(row, mapping, "counterparty")
        if amount is None or issue is None or not party:
            res.errors.append(RowError(rn, "invoice needs amount, issue date and customer/supplier"))
            continue
        due = due or issue
        kind_raw = normalize(_get(row, mapping, "kind") or _get(row, mapping, "type"))
        if kind_raw in ("payable", "purchase", "supplier", "bill", "ap"):
            kind = "payable"
        elif kind_raw in ("receivable", "sale", "sales", "customer", "ar"):
            kind = "receivable"
        else:
            kind = "payable" if any(w in party_col for w in ("supplier", "vendor", "payee")) else "receivable"
        paid = parse_date_any(_get(row, mapping, "paid_date"))
        paid_amt = parse_amount(_get(row, mapping, "amount_paid")) or (abs(amount) if paid else 0.0)
        st = normalize(_get(row, mapping, "status"))
        if paid_amt >= abs(amount) - 0.005 or st in ("paid", "settled", "closed"):
            status, paid_amt = "paid", abs(amount)
        elif paid_amt > 0 or st == "partial":
            status = "partial"
        else:
            status = "open"
        notes = _get(row, mapping, "description")
        flags = ["injection_suspect"] if scan(f"{notes} {party}").suspicious else []
        res.invoices.append(NormalizedInvoice(
            kind=kind, counterparty=party[:200], amount=round(abs(amount), 2), issue_date=issue, due_date=due,
            invoice_no=_get(row, mapping, "invoice_no")[:60], paid_date=paid if status == "paid" else None,
            amount_paid=round(paid_amt, 2), status=status, phone=_get(row, mapping, "account") or None,
            notes=notes[:500], source_row=rn, flags=flags))
    return res


def parse_table(content: bytes, filename: str, doc_type: str = "auto") -> ParseResult:
    if doc_type not in DOC_TYPES:
        raise ValueError(f"doc_type must be one of {DOC_TYPES}")
    df = read_table(content, filename)
    mapping = map_columns(list(df.columns))
    detected = detect_doc_type(df, mapping) if doc_type == "auto" else doc_type
    if "date" not in mapping and detected != "invoices":
        raise ValueError(f"could not find a date column. Columns seen: {list(df.columns)[:12]}")
    if detected == "invoices":
        return normalize_invoices(df, mapping)
    return normalize_transactions(df, mapping, detected)


# ----------------------------------------------------------------------------- persistence
@dataclass
class ImportReport:
    batch_id: int | None
    filename: str
    doc_type: str
    rows_total: int
    imported: int
    duplicates: list[dict[str, Any]]
    anomalies: list[dict[str, Any]]
    injection_flags: list[dict[str, Any]]
    uncategorized: int
    errors: list[dict[str, Any]]
    column_map: dict[str, str]
    already_imported: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _existing_keys(session: Session, business_id: int) -> list[TxnKey]:
    rows = session.execute(select(
        Transaction.id, Transaction.txn_date, Transaction.amount, Transaction.direction, Transaction.description,
        Transaction.reference, Transaction.counterparty, Transaction.category,
    ).where(Transaction.business_id == business_id, Transaction.is_duplicate.is_(False))).all()
    return [TxnKey(*r) for r in rows]


def import_file(session: Session, business_id: int, content: bytes, filename: str, *, doc_type: str = "auto",
                actor: str = "") -> ImportReport:
    sha = hashlib.sha256(content).hexdigest()
    prev = session.scalar(select(ImportBatch).where(ImportBatch.business_id == business_id,
                                                    ImportBatch.file_sha256 == sha))
    if prev is not None:
        return ImportReport(prev.id, filename, prev.doc_type, prev.rows_total, 0, [], [], [], 0, [], {},
                            already_imported=True)
    parsed = parse_table(content, filename, doc_type)
    batch = ImportBatch(business_id=business_id, filename=filename[:255], doc_type=parsed.doc_type,
                        file_sha256=sha, rows_total=parsed.rows_total, created_by=actor)
    session.add(batch)
    session.flush()
    source = "xlsx" if filename.lower().endswith((".xlsx", ".xls", ".xlsm")) else "csv"
    if parsed.doc_type == "invoices":
        report = _store_invoices(session, business_id, parsed, batch, source)
    else:
        report = store_transactions(session, business_id, parsed.transactions, source=f"{source}:{filename}",
                                    batch=batch)
        report.errors = [e.__dict__ for e in parsed.errors]
        report.column_map = parsed.column_map
        report.rows_total = parsed.rows_total
        report.doc_type = parsed.doc_type
        report.filename = filename
    batch.imported = report.imported
    batch.duplicates = len(report.duplicates)
    batch.anomalies = len(report.anomalies)
    batch.injection_flags = len(report.injection_flags)
    session.flush()
    return report


def store_transactions(session: Session, business_id: int, rows: list[NormalizedTxn], *, source: str,
                       batch: ImportBatch | None = None) -> ImportReport:
    existing = _existing_keys(session, business_id)
    keys = [TxnKey(None, r.txn_date, r.amount, r.direction, r.description, r.reference, r.counterparty, r.category)
            for r in rows]
    dups = find_duplicates(keys, existing)
    objs: list[Transaction] = []
    for r in rows:
        objs.append(Transaction(
            business_id=business_id, txn_date=r.txn_date, amount=r.amount, direction=r.direction,
            category=r.category, counterparty=r.counterparty, description=r.description, channel=r.channel,
            account_ref=r.account_ref, reference=r.reference, quantity=r.quantity, source=source[:40],
            batch_id=batch.id if batch else None, source_row=r.source_row, flags=list(r.flags),
            categorized_by=r.categorized_by, category_confidence=r.category_confidence))
    session.add_all(objs)
    session.flush()
    dup_report = []
    for i, (ref, reason) in dups.items():
        o = objs[i]
        o.is_duplicate = True
        if ref.startswith("txn:"):
            o.duplicate_of = int(ref[4:])
        else:
            o.duplicate_of = objs[int(ref[4:])].id
        o.flags = [*o.flags, "duplicate"]
        dup_report.append({"id": o.id, "row": o.source_row, "duplicate_of": o.duplicate_of, "reason": reason,
                           "amount": o.amount, "date": o.txn_date.isoformat()})
    anomalies = refresh_anomalies(session, business_id, only_ids={o.id for o in objs})
    inj = [{"id": o.id, "row": o.source_row, "text": (o.description or o.counterparty)[:120]}
           for o in objs if "injection_suspect" in o.flags]
    return ImportReport(
        batch_id=batch.id if batch else None, filename=batch.filename if batch else source, doc_type="ledger",
        rows_total=len(rows), imported=len(objs) - len(dup_report), duplicates=dup_report, anomalies=anomalies,
        injection_flags=inj, uncategorized=sum(1 for o in objs if o.category == "uncategorized"),
        errors=[], column_map={})


def refresh_anomalies(session: Session, business_id: int, only_ids: set[int] | None = None) -> list[dict[str, Any]]:
    """Re-run anomaly detection over all non-duplicate transactions; mark and report new flags."""
    txns = session.scalars(select(Transaction).where(Transaction.business_id == business_id,
                                                     Transaction.is_duplicate.is_(False))).all()
    flags = detect_anomalies([TxnKey(t.id, t.txn_date, float(t.amount), t.direction, t.description, t.reference,
                                     t.counterparty, t.category) for t in txns])
    out = []
    for t in txns:
        if t.id in flags and (only_ids is None or t.id in only_ids):
            t.is_anomaly = True
            t.anomaly_reason = flags[t.id][:300]
            if "anomaly" not in (t.flags or []):
                t.flags = [*(t.flags or []), "anomaly"]
            out.append({"id": t.id, "row": t.source_row, "date": t.txn_date.isoformat(), "amount": float(t.amount),
                        "category": t.category, "reason": flags[t.id]})
    return out


def _store_invoices(session: Session, business_id: int, parsed: ParseResult, batch: ImportBatch,
                    source: str) -> ImportReport:
    existing = {(i.kind, normalize(i.invoice_no)) for i in session.scalars(
        select(Invoice).where(Invoice.business_id == business_id)) if i.invoice_no}
    dups, imported, inj = [], 0, []
    for inv in parsed.invoices:
        key = (inv.kind, normalize(inv.invoice_no))
        if inv.invoice_no and key in existing:
            dups.append({"row": inv.source_row, "invoice_no": inv.invoice_no, "reason": "invoice number already exists"})
            continue
        existing.add(key)
        obj = Invoice(business_id=business_id, kind=inv.kind, invoice_no=inv.invoice_no, counterparty=inv.counterparty,
                      counterparty_phone=inv.phone, amount=inv.amount, amount_paid=inv.amount_paid,
                      issue_date=inv.issue_date, due_date=inv.due_date, paid_date=inv.paid_date, status=inv.status,
                      notes=inv.notes, source=f"{source}:{batch.filename}"[:40], source_row=inv.source_row)
        session.add(obj)
        session.flush()
        imported += 1
        if inv.flags:
            inj.append({"id": obj.id, "row": inv.source_row, "text": (inv.notes or inv.counterparty)[:120]})
    return ImportReport(batch.id, batch.filename, "invoices", parsed.rows_total, imported, dups, [], inj, 0,
                        [e.__dict__ for e in parsed.errors], parsed.column_map)


def store_parsed_entry(session: Session, business_id: int, entry: ParsedEntry, *, source: str = "nl") -> ImportReport:
    """Persist a quick natural-language entry (after the caller validated it)."""
    if entry.amount is None or entry.direction is None:
        raise ValueError(f"entry incomplete, missing: {entry.missing}")
    row = NormalizedTxn(
        txn_date=date.fromisoformat(entry.txn_date), amount=float(entry.amount), direction=entry.direction,
        category=entry.category, description=entry.description, counterparty=entry.counterparty,
        channel=entry.channel, quantity=entry.quantity, categorized_by="rule",
        category_confidence=entry.confidence,
        flags=["injection_suspect"] if scan(entry.description).suspicious else [])
    return store_transactions(session, business_id, [row], source=source)


def text_to_bytes(text: str) -> bytes:
    """Pasted CSV text -> bytes for parse_table. Normalises odd separators like ';'."""
    if text.count(";") > text.count(",") and "\t" not in text:
        text = re.sub(r";", ",", text)
    return text.encode("utf-8")
