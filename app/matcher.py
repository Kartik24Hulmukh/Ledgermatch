"""Deterministic, ambiguity-preserving deposit-to-invoice reconciliation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

MAX_LOOKBACK_DAYS = 400
GRACE_DAYS = 7
SUBSET_MAX_ITEMS = 30
GLOBAL_SUBSET_MAX_OPEN = 20
MAX_STATES = 400_000
MAX_ALTERNATIVES = 5
CLOSED_STATUSES = {"paid", "void", "voided", "cancelled", "canceled", "credited"}
STOPWORDS = {"ltd", "llc", "inc", "the", "and", "pvt", "co", "corp", "company",
             "limited", "services", "service", "solutions", "group"}


@dataclass(frozen=True)
class BankTxn:
    id: str
    date: date
    description: str
    amount: Decimal
    currency: str = "USD"


@dataclass(frozen=True)
class Invoice:
    id: str
    invoice_no: str
    customer: str
    date: date
    amount: Decimal
    status: str = "open"
    currency: str = "USD"


@dataclass
class Match:
    txn: BankTxn
    invoices: list[Invoice]
    match_type: str
    confidence: float
    explanation: str
    evidence_class: str = "SUPPORTED"
    solver_status: str = "exact_unique"
    residual: Decimal = Decimal("0.00")
    alternatives: list[list[str]] = field(default_factory=list)


@dataclass
class UnmatchedTxn:
    txn: BankTxn
    reason: str
    suggestions: str = ""
    solver_status: str = "unresolved"
    alternatives: list[list[str]] = field(default_factory=list)


@dataclass
class ReconcileResult:
    matches: list[Match]
    unmatched: list[UnmatchedTxn]
    unpaid_invoices: list[Invoice]
    skipped_non_deposits: int = 0
    as_of: date | None = None
    currency: str = "USD"

    @property
    def deposits_processed(self) -> int:
        return len(self.matches) + len(self.unmatched)

    @property
    def match_rate(self) -> float:
        n = self.deposits_processed
        return (len(self.matches) / n) if n else 0.0

    @property
    def matched_amount(self) -> Decimal:
        return sum((m.txn.amount for m in self.matches), Decimal("0"))

    @property
    def matched_invoice_count(self) -> int:
        return sum(len(m.invoices) for m in self.matches)


_norm_ref_re = re.compile(r"[^a-z0-9]")
_norm_text_re = re.compile(r"[^a-z0-9 ]")


def norm_ref(s: str) -> str:
    return _norm_ref_re.sub("", (s or "").lower())


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", _norm_text_re.sub(" ", (s or "").lower())).strip()


def cents(a: Decimal) -> int:
    scaled = a * 100
    if scaled != scaled.to_integral_value():
        raise ValueError(f"amount has more than two decimal places: {a}")
    return int(scaled)


def invoice_ref_in_desc(inv: Invoice, desc_ref: str, desc_tokens: set[str]) -> bool:
    r = norm_ref(inv.invoice_no)
    if len(r) < 3:
        return False
    if len(r) >= 5 and r in desc_ref:
        return True
    return any(t == r or (len(r) >= 4 and t.endswith(r) and t[:-len(r)] and not t[:-len(r)].isdigit())
               for t in desc_tokens)


def customer_in_desc(customer: str, desc_ref: str, desc_tokens: set[str]) -> bool:
    c = norm_ref(customer)
    if len(c) >= 4 and c in desc_ref:
        return True
    words = [w for w in norm_text(customer).split() if len(w) >= 3 and w not in STOPWORDS]
    return bool(words) and all(w in desc_tokens for w in words)


def subset_candidates(invs: list[Invoice], target_c: int, tol_c: int = 0,
                      max_alternatives: int = MAX_ALTERNATIVES) -> tuple[list[list[Invoice]], str]:
    """Return bounded, deterministic candidate subsets and a solver status."""
    ordered = sorted(invs, key=lambda i: (i.date, i.invoice_no, i.id))
    if not ordered or len(ordered) > SUBSET_MAX_ITEMS:
        return [], "limit_exceeded"
    limit = target_c + tol_c
    states: dict[int, list[tuple[int, ...]]] = {0: [()]}
    for idx, inv in enumerate(ordered):
        amount = cents(inv.amount)
        if amount <= 0 or amount > limit:
            continue
        additions: dict[int, list[tuple[int, ...]]] = {}
        for total, combos in list(states.items()):
            new_total = total + amount
            if new_total > limit:
                continue
            bucket = additions.setdefault(new_total, [])
            existing = states.get(new_total, [])
            for combo in combos:
                candidate = combo + (idx,)
                if candidate not in existing and candidate not in bucket:
                    bucket.append(candidate)
                if len(existing) + len(bucket) >= max_alternatives:
                    break
        for total, combos in additions.items():
            states.setdefault(total, []).extend(combos[:max_alternatives - len(states.get(total, []))])
        if len(states) > MAX_STATES:
            return [], "limit_exceeded"
    ranked: list[tuple[int, tuple[int, ...]]] = []
    for total, combos in states.items():
        if abs(total - target_c) <= tol_c:
            for combo in combos:
                if len(combo) >= 2:
                    ranked.append((abs(total - target_c), combo))
    ranked.sort(key=lambda item: (item[0], len(item[1]), tuple(ordered[i].invoice_no for i in item[1])))
    unique: list[list[Invoice]] = []
    seen: set[tuple[str, ...]] = set()
    for _, combo in ranked:
        key = tuple(ordered[i].id for i in combo)
        if key in seen:
            continue
        seen.add(key)
        unique.append([ordered[i] for i in combo])
        if len(unique) >= max_alternatives:
            break
    if not unique:
        return [], "unresolved"
    return unique, "exact_unique" if len(unique) == 1 else "exact_ambiguous"


def subset_sum(invs: list[Invoice], target_c: int, tol_c: int = 0):
    candidates, _ = subset_candidates(invs, target_c, tol_c, 1)
    return candidates[0] if candidates else None


def _within_window(inv: Invoice, txn: BankTxn) -> bool:
    delta = (txn.date - inv.date).days
    return -GRACE_DAYS <= delta <= MAX_LOOKBACK_DAYS


def _alt(candidates: list[list[Invoice]]) -> list[list[str]]:
    return [[i.invoice_no for i in combo] for combo in candidates]


def _residual(txn: BankTxn, invoices: list[Invoice]) -> Decimal:
    return txn.amount - sum((i.amount for i in invoices), Decimal("0"))


def _ambiguous(txn: BankTxn, reason: str, candidates: list[list[Invoice]], text: str) -> UnmatchedTxn:
    return UnmatchedTxn(txn, reason, text, "exact_ambiguous", _alt(candidates))


def match_txn(txn: BankTxn, remaining: dict[str, Invoice], fee_tol: Decimal):
    if txn.currency not in {i.currency for i in remaining.values()} and remaining:
        return UnmatchedTxn(txn, "CURRENCY_MISMATCH", "No open invoice uses the deposit currency.", "invalid")
    desc_ref = norm_ref(txn.description)
    desc_tokens = set(norm_text(txn.description).split())
    tol_c = cents(fee_tol)
    target_c = cents(txn.amount)
    invs = [i for i in remaining.values() if i.currency == txn.currency]

    refs = [i for i in invs if _within_window(i, txn) and invoice_ref_in_desc(i, desc_ref, desc_tokens)]
    if refs:
        total = sum(cents(i.amount) for i in refs)
        if total == target_c:
            return Match(txn, refs, "reference", 1.0,
                         f"Referenced invoice(s) {', '.join(i.invoice_no for i in refs)} exactly equal the deposit.",
                         "DIRECT_REFERENCE")
        if len(refs) == 1 and target_c < cents(refs[0].amount):
            r = refs[0]
            return UnmatchedTxn(txn, "PARTIAL_PAYMENT",
                                f"Deposit references {r.invoice_no}, but does not equal its full amount.")
        candidates, status = subset_candidates(refs, target_c, tol_c)
        exact = [c for c in candidates if _residual(txn, c) == 0]
        if len(exact) == 1:
            return Match(txn, exact[0], "reference-subset", 1.0,
                         "A unique exact subset of referenced invoices equals the deposit.",
                         "DIRECT_REFERENCE", "exact_unique")
        if len(exact) > 1:
            return _ambiguous(txn, "AMBIGUOUS_COMBINATION", exact,
                              "Multiple referenced invoice combinations exactly equal the deposit; review required.")
        if candidates:
            return UnmatchedTxn(txn, "RESIDUAL_REVIEW",
                                "A referenced combination is within tolerance but has a non-zero residual.",
                                status, _alt(candidates))
        return UnmatchedTxn(txn, "AMOUNT_MISMATCH",
                            "Referenced invoice totals do not equal the deposit; review fees, credits, or remittance.")

    cust_invs = [i for i in invs if _within_window(i, txn)
                 and customer_in_desc(i.customer, desc_ref, desc_tokens)]
    if cust_invs:
        exact = [i for i in cust_invs if cents(i.amount) == target_c]
        if len(exact) == 1:
            pick = exact[0]
            return Match(txn, [pick], "customer+amount", 1.0,
                         f"Customer signal and unique exact invoice {pick.invoice_no} agree.", "CORROBORATED")
        if len(exact) > 1:
            candidates = [[i] for i in sorted(exact, key=lambda i: (i.date, i.invoice_no, i.id))]
            return _ambiguous(txn, "AMBIGUOUS_AMOUNT", candidates,
                              "Multiple invoices for this customer share the exact amount; no invoice was selected.")
        candidates, status = subset_candidates(cust_invs, target_c, tol_c)
        exact_sets = [c for c in candidates if _residual(txn, c) == 0]
        if len(exact_sets) == 1:
            combo = exact_sets[0]
            return Match(txn, combo, "lump-sum", 1.0,
                         "Customer signal and a unique exact invoice subset agree.",
                         "CORROBORATED", "exact_unique")
        if len(exact_sets) > 1:
            return _ambiguous(txn, "AMBIGUOUS_COMBINATION", exact_sets,
                              "Multiple invoice combinations exactly equal the deposit; no combination was selected.")
        if candidates:
            return UnmatchedTxn(txn, "RESIDUAL_REVIEW",
                                "A customer-constrained combination is within tolerance but has a non-zero residual.",
                                status, _alt(candidates))
        larger = [i for i in cust_invs if cents(i.amount) > target_c]
        if larger:
            return UnmatchedTxn(txn, "PARTIAL_PAYMENT",
                                "Customer matched, but the deposit is below an open invoice and no exact combination exists.")
        return UnmatchedTxn(txn, "CUSTOMER_NO_COMBINATION",
                            "Customer matched, but no unique exact invoice combination equals the deposit.", status)

    hits = [i for i in invs if _within_window(i, txn) and cents(i.amount) == target_c]
    if len(hits) == 1:
        h = hits[0]
        return Match(txn, [h], "amount-unique", 1.0,
                     f"Exactly one open invoice in the date window equals the deposit: {h.invoice_no}.",
                     "AMOUNT_ONLY")
    if len(hits) > 1:
        return _ambiguous(txn, "AMBIGUOUS_AMOUNT", [[i] for i in hits],
                          "Multiple open invoices equal the deposit; review required.")

    if 0 < len(invs) <= GLOBAL_SUBSET_MAX_OPEN:
        candidates, status = subset_candidates(invs, target_c, tol_c)
        if candidates:
            return UnmatchedTxn(txn, "SUGGESTED_COMBINATION",
                                "Amount-only combinations exist but lack customer/reference evidence; verify manually.",
                                status, _alt(candidates))
    return UnmatchedTxn(txn, "NO_CANDIDATE",
                        "No supported invoice reference, customer signal, or exact amount candidate was found.")


def reconcile(txns, invoices, fee_tol: Decimal = Decimal("0.00"), currency: str | None = None) -> ReconcileResult:
    if fee_tol < 0:
        raise ValueError("fee tolerance must be non-negative")
    ids = [i.id for i in invoices]
    refs = [norm_ref(i.invoice_no) for i in invoices if norm_ref(i.invoice_no)]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate invoice row IDs")
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate invoice numbers")
    currencies = {i.currency for i in invoices} | {t.currency for t in txns}
    if currency:
        currencies.add(currency)
    if len(currencies) > 1:
        raise ValueError(f"mixed currencies are not supported in one run: {sorted(currencies)}")
    run_currency = next(iter(currencies), currency or "USD")
    remaining = {inv.id: inv for inv in invoices
                 if (inv.status or "open").strip().lower() not in CLOSED_STATUSES}
    matches, unmatched = [], []
    deposits = [t for t in txns if t.amount > 0]
    for txn in sorted(deposits, key=lambda t: (t.date, t.id)):
        result = match_txn(txn, remaining, fee_tol)
        if isinstance(result, Match):
            if result.residual != 0:
                raise AssertionError("accepted match has a non-zero residual")
            matches.append(result)
            for inv in result.invoices:
                if inv.id not in remaining:
                    raise AssertionError("invoice reused")
                remaining.pop(inv.id)
        else:
            unmatched.append(result)
    as_of = max((t.date for t in txns), default=None)
    unpaid = sorted(remaining.values(), key=lambda i: (i.date, i.invoice_no, i.id))
    return ReconcileResult(matches, unmatched, unpaid, len(txns) - len(deposits), as_of, run_currency)
