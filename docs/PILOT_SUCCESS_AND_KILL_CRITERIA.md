# LedgerMatch Pilot Success and Kill Criteria

## Success Criteria

The pilot is considered **successful** when **all** of the following are
true, based on actual practitioner-supplied and validated data:

### Factual Measurements

1. **False automatic allocations: 0** — no case where an automatically
   accepted candidate would have been incorrect.
2. **Evidence validation: 100% pass** — every case's evidence bundle
   validated independently.
3. **Review-ledger validation: 100% pass** — every case's review ledger
   validated independently.
4. **Correct-candidate retention: ≥ 95%** —
   sum(correct_candidate_retained_cases) /
   sum(candidate_expected_cases) ≥ 0.95. If the denominator is zero, this
   metric is not applicable.
5. **Conservation: 100%** — no case violated monetary conservation.
6. **Invoice exclusivity: 100%** — no case reused an invoice across
   multiple deposits.
7. **Ambiguity preservation: 100%** — no ambiguous case was presented as
   unambiguous.

### Minimum Sample

8. **At least 5 practitioners** participated (from qualifying real rows).
9. **At least 30 historical cases** were processed (from qualifying real rows).
10. **At least 10 grouped or ambiguous cases** were included (from the
    explicit `genuine_ambiguous_cases` field, not `review_exceptions`).
11. **At least 3 CSV input layouts** were tested (from unique
    `input_layout_id` values, not currencies).
12. **Separate runs per currency** were completed for at least 2 currencies.

### Signals

13. **Repeat-use response: majority positive** — more than 50% of
    practitioners responded `yes` (excluding `undecided`).
14. **Support signal: at least one positive** — at least one practitioner
    responded `willing_to_pay` or `willing_to_contribute`.

## Kill Criteria (Immediate Termination)

The pilot must be **immediately terminated** if **any** of the following
occur:

1. **Any false automatic allocation** — a candidate that would have been
   automatically accepted but was incorrect. Zero tolerance.
2. **Evidence validation failure** that cannot be reproduced as a
   deterministic defect in the evidence bundler.
3. **Review-ledger tamper undetected** — a modification to the review
   ledger that passes validation.
4. **Conservation violation** — allocated amounts do not conserve the
   deposit total.
5. **Invoice reuse** — the same invoice is allocated to multiple deposits.
6. **Ambiguity hidden** — a case that should be ambiguous is presented as
   unambiguous.
7. **Data breach** — real customer data is committed to any repository or
   shared channel.
8. **AI authorization** — the AI component authorizes, accepts, rejects,
   posts, or writes back a financial allocation without human review.

## Continuation Gate

The continuation gate is a programmatic check implemented in
`scripts/verify_pilot_result.py`. It fails the pilot if:

- `false_automatic_allocations > 0` for any case.
- `evidence_validation` is `false` for any case.
- `review_ledger_validation` is `false` for any case.

The gate does **not** check for positive signals (repeat-use, support).
Those are reported as aggregate metrics but do not block continuation.

## What Success Does Not Mean

- Success does not mean the product is ready for public deployment.
- Success does not mean the product is compliant with any regulation.
- Success does not mean the product is secure for public hosting.
- Success does not mean customers will adopt the product.
- Success does not mean the AI component is reliable for autonomous
  operation.
- Success means the factual measurements were recorded and the kill
  criteria were not triggered, based on actual practitioner data.

## What Failure Does Not Mean

- Failure does not mean the product is fundamentally broken.
- Failure means a specific gate was triggered and must be investigated.
- The root cause must be identified and documented in `BLOCKERS.md`.
- At most three corrective loops are allowed before escalating.
