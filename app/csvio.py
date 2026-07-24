"""Strict-profile CSV parsing with deterministic source-row identity."""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .matcher import BankTxn, Invoice

MAX_ROWS = 200_000


class CsvFormatError(ValueError):
    pass


@dataclass(frozen=True)
class ImportProfile:
    currency: str = "USD"
    date_format: str = "YMD"
    precision: int = 2

    def to_dict(self):
        return asdict(self)


DATE_FORMATS = {"YMD": ["%Y-%m-%d", "%Y/%m/%d"],
                "DMY": ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"],
                "MDY": ["%m/%d/%Y", "%b %d %Y", "%B %d %Y"]}
BANK_SPEC = [
    ("date", ["date", "transaction date", "txn date", "value date", "posting date", "posted"]),
    ("description", ["description", "narration", "details", "memo", "transaction details", "particulars", "payee", "reference", "name"]),
    ("amount", ["amount", "value"]), ("credit", ["credit", "deposit", "paid in", "money in", "credit amount", "cr"]),
    ("debit", ["debit", "withdrawal", "paid out", "money out", "debit amount", "dr"]),
]
INVOICE_SPEC = [
    ("invoice_no", ["invoice no", "invoice number", "invoice #", "invoice", "inv no", "inv", "invoice id", "doc number", "number", "reference"]),
    ("customer", ["customer", "customer name", "client", "client name", "company", "account", "contact", "name"]),
    ("date", ["date", "invoice date", "issue date", "created"]),
    ("amount", ["amount", "total", "amount due", "invoice amount", "total amount", "gross", "value"]),
    ("status", ["status", "state", "paid"]),
]


def parse_date_str(value, date_format="YMD"):
    raw = (value or "").strip().replace(",", "")
    formats = DATE_FORMATS.get(date_format.upper())
    if not formats:
        raise CsvFormatError("date format must be YMD, DMY, or MDY")
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise CsvFormatError(f"Unrecognized or profile-incompatible date {raw!r}; expected {date_format.upper()}.")


_amount_re = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


def parse_amount_str(value, precision=2):
    if value is None or not str(value).strip():
        raise CsvFormatError("Missing amount")
    raw = str(value).strip()
    neg_parentheses = raw.startswith("(") and raw.endswith(")")
    if neg_parentheses:
        raw = "-" + raw[1:-1].strip()
    cleaned = re.sub(r"[$£€₹,\s]", "", raw)
    if not _amount_re.fullmatch(cleaned):
        raise CsvFormatError(f"Unrecognized amount {value!r}; use an unambiguous dot-decimal value")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise CsvFormatError(f"Unrecognized amount {value!r}") from exc
    if not amount.is_finite():
        raise CsvFormatError("Amount must be finite")
    exponent = max(0, -amount.as_tuple().exponent)
    if exponent > precision:
        raise CsvFormatError(f"Amount {value!r} exceeds configured precision {precision}")
    return amount


def _norm_h(header):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9# ]", " ", (header or "").lower())).strip()


def _read(text, spec, required):
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise CsvFormatError("CSV appears to be empty")
    normed = {}
    for field in reader.fieldnames:
        normed.setdefault(_norm_h(field), field)
    mapping = {}
    for canonical, aliases in spec:
        for alias in aliases:
            if alias in normed and normed[alias] not in mapping.values():
                mapping[canonical] = normed[alias]
                break
    missing = [name for name in required if name not in mapping]
    if missing:
        raise CsvFormatError(f"Could not find column(s) {missing} in headers {reader.fieldnames}.")
    rows = []
    for line_number, row in enumerate(reader, 2):
        if row and any((v or "").strip() for v in row.values() if isinstance(v, str)):
            rows.append((line_number, row))
        if len(rows) > MAX_ROWS:
            raise CsvFormatError(f"CSV exceeds {MAX_ROWS} rows")
    return rows, mapping


def _source_id(prefix, text, line_number):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}-{line_number}"


def parse_bank_csv(text, profile: ImportProfile | None = None):
    profile = profile or ImportProfile()
    rows, mapping = _read(text, BANK_SPEC, ["date", "description"])
    if "amount" not in mapping and "credit" not in mapping:
        raise CsvFormatError("Bank statement needs Amount or Credit/Debit columns")
    txns, errors = [], []
    for line_number, row in rows:
        try:
            date_value = parse_date_str(row.get(mapping["date"]), profile.date_format)
            description = (row.get(mapping["description"]) or "").strip()
            if "amount" in mapping:
                amount = parse_amount_str(row.get(mapping["amount"]), profile.precision)
            else:
                credit = row.get(mapping["credit"]) if "credit" in mapping else None
                debit = row.get(mapping["debit"]) if "debit" in mapping else None
                credit_value = parse_amount_str(credit, profile.precision) if credit and str(credit).strip() else Decimal("0")
                debit_value = parse_amount_str(debit, profile.precision) if debit and str(debit).strip() else Decimal("0")
                amount = credit_value - debit_value
            txns.append(BankTxn(_source_id("B", text, line_number), date_value, description, amount, profile.currency))
        except CsvFormatError as exc:
            errors.append(f"line {line_number}: {exc}")
            if len(errors) >= 5:
                break
    if errors:
        raise CsvFormatError("Bank statement problems: " + "; ".join(errors))
    if not txns:
        raise CsvFormatError("No transactions found")
    return txns


def parse_invoice_csv(text, profile: ImportProfile | None = None):
    profile = profile or ImportProfile()
    rows, mapping = _read(text, INVOICE_SPEC, ["invoice_no", "customer", "date", "amount"])
    invoices, errors = [], []
    for line_number, row in rows:
        invoice_no = (row.get(mapping["invoice_no"]) or "").strip()
        if not invoice_no:
            continue
        try:
            invoices.append(Invoice(
                _source_id("I", text, line_number), invoice_no,
                (row.get(mapping["customer"]) or "").strip(),
                parse_date_str(row.get(mapping["date"]), profile.date_format),
                parse_amount_str(row.get(mapping["amount"]), profile.precision),
                (row.get(mapping["status"]) or "open").strip() if "status" in mapping else "open",
                profile.currency,
            ))
        except CsvFormatError as exc:
            errors.append(f"line {line_number}: {exc}")
            if len(errors) >= 5:
                break
    if errors:
        raise CsvFormatError("Invoice register problems: " + "; ".join(errors))
    if not invoices:
        raise CsvFormatError("No invoices found")
    return invoices
