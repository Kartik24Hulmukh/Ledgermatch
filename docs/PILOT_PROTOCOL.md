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

## Counting Rules

Only rows with **all** of the following qualify as real practitioner evidence:

- `data_origin` = `authorized_pseudonymized_historical`
- `direct_reconciliation_experience` = `true`
- `consent_received` = `true`
- `real_participant_attestation` = `true`
- `operator_attestation` = `true`
- `evidence_validation` = `true`
- `review_ledger_validation` = `true`

- **Real practitioners** are counted from unique `practitioner_id` values
  in qualifying real rows.
- **Real historical cases** are counted from qualifying real rows.
- **Genuine ambiguous cases** are counted from the explicit
  `genuine_ambiguous_cases` field, not from `review_exceptions`.
- **Input layouts** are counted from unique `input_layout_id` values.
- **Currencies** are counted independently from unique `currency` values.

Never count synthetic rows toward real sample requirements.
Never count review_exceptions as ambiguous cases.
Never count currencies as layouts.

## Data Requirements

- **Synthetic data** — generated via `demo_data/generate_demo.py` or
  equivalent synthetic generators.
- **Authorized pseudonymized historical data** — if real historical cases
  are used, all customer names, account numbers, email addresses, and
  personally identifiable information must be removed or replaced with
  pseudonymous identifiers before import. The operator must have documented
  authority to use the data. Old data is not automatically authorized or
  de-identified. Exact amounts and dates may remain sensitive
  quasi-identifiers.
- **No customer files in GitHub** — pilot data must never be committed to
  any repository. Store pilot data locally on the practitioner's machine.

## Experiment Design

The pilot must use:

- **Two comparable case sets** per practitioner.
- **Randomized or counterbalanced ordering** — the order of manual-first
  vs. LedgerMatch-first review is randomized or counterbalanced to avoid
  learning-order bias.
- **No reuse of the same solved case** for both timed workflows.
- **Baseline timing recorded before exposure** to the corresponding
  LedgerMatch solution for that case set.
- **Retrospective estimates** explicitly labelled as
  `baseline_method = retrospective_estimate` and excluded from causal
  time-improvement claims.
- **Per-practitioner reporting** as well as per-case reporting, so one
  participant cannot dominate aggregates.

## Currency Runs

Each currency must be run separately. Results must be recorded per-currency
in the pilot results template.

## Evidence and Review-Ledger Validation

Every pilot run must produce:

1. **Reconciliation Evidence Bundle** — validated by
   `scripts/verify_release.py` evidence validation.
2. **Review Ledger** — validated by the review-ledger CLI
   (`python3 -m app.review verify`).

Both must pass independently. A failure in either blocks continuation.

## Before-and-After Review Time

For each case, the practitioner must record:

- `review_minutes_baseline` — time spent on manual reconciliation.
- `baseline_method` — one of `measured_counterbalanced`,
  `measured_matched_case_set`, or `retrospective_estimate`.
- `review_minutes_with_ledgermatch` — time spent using LedgerMatch's
  candidate presentation and review-ledger workflow.

Median times are computed for measured rows only. Retrospective estimates
are reported separately and excluded from causal time-improvement claims.

## False Automatic Allocation Count

The pilot must track `false_automatic_allocations` — the number of cases
where LedgerMatch presented a candidate that, if automatically accepted,
would have been incorrect.

**The continuation gate fails if any false automatic allocation is found.**
This is a hard kill gate. Zero tolerance.

## Correct-Candidate Retention

The pilot must track:

- `candidate_expected_cases` — the number of cases where a correct
  candidate was expected to exist.
- `correct_candidate_retained_cases` — the number of cases where the
  correct candidate was present in the candidate set.

Candidate retention rate = sum(correct_candidate_retained_cases) /
sum(candidate_expected_cases). If the denominator is zero, the rate is
reported as null/not applicable.

## Repeat-Use Response

After completing their assigned cases, each practitioner is asked whether
they would request to use LedgerMatch again. The response is recorded as
`repeat_use_response` with values: `yes`, `no`, or `undecided`.

## Support Signal

Each practitioner is asked whether they would pay for or contribute to
LedgerMatch. The response is recorded as `support_signal` with values:
`willing_to_pay`, `willing_to_contribute`, `neither`, or `undecided`.

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
