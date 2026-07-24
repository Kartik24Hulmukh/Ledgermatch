# LedgerMatch Private Pilot Protocol

## Purpose

This protocol governs a private, local-only evaluation of LedgerMatch v0.4.0
by qualified reconciliation practitioners using synthetic or properly
de-identified data. It does not constitute a public deployment, customer
trial, or compliance audit.

## Prerequisites

- LedgerMatch v0.4.0 source (SHA-256 verified)
- Python 3.10+ with standard library only
- Local or private-network execution environment
- No customer financial data in any repository, cloud storage, or issue tracker

## Minimum Sample Requirements

The pilot must include **at least**:

| Requirement | Minimum |
|---|---|
| Practitioners | 5 |
| Historical cases | 30 |
| Grouped or ambiguous cases | 10 |
| CSV input layouts | 3 |
| Currencies tested | Separate runs per currency |

If any minimum is unmet, the continuation gate reports the shortfall but
does not fabricate a pass.

## Data Requirements

- **Synthetic data only** — generated via `demo_data/generate_demo.py` or
  equivalent synthetic generators.
- **De-identified data** — if real historical cases are used, all customer
  names, account numbers, email addresses, and personally identifiable
  information must be removed or replaced with pseudonymous identifiers
  before import.
- **No customer files in GitHub** — pilot data must never be committed to
  any repository. Store pilot data locally on the practitioner's machine.

## Input Layouts

At least three distinct CSV layouts must be tested to validate the import
profile system:

1. **Layout A** — standard bank statement with columns: date, description,
   amount, balance.
2. **Layout B** — invoice register with columns: invoice_number, customer,
   amount, currency, issue_date, due_date.
3. **Layout C** — payment ledger with columns: payment_id, paid_amount,
   payment_date, reference, currency.

Each layout must have a corresponding import profile (`examples/profile.json`
format) that specifies date format, currency, decimal precision, and column
mappings.

## Currency Runs

Each currency must be run separately. The pilot must cover at least:

- USD runs
- EUR runs
- A third currency (e.g., GBP, INR, JPY)

Results must be recorded per-currency in the pilot results template.

## Evidence and Review-Ledger Validation

Every pilot run must produce:

1. **Reconciliation Evidence Bundle** — validated by
   `scripts/verify_release.py` evidence validation.
2. **Review Ledger** — validated by the review-ledger CLI
   (`python3 -m app.cli review-verify`).

Both must pass independently. A failure in either blocks continuation.

## Before-and-After Review Time

For each case, the practitioner must record:

- `review_minutes_before` — time spent on manual reconciliation without
  LedgerMatch.
- `review_minutes_with_ledgermatch` — time spent using LedgerMatch's
  candidate presentation and review-ledger workflow.

These are factual measurements, not marketing claims.

## False Automatic Allocation Count

The pilot must track `false_automatic_allocations` — the number of cases
where LedgerMatch presented a candidate that, if automatically accepted,
would have been incorrect.

**The continuation gate fails if any false automatic allocation is found.**
This is a hard kill gate. Zero tolerance.

## Correct-Candidate Retention

The pilot must track `correct_candidate_retained` — whether the correct
candidate was present in the candidate set presented by LedgerMatch for
each case.

A case where the correct candidate is not retained is a failure that must
be investigated, but does not automatically kill the pilot unless it
results in a false automatic allocation.

## Repeat-Use Request

After completing their assigned cases, each practitioner must be asked
whether they would request to use LedgerMatch again for future
reconciliation work. The response is recorded as a boolean
(`repeat_use_requested`).

## Payment or Contribution Signal

Each practitioner must be asked whether they would pay for or contribute
to LedgerMatch. The response is recorded as a free-text signal
(`payment_or_contribution_signal`) containing no personal information.

## Continuation Gate

The pilot continuation gate fails if **any** of the following are true:

- Any false automatic allocation is found (> 0).
- Evidence validation fails for any case.
- Review-ledger validation fails for any case.
- Ambiguity is hidden (a case that should be ambiguous is presented as
  unambiguous).
- Invoice reuse occurs (the same invoice is allocated to multiple
  deposits).
- Conservation fails (allocated amounts do not conserve the deposit total).

The gate does **not** pass until actual practitioner data is supplied and
validated. Synthetic-only runs do not constitute a passed pilot.

## What This Protocol Does Not Claim

- This protocol does not claim customer demand.
- This protocol does not claim accounting assurance.
- This protocol does not claim regulatory compliance.
- This protocol does not claim public-hosting security.
- This protocol does not claim practitioner outcomes beyond the factual
  measurements recorded.
- AI output is advisory only. AI must never authorize or post financial
  allocations.
