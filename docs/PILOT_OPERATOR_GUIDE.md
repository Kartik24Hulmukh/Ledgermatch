# LedgerMatch Pilot Operator Guide

## Role

The pilot operator is responsible for setting up, running, and recording
the private LedgerMatch pilot. The operator is not a test subject — they
facilitate the evaluation by practitioners.

## Setup

### 1. Verify Source

```bash
sha256sum LedgerMatch-0.4.0-review-ledger-source.zip
# Expected: cc34bc9eb8f9a98fc6f40bab5732105a7f11a9be266a86f15dd4f17125dd8927

unzip -t LedgerMatch-0.4.0-review-ledger-source.zip  # integrity check
unzip -l LedgerMatch-0.4.0-review-ledger-source.zip  # 51 entries
```

### 2. Run Baseline Verification

```bash
cd Ledgermatch
python3 scripts/verify_release.py
```

All gates must pass before proceeding.

### 3. Generate Synthetic Data

```bash
python3 demo_data/generate_demo.py
```

### 4. Prepare Import Profiles

Create at least three import profiles for the three CSV layouts. See
`examples/profile.json` for the format.

### 5. Distribute to Practitioners

Each practitioner receives:
- The verified LedgerMatch source (not a fork — a local copy).
- Synthetic data files or authorized pseudonymized historical data.
- Import profiles for their assigned layout.
- The pilot results template (`examples/pilot-results-template.csv`).
- The pilot case template (`examples/pilot-case-template.json`).
- This operator guide.

## Running a Case

### Step 1: Import Data

```bash
cd Ledgermatch
python3 -m app.cli \
  --bank <deposits.csv> \
  --invoices <invoices.csv> \
  --out out_pilot/<case_id>/ \
  --profile <profile.json> \
  --currency <USD|EUR|...>
```

### Step 2: Review Candidates

The CLI output presents candidate matches. The practitioner must:

1. Review each candidate.
2. Use `approve_exact`, `reject`, or `defer` for each.
3. Record the review decision in the review ledger.

```bash
python3 -m app.review create \
  --evidence out_pilot/<case_id>/evidence.json \
  --decisions out_pilot/<case_id>/review_decisions.json \
  --out out_pilot/<case_id>/review_ledger.jsonl
```

### Step 3: Validate Evidence and Review Ledger

```bash
python3 -m app.review verify \
  --evidence out_pilot/<case_id>/evidence.json \
  --review out_pilot/<case_id>/review_ledger.jsonl \
  --receipt out_pilot/<case_id>/review_ledger.jsonl.receipt.json
```

Both evidence and review-ledger validation must pass.

### Step 4: Record Results

Enter the case results into the pilot results template CSV using the v2.0
schema. See `examples/pilot-results-template.csv` for all required columns.

Key fields:
- `pilot_case_id` — unique identifier for this case.
- `session_id` — unique identifier for this session.
- `practitioner_id` — pseudonymous identifier.
- `role_category` — e.g., accountant, bookkeeper, AR clerk.
- `data_origin` — `synthetic` or `authorized_pseudonymized_historical`.
- `direct_reconciliation_experience` — `true`/`false`.
- `consent_received` — `true`/`false`.
- `real_participant_attestation` — `true`/`false`.
- `operator_attestation` — `true`/`false`.
- `input_layout_id` — identifier for the CSV layout used.
- `currency` — currency code.
- `deposits_processed` — number of deposits.
- `accepted_matches` — number of matches approved.
- `review_exceptions` — number of exceptions reviewed.
- `genuine_ambiguous_cases` — count of genuinely ambiguous cases (strict definition).
- `false_automatic_allocations` — must be 0.
- `candidate_expected_cases` — cases where a correct candidate was expected.
- `correct_candidate_retained_cases` — cases where correct candidate was present.
- `review_minutes_baseline` — manual reconciliation time.
- `baseline_method` — `measured_counterbalanced`, `measured_matched_case_set`, or `retrospective_estimate`.
- `review_minutes_with_ledgermatch` — LedgerMatch-assisted time.
- `evidence_validation` — `true`/`false`.
- `review_ledger_validation` — `true`/`false`.
- `repeat_use_response` — `yes`, `no`, or `undecided`.
- `recommendation` — `recommend`, `neutral`, or `do_not_recommend`.
- `support_signal` — `willing_to_pay`, `willing_to_contribute`, `neither`, or `undecided`.
- `notes` — free text, no personal or customer info.

## Experiment Design

The pilot must use two comparable case sets per practitioner with
randomized or counterbalanced ordering. Do not reuse the same solved case
for both timed workflows. Baseline timing must be recorded before exposure
to the corresponding LedgerMatch solution.

Retrospective estimates must be labelled as
`baseline_method = retrospective_estimate` and are excluded from causal
time-improvement claims.

## Validating Results

After all practitioners complete their cases:

```bash
python3 scripts/verify_pilot_result.py examples/pilot-results-template.csv
```

The validator will:
- Check all required columns are present (v2.0 schema).
- Validate data types (booleans, integers, enums, currency codes).
- Reject negative values.
- Reject duplicate pilot case IDs.
- Verify accepted_matches + review_exceptions = deposits_processed.
- Verify genuine_ambiguous_cases ≤ review_exceptions.
- Verify false_automatic_allocations ≤ accepted_matches.
- Verify correct_candidate_retained_cases ≤ candidate_expected_cases.
- Scan ALL text-capable fields for privacy violations.
- Compute median review times (measured only, retrospective reported separately).
- Compute candidate retention rate from numerator/denominator.
- Report unmet minimum sample requirements from real rows only.
- **Fail** if any false automatic allocation is found.
- Never count synthetic rows toward real sample requirements.
- Never count review_exceptions as ambiguous cases.
- Never count currencies as layouts.

## Post-Pilot

1. Collect all result CSVs from practitioners.
2. Merge into a single results file.
3. Run the validator on the merged file.
4. Record the aggregate summary.
5. Delete pilot working copies and generated outputs after the approved
   retention period. Do NOT delete original accounting records.
6. Keep only the validated results summary and validation receipts.
7. Do not commit raw pilot data to any repository.

## What Not to Do

- Do not deploy LedgerMatch to a public server during the pilot.
- Do not allow AI to authorize or post financial allocations.
- Do not claim the pilot passed before actual practitioner data is supplied.
- Do not claim customer demand, compliance, or hosted security.
- Do not weaken or skip the continuation gate.
- Do not instruct practitioners to delete original accounting records.
