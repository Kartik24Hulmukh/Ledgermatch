#!/usr/bin/env python3
"""Generates realistic, seeded demo data for LedgerMatch (18 months of activity):
referenced payments, customer-only payments, lump-sum multi-invoice payments,
part-payments, unpaid invoices, and non-invoice noise. Deterministic (seed 42)."""
import csv
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

random.seed(42)
HERE = Path(__file__).parent

CUSTOMERS = ["Acme Interiors", "Bluepeak Consulting", "Corewave Media",
             "Delta Fabrication", "Eastgate Clinic", "Fernhill Landscaping",
             "Gridline Electrical", "Harbor & Sons Plumbing", "Ironwood Joinery",
             "Juniper Design Co", "Kestrel Logistics", "Lumen Marketing",
             "Maplewood Property", "Northbay Catering", "Orchid Wellness"]


def money(lo, hi):
    return Decimal(random.randint(lo, hi)) + Decimal(random.choice([0, 0, 25, 50, 75, 99])) / 100


start = date(2025, 1, 6)
invoices = []
seq = 0
for m in range(18):
    for _ in range(random.randint(15, 21)):
        seq += 1
        d = start + timedelta(days=m * 30 + random.randint(0, 27))
        invoices.append({"no": f"INV-{d.year}-{seq:04d}", "customer": random.choice(CUSTOMERS),
                         "date": d, "amount": money(150, 8500)})

txns = []


def add_txn(d, desc, amount):
    txns.append({"date": d, "desc": desc, "amount": amount})


pool = invoices[:]
random.shuffle(pool)
n = len(pool)

# 1) referenced payments (~55%)
for inv in pool[: int(n * 0.55)]:
    tpl = random.choice(["NEFT {C} {R}", "ACH CREDIT {C} REF {R}", "BANK TRANSFER {R} {C}",
                         "REMITTANCE {R}", "PAYMENT RECEIVED {C} {R}"])
    add_txn(inv["date"] + timedelta(days=random.randint(4, 40)),
            tpl.format(C=inv["customer"].upper(), R=inv["no"].replace("-", "")),
            inv["amount"])

# 2) customer-name-only exact-amount payments (~14%)
for inv in pool[int(n * 0.55): int(n * 0.69)]:
    tpl = random.choice(["NEFT {C}", "UPI {C}", "TRANSFER FROM {C}", "{C} PAYMENT"])
    add_txn(inv["date"] + timedelta(days=random.randint(4, 50)),
            tpl.format(C=inv["customer"].upper()), inv["amount"])

# 3) lump-sum multi-invoice payments (~14%), grouped per customer within ~100 days
seg = pool[int(n * 0.69): int(n * 0.83)]
by_cust = {}
for inv in seg:
    by_cust.setdefault(inv["customer"], []).append(inv)
leftover = []
for cust, invs_c in by_cust.items():
    invs_c.sort(key=lambda x: x["date"])

    def flush(group):
        if len(group) >= 2:
            total = sum(g["amount"] for g in group)
            pay_date = max(g["date"] for g in group) + timedelta(days=random.randint(5, 25))
            tpl = random.choice(["RTGS {C} BULK PAYMENT", "EFT {C} INVOICE BATCH", "WIRE TRANSFER {C}"])
            add_txn(pay_date, tpl.format(C=cust.upper()), total)
        elif group:
            leftover.extend(group)

    group = []
    for invd in invs_c:
        if not group or ((invd["date"] - group[0]["date"]).days <= 100 and len(group) < 4):
            group.append(invd)
        else:
            flush(group)
            group = [invd]
    flush(group)
for inv in leftover:
    add_txn(inv["date"] + timedelta(days=random.randint(4, 45)),
            f"EFT {inv['customer'].upper()}", inv["amount"])

# 4) part-payments (~5%) - flagged, invoice stays open
for inv in pool[int(n * 0.83): int(n * 0.88)]:
    frac = Decimal(random.randint(35, 70)) / 100
    part = (inv["amount"] * frac).quantize(Decimal("0.01"))
    add_txn(inv["date"] + timedelta(days=random.randint(4, 30)),
            f"PART PAYMENT {inv['customer'].upper()} {inv['no'].replace('-', '')}", part)

# 5) remaining ~12% never paid (stay in unpaid_invoices)

# 6) noise: withdrawals + non-invoice deposits
for _ in range(140):
    d = start + timedelta(days=random.randint(0, 18 * 30))
    add_txn(d, random.choice(["CARD PURCHASE OFFICEMART", "PAYROLL RUN", "RENT STANDING ORDER",
                              "UTILITY DIRECT DEBIT", "SOFTWARE SUBSCRIPTION", "FUEL STATION"]),
            -money(40, 4200))
for _ in range(14):
    d = start + timedelta(days=random.randint(0, 18 * 30))
    add_txn(d, random.choice(["BANK INTEREST", "CASH DEPOSIT", "TAX REFUND", "VENDOR REBATE"]),
            money(5, 400))

txns.sort(key=lambda t: t["date"])
with open(HERE / "bank_statement.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Date", "Description", "Amount"])
    for t in txns:
        w.writerow([t["date"].isoformat(), t["desc"], f"{t['amount']:.2f}"])

invoices.sort(key=lambda x: x["date"])
with open(HERE / "invoices.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Invoice No", "Customer", "Date", "Amount", "Status"])
    for inv in invoices:
        w.writerow([inv["no"], inv["customer"], inv["date"].isoformat(), f"{inv['amount']:.2f}", "Open"])

print(f"Wrote {len(invoices)} invoices and {len(txns)} bank transactions")
