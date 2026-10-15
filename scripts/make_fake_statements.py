"""Generate clearly FAKE statements for a Bangladeshi SME, clean and messy, plus the expected figures.

Every file is fictional (names marked "FAKE", account numbers 0000-...). Expected totals are computed
with pandas from the same rows that were written, and saved to expected.json next to the files.

    python scripts/make_fake_statements.py [out_dir]     (default: data/fake_statements, git-ignored)
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
START = date(2026, 4, 1)

INFLOWS = [("Deposit from FAKE Karim Knit Composite", 45000, 120000), ("bKash settlement - retail sales", 8000, 30000),
           ("Cash deposit - counter sales", 10000, 40000), ("Transfer from FAKE Shapla Apparels", 30000, 90000)]
OUTFLOWS = [("Cheque to FAKE Dhaka Zipper House - stock", 40000, 130000), ("FAKE shop rent - Mirpur", 36500, 36500),
            ("FAKE staff salary", 51000, 51000), ("DESCO electricity bill", 4000, 9000), ("Courier charges", 500, 3000),
            ("Loan EMI - FAKE Bank", 17250, 17250), ("Nagad payment to FAKE packaging supplier", 3000, 15000)]
BN_DESC = ["দোকান ভাড়া", "কর্মচারীর বেতন", "বিদ্যুৎ বিল", "বোতাম বিক্রি", "চেইন বিক্রি", "কুরিয়ার খরচ"]


def _rows(n: int, seed: int) -> pd.DataFrame:
    rnd = random.Random(seed)
    out: list[dict] = []
    seen: dict[tuple[str, float], set[int]] = {}
    while len(out) < n:
        d = START + timedelta(days=rnd.randrange(0, 180 if n < 1000 else 1800))
        if rnd.random() < 0.55:
            desc, lo, hi = rnd.choice(INFLOWS)
            row = {"date": d, "desc": desc, "out": 0.0, "in": float(rnd.randrange(lo, hi + 1, 50))}
        else:
            desc, lo, hi = rnd.choice(OUTFLOWS)
            row = {"date": d, "desc": desc, "out": float(rnd.randrange(lo, hi + 1, 50)), "in": 0.0}
        key = (row["desc"], row["in"] or row["out"])
        # A real statement does not repeat the same payment within days; such rows are rightly flagged as duplicates.
        days = seen.setdefault(key, set())
        if any(d.toordinal() + k in days for k in range(-3, 4)):
            continue
        days.add(d.toordinal())
        out.append(row)
    return pd.DataFrame(out).sort_values("date", kind="stable").reset_index(drop=True)


def _expect(df: pd.DataFrame, **extra) -> dict:
    df = df.copy()
    df["month"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
    by_month = df.groupby("month")[["in", "out"]].sum()
    return {"rows": int(len(df)), "total_in": round(float(df["in"].sum()), 2), "total_out": round(float(df["out"].sum()), 2),
            "net": round(float(df["in"].sum() - df["out"].sum()), 2),
            "by_month": {m: {"in": round(float(r["in"]), 2), "out": round(float(r["out"]), 2)} for m, r in by_month.iterrows()},
            **extra}


def _bank_csv(df: pd.DataFrame, date_fmt=lambda d: d.strftime("%d/%m/%Y")) -> str:
    lines = ["FAKE Bank Ltd - Current Account Statement (TEST DATA, NOT REAL)", "Account Name: FAKE TRIMS & ACCESSORIES",
             "Account No: 0000-0000-0000", "", "Txn Date,Narration,Withdrawal,Deposit"]
    for r in df.itertuples():
        lines.append(f"{date_fmt(r.date)},\"{r.desc}\",{r.out or ''},{r._4 or ''}")
    return "\n".join(lines) + "\n"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "fake_statements"
    out.mkdir(parents=True, exist_ok=True)
    expected: dict[str, dict] = {}

    clean = _rows(300, 1)
    (out / "01_clean_bank.csv").write_text(_bank_csv(clean), encoding="utf-8")
    expected["01_clean_bank.csv"] = _expect(clean, outcome="imported")

    xl = _rows(120, 2)
    xl.rename(columns={"date": "Date", "desc": "Description", "out": "Debit", "in": "Credit"}).to_excel(
        out / "02_clean_bank.xlsx", index=False)
    expected["02_clean_bank.xlsx"] = _expect(xl, outcome="imported")

    # Bangla headers, Bangla descriptions, Bangla digits and the taka sign in amounts.
    bn = _rows(80, 3)
    bn["desc"] = [random.Random(i).choice(BN_DESC) for i in range(len(bn))]
    lines = ["তারিখ,বিবরণ,খরচ,জমা"]
    for r in bn.itertuples():
        amt = lambda v: f"\"৳{int(v):,}\"".translate(BN_DIGITS) if v else ""  # noqa: E731
        lines.append(f"{r.date.strftime('%d/%m/%Y').translate(BN_DIGITS)},{r.desc},{amt(r.out)},{amt(r._4)}")
    (out / "03_bangla_headers_digits.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    expected["03_bangla_headers_digits.csv"] = _expect(bn, outcome="imported")

    # Mixed date formats in one file.
    mixed = _rows(60, 4)
    fmts = [lambda d: d.strftime("%d/%m/%Y"), lambda d: d.isoformat(), lambda d: d.strftime("%d %b %Y"),
            lambda d: d.strftime("%d-%m-%Y")]
    lines = ["Date,Description,Withdrawal,Deposit"]
    for i, r in enumerate(mixed.itertuples()):
        lines.append(f"{fmts[i % 4](r.date)},\"{r.desc}\",{r.out or ''},{r._4 or ''}")
    (out / "04_mixed_dates.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    expected["04_mixed_dates.csv"] = _expect(mixed, outcome="imported")

    # Rows exported twice (same bank reference): the importer should flag them, not double-count.
    # Identical rows *without* a shared reference are separate real transactions and are kept.
    dup = _rows(50, 5)
    dup_file = pd.concat([dup, dup.iloc[:10]]).sort_values("date", kind="stable")
    lines = ["Date,Ref No,Description,Withdrawal,Deposit"] + [
        f"{r.date.strftime('%d/%m/%Y')},FAKEREF{r.Index:05d},\"{r.desc}\",{r.out or ''},{r._4 or ''}"
        for r in dup_file.itertuples()]
    (out / "05_duplicates.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    expected["05_duplicates.csv"] = _expect(dup, outcome="imported", duplicate_rows_in_file=10,
                                            note="totals exclude the 10 repeated rows")

    # Broken inputs: must give a clear message, never a crash or silent garbage.
    (out / "06_missing_amount_column.csv").write_text(
        "Date,Description,Party\n01/05/2026,Shop rent,FAKE landlord\n02/05/2026,Salary,Staff\n", encoding="utf-8")
    expected["06_missing_amount_column.csv"] = {"outcome": "clear error: no amount column"}
    (out / "07_empty.csv").write_bytes(b"")
    expected["07_empty.csv"] = {"outcome": "clear error: empty file"}
    (out / "08_header_only.csv").write_text("Date,Description,Amount,Type\n", encoding="utf-8")
    expected["08_header_only.csv"] = {"outcome": "clear message: no rows"}
    (out / "09_binary_garbage.csv").write_bytes(bytes(random.Random(9).randrange(256) for _ in range(4096)))
    expected["09_binary_garbage.csv"] = {"outcome": "clear error: unreadable"}

    # Large but allowed (< 5 MB) and too large (> 5 MB).
    big = _rows(60000, 10)
    text = _bank_csv(big)
    while len(text.encode()) > 4_900_000:
        big = big.iloc[: int(len(big) * 0.95)]
        text = _bank_csv(big)
    (out / "10_large_4_9mb.csv").write_text(text, encoding="utf-8")
    expected["10_large_4_9mb.csv"] = _expect(big, outcome="imported", size_bytes=len(text.encode()))
    huge = _bank_csv(_rows(75000, 11))
    (out / "11_too_large_6mb.csv").write_text(huge + huge[: max(0, 6_200_000 - len(huge.encode()))], encoding="utf-8")
    expected["11_too_large_6mb.csv"] = {"outcome": "HTTP 413 file too large"}

    # Formats the app does not accept: must be rejected clearly.
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(out / "12_statement.pdf"), pagesize=A4)
    c.drawString(72, 800, "FAKE Bank Ltd - TEST statement (not real)")
    for i, r in enumerate(clean.head(30).itertuples()):
        c.drawString(72, 770 - i * 18, f"{r.date:%d/%m/%Y}  {r.desc[:40]}  {r.out or ''}  {r._4 or ''}")
    c.save()
    expected["12_statement.pdf"] = {"outcome": "HTTP 415 unsupported type"}

    (out / "expected.json").write_text(json.dumps(expected, indent=1, ensure_ascii=False), encoding="utf-8")
    for p in sorted(out.iterdir()):
        print(f"{p.name:32s} {p.stat().st_size:>10,d} bytes")


if __name__ == "__main__":
    main()
